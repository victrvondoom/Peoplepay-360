"""
Housing Domain - Specialist Agents
Routes to: rental_tenancy, rera_builder, property_registration, property_tax,
apartment_society, home_loan, consumer_escalation, general_housing
"""
import logging
from typing import Dict, Any
from app.agents.json_parser import parse_agent_json
from app.llm.service import llm_service
from app.models.domain import Domain
from app.rag.retrieval.qdrant_service import qdrant_service
from app.services.citation_verification import verify_claims

logger = logging.getLogger(__name__)

# Running specialist agents against retrieved regulations and the user's own
# evidence only pays off if the answer is a complete, usable resolution --
# not a shallow reply that just says "consult a lawyer" or asks for more
# documents before it'll help, which is indistinguishable from a plain
# chatbot and defeats the reason to run agents at all.
COMPLETENESS_MANDATE = (
    "Before answering: your \"analysis\" and \"action_plan\" must form a complete, usable resolution "
    "built from what's available now, not a request for more information as the primary answer. Name "
    "the specific RERA provision, tenancy act section, or society bye-law from the Regulatory & "
    "Procedural Context above (not \"relevant housing rules\"). Give the exact escalation channel -- "
    "State RERA Authority portal (e.g. Maharashtra: maharera.mahaonline.gov.in, Karnataka: "
    "rera.karnataka.gov.in -- name the correct one for the state mentioned, or say 'search [state] RERA "
    "portal' if the state isn't given) or Rent Authority/Registrar, then Consumer Forum (National "
    "Consumer Helpline 1915 / consumerhelpline.gov.in) -- with what each step requires. If an exact date "
    "or amount is missing from the query and evidence, give the complete plan for the most likely "
    "scenario and note what to confirm in one line, rather than stopping to ask."
)


class HousingSpecialistAgent:
    def __init__(self, name: str, focus: str, system_prompt: str):
        self.name = name
        self.focus = focus
        self.system_prompt = system_prompt

    async def process(self, context: Dict[str, Any]) -> Dict[str, Any]:
        query = context.get("case_summary", "")
        evidence_bundle = context.get("evidence_bundle", "")

        results = await qdrant_service.search_chunks(
            Domain.HOUSING, f"{self.focus}: {query}", top_k=5
        )
        context_text = "\n\n".join(r.get("text", "") for r in results)

        evidence_section = evidence_bundle[:16000] if evidence_bundle else "No documents were uploaded for this case."
        evidence_instruction = (
            "Before using the uploaded evidence above, check whether it actually relates to this case "
            "(same property/lease, same landlord or incident, same underlying issue -- not just the same "
            "broad topic). Set \"evidence_relevant\" to false if it clearly does NOT relate (e.g. it's a "
            "certificate or an unrelated document), and in that case leave \"evidence_facts\" empty and do not "
            "draw any facts from it. Set it to true if it DOES relate, and populate \"evidence_facts\" with the "
            "specific dates, amounts, reference numbers, and names you found in the evidence -- this is what "
            "makes the answer visibly grounded in what the user uploaded rather than generic advice."
            if evidence_bundle
            else "No documents were uploaded -- always set \"evidence_relevant\" to true (there is no separate "
            "uploaded document to judge as relevant or not) and leave \"evidence_facts\" empty."
        )

        prompt = f"""{self.system_prompt}

# User Query
{query}

# Uploaded Case Evidence
{evidence_section}

# Regulatory & Procedural Context (retrieved from knowledge base)
{context_text}

{evidence_instruction}

{COMPLETENESS_MANDATE}

# Output (strict JSON only)
{{
    "evidence_relevant": true,
    "evidence_facts": ["specific dates/amounts/reference numbers/names found in the uploaded evidence, empty list if none uploaded or not relevant"],
    "analysis": "...",
    "applicable_rules": ["..."],
    "action_plan": ["..."],
    "escalation_path": "State RERA Authority / Registrar of Cooperative Societies / Sub-Registrar / RBI Ombudsman / Consumer Forum",
    "grievance_channel": "State RERA / Rent Authority / Registrar / NCDRC / National Consumer Helpline",
    "estimated_resolution_days": "..."
}}"""
        raw = await llm_service.generate(prompt, purpose="reasoning")
        data = parse_agent_json(raw, {"analysis": "", "applicable_rules": [], "action_plan": []})
        if "_parse_failed" in data:
            logger.error(f"{self.name} JSON parse error")

        rules = data.get("applicable_rules")
        if isinstance(rules, list) and rules:
            _, unverified = verify_claims(rules, context_text)
            data["unverified_rules"] = unverified

        return {"specialist_name": self.name, "specialist_focus": self.focus, "strategy": data}


