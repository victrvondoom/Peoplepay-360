"""Payment and commerce data models."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator
from shared.schemas import (
    Currency,
    Money,
    User,
    Order,
    OrderStatus,
    PaymentStatus as SharedPaymentStatus,
    PaymentMethod as SharedPaymentMethod,
)


# =============================================================================
# PAYMENT ENUMS AND CONSTANTS
# =============================================================================

class PaymentStatus(str, Enum):
    """Payment lifecycle status (extended for internal use)."""
    PENDING = "pending"
    AUTHORIZED = "authorized"
    CAPTURED = "captured"
    FAILED = "failed"
    REFUNDED = "refunded"
    PARTIAL_REFUNDED = "partial_refunded"
    CANCELLED = "cancelled"
    REVERSAL_PENDING = "reversal_pending"
    
    @classmethod
    def from_shared(cls, status: SharedPaymentStatus) -> "PaymentStatus":
        return cls(status.value)
    
    def to_shared(self) -> SharedPaymentStatus:
        return SharedPaymentStatus(self.value)


class PaymentMethod(str, Enum):
    """Payment method types."""
    SANDBOX = "sandbox"
    # Future: CARD, BANK_TRANSFER, WALLET, etc.
    
    @classmethod
    def from_shared(cls, method: SharedPaymentMethod) -> "PaymentMethod":
        return cls(method.value)
    
    def to_shared(self) -> SharedPaymentMethod:
        return SharedPaymentMethod(self.value)


class PaymentAction(str, Enum):
    """Payment actions."""
    AUTHORIZE = "authorize"
    CAPTURE = "capture"
    REFUND = "refund"
    CANCEL = "cancel"
    VERIFY = "verify"


class WebhookEventType(str, Enum):
    """Webhook event types."""
    PAYMENT_AUTHORIZED = "payment.authorized"
    PAYMENT_CAPTURED = "payment.captured"
    PAYMENT_FAILED = "payment.failed"
    PAYMENT_REFUNDED = "payment.refunded"
    PAYMENT_CANCELLED = "payment.cancelled"
    DISPUTE_CREATED = "dispute.created"
    DISPUTE_RESOLVED = "dispute.resolved"
    ORDER_PLACED = "order.placed"
    ORDER_FULFILLED = "order.fulfilled"
    ORDER_CANCELLED = "order.cancelled"


# =============================================================================
# PAYMENT MODELS
# =============================================================================

class PaymentRequest(BaseModel):
    """Request to create or process a payment."""
    # Identification
    payment_id: str | None = Field(default=None, description="Payment identifier (generated if None)")
    order_id: str | None = Field(default=None, description="Related order identifier")
    transaction_id: str | None = Field(default=None, description="Related transaction identifier")
    
    # Payment details
    amount: int = Field(..., ge=0, description="Amount in minor units")
    currency: Currency = Field(default=Currency.USD, description="Currency")
    method: PaymentMethod = Field(default=PaymentMethod.SANDBOX, description="Payment method")
    description: str | None = Field(default=None, description="Payment description")
    
    # Context
    user_id: str = Field(..., description="Payer user identifier")
    organization_id: str | None = Field(default=None, description="Organization context")
    
    # Processing
    action: PaymentAction | None = Field(default=None, description="Payment action to perform")
    idempotency_key: str | None = Field(default=None, description="Idempotency key")
    
    # Authorization
    requires_approval: bool = Field(default=True, description="Whether human approval is required")
    approved_by: str | None = Field(default=None, description="Approver user identifier")
    approval_token: str | None = Field(default=None, description="Approval authorization token")
    
    # Metadata
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    callback_url: str | None = Field(default=None, description="Callback URL for status updates")
    
    @field_validator('idempotency_key')
    @classmethod
    def validate_idempotency_key(cls, v: str | None) -> str | None:
        if v is not None and len(v) > 255:
            raise ValueError("Idempotency key must be 255 characters or less")
        return v
    
    @field_validator('metadata')
    @classmethod
    def validate_metadata_size(cls, v: dict[str, Any]) -> dict[str, Any]:
        if len(v) > 50:
            raise ValueError("Metadata cannot have more than 50 fields")
        return v


class PaymentResponse(BaseModel):
    """Response from payment processing."""
    # Identification
    payment_id: str = Field(..., description="Payment identifier")
    order_id: str | None = Field(default=None, description="Related order identifier")
    transaction_id: str | None = Field(default=None, description="Related transaction identifier")
    
    # Status
    status: PaymentStatus = Field(..., description="Current payment status")
    previous_status: PaymentStatus | None = Field(default=None, description="Previous status")
    
    # Payment details
    amount: int = Field(..., ge=0, description="Amount in minor units")
    currency: Currency = Field(..., description="Currency")
    method: PaymentMethod = Field(..., description="Payment method")
    
    # Processing info
    action: PaymentAction | None = Field(default=None, description="Action performed")
    processed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    captured_at: datetime | None = Field(default=None, description="Capture timestamp")
    
    # References
    reference: str | None = Field(default=None, description="Provider reference")
    authorization_code: str | None = Field(default=None, description="Authorization code")
    capture_reference: str | None = Field(default=None, description="Capture reference")
    
    # Context
    user_id: str = Field(..., description="Payer user identifier")
    organization_id: str | None = Field(default=None, description="Organization context")
    
    # Flags
    sandbox: bool = Field(default=True, description="Whether this is a sandbox payment")
    money_moved: bool = Field(default=False, description="Whether actual money was moved")
    idempotent: bool = Field(default=False, description="Whether this was an idempotent replay")
    
    # Approval
    requires_approval: bool = Field(default=True, description="Whether human approval is required")
    approved_by: str | None = Field(default=None, description="Approver user identifier")
    approved_at: datetime | None = Field(default=None, description="Approval timestamp")
    approval_required: bool = Field(default=False, description="Whether approval is still needed")
    
    # Metadata
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    error_message: str | None = Field(default=None, description="Error message if failed")
    
    # State
    state_transition: bool = Field(default=False, description="Whether state changed")


class PaymentState(BaseModel):
    """Complete payment state."""
    payment: PaymentResponse = Field(..., description="Payment response")
    order: Order | None = Field(default=None, description="Related order")
    user: User | None = Field(default=None, description="Payer user")
    audit_trail: list[AuditRecord] = Field(default_factory=list, description="Audit trail")
    approvals: list[Approval] = Field(default_factory=list, description="Approval history")
    webhook_events: list[WebhookEvent] = Field(default_factory=list, description="Webhook events")


# =============================================================================
# CHECKOUT MODELS
# =============================================================================

class CheckoutSession(BaseModel):
    """Checkout session for payment processing."""
    session_id: str = Field(..., description="Unique session identifier")
    order_id: str | None = Field(default=None, description="Related order identifier")
    user_id: str = Field(..., description="User identifier")
    organization_id: str | None = Field(default=None, description="Organization context")
    
    # Session state
    status: str = Field(default="draft", description="Session status")  # draft, ready, processing, completed, cancelled, failed
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime | None = Field(default=None, description="Session expiration")
    
    # Payment details
    amount: int = Field(..., ge=0, description="Amount in minor units")
    currency: Currency = Field(default=Currency.USD, description="Currency")
    method: PaymentMethod = Field(default=PaymentMethod.SANDBOX, description="Payment method")
    
    # Approval
    requires_approval: bool = Field(default=True, description="Whether approval is required")
    approved_by: str | None = Field(default=None, description="Approver user identifier")
    approved_at: datetime | None = Field(default=None, description="Approval timestamp")
    approval_token: str | None = Field(default=None, description="Approval token")
    
    # Context
    idempotency_key: str | None = Field(default=None, description="Idempotency key")
    callback_url: str | None = Field(default=None, description="Callback URL")
    success_url: str | None = Field(default=None, description="Success redirect URL")
    cancel_url: str | None = Field(default=None, description="Cancel redirect URL")
    
    # Metadata
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    
    # State
    payment_id: str | None = Field(default=None, description="Created payment identifier")
    error_message: str | None = Field(default=None, description="Error message if failed")


class CheckoutRequest(BaseModel):
    """Request to create a checkout session."""
    order_id: str = Field(..., description="Order identifier")
    user_id: str = Field(..., description="User identifier")
    organization_id: str | None = Field(default=None, description="Organization context")
    
    # Overrides
    amount: int | None = Field(default=None, ge=0, description="Override amount in minor units")
    currency: Currency | None = Field(default=None, description="Override currency")
    method: PaymentMethod | None = Field(default=None, description="Override payment method")
    
    # Behavior
    require_approval: bool = Field(default=True, description="Require human approval")
    auto_capture: bool = Field(default=False, description="Automatically capture after authorization")
    
    # URLs
    callback_url: str | None = Field(default=None, description="Callback URL")
    success_url: str | None = Field(default=None, description="Success redirect URL")
    cancel_url: str | None = Field(default=None, description="Cancel redirect URL")
    
    # Context
    idempotency_key: str | None = Field(default=None, description="Idempotency key")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


# =============================================================================
# APPROVAL MODELS
# =============================================================================

class ApprovalStatus(str, Enum):
    """Approval status."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class Approval(BaseModel):
    """Approval record for payment authorization."""
    approval_id: str = Field(..., description="Unique approval identifier")
    payment_id: str | None = Field(default=None, description="Related payment identifier")
    order_id: str | None = Field(default=None, description="Related order identifier")
    
    # Approval details
    status: ApprovalStatus = Field(default=ApprovalStatus.PENDING, description="Approval status")
    requester_id: str = Field(..., description="Requester user identifier")
    approver_id: str | None = Field(default=None, description="Approver user identifier")
    
    # Context
    amount: int = Field(..., ge=0, description="Approval amount in minor units")
    currency: Currency = Field(default=Currency.USD, description="Currency")
    reason: str | None = Field(default=None, description="Approval reason")
    notes: str | None = Field(default=None, description="Approval notes")
    
    # Timestamps
    requested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    approved_at: datetime | None = Field(default=None, description="Approval timestamp")
    rejected_at: datetime | None = Field(default=None, description="Rejection timestamp")
    expires_at: datetime | None = Field(default=None, description="Approval expiration")
    
    # Token for authorization
    approval_token: str | None = Field(default=None, description="Approval authorization token")
    token_used: bool = Field(default=False, description="Whether token was used")
    used_at: datetime | None = Field(default=None, description="Token usage timestamp")
    
    # Metadata
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class ApprovalRequest(BaseModel):
    """Request to create an approval."""
    payment_id: str | None = Field(default=None, description="Related payment identifier")
    order_id: str | None = Field(default=None, description="Related order identifier")
    
    # Approval details
    amount: int = Field(..., ge=0, description="Approval amount in minor units")
    currency: Currency = Field(default=Currency.USD, description="Currency")
    
    # Context
    requester_id: str = Field(..., description="Requester user identifier")
    organization_id: str | None = Field(default=None, description="Organization context")
    reason: str | None = Field(default=None, description="Approval reason")
    
    # Behavior
    auto_approve: bool = Field(default=False, description="Automatically approve if within limits")
    
    # Metadata
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


