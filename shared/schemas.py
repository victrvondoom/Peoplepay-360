"""Shared data schemas and contracts for PeoplePay 360.

This module defines the canonical data contracts used across all services.
All schemas should be typed, serializable, and version-aware.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Generic, TypeVar
from pydantic import BaseModel, Field, field_validator


# =============================================================================
# IDENTITY AND ACCESS MANAGEMENT
# =============================================================================

class UserRole(str, Enum):
    """Standard user roles in PeoplePay 360."""
    ADMIN = "admin"
    USER = "user"
    VIEWER = "viewer"
    GUEST = "guest"


class Permission(str, Enum):
    """Fine-grained permissions for resource access."""
    # System-level permissions
    SYSTEM_ADMIN = "system:admin"
    SYSTEM_CONFIG = "system:config"
    SYSTEM_AUDIT = "system:audit"
    
    # Organization-level permissions
    ORG_ADMIN = "org:admin"
    ORG_MANAGE_MEMBERS = "org:manage_members"
    ORG_MANAGE_BUDGETS = "org:manage_budgets"
    ORG_VIEW = "org:view"
    
    # Transaction-level permissions
    TRANSACTION_CREATE = "transaction:create"
    TRANSACTION_READ = "transaction:read"
    TRANSACTION_UPDATE = "transaction:update"
    TRANSACTION_APPROVE = "transaction:approve"
    TRANSACTION_CANCEL = "transaction:cancel"
    
    # Commerce permissions
    COMMERCE_CART = "commerce:cart"
    COMMERCE_CHECKOUT = "commerce:checkout"
    COMMERCE_ORDER = "commerce:order"
    COMMERCE_PAYMENT = "commerce:payment"
    COMMERCE_REFUND = "commerce:refund"
    
    # Evidence and intelligence permissions
    EVIDENCE_READ = "evidence:read"
    EVIDENCE_WRITE = "evidence:write"
    EVIDENCE_ANALYZE = "evidence:analyze"
    
    # Agent and workflow permissions
    AGENT_READ = "agent:read"
    AGENT_EXECUTE = "agent:execute"
    AGENT_APPROVE = "agent:approve"
    WORKFLOW_CREATE = "workflow:create"
    WORKFLOW_MANAGE = "workflow:manage"
    
    # Supplier and product permissions
    SUPPLIER_READ = "supplier:read"
    SUPPLIER_WRITE = "supplier:write"
    PRODUCT_READ = "product:read"
    PRODUCT_WRITE = "product:write"
    
    # Sustainability permissions
    SUSTAINABILITY_READ = "sustainability:read"
    SUSTAINABILITY_ANALYZE = "sustainability:analyze"


class UserStatus(str, Enum):
    """User account status."""
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    PENDING = "pending"


class User(BaseModel):
    """Canonical user representation."""
    user_id: str = Field(..., description="Unique user identifier")
    email: str | None = Field(default=None, description="User email address")
    display_name: str = Field(..., description="Display name")
    roles: list[UserRole] = Field(default_factory=list, description="User roles")
    permissions: list[Permission] = Field(default_factory=list, description="Explicit permissions")
    organization_id: str | None = Field(default=None, description="Primary organization")
    status: UserStatus = Field(default=UserStatus.ACTIVE, description="Account status")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_login_at: datetime | None = Field(default=None)
    
    @field_validator('email')
    @classmethod
    def validate_email(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if '@' not in v or '.' not in v:
            raise ValueError("Invalid email format")
        return v.lower()
    
    @property
    def is_admin(self) -> bool:
        return UserRole.ADMIN in self.roles
    
    @property
    def is_active(self) -> bool:
        return self.status == UserStatus.ACTIVE


class OrganizationStatus(str, Enum):
    """Organization status."""
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"


class Organization(BaseModel):
    """Organization representation."""
    organization_id: str = Field(..., description="Unique organization identifier")
    name: str = Field(..., description="Organization name")
    description: str | None = Field(default=None, description="Description")
    domain: str | None = Field(default=None, description="Primary domain")
    status: OrganizationStatus = Field(default=OrganizationStatus.ACTIVE)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Budget and policy defaults
    default_currency: str = Field(default="USD", description="Default currency")
    default_budget_limit: int | None = Field(default=None, description="Default budget limit in minor units")
    require_approval_for_payments: bool = Field(default=True, description="Require human approval for payments")
    
    @property
    def is_active(self) -> bool:
        return self.status == OrganizationStatus.ACTIVE


class OrganizationMembership(BaseModel):
    """User membership in an organization."""
    membership_id: str = Field(..., description="Unique membership identifier")
    user_id: str = Field(..., description="User identifier")
    organization_id: str = Field(..., description="Organization identifier")
    role: UserRole = Field(default=UserRole.USER, description="Role in organization")
    permissions: list[Permission] = Field(default_factory=list, description="Organization-specific permissions")
    joined_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    left_at: datetime | None = Field(default=None)
    
    @property
    def is_active(self) -> bool:
        return self.left_at is None


# =============================================================================
# COMMON TYPES
# =============================================================================

class Currency(str, Enum):
    """Supported currencies."""
    USD = "USD"
    EUR = "EUR"
    GBP = "GBP"
    INR = "INR"


class Money(BaseModel):
    """Monetary amount with currency."""
    amount: int = Field(..., description="Amount in minor units (cents, pence, etc.)", ge=0)
    currency: Currency = Field(default=Currency.USD, description="Currency code")
    
    def to_dict(self) -> dict[str, Any]:
        return {"amount": self.amount, "currency": self.currency.value}
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Money":
        return cls(amount=data.get("amount", 0), currency=data.get("currency", "USD"))


class Identifier(BaseModel):
    """Generic identifier with type."""
    id: str = Field(..., description="Unique identifier")
    type: str = Field(..., description="Identifier type/namespace")
    
    @classmethod
    def from_string(cls, value: str) -> "Identifier":
        """Parse 'type:id' format."""
        if ':' in value:
            type_, id_ = value.split(':', 1)
            return cls(id=id_, type=type_)
        return cls(id=value, type="default")


# =============================================================================
# AUDIT AND PROVENANCE
# =============================================================================

class AuditAction(str, Enum):
    """Audit event actions."""
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    APPROVE = "approve"
    REJECT = "reject"
    EXECUTE = "execute"
    CANCEL = "cancel"
    AUTHENTICATE = "authenticate"
    AUTHORIZE = "authorize"


class AuditResource(str, Enum):
    """Audit event resource types."""
    USER = "user"
    ORGANIZATION = "organization"
    TRANSACTION = "transaction"
    ORDER = "order"
    PAYMENT = "payment"
    DISPUTE = "dispute"
    EVIDENCE = "evidence"
    DECISION = "decision"
    AGENT = "agent"
    WORKFLOW = "workflow"
    SUPPLIER = "supplier"
    PRODUCT = "product"
    CONFIGURATION = "configuration"


T = TypeVar('T')


class AuditEvent(BaseModel, Generic[T]):
    """Immutable audit trail entry."""
    event_id: str = Field(..., description="Unique event identifier")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    action: AuditAction = Field(..., description="Action performed")
    resource: AuditResource = Field(..., description="Resource type")
    resource_id: str = Field(..., description="Resource identifier")
    actor_id: str | None = Field(default=None, description="Who performed the action")
    actor_type: str = Field(default="user", description="Actor type (user, agent, system)")
    organization_id: str | None = Field(default=None, description="Organization context")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional context")
    ip_address: str | None = Field(default=None, description="Client IP address")
    user_agent: str | None = Field(default=None, description="Client user agent")
    success: bool = Field(default=True, description="Whether the action succeeded")
    error_message: str | None = Field(default=None, description="Error message if failed")
    
    # Provenance tracking
    correlation_id: str | None = Field(default=None, description="Request correlation ID")
    parent_event_id: str | None = Field(default=None, description="Parent event if part of workflow")
    
    @classmethod
    def for_action(
        cls,
        action: AuditAction,
        resource: AuditResource,
        resource_id: str,
        actor_id: str | None = None,
        organization_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        success: bool = True,
        error_message: str | None = None,
        correlation_id: str | None = None,
    ) -> "AuditEvent":
        return cls(
            event_id=f"evt_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}",
            action=action,
            resource=resource,
            resource_id=resource_id,
            actor_id=actor_id,
            organization_id=organization_id,
            metadata=metadata or {},
            success=success,
            error_message=error_message,
            correlation_id=correlation_id,
        )


class ProvenanceRecord(BaseModel):
    """Provenance tracking for evidence and decisions."""
    source_id: str = Field(..., description="Source identifier")
    source_type: str = Field(..., description="Source type")
    source_timestamp: datetime | None = Field(default=None, description="When source was created")
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    version: str | None = Field(default=None, description="Source version")
    checksum: str | None = Field(default=None, description="Content checksum")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Confidence score")


# =============================================================================
# ERROR HANDLING
# =============================================================================

class ErrorCode(str, Enum):
    """Standard error codes."""
    VALIDATION_ERROR = "E001"
    NOT_FOUND = "E002"
    UNAUTHORIZED = "E003"
    FORBIDDEN = "E004"
    CONFLICT = "E005"
    INTERNAL_ERROR = "E500"
    SERVICE_UNAVAILABLE = "E503"
    RATE_LIMITED = "E429"
    INVALID_REQUEST = "E400"


class ErrorResponse(BaseModel):
    """Standard error response schema."""
    error: str = Field(..., description="Error type")
    code: ErrorCode = Field(..., description="Error code")
    message: str = Field(..., description="Human-readable error message")
    details: dict[str, Any] | None = Field(default=None, description="Additional error details")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    request_id: str | None = Field(default=None, description="Request identifier for correlation")
    
    @classmethod
    def validation_error(cls, message: str, details: dict[str, Any] | None = None) -> "ErrorResponse":
        return cls(error="validation_error", code=ErrorCode.VALIDATION_ERROR, message=message, details=details)
    
    @classmethod
    def not_found(cls, resource: str, resource_id: str) -> "ErrorResponse":
        return cls(error="not_found", code=ErrorCode.NOT_FOUND, message=f"{resource} not found: {resource_id}")
    
    @classmethod
    def unauthorized(cls, message: str = "Authentication required") -> "ErrorResponse":
        return cls(error="unauthorized", code=ErrorCode.UNAUTHORIZED, message=message)
    
    @classmethod
    def forbidden(cls, message: str = "Permission denied") -> "ErrorResponse":
        return cls(error="forbidden", code=ErrorCode.FORBIDDEN, message=message)
    
    @classmethod
    def conflict(cls, message: str) -> "ErrorResponse":
        return cls(error="conflict", code=ErrorCode.CONFLICT, message=message)
    
    @classmethod
    def internal_error(cls, message: str = "Internal server error") -> "ErrorResponse":
        return cls(error="internal_error", code=ErrorCode.INTERNAL_ERROR, message=message)


# =============================================================================
# HEALTH AND STATUS
# =============================================================================

class ServiceStatus(str, Enum):
    """Service health status."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    STARTING = "starting"
    NOT_CONFIGURED = "not_configured"
    UNAVAILABLE = "unavailable"