class RentalTenancyAgent(HousingSpecialistAgent):
    def __init__(self):
        super().__init__(
            name="Rental & Tenancy Specialist",
            focus="Rental agreement disputes, security deposit refunds, landlord-tenant disputes, illegal eviction, Model Tenancy Act",
            system_prompt="""You are an expert on Indian rental/tenancy law: rental and lease agreements,
security deposit refund disputes, landlord-tenant conflicts, and the Model Tenancy Act, 2021 framework
where a state has adopted it. You evaluate disputes over deposit withholding, illegal lock-outs,
unauthorized rent hikes, and repair obligations, recommending the correct Rent Authority/civil remedy."""
        )


class ReraBuilderAgent(HousingSpecialistAgent):
    def __init__(self):
        super().__init__(
            name="RERA & Builder Disputes Specialist",
            focus="RERA complaints, builder possession delay, defective construction, occupancy certificate, completion certificate, promoter obligations",
            system_prompt="""You are an expert on the Real Estate (Regulation and Development) Act, 2016 (RERA)
and builder-buyer disputes. You evaluate possession delays (Section 18), structural/quality defects
(Section 14(3)), occupancy/completion certificate non-compliance, and hidden charges, citing the
specific RERA section and recommending State RERA Authority complaint procedure and remedy (refund
with interest, continued possession with interest, or rectification)."""
        )


class PropertyRegistrationAgent(HousingSpecialistAgent):
    def __init__(self):
        super().__init__(
            name="Property Registration Specialist",
            focus="Property registration delay, Sub-Registrar Office, stamp duty, encumbrance certificate, mutation, Registration Act 1908",
            system_prompt="""You are an expert on property registration under the Registration Act, 1908,
state stamp duty rules, and encumbrance certificates. You evaluate registration delays, stamp duty
refund requests, and encumbrance certificate errors, recommending escalation through the Sub-Registrar,
District Registrar/IGR, and the Tahsildar for mutation issues."""
        )


class PropertyTaxAgent(HousingSpecialistAgent):
    def __init__(self):
        super().__init__(
            name="Property Tax Specialist",
            focus="Property tax assessment disputes, wrong classification, municipal corporation tax appeals",
            system_prompt="""You are an expert on Indian municipal property tax assessment and disputes.
You evaluate incorrect classification, wrong built-up area, or incorrect occupancy-status assessments,
recommending correction requests to the Municipal Corporation Revenue department and the applicable
statutory appeal mechanism."""
        )


class ApartmentSocietyAgent(HousingSpecialistAgent):
    def __init__(self):
        super().__init__(
            name="Apartment Society & Maintenance Specialist",
            focus="Maintenance charge disputes, society NOC denial, RWA/managing committee conduct, Cooperative Societies Act",
            system_prompt="""You are an expert on housing society/RWA governance under state Cooperative
Societies Acts and RERA-linked builder maintenance obligations. You evaluate disputes over illegal or
undisclosed maintenance charges and NOC denials, recommending escalation to the society general body,
the Registrar of Cooperative Societies, or the State RERA Authority where a builder still controls
maintenance before formal handover."""
        )


class HomeLoanAgent(HousingSpecialistAgent):
    def __init__(self):
        super().__init__(
            name="Home Loan Specialist",
            focus="Home loan documentation, foreclosure penalty, property document release, construction-linked disbursement",
            system_prompt="""You are an expert on Indian home loan documentation and RBI's lender-conduct
directions. You evaluate foreclosure/prepayment penalty disputes on floating-rate loans, delayed
release of property documents after loan closure, and construction-linked disbursement issues,
recommending escalation through the lender's Nodal Officer and the RBI Integrated Ombudsman Scheme."""
        )


class ConsumerEscalationAgent(HousingSpecialistAgent):
    def __init__(self):
        super().__init__(
            name="Consumer Escalation Specialist",
            focus="NCDRC, consumer court filing, National Consumer Helpline, general housing grievance escalation",
            system_prompt="""You are a generalist on consumer-forum escalation for housing disputes not
resolved by RERA, the society, or the registration department. You know when a District/State/National
Consumer Disputes Redressal Commission complaint is the right next step (deficiency in service,
compensation claims) versus a specialized forum, and cite the applicable pecuniary jurisdiction."""
        )


class GeneralHousingAgent(HousingSpecialistAgent):
    def __init__(self):
        super().__init__(
            name="General Housing Specialist",
            focus="MoHUA policy, PMAY scheme guidance, general housing questions not covered by a more specific specialist",
            system_prompt="""You are a generalist on Indian housing policy: MoHUA programs, PMAY scheme
eligibility and documentation, and general citizen housing questions. You identify the correct
department/portal and hand off to a more specific specialist when the case clearly fits one."""
        )


def get_housing_specialists() -> Dict[str, HousingSpecialistAgent]:
    return {
        "rental_tenancy": RentalTenancyAgent(),
        "rera_builder": ReraBuilderAgent(),
        "property_registration": PropertyRegistrationAgent(),
        "property_tax": PropertyTaxAgent(),
        "apartment_society": ApartmentSocietyAgent(),
        "home_loan": HomeLoanAgent(),
        "consumer_escalation": ConsumerEscalationAgent(),
        "general_housing": GeneralHousingAgent(),
    }
