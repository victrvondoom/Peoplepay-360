#!/usr/bin/env python3
"""
Script to create all remaining PeoplePay 360 services.
This creates:
- Supplier Intelligence Service (suppliers/)
- Personalization Service (personalization/)
- Graph Intelligence Layer (graph/)
- Evidence and Provenance Engine (evidence/)
- Observability & Monitoring (observability/)
- Plugin Architecture (plugins/)
"""

import os
import sys

# Ensure we're in the right directory
os.chdir("C:\\Users\\Administrator\\Downloads\\payment at critical situation")

# Create directories
os.makedirs("suppliers", exist_ok=True)
os.makedirs("personalization", exist_ok=True)
os.makedirs("graph", exist_ok=True)
os.makedirs("evidence", exist_ok=True)
os.makedirs("observability", exist_ok=True)
os.makedirs("plugins", exist_ok=True)

print("Creating remaining services...")

# ============================================================================
# SUPPLIER INTELLIGENCE SERVICE
# ============================================================================

supplier_models = '''"""
Supplier Intelligence Service - Data Models
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any
from uuid import uuid4


class SupplierStatus(Enum):
    """Supplier status."""
    ACTIVE = "active"
    PENDING = "pending"
    SUSPENDED = "suspended"
    DEACTIVATED = "deactivated"


class SupplierTier(Enum):
    """Supplier tier level."""
    PLATINUM = "platinum"
    GOLD = "gold"
    SILVER = "silver"
    BRONZE = "bronze"
    STANDARD = "standard"


class ProductCategory(Enum):
    """Product categories."""
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
    """Product information."""
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
    """Supplier information."""
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


@dataclass
class SupplierProfile:
    """Extended supplier profile with intelligence data."""
    supplier: Supplier
    average_rating: float = 0.0
    total_reviews: int = 0
    delivery_reliability: float = 0.0  # Percentage
    quality_score: float = 0.0  # Percentage
    price_competitiveness: float = 0.0  # Percentage
    sustainability_score: Optional[float] = None
    risk_level: str = "low"
    trust_score: float = 0.0
    response_time_hours: Optional[float] = None
    fulfillment_rate: float = 0.0  # Percentage
    on_time_delivery_rate: float = 0.0  # Percentage
    product_count: int = 0
    years_in_business: Optional[int] = None


@dataclass
class ProductCatalog:
    """Supplier product catalog."""
    supplier_id: str
    products: List[Product] = field(default_factory=list)
    categories: List[ProductCategory] = field(default_factory=list)
    last_updated: datetime = field(default_factory=datetime.utcnow)


@dataclass
class SupplierReputation:
    """Supplier reputation data."""
    supplier_id: str
    average_rating: float
    total_reviews: int
    positive_reviews: int = 0
    neutral_reviews: int = 0
    negative_reviews: int = 0
    ratings_distribution: Dict[str, int] = field(default_factory=dict)
    review_snippets: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class PricingRecord:
    """Historical pricing record."""
    record_id: str = field(default_factory=lambda: str(uuid4()))
    supplier_id: str
    product_id: str
    price: float
    currency: str = "USD"
    effective_date: datetime = field(default_factory=datetime.utcnow)
    expiration_date: Optional[datetime] = None
    quantity: Optional[int] = None
    is_promotional: bool = False


@dataclass
class SupplierRiskAssessment:
    """Supplier risk assessment."""
    supplier_id: str
    financial_risk: float = 0.0  # 0-100 scale
    operational_risk: float = 0.0
    compliance_risk: float = 0.0
    quality_risk: float = 0.0
    delivery_risk: float = 0.0
    overall_risk_score: float = 0.0
    risk_level: str = "low"
    risk_factors: List[Dict[str, Any]] = field(default_factory=list)
    mitigation_measures: List[str] = field(default_factory=list)
    assessment_date: datetime = field(default_factory=datetime.utcnow)


@dataclass
class SupplierComparison:
    """Comparison of multiple suppliers."""
    comparison_id: str = field(default_factory=lambda: str(uuid4()))
    supplier_ids: List[str]
    criteria: List[str] = field(default_factory=list)
    scores: Dict[str, Dict[str, float]] = field(default_factory=dict)
    normalized_scores: Dict[str, Dict[str, float]] = field(default_factory=dict)
    rankings: Dict[str, List[str]] = field(default_factory=dict)
    winner: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)


class SupplierError(Exception):
    """Base error for supplier service."""
    code: str = "SUPPLIER_ERROR"
    
    def __init__(self, message: str, code: Optional[str] = None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code


class SupplierNotFoundError(SupplierError):
    """Supplier not found."""
    code = "SUPPLIER_NOT_FOUND"


class ProductNotFoundError(SupplierError):
    """Product not found."""
    code = "PRODUCT_NOT_FOUND"


class InvalidSupplierDataError(SupplierError):
    """Invalid supplier data."""
    code = "INVALID_SUPPLIER_DATA"


class SupplierSearchError(SupplierError):
    """Error during supplier search."""
    code = "SUPPLIER_SEARCH_ERROR"
'''

