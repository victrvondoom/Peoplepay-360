"""
Sustainability Intelligence Service - Main Service

Provides comprehensive sustainability intelligence including emissions calculations,
scoring, supplier sustainability profiles, comparisons, and reporting.
"""

import logging
from dataclasses import field
from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import uuid4

from sustainability.models import (
    EmissionFactor,
    EnvironmentalImpact,
    CarbonFootprint,
    SustainabilityScore,
    SupplierSustainability,
    SustainabilityComparison,
    SustainabilityReport,
    SustainabilityCategory,
    DataConfidence,
    SustainabilityRating,
)
from sustainability.calculator import EmissionCalculator, get_emission_calculator
from sustainability.scoring import SustainabilityScorer, get_sustainability_scorer
from sustainability.errors import (
    SustainabilityError,
    EmissionCalculationError,
    SustainabilityScoringError,
    SupplierSustainabilityNotFoundError,
    InvalidSustainabilityDataError,
)
import logging

logger = logging.getLogger(__name__)


class SustainabilityService:
    """
    Main service for sustainability intelligence.
    
    Provides:
    - Emission calculations
    - Carbon footprint calculations
    - Sustainability scoring
    - Supplier sustainability profiles
    - Comparisons between suppliers
    - Report generation
    - Evidence-backed assessments
    """

    def __init__(
        self,
        emission_calculator: Optional[EmissionCalculator] = None,
        sustainability_scorer: Optional[SustainabilityScorer] = None,
    ):
        self._emission_calculator = emission_calculator or get_emission_calculator()
        self._sustainability_scorer = sustainability_scorer or get_sustainability_scorer()
        
        # In-memory storage for supplier sustainability data
        self._supplier_sustainability: Dict[str, SupplierSustainability] = {}
        self._carbon_footprints: Dict[str, CarbonFootprint] = {}
        self._sustainability_scores: Dict[str, SustainabilityScore] = {}
        self._sustainability_reports: Dict[str, SustainabilityReport] = {}
        
        logger.info("SustainabilityService initialized")

    # ==================== Emission Calculations ====================

    def calculate_emission(
        self,
        factor_id: str,
        activity_value: float,
        unit: Optional[str] = None,
    ) -> EnvironmentalImpact:
        """Calculate emissions for a given activity using a specific emission factor."""
        try:
            return self._emission_calculator.calculate_emission(
                factor_id, activity_value, unit
            )
        except Exception as e:
            logger.error(f"Error calculating emission: {e}")
            raise EmissionCalculationError(f"Failed to calculate emission: {e}")

    def calculate_carbon_footprint(
        self,
        entity_id: str,
        entity_type: str,
        scope_1_data: Optional[Dict[str, float]] = None,
        scope_2_data: Optional[Dict[str, float]] = None,
        scope_3_data: Optional[Dict[str, float]] = None,
    ) -> CarbonFootprint:
        """Calculate comprehensive carbon footprint for an entity."""
        try:
            footprint = self._emission_calculator.calculate_carbon_footprint(
                entity_id, entity_type, scope_1_data, scope_2_data, scope_3_data
            )
            self._carbon_footprints[footprint.id] = footprint
            logger.info(f"Calculated carbon footprint for {entity_type}:{entity_id}")
            return footprint
        except Exception as e:
            logger.error(f"Error calculating carbon footprint: {e}")
            raise EmissionCalculationError(f"Failed to calculate carbon footprint: {e}")

    def get_carbon_footprint(self, footprint_id: str) -> Optional[CarbonFootprint]:
        """Get a previously calculated carbon footprint."""
        return self._carbon_footprints.get(footprint_id)

    def list_carbon_footprints(self, entity_id: Optional[str] = None) -> List[CarbonFootprint]:
        """List carbon footprints with optional filtering."""
        footprints = list(self._carbon_footprints.values())
        if entity_id:
            footprints = [f for f in footprints if f.entity_id == entity_id]
        return footprints

    def calculate_product_carbon_footprint(
        self,
        product_id: str,
        weight_kg: float,
        material_composition: Dict[str, float],
        manufacturing_region: str = "US",
        transport_distance_km: float = 0.0,
        transport_mode: str = "truck",
    ) -> CarbonFootprint:
        """Calculate carbon footprint for a specific product."""
        try:
            footprint = self._emission_calculator.calculate_product_carbon_footprint(
                product_id, weight_kg, material_composition,
                manufacturing_region, transport_distance_km, transport_mode
            )
            self._carbon_footprints[footprint.id] = footprint
            return footprint
        except Exception as e:
            logger.error(f"Error calculating product carbon footprint: {e}")
            raise EmissionCalculationError(f"Failed to calculate product carbon footprint: {e}")

    # ==================== Sustainability Scoring ====================

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
        """Calculate comprehensive sustainability score for an entity."""
        try:
            score = self._sustainability_scorer.calculate_sustainability_score(
                entity_id, entity_type,
                carbon_footprint, energy_efficiency, water_efficiency,
                waste_diversion_rate, ethical_sourcing_score, recycled_content,
                transport_distance, transport_mode, packaging_weight,
                recyclable_percentage, renewable_energy_percentage, social_impact_score,
                category_weights,
            )
            self._sustainability_scores[score.id] = score
            logger.info(f"Calculated sustainability score for {entity_type}:{entity_id}")
            return score
        except Exception as e:
            logger.error(f"Error calculating sustainability score: {e}")
            raise SustainabilityScoringError(f"Failed to calculate sustainability score: {e}")

    def get_sustainability_score(self, score_id: str) -> Optional[SustainabilityScore]:
        """Get a previously calculated sustainability score."""
        return self._sustainability_scores.get(score_id)

    def list_sustainability_scores(
        self, entity_id: Optional[str] = None
    ) -> List[SustainabilityScore]:
        """List sustainability scores with optional filtering."""
        scores = list(self._sustainability_scores.values())
        if entity_id:
            scores = [s for s in scores if s.entity_id == entity_id]
        return scores

    # ==================== Supplier Sustainability ====================

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
        """Calculate comprehensive sustainability profile for a supplier."""
        try:
            supplier = self._sustainability_scorer.calculate_supplier_sustainability(
                supplier_id, supplier_name,
                carbon_footprint, certifications, sustainability_policies,
                renewable_energy_usage, waste_diversion_rate,
                water_usage_efficiency, ethical_sourcing_score,
                social_impact_score, sustainability_report_url,
            )
            self._supplier_sustainability[supplier.supplier_id] = supplier
            logger.info(f"Calculated sustainability for supplier: {supplier.supplier_name}")
            return supplier
        except Exception as e:
            logger.error(f"Error calculating supplier sustainability: {e}")
            raise SustainabilityScoringError(f"Failed to calculate supplier sustainability: {e}")

    def get_supplier_sustainability(self, supplier_id: str) -> Optional[SupplierSustainability]:
        """Get sustainability data for a specific supplier."""
        return self._supplier_sustainability.get(supplier_id)

    def list_supplier_sustainability(self) -> List[SupplierSustainability]:
        """List all supplier sustainability profiles."""
        return list(self._supplier_sustainability.values())

    def update_supplier_sustainability(
        self,
        supplier_id: str,
        **kwargs,
    ) -> Optional[SupplierSustainability]:
        """Update sustainability data for a supplier."""
        supplier = self._supplier_sustainability.get(supplier_id)
        if supplier is None:
            raise SupplierSustainabilityNotFoundError(f"Supplier {supplier_id} not found")
        
        for key, value in kwargs.items():
            if hasattr(supplier, key):
                setattr(supplier, key, value)
        
        supplier.last_assessed = datetime.utcnow()
        logger.info(f"Updated sustainability for supplier: {supplier_id}")
        return supplier

    # ==================== Comparisons ====================

    def compare_suppliers(
        self,
        supplier_ids: List[str],
        metric: str = "overall_score",
    ) -> SustainabilityComparison:
        """Compare sustainability metrics between multiple suppliers."""
        try:
            values: Dict[str, float] = {}
            
            for supplier_id in supplier_ids:
                supplier = self._supplier_sustainability.get(supplier_id)
                if supplier and supplier.sustainability_score:
                    if metric == "overall_score":
                        values[supplier_id] = supplier.sustainability_score.overall_score
                    elif metric == "carbon_footprint" and supplier.carbon_footprint:
                        values[supplier_id] = supplier.carbon_footprint.total_co2e
                    elif metric == "rating":
                        # Map rating to numeric value
                        rating_values = {
                            SustainabilityRating.EXCELLENT: 5.0,
                            SustainabilityRating.GOOD: 4.0,
                            SustainabilityRating.FAIR: 3.0,
                            SustainabilityRating.POOR: 2.0,
                            SustainabilityRating.UNKNOWN: 1.0,
                        }
                        if supplier.sustainability_score:
                            values[supplier_id] = rating_values.get(
                                supplier.sustainability_score.rating, 0.0
                            )
            
            if not values:
                raise InvalidSustainabilityDataError(
                    f"No data available for metric: {metric}"
                )
            
            # Calculate statistics
            vals = list(values.values())
            avg = sum(vals) / len(vals)
            variance = sum((v - avg) ** 2 for v in vals) / len(vals) if len(vals) > 1 else 0
            std_dev = variance ** 0.5
            
            # Normalize values (0-100 scale)
            if max(vals) - min(vals) > 0:
                normalized = {k: ((v - min(vals)) / (max(vals) - min(vals))) * 100 
                            for k, v in values.items()}
            else:
                normalized = {k: 50.0 for k in values}
            
            return SustainabilityComparison(
                comparison_id=str(uuid4()),
                supplier_ids=supplier_ids,
                metric=metric,
                values=values,
                normalized_values=normalized,
                best_performer=max(values, key=values.get) if values else None,
                worst_performer=min(values, key=values.get) if values else None,
                average=avg,
                std_deviation=std_dev,
            )
        except Exception as e:
            logger.error(f"Error comparing suppliers: {e}")
            raise SustainabilityScoringError(f"Failed to compare suppliers: {e}")

    # ==================== Reports ====================

    def generate_sustainability_report(
        self,
        title: str,
        organization_id: Optional[str] = None,
        order_id: Optional[str] = None,
        supplier_ids: Optional[List[str]] = None,
        include_details: bool = True,
    ) -> SustainabilityReport:
        """Generate a comprehensive sustainability report."""
        try:
            sections: List[Dict[str, Any]] = []
            metrics: Dict[str, Any] = {}
            scores: List[SustainabilityScore] = []
            footprints: List[CarbonFootprint] = []
            recommendations: List[str] = []
            
            # Executive Summary
            sections.append({
                "title": "Executive Summary",
                "content": f"This report provides a comprehensive sustainability assessment for {'organization ' + organization_id if organization_id else 'the specified entities'}.",
            })
            
            # Collect data
            if supplier_ids:
                for supplier_id in supplier_ids:
                    supplier = self._supplier_sustainability.get(supplier_id)
                    if supplier:
                        if supplier.sustainability_score:
                            scores.append(supplier.sustainability_score)
                        if supplier.carbon_footprint:
                            footprints.append(supplier.carbon_footprint)
                        
                        # Add supplier section
                        sections.append({
                            "title": f"Supplier: {supplier.supplier_name}",
                            "content": self._format_supplier_section(supplier),
                        })
            
            # Calculate aggregate metrics
            total_co2e = sum(f.total_co2e for f in footprints)
            avg_score = sum(s.overall_score for s in scores) / len(scores) if scores else 0
            
            metrics = {
                "total_carbon_footprint_kg_co2e": total_co2e,
                "average_sustainability_score": avg_score,
                "number_of_suppliers": len(supplier_ids or []),
                "report_generated_at": datetime.utcnow().isoformat(),
            }
            
            # Add recommendations
            if avg_score < 70:
                recommendations.append(
                    "Overall sustainability score is below 70. Consider implementing "
                    "improvement programs across suppliers."
                )
            
            if total_co2e > 10000:
                recommendations.append(
                    f"Total carbon footprint of {total_co2e:.2f} kg CO2e is high. "
                    "Consider carbon reduction initiatives."
                )
            
            # Finalize report
            report = SustainabilityReport(
                report_id=str(uuid4()),
                organization_id=organization_id,
                order_id=order_id,
                title=title,
                summary=f"Sustainability assessment covering {len(supplier_ids or [])} suppliers with average score of {avg_score:.1f}",
                sections=sections,
                metrics=metrics,
                sustainability_scores=scores,
                carbon_footprints=footprints,
                recommendations=recommendations,
            )
            
            self._sustainability_reports[report.report_id] = report
            logger.info(f"Generated sustainability report: {report.title}")
            return report
            
        except Exception as e:
            logger.error(f"Error generating sustainability report: {e}")
            raise SustainabilityScoringError(f"Failed to generate sustainability report: {e}")

    def _format_supplier_section(self, supplier: SupplierSustainability) -> str:
        """Format a supplier section for the report."""
        lines = []
        lines.append(f"**Supplier ID:** {supplier.supplier_id}")
        lines.append(f"**Name:** {supplier.supplier_name}")
        
        if supplier.sustainability_score:
            lines.append(
                f"**Overall Score:** {supplier.sustainability_score.overall_score:.1f}/100 "
                f"({supplier.sustainability_score.rating.value})"
            )
        
        if supplier.carbon_footprint:
            lines.append(
                f"**Carbon Footprint:** {supplier.carbon_footprint.total_co2e:.2f} kg CO2e"
            )
        
        if supplier.certifications:
            lines.append(f"**Certifications:** {', '.join(supplier.certifications)}")
        
        if supplier.renewable_energy_usage:
            lines.append(f"**Renewable Energy:** {supplier.renewable_energy_usage:.1f}%")
        
        if supplier.waste_diversion_rate:
            lines.append(f"**Waste Diversion:** {supplier.waste_diversion_rate:.1f}%")
        
        return "\n".join(lines)

    def get_sustainability_report(self, report_id: str) -> Optional[SustainabilityReport]:
        """Get a previously generated sustainability report."""
        return self._sustainability_reports.get(report_id)

    def list_sustainability_reports(
        self,
        organization_id: Optional[str] = None,
        order_id: Optional[str] = None,
    ) -> List[SustainabilityReport]:
        """List sustainability reports with optional filtering."""
        reports = list(self._sustainability_reports.values())
        if organization_id:
            reports = [r for r in reports if r.organization_id == organization_id]
        if order_id:
            reports = [r for r in reports if r.order_id == order_id]
        return reports

    # ==================== Evidence & Provenance ====================

    def get_emission_factor_provenance(self, factor_id: str) -> Dict[str, Any]:
        """Get provenance information for an emission factor."""
        try:
            factor = self._emission_calculator.get_emission_factor(factor_id)
            return {
                "id": factor.id,
                "name": factor.name,
                "description": factor.description,
                "value": factor.value,
                "unit": factor.unit,
                "source": factor.source,
                "confidence": factor.confidence.value,
                "region": factor.region,
                "year": factor.year,
                "category": factor.category,
                "created_at": factor.created_at.isoformat(),
                "updated_at": factor.updated_at.isoformat(),
            }
        except Exception as e:
            logger.error(f"Error getting emission factor provenance: {e}")
            raise InvalidSustainabilityDataError(f"Failed to get emission factor provenance: {e}")

    def get_calculation_audit_trail(
        self,
        entity_id: str,
        entity_type: str,
    ) -> Dict[str, Any]:
        """Get audit trail for sustainability calculations for an entity."""
        scores = self.list_sustainability_scores(entity_id)
        footprints = self.list_carbon_footprints(entity_id)
        
        return {
            "entity_id": entity_id,
            "entity_type": entity_type,
            "sustainability_scores": [
                {
                    "score_id": s.id,
                    "overall_score": s.overall_score,
                    "rating": s.rating.value,
                    "timestamp": s.timestamp.isoformat(),
                    "confidence": s.confidence.value,
                } for s in scores
            ],
            "carbon_footprints": [
                {
                    "footprint_id": f.id,
                    "total_co2e": f.total_co2e,
                    "timestamp": f.timestamp.isoformat(),
                    "confidence": f.confidence.value,
                } for f in footprints
            ],
        }


# Singleton instance
_sustainability_service: Optional[SustainabilityService] = None


def get_sustainability_service(
    emission_calculator: Optional[EmissionCalculator] = None,
    sustainability_scorer: Optional[SustainabilityScorer] = None,
) -> SustainabilityService:
    """Get the singleton SustainabilityService instance."""
    global _sustainability_service
    if _sustainability_service is None:
        _sustainability_service = SustainabilityService(emission_calculator, sustainability_scorer)
    return _sustainability_service