# =============================================================================
# WEBHOOK MODELS
# =============================================================================

class WebhookEvent(BaseModel):
    """Webhook event for payment status updates."""
    event_id: str = Field(..., description="Unique event identifier")
    payment_id: str | None = Field(default=None, description="Related payment identifier")
    order_id: str | None = Field(default=None, description="Related order identifier")
    
    # Event details
    event_type: WebhookEventType = Field(..., description="Event type")
    data: dict[str, Any] = Field(default_factory=dict, description="Event data")
    
    # Processing
    signature: str | None = Field(default=None, description="Event signature for verification")
    verified: bool = Field(default=False, description="Whether signature was verified")
    processed: bool = Field(default=False, description="Whether event was processed")
    processing_attempts: int = Field(default=0, ge=0, description="Number of processing attempts")
    
    # Timestamps
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    processed_at: datetime | None = Field(default=None, description="Processing timestamp")
    
    # Context
    source: str = Field(default="internal", description="Event source")
    correlation_id: str | None = Field(default=None, description="Correlation ID")
    
    # Metadata
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class WebhookConfig(BaseModel):
    """Webhook configuration."""
    url: str = Field(..., description="Webhook URL")
    secret: str | None = Field(default=None, description="Webhook secret for signing")
    events: list[WebhookEventType] = Field(default_factory=list, description="Subscribed events")
    active: bool = Field(default=True, description="Whether webhook is active")
    
    # Retry settings
    max_retries: int = Field(default=3, ge=0, le=10, description="Maximum retry attempts")
    retry_delay: float = Field(default=1.0, ge=0.1, description="Retry delay in seconds")
    
    # Rate limiting
    rate_limit: int | None = Field(default=None, ge=1, description="Events per second limit")
    
    # Metadata
    name: str | None = Field(default=None, description="Webhook name")
    description: str | None = Field(default=None, description="Webhook description")


