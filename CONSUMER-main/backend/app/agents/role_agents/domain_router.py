"""Global Domain Router — classifies a raw user query against all active
domains instead of requiring the caller to pick one upfront.

Deterministic (keyword-scored), matching the existing supervisor/planner
philosophy of not spending an LLM call on orchestration decisions. Supports
multi-domain classification: a query like "My flight was cancelled and my
travel insurance rejected the claim" should surface both Domain.AIRLINES and
Domain.HEALTH_INSURANCE so the caller can run both workflows and merge them.
"""
from __future__ import annotations

import difflib
import re

from app.agents.role_agents.planner import (
    BANK_CARD_TERMS, BANK_LOAN_TERMS, BANK_PAYMENT_TERMS, BANK_REG_TERMS,
    CLAIM_TERMS, POLICY_TERMS, MEDICAL_TERMS,
    TELECOM_BILLING_TERMS, TELECOM_NETWORK_TERMS, TELECOM_MNP_TERMS, TELECOM_REG_TERMS,
    ECOMMERCE_CONSUMER_TERMS, ECOMMERCE_RETURN_TERMS, ECOMMERCE_MARKETPLACE_TERMS,
    ECOMMERCE_DELIVERY_TERMS, ECOMMERCE_WARRANTY_TERMS,
    GOVT_IDENTITY_TERMS, GOVT_TRAVEL_TERMS, GOVT_CERTIFICATE_TERMS, GOVT_TRANSPORT_TERMS,
    GOVT_PROPERTY_TERMS, GOVT_PENSION_TERMS, GOVT_GRIEVANCE_TERMS, GOVT_GENERAL_TERMS,
    HOUSING_RENTAL_TERMS, HOUSING_RERA_TERMS, HOUSING_REGISTRATION_TERMS, HOUSING_TAX_TERMS,
    HOUSING_SOCIETY_TERMS, HOUSING_LOAN_TERMS, HOUSING_CONSUMER_TERMS, HOUSING_GENERAL_TERMS,
    HEALTHCARE_DISEASE_TERMS, HEALTHCARE_PREVENTIVE_TERMS, HEALTHCARE_GUIDELINE_TERMS,
    HEALTHCARE_DRUG_TERMS, HEALTHCARE_LAB_TERMS, HEALTHCARE_PATIENT_RIGHTS_TERMS,
    HEALTHCARE_PUBLIC_HEALTH_TERMS, HEALTHCARE_HOSPITAL_QUALITY_TERMS, HEALTHCARE_GENERAL_TERMS,
)
from app.agents.state import AgentState
from app.models.domain import ACTIVE_DOMAINS, Domain

AIRLINE_TERMS = {
    "flight", "airline", "airfare", "boarding", "baggage", "luggage", "dgca", "ticket",
    "aviation", "delay", "cancellation", "cancelled", "canceled", "overbooking",
    "denied boarding", "connection", "layover", "check-in", "pnr", "air india",
    "indigo", "spicejet", "vistara", "akasa", "wheelchair", "refund fare",
}