class ServiceMode(str, Enum):
    """Service operating mode."""
    LIVE = "live"
    SANDBOX = "sandbox"
    MOCK = "mock"
    DEMO = "demo"


class HealthResponse(BaseModel):
    """Standard health check response."""
    status: ServiceStatus = Field(default=ServiceStatus.HEALTHY)
    mode: ServiceMode | None = Field(default=None)
    service: str = Field(..., description="Service name")
    version: str = Field(..., description="Service version")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    uptime: float | None = Field(default=None, description="Uptime in seconds")
    dependencies: dict[str, ServiceStatus] = Field(default_factory=dict, description="Dependency status")
    warnings: list[str] = Field(default_factory=list, description="Health warnings")
    details: dict[str, Any] | None = Field(default=None, description="Additional details")


# =============================================================================
# PAGINATION
# =============================================================================

class PageInfo(BaseModel):
    """Pagination metadata."""
    page: int = Field(default=1, ge=1, description="Current page number")
    page_size: int = Field(default=20, ge=1, le=100, description="Items per page")
    total_items: int = Field(default=0, ge=0, description="Total number of items")
    total_pages: int = Field(default=0, ge=0, description="Total number of pages")
    has_next: bool = Field(default=False, description="Whether there are more items")
    has_previous: bool = Field(default=False, description="Whether there are previous items")