# =============================================================================
# AUDIT MODELS
# =============================================================================

class AuditAction(str, Enum):
    """Audit action types for payments."""
    PAYMENT_CREATED = "payment_created"
    PAYMENT_AUTHORIZED = "payment_authorized"
    PAYMENT_CAPTURED = "payment_captured"
    PAYMENT_FAILED = "payment_failed"
    PAYMENT_REFUNDED = "payment_refunded"
    PAYMENT_CANCELLED = "payment_cancelled"
    CHECKOUT_CREATED = "checkout_created"
    CHECKOUT_COMPLETED = "checkout_completed"
    APPROVAL_REQUESTED = "approval_requested"
    APPROVAL_GRANTED = "approval_granted"
    APPROVAL_DENIED = "approval_denied"
    WEBHOOK_RECEIVED = "webhook_received"
    WEBHOOK_PROCESSED = "webhook_processed"
    IDENPOTENCY_CHECK = "idempotency_check"


class AuditRecord(BaseModel):
    """Audit trail record for payments."""
    record_id: str = Field(..., description="Unique record identifier")
    payment_id: str | None = Field(default=None, description="Related payment identifier")
    order_id: str | None = Field(default=None, description="Related order identifier")
    
    # Action details
    action: AuditAction = Field(..., description="Action performed")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Context
    user_id: str | None = Field(default=None, description="User identifier")
    organization_id: str | None = Field(default=None, description="Organization context")
    
    # Details
    details: dict[str, Any] = Field(default_factory=dict, description="Action details")
    previous_state: str | None = Field(default=None, description="Previous state")
    new_state: str | None = Field(default=None, description="New state")
    
    # Metadata
    ip_address: str | None = Field(default=None, description="Client IP address")
    user_agent: str | None = Field(default=None, description="Client user agent")
    correlation_id: str | None = Field(default=None, description="Request correlation ID")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    
    # Provenance
    evidence_references: list[str] = Field(default_factory=list, description="Related evidence IDs")


