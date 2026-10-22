"""
Supplier Intelligence Service - Main Service
"""

import logging
from typing import Optional, List, Dict, Any
from uuid import uuid4
from datetime import datetime

from suppliers.models import (
    Supplier,
    Product,
    SupplierStatus,
    SupplierTier,
    ProductCategory,
    SupplierError,
    SupplierNotFoundError,
    ProductNotFoundError,
    InvalidSupplierDataError,
)

logger = logging.getLogger(__name__)


class SupplierService:
    def __init__(self):
        self._suppliers: Dict[str, Supplier] = {}
        self._products: Dict[str, Product] = {}
        self._initialize_sample_data()
        logger.info("SupplierService initialized")

    def _initialize_sample_data(self):
        # Sample suppliers
        suppliers = [
            Supplier(
                supplier_id="supplier_001",
                name="OfficePro Supplies",
                description="Leading office supplies manufacturer",
                status=SupplierStatus.ACTIVE,
                tier=SupplierTier.PLATINUM,
                categories=[ProductCategory.OFFICE_SUPPLIES, ProductCategory.FURNITURE],
            ),
            Supplier(
                supplier_id="supplier_002",
                name="TechGadgets Inc",
                description="Technology hardware and accessories",
                status=SupplierStatus.ACTIVE,
                tier=SupplierTier.GOLD,
                categories=[ProductCategory.ELECTRONICS],
            ),
            Supplier(
                supplier_id="supplier_003",
                name="EcoFurniture Co",
                description="Sustainable furniture solutions",
                status=SupplierStatus.ACTIVE,
                tier=SupplierTier.SILVER,
                categories=[ProductCategory.FURNITURE],
            ),
        ]
        for s in suppliers:
            self._suppliers[s.supplier_id] = s

        # Sample products
        products = [
            Product(
                product_id="product_001",
                name="Ergonomic Office Chair",
                description="High-quality ergonomic office chair",
                category=ProductCategory.FURNITURE,
                price=299.99,
                supplier_id="supplier_001",
            ),
            Product(
                product_id="product_002",
                name="Wireless Keyboard",
                description="Bluetooth wireless keyboard",
                category=ProductCategory.ELECTRONICS,
                price=49.99,
                supplier_id="supplier_002",
            ),
            Product(
                product_id="product_003",
                name="Bamboo Desk",
                description="Eco-friendly bamboo desk",
                category=ProductCategory.FURNITURE,
                price=399.99,
                supplier_id="supplier_003",
            ),
        ]
        for p in products:
            self._products[p.product_id] = p

    def create_supplier(self, supplier_data: Dict[str, Any]) -> Supplier:
        supplier_id = supplier_data.get("supplier_id", str(uuid4()))
        supplier = Supplier(
            supplier_id=supplier_id,
            name=supplier_data["name"],
            description=supplier_data.get("description"),
            status=supplier_data.get("status", SupplierStatus.ACTIVE),
            tier=supplier_data.get("tier", SupplierTier.STANDARD),
            categories=supplier_data.get("categories", []),
        )
        self._suppliers[supplier.supplier_id] = supplier
        return supplier

    def get_supplier(self, supplier_id: str) -> Optional[Supplier]:
        return self._suppliers.get(supplier_id)

    def list_suppliers(
        self,
        status: Optional[SupplierStatus] = None,
        tier: Optional[SupplierTier] = None,
        category: Optional[ProductCategory] = None,
    ) -> List[Supplier]:
        suppliers = list(self._suppliers.values())
        if status:
            suppliers = [s for s in suppliers if s.status == status]
        if tier:
            suppliers = [s for s in suppliers if s.tier == tier]
        if category:
            suppliers = [s for s in suppliers if category in s.categories]
        return suppliers

    def create_product(self, product_data: Dict[str, Any]) -> Product:
        product_id = product_data.get("product_id", str(uuid4()))
        product = Product(
            product_id=product_id,
            name=product_data["name"],
            description=product_data.get("description", ""),
            category=product_data.get("category", ProductCategory.OTHER),
            price=product_data.get("price"),
            supplier_id=product_data.get("supplier_id"),
        )
        self._products[product.product_id] = product
        return product

    def get_product(self, product_id: str) -> Optional[Product]:
        return self._products.get(product_id)

    def list_products(
        self,
        supplier_id: Optional[str] = None,
        category: Optional[ProductCategory] = None,
    ) -> List[Product]:
        products = list(self._products.values())
        if supplier_id:
            products = [p for p in products if p.supplier_id == supplier_id]
        if category:
            products = [p for p in products if p.category == category]
        return products

    def search_suppliers(
        self,
        query: Optional[str] = None,
        category: Optional[ProductCategory] = None,
    ) -> List[Supplier]:
        suppliers = list(self._suppliers.values())
        if query:
            query_lower = query.lower()
            suppliers = [
                s for s in suppliers
                if query_lower in s.name.lower() or
                (s.description and query_lower in s.description.lower())
            ]
        if category:
            suppliers = [s for s in suppliers if category in s.categories]
        return suppliers


_supplier_service: Optional[SupplierService] = None


def get_supplier_service() -> SupplierService:
    global _supplier_service
    if _supplier_service is None:
        _supplier_service = SupplierService()
    return _supplier_service
