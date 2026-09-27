"""Per-domain profile data (schema fields, regulator/escalation path, research
focus, terminology) used to build genuinely domain-aware prompts.

Root cause this fixes: evidence_prompt/strategy_prompt/negotiation_prompt/
review_prompt/research_prompt in health_insurance_agents.py were hardcoded to
health-insurance schemas and language (diagnosis/hospital/IRDAI/Insurance
Ombudsman) but run unconditionally for every domain in case_workflow's graph
-- a banking or airlines case got asked to fill in a "diagnosis" field and
appeal to IRDAI. This module is the single source of truth those prompt
builders pull from instead.
"""
from __future__ import annotations

from app.models.domain import Domain


class DomainProfile:
    def __init__(
        self,
        entity: str,
        counterparty: str,
        regulator: str,
        escalation_path: list[str],
        research_questions: list[str],
        evidence_schema: dict[str, str],
        is_dispute: bool = True,
    ) -> None:
        self.entity = entity
        self.counterparty = counterparty
        self.regulator = regulator
        self.escalation_path = escalation_path
        self.research_questions = research_questions
        self.evidence_schema = evidence_schema
        self.is_dispute = is_dispute


DOMAIN_PROFILES: dict[Domain, DomainProfile] = {
    Domain.HEALTH_INSURANCE: DomainProfile(
        entity="policyholder",
        counterparty="insurer",
        regulator="IRDAI",
        escalation_path=[
            "Internal appeal to the insurer's Grievance Redressal Officer (GRO) -- named on your policy document/insurer's website 'Grievance Redressal' page",
            "IRDAI Bima Bharosa portal (bimabharosa.irdai.gov.in) or IRDAI Grievance Call Centre: 155255 / 1800-4254-732",
            "Insurance Ombudsman -- find your zone's office at cioins.co.in",
        ],
        research_questions=[
            "Which policy clauses apply to this claim?",
            "Which exclusions may the insurer invoke?",
            "Which waiting periods apply?",
            "Which IRDAI regulations or policyholder rights apply?",
        ],
        evidence_schema={
            "diagnosis": "e.g. Lumbar disc herniation L4-L5",
            "treatment": "e.g. Microdiscectomy surgery",
            "hospital": "e.g. Apollo Hospitals, Chennai",
            "coverage_requested": "e.g. Rs 3,50,000 surgery + Rs 45,000 room charges",
            "admission_date": "e.g. 2026-01-15",
            "discharge_date": "e.g. 2026-01-18",
            "bill_amount": "e.g. Rs 4,12,000",
            "reason_for_rejection": "e.g. Pre-existing condition exclusion under clause 4.3",
        },
    ),
    Domain.BANKING: DomainProfile(
        entity="account holder",
        counterparty="bank",
        regulator="RBI Banking Ombudsman",
        escalation_path=[
            "Bank's internal grievance redressal / nodal officer -- contact listed on your bank's website 'Customer Grievance' page and on your passbook/statement",
            "RBI Integrated Ombudsman Scheme: file online at cms.rbi.org.in, or call the RBI complaint toll-free number 14448",
        ],
        research_questions=[
            "Which RBI circulars or chargeback network rules apply?",
            "What is the mandated dispute-resolution timeline?",
            "What fraud/authorization evidence is required (OTP logs, device fingerprint, transaction alerts)?",
            "What does RBI's limited-liability circular say about the customer's liability here?",
        ],
        evidence_schema={
            "transaction_date": "e.g. 2026-01-15",
            "transaction_amount": "e.g. Rs 12,500",
            "transaction_reference": "e.g. UPI/UTR reference number",
            "dispute_type": "e.g. unauthorized transaction / duplicate charge / failed transaction not reversed",
            "bank_response": "e.g. Bank denied the dispute citing customer negligence",
            "amount_at_stake": "e.g. Rs 12,500",
            "reason_for_rejection": "e.g. Bank claims the transaction was authorized via OTP",
        },
    ),
    Domain.AIRLINES: DomainProfile(
        entity="passenger",
        counterparty="airline",
        regulator="DGCA",
        escalation_path=[
            "Airline's customer relations / nodal officer -- contact listed on the airline's website 'Contact Us'/'Nodal Officer' page",
            "AirSewa portal: airsewa.gov.in, or call the AirSewa helpline 1800-11-2124",
            "Consumer forum (National Consumer Helpline 1915 / consumerhelpline.gov.in), if compensation is refused",
        ],
        research_questions=[
            "Which DGCA passenger-rights rules apply (cancellation, delay, denied boarding)?",
            "What compensation or refund is the passenger entitled to under the applicable rules?",
            "What is the airline's stated reason, and does it qualify as an extraordinary circumstance exemption?",
            "What is the refund/compensation claim window?",
        ],
        evidence_schema={
            "flight_number": "e.g. 6E-2134",
            "scheduled_date": "e.g. 2026-01-15",
            "disruption_type": "e.g. cancellation / delay / denied boarding / baggage loss",
            "delay_duration": "e.g. 6 hours",
            "airline_reason_given": "e.g. Technical fault (airline's stated reason)",
            "amount_at_stake": "e.g. Rs 8,500 ticket + Rs 3,000 compensation claimed",
            "reason_for_rejection": "e.g. Airline classified it as a weather-related exemption",
        },
    ),
    Domain.TELECOM: DomainProfile(
        entity="subscriber",
        counterparty="telecom operator",
        regulator="TRAI / Department of Telecommunications",
        escalation_path=[
            "Operator's appellate authority (mandatory first step under TRAI regulations) -- contact listed on the operator's website 'Consumer Grievance' page and on your bill",
            "DoT's Sanchar Saathi portal: sancharsaathi.gov.in, for complaints the operator doesn't resolve",
            "Consumer forum (National Consumer Helpline 1915 / consumerhelpline.gov.in)",
        ],
        research_questions=[
            "Which TRAI regulations govern this billing/service issue?",
            "Do the plan terms and tariff disclosures support the subscriber's claim?",
            "Is there documented evidence of the service outage or billing error?",
            "What is the mandated timeline for the operator's appellate authority to respond?",
        ],
        evidence_schema={
            "account_number": "e.g. subscriber/account ID",
            "billing_cycle": "e.g. Jan 2026",
            "disputed_amount": "e.g. Rs 899",
            "issue_type": "e.g. billing error / service outage / plan mis-selling / porting delay",
            "operator_response": "e.g. Operator says charges are as per plan terms",
            "amount_at_stake": "e.g. Rs 899",
            "reason_for_rejection": "e.g. Operator disputes the outage occurred",
        },
    ),
    Domain.ECOMMERCE: DomainProfile(
        entity="buyer",
        counterparty="seller/platform",
        regulator="Consumer Protection Act, 2019 / National Consumer Helpline",
        escalation_path=[
            "Seller/platform's return-and-refund support -- via the app/website's order help section",
            "National Consumer Helpline: call 1915 or 1800-11-4000, or use the UMANG app / consumerhelpline.gov.in",
            "File a case on the e-daakhil portal (edaakhil.nic.in) with the District Consumer Disputes Redressal Commission",
        ],
        research_questions=[
            "What do the platform's return/warranty terms say, and were they honored?",
            "Does this qualify as a defective, counterfeit, or not-as-described product under consumer protection rules?",
            "Is the buyer still within the return/refund window?",
            "What evidence (photos, order confirmation, seller messages) supports the claim?",
        ],
        evidence_schema={
            "order_id": "e.g. platform order number",
            "order_date": "e.g. 2026-01-15",
            "product": "e.g. wireless headphones",
            "issue_type": "e.g. defective / counterfeit / not as described / not delivered",
            "seller_response": "e.g. Seller refused return citing 'used' condition",
            "amount_at_stake": "e.g. Rs 2,499",
            "reason_for_rejection": "e.g. Platform claims return window has expired",
        },
    ),
    Domain.GOVERNMENT: DomainProfile(
        entity="citizen/applicant",
        counterparty="government department",
        regulator="CPGRAMS (Centralized Public Grievance Redress)",
        escalation_path=[
            "Department's designated Public Grievance Officer -- listed on the department's official website",
            "CPGRAMS portal: pgportal.gov.in",
            "RTI Act request for status via rtionline.gov.in, or appeal to the relevant appellate authority",
        ],
        research_questions=[
            "What is the statutory service-delivery timeline for this application/scheme (e.g. under a state Right to Public Services Act)?",
            "What eligibility criteria and required documents apply?",
            "What grievance or appeal channel applies to this specific department/scheme?",
            "Is an RTI request appropriate to obtain the current file status?",
        ],
        evidence_schema={
            "application_reference": "e.g. application/reference number",
            "application_date": "e.g. 2026-01-15",
            "service_or_scheme": "e.g. passport renewal / ration card / pension scheme",
            "department": "e.g. Regional Passport Office",
            "current_status": "e.g. Stuck in police verification stage",
            "days_pending": "e.g. 90 days",
            "reason_for_delay": "e.g. No reason communicated to applicant",
        },
    ),
    Domain.HOUSING: DomainProfile(
        entity="tenant/homebuyer",
        counterparty="landlord/builder",
        regulator="RERA / local Rent Control Act",
        escalation_path=[
            "Written notice to the landlord/builder with a documented response deadline",
            "State RERA authority complaint (for builder/possession disputes) -- each state runs its own RERA portal, e.g. Maharashtra: maharera.mahaonline.gov.in, Karnataka: rera.karnataka.gov.in; search '[your state] RERA' for others -- or Rent Control/local tribunal (for tenancy disputes)",
            "Consumer forum (National Consumer Helpline 1915 / consumerhelpline.gov.in) or civil court, if unresolved",
        ],
        research_questions=[
            "Which RERA provisions apply (for builder/possession delays) or which local tenancy law applies (for rental disputes)?",
            "What does the lease/sale agreement say about the disputed clause (deposit, possession date, maintenance)?",
            "What evidence (agreement, notices, payment receipts, photos) supports the claim?",
            "What is the compensation or remedy available under RERA or the applicable tenancy law?",
        ],
        evidence_schema={
            "agreement_date": "e.g. 2024-06-01",
            "property_address": "e.g. Flat 4B, XYZ Apartments",
            "issue_type": "e.g. possession delay / deposit deduction / maintenance dispute",
            "promised_date": "e.g. possession promised by Dec 2025",
            "counterparty_response": "e.g. Builder cites force majeure delay",
            "amount_at_stake": "e.g. Rs 25,000 deposit / EMI + rent overlap",
            "reason_for_rejection": "e.g. Builder disputes the RERA-registered timeline applies",
        },
    ),
    Domain.HEALTHCARE: DomainProfile(
        entity="reader",
        counterparty="N/A -- informational domain, not a dispute",
        regulator="N/A",
        escalation_path=[
            "Consult a licensed physician for diagnosis or treatment decisions",
            "For any red-flag/urgent symptoms, seek emergency care immediately: call 112 (national emergency) or 108 (ambulance), or go to the nearest hospital emergency department",
        ],
        research_questions=[
            "What do authoritative clinical/public-health sources (WHO, MedlinePlus, CDC-equivalent guidance) say about this topic?",
            "What are the typical symptoms, causes, and evidence-based treatment or prevention options?",
            "Are there any red-flag symptoms mentioned that warrant urgent/emergency care?",
            "What follow-up questions or context would a clinician need to give personalized advice?",
        ],
        evidence_schema={
            "topic": "e.g. dengue fever symptoms",
            "specific_question": "e.g. When should I see a doctor?",
            "symptoms_mentioned": "e.g. fever, joint pain, rash (leave empty if none mentioned)",
            "duration_mentioned": "e.g. 3 days (leave empty if not mentioned)",
            "urgency_flags": "e.g. none identified / mentions bleeding or breathing difficulty",
        },
        is_dispute=False,
    ),
}

DEFAULT_PROFILE = DomainProfile(
    entity="consumer",
    counterparty="counterparty",
    regulator="the relevant sector regulator",
    escalation_path=[
        "Counterparty's internal grievance channel",
        "Relevant sector regulator, or the National Consumer Helpline: call 1915 / 1800-11-4000 or visit consumerhelpline.gov.in",
    ],
    research_questions=["What rules, regulations, or contractual terms apply to this dispute?"],
    evidence_schema={"issue_summary": "e.g. brief summary of the dispute", "amount_at_stake": "e.g. Rs 0"},
)


def get_profile(domain: Domain) -> DomainProfile:
    return DOMAIN_PROFILES.get(domain, DEFAULT_PROFILE)