class PaginatedResponse(BaseModel, Generic[T]):
    """Paginated response wrapper."""
    items: list[T] = Field(default_factory=list, description="Response items")
    page_info: PageInfo = Field(default_factory=PageInfo)


# =============================================================================
# WORKFLOW AND STATE
# =============================================================================

class WorkflowStatus(str, Enum):
    """Workflow execution status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"


class StateTransition(BaseModel):
    """State transition record."""
    from_state: str = Field(..., description="Previous state")
    to_state: str = Field(..., description="New state")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    actor: str | None = Field(default=None, description="Who triggered the transition")
    reason: str | None = Field(default=None, description="Transition reason")


# =============================================================================
# EXTENSION AND PLUGIN
# =============================================================================

class ExtensionStatus(str, Enum):
    """Extension lifecycle status."""
    DISABLED = "disabled"
    ENABLED = "enabled"
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    ERROR = "error"


class CapabilityType(str, Enum):
    """Extension capability types."""
    DISCOVERY = "discovery"
    ANALYSIS = "analysis"
    VERIFICATION = "verification"
    RECOMMENDATION = "recommendation"
    TRANSACTION = "transaction"
    AFTER_SALES = "after_sales"
    SUSTAINABILITY = "sustainability"


# =============================================================================
# COMMERCE
# =============================================================================

class OrderStatus(str, Enum):
    """Order lifecycle status."""
    DRAFT = "draft"
    REVIEW_REQUIRED = "review_required"
    APPROVED = "approved"
    REJECTED = "rejected"
    ORDER_PLACED = "order_placed"
    FULFILLED = "fulfilled"
    PARTIAL_FULFILLED = "partial_fulfilled"
    CANCELLED = "cancelled"
    FAILED = "failed"
    DISPUTED = "disputed"


class PaymentStatus(str, Enum):
    """Payment lifecycle status."""
    PENDING = "pending"
    AUTHORIZED = "authorized"
    CAPTURED = "captured"
    FAILED = "failed"
    REFUNDED = "refunded"
    PARTIAL_REFUNDED = "partial_refunded"
    CANCELLED = "cancelled"


class PaymentMethod(str, Enum):
    """Payment method types (sandbox only)."""
    SANDBOX = "sandbox"
    # Future: CARD, BANK_TRANSFER, etc.


class LineItem(BaseModel):
    """Order line item."""
    line_id: str = Field(..., description="Unique line identifier")
    product_id: str | None = Field(default=None, description="Product identifier")
    product_name: str = Field(..., description="Product name")
    product_description: str | None = Field(default=None, description="Product description")
    supplier_id: str | None = Field(default=None, description="Supplier identifier")
    supplier_name: str = Field(..., description="Supplier name")
    quantity: int = Field(..., ge=1, description="Quantity")
    unit_price: Money = Field(..., description="Unit price")
    total_price: Money = Field(..., description="Total price (unit * quantity)")
    variant: str | None = Field(default=None, description="Product variant")
    url: str | None = Field(default=None, description="Product URL")


class ShoppingCart(BaseModel):
    """Shopping cart representation."""
    cart_id: str = Field(..., description="Unique cart identifier")
    user_id: str = Field(..., description="Owner user identifier")
    organization_id: str | None = Field(default=None, description="Organization context")
    items: list[LineItem] = Field(default_factory=list, description="Cart items")
    currency: Currency = Field(default=Currency.USD, description="Currency")
    subtotal: Money = Field(default=Money(amount=0, currency=Currency.USD), description="Subtotal")
    shipping: Money = Field(default=Money(amount=0, currency=Currency.USD), description="Shipping cost")
    tax: Money = Field(default=Money(amount=0, currency=Currency.USD), description="Tax amount")
    total: Money = Field(default=Money(amount=0, currency=Currency.USD), description="Total amount")
    cart_hash: str = Field(..., description="Cart content hash for idempotency")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    status: str = Field(default="active", description="Cart status")


class Order(BaseModel):
    """Order representation."""
    order_id: str = Field(..., description="Unique order identifier")
    user_id: str = Field(..., description="Owner user identifier")
    organization_id: str | None = Field(default=None, description="Organization context")
    transaction_id: str | None = Field(default=None, description="Related transaction")
    cart: ShoppingCart = Field(..., description="Order cart")
    status: OrderStatus = Field(default=OrderStatus.DRAFT, description="Order status")
    payment_status: PaymentStatus | None = Field(default=None, description="Payment status")
    payment_method: PaymentMethod | None = Field(default=None, description="Payment method")
    payment_reference: str | None = Field(default=None, description="Payment provider reference")
    shipping_address: dict[str, Any] | None = Field(default=None, description="Shipping address")
    billing_address: dict[str, Any] | None = Field(default=None, description="Billing address")
    notes: str | None = Field(default=None, description="Order notes")
    
    # Approval tracking
    requires_approval: bool = Field(default=True, description="Whether approval is required")
    approved_by: str | None = Field(default=None, description="Approver user identifier")
    approved_at: datetime | None = Field(default=None, description="Approval timestamp")
    approval_notes: str | None = Field(default=None, description="Approval notes")
    
    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Metadata
    source: str = Field(default="SELF_REPORTED", description="Order source")
    evidence_references: list[str] = Field(default_factory=list, description="Related evidence IDs")
    decision_version: str | None = Field(default=None, description="Decision version used")


class Payment(BaseModel):
    """Payment representation."""
    payment_id: str = Field(..., description="Unique payment identifier")
    order_id: str = Field(..., description="Related order identifier")
    transaction_id: str | None = Field(default=None, description="Related transaction")
    user_id: str = Field(..., description="Payer user identifier")
    organization_id: str | None = Field(default=None, description="Organization context")
    amount: Money = Field(..., description="Payment amount")
    currency: Currency = Field(..., description="Currency")
    status: PaymentStatus = Field(default=PaymentStatus.PENDING, description="Payment status")
    method: PaymentMethod = Field(..., description="Payment method")
    reference: str | None = Field(default=None, description="Payment provider reference")
    description: str | None = Field(default=None, description="Payment description")
    
    # Authorization
    authorized_by: str | None = Field(default=None, description="Authorizer user identifier")
    authorized_at: datetime | None = Field(default=None, description="Authorization timestamp")
    
    # Capture
    captured_at: datetime | None = Field(default=None, description="Capture timestamp")
    capture_reference: str | None = Field(default=None, description="Capture reference")
    
    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Metadata
    idempotency_key: str | None = Field(default=None, description="Idempotency key")
    webhook_signature: str | None = Field(default=None, description="Webhook signature for verification")
    webhook_data: dict[str, Any] | None = Field(default=None, description="Raw webhook data")
    
    # Flags
    sandbox: bool = Field(default=True, description="Whether this is a sandbox payment")
    money_moved: bool = Field(default=False, description="Whether actual money was moved")


class WebhookEvent(BaseModel):
    """Webhook event for payment verification."""
    event_id: str = Field(..., description="Unique event identifier")
    payment_id: str = Field(..., description="Related payment identifier")
    event_type: str = Field(..., description="Event type (payment.authorized, payment.captured, etc.)")
    data: dict[str, Any] = Field(default_factory=dict, description="Event data")
    signature: str | None = Field(default=None, description="Event signature for verification")
    verified: bool = Field(default=False, description="Whether signature was verified")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    processed: bool = Field(default=False, description="Whether event was processed")


# =============================================================================
# NOTIFICATIONS
# =============================================================================

class NotificationType(str, Enum):
    """Notification types."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    APPROVAL_REQUEST = "approval_request"
    ORDER_UPDATE = "order_update"
    PAYMENT_UPDATE = "payment_update"
    DISPUTE_CREATED = "dispute_created"
    WORKFLOW_COMPLETED = "workflow_completed"
    WORKFLOW_FAILED = "workflow_failed"


