"""
Document relevance checker.
Uses fast keyword matching to decide if an uploaded document is relevant
to the dispute domain. If not, we skip vector-indexing it and warn the user.
"""
import re
from app.models.domain import Domain

# ── Per-domain keyword sets ──────────────────────────────────────────────────

_DOMAIN_KEYWORDS: dict[Domain, set[str]] = {
    Domain.HEALTH_INSURANCE: {
        "insurance", "policy", "claim", "denial", "reimbursement", "premium",
        "cashless", "hospital", "diagnosis", "treatment", "coverage", "irdai",
        "deductible", "sum insured", "mediclaim", "pre-auth", "preauthorization",
        "discharge", "patient", "doctor", "surgery", "procedure", "network",
        "tpa", "third party administrator", "health", "medical",
    },
    Domain.BANKING: {
        "bank", "account", "credit card", "debit card", "upi", "neft", "rtgs",
        "imps", "emi", "loan", "interest", "atm", "chargeback", "fraud",
        "unauthorized", "transaction", "statement", "kyc", "rbi", "ombudsman",
        "cheque", "npa", "overdraft", "ifsc", "savings", "current account",
        "fixed deposit", "fd", "recurring", "bank transfer", "invoice",
    },
    Domain.AIRLINES: {
        "flight", "airline", "ticket", "boarding", "pnr", "passenger",
        "baggage", "luggage", "delay", "cancellation", "refund", "dgca",
        "airport", "check-in", "departure", "arrival", "booking", "itinerary",
        "seat", "cargo", "denied boarding", "compensation", "indigo", "air india",
        "spicejet", "akasa", "vistara", "cabin", "iata", "montreal", "charter",
    },
    Domain.TELECOM: {
        "telecom", "mobile", "sim", "recharge", "plan", "data", "broadband",
        "fiber", "internet", "trai", "airtel", "jio", "bsnl", "vodafone", "vi",
        "mnp", "portability", "bill", "billing", "vas", "call drop", "network",
        "signal", "roaming", "4g", "5g", "prepaid", "postpaid", "operator",
        "subscriber", "tariff", "dot", "telecom",
    },
    Domain.ECOMMERCE: {
        "order", "product", "delivery", "refund", "return", "exchange",
        "shipment", "courier", "amazon", "flipkart", "myntra", "meesho",
        "ajio", "blinkit", "zepto", "bigbasket", "seller", "marketplace",
        "invoice", "warranty", "fake", "counterfeit", "wrong product",
        "cancellation", "consumer", "complaint", "tracking", "package",
        "otp delivery", "undelivered", "customer support",
    },
    Domain.HOUSING: {
        "rent", "rental", "landlord", "tenant", "lease", "rera", "builder",
        "possession", "society", "maintenance", "deposit", "eviction",
        "property", "registration", "sale deed", "apartment", "flat",
        "construction", "occupancy", "noc", "home loan", "mortgage",
        "stamp duty", "allotment", "carpet area", "encumbrance", "tenancy",
        "housing society", "co-operative",
    },
    Domain.GOVERNMENT: {
        "rti", "right to information", "grievance", "certificate", "scheme",
        "application", "government", "department", "ministry", "office",
        "ration card", "aadhaar", "pan card", "passport", "license",
        "municipal", "panchayat", "taluk", "collector", "public",
        "administrative", "appeal", "pension", "subsidy", "welfare",
        "notice", "gazette", "affidavit", "district magistrate",
    },
    Domain.HEALTHCARE: {
        "disease", "symptom", "vaccination", "vaccine", "clinical", "lab",
        "laboratory", "reference range", "drug", "medication", "patient",
        "diagnosis", "treatment", "prescription", "hospital", "doctor",
        "medical", "health", "prevention", "screening", "test result",
        "immunization", "dosage", "side effect", "clinical guideline",
    },
}

# Generic "noise" documents we always reject regardless of domain
_IRRELEVANT_STRONG_SIGNALS = {
    "internship certificate", "completion certificate", "marksheet",
    "admit card", "hall ticket", "offer letter", "resume", "curriculum vitae",
    "cv", "passport", "aadhaar", "pan card", "birth certificate",
    "school certificate", "degree certificate", "graduation", "convocation",
    "employment letter", "salary slip", "payslip", "caste certificate",
    "domicile certificate", "marriage certificate", "death certificate",
}

MIN_RELEVANCE_SCORE = 2   # how many keyword hits needed to pass


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower())


def check_document_relevance(
    text: str,
    domain: Domain,
    filename: str = "",
) -> tuple[bool, str]:
    """
    Returns (is_relevant: bool, reason: str).

    Fast path: if the filename or first 300 chars contain a strong
    irrelevant signal, reject immediately.

    Otherwise: count domain keyword hits in the first 3000 chars
    of the text. If hits < MIN_RELEVANCE_SCORE, reject.
    """
    combined = _normalise(f"{filename} {text[:3000]}")

    # Hard reject on obvious unrelated docs
    for signal in _IRRELEVANT_STRONG_SIGNALS:
        if signal in combined:
            return (
                False,
                f"The uploaded document appears to be a '{signal}'. "
                f"Please upload evidence relevant to your {domain.value} dispute "
                f"(e.g. invoices, policy documents, transaction records, correspondence).",
            )

    keywords = _DOMAIN_KEYWORDS.get(domain, set())
    hits = sum(1 for kw in keywords if kw in combined)

    if hits >= MIN_RELEVANCE_SCORE:
        return True, "Document is relevant."

    # One final fallback: if hits==1 and text is very short, still accept
    if hits == 1 and len(text.strip()) < 500:
        return True, "Short document accepted with partial match."

    return (
        False,
        f"The uploaded document does not appear to be related to your "
        f"{domain.value.replace('_', ' ')} dispute. Found {hits} relevant keyword(s), "
        f"need at least {MIN_RELEVANCE_SCORE}. "
        f"Please upload documents such as bills, invoices, policy papers, "
        f"correspondence with the company, or complaint acknowledgements.",
    )
