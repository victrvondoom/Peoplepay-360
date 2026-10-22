"""
PeoplePay 360 - Sustainability Intelligence Service

Provides emissions calculations, supplier environmental scoring, sustainability indicators,
resource-efficiency assessments, and evidence-backed environmental assessments.
"""

from sustainability.models import (
    EmissionFactor,
    EnvironmentalImpact,
    SustainabilityScore,
    SupplierSustainability,
    CarbonFootprint,
)
from sustainability.calculator import (
    EmissionCalculator,
    get_emission_calculator,
)
from sustainability.scoring import (
    SustainabilityScorer,
    get_sustainability_scorer,
)
from sustainability.service import (
    SustainabilityService,
    get_sustainability_service,
)
from sustainability.errors import SustainabilityError

__all__ = [
    # Models
    "EmissionFactor",
    "EnvironmentalImpact",
    "SustainabilityScore",
    "SupplierSustainability",
    "CarbonFootprint",
    # Calculator
    "EmissionCalculator",
    "get_emission_calculator",
    # Scoring
    "SustainabilityScorer",
    "get_sustainability_scorer",
    # Service
    "SustainabilityService",
    "get_sustainability_service",
    # Errors
    "SustainabilityError",
]