class Notification(BaseModel):
    """Notification representation."""
    notification_id: str = Field(..., description="Unique notification identifier")
    user_id: str = Field(..., description="Recipient user identifier")
    organization_id: str | None = Field(default=None, description="Organization context")
    notification_type: NotificationType = Field(..., description="Notification type")
    title: str = Field(..., description="Notification title")
    message: str = Field(..., description="Notification message")
    data: dict[str, Any] = Field(default_factory=dict, description="Additional data")
    resource_type: str | None = Field(default=None, description="Related resource type")
    resource_id: str | None = Field(default=None, description="Related resource identifier")
    read: bool = Field(default=False, description="Whether notification was read")
    priority: int = Field(default=0, ge=0, le=10, description="Priority level")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime | None = Field(default=None, description="Expiration timestamp")


# =============================================================================
# SUPPLIERS AND PRODUCTS
# =============================================================================

class SupplierStatus(str, Enum):
    """Supplier status."""
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    VERIFIED = "verified"


class Supplier(BaseModel):
    """Supplier representation."""
    supplier_id: str = Field(..., description="Unique supplier identifier")
    name: str = Field(..., description="Supplier name")
    description: str | None = Field(default=None, description="Description")
    website: str | None = Field(default=None, description="Website URL")
    email: str | None = Field(default=None, description="Contact email")
    phone: str | None = Field(default=None, description="Contact phone")
    address: dict[str, Any] | None = Field(default=None, description="Address")
    status: SupplierStatus = Field(default=SupplierStatus.ACTIVE)
    
    # Scoring and metrics
    reliability_score: float | None = Field(default=None, ge=0.0, le=100.0, description="Reliability score")
    quality_score: float | None = Field(default=None, ge=0.0, le=100.0, description="Quality score")
    delivery_score: float | None = Field(default=None, ge=0.0, le=100.0, description="Delivery score")
    sustainability_score: float | None = Field(default=None, ge=0.0, le=100.0, description="Sustainability score")
    overall_score: float | None = Field(default=None, ge=0.0, le=100.0, description="Overall score")
    
    # Evidence
    evidence_references: list[str] = Field(default_factory=list, description="Related evidence IDs")
    certifications: list[str] = Field(default_factory=list, description="Certifications")
    
    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_reviewed_at: datetime | None = Field(default=None)
    
    # Metadata
    categories: list[str] = Field(default_factory=list, description="Product categories")
    regions: list[str] = Field(default_factory=list, description="Service regions")
    payment_terms: dict[str, Any] | None = Field(default=None, description="Payment terms")
    minimum_order_value: Money | None = Field(default=None, description="Minimum order value")


class ProductCategory(str, Enum):
    """Product categories."""
    ELECTRONICS = "electronics"
    FURNITURE = "furniture"
    OFFICE_SUPPLIES = "office_supplies"
    SOFTWARE = "software"
    SERVICES = "services"
    OTHER = "other"


class Product(BaseModel):
    """Product representation."""
    product_id: str = Field(..., description="Unique product identifier")
    name: str = Field(..., description="Product name")
    description: str | None = Field(default=None, description="Description")
    category: ProductCategory = Field(default=ProductCategory.OTHER)
    supplier_id: str = Field(..., description="Supplier identifier")
    supplier_name: str = Field(..., description="Supplier name")
    
    # Pricing
    price: Money = Field(..., description="Product price")
    currency: Currency = Field(default=Currency.USD)
    price_unit: str = Field(default="unit", description="Price unit (unit, kg, hour, etc.)")
    
    # Availability
    in_stock: bool = Field(default=True, description="Whether in stock")
    stock_quantity: int | None = Field(default=None, ge=0, description="Available quantity")
    lead_time_days: int | None = Field(default=None, ge=0, description="Lead time in days")
    
    # Specifications
    specifications: dict[str, Any] = Field(default_factory=dict, description="Product specifications")
    variants: list[dict[str, Any]] = Field(default_factory=list, description="Product variants")
    
    # Media
    images: list[str] = Field(default_factory=list, description="Image URLs")
    
    # Evidence
    evidence_references: list[str] = Field(default_factory=list, description="Related evidence IDs")
    
    # Sustainability
    sustainability_score: float | None = Field(default=None, ge=0.0, le=100.0)
    carbon_footprint: float | None = Field(default=None, ge=0.0, description="Carbon footprint in kg CO2")
    
    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Status
    is_active: bool = Field(default=True, description="Whether product is active")
    is_verified: bool = Field(default=False, description="Whether product is verified")