# =============================================================================
# IDEMPOTENCY MODELS
# =============================================================================

class IdempotencyRecord(BaseModel):
    """Idempotency key record."""
    key: str = Field(..., description="Idempotency key")
    operation: str = Field(..., description="Operation type")
    request_hash: str = Field(..., description="Request hash")
    response: dict[str, Any] = Field(..., description="Stored response")
    
    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime | None = Field(default=None, description="Expiration timestamp")
    
    # Metadata
    user_id: str | None = Field(default=None, description="User identifier")
    organization_id: str | None = Field(default=None, description="Organization context")
    usage_count: int = Field(default=0, ge=0, description="Number of times used")


class IdempotencyConfig(BaseModel):
    """Idempotency configuration."""
    enabled: bool = Field(default=True, description="Whether idempotency is enabled")
    ttl_hours: int = Field(default=24, ge=1, description="Idempotency record TTL in hours")
    max_keys_per_user: int | None = Field(default=None, ge=1, description="Maximum keys per user")
    max_total_keys: int | None = Field(default=None, ge=1, description="Maximum total keys")


# =============================================================================
# SANDBOX MODELS
# =============================================================================

class SandboxAccount(BaseModel):
    """Sandbox payment account."""
    account_id: str = Field(..., description="Unique account identifier")
    user_id: str = Field(..., description="Owner user identifier")
    organization_id: str | None = Field(default=None, description="Organization context")
    
    # Account details
    name: str | None = Field(default=None, description="Account name")
    account_type: str = Field(default="sandbox", description="Account type")
    
    # Balance (sandbox only)
    balance_minor: int = Field(default=0, description="Balance in minor units")
    currency: Currency = Field(default=Currency.USD, description="Currency")
    
    # Limits
    daily_limit_minor: int | None = Field(default=None, description="Daily spending limit")
    transaction_limit_minor: int | None = Field(default=None, description="Per-transaction limit")
    
    # Status
    status: str = Field(default="active", description="Account status")  # active, frozen, closed
    
    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Metadata
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class SandboxTransaction(BaseModel):
    """Sandbox transaction record."""
    transaction_id: str = Field(..., description="Unique transaction identifier")
    account_id: str = Field(..., description="Sandbox account identifier")
    
    # Transaction details
    amount_minor: int = Field(..., description="Amount in minor units")
    currency: Currency = Field(default=Currency.USD, description="Currency")
    description: str | None = Field(default=None, description="Transaction description")
    
    # Processing
    status: PaymentStatus = Field(default=PaymentStatus.PENDING, description="Transaction status")
    type: str = Field(..., description="Transaction type")  # debit, credit, reversal
    
    # References
    payment_id: str | None = Field(default=None, description="Related payment identifier")
    order_id: str | None = Field(default=None, description="Related order identifier")
    
    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    processed_at: datetime | None = Field(default=None, description="Processing timestamp")
    
    # Metadata
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")