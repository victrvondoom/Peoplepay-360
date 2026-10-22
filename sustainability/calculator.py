"""
Sustainability Intelligence Service - Emission Calculator

Provides emissions calculations based on standardized emission factors.
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
    EmissionScope,
    DataConfidence,
    SustainabilityCategory,
)
from sustainability.errors import (
    EmissionCalculationError,
    InvalidEmissionFactorError,
    MissingEmissionDataError,
)

logger = logging.getLogger(__name__)


class EmissionCalculator:
    """
    Calculator for greenhouse gas emissions.
    
    Supports:
    - Direct emissions (Scope 1)
    - Energy indirect emissions (Scope 2)
    - Other indirect emissions (Scope 3)
    
    Uses standardized emission factors with provenance tracking.
    """

    # Default emission factors (kg CO2e per unit)
    DEFAULT_EMISSION_FACTORS = {
        "electricity_grid_us": {
            "name": "US Grid Electricity",
            "description": "Average CO2 emissions per kWh from US grid",
            "category": "energy",
            "unit": "kg CO2e per kWh",
            "value": 0.403,  # kg CO2e/kWh (US average)
            "source": "EPA eGRID 2021",
            "confidence": DataConfidence.VERIFIED,
            "region": "US",
            "year": 2021,
        },
        "electricity_grid_eu": {
            "name": "EU Grid Electricity",
            "description": "Average CO2 emissions per kWh from EU grid",
            "category": "energy",
            "unit": "kg CO2e per kWh",
            "value": 0.231,  # kg CO2e/kWh (EU-27 average)
            "source": "ENTSO-E 2022",
            "confidence": DataConfidence.VERIFIED,
            "region": "EU",
            "year": 2022,
        },
        "natural_gas_combustion": {
            "name": "Natural Gas Combustion",
            "description": "CO2 emissions from natural gas combustion",
            "category": "fuel",
            "unit": "kg CO2e per m3",
            "value": 1.89,  # kg CO2e/m3
            "source": "IPCC 2021",
            "confidence": DataConfidence.VERIFIED,
        },
        "diesel_combustion": {
            "name": "Diesel Combustion",
            "description": "CO2 emissions from diesel combustion",
            "category": "fuel",
            "unit": "kg CO2e per liter",
            "value": 2.68,  # kg CO2e/liter
            "source": "IPCC 2021",
            "confidence": DataConfidence.VERIFIED,
        },
        "truck_transport": {
            "name": "Truck Transport",
            "description": "CO2 emissions from heavy truck transport",
            "category": "transportation",
            "unit": "kg CO2e per ton-km",
            "value": 0.104,  # kg CO2e/ton-km
            "source": "EPA MOVES 2022",
            "confidence": DataConfidence.VERIFIED,
            "region": "US",
        },
        "ocean_freight": {
            "name": "Ocean Freight",
            "description": "CO2 emissions from ocean container shipping",
            "category": "transportation",
            "unit": "kg CO2e per ton-km",
            "value": 0.014,  # kg CO2e/ton-km
            "source": "ICCT 2021",
            "confidence": DataConfidence.VERIFIED,
        },
        "air_freight": {
            "name": "Air Freight",
            "description": "CO2 emissions from air cargo",
            "category": "transportation",
            "unit": "kg CO2e per ton-km",
            "value": 0.688,  # kg CO2e/ton-km
            "source": "IPCC 2021",
            "confidence": DataConfidence.VERIFIED,
        },
        "steel_production": {
            "name": "Steel Production",
            "description": "CO2 emissions from steel production (primary)",
            "category": "materials",
            "unit": "kg CO2e per kg",
            "value": 1.83,  # kg CO2e/kg
            "source": "World Steel Association 2022",
            "confidence": DataConfidence.VERIFIED,
        },
        "concrete_production": {
            "name": "Concrete Production",
            "description": "CO2 emissions from cement production",
            "category": "materials",
            "unit": "kg CO2e per kg",
            "value": 0.82,  # kg CO2e/kg cement
            "source": "IPCC 2021",
            "confidence": DataConfidence.VERIFIED,
        },
        "paper_production": {
            "name": "Paper Production",
            "description": "CO2 emissions from paper production",
            "category": "materials",
            "unit": "kg CO2e per kg",
            "value": 0.74,  # kg CO2e/kg
            "source": "EPA 2021",
            "confidence": DataConfidence.VERIFIED,
        },
        "plastic_production": {
            "name": "Plastic Production",
            "description": "CO2 emissions from plastic production",
            "category": "materials",
            "unit": "kg CO2e per kg",
            "value": 2.5,  # kg CO2e/kg (average)
            "source": "Plastics Europe 2022",
            "confidence": DataConfidence.ESTIMATED,
        },
    }

    def __init__(self, custom_emission_factors: Optional[Dict[str, Dict[str, Any]]] = None):
        self._emission_factors: Dict[str, EmissionFactor] = {}
        self._custom_factors: Dict[str, EmissionFactor] = {}
        
        # Load default emission factors
        for factor_id, factor_data in self.DEFAULT_EMISSION_FACTORS.items():
            self._emission_factors[factor_id] = EmissionFactor(
                id=factor_id,
                name=factor_data["name"],
                description=factor_data["description"],
                category=factor_data["category"],
                unit=factor_data["unit"],
                value=factor_data["value"],
                source=factor_data["source"],
                confidence=factor_data["confidence"],
                region=factor_data.get("region"),
                year=factor_data.get("year"),
            )
        
        # Load custom emission factors
        if custom_emission_factors:
            for factor_id, factor_data in custom_emission_factors.items():
                self._custom_factors[factor_id] = EmissionFactor(
                    id=factor_id,
                    name=factor_data.get("name", factor_id),
                    description=factor_data.get("description", ""),
                    category=factor_data.get("category", "custom"),
                    unit=factor_data.get("unit", ""),
                    value=factor_data["value"],
                    source=factor_data.get("source", "custom"),
                    confidence=factor_data.get("confidence", DataConfidence.SELF_REPORTED),
                    region=factor_data.get("region"),
                    year=factor_data.get("year"),
                )
                self._emission_factors[factor_id] = self._custom_factors[factor_id]

    def get_emission_factor(self, factor_id: str) -> EmissionFactor:
        """Get an emission factor by ID."""
        if factor_id not in self._emission_factors:
            raise InvalidEmissionFactorError(f"Emission factor '{factor_id}' not found")
        return self._emission_factors[factor_id]

    def list_emission_factors(
        self,
        category: Optional[str] = None,
        region: Optional[str] = None,
        confidence: Optional[DataConfidence] = None,
    ) -> List[EmissionFactor]:
        """List available emission factors with optional filtering."""
        factors = list(self._emission_factors.values())
        
        if category:
            factors = [f for f in factors if f.category == category]
        if region:
            factors = [f for f in factors if f.region == region]
        if confidence:
            factors = [f for f in factors if f.confidence == confidence]
        
        return factors

    def add_emission_factor(self, factor: EmissionFactor) -> EmissionFactor:
        """Add a custom emission factor."""
        if factor.id in self._emission_factors:
            raise InvalidEmissionFactorError(f"Emission factor '{factor.id}' already exists")
        
        self._emission_factors[factor.id] = factor
        self._custom_factors[factor.id] = factor
        
        logger.info(f"Added custom emission factor: {factor.id}")
        return factor

    def calculate_emission(
        self,
        factor_id: str,
        activity_value: float,
        unit: Optional[str] = None,
    ) -> EnvironmentalImpact:
        """
        Calculate emissions for a given activity.
        
        Args:
            factor_id: ID of the emission factor to use
            activity_value: The amount of activity (e.g., kWh, kg, km)
            unit: Optional unit override
            
        Returns:
            EnvironmentalImpact with the calculated emissions
        """
        try:
            factor = self.get_emission_factor(factor_id)
            
            if activity_value < 0:
                raise EmissionCalculationError("Activity value cannot be negative")
            
            calculated_value = factor.value * activity_value
            
            return EnvironmentalImpact(
                id=str(uuid4()),
                entity_id=factor_id,
                entity_type="emission_factor",
                category=SustainabilityCategory.CARBON_FOOTPRINT,
                impact_value=calculated_value,
                impact_unit=f"{factor.unit.split(' per ')[0]}",
                calculation_method=f"factor:{factor.id}",
                emission_factors=[factor.id],
                confidence=factor.confidence,
                metadata={
                    "factor_name": factor.name,
                    "factor_description": factor.description,
                    "source": factor.source,
                    "activity_value": activity_value,
                    "activity_unit": factor.unit.split(" per ")[-1],
                },
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
        """
        Calculate comprehensive carbon footprint across all scopes.
        
        Args:
            entity_id: ID of the entity (product, supplier, order)
            entity_type: Type of entity
            scope_1_data: Direct emission data {factor_id: value}
            scope_2_data: Energy indirect emission data {factor_id: value}
            scope_3_data: Other indirect emission data {factor_id: value}
            
        Returns:
            CarbonFootprint with calculated emissions
        """
        try:
            total_scope_1 = 0.0
            total_scope_2 = 0.0
            total_scope_3 = 0.0
            all_factors: List[str] = []
            assumptions: Dict[str, Any] = {}
            
            # Calculate Scope 1 (Direct emissions)
            if scope_1_data:
                for factor_id, value in scope_1_data.items():
                    factor = self.get_emission_factor(factor_id)
                    emissions = factor.value * value
                    total_scope_1 += emissions
                    all_factors.append(factor_id)
                    assumptions[factor_id] = {
                        "value": value,
                        "unit": factor.unit,
                    }
            
            # Calculate Scope 2 (Indirect from energy)
            if scope_2_data:
                for factor_id, value in scope_2_data.items():
                    factor = self.get_emission_factor(factor_id)
                    emissions = factor.value * value
                    total_scope_2 += emissions
                    all_factors.append(factor_id)
                    assumptions[factor_id] = {
                        "value": value,
                        "unit": factor.unit,
                    }
            
            # Calculate Scope 3 (Other indirect)
            if scope_3_data:
                for factor_id, value in scope_3_data.items():
                    factor = self.get_emission_factor(factor_id)
                    emissions = factor.value * value
                    total_scope_3 += emissions
                    all_factors.append(factor_id)
                    assumptions[factor_id] = {
                        "value": value,
                        "unit": factor.unit,
                    }
            
            total = total_scope_1 + total_scope_2 + total_scope_3
            
            # Determine confidence based on data completeness
            if scope_1_data and scope_2_data and scope_3_data:
                confidence = DataConfidence.VERIFIED
            elif (scope_1_data and scope_2_data) or (scope_2_data and scope_3_data):
                confidence = DataConfidence.ESTIMATED
            else:
                confidence = DataConfidence.MODELED
            
            return CarbonFootprint(
                id=str(uuid4()),
                entity_id=entity_id,
                entity_type=entity_type,
                total_co2e=total,
                scope_1_co2e=total_scope_1,
                scope_2_co2e=total_scope_2,
                scope_3_co2e=total_scope_3,
                calculation_method="comprehensive",
                emission_factors_used=all_factors,
                confidence=confidence,
                assumptions=assumptions,
                notes=f"Calculated using {len(all_factors)} emission factors",
            )
            
        except Exception as e:
            logger.error(f"Error calculating carbon footprint: {e}")
            raise MissingEmissionDataError(f"Failed to calculate carbon footprint: {e}")

    def calculate_product_carbon_footprint(
        self,
        product_id: str,
        weight_kg: float,
        material_composition: Dict[str, float],  # {"steel_kg": 10, "plastic_kg": 5, ...}
        manufacturing_region: str = "US",
        transport_distance_km: float = 0.0,
        transport_mode: str = "truck",
    ) -> CarbonFootprint:
        """
        Calculate carbon footprint for a specific product.
        
        This is a convenience method for common product carbon footprint calculations.
        """
        try:
            scope_3_data: Dict[str, float] = {}
            
            # Material emissions
            for material, weight in material_composition.items():
                if material == "steel_kg":
                    scope_3_data["steel_production"] = weight
                elif material == "concrete_kg":
                    scope_3_data["concrete_production"] = weight
                elif material == "paper_kg":
                    scope_3_data["paper_production"] = weight
                elif material == "plastic_kg":
                    scope_3_data["plastic_production"] = weight
            
            # Transport emissions
            if transport_distance_km > 0:
                if transport_mode == "truck":
                    scope_3_data["truck_transport"] = weight_kg * transport_distance_km / 1000
                elif transport_mode == "ocean":
                    scope_3_data["ocean_freight"] = weight_kg * transport_distance_km / 1000
                elif transport_mode == "air":
                    scope_3_data["air_freight"] = weight_kg * transport_distance_km / 1000
            
            # Manufacturing electricity
            if manufacturing_region == "US":
                scope_2_data = {"electricity_grid_us": weight_kg * 5}  # Estimate 5 kWh per kg
            elif manufacturing_region == "EU":
                scope_2_data = {"electricity_grid_eu": weight_kg * 5}
            else:
                scope_2_data = {}
            
            return self.calculate_carbon_footprint(
                entity_id=product_id,
                entity_type="product",
                scope_1_data=None,
                scope_2_data=scope_2_data,
                scope_3_data=scope_3_data,
            )
            
        except Exception as e:
            logger.error(f"Error calculating product carbon footprint: {e}")
            raise EmissionCalculationError(f"Failed to calculate product carbon footprint: {e}")


# Singleton instance
_emission_calculator: Optional[EmissionCalculator] = None


def get_emission_calculator(custom_factors: Optional[Dict[str, Dict[str, Any]]] = None) -> EmissionCalculator:
    """Get the singleton EmissionCalculator instance."""
    global _emission_calculator
    if _emission_calculator is None:
        _emission_calculator = EmissionCalculator(custom_factors)
    return _emission_calculator