DOMAIN_KEYWORDS: dict[Domain, set[str]] = {
    # LEGAL_TERMS (rights, complaint, law, appeal, rule, grievance, regulation,
    # circular) used to be folded in here, but it's generic dispute
    # vocabulary that applies to every domain, not health-insurance-specific
    # -- it gave health_insurance a structural home-field advantage over
    # every other domain (e.g. "what are my legal rights" alone would win
    # health_insurance even for a housing/construction dispute) since no
    # other domain's keyword set included it.
    Domain.HEALTH_INSURANCE: CLAIM_TERMS | POLICY_TERMS | MEDICAL_TERMS
    | {"health insurance", "insurer", "insurance", "irdai", "mediclaim", "tpa"},
    Domain.BANKING: BANK_CARD_TERMS | BANK_LOAN_TERMS | BANK_PAYMENT_TERMS | BANK_REG_TERMS
    | {"bank", "banking", "savings account", "current account", "cheque", "neft", "rtgs", "imps"},
    Domain.AIRLINES: AIRLINE_TERMS,
    Domain.TELECOM: TELECOM_BILLING_TERMS | TELECOM_NETWORK_TERMS | TELECOM_MNP_TERMS | TELECOM_REG_TERMS
    | {"telecom", "mobile network", "operator", "postpaid", "prepaid"},
    Domain.ECOMMERCE: ECOMMERCE_CONSUMER_TERMS | ECOMMERCE_RETURN_TERMS | ECOMMERCE_MARKETPLACE_TERMS
    | ECOMMERCE_DELIVERY_TERMS | ECOMMERCE_WARRANTY_TERMS | {"ecommerce", "online order", "online shopping"},
    Domain.GOVERNMENT: GOVT_IDENTITY_TERMS | GOVT_TRAVEL_TERMS | GOVT_CERTIFICATE_TERMS
    | GOVT_TRANSPORT_TERMS | GOVT_PROPERTY_TERMS | GOVT_PENSION_TERMS | GOVT_GRIEVANCE_TERMS
    | GOVT_GENERAL_TERMS,
    Domain.HOUSING: HOUSING_RENTAL_TERMS | HOUSING_RERA_TERMS | HOUSING_REGISTRATION_TERMS
    | HOUSING_TAX_TERMS | HOUSING_SOCIETY_TERMS | HOUSING_LOAN_TERMS | HOUSING_CONSUMER_TERMS
    | HOUSING_GENERAL_TERMS,
    Domain.HEALTHCARE: HEALTHCARE_DISEASE_TERMS | HEALTHCARE_PREVENTIVE_TERMS | HEALTHCARE_GUIDELINE_TERMS
    | HEALTHCARE_DRUG_TERMS | HEALTHCARE_LAB_TERMS | HEALTHCARE_PATIENT_RIGHTS_TERMS
    | HEALTHCARE_PUBLIC_HEALTH_TERMS | HEALTHCARE_HOSPITAL_QUALITY_TERMS | HEALTHCARE_GENERAL_TERMS,
}

# Terms that are strong, low-ambiguity signals for their domain — a single hit
# is enough to include the domain as a candidate even alongside a
# higher-scoring domain, which is what makes genuine multi-domain queries work
# (e.g. "insurance" alone shouldn't need three other health-insurance words to
# also fire alongside a strongly-matched Airlines query).
STRONG_SIGNAL_TERMS: dict[Domain, set[str]] = {
    Domain.HEALTH_INSURANCE: {"insurance", "insurer", "health insurance", "mediclaim", "irdai", "claim denied", "cashless"},
    Domain.BANKING: {"bank", "banking", "rbi", "chargeback", "credit card", "debit card"},
    Domain.AIRLINES: {"flight", "airline", "dgca", "baggage", "boarding"},
    Domain.TELECOM: {"telecom", "trai", "sim", "broadband", "recharge"},
    Domain.ECOMMERCE: {"amazon", "flipkart", "ecommerce", "online order", "seller"},
    Domain.GOVERNMENT: {"aadhaar", "passport", "rti", "cpgrams", "pan card"},
    Domain.HOUSING: {"rera", "landlord", "tenant", "builder", "property registration", "construction", "possession"},
    Domain.HEALTHCARE: {"symptom", "symptoms", "vaccine", "vaccination", "who", "mohfw", "dengue", "diagnosis"},
}


def _term_matches(term: str, text: str) -> bool:
    """Word-boundary match so short generic terms (e.g. "act") don't
    spuriously match as a substring of an unrelated word (e.g. "transaction")."""
    return re.search(rf"\b{re.escape(term)}\b", text) is not None


def _fuzzy_term_matches(term: str, words: set[str]) -> bool:
    """Typo-tolerant fallback for single-word terms only -- real user text is
    full of typos ("constuction", "legel rigts"), and those would otherwise
    never match anything and fall through to the (previously dishonest)
    zero-match fallback. Multi-word phrases and short terms (<5 chars, where
    a fuzzy match is more likely to be coincidental) are skipped."""
    if " " in term or len(term) < 5:
        return False
    return bool(difflib.get_close_matches(term, words, n=1, cutoff=0.82))


