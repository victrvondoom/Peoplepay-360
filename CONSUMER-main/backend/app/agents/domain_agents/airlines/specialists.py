import logging
from typing import Dict, Any, Optional
from app.agents.json_parser import parse_agent_json
from app.llm.gemini.service import gemini_service
from app.models.domain import Domain
from app.rag.retrieval.qdrant_service import qdrant_service
from app.services.citation_verification import verify_claims

logger = logging.getLogger(__name__)

# Running specialist agents against retrieved regulations and the user's own
# evidence only pays off if the answer is a complete, usable resolution --
# not a shallow reply that just says "consult support" or asks for more
# documents before it'll help, which is indistinguishable from a plain
# chatbot and defeats the reason to run agents at all.
COMPLETENESS_MANDATE = (
    "Before answering: your \"analysis\" and \"action_plan\" must form a complete, usable resolution "
    "built from what's available now, not a request for more information as the primary answer. "
    "Name the specific DGCA CAR section/circular from the Regulatory & Policy Context above (not "
    "\"relevant DGCA rules\"). Give the exact escalation channel -- airline's Nodal Officer, then "
    "AirSewa (airsewa.gov.in), then the Ministry of Civil Aviation -- with what each step requires. "
    "If an exact date or amount is missing from the query and evidence, give the complete plan for the "
    "most likely scenario and note what to confirm in one line, rather than stopping to ask."
)

class AirlineSpecialistAgent:
    """Base class for all airline specialists"""
    def __init__(self, name: str, focus: str, system_prompt: str):
        self.name = name
        self.focus = focus
        self.system_prompt = system_prompt
        
    async def process(self, context: Dict[str, Any]) -> Dict[str, Any]:
        query = context.get("case_summary", "")
        evidence_bundle = context.get("evidence_bundle", "")

        # Pull vector context
        search_query = f"{self.focus}: {query}"
        results = await qdrant_service.search_chunks(Domain.AIRLINES, search_query, top_k=5)
        context_text = "\n\n".join([r.get("text", "") for r in results])

        evidence_section = evidence_bundle[:16000] if evidence_bundle else "No documents were uploaded for this case."
        evidence_instruction = (
            "Before using the uploaded evidence above, check whether it actually relates to this case "
            "(same airline/booking, same flight or incident, same underlying issue -- not just the same broad "
            "topic). Set \"evidence_relevant\" to false if it clearly does NOT relate (e.g. it's a certificate "
            "or an unrelated document), and in that case leave \"evidence_facts\" empty and do not draw any "
            "facts from it. Set it to true if it DOES relate, and populate \"evidence_facts\" with the specific "
            "dates, amounts, reference numbers, and names you found in the evidence -- this is what makes the "
            "answer visibly grounded in what the user uploaded rather than generic advice."
            if evidence_bundle
            # No documents were uploaded -- there's no separate "uploaded
            # document" to judge, so leaving this branch empty gave the
            # model no guidance and it would often guess evidence_relevant
            # =false anyway, rendering a false "the document you uploaded
            # doesn't relate" note when nothing was uploaded at all.
            else "No documents were uploaded -- always set \"evidence_relevant\" to true (there is no separate "
            "uploaded document to judge as relevant or not) and leave \"evidence_facts\" empty."
        )

        prompt = f"""
{self.system_prompt}

# Task
Analyze the user's issue and provided evidence, and formulate a strategy based on the retrieved airline policies and DGCA regulations.

# User Query
{query}

# Uploaded Case Evidence
{evidence_section}

# Regulatory & Policy Context
{context_text}

{evidence_instruction}

{COMPLETENESS_MANDATE}

# Output format
Return ONLY valid JSON:
{{
    "evidence_relevant": true,
    "evidence_facts": ["specific dates/amounts/reference numbers/names found in the uploaded evidence, empty list if none uploaded or not relevant"],
    "analysis": "...",
    "applicable_rules": ["..."],
    "action_plan": ["..."],
    "compensation_eligibility": "YES/NO/PARTIAL",
    "compensation_amount_estimate": "..."
}}
"""
        raw_response = await gemini_service.generate(prompt, purpose="reasoning")
        data = parse_agent_json(raw_response, {"analysis": "", "applicable_rules": [], "action_plan": []})
        if "_parse_failed" in data:
            logger.error(f"Failed to parse JSON from {self.name}")

        # Deterministic check, not another LLM call: does each cited rule
        # actually appear in the retrieved policy/regulation text this
        # specialist was given? Closes the gap where a hallucinated
        # citation would otherwise sail through with no ground-truth check.
        rules = data.get("applicable_rules")
        if isinstance(rules, list) and rules:
            _, unverified = verify_claims(rules, context_text)
            data["unverified_rules"] = unverified

        return {
            "specialist_name": self.name,
            "specialist_focus": self.focus,
            "strategy": data
        }

# ==========================================
# Specialized Airline Agents
# ==========================================

class DelayCancellationAgent(AirlineSpecialistAgent):
    def __init__(self):
        super().__init__(
            name="Delay and Cancellation Specialist",
            focus="Flight Delays, Cancellations, Missed Connections, Overbooking, DGCA CAR",
            system_prompt="""You are an expert aviation dispute agent specializing in flight delays, cancellations, and denied boarding.
You possess deep knowledge of the DGCA Civil Aviation Requirements (CAR), Passenger Charter, and Montreal Convention.
Your goal is to determine if the airline owes compensation, meals, or hotel accommodation based on the delay duration or cancellation notice period, and draft strong arguments to force the airline to comply."""
        )

class BaggageAgent(AirlineSpecialistAgent):
    def __init__(self):
        super().__init__(
            name="Baggage Claim Specialist",
            focus="Lost Baggage, Damaged Baggage, Delayed Baggage, Property Irregularity Report (PIR)",
            system_prompt="""You are an expert baggage dispute agent.
You understand the Montreal Convention weight-based limits (SDR) for international flights, and domestic carriage limits.
You focus on ensuring the passenger filed a Property Irregularity Report (PIR) within the strict timeline (7 days for damage, 21 days for delay/loss) and calculating maximum liability."""
        )

class RefundTicketingAgent(AirlineSpecialistAgent):
    def __init__(self):
        super().__init__(
            name="Refund & Ticketing Specialist",
            focus="Ticket Refunds, Cancellation Fees, Duplicate Charges, Name Corrections, No-Show Policies",
            system_prompt="""You are an expert in airline ticketing and refund policies.
You analyze fare rules (refundable vs non-refundable), DGCA rules on cancellation charges (which cannot exceed base fare + fuel surcharge), and mandatory refunds for statutory taxes (UDF, PSF).
You ensure passengers aren't charged predatory cancellation fees and help resolve duplicate booking charges."""
        )

class GeneralAviationAgent(AirlineSpecialistAgent):
    def __init__(self):
        super().__init__(
            name="General Airline Support Specialist",
            focus="Customer Service Complaints, Wheelchair Assistance, Pet Travel, Lounge Issues, Travel Insurance",
            system_prompt="""You are a general airline dispute agent handling customer service failures, unprovided special assistance (wheelchairs), denied access, and travel insurance claims.
You use airline Conditions of Carriage and passenger charters to hold airlines accountable for service deficiencies."""
        )

# Factory function
def get_airline_specialists() -> Dict[str, AirlineSpecialistAgent]:
    return {
        "delay_cancellation": DelayCancellationAgent(),
        "baggage": BaggageAgent(),
        "refund_ticketing": RefundTicketingAgent(),
        "general_aviation": GeneralAviationAgent()
    }
