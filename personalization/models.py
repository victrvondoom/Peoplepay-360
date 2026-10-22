"""
Personalization Service - Data Models
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any
from uuid import uuid4


class PreferenceType(Enum):
    BUDGET = "budget"
    CATEGORY = "category"
    QUALITY = "quality"
    SUSTAINABILITY = "sustainability"
    PRICE = "price"
    DELIVERY_SPEED = "delivery_speed"
    SUPPLIER_RELIABILITY = "supplier_reliability"


class RecommendationType(Enum):
    PRODUCT = "product"
    SUPPLIER = "supplier"
    BUNDLE = "bundle"


@dataclass
class UserPreference:
    user_id: str
    preference_type: PreferenceType
    value: Any
    priority: int = 1  # 1-5 scale
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class OrganizationPreference:
    organization_id: str
    preference_type: PreferenceType
    value: Any
    applies_to_all: bool = True
    user_exceptions: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Recommendation:
    recommendation_id: str = field(default_factory=lambda: str(uuid4()))
    user_id: Optional[str] = None
    organization_id: Optional[str] = None
    recommendation_type: RecommendationType = RecommendationType.PRODUCT
    items: List[str] = field(default_factory=list)  # IDs of recommended items
    score: float = 0.0
    explanation: str = ""
    confidence: float = 0.0
    evidence: List[Dict[str, Any]] = field(default_factory=list)
    alternatives: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)


class PersonalizationError(Exception):
    code: str = "PERSONALIZATION_ERROR"
    
    def __init__(self, message: str, code: Optional[str] = None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