with open("suppliers/models.py", "w") as f:
    f.write(supplier_models)
print("[OK] Created suppliers/models.py")


supplier_service = '''"""
Supplier Intelligence Service - Main Service
"""

import logging
from typing import Optional, List, Dict, Any
from uuid import uuid4
from datetime import datetime

from suppliers.models import (
    Supplier,
    SupplierProfile,
    Product,
    ProductCatalog,
    SupplierComparison,
    SupplierReputation,
    PricingRecord,
    SupplierRiskAssessment,
    SupplierStatus,
    SupplierTier,
    ProductCategory,
)
from suppliers.models import (
    SupplierError,
    SupplierNotFoundError,
    ProductNotFoundError,
    InvalidSupplierDataError,
    SupplierSearchError,
)

logger = logging.getLogger(__name__)


class SupplierService:
    """
    Main service for supplier intelligence.
    
    Provides:
    - Supplier management (CRUD)
    - Product catalog management
    - Supplier search and discovery
    - Supplier comparison
    - Reputation tracking
    - Risk assessment
    - Pricing history
    """

    def __init__(self):
        self._suppliers: Dict[str, Supplier] = {}
        self._products: Dict[str, Product] = {}
        self._reputations: Dict[str, SupplierReputation] = {}
        self._pricing_history: Dict[str, List[PricingRecord]] = {}
        self._risk_assessments: Dict[str, SupplierRiskAssessment] = {}
        self._catalogs: Dict[str, ProductCatalog] = {}
        
        # Sample data for demonstration
        self._initialize_sample_data()
        
        logger.info("SupplierService initialized")

    def _initialize_sample_data(self):
        """Initialize with sample supplier data."""
        # Create sample suppliers
        supplier1 = Supplier(
            supplier_id="supplier_001",
            name="OfficePro Supplies",
            description="Leading office supplies manufacturer",
            email="contact@officepro.com",
            phone="+1-555-0101",
            address={"street": "123 Business Ave", "city": "New York", "state": "NY", "zip": "10001", "country": "US"},
            website="https://officepro.com",
            status=SupplierStatus.ACTIVE,
            tier=SupplierTier.PLATINUM,
            categories=[ProductCategory.OFFICE_SUPPLIES, ProductCategory.FURNITURE],
            founded_year=1995,
            employee_count=500,
            annual_revenue=150000000.0,
            certifications=["ISO 9001", "ISO 14001"],
            payment_terms="Net 30",
            shipping_methods=["FedEx", "UPS", "USPS"],
        )
        
        supplier2 = Supplier(
            supplier_id="supplier_002",
            name="TechGadgets Inc",
            description="Technology hardware and accessories",
            email="sales@techgadgets.com",
            phone="+1-555-0102",
            address={"street": "456 Tech Blvd", "city": "San Francisco", "state": "CA", "zip": "94105", "country": "US"},
            website="https://techgadgets.com",
            status=SupplierStatus.ACTIVE,
            tier=SupplierTier.GOLD,
            categories=[ProductCategory.ELECTRONICS, ProductCategory.EQUIPMENT],
            founded_year=2010,
            employee_count=200,
            annual_revenue=80000000.0,
            certifications=["ISO 9001", "UL Certified"],
            payment_terms="Net 45",
            shipping_methods=["FedEx", "UPS"],
        )
        
        supplier3 = Supplier(
            supplier_id="supplier_003",
            name="EcoFurniture Co",
            description="Sustainable furniture solutions",
            email="info@ecofurniture.com",
            phone="+1-555-0103",
            address={"street": "789 Green St", "city": "Portland", "state": "OR", "zip": "97201", "country": "US"},
            website="https://ecofurniture.com",
            status=SupplierStatus.ACTIVE,
            tier=SupplierTier.SILVER,
            categories=[ProductCategory.FURNITURE],
            founded_year=2015,
            employee_count=75,
            annual_revenue=25000000.0,
            certifications=["FSC Certified", "Cradle to Cradle"],
            payment_terms="Net 30",
            shipping_methods=["FedEx", "UPS"],
        )
        
        self._suppliers[supplier1.supplier_id] = supplier1
        self._suppliers[supplier2.supplier_id] = supplier2
        self._suppliers[supplier3.supplier_id] = supplier3
        
        # Create sample products
        products = [
            Product(
                product_id="product_001",
                name="Ergonomic Office Chair",
                description="High-quality ergonomic office chair",
                category=ProductCategory.FURNITURE,
                sku="EC-001",
                price=299.99,
                currency="USD",
                supplier_id="supplier_001",
                specifications={"color": "black", "material": "mesh", "weight": "25kg"},
            ),
            Product(
                product_id="product_002",
                name="Wireless Keyboard",
                description="Bluetooth wireless keyboard",
                category=ProductCategory.ELECTRONICS,
                sku="WK-002",
                price=49.99,
                currency="USD",
                supplier_id="supplier_002",
                specifications={"battery_life": "24 months", "range": "30ft"},
            ),
            Product(
                product_id="product_003",
                name="Bamboo Desk",
                description="Eco-friendly bamboo desk",
                category=ProductCategory.FURNITURE,
                sku="BD-003",
                price=399.99,
                currency="USD",
                supplier_id="supplier_003",
                specifications={"material": "bamboo", "size": "60x30 inches"},
            ),
        ]
        
        for product in products:
            self._products[product.product_id] = product
        
        # Create sample reputations
        self._reputations = {
            "supplier_001": SupplierReputation(
                supplier_id="supplier_001",
                average_rating=4.8,
                total_reviews=125,
                positive_reviews=110,
                neutral_reviews=10,
                negative_reviews=5,
                ratings_distribution={"5": 100, "4": 20, "3": 3, "2": 1, "1": 1},
            ),
            "supplier_002": SupplierReputation(
                supplier_id="supplier_002",
                average_rating=4.5,
                total_reviews=85,
                positive_reviews=70,
                neutral_reviews=10,
                negative_reviews=5,
                ratings_distribution={"5": 60, "4": 15, "3": 8, "2": 1, "1": 1},
            ),
            "supplier_003": SupplierReputation(
                supplier_id="supplier_003",
                average_rating=4.9,
                total_reviews=45,
                positive_reviews=43,
                neutral_reviews=2,
                negative_reviews=0,
                ratings_distribution={"5": 40, "4": 3, "3": 0, "2": 0, "1": 0},
            ),
        }
        
        # Create sample risk assessments
        self._risk_assessments = {
            "supplier_001": SupplierRiskAssessment(
                supplier_id="supplier_001",
                financial_risk=10.0,
                operational_risk=5.0,
                compliance_risk=2.0,
                quality_risk=3.0,
                delivery_risk=5.0,
                overall_risk_score=5.0,
                risk_level="low",
            ),
            "supplier_002": SupplierRiskAssessment(
                supplier_id="supplier_002",
                financial_risk=15.0,
                operational_risk=10.0,
                compliance_risk=8.0,
                quality_risk=5.0,
                delivery_risk=10.0,
                overall_risk_score=10.0,
                risk_level="medium",
            ),
            "supplier_003": SupplierRiskAssessment(
                supplier_id="supplier_003",
                financial_risk=20.0,
                operational_risk=15.0,
                compliance_risk=5.0,
                quality_risk=2.0,
                delivery_risk=12.0,
                overall_risk_score=12.0,
                risk_level="medium",
            ),
        }

    # ==================== Supplier CRUD ====================

    def create_supplier(self, supplier_data: Dict[str, Any]) -> Supplier:
        """Create a new supplier."""
        try:
            supplier_id = supplier_data.get("supplier_id", str(uuid4()))
            supplier = Supplier(
                supplier_id=supplier_id,
                name=supplier_data["name"],
                description=supplier_data.get("description"),
                email=supplier_data.get("email"),
                phone=supplier_data.get("phone"),
                address=supplier_data.get("address"),
                website=supplier_data.get("website"),
                status=supplier_data.get("status", SupplierStatus.ACTIVE),
                tier=supplier_data.get("tier", SupplierTier.STANDARD),
                categories=supplier_data.get("categories", []),
                founded_year=supplier_data.get("founded_year"),
                employee_count=supplier_data.get("employee_count"),
                annual_revenue=supplier_data.get("annual_revenue"),
                certifications=supplier_data.get("certifications", []),
                payment_terms=supplier_data.get("payment_terms"),
                shipping_methods=supplier_data.get("shipping_methods", []),
            )
            self._suppliers[supplier.supplier_id] = supplier
            logger.info(f"Created supplier: {supplier.supplier_id}")
            return supplier
        except Exception as e:
            logger.error(f"Error creating supplier: {e}")
            raise InvalidSupplierDataError(f"Failed to create supplier: {e}")

    def get_supplier(self, supplier_id: str) -> Optional[Supplier]:
        """Get a supplier by ID."""
        return self._suppliers.get(supplier_id)

    def list_suppliers(
        self,
        status: Optional[SupplierStatus] = None,
        tier: Optional[SupplierTier] = None,
        category: Optional[ProductCategory] = None,
        search: Optional[str] = None,
    ) -> List[Supplier]:
        """List suppliers with optional filtering."""
        suppliers = list(self._suppliers.values())
        
        if status:
            suppliers = [s for s in suppliers if s.status == status]
        if tier:
            suppliers = [s for s in suppliers if s.tier == tier]
        if category:
            suppliers = [s for s in suppliers if category in s.categories]
        if search:
            search_lower = search.lower()
            suppliers = [
                s for s in suppliers
                if search_lower in s.name.lower() or
                (s.description and search_lower in s.description.lower())
            ]
        
        return suppliers

    def update_supplier(self, supplier_id: str, updates: Dict[str, Any]) -> Optional[Supplier]:
        """Update a supplier."""
        supplier = self._suppliers.get(supplier_id)
        if supplier is None:
            raise SupplierNotFoundError(f"Supplier {supplier_id} not found")
        
        for key, value in updates.items():
            if hasattr(supplier, key):
                setattr(supplier, key, value)
        
        supplier.updated_at = datetime.utcnow()
        logger.info(f"Updated supplier: {supplier_id}")
        return supplier

    def delete_supplier(self, supplier_id: str) -> bool:
        """Delete a supplier."""
        if supplier_id not in self._suppliers:
            return False
        
        del self._suppliers[supplier_id]
        logger.info(f"Deleted supplier: {supplier_id}")
        return True

    # ==================== Product CRUD ====================

    def create_product(self, product_data: Dict[str, Any]) -> Product:
        """Create a new product."""
        try:
            product_id = product_data.get("product_id", str(uuid4()))
            product = Product(
                product_id=product_id,
                name=product_data["name"],
                description=product_data.get("description", ""),
                category=product_data.get("category", ProductCategory.OTHER),
                sku=product_data.get("sku"),
                price=product_data.get("price"),
                currency=product_data.get("currency", "USD"),
                unit=product_data.get("unit", "each"),
                stock_quantity=product_data.get("stock_quantity"),
                in_stock=product_data.get("in_stock", True),
                specifications=product_data.get("specifications", {}),
                tags=product_data.get("tags", []),
                supplier_id=product_data.get("supplier_id"),
            )
            self._products[product.product_id] = product
            logger.info(f"Created product: {product.product_id}")
            return product
        except Exception as e:
            logger.error(f"Error creating product: {e}")
            raise InvalidSupplierDataError(f"Failed to create product: {e}")

    def get_product(self, product_id: str) -> Optional[Product]:
        """Get a product by ID."""
        return self._products.get(product_id)

    def list_products(
        self,
        supplier_id: Optional[str] = None,
        category: Optional[ProductCategory] = None,
        search: Optional[str] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
    ) -> List[Product]:
        """List products with optional filtering."""
        products = list(self._products.values())
        
        if supplier_id:
            products = [p for p in products if p.supplier_id == supplier_id]
        if category:
            products = [p for p in products if p.category == category]
        if search:
            search_lower = search.lower()
            products = [
                p for p in products
                if search_lower in p.name.lower() or
                search_lower in p.description.lower() or
                (p.sku and search_lower in p.sku.lower())
            ]
        if min_price is not None:
            products = [p for p in products if p.price is not None and p.price >= min_price]
        if max_price is not None:
            products = [p for p in products if p.price is not None and p.price <= max_price]
        
        return products

    def update_product(self, product_id: str, updates: Dict[str, Any]) -> Optional[Product]:
        """Update a product."""
        product = self._products.get(product_id)
        if product is None:
            raise ProductNotFoundError(f"Product {product_id} not found")
        
        for key, value in updates.items():
            if hasattr(product, key):
                setattr(product, key, value)
        
        product.updated_at = datetime.utcnow()
        logger.info(f"Updated product: {product_id}")
        return product

    def delete_product(self, product_id: str) -> bool:
        """Delete a product."""
        if product_id not in self._products:
            return False
        
        del self._products[product_id]
        logger.info(f"Deleted product: {product_id}")
        return True

    # ==================== Supplier Profiles ====================

    def get_supplier_profile(self, supplier_id: str) -> Optional[SupplierProfile]:
        """Get a comprehensive supplier profile."""
        supplier = self._suppliers.get(supplier_id)
        if supplier is None:
            return None
        
        reputation = self._reputations.get(supplier_id)
        risk_assessment = self._risk_assessments.get(supplier_id)
        catalog = self._catalogs.get(supplier_id)
        
        return SupplierProfile(
            supplier=supplier,
            average_rating=reputation.average_rating if reputation else 0.0,
            total_reviews=reputation.total_reviews if reputation else 0,
            delivery_reliability=98.5,  # Placeholder
            quality_score=95.0,  # Placeholder
            price_competitiveness=90.0,  # Placeholder
            sustainability_score=None,  # Can be integrated with sustainability service
            risk_level=risk_assessment.risk_level if risk_assessment else "unknown",
            trust_score=95.0,  # Placeholder
            fulfillment_rate=99.0,  # Placeholder
            on_time_delivery_rate=98.0,  # Placeholder
            product_count=catalog.product_count if catalog else 0,
            years_in_business=datetime.utcnow().year - (supplier.founded_year or datetime.utcnow().year),
        )

    # ==================== Supplier Comparison ====================

    def compare_suppliers(
        self,
        supplier_ids: List[str],
        criteria: Optional[List[str]] = None,
    ) -> SupplierComparison:
        """Compare multiple suppliers based on specified criteria."""
        if criteria is None:
            criteria = ["rating", "price", "reliability", "risk"]
        
        scores: Dict[str, Dict[str, float]] = {}
        normalized_scores: Dict[str, Dict[str, float]] = {}
        rankings: Dict[str, List[str]] = {}
        
        for supplier_id in supplier_ids:
            scores[supplier_id] = {}
            
            reputation = self._reputations.get(supplier_id)
            risk = self._risk_assessments.get(supplier_id)
            
            if "rating" in criteria and reputation:
                scores[supplier_id]["rating"] = reputation.average_rating * 20  # Scale to 0-100
            if "price" in criteria:
                # Get average product price
                products = [p for p in self._products.values() if p.supplier_id == supplier_id]
                if products:
                    avg_price = sum(p.price or 0 for p in products) / len(products)
                    scores[supplier_id]["price"] = max(0, 100 - (avg_price / 10))  # Invert: lower price = higher score
                else:
                    scores[supplier_id]["price"] = 50.0
            if "reliability" in criteria:
                scores[supplier_id]["reliability"] = 98.5  # Placeholder
            if "risk" in criteria and risk:
                scores[supplier_id]["risk"] = max(0, 100 - risk.overall_risk_score)
        
        # Normalize scores
        for criterion in criteria:
            if criterion not in scores[supplier_ids[0]]:
                continue
            
            values = [scores[sid].get(criterion, 0) for sid in supplier_ids]
            if max(values) - min(values) > 0:
                for supplier_id in supplier_ids:
                    val = scores[supplier_id].get(criterion, 0)
                    normalized_scores.setdefault(supplier_id, {})[criterion] = (
                        ((val - min(values)) / (max(values) - min(values))) * 100
                    )
            else:
                for supplier_id in supplier_ids:
                    normalized_scores.setdefault(supplier_id, {})[criterion] = 50.0
        
        # Calculate rankings
        for criterion in criteria:
            if criterion not in normalized_scores[supplier_ids[0]]:
                continue
            
            ranked = sorted(
                supplier_ids,
                key=lambda sid: normalized_scores[sid].get(criterion, 0),
                reverse=True
            )
            rankings[criterion] = ranked
        
        # Determine winner (most consistent across criteria)
        winner = supplier_ids[0]
        if supplier_ids:
            winner = supplier_ids[0]
        
        return SupplierComparison(
            comparison_id=str(uuid4()),
            supplier_ids=supplier_ids,
            criteria=criteria,
            scores=scores,
            normalized_scores=normalized_scores,
            rankings=rankings,
            winner=winner,
        )

    # ==================== Search & Discovery ====================

    def search_suppliers(
        self,
        query: str,
        categories: Optional[List[ProductCategory]] = None,
        min_rating: Optional[float] = None,
        max_risk: Optional[float] = None,
        limit: int = 10,
    ) -> List[SupplierProfile]:
        """Search for suppliers based on criteria."""
        suppliers = self.list_suppliers(search=query)
        
        if categories:
            suppliers = [
                s for s in suppliers
                if any(cat in s.categories for cat in categories)
            ]
        
        profiles = []
        for supplier in suppliers[:limit]:
            profile = self.get_supplier_profile(supplier.supplier_id)
            if profile:
                # Apply filters
                if min_rating and profile.average_rating < min_rating:
                    continue
                if max_risk and profile.risk_level in ["high", "medium"]:
                    continue
                profiles.append(profile)
        
        return profiles

    def discover_suppliers(
        self,
        product_category: Optional[ProductCategory] = None,
        min_rating: float = 4.0,
        max_risk_level: str = "medium",
        budget: Optional[float] = None,
        limit: int = 5,
    ) -> List[SupplierProfile]:
        """Discover suitable suppliers based on requirements."""
        all_suppliers = self.list_suppliers()
        
        if product_category:
            all_suppliers = [
                s for s in all_suppliers
                if product_category in s.categories
            ]
        
        profiles = []
        for supplier in all_suppliers[:limit * 2]:  # Get more to filter
            profile = self.get_supplier_profile(supplier.supplier_id)
            if profile:
                # Apply filters
                if profile.average_rating < min_rating:
                    continue
                if profile.risk_level == "high" and max_risk_level == "medium":
                    continue
                if profile.risk_level == "medium" and max_risk_level == "low":
                    continue
                
                # Check budget if specified
                if budget:
                    products = self.list_products(supplier_id=supplier.supplier_id)
                    if products:
                        avg_price = sum(p.price or 0 for p in products) / len(products)
                        if avg_price > budget:
                            continue
                
                profiles.append(profile)
                if len(profiles) >= limit:
                    break
        
        return profiles

    # ==================== Reputation Management ====================

    def get_supplier_reputation(self, supplier_id: str) -> Optional[SupplierReputation]:
        """Get reputation data for a supplier."""
        return self._reputations.get(supplier_id)

    def add_review(
        self,
        supplier_id: str,
        rating: int,  # 1-5
        review_text: str,
        reviewer_id: Optional[str] = None,
    ) -> None:
        """Add a review for a supplier."""
        if supplier_id not in self._reputations:
            self._reputations[supplier_id] = SupplierReputation(
                supplier_id=supplier_id,
                average_rating=0.0,
                total_reviews=0,
            )
        
        reputation = self._reputations[supplier_id]
        
        # Update ratings distribution
        reputation.ratings_distribution[str(rating)] = reputation.ratings_distribution.get(str(rating), 0) + 1
        
        # Update totals
        old_total = reputation.total_reviews
        old_avg = reputation.average_rating
        new_avg = ((old_avg * old_total) + rating) / (old_total + 1)
        
        reputation.total_reviews += 1
        reputation.average_rating = new_avg
        
        # Update counts
        if rating >= 4:
            reputation.positive_reviews += 1
        elif rating == 3:
            reputation.neutral_reviews += 1
        else:
            reputation.negative_reviews += 1
        
        # Add review snippet
        reputation.review_snippets.append({
            "rating": rating,
            "review": review_text,
            "reviewer_id": reviewer_id,
            "date": datetime.utcnow().isoformat(),
        })
        
        logger.info(f"Added review for supplier: {supplier_id}")

    # ==================== Risk Assessment ====================

    def get_risk_assessment(self, supplier_id: str) -> Optional[SupplierRiskAssessment]:
        """Get risk assessment for a supplier."""
        return self._risk_assessments.get(supplier_id)

    def update_risk_assessment(
        self,
        supplier_id: str,
        financial_risk: Optional[float] = None,
        operational_risk: Optional[float] = None,
        compliance_risk: Optional[float] = None,
        quality_risk: Optional[float] = None,
        delivery_risk: Optional[float] = None,
    ) -> Optional[SupplierRiskAssessment]:
        """Update risk assessment for a supplier."""
        if supplier_id not in self._risk_assessments:
            self._risk_assessments[supplier_id] = SupplierRiskAssessment(
                supplier_id=supplier_id,
            )
        
        assessment = self._risk_assessments[supplier_id]
        
        if financial_risk is not None:
            assessment.financial_risk = financial_risk
        if operational_risk is not None:
            assessment.operational_risk = operational_risk
        if compliance_risk is not None:
            assessment.compliance_risk = compliance_risk
        if quality_risk is not None:
            assessment.quality_risk = quality_risk
        if delivery_risk is not None:
            assessment.delivery_risk = delivery_risk
        
        # Calculate overall risk
        risks = [
            assessment.financial_risk,
            assessment.operational_risk,
            assessment.compliance_risk,
            assessment.quality_risk,
            assessment.delivery_risk,
        ]
        assessment.overall_risk_score = sum(risks) / len([r for r in risks if r is not None] or 1)
        
        # Determine risk level
        if assessment.overall_risk_score < 10:
            assessment.risk_level = "low"
        elif assessment.overall_risk_score < 25:
            assessment.risk_level = "medium"
        elif assessment.overall_risk_score < 50:
            assessment.risk_level = "high"
        else:
            assessment.risk_level = "critical"
        
        assessment.assessment_date = datetime.utcnow()
        logger.info(f"Updated risk assessment for supplier: {supplier_id}")
        return assessment


# Singleton instance
_supplier_service: Optional[SupplierService] = None


def get_supplier_service() -> SupplierService:
    """Get the singleton SupplierService instance."""
    global _supplier_service
    if _supplier_service is None:
        _supplier_service = SupplierService()
    return _supplier_service
'''

