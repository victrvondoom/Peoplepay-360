"""Minimal structured facts; no free text, medical records or payment data."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Facts(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    age: int | None = Field(default=None, ge=0, le=120)
    income_annual: int | None = Field(default=None, ge=0, le=10_000_000)
    household_size: int | None = Field(default=None, ge=1, le=30)
    state: str = Field(default="", pattern=r"^([A-Z]{2})?$")
    city: str = Field(default="", max_length=100)
    citizenship: Literal["", "citizen", "permanent_resident", "refugee", "asylee", "undocumented"] = ""


class AssistanceInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    jurisdiction: str = Field(pattern=r"^[A-Z]{2}$")
    need: Literal["housing", "eviction", "food", "healthcare", "medical_bill", "legal", "crisis", "domestic_violence"]
    language: str = Field(default="en", pattern=r"^[a-z]{2,3}(?:-[A-Za-z]{2,4})?$")
    facts: Facts = Field(default_factory=Facts)
    consent: Literal[True]


class ServiceRequest(AssistanceInput):
    workflow_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
    request_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
