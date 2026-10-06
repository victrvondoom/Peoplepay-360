"""Deterministic intent routing; provider coverage is explicit and replaceable."""
import re
from typing import Any


def route_need(message: Any, jurisdiction: Any):
    if not isinstance(jurisdiction, str) or not re.fullmatch(r"[A-Z]{2}", jurisdiction):
        raise ValueError("an ISO country code is required")
    if not isinstance(message, str) or not 1 <= len(message.strip()) <= 1000:
        raise ValueError("a bounded need is required")
    text = message.lower()
    urgent = next((name for name, pattern in [
        ("crisis", r"kill myself|suicid|want to die|end my life"),
        ("domestic_violence", r"domestic violence|hits me|abusive partner")]
        if re.search(pattern, text)), None)
    # A company buying goods is commercial even when it mentions sustainable benefits.
    if not urgent and re.search(r"\b(company|procure|office chairs|supplier|laptop)\b", text) and not re.search(r"evict|\b(?:homeless|medical bill|hospital bill)\b", text):
        return {"intent": "procurement", "need": None, "capabilities": ["supplier_discovery", "price_intelligence"],
                "providers": ["greenchain", "inflationforge"], "civicmesh_invoked": False,
                "reason": "Commercial sourcing request; assistance capability is irrelevant."}
    patterns = [("crisis", r"kill myself|suicid|want to die|end my life"),
                ("domestic_violence", r"domestic violence|hits me|abusive partner"),
                ("eviction", r"evict|landlord|homeless|losing.*(?:home|apartment)"),
                ("medical_bill", r"medical bill|hospital bill|struggling to pay.*(?:hospital|medical)"),
                ("housing", r"housing|shelter|apartment"), ("healthcare", r"healthcare|medication|health care"),
                ("food", r"hunger|hungry|food|groceries"), ("legal", r"legal aid|legal help|court")]
    need = urgent or next((name for name, pattern in patterns if re.search(pattern, text)), None)
    return {"intent": "assistance" if need else "unsupported", "need": need,
            "capabilities": ["assistance_eligibility"] if need else [], "providers": [],
            "civicmesh_invoked": False, "reason": "Relevant assistance intent; select a provider with matching jurisdiction and health." if need else "No reviewed capability matches this need."}
