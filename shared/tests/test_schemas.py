"""Tests for shared schemas."""

import pytest
from datetime import datetime, timezone
from pydantic import ValidationError

from shared.schemas import (
    User,
    UserRole,
    UserStatus,
    Organization,
    OrganizationStatus,
    Permission,
    Money,
    Currency,
    AuditEvent,
    AuditAction,
    AuditResource,
    ErrorResponse,
    ErrorCode,
    HealthResponse,
    ServiceStatus,
    ServiceMode,
    PaginatedResponse,
    PageInfo,
    Order,
    OrderStatus,
    Payment,
    PaymentStatus,
    PaymentMethod,
    LineItem,
    ShoppingCart,
    WebhookEvent,
    Notification,
    NotificationType,
    Supplier,
    SupplierStatus,
    Product,
    ProductCategory,
    SustainabilityScore,
)


class TestMoney:
    """Tests for Money schema."""
    
    def test_create_money(self):
        money = Money(amount=1000, currency=Currency.USD)
        assert money.amount == 1000
        assert money.currency == Currency.USD
    
    def test_money_to_dict(self):
        money = Money(amount=1000, currency=Currency.USD)
        data = money.to_dict()
        assert data["amount"] == 1000
        assert data["currency"] == "USD"
    
    def test_money_from_dict(self):
        data = {"amount": 1000, "currency": "EUR"}
        money = Money.from_dict(data)
        assert money.amount == 1000
        assert money.currency == Currency.EUR
    
    def test_money_validation(self):
        with pytest.raises(ValidationError):
            Money(amount=-100, currency=Currency.USD)


class TestUser:
    """Tests for User schema."""
    
    def test_create_user(self):
        user = User(
            user_id="user_123",
            display_name="John Doe",
            email="john@example.com",
            roles=[UserRole.ADMIN],
        )
        assert user.user_id == "user_123"
        assert user.display_name == "John Doe"
        assert user.email == "john@example.com"
        assert user.is_admin
    
    def test_user_email_validation(self):
        user = User(
            user_id="user_123",
            display_name="John Doe",
            email="john@example.com",
        )
        assert user.email == "john@example.com"
    
    def test_user_email_lowercase(self):
        user = User(
            user_id="user_123",
            display_name="John Doe",
            email="JOHN@EXAMPLE.COM",
        )
        assert user.email == "john@example.com"
    
    def test_user_is_active(self):
        user = User(
            user_id="user_123",
            display_name="John Doe",
            status=UserStatus.ACTIVE,
        )
        assert user.is_active
    
    def test_user_is_not_active(self):
        user = User(
            user_id="user_123",
            display_name="John Doe",
            status=UserStatus.SUSPENDED,
        )
        assert not user.is_active


class TestOrganization:
    """Tests for Organization schema."""
    
    def test_create_organization(self):
        org = Organization(
            organization_id="org_123",
            name="Acme Corp",
            description="A test organization",
        )
        assert org.organization_id == "org_123"
        assert org.name == "Acme Corp"
        assert org.is_active


class TestAuditEvent:
    """Tests for AuditEvent schema."""
    
    def test_create_audit_event(self):
        event = AuditEvent(
            event_id="evt_123",
            action=AuditAction.CREATE,
            resource=AuditResource.TRANSACTION,
            resource_id="txn_123",
            actor_id="user_123",
        )
        assert event.event_id == "evt_123"
        assert event.action == AuditAction.CREATE
        assert event.resource == AuditResource.TRANSACTION

    def test_audit_event_for_action(self):
        event = AuditEvent.for_action(
            action=AuditAction.CREATE,
            resource=AuditResource.TRANSACTION,
            resource_id="txn_123",
            actor_id="user_123",
        )
        assert event.event_id.startswith("evt_")
        assert event.action == AuditAction.CREATE


class TestOrder:
    """Tests for Order schema."""
    
    def test_create_order(self):
        cart = ShoppingCart(
            cart_id="cart_123",
            user_id="user_123",
            items=[],
            currency=Currency.USD,
            cart_hash="abc123",
        )
        order = Order(
            order_id="order_123",
            user_id="user_123",
            cart=cart,
            status=OrderStatus.DRAFT,
        )
        assert order.order_id == "order_123"
        assert order.status == OrderStatus.DRAFT


