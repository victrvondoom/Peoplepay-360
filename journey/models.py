"""Concrete procurement input and stable snapshot hashing for Journey v1."""

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=True, allow_nan=False).encode()).hexdigest()


class ProcurementRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    description: str = Field(min_length=5, max_length=1000)
    product: str = Field(min_length=2, max_length=120)
    quantity: int = Field(gt=0, le=10000)
    budget_minor: int = Field(gt=0, le=10**12)
    currency: Literal["INR"] = "INR"
    delivery_days: int = Field(gt=0, le=365)
    destination: str = Field(default="IN", pattern=r"^[A-Z]{2}$")
    prioritize_sustainability: StrictBool = True


REFERENCE_REQUIREMENT = {
    "description": "Procure 300 ergonomic office chairs under INR 20 lakh, delivery within 30 days, prioritize sustainability.",
    "product": "ergonomic office chairs", "quantity": 300, "budget_minor": 200000000,
    "currency": "INR", "delivery_days": 30, "destination": "IN", "prioritize_sustainability": True,
}
