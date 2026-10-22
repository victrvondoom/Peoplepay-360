"""
Supplier Intelligence Service - Data Models
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any
from uuid import uuid4


class SupplierStatus(Enum):
    ACTIVE = "active"
    PENDING = "pending"
    SUSPENDED = "suspended"
    DEACTIVATED = "deactivated"


class SupplierTier(Enum):
    PLATINUM = "platinum"
    GOLD = "gold"
    SILVER = "silver"
    BRONZE = "bronze"
    STANDARD = "standard"


class ProductCategory(Enum):
    ELECTRONICS = "electronics"
    FURNITURE = "furniture"
    OFFICE_SUPPLIES = "office_supplies"
    SOFTWARE = "software"
    SERVICES = "services"
    CONSUMABLES = "consumables"
    EQUIPMENT = "equipment"
    OTHER = "other"


@dataclass
class Product:
    product_id: str
    name: str
    description: str
    category: ProductCategory = ProductCategory.OTHER
    sku: Optional[str] = None
    price: Optional[float] = None
    currency: str = "USD"
    unit: str = "each"
    stock_quantity: Optional[int] = None
    in_stock: bool = True
    specifications: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    supplier_id: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Supplier:
    supplier_id: str
    name: str
    description: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[Dict[str, str]] = None
    website: Optional[str] = None
    status: SupplierStatus = SupplierStatus.ACTIVE
    tier: SupplierTier = SupplierTier.STANDARD
    categories: List[ProductCategory] = field(default_factory=list)
    founded_year: Optional[int] = None
    employee_count: Optional[int] = None
    annual_revenue: Optional[float] = None
    certifications: List[str] = field(default_factory=list)
    payment_terms: Optional[str] = None
    shipping_methods: List[str] = field(default_factory=list)
    return_policy: Optional[str] = None
    warranty_policy: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


class SupplierError(Exception):
    code: str = "SUPPLIER_ERROR"
    
    def __init__(self, message: str, code: Optional[str] = None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code


class SupplierNotFoundError(SupplierError):
    code = "SUPPLIER_NOT_FOUND"


class ProductNotFoundError(SupplierError):
    code = "PRODUCT_NOT_FOUND"


class InvalidSupplierDataError(SupplierError):
    code = "INVALID_SUPPLIER_DATA"


class SupplierSearchError(SupplierError):
    code = "SUPPLIER_SEARCH_ERROR"
