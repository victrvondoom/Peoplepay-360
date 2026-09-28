from enum import Enum


class Domain(str, Enum):
    HEALTH_INSURANCE = "health_insurance"
    BANKING = "banking"
    TELECOM = "telecom"
    AIRLINES = "airlines"
    HEALTHCARE_PROVIDER = "healthcare_provider"
    HOUSING = "housing"
    ECOMMERCE = "ecommerce"
    GOVERNMENT = "government"
    HEALTHCARE = "healthcare"


ACTIVE_DOMAINS = {Domain.HEALTH_INSURANCE, Domain.BANKING, Domain.AIRLINES, Domain.TELECOM, Domain.ECOMMERCE, Domain.GOVERNMENT, Domain.HOUSING, Domain.HEALTHCARE}

DOMAIN_LABELS = {
    Domain.HEALTH_INSURANCE: "Health insurance claim denials and reimbursement disputes",
    Domain.BANKING: "Banking, credit card, chargeback, and unauthorized transaction disputes",
    Domain.TELECOM: "Telecom, broadband, billing, and contract disputes",
    Domain.AIRLINES: "Airline refunds, cancellation, delay, and baggage claims",
    Domain.HEALTHCARE_PROVIDER: "Hospital billing, medical records, and provider charge disputes",
    Domain.HOUSING: "Rental/landlord-tenant disputes, RERA builder complaints, property registration, society/maintenance, and home loan documentation",
    Domain.ECOMMERCE: "Refund, warranty, defective product, and seller disputes",
    Domain.GOVERNMENT: "Public grievance, RTI, certificate, scheme, and administrative appeals",
    Domain.HEALTHCARE: "Educational, evidence-based public health information: diseases, symptoms, preventive care, vaccination, clinical guidelines, lab reference ranges, drug safety, and patient rights. Not diagnostic and not a substitute for professional medical advice.",
}