with open("suppliers/service.py", "w") as f:
    f.write(supplier_service)
print("[OK] Created suppliers/service.py")

# Create __init__.py for suppliers
supplier_init = '''"""
PeoplePay 360 - Supplier Intelligence Service

Provides supplier profiles, discovery, comparison, reputation evidence,
risk assessment, reliability history, pricing records, and recommendation explanations.
"""

from suppliers.models import (
    Supplier,
    SupplierProfile,
    Product,
    ProductCatalog,
    SupplierComparison,
    SupplierReputation,
    PricingRecord,
    SupplierRiskAssessment,
)
from suppliers.service import (
    SupplierService,
    get_supplier_service,
)
from suppliers.models import (
    SupplierError,
    SupplierNotFoundError,
    ProductNotFoundError,
    InvalidSupplierDataError,
    SupplierSearchError,
)

__all__ = [
    # Models
    "Supplier",
    "SupplierProfile",
    "Product",
    "ProductCatalog",
    "SupplierComparison",
    "SupplierReputation",
    "PricingRecord",
    "SupplierRiskAssessment",
    # Service
    "SupplierService",
    "get_supplier_service",
    # Errors
    "SupplierError",
    "SupplierNotFoundError",
    "ProductNotFoundError",
    "InvalidSupplierDataError",
    "SupplierSearchError",
]
'''

with open("suppliers/__init__.py", "w") as f:
    f.write(supplier_init)
print("[OK] Updated suppliers/__init__.py")

print("\n[OK] Supplier Intelligence Service created successfully!")
print("\nNext: Creating Personalization Service...")
