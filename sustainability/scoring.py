"""
Sustainability Intelligence Service - Scoring Engine

Provides sustainability scoring based on multiple factors and weightings.
"""

import logging
from dataclasses import field
from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import uuid4

from sustainability.models import (
    SustainabilityScore,
    SustainabilityCategory,
    SustainabilityRating,
    DataConfidence,
    SupplierSustainability,
    CarbonFootprint,
    EnvironmentalImpact,
)
from sustainability.calculator import EmissionCalculator, get_emission_calculator
from sustainability.errors import (
    SustainabilityScoringError,
    InvalidSustainabilityDataError,
)

logger = logging.getLogger(__name__)


class SustainabilityScorer:
    """
    Engine for calculating sustainability scores.
    
    Uses weighted scoring across multiple categories with configurable weightings.
    """

    # Default category weightings (0-1, sum should be 1.0)
    DEFAULT_CATEGORY_WEIGHTS: Dict[SustainabilityCategory, float] = {
        SustainabilityCategory.CARBON_FOOTPRINT: 0.25,
        SustainabilityCategory.ENERGY_EFFICIENCY: 0.15,
        SustainabilityCategory.WATER_USAGE: 0.10,
        SustainabilityCategory.WASTE_MANAGEMENT: 0.10,
        SustainabilityCategory.MATERIAL_SOURCING: 0.15,
        SustainabilityCategory.TRANSPORTATION: 0.10,
        SustainabilityCategory.PACKAGING: 0.05,
        SustainabilityCategory.CIRCULAR_ECONOMY: 0.05,
        SustainabilityCategory.RENEWABLE_ENERGY: 0.05,
        SustainabilityCategory.SOCIAL_IMPACT: 0.05,
    }

    def __init__(
        self,
        emission_calculator: Optional[EmissionCalculator] = None,
        category_weights: Optional[Dict[SustainabilityCategory, float]] = None,
    ):
        self._emission_calculator = emission_calculator or get_emission_calculator()
        self._category_weights = category_weights or self.DEFAULT_CATEGORY_WEIGHTS
        
        # Validate weights sum to 1.0
        total_weight = sum(self._category_weights.values())
        if not (0.99 <= total_weight <= 1.01):
            logger.warning(f"Category weights sum to {total_weight}, not 1.0")

    def get_category_weights(self) -> Dict[SustainabilityCategory, float]:
        """Get the current category weightings."""
        return self._category_weights.copy()

    def set_category_weights(self, weights: Dict[SustainabilityCategory, float]) -> None:
        """Set custom category weightings."""
        total = sum(weights.values())
        if not (0.99 <= total <= 1.01):
            raise InvalidSustainabilityDataError(
                f"Category weights must sum to 1.0, got {total}"
            )
        self._category_weights = weights
        logger.info(f"Updated category weights: {weights}")

    def _normalize_score(self, score: float, min_val: float = 0.0, max_val: float = 100.0) -> float:
        """Normalize a score to 0-100 scale."""
        if max_val - min_val == 0:
            return 50.0  # Default middle value
        return ((score - min_val) / (max_val - min_val)) * 100.0

    def _score_carbon_footprint(
        self,
        carbon_footprint: Optional[CarbonFootprint],
        benchmark: float = 1000.0,  # kg CO2e benchmark
    ) -> float:
        """Score carbon footprint (lower is better, so we invert)."""
        if carbon_footprint is None:
            return 0.0
        
        # Compare to benchmark
        ratio = carbon_footprint.total_co2e / benchmark
        
        # Invert: lower footprint = higher score
        if ratio >= 1.0:
            # Above benchmark, score decreases
            score = max(0, 100 - (ratio - 1) * 100)
        else:
            # Below benchmark, score increases
            score = 100 - ratio * 100
        
        return score

    def _score_energy_efficiency(self, efficiency_score: Optional[float]) -> float:
        """Score energy efficiency (0-100 scale)."""
        if efficiency_score is None:
            return 0.0
        return efficiency_score

    def _score_water_usage(self, efficiency_score: Optional[float]) -> float:
        """Score water usage efficiency (0-100 scale)."""
        if efficiency_score is None:
            return 0.0
        return efficiency_score

    def _score_waste_management(self, diversion_rate: Optional[float]) -> float:
        """Score waste management (waste diversion rate as %)."""
        if diversion_rate is None:
            return 0.0
        return min(100, diversion_rate)

    def _score_material_sourcing(
        self,
        ethical_sourcing_score: Optional[float],
        recycled_content: Optional[float] = None,
    ) -> float:
        """Score material sourcing."""
        if ethical_sourcing_score is None:
            return 0.0
        score = ethical_sourcing_score * 0.7
        if recycled_content:
            score += recycled_content * 0.3
        return min(100, score)

    def _score_transportation(
        self,
        transport_distance: Optional[float] = None,
        transport_mode: Optional[str] = None,
    ) -> float:
        """Score transportation impact."""
        if transport_distance is None or transport_mode is None:
            return 50.0  # Default
        
        # Mode multipliers (higher = worse)
        mode_multipliers = {
            "walk": 0.0,
            "bicycle": 0.0,
            "electric_vehicle": 0.2,
            "train": 0.3,
            "ship": 0.4,
            "truck": 0.8,
            "air": 2.0,
        }
        
        multiplier = mode_multipliers.get(transport_mode, 1.0)
        score = 100 - min(100, transport_distance * multiplier / 100)
        return max(0, score)

    def _score_packaging(
        self,
        packaging_weight: Optional[float] = None,
        recyclable_percentage: Optional[float] = None,
    ) -> float:
        """Score packaging sustainability."""
        if packaging_weight is None:
            return 50.0
        
        score = 50.0
        if recyclable_percentage:
            score += recyclable_percentage * 0.5
        
        # Penalize for weight
        score -= min(50, packaging_weight * 0.1)
        return max(0, min(100, score))

    def _score_circular_economy(
        self,
        recyclable_percentage: Optional[float] = None,
        recycled_content_percentage: Optional[float] = None,
    ) -> float:
        """Score circular economy practices."""
        if recyclable_percentage is None and recycled_content_percentage is None:
            return 0.0
        
        score = 0.0
        if recyclable_percentage:
            score += recyclable_percentage * 0.5
        if recycled_content_percentage:
            score += recycled_content_percentage * 0.5
        return min(100, score)

    def _score_renewable_energy(self, percentage: Optional[float]) -> float:
        """Score renewable energy usage."""
        if percentage is None:
            return 0.0
        return min(100, percentage)

    def _score_social_impact(self, score: Optional[float]) -> float:
        """Score social impact."""
        if score is None:
            return 0.0
        return min(100, score)

    def calculate_sustainability_score(
        self,
        entity_id: str,
        entity_type: str,
        carbon_footprint: Optional[CarbonFootprint] = None,
        energy_efficiency: Optional[float] = None,
        water_efficiency: Optional[float] = None,
        waste_diversion_rate: Optional[float] = None,
        ethical_sourcing_score: Optional[float] = None,
        recycled_content: Optional[float] = None,
        transport_distance: Optional[float] = None,
        transport_mode: Optional[str] = None,
        packaging_weight: Optional[float] = None,
        recyclable_percentage: Optional[float] = None,
        renewable_energy_percentage: Optional[float] = None,
        social_impact_score: Optional[float] = None,
        category_weights: Optional[Dict[SustainabilityCategory, float]] = None,
    ) -> SustainabilityScore:
        """
        Calculate comprehensive sustainability score for an entity.
        
        Args:
            entity_id: ID of the entity to score
            entity_type: Type of entity (product, supplier, etc.)
            carbon_footprint: Carbon footprint data
            energy_efficiency: Energy efficiency score (0-100)
            water_efficiency: Water usage efficiency score (0-100)
            waste_diversion_rate: Waste diversion rate as percentage
            ethical_sourcing_score: Ethical sourcing score (0-100)
            recycled_content: Percentage of recycled content
            transport_distance: Transport distance in km
            transport_mode: Transport mode
            packaging_weight: Packaging weight in kg
            recyclable_percentage: Percentage of recyclable packaging
            renewable_energy_percentage: Percentage of renewable energy
            social_impact_score: Social impact score (0-100)
            category_weights: Optional custom category weights
            
        Returns:
            SustainabilityScore with calculated scores
        """
        try:
            # Use custom weights if provided
            weights = category_weights or self._category_weights
            
            # Calculate individual category scores
            category_scores: Dict[SustainabilityCategory, float] = {}
            explanations: List[str] = []
            
            # Carbon Footprint
            cf_score = self._score_carbon_footprint(carbon_footprint)
            category_scores[SustainabilityCategory.CARBON_FOOTPRINT] = cf_score
            if carbon_footprint:
                explanations.append(
                    f"Carbon footprint: {carbon_footprint.total_co2e:.2f} kg CO2e "
                    f"(Score: {cf_score:.1f})"
                )
            
            # Energy Efficiency
            ee_score = self._score_energy_efficiency(energy_efficiency)
            category_scores[SustainabilityCategory.ENERGY_EFFICIENCY] = ee_score
            if energy_efficiency:
                explanations.append(f"Energy efficiency: {energy_efficiency:.1f}% (Score: {ee_score:.1f})")
            
            # Water Usage
            wu_score = self._score_water_usage(water_efficiency)
            category_scores[SustainabilityCategory.WATER_USAGE] = wu_score
            if water_efficiency:
                explanations.append(f"Water efficiency: {water_efficiency:.1f}% (Score: {wu_score:.1f})")
            
            # Waste Management
            wm_score = self._score_waste_management(waste_diversion_rate)
            category_scores[SustainabilityCategory.WASTE_MANAGEMENT] = wm_score
            if waste_diversion_rate:
                explanations.append(f"Waste diversion: {waste_diversion_rate:.1f}% (Score: {wm_score:.1f})")
            
            # Material Sourcing
            ms_score = self._score_material_sourcing(ethical_sourcing_score, recycled_content)
            category_scores[SustainabilityCategory.MATERIAL_SOURCING] = ms_score
            if ethical_sourcing_score:
                explanations.append(
                    f"Material sourcing: {ethical_sourcing_score:.1f}% ethical "
                    f"(Score: {ms_score:.1f})"
                )
            
            # Transportation
            t_score = self._score_transportation(transport_distance, transport_mode)
            category_scores[SustainabilityCategory.TRANSPORTATION] = t_score
            if transport_distance and transport_mode:
                explanations.append(
                    f"Transportation: {transport_distance}km by {transport_mode} "
                    f"(Score: {t_score:.1f})"
                )
            
            # Packaging
            p_score = self._score_packaging(packaging_weight, recyclable_percentage)
            category_scores[SustainabilityCategory.PACKAGING] = p_score
            if packaging_weight:
                explanations.append(
                    f"Packaging: {packaging_weight}kg, {recyclable_percentage or 0:.0f}% recyclable "
                    f"(Score: {p_score:.1f})"
                )
            
            # Circular Economy
            ce_score = self._score_circular_economy(recyclable_percentage, recycled_content)
            category_scores[SustainabilityCategory.CIRCULAR_ECONOMY] = ce_score
            if recyclable_percentage or recycled_content:
                explanations.append(
                    f"Circular economy: {recyclable_percentage or 0:.0f}% recyclable, "
                    f"{recycled_content or 0:.0f}% recycled content (Score: {ce_score:.1f})"
                )
            
            # Renewable Energy
            re_score = self._score_renewable_energy(renewable_energy_percentage)
            category_scores[SustainabilityCategory.RENEWABLE_ENERGY] = re_score
            if renewable_energy_percentage:
                explanations.append(
                    f"Renewable energy: {renewable_energy_percentage:.1f}% "
                    f"(Score: {re_score:.1f})"
                )
            
            # Social Impact
            si_score = self._score_social_impact(social_impact_score)
            category_scores[SustainabilityCategory.SOCIAL_IMPACT] = si_score
            if social_impact_score:
                explanations.append(f"Social impact: {social_impact_score:.1f}% (Score: {si_score:.1f})")
            
            # Calculate weighted overall score
            total_weight = 0.0
            weighted_sum = 0.0
            
            for category, score in category_scores.items():
                weight = weights.get(category, 0.0)
                weighted_sum += score * weight
                total_weight += weight
            
            if total_weight > 0:
                overall_score = weighted_sum / total_weight
            else:
                overall_score = 0.0
            
            # Generate recommendations
            recommendations: List[str] = []
            if overall_score < 70:
                recommendations.append("Improve sustainability practices to achieve a better rating")
            
            if carbon_footprint and carbon_footprint.total_co2e > 1000:
                recommendations.append(
                    f"Reduce carbon footprint from {carbon_footprint.total_co2e:.2f} kg CO2e"
                )
            
            if renewable_energy_percentage is None or renewable_energy_percentage < 50:
                recommendations.append("Increase renewable energy usage")
            
            if waste_diversion_rate is None or waste_diversion_rate < 70:
                recommendations.append("Improve waste diversion rate")
            
            return SustainabilityScore(
                id=str(uuid4()),
                entity_id=entity_id,
                entity_type=entity_type,
                category_scores=category_scores,
                overall_score=overall_score,
                confidence=DataConfidence.ESTIMATED,
                weightings=weights,
                explanation="\n".join(explanations) if explanations else "No data available",
                recommendations=recommendations,
            )
            
        except Exception as e:
            logger.error(f"Error calculating sustainability score: {e}")
            raise SustainabilityScoringError(f"Failed to calculate sustainability score: {e}")

    def calculate_supplier_sustainability(
        self,
        supplier_id: str,
        supplier_name: str,
        carbon_footprint: Optional[CarbonFootprint] = None,
        certifications: Optional[List[str]] = None,
        sustainability_policies: Optional[List[str]] = None,
        renewable_energy_usage: Optional[float] = None,
        waste_diversion_rate: Optional[float] = None,
        water_usage_efficiency: Optional[float] = None,
        ethical_sourcing_score: Optional[float] = None,
        social_impact_score: Optional[float] = None,
        sustainability_report_url: Optional[str] = None,
    ) -> SupplierSustainability:
        """
        Calculate comprehensive sustainability profile for a supplier.
        """
        try:
            # Calculate sustainability score
            score = self.calculate_sustainability_score(
                entity_id=supplier_id,
                entity_type="supplier",
                carbon_footprint=carbon_footprint,
                energy_efficiency=None,  # TODO: Add energy efficiency
                water_efficiency=water_usage_efficiency,
                waste_diversion_rate=waste_diversion_rate,
                ethical_sourcing_score=ethical_sourcing_score,
                renewable_energy_percentage=renewable_energy_usage,
                social_impact_score=social_impact_score,
            )
            
            return SupplierSustainability(
                supplier_id=supplier_id,
                supplier_name=supplier_name,
                sustainability_score=score,
                carbon_footprint=carbon_footprint,
                certifications=certifications or [],
                sustainability_policies=sustainability_policies or [],
                renewable_energy_usage=renewable_energy_usage,
                waste_diversion_rate=waste_diversion_rate,
                water_usage_efficiency=water_usage_efficiency,
                ethical_sourcing_score=ethical_sourcing_score,
                social_impact_score=social_impact_score,
                sustainability_report_url=sustainability_report_url,
                confidence=DataConfidence.ESTIMATED,
                data_sources=["PeoplePay 360"],
            )
            
        except Exception as e:
            logger.error(f"Error calculating supplier sustainability: {e}")
            raise SustainabilityScoringError(f"Failed to calculate supplier sustainability: {e}")


# Singleton instance
_sustainability_scorer: Optional[SustainabilityScorer] = None


def get_sustainability_scorer(
    emission_calculator: Optional[EmissionCalculator] = None,
    category_weights: Optional[Dict[SustainabilityCategory, float]] = None,
) -> SustainabilityScorer:
    """Get the singleton SustainabilityScorer instance."""
    global _sustainability_scorer
    if _sustainability_scorer is None:
        _sustainability_scorer = SustainabilityScorer(emission_calculator, category_weights)
    return _sustainability_scorer
