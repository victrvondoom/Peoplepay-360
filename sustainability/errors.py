"""
Sustainability Intelligence Service - Error Definitions
"""

from typing import Optional, Any


class PeoplePayError(Exception):
    """Base error for PeoplePay 360."""
    code: str = "PEOPLEPAY_ERROR"
    error_type: str = "error"
    
    def __init__(self, message: str, code: Optional[str] = None, error_type: Optional[str] = None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        if error_type:
            self.error_type = error_type


class SustainabilityError(PeoplePayError):
    """Base error for sustainability intelligence service."""
    code = "SUSTAINABILITY_ERROR"


class EmissionCalculationError(SustainabilityError):
    """Error during emission calculation."""
    code = "EMISSION_CALCULATION_ERROR"


class InvalidEmissionFactorError(SustainabilityError):
    """Invalid emission factor provided."""
    code = "INVALID_EMISSION_FACTOR_ERROR"


class MissingEmissionDataError(SustainabilityError):
    """Required emission data is missing."""
    code = "MISSING_EMISSION_DATA_ERROR"


class SustainabilityScoringError(SustainabilityError):
    """Error during sustainability scoring."""
    code = "SUSTAINABILITY_SCORING_ERROR"


class SupplierSustainabilityNotFoundError(SustainabilityError):
    """Supplier sustainability data not found."""
    code = "SUPPLIER_SUSTAINABILITY_NOT_FOUND"


class InvalidSustainabilityDataError(SustainabilityError):
    """Invalid sustainability data provided."""
    code = "INVALID_SUSTAINABILITY_DATA_ERROR"


class SustainabilityEvidenceError(SustainabilityError):
    """Error with sustainability evidence."""
    code = "SUSTAINABILITY_EVIDENCE_ERROR"


class CarbonFootprintCalculationError(SustainabilityError):
    """Error calculating carbon footprint."""
    code = "CARBON_FOOTPRINT_CALCULATION_ERROR"


# Singleton instances
emission_calculation_error = EmissionCalculationError
invalid_emission_factor_error = InvalidEmissionFactorError
missing_emission_data_error = MissingEmissionDataError
sustainability_scoring_error = SustainabilityScoringError
supplier_sustainability_not_found_error = SupplierSustainabilityNotFoundError
invalid_sustainability_data_error = InvalidSustainabilityDataError
sustainability_evidence_error = SustainabilityEvidenceError
carbon_footprint_calculation_error = CarbonFootprintCalculationError
