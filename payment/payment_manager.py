"""Main payment manager for PeoplePay 360.

This module provides the central payment orchestration service with:
- Unified payment API
- Sandbox payment execution
- Webhook processing
- Audit trail
- Approval workflows
- Idempotency support
- Transaction state management
"""

from __future__ import annotations

import threading
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from shared.config import Config, get_config
from shared.logging_wrapper import get_logger

from payment.audit import AuditService
from payment.approval import ApprovalService, ApprovalPolicy
from payment.errors import (
    ApprovalRequiredError,
    CurrencyMismatchError,
    PaymentAlreadyProcessedError,
    PaymentError,
    PaymentFailedError,
    PaymentNotFoundError,
    IdempotencyConflictError,
)
from payment.models import (
    AuditAction,
    Approval,
    ApprovalRequest,
    PaymentAction,
    PaymentMethod,
    PaymentRequest,
    PaymentResponse,
    PaymentStatus,
    CheckoutRequest,
    CheckoutSession,
    WebhookEvent,
    WebhookEventType,
    Currency,
)
from payment.sandbox import SandboxPaymentService
from payment.webhook import WebhookService


logger = get_logger("payment.payment_manager")


# Singleton instance
_payment_manager: PaymentManager | None = None


class PaymentManager:
    """Central payment orchestration manager.
    
    This class provides a unified interface for all payment operations,
    coordinating between sandbox execution, approval workflows, audit trails,
    and webhook processing.
    """
    
    def __init__(
        self,
        config: Config | None = None,
        sandbox_service: SandboxPaymentService | None = None,
        webhook_service: WebhookService | None = None,
        audit_service: AuditService | None = None,
        approval_service: ApprovalService | None = None
    ):
        self.config = config or get_config()
        self._lock = threading.RLock()
        
        # Initialize services
        self.sandbox = sandbox_service or SandboxPaymentService()
        self.webhook = webhook_service or WebhookService()
        self.audit = audit_service or AuditService()
        self.approval = approval_service or ApprovalService()
        
        # Payment storage
        self._payments: dict[str, PaymentResponse] = {}
        self._checkout_sessions: dict[str, CheckoutSession] = {}
        
        # Idempotency tracking
        self._idempotency: dict[str, dict[str, Any]] = {}
        
        # Initialize from config
        self._initialize_from_config()
        
    def _initialize_from_config(self) -> None:
        """Initialize manager from configuration."""
        # Set up webhook from config
        webhook_config = self.config.get("payment.webhook")
        if webhook_config:
            from payment.models import WebhookConfig
            self.webhook.configure(WebhookConfig(**webhook_config))
        
        # Set up approval policies from config
        approval_config = self.config.get("payment.approval")
        if approval_config:
            self._configure_approval_policies(approval_config)
        
        # Register webhook handlers
        self._register_webhook_handlers()
    
    def _configure_approval_policies(self, config: dict[str, Any]) -> None:
        """Configure approval policies from config."""
        default_policy = ApprovalPolicy(
            policy_id="default",
            name="Default Policy",
            require_approval=config.get("require_approval", True),
            auto_approve_limit=config.get("auto_approve_limit", 0),
            approvers=config.get("approvers", []),
            requires_reason=config.get("requires_reason", False),
            approval_expiry_hours=config.get("approval_expiry_hours", 24)
        )
        self.approval.set_policy(default_policy)
    
    def _register_webhook_handlers(self) -> None:
        """Register webhook event handlers."""
        # Handle payment status updates
        self.webhook.register_handler(
            WebhookEventType.PAYMENT_AUTHORIZED,
            self._handle_payment_authorized
        )
        self.webhook.register_handler(
            WebhookEventType.PAYMENT_CAPTURED,
            self._handle_payment_captured
        )
        self.webhook.register_handler(
            WebhookEventType.PAYMENT_FAILED,
            self._handle_payment_failed
        )
        self.webhook.register_handler(
            WebhookEventType.PAYMENT_REFUNDED,
            self._handle_payment_refunded
        )
    
    def _handle_payment_authorized(self, event: WebhookEvent) -> None:
        """Handle payment authorized webhook."""
        logger.info(f"Payment authorized webhook received: {event.payment_id}")
        # Update payment status
        try:
            payment = self.get_payment(event.payment_id)
            if payment.status != PaymentStatus.AUTHORIZED:
                # This is a new authorization
                response = self.sandbox.authorize_payment(
                    event.payment_id,
                    PaymentRequest(
                        payment_id=event.payment_id,
                        user_id=payment.user_id,
                        organization_id=payment.organization_id,
                        amount=payment.amount,
                        currency=payment.currency,
                        method=payment.method
                    )
                )
                logger.info(f"Updated payment {event.payment_id} to AUTHORIZED")
        except PaymentNotFoundError:
            logger.warning(f"Payment not found for webhook: {event.payment_id}")
    
    def _handle_payment_captured(self, event: WebhookEvent) -> None:
        """Handle payment captured webhook."""
        logger.info(f"Payment captured webhook received: {event.payment_id}")
    
    def _handle_payment_failed(self, event: WebhookEvent) -> None:
        """Handle payment failed webhook."""
        logger.warning(f"Payment failed webhook received: {event.payment_id}")
    
    def _handle_payment_refunded(self, event: WebhookEvent) -> None:
        """Handle payment refunded webhook."""
        logger.info(f"Payment refunded webhook received: {event.payment_id}")
    
    def _generate_id(self, prefix: str = "pay") -> str:
        """Generate a unique payment identifier."""
        return f"{prefix}-{uuid.uuid4().hex[:12]}"
    
    def _check_idempotency(self, key: str, request_data: dict[str, Any]) -> bool:
        """Check idempotency key."""
        with self._lock:
            if key in self._idempotency:
                record = self._idempotency[key]
                current_hash = self._hash_request(request_data)
                
                if current_hash == record["request_hash"]:
                    return True
                else:
                    raise IdempotencyConflictError(key, "Idempotency key reused with different request")
            
            # Store new key
            request_hash = self._hash_request(request_data)
            self._idempotency[key] = {
                "request_hash": request_hash,
                "response": None,
                "created_at": datetime.now(timezone.utc)
            }
            return False
    
    def _hash_request(self, data: dict[str, Any]) -> str:
        """Hash request data for idempotency."""
        import hashlib
        import json
        sorted_data = dict(sorted(data.items()))
        data_str = json.dumps(sorted_data, sort_keys=True, default=str).encode()
        return hashlib.sha256(data_str).hexdigest()
    
    def create_payment(self, request: PaymentRequest) -> PaymentResponse:
        """Create a new payment.
        
        This is the main entry point for payment creation. It handles:
        - Validation
        - Idempotency
        - Approval requirements
        - Sandbox execution
        - Audit trail
        """
        # Check idempotency
        idempotency_key = request.idempotency_key or self._generate_id("idemp")
        request_data = request.model_dump(exclude={"idempotency_key"})
        is_idempotent = self._check_idempotency(idempotency_key, request_data)
        
        if is_idempotent:
            cached = self._idempotency[idempotency_key]["response"]
            response_dict = dict(cached)
            response_dict["idempotent"] = True
            return PaymentResponse(**response_dict)
        
        # Generate payment ID if not provided
        payment_id = request.payment_id or self._generate_id()
        
        # Set default values
        if not request.currency:
            request.currency = Currency.USD
        if not request.method:
            request.method = PaymentMethod.SANDBOX
        
        # Check if approval is required
        if request.requires_approval and not request.approved_by:
            # Create approval request
            approval_request = ApprovalRequest(
                payment_id=payment_id,
                order_id=request.order_id,
                requester_id=request.user_id,
                organization_id=request.organization_id,
                amount=request.amount,
                currency=request.currency,
                metadata=request.metadata
            )
            
            approval = self.approval.request_approval(approval_request)
            
            # Create payment in pending state
            now = datetime.now(timezone.utc)
            response = PaymentResponse(
                payment_id=payment_id,
                order_id=request.order_id,
                transaction_id=request.transaction_id,
                amount=request.amount,
                currency=request.currency,
                method=request.method,
                status=PaymentStatus.PENDING,
                action=PaymentAction.AUTHORIZE,
                processed_at=now,
                user_id=request.user_id,
                organization_id=request.organization_id,
                sandbox=True,
                money_moved=False,
                idempotent=False,
                requires_approval=True,
                approved_by=None,
                approved_at=None,
                approval_required=True,
                reference=None,
                authorization_code=None,
                capture_reference=None,
                metadata=request.metadata or {},
                error_message=None,
                state_transition=False
            )
            
            # Record in audit trail
            self.audit.record_payment_created(response, request)
            self.audit.record_approval_requested(
                payment_id=payment_id,
                order_id=request.order_id,
                user_id=request.user_id,
                organization_id=request.organization_id,
                amount=request.amount,
                currency=request.currency.value,
                reason="Payment requires approval"
            )
        else:
            # Process payment directly (approval already granted or not required)
            sandbox_request = PaymentRequest(
                payment_id=payment_id,
                order_id=request.order_id,
                transaction_id=request.transaction_id,
                amount=request.amount,
                currency=request.currency,
                method=request.method,
                user_id=request.user_id,
                organization_id=request.organization_id,
                requires_approval=False,  # Already approved or not required
                approved_by=request.approved_by,
                approval_token=request.approval_token,
                metadata=request.metadata or {}
            )
            
            response = self.sandbox.create_payment(sandbox_request)
            
            # Record in audit trail
            self.audit.record_payment_created(response, request)
            
            if response.requires_approval and response.approval_required:
                self.audit.record_approval_requested(
                    payment_id=payment_id,
                    order_id=request.order_id,
                    user_id=request.user_id,
                    organization_id=request.organization_id,
                    amount=request.amount,
                    currency=request.currency.value
                )
    
        # Store payment
        with self._lock:
            self._payments[payment_id] = response
            if idempotency_key:
                self._idempotency[idempotency_key]["response"] = response.model_dump()
        
        return response
    
    def authorize_payment(self, payment_id: str, request: PaymentRequest) -> PaymentResponse:
        """Authorize a payment.
        
        This transitions a pending payment to authorized status.
        """
        # Check if approval is required
        if request.requires_approval and not request.approved_by:
            raise ApprovalRequiredError("Human approval required before payment authorization")
        
        # Check if we need to validate approval token
        if request.requires_approval:
            self.approval.validate_token(payment_id, request.approval_token or "")
        
        # Authorize through sandbox
        response = self.sandbox.authorize_payment(payment_id, request)
        
        # Record in audit trail
        self.audit.record_payment_authorized(
            response,
            authorized_by=request.approved_by,
            correlation_id=request.metadata.get("correlation_id") if request.metadata else None
        )
        
        return response
    
    def capture_payment(
        self, 
        payment_id: str, 
        amount: int | None = None,
        idempotency_key: str | None = None
    ) -> PaymentResponse:
        """Capture a previously authorized payment."""
        # Check idempotency
        request_data = {"payment_id": payment_id, "amount": amount or "full"}
        if idempotency_key:
            is_idempotent = self._check_idempotency(idempotency_key, request_data)
            if is_idempotent:
                cached = self._idempotency[idempotency_key]["response"]
                response_dict = dict(cached)
                response_dict["idempotent"] = True
                return PaymentResponse(**response_dict)
        
        # Capture through sandbox
        response = self.sandbox.capture_payment(payment_id, amount)
        
        # Record in audit trail
        self.audit.record_payment_captured(
            response,
            captured_amount=amount,
            correlation_id=None
        )
        
        # Store in idempotency cache
        if idempotency_key:
            with self._lock:
                self._idempotency[idempotency_key]["response"] = response.model_dump()
        
        return response
    
    def refund_payment(
        self,
        payment_id: str,
        amount: int | None = None,
        reason: str | None = None,
        idempotency_key: str | None = None
    ) -> PaymentResponse:
        """Refund a previously captured payment."""
        # Check idempotency
        request_data = {"payment_id": payment_id, "amount": amount or "full", "reason": reason}
        if idempotency_key:
            is_idempotent = self._check_idempotency(idempotency_key, request_data)
            if is_idempotent:
                cached = self._idempotency[idempotency_key]["response"]
                response_dict = dict(cached)
                response_dict["idempotent"] = True
                return PaymentResponse(**response_dict)
        
        # Refund through sandbox
        response = self.sandbox.refund_payment(payment_id, amount, reason)
        
        # Record in audit trail
        self.audit.record_payment_refunded(
            response,
            refund_amount=amount or response.amount,
            reason=reason
        )
        
        # Store in idempotency cache
        if idempotency_key:
            with self._lock:
                self._idempotency[idempotency_key]["response"] = response.model_dump()
        
        return response
    
    def cancel_payment(self, payment_id: str, reason: str | None = None) -> PaymentResponse:
        """Cancel a payment."""
        # Cancel through sandbox
        response = self.sandbox.cancel_payment(payment_id, reason)
        
        # Record in audit trail
        self.audit.record_payment_failed(
            payment_id=payment_id,
            order_id=response.order_id,
            user_id=response.user_id,
            organization_id=response.organization_id,
            error_message=reason or "Payment cancelled"
        )
        
        return response
    
    def get_payment(self, payment_id: str) -> PaymentResponse:
        """Get payment details."""
        with self._lock:
            if payment_id not in self._payments:
                # Try sandbox storage
                return self.sandbox.get_payment_status(payment_id)
            return self._payments[payment_id]
    
    def get_payment_state(self, payment_id: str) -> PaymentResponse:
        """Get the current state of a payment (alias for get_payment)."""
        return self.get_payment(payment_id)
    
    def list_payments(
        self,
        user_id: str | None = None,
        organization_id: str | None = None,
        status: PaymentStatus | None = None,
        limit: int = 100,
        offset: int = 0
    ) -> list[PaymentResponse]:
        """List payments with optional filtering."""
        # Get from sandbox storage
        sandbox_payments = self.sandbox.list_payments(
            user_id=user_id,
            organization_id=organization_id,
            status=status,
            limit=limit,
            offset=offset
        )
        
        # Also include manager's payments
        with self._lock:
            if user_id:
                manager_payments = [
                    p for p in self._payments.values()
                    if p.user_id == user_id
                ]
            elif organization_id:
                manager_payments = [
                    p for p in self._payments.values()
                    if p.organization_id == organization_id
                ]
            else:
                manager_payments = list(self._payments.values())
        
        # Combine and deduplicate
        all_payments = {}
        for payment in sandbox_payments + manager_payments:
            all_payments[payment.payment_id] = payment
        
        result = list(all_payments.values())
        
        # Filter by status if specified
        if status:
            result = [p for p in result if p.status == status]
        
        # Sort by processed_at descending
        result.sort(key=lambda p: p.processed_at, reverse=True)
        
        return result[offset:offset + limit]
    
    def create_checkout_session(self, request: CheckoutRequest) -> CheckoutSession:
        """Create a new checkout session."""
        session_id = f"checkout-{uuid.uuid4().hex[:12]}"
        
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(hours=1)  # 1 hour expiration
        
        session = CheckoutSession(
            session_id=session_id,
            order_id=request.order_id,
            user_id=request.user_id,
            organization_id=request.organization_id,
            status="draft",
            created_at=now,
            updated_at=now,
            expires_at=expires_at,
            amount=request.amount or 0,
            currency=request.currency or Currency.USD,
            method=request.method or PaymentMethod.SANDBOX,
            requires_approval=request.require_approval,
            approved_by=None,
            approved_at=None,
            approval_token=None,
            idempotency_key=request.idempotency_key,
            callback_url=request.callback_url,
            success_url=request.success_url,
            cancel_url=request.cancel_url,
            metadata=request.metadata or {},
            payment_id=None,
            error_message=None
        )
        
        with self._lock:
            self._checkout_sessions[session_id] = session
        
        return session
    
    def get_checkout_session(self, session_id: str) -> CheckoutSession:
        """Get checkout session details."""
        with self._lock:
            if session_id not in self._checkout_sessions:
                raise PaymentNotFoundError(session_id)
            return self._checkout_sessions[session_id]
    
    def complete_checkout(self, session_id: str) -> PaymentResponse:
        """Complete a checkout session and create a payment."""
        session = self.get_checkout_session(session_id)
        
        if session.error_message:
            raise PaymentFailedError(session.error_message)
        
        # Create payment request from session
        payment_request = PaymentRequest(
            payment_id=session.payment_id,
            order_id=session.order_id,
            transaction_id=None,
            amount=session.amount,
            currency=session.currency,
            method=session.method,
            user_id=session.user_id,
            organization_id=session.organization_id,
            requires_approval=session.requires_approval,
            approved_by=session.approved_by,
            approval_token=session.approval_token,
            idempotency_key=session.idempotency_key,
            metadata=session.metadata
        )
        
        # Create payment
        response = self.create_payment(payment_request)
        
        # Update session
        session.status = "completed"
        session.payment_id = response.payment_id
        session.updated_at = datetime.now(timezone.utc)
        
        with self._lock:
            self._checkout_sessions[session_id] = session
        
        return response
    
    def process_webhook(self, payload: dict[str, Any], signature: str | None = None) -> WebhookEvent:
        """Process an incoming webhook event."""
        return self.webhook.process_payload(payload, signature)
    
    def create_signed_webhook(
        self,
        event_type: WebhookEventType,
        payment_id: str,
        data: dict[str, Any],
        secret: str
    ) -> WebhookEvent:
        """Create a signed webhook event for testing."""
        return self.webhook.create_signed_event(
            event_type=event_type,
            payment_id=payment_id,
            data=data,
            secret=secret
        )
    
    def get_audit_trail(self, payment_id: str | None = None) -> list[dict[str, Any]]:
        """Get audit trail for a payment or all payments."""
        if payment_id:
            records = self.audit.get_payment_audit_trail(payment_id)
        else:
            records = self.audit.get_records()
        
        return [record.model_dump() for record in records]
    
    def verify_audit_integrity(self) -> dict[str, Any]:
        """Verify the integrity of the audit trail."""
        return self.audit.verify_integrity()
    
    def is_approval_required(self, payment_id: str) -> bool:
        """Check if approval is required for a payment."""
        return self.approval.is_approval_required(payment_id)
    
    def request_approval(
        self,
        payment_id: str,
        requester_id: str,
        amount: int,
        currency: Currency,
        reason: str | None = None
    ) -> Approval:
        """Request approval for a payment."""
        approval_request = ApprovalRequest(
            payment_id=payment_id,
            requester_id=requester_id,
            amount=amount,
            currency=currency,
            reason=reason
        )
        return self.approval.request_approval(approval_request)
    
    def approve_payment(
        self,
        payment_id: str,
        approver_id: str,
        notes: str | None = None
    ) -> Approval:
        """Approve a payment."""
        # Get the approval from the payment
        approval = self.approval.get_approval_for_payment(payment_id)
        if approval is None:
            from payment.errors import ApprovalNotFoundError
            raise ApprovalNotFoundError(payment_id)
        return self.approval.approve(approval.approval_id, approver_id, notes)
    
    def reject_payment(
        self,
        payment_id: str,
        approver_id: str,
        reason: str,
        notes: str | None = None
    ) -> Approval:
        """Reject a payment approval request."""
        # Get the approval from the payment
        approval = self.approval.get_approval_for_payment(payment_id)
        if approval is None:
            from payment.errors import ApprovalNotFoundError
            raise ApprovalNotFoundError(payment_id)
        return self.approval.reject(approval.approval_id, approver_id, reason, notes)
    
    def reset(self) -> None:
        """Reset the payment manager (for testing)."""
        with self._lock:
            self._payments.clear()
            self._checkout_sessions.clear()
            self._idempotency.clear()
            self.sandbox.reset()
            self.webhook.reset()
            self.audit.reset()
            self.approval.reset()


# =============================================================================
# SINGLETON MANAGEMENT
# =============================================================================


def get_payment_manager() -> PaymentManager:
    """Get the singleton PaymentManager instance."""
    global _payment_manager
    if _payment_manager is None:
        _payment_manager = PaymentManager()
    return _payment_manager


def reset_payment_manager() -> None:
    """Reset the singleton PaymentManager instance (for testing)."""
    global _payment_manager
    if _payment_manager is not None:
        _payment_manager.reset()
        _payment_manager = None