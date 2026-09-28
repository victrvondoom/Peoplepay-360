from app.agents.state import AgentState
from app.models.domain import Domain

CLAIM_TERMS = {"claim", "denial", "denied", "cashless", "reimbursement", "settlement", "preauth", "pre-authorisation", "preauthorization", "hospital bill"}
POLICY_TERMS = {"cover", "covered", "coverage", "policy", "exclusion", "waiting period", "room rent", "sum insured", "rider", "add-on", "deductible"}
MEDICAL_TERMS = {"surgery", "disease", "diagnosis", "treatment", "procedure", "cataract", "cancer", "diabetes", "mri", "ct scan", "ayush"}
LEGAL_TERMS = {"irdai", "regulation", "circular", "ombudsman", "grievance", "complaint", "rights", "rule", "law", "appeal"}
FAQ_TERMS = {"how", "what", "when", "where", "who", "faq", "general", "explain"}

# Banking terms
BANK_CARD_TERMS = {"card", "credit", "debit", "chargeback", "merchant", "fraud", "unauthorized", "cvv", "otp", "atm"}
BANK_LOAN_TERMS = {"loan", "emi", "interest", "foreclosure", "rate", "penalty"}
BANK_PAYMENT_TERMS = {"upi", "payment", "gateway", "failed", "double debit", "account", "transfer", "kyc"}
BANK_REG_TERMS = {"rbi", "regulation", "circular", "ombudsman", "rule", "complaint", "cms", "npci"}

# Telecom terms
TELECOM_BILLING_TERMS = {"bill", "billing", "recharge", "deduction", "vas", "balance", "roaming", "invoice", "charge", "refund", "overcharge"}
TELECOM_NETWORK_TERMS = {"network", "signal", "speed", "internet", "broadband", "fiber", "call drop", "slow", "data", "4g", "5g", "connectivity"}
TELECOM_MNP_TERMS = {"mnp", "port", "portability", "sim", "activation", "number", "transfer", "upc"}
TELECOM_REG_TERMS = {"trai", "dot", "tdsat", "telecom", "operator", "airtel", "jio", "vi", "bsnl", "vodafone"}

# E-Commerce terms
ECOMMERCE_CONSUMER_TERMS = {"consumer", "ccpa", "rights", "act", "law", "court", "nch", "ondc"}
ECOMMERCE_RETURN_TERMS = {"return", "refund", "exchange", "cancellation", "reject", "deny"}
ECOMMERCE_MARKETPLACE_TERMS = {"amazon", "flipkart", "myntra", "ajio", "meesho", "jiomart", "blinkit", "zepto", "bigbasket", "account", "block", "policy"}
ECOMMERCE_DELIVERY_TERMS = {"delivery", "courier", "missing", "package", "delay", "damaged", "otp", "shipment"}
ECOMMERCE_WARRANTY_TERMS = {"warranty", "fake", "counterfeit", "seller", "defective", "wrong", "fraud"}

# Government terms
GOVT_IDENTITY_TERMS = {"aadhaar", "uidai", "pan", "nsdl", "protean", "digilocker", "e-kyc", "ekyc", "biometric"}
GOVT_TRAVEL_TERMS = {"passport", "tatkal", "reissue", "police verification", "rpo", "psk", "visa"}
GOVT_CERTIFICATE_TERMS = {"income certificate", "caste certificate", "birth certificate", "death certificate", "domicile", "tahsildar", "e-district"}
GOVT_TRANSPORT_TERMS = {"driving licence", "driving license", "learner", "rto", "parivahan", "sarathi", "vahan", "vehicle registration", "rc transfer"}
GOVT_PROPERTY_TERMS = {"property registration", "sub-registrar", "sale deed", "stamp duty", "mutation", "land record", "khatauni", "encumbrance"}
GOVT_PENSION_TERMS = {"pension", "epfo", "epf", "pf withdrawal", "nps", "pfrda", "ration card", "pds", "dbt"}
GOVT_GRIEVANCE_TERMS = {"cpgrams", "rti", "grievance", "appeal", "pio", "public information officer", "ombudsman", "escalate", "escalation"}
GOVT_GENERAL_TERMS = {"government", "govt", "ministry", "department", "scheme", "e-sevai", "meeseva", "seva kendra", "national consumer helpline"}

# Housing terms
HOUSING_RENTAL_TERMS = {"rent", "rental", "lease", "tenant", "landlord", "deposit", "eviction", "lock-out", "vacate", "tenancy"}
HOUSING_RERA_TERMS = {"rera", "builder", "promoter", "possession", "delay", "construction", "occupancy certificate", "completion certificate", "defect", "seepage", "crack"}
HOUSING_REGISTRATION_TERMS = {"registration", "sub-registrar", "sale deed", "stamp duty", "encumbrance", "mutation", "survey number"}
HOUSING_TAX_TERMS = {"property tax", "assessment", "municipal", "tax classification"}
HOUSING_SOCIETY_TERMS = {"society", "maintenance", "rwa", "managing committee", "noc", "corpus fund", "cooperative"}
HOUSING_LOAN_TERMS = {"home loan", "foreclosure", "emi", "mortgage", "disbursement", "loan documents"}
HOUSING_CONSUMER_TERMS = {"ncdrc", "consumer court", "consumer forum", "national consumer helpline"}
HOUSING_GENERAL_TERMS = {"housing", "mohua", "pmay", "apartment", "villa", "plot", "flat"}

# Healthcare terms (public health education domain)
HEALTHCARE_DISEASE_TERMS = {"symptom", "symptoms", "disease", "fever", "dengue", "malaria", "tuberculosis", "tb", "diabetes", "hypertension", "flu", "influenza", "covid", "diarrhea", "diarrhoea", "infection", "illness", "cough", "cold"}
HEALTHCARE_PREVENTIVE_TERMS = {"vaccine", "vaccination", "immunization", "immunisation", "booster", "screening", "preventive", "prevention"}
HEALTHCARE_GUIDELINE_TERMS = {"guideline", "guidelines", "standard treatment", "treatment protocol", "clinical practice", "evidence-based", "treatment approach"}
HEALTHCARE_DRUG_TERMS = {"medicine", "medication", "drug", "dosage", "dose", "interaction", "side effect", "adverse reaction", "generic", "cdsco", "pharmacovigilance", "prescription"}
HEALTHCARE_LAB_TERMS = {"lab test", "lab report", "blood test", "hba1c", "cholesterol", "lft", "kft", "egfr", "cbc", "reference range", "test result", "tsh"}
HEALTHCARE_PATIENT_RIGHTS_TERMS = {"patient rights", "informed consent", "medical records", "discharge summary", "second opinion", "confidentiality", "itemized bill", "grievance"}
HEALTHCARE_PUBLIC_HEALTH_TERMS = {"outbreak", "advisory", "epidemic", "surveillance", "public health", "ncdc", "idsp"}
HEALTHCARE_HOSPITAL_QUALITY_TERMS = {"nabh", "accreditation", "hospital quality", "infection control"}
HEALTHCARE_GENERAL_TERMS = {"health", "healthcare", "medical", "hospital", "doctor", "ayushman bharat", "pmjay", "who", "mohfw", "icmr"}


def _contains(text: str, terms: set[str]) -> bool:
    return any(term in text for term in terms)


def build_plan(state: AgentState) -> dict:
    query = state.get("case_summary", "").lower()
    domain = state.get("domain", Domain.HEALTH_INSURANCE)
    specialists: list[str] = []

    if domain == Domain.BANKING:
        if _contains(query, BANK_CARD_TERMS):
            specialists.append("cards")
        if _contains(query, BANK_LOAN_TERMS):
            specialists.append("loans")
        if _contains(query, BANK_PAYMENT_TERMS):
            specialists.append("payments")
        if _contains(query, BANK_REG_TERMS):
            specialists.append("regulatory")
    elif domain == Domain.AIRLINES:
        AIRLINE_DELAY_TERMS = {"delay", "cancel", "cancellation", "missed", "connection", "overbooking", "denied", "boarding", "schedule"}
        AIRLINE_BAGGAGE_TERMS = {"baggage", "luggage", "lost", "damaged", "pir", "weight", "cabin", "check-in"}
        AIRLINE_REFUND_TERMS = {"refund", "ticket", "fare", "fee", "charge", "name correction", "duplicate"}
        AIRLINE_GEN_TERMS = {"dgca", "charter", "wheelchair", "complaint", "support", "insurance"}
        
        if _contains(query, AIRLINE_DELAY_TERMS):
            specialists.append("delay_cancellation")
        if _contains(query, AIRLINE_BAGGAGE_TERMS):
            specialists.append("baggage")
        if _contains(query, AIRLINE_REFUND_TERMS):
            specialists.append("refund_ticketing")
        if _contains(query, AIRLINE_GEN_TERMS):
            specialists.append("general_aviation")
    elif domain == Domain.TELECOM:
        if _contains(query, TELECOM_BILLING_TERMS):
            specialists.append("billing_disputes")
        if _contains(query, TELECOM_NETWORK_TERMS):
            specialists.append("network_quality")
        if _contains(query, TELECOM_MNP_TERMS):
            specialists.append("mnp_portability")
        if _contains(query, TELECOM_REG_TERMS):
            specialists.append("trai_regulatory")
    elif domain == Domain.ECOMMERCE:
        if _contains(query, ECOMMERCE_CONSUMER_TERMS):
            specialists.append("consumer_protection")
        if _contains(query, ECOMMERCE_RETURN_TERMS):
            specialists.append("returns_refunds")
        if _contains(query, ECOMMERCE_MARKETPLACE_TERMS):
            specialists.append("marketplace_policy")
        if _contains(query, ECOMMERCE_DELIVERY_TERMS):
            specialists.append("delivery_logistics")
        if _contains(query, ECOMMERCE_WARRANTY_TERMS):
            specialists.append("warranty_seller")
    elif domain == Domain.GOVERNMENT:
        if _contains(query, GOVT_IDENTITY_TERMS):
            specialists.append("identity_documents")
        if _contains(query, GOVT_TRAVEL_TERMS):
            specialists.append("travel_documents")
        if _contains(query, GOVT_CERTIFICATE_TERMS):
            specialists.append("civil_certificates")
        if _contains(query, GOVT_TRANSPORT_TERMS):
            specialists.append("transport_licensing")
        if _contains(query, GOVT_PROPERTY_TERMS):
            specialists.append("property_land_records")
        if _contains(query, GOVT_PENSION_TERMS):
            specialists.append("pensions_welfare")
        if _contains(query, GOVT_GRIEVANCE_TERMS):
            specialists.append("grievance_rti")
        if _contains(query, GOVT_GENERAL_TERMS):
            specialists.append("general_government")
        if not specialists:
            specialists.append("general_government")
    elif domain == Domain.HOUSING:
        if _contains(query, HOUSING_RENTAL_TERMS):
            specialists.append("rental_tenancy")
        if _contains(query, HOUSING_RERA_TERMS):
            specialists.append("rera_builder")
        if _contains(query, HOUSING_REGISTRATION_TERMS):
            specialists.append("property_registration")
        if _contains(query, HOUSING_TAX_TERMS):
            specialists.append("property_tax")
        if _contains(query, HOUSING_SOCIETY_TERMS):
            specialists.append("apartment_society")
        if _contains(query, HOUSING_LOAN_TERMS):
            specialists.append("home_loan")
        if _contains(query, HOUSING_CONSUMER_TERMS):
            specialists.append("consumer_escalation")
        if _contains(query, HOUSING_GENERAL_TERMS):
            specialists.append("general_housing")
        if not specialists:
            specialists.append("general_housing")
    elif domain == Domain.HEALTHCARE:
        if _contains(query, HEALTHCARE_DISEASE_TERMS):
            specialists.append("disease_symptom_info")
        if _contains(query, HEALTHCARE_PREVENTIVE_TERMS):
            specialists.append("preventive_care_vaccination")
        if _contains(query, HEALTHCARE_GUIDELINE_TERMS):
            specialists.append("clinical_guidelines")
        if _contains(query, HEALTHCARE_DRUG_TERMS):
            specialists.append("drug_safety")
        if _contains(query, HEALTHCARE_LAB_TERMS):
            specialists.append("lab_diagnostics")
        if _contains(query, HEALTHCARE_PATIENT_RIGHTS_TERMS):
            specialists.append("patient_rights")
        if _contains(query, HEALTHCARE_PUBLIC_HEALTH_TERMS):
            specialists.append("public_health_advisory")
        if _contains(query, HEALTHCARE_HOSPITAL_QUALITY_TERMS):
            specialists.append("hospital_quality")
        if _contains(query, HEALTHCARE_GENERAL_TERMS):
            specialists.append("general_healthcare")
        if not specialists:
            specialists.append("general_healthcare")
    else:
        # Default/Health Insurance
        if _contains(query, CLAIM_TERMS):
            specialists.append("claims")
        if _contains(query, POLICY_TERMS):
            specialists.append("policy")
        if _contains(query, MEDICAL_TERMS):
            specialists.append("medical")
        if _contains(query, LEGAL_TERMS):
            specialists.append("legal")

    if not specialists:
        specialists.append("faq")
    if _contains(query, FAQ_TERMS) and len(specialists) == 0:
        specialists.append("faq")

    needs_graph = bool(state.get("institution_name"))
    needs_web = any(term in query for term in ["latest", "today", "current", "new circular", "recent"])

    return {
        "route": specialists[0],
        "specialists": specialists[:3],
        "tools": {
            "retrieval": True,
            "knowledge_graph": needs_graph,
            "web_search": needs_web,
            "negotiator": len(specialists) > 1,
        },
        "reason": f"Routed to {', '.join(specialists)} based on query intent for domain {domain.value}.",
    }


async def run_planner_agent(state: AgentState) -> AgentState:
    plan = build_plan(state)
    state["plan"] = plan
    state["route"] = plan["route"]
    state.setdefault("agent_trace", []).append(f"planner:{plan['route']}")
    return state
