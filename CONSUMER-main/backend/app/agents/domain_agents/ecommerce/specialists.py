"""
E-Commerce Domain - Specialist Agents
Routes to: consumer_protection, returns_refunds, marketplace_policy, delivery_logistics, warranty_seller
"""
import logging
from typing import Dict, Any
from app.agents.json_parser import parse_agent_json
from app.llm.gemini.service import gemini_service
from app.models.domain import Domain
from app.rag.retrieval.qdrant_service import qdrant_service
from app.services.citation_verification import verify_claims

logger = logging.getLogger(__name__)

# Running specialist agents against retrieved regulations and the user's own
# evidence only pays off if the answer is a complete, usable resolution --
# not a shallow reply that just says "contact the seller" or asks for more
# documents before it'll help, which is indistinguishable from a plain
# chatbot and defeats the reason to run agents at all.
COMPLETENESS_MANDATE = (
    "Before answering: your \"analysis\" and \"action_plan\" must form a complete, usable resolution "
    "built from what's available now, not a request for more information as the primary answer. Name "
    "the specific Consumer Protection (E-Commerce) Rules provision or Consumer Protection Act section "
    "from the Regulatory & Policy Context above (not \"relevant consumer rules\"). Give the exact "
    "escalation channel -- marketplace's Grievance Officer, then National Consumer Helpline (1915 / "
    "consumerhelpline.gov.in), then District Consumer Disputes Redressal Commission -- with what each "
    "step requires. If an exact date or amount is missing from the query and evidence, give the complete "
    "plan for the most likely scenario and note what to confirm in one line, rather than stopping to ask."
)

class EcommerceSpecialistAgent:
    def __init__(self, name: str, focus: str, system_prompt: str):
        self.name = name
        self.focus = focus
        self.system_prompt = system_prompt

    async def process(self, context: Dict[str, Any]) -> Dict[str, Any]:
        query = context.get("case_summary", "")
        evidence_bundle = context.get("evidence_bundle", "")

        results = await qdrant_service.search_chunks(
            Domain.ECOMMERCE, f"{self.focus}: {query}", top_k=5
        )
        context_text = "\n\n".join(r.get("text", "") for r in results)

        evidence_section = evidence_bundle[:16000] if evidence_bundle else "No documents were uploaded for this case."
        evidence_instruction = (
            "Before using the uploaded evidence above, check whether it actually relates to this case "
            "(same order/seller, same purchase or incident, same underlying issue -- not just the same broad "
            "topic). Set \"evidence_relevant\" to false if it clearly does NOT relate (e.g. it's a certificate "
            "or an unrelated document), and in that case leave \"evidence_facts\" empty and do not draw any "
            "facts from it. Set it to true if it DOES relate, and populate \"evidence_facts\" with the specific "
            "dates, amounts, reference numbers, and names you found in the evidence -- this is what makes the "
            "answer visibly grounded in what the user uploaded rather than generic advice."
            if evidence_bundle
            else "No documents were uploaded -- always set \"evidence_relevant\" to true (there is no separate "
            "uploaded document to judge as relevant or not) and leave \"evidence_facts\" empty."
        )

        prompt = f"""{self.system_prompt}

# User Query
{query}

# Uploaded Case Evidence
{evidence_section}

# Regulatory & Policy Context (retrieved from knowledge base)
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
    "escalation_path": "Marketplace Grievance Officer / National Consumer Helpline / Consumer Court",
    "refund_eligible": "YES/NO/PARTIAL",
    "estimated_resolution_days": "..."
}}"""
        raw = await gemini_service.generate(prompt, purpose="reasoning")
        data = parse_agent_json(raw, {"analysis": "", "applicable_rules": [], "action_plan": []})
        if "_parse_failed" in data:
            logger.error(f"{self.name} JSON parse error")

        rules = data.get("applicable_rules")
        if isinstance(rules, list) and rules:
            _, unverified = verify_claims(rules, context_text)
            data["unverified_rules"] = unverified

        return {"specialist_name": self.name, "specialist_focus": self.focus, "strategy": data}

class ConsumerProtectionAgent(EcommerceSpecialistAgent):
    def __init__(self):
        super().__init__(
            name="Consumer Protection Specialist",
            focus="Consumer Protection Act, E-Commerce Rules, ONDC, CCPA, NCH, unfair trade practices",
            system_prompt="""You are an expert in Indian Consumer Protection Law and E-Commerce Rules 2020.
You evaluate disputes involving unfair trade practices, misleading advertisements, and dark patterns.
Your goal is to identify statutory violations and draft complaints to the CCPA or National Consumer Helpline."""
        )

class ReturnsRefundsAgent(EcommerceSpecialistAgent):
    def __init__(self):
        super().__init__(
            name="Returns & Refunds Specialist",
            focus="Refund denied, return rejected, cancellation charges, duplicate payment, refund timelines",
            system_prompt="""You are a specialist in e-commerce returns, exchanges, and payment refunds.
You evaluate cases where a marketplace denies a legitimate return request or delays a refund.
You reference specific marketplace return window policies and UPI/Card chargeback guidelines."""
        )

class MarketplacePolicyAgent(EcommerceSpecialistAgent):
    def __init__(self):
        super().__init__(
            name="Marketplace Policy Specialist",
            focus="Amazon A-to-z, Flipkart SuperCoins, Myntra terms, account blocking, seller terms",
            system_prompt="""You are an expert on specific marketplace policies (Amazon, Flipkart, Myntra, JioMart, etc.).
You mediate disputes using the platform's own stated terms of service and buyer protection guarantees,
holding them accountable to their published SLAs."""
        )

class DeliveryLogisticsAgent(EcommerceSpecialistAgent):
    def __init__(self):
        super().__init__(
            name="Delivery & Logistics Specialist",
            focus="Missing package, delivery delay, damaged shipment, courier, OTP issues, quick commerce",
            system_prompt="""You are a logistics and last-mile delivery specialist.
You investigate missing packages, delayed deliveries, and "delivered but not received" claims.
You use courier policies (Delhivery, Blue Dart) and quick commerce SLAs (Blinkit, Zepto) to demand compensation."""
        )

class WarrantySellerAgent(EcommerceSpecialistAgent):
    def __init__(self):
        super().__init__(
            name="Warranty & Seller Fraud Specialist",
            focus="Fake product, warranty refused, seller disappeared, wrong product delivered, defective item",
            system_prompt="""You specialize in seller fraud, counterfeit goods, and warranty denials.
You know that under E-Commerce Rules, marketplaces share liability for fake products.
You draft notices to sellers and brands to enforce product warranties and demand replacements for defective goods."""
        )

def get_ecommerce_specialists() -> Dict[str, EcommerceSpecialistAgent]:
    return {
        "consumer_protection": ConsumerProtectionAgent(),
        "returns_refunds": ReturnsRefundsAgent(),
        "marketplace_policy": MarketplacePolicyAgent(),
        "delivery_logistics": DeliveryLogisticsAgent(),
        "warranty_seller": WarrantySellerAgent(),
    }
