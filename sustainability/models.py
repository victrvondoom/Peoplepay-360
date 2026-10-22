"""
Sustainability Intelligence Service - Data Models
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any
from uuid import UUID, uuid4

from sustainability.errors import InvalidSustainabilityDataError


class SustainabilityCategory(Enum):
    """Categories for sustainability assessment."""
    CARBON_FOOTPRINT = "carbon_footprint"
    ENERGY_EFFICIENCY = "energy_efficiency"
    WATER_USAGE = "water_usage"
    WASTE_MANAGEMENT = "waste_management"
    MATERIAL_SOURCING = "material_sourcing"
    TRANSPORTATION = "transportation"
    PACKAGING = "packaging"
    CIRCULAR_ECONOMY = "circular_economy"
    RENEWABLE_ENERGY = "renewable_energy"
    SOCIAL_IMPACT = "social_impact"


class EmissionScope(Enum):
    """Emission scopes as defined by GHG Protocol."""
    SCOPE_1 = "scope_1"  # Direct emissions
    SCOPE_2 = "scope_2"  # Indirect emissions from energy
    SCOPE_3 = "scope_3"  # Other indirect emissions


class SustainabilityRating(Enum):
    """Sustainability rating levels."""
    EXCELLENT = "excellent"
    GOOD = "good"
    FAIR = "fair"
    POOR = "poor"
    UNKNOWN = "unknown"


class DataConfidence(Enum):
    """Confidence level for sustainability data."""
    VERIFIED = "verified"
    ESTIMATED = "estimated"
    MODELED = "modeled"
    SELF_REPORTED = "self_reported"
    UNKNOWN = "unknown"


@dataclass
class EmissionFactor:
    """Emission factor for calculating greenhouse gas emissions."""
    name: str
    description: str
    category: str
    unit: str  # e.g., "kg CO2e per kg", "kg CO2e per km"
    value: float  # Emission factor value
    source: str
    id: str = field(default_factory=lambda: str(uuid4()))
    confidence: DataConfidence = DataConfidence.VERIFIED
    region: Optional[str] = None
    year: Optional[int] = None
    version: str = "1.0"
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self):
        if self.value < 0:
            raise InvalidSustainabilityDataError("Emission factor value cannot be negative")


@dataclass
class EnvironmentalImpact:
    """Environmental impact assessment for a product or supplier."""
    entity_id: str  # Product ID or Supplier ID
    entity_type: str  # "product" or "supplier"
    category: SustainabilityCategory
    impact_value: float
    impact_unit: str
    calculation_method: str
    emission_factors: List[str]  # List of emission factor IDs used
    id: str = field(default_factory=lambda: str(uuid4()))
    confidence: DataConfidence = DataConfidence.ESTIMATED
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CarbonFootprint:
    """Carbon footprint calculation result."""
    entity_id: str
    entity_type: str
    total_co2e: float  # Total CO2 equivalent in kg
    id: str = field(default_factory=lambda: str(uuid4()))
    scope_1_co2e: float = 0.0
    scope_2_co2e: float = 0.0
    scope_3_co2e: float = 0.0
    scope_breakdown: Dict[EmissionScope, float] = field(default_factory=dict)
    calculation_method: str = "standard"
    emission_factors_used: List[str] = field(default_factory=list)
    confidence: DataConfidence = DataConfidence.ESTIMATED
    timestamp: datetime = field(default_factory=datetime.utcnow)
    assumptions: Dict[str, Any] = field(default_factory=dict)
    notes: str = ""

    def __post_init__(self):
        self.scope_breakdown = {
            EmissionScope.SCOPE_1: self.scope_1_co2e,
            EmissionScope.SCOPE_2: self.scope_2_co2e,
            EmissionScope.SCOPE_3: self.scope_3_co2e,
        }
        self.total_co2e = self.scope_1_co2e + self.scope_2_co2e + self.scope_3_co2e


@dataclass
class SustainabilityScore:
    """Sustainability score for an entity."""
    entity_id: str
    entity_type: str
    id: str = field(default_factory=lambda: str(uuid4()))
    category_scores: Dict[SustainabilityCategory, float] = field(default_factory=dict)
    overall_score: float = 0.0  # 0-100 scale
    rating: SustainabilityRating = SustainabilityRating.UNKNOWN
    confidence: DataConfidence = DataConfidence.ESTIMATED
    weightings: Dict[SustainabilityCategory, float] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    explanation: str = ""
    recommendations: List[str] = field(default_factory=list)

    def __post_init__(self):
        if self.overall_score >= 90:
            self.rating = SustainabilityRating.EXCELLENT
        elif self.overall_score >= 75:
            self.rating = SustainabilityRating.GOOD
        elif self.overall_score >= 60:
            self.rating = SustainabilityRating.FAIR
        elif self.overall_score >= 30:
            self.rating = SustainabilityRating.POOR
        else:
            self.rating = SustainabilityRating.POOR


@dataclass
class SupplierSustainability:
    """Sustainability profile for a supplier."""
    supplier_id: str
    supplier_name: str
    sustainability_score: Optional[SustainabilityScore] = None
    carbon_footprint: Optional[CarbonFootprint] = None
    environmental_impacts: List[EnvironmentalImpact] = field(default_factory=list)
    certifications: List[str] = field(default_factory=list)
    sustainability_policies: List[str] = field(default_factory=list)
    last_assessed: datetime = field(default_factory=datetime.utcnow)
    confidence: DataConfidence = DataConfidence.ESTIMATED
    renewable_energy_usage: Optional[float] = None  # Percentage
    waste_diversion_rate: Optional[float] = None  # Percentage
    water_usage_efficiency: Optional[float] = None  # Score 0-100
    ethical_sourcing_score: Optional[float] = None  # Score 0-100
    social_impact_score: Optional[float] = None  # Score 0-100
    sustainability_report_url: Optional[str] = None
    data_sources: List[str] = field(default_factory=list)
    notes: str = ""


@dataclass
class SustainabilityComparison:
    """Comparison of sustainability metrics between suppliers."""
    supplier_ids: List[str]
    metric: str  # e.g., "carbon_footprint", "overall_score"
    comparison_id: str = field(default_factory=lambda: str(uuid4()))
    values: Dict[str, float] = field(default_factory=dict)
    normalized_values: Dict[str, float] = field(default_factory=dict)
    best_performer: Optional[str] = None
    worst_performer: Optional[str] = None
    average: float = 0.0
    std_deviation: float = 0.0
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class SustainabilityReport:
    """Sustainability report for an organization or order."""
    title: str
    summary: str
    report_id: str = field(default_factory=lambda: str(uuid4()))
    organization_id: Optional[str] = None
    order_id: Optional[str] = None
    sections: List[Dict[str, Any]] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    sustainability_scores: List[SustainabilityScore] = field(default_factory=list)
    carbon_footprints: List[CarbonFootprint] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    generated_at: datetime = field(default_factory=datetime.utcnow)
    generated_by: str = "PeoplePay 360"
    version: str = "1.0"


# Request/Response Models
@dataclass
class CalculateEmissionRequest:
    """Request to calculate emissions."""
    entity_id: str
    entity_type: str
    activity_data: Dict[str, float]  # e.g., {"weight_kg": 100, "distance_km": 500}
    emission_factor_ids: Optional[List[str]] = None
    calculation_method: str = "standard"


@dataclass
class CalculateCarbonFootprintRequest:
    """Request to calculate carbon footprint."""
    entity_id: str
    entity_type: str
    scope_1_data: Optional[Dict[str, float]] = None
    scope_2_data: Optional[Dict[str, float]] = None
    scope_3_data: Optional[Dict[str, float]] = None


@dataclass
class ScoreSustainabilityRequest:
    """Request to calculate sustainability score."""
    entity_id: str
    entity_type: str
    category_weights: Optional[Dict[SustainabilityCategory, float]] = None


# Response Models
@dataclass
class SustainabilityResponse:
    """Base response for sustainability operations."""
    data: Any = None
    warnings: List[str] = field(default_factory=list)
    confidence: DataConfidence = DataConfidence.ESTIMATED


@dataclass
class EmissionCalculationResponse:
    """Response for emission calculation."""
    emission_factor: EmissionFactor
    calculated_value: float
    unit: str
    data: Any = None
    warnings: List[str] = field(default_factory=list)
    confidence: DataConfidence = DataConfidence.ESTIMATED


@dataclass
class CarbonFootprintResponse:
    """Response for carbon footprint calculation."""
    carbon_footprint: CarbonFootprint
    data: Any = None
    warnings: List[str] = field(default_factory=list)
    confidence: DataConfidence = DataConfidence.ESTIMATED


@dataclass
class SustainabilityScoreResponse:
    """Response for sustainability scoring."""
    score: SustainabilityScore
    data: Any = None
    warnings: List[str] = field(default_factory=list)
    confidence: DataConfidence = DataConfidence.ESTIMATED


@dataclass
class SupplierSustainabilityResponse:
    """Response for supplier sustainability data."""
    supplier_sustainability: SupplierSustainability
    data: Any = None
    warnings: List[str] = field(default_factory=list)
    confidence: DataConfidence = DataConfidence.ESTIMATED