class TestPayment:
    """Tests for Payment schema."""
    
    def test_create_payment(self):
        payment = Payment(
            payment_id="pay_123",
            order_id="order_123",
            user_id="user_123",
            amount=Money(amount=1000, currency=Currency.USD),
            currency=Currency.USD,
            status=PaymentStatus.PENDING,
            method=PaymentMethod.SANDBOX,
        )
        assert payment.payment_id == "pay_123"
        assert payment.status == PaymentStatus.PENDING
        assert payment.sandbox
        assert not payment.money_moved


class TestErrorResponse:
    """Tests for ErrorResponse schema."""
    
    def test_validation_error(self):
        error = ErrorResponse.validation_error("Invalid input", {"field": "name"})
        assert error.error == "validation_error"
        assert error.code == ErrorCode.VALIDATION_ERROR
        assert error.message == "Invalid input"
    
    def test_not_found(self):
        error = ErrorResponse.not_found("User", "user_123")
        assert error.error == "not_found"
        assert error.code == ErrorCode.NOT_FOUND
        assert "User" in error.message
        assert "user_123" in error.message


class TestHealthResponse:
    """Tests for HealthResponse schema."""
    
    def test_healthy(self):
        health = HealthResponse(
            status=ServiceStatus.HEALTHY,
            service="gateway",
            version="1.0.0",
        )
        assert health.status == ServiceStatus.HEALTHY
        assert health.service == "gateway"


class TestPaginatedResponse:
    """Tests for PaginatedResponse schema."""
    
    def test_paginated_response(self):
        items = [{"id": "1"}, {"id": "2"}]
        page_info = PageInfo(
            page=1,
            page_size=20,
            total_items=2,
            total_pages=1,
        )
        response = PaginatedResponse[dict](items=items, page_info=page_info)
        assert len(response.items) == 2
        assert response.page_info.page == 1


class TestLineItem:
    """Tests for LineItem schema."""
    
    def test_create_line_item(self):
        item = LineItem(
            line_id="line_1",
            product_name="Office Chair",
            supplier_name="Acme Corp",
            quantity=5,
            unit_price=Money(amount=10000, currency=Currency.USD),
            total_price=Money(amount=50000, currency=Currency.USD),
        )
        assert item.line_id == "line_1"
        assert item.quantity == 5


class TestWebhookEvent:
    """Tests for WebhookEvent schema."""
    
    def test_create_webhook_event(self):
        event = WebhookEvent(
            event_id="evt_123",
            payment_id="pay_123",
            event_type="payment.authorized",
            data={"status": "authorized"},
        )
        assert event.event_id == "evt_123"
        assert event.event_type == "payment.authorized"


class TestNotification:
    """Tests for Notification schema."""
    
    def test_create_notification(self):
        notification = Notification(
            notification_id="notif_123",
            user_id="user_123",
            notification_type=NotificationType.INFO,
            title="Test Notification",
            message="This is a test notification",
        )
        assert notification.notification_id == "notif_123"
        assert notification.notification_type == NotificationType.INFO
        assert not notification.read


class TestSupplier:
    """Tests for Supplier schema."""
    
    def test_create_supplier(self):
        supplier = Supplier(
            supplier_id="supplier_123",
            name="Acme Corp",
            description="A test supplier",
            reliability_score=85.5,
            quality_score=90.0,
        )
        assert supplier.supplier_id == "supplier_123"
        assert supplier.name == "Acme Corp"
        assert supplier.reliability_score == 85.5


class TestProduct:
    """Tests for Product schema."""
    
    def test_create_product(self):
        product = Product(
            product_id="product_123",
            name="Office Chair",
            description="A comfortable office chair",
            category=ProductCategory.FURNITURE,
            supplier_id="supplier_123",
            supplier_name="Acme Corp",
            price=Money(amount=10000, currency=Currency.USD),
        )
        assert product.product_id == "product_123"
        assert product.name == "Office Chair"
        assert product.category == ProductCategory.FURNITURE


class TestSustainabilityScore:
    """Tests for SustainabilityScore schema."""
    
    def test_create_sustainability_score(self):
        score = SustainabilityScore(
            entity_id="supplier_123",
            entity_type="supplier",
            overall_score=85.5,
            carbon_score=80.0,
            energy_score=90.0,
            carbon_footprint_kg=100.5,
        )
        assert score.overall_score == 85.5
        assert score.carbon_footprint_kg == 100.5