def classify_domains(query: str, max_domains: int = 3, min_relative_score: float = 0.55) -> list[dict]:
    """Score every active domain against the query and return ranked candidates.

    The top match is always included. A secondary domain is included only if
    it BOTH scores at least `min_relative_score` of the top domain's score
    AND has at least one strong, unambiguous signal term (STRONG_SIGNAL_TERMS)
    -- not just incidental overlap on a generic word shared across domains
    (e.g. "charged", "refund", "complaint"). Previously a single weak hit
    was enough on its own (base score floor of 0.2, relative threshold of
    0.4), which meant a plain banking query like "my bank charged me twice"
    could pull in Telecom or E-commerce as a full duplicate analysis purely
    because they share generic billing vocabulary, with zero domain-specific
    signal behind the match.
    """
    text = query.lower()
    words = set(re.findall(r"[a-z]+", text))
    scored: list[dict] = []
    for domain in ACTIVE_DOMAINS:
        terms = DOMAIN_KEYWORDS.get(domain, set())
        exact_hits = {t for t in terms if _term_matches(t, text)}
        fuzzy_hits = {t for t in terms if t not in exact_hits and _fuzzy_term_matches(t, words)}
        hits = sorted(exact_hits | fuzzy_hits, key=len, reverse=True)
        if not hits:
            continue
        strong_hits = [t for t in hits if t in STRONG_SIGNAL_TERMS.get(domain, set())]
        # Base score from breadth of matches, bonus for strong/unambiguous
        # terms; fuzzy-only matches count for less than an exact hit since
        # they're inherently less certain.
        score = min(1.0, 0.2 + 0.12 * len(exact_hits) + 0.06 * len(fuzzy_hits) + 0.15 * len(strong_hits))
        scored.append({
            "domain": domain,
            "confidence": round(score, 3),
            "matched_terms": hits[:8],
            "_strong_hits": strong_hits,
        })

    if not scored:
        # Genuinely nothing matched, even fuzzily -- don't pretend to have
        # confidently detected a specific domain (this used to always claim
        # "health_insurance" regardless of content). confidence 0.0 plus
        # fallback=True tells the caller/UI this isn't a real detection; the
        # domain is still populated so downstream code that indexes
        # candidates[0] doesn't break, but nothing should present this as
        # "detected".
        return [{
            "domain": Domain.HEALTH_INSURANCE,
            "confidence": 0.0,
            "matched_terms": [],
            "fallback": True,
        }]

    scored.sort(key=lambda item: item["confidence"], reverse=True)
    top_score = scored[0]["confidence"]
    selected = [scored[0]]
    for candidate in scored[1:]:
        if len(selected) >= max_domains:
            break
        if candidate["_strong_hits"] and candidate["confidence"] >= top_score * min_relative_score:
            selected.append(candidate)
    for candidate in selected:
        candidate.pop("_strong_hits", None)
    return selected


async def classify_domains_multilingual(query: str, max_domains: int = 3, min_relative_score: float = 0.55) -> list[dict]:
    """classify_domains() only recognizes ASCII a-z keywords -- any query
    with no English-keyword overlap produces zero hits and silently falls
    back to a hardcoded HEALTH_INSURANCE default with confidence 0.0.
    Confirmed live: a Tamil query about a cancelled flight got analyzed as
    a health insurance pre-existing-condition case, completely unrelated to
    what was actually asked, because classification failed before the real
    pipeline ever ran.

    Deliberately does NOT branch on script/character-set (e.g. "is this
    mostly non-ASCII") -- that heuristic correctly catches Tamil/Hindi/
    Chinese/Japanese/Arabic (non-Latin scripts) but silently misses
    Portuguese, Spanish, French, German, and Italian, which are written in
    the same Latin alphabet as English and would score as "mostly ASCII"
    while still having zero real keyword overlap. Instead: always try the
    fast, free, zero-LLM-call keyword classifier first -- it correctly
    handles English (the common case) with no added latency at all -- and
    only fall back to translating when it genuinely found nothing, which is
    the actual signal that the query wasn't in English, regardless of what
    script or language it's actually written in."""
    candidates = classify_domains(query, max_domains, min_relative_score)
    if not candidates[0].get("fallback"):
        return candidates
    try:
        from app.llm.service import llm_service

        prompt = (
            "Translate the following text to English for classification purposes only. "
            "Return ONLY the English translation, no commentary, no quotes:\n\n" + query[:2000]
        )
        translated = await llm_service.generate(prompt, temperature=0.0, purpose="router")
        translated = translated.strip()
    except Exception:
        translated = ""
    if not translated:
        return candidates
    return classify_domains(translated, max_domains, min_relative_score)


async def run_domain_router_agent(state: AgentState) -> AgentState:
    """Populate state["candidate_domains"] and default state["domain"] to the
    top candidate when the caller hasn't already pinned one explicitly."""
    query = state.get("case_summary", "")
    candidates = await classify_domains_multilingual(query)
    state["candidate_domains"] = candidates
    if not state.get("domain"):
        state["domain"] = candidates[0]["domain"]
    state.setdefault("agent_trace", []).append(
        "domain_router:" + ",".join(f"{c['domain'].value}:{c['confidence']}" for c in candidates)
    )
    return state