# =============================================================================
# SUSTAINABILITY
# =============================================================================

class SustainabilityMetric(str, Enum):
    """Sustainability metrics."""
    CARBON_FOOTPRINT = "carbon_footprint"
    ENERGY_USAGE = "energy_usage"
    WATER_USAGE = "water_usage"
    WASTE_GENERATION = "waste_generation"
    RECYCLABLE_CONTENT = "recyclable_content"
    RENEWABLE_ENERGY = "renewable_energy"


class EmissionsScope(str, Enum):
    """Emissions scopes."""
    SCOPE_1 = "scope_1"  # Direct emissions
    SCOPE_2 = "scope_2"  # Indirect emissions from energy
    SCOPE_3 = "scope_3"  # Other indirect emissions


class SustainabilityScore(BaseModel):
    """Sustainability scoring for a supplier or product."""
    entity_id: str = Field(..., description="Entity identifier")
    entity_type: str = Field(..., description="Entity type (supplier, product, order)")
    overall_score: float = Field(..., ge=0.0, le=100.0, description="Overall sustainability score")
    
    # Component scores
    carbon_score: float | None = Field(default=None, ge=0.0, le=100.0)
    energy_score: float | None = Field(default=None, ge=0.0, le=100.0)
    waste_score: float | None = Field(default=None, ge=0.0, le=100.0)
    social_score: float | None = Field(default=None, ge=0.0, le=100.0)
    
    # Metrics
    carbon_footprint_kg: float | None = Field(default=None, ge=0.0)
    energy_usage_kwh: float | None = Field(default=None, ge=0.0)
    waste_generation_kg: float | None = Field(default=None, ge=0.0)
    
    # Emissions by scope
    scope_1_emissions: float | None = Field(default=None, ge=0.0)
    scope_2_emissions: float | None = Field(default=None, ge=0.0)
    scope_3_emissions: float | None = Field(default=None, ge=0.0)
    
    # Evidence
    evidence_references: list[str] = Field(default_factory=list)
    calculation_methodology: str | None = Field(default=None)
    data_sources: list[str] = Field(default_factory=list)
    last_calculated: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Confidence
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    notes: str | None = Field(default=None)
