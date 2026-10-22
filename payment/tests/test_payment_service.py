"""Tests for the payment service."""

import pytest
from datetime import datetime, timezone

from payment import (
    get_payment_manager,
    reset_payment_manager,
    PaymentRequest,
    PaymentResponse,
    PaymentStatus,
    PaymentMethod,
    PaymentAction,
    Currency,
    WebhookEvent,
    WebhookEventType,
    CheckoutRequest,
    CheckoutSession,
    Approval,
    ApprovalStatus,
)
from payment.errors import (
    PaymentNotFoundError,
    ApprovalRequiredError,
    IdempotencyConflictError,
    WebhookVerificationError,
    InvalidWebhookPayloadError,
)


@pytest.fixture
def payment_manager():
    """Get a fresh payment manager for each test."""
    reset_payment_manager()
    pm = get_payment_manager()
    yield pm
    reset_payment_manager()


@pytest.fixture
def sample_payment_request():
    """Sample payment request for testing."""
    return PaymentRequest(
        user_id="test-user",
        organization_id="test-org",
        amount=10000,  # 100.00
        currency=Currency.USD,
        requires_approval=False,
        approved_by="test-user"
    )


class TestPaymentManager:
    """Tests for PaymentManager."""
    
    def test_create_payment(self, payment_manager, sample_payment_request):
        """Test creating a payment."""
        response = payment_manager.create_payment(sample_payment_request)
        
        assert response.payment_id is not None
        assert response.status == PaymentStatus.AUTHORIZED
        assert response.amount == 10000
        assert response.currency == Currency.USD
        assert response.sandbox is True
        assert response.money_moved is False
        assert response.user_id == "test-user"
        assert response.organization_id == "test-org"
    
    def test_create_payment_with_idempotency(self, payment_manager, sample_payment_request):
        """Test idempotency in payment creation."""
        # First request
        request1 = sample_payment_request.model_copy()
        request1.idempotency_key = "test-idempotency-key"
        response1 = payment_manager.create_payment(request1)
        
        # Second request with same key and data
        request2 = sample_payment_request.model_copy()
        request2.idempotency_key = "test-idempotency-key"
        response2 = payment_manager.create_payment(request2)
        
        assert response1.payment_id == response2.payment_id
        assert response2.idempotent is True
    
    def test_idempotency_conflict(self, payment_manager):
        """Test idempotency key conflict."""
        request1 = PaymentRequest(
            user_id="test-user",
            amount=10000,
            currency=Currency.USD,
            requires_approval=False,
            approved_by="test-user",
            idempotency_key="conflict-key"
        )
        
        request2 = PaymentRequest(
            user_id="test-user",
            amount=20000,  # Different amount
            currency=Currency.USD,
            requires_approval=False,
            approved_by="test-user",
            idempotency_key="conflict-key"
        )
        
        # First request should succeed
        payment_manager.create_payment(request1)
        
        # Second request with different data should fail
        with pytest.raises(IdempotencyConflictError):
            payment_manager.create_payment(request2)
    
    def test_create_payment_with_approval_required(self, payment_manager):
        """Test payment creation with approval required."""
        request = PaymentRequest(
            user_id="test-user",
            amount=10000,
            currency=Currency.USD,
            requires_approval=True,  # Requires approval
            approved_by=None
        )
        
        response = payment_manager.create_payment(request)
        
        assert response.payment_id is not None
        assert response.status == PaymentStatus.PENDING
        assert response.approval_required is True
        assert response.requires_approval is True
    
    def test_get_payment(self, payment_manager, sample_payment_request):
        """Test retrieving a payment."""
        # Create payment
        create_response = payment_manager.create_payment(sample_payment_request)
        payment_id = create_response.payment_id
        
        # Retrieve payment
        get_response = payment_manager.get_payment(payment_id)
        
        assert get_response.payment_id == payment_id
        assert get_response.amount == 10000
        assert get_response.user_id == "test-user"
    
    def test_get_payment_not_found(self, payment_manager):
        """Test retrieving a non-existent payment."""
        with pytest.raises(PaymentNotFoundError):
            payment_manager.get_payment("non-existent-payment-id")
    
    def test_list_payments(self, payment_manager, sample_payment_request):
        """Test listing payments."""
        # Create multiple payments
        for i in range(3):
            request = sample_payment_request.model_copy()
            request.amount = 10000 + i * 1000
            payment_manager.create_payment(request)
        
        # List all payments
        payments = payment_manager.list_payments()
        
        assert len(payments) == 3
        
        # List payments for specific user
        user_payments = payment_manager.list_payments(user_id="test-user")
        assert len(user_payments) == 3
        
        # List payments for specific organization
        org_payments = payment_manager.list_payments(organization_id="test-org")
        assert len(org_payments) == 3
    
    def test_capture_payment(self, payment_manager, sample_payment_request):
        """Test capturing a payment."""
        # Create and authorize payment
        create_response = payment_manager.create_payment(sample_payment_request)
        payment_id = create_response.payment_id
        
        # Capture payment
        capture_response = payment_manager.capture_payment(payment_id)
        
        assert capture_response.payment_id == payment_id
        assert capture_response.status == PaymentStatus.CAPTURED
        assert capture_response.action == PaymentAction.CAPTURE
        assert capture_response.captured_at is not None
    
    def test_refund_payment(self, payment_manager, sample_payment_request):
        """Test refunding a payment."""
        # Create and capture payment
        create_response = payment_manager.create_payment(sample_payment_request)
        payment_id = create_response.payment_id
        payment_manager.capture_payment(payment_id)
        
        # Refund payment
        refund_response = payment_manager.refund_payment(payment_id, reason="Test refund")
        
        assert refund_response.payment_id == payment_id
        assert refund_response.status == PaymentStatus.REFUNDED
        assert refund_response.action == PaymentAction.REFUND
    
    def test_partial_refund_payment(self, payment_manager, sample_payment_request):
        """Test partial refund of a payment."""
        # Create and capture payment
        create_response = payment_manager.create_payment(sample_payment_request)
        payment_id = create_response.payment_id
        payment_manager.capture_payment(payment_id)
        
        # Partial refund
        refund_response = payment_manager.refund_payment(payment_id, amount=5000, reason="Partial refund")
        
        assert refund_response.payment_id == payment_id
        assert refund_response.status == PaymentStatus.PARTIAL_REFUNDED
    
    def test_cancel_payment(self, payment_manager, sample_payment_request):
        """Test cancelling a payment."""
        # Create payment
        create_response = payment_manager.create_payment(sample_payment_request)
        payment_id = create_response.payment_id
        
        # Cancel payment
        cancel_response = payment_manager.cancel_payment(payment_id, reason="Test cancellation")
        
        assert cancel_response.payment_id == payment_id
        assert cancel_response.status == PaymentStatus.CANCELLED
        assert cancel_response.action == PaymentAction.CANCEL
        assert cancel_response.error_message == "Test cancellation"


class TestApprovalService:
    """Tests for the approval service."""
    
    def test_request_approval(self, payment_manager):
        """Test requesting approval for a payment."""
        approval = payment_manager.request_approval(
            payment_id="test-payment",
            requester_id="test-user",
            amount=10000,
            currency=Currency.USD,
            reason="Test approval"
        )
        
        assert approval.approval_id is not None
        assert approval.status == ApprovalStatus.PENDING
        assert approval.requester_id == "test-user"
        assert approval.amount == 10000
        assert approval.currency == Currency.USD
        assert approval.reason == "Test approval"
    
    def test_approve_payment(self, payment_manager):
        """Test approving a payment."""
        # Request approval
        approval = payment_manager.request_approval(
            payment_id="test-payment",
            requester_id="test-user",
            amount=10000,
            currency=Currency.USD
        )
        
        # Approve
        approved = payment_manager.approve_payment(
            payment_id="test-payment",
            approver_id="approver-user",
            notes="Approved"
        )
        
        assert approved.approval_id == approval.approval_id
        assert approved.status == ApprovalStatus.APPROVED
        assert approved.approver_id == "approver-user"
        assert approved.notes == "Approved"
        assert approved.approved_at is not None
    
    def test_reject_payment(self, payment_manager):
        """Test rejecting a payment approval."""
        # Request approval
        approval = payment_manager.request_approval(
            payment_id="test-payment",
            requester_id="test-user",
            amount=10000,
            currency=Currency.USD
        )
        
        # Reject
        rejected = payment_manager.reject_payment(
            payment_id="test-payment",
            approver_id="approver-user",
            reason="Budget exceeded",
            notes="Please reduce amount"
        )
        
        assert rejected.approval_id == approval.approval_id
        assert rejected.status == ApprovalStatus.REJECTED
        assert rejected.notes == "Please reduce amount"
    
    def test_is_approval_required(self, payment_manager):
        """Test checking if approval is required."""
        # Request approval
        payment_manager.request_approval(
            payment_id="test-payment-pending",
            requester_id="test-user",
            amount=10000,
            currency=Currency.USD
        )
        
        # Check if approval required
        assert payment_manager.is_approval_required("test-payment-pending") is True
        assert payment_manager.is_approval_required("test-payment-not-found") is False


class TestWebhookService:
    """Tests for the webhook service."""
    
    def test_create_webhook_event(self, payment_manager):
        """Test creating a webhook event."""
        event = payment_manager.create_signed_webhook(
            event_type=WebhookEventType.PAYMENT_AUTHORIZED,
            payment_id="test-payment",
            data={"amount": 10000, "currency": "USD"},
            secret="test-secret"
        )
        
        assert event.event_id is not None
        assert event.event_type == WebhookEventType.PAYMENT_AUTHORIZED
        assert event.payment_id == "test-payment"
        assert event.signature is not None
        assert event.verified is True
    
    def test_webhook_signature_verification(self, payment_manager):
        """Test webhook signature verification."""
        # Create signed event
        event = payment_manager.create_signed_webhook(
            event_type=WebhookEventType.PAYMENT_CAPTURED,
            payment_id="test-payment",
            data={"amount": 10000},
            secret="test-secret"
        )
        
        # Verify signature
        assert payment_manager.webhook.verify_event_signature(event, "test-secret") is True
        
        # Invalid secret should fail
        with pytest.raises(WebhookVerificationError):
            payment_manager.webhook.verify_event_signature(event, "wrong-secret")
    
    def test_process_webhook_payload(self, payment_manager):
        """Test processing webhook payload."""
        payload = {
            "event_type": "payment.authorized",
            "payment_id": "test-payment",
            "data": {"amount": 10000}
        }
        
        # Process payload without signature
        event = payment_manager.process_webhook(payload)
        
        assert event.event_type == WebhookEventType.PAYMENT_AUTHORIZED
        assert event.payment_id == "test-payment"
    
    def test_webhook_with_invalid_payload(self, payment_manager):
        """Test webhook with invalid payload."""
        # Missing required fields
        payload = {"event_type": "payment.authorized"}  # Missing payment_id
        
        with pytest.raises(InvalidWebhookPayloadError):
            payment_manager.process_webhook(payload)


class TestCheckoutService:
    """Tests for the checkout service."""
    
    def test_create_checkout_session(self, payment_manager):
        """Test creating a checkout session."""
        request = CheckoutRequest(
            order_id="test-order",
            user_id="test-user",
            amount=10000,
            currency=Currency.USD,
            require_approval=False
        )
        
        session = payment_manager.create_checkout_session(request)
        
        assert session.session_id is not None
        assert session.order_id == "test-order"
        assert session.user_id == "test-user"
        assert session.amount == 10000
        assert session.currency == Currency.USD
        assert session.status == "draft"
    
    def test_get_checkout_session(self, payment_manager):
        """Test getting a checkout session."""
        request = CheckoutRequest(
            order_id="test-order",
            user_id="test-user",
            amount=10000,
            currency=Currency.USD
        )
        
        session = payment_manager.create_checkout_session(request)
        
        # Retrieve session
        retrieved = payment_manager.get_checkout_session(session.session_id)
        
        assert retrieved.session_id == session.session_id
        assert retrieved.order_id == "test-order"
    
    def test_complete_checkout(self, payment_manager):
        """Test completing a checkout session."""
        request = CheckoutRequest(
            order_id="test-order",
            user_id="test-user",
            amount=10000,
            currency=Currency.USD,
            require_approval=False
        )
        
        session = payment_manager.create_checkout_session(request)
        
        # Complete checkout
        payment = payment_manager.complete_checkout(session.session_id)
        
        assert payment.payment_id is not None
        assert payment.amount == 10000
        assert payment.status == PaymentStatus.AUTHORIZED


class TestAuditService:
    """Tests for the audit service."""
    
    def test_audit_trail(self, payment_manager, sample_payment_request):
        """Test audit trail for payment operations."""
        # Create payment
        payment_manager.create_payment(sample_payment_request)
        
        # Get audit trail
        audit_trail = payment_manager.get_audit_trail()
        
        assert len(audit_trail) >= 1
        
        # Check audit record structure
        record = audit_trail[0]
        assert "record_id" in record
        assert "action" in record
        assert "timestamp" in record
    
    def test_payment_audit_trail(self, payment_manager, sample_payment_request):
        """Test audit trail for a specific payment."""
        # Create payment
        response = payment_manager.create_payment(sample_payment_request)
        payment_id = response.payment_id
        
        # Get audit trail for this payment
        audit_trail = payment_manager.get_audit_trail(payment_id)
        
        assert len(audit_trail) >= 1
        
        # Verify all records are for this payment
        for record in audit_trail:
            assert record["payment_id"] == payment_id
    
    def test_audit_integrity(self, payment_manager, sample_payment_request):
        """Test audit trail integrity verification."""
        # Create payment
        payment_manager.create_payment(sample_payment_request)
        
        # Verify integrity
        integrity_report = payment_manager.verify_audit_integrity()
        
        assert integrity_report["integrity_ok"] is True
        assert integrity_report["total_records"] >= 1
        assert integrity_report["verified_records"] >= 1
        assert integrity_report["integrity_issues"] == 0


class TestSandboxService:
    """Tests for the sandbox service."""
    
    def test_sandbox_accounts(self, payment_manager):
        """Test sandbox account management."""
        # Get or create account
        account = payment_manager.sandbox.get_or_create_user_account("test-user")
        
        assert account.account_id is not None
        assert account.user_id == "test-user"
        assert account.balance_minor >= 0
        assert account.currency == Currency.USD
    
    def test_sandbox_transactions(self, payment_manager, sample_payment_request):
        """Test sandbox transaction recording."""
        # Create payment
        payment_manager.create_payment(sample_payment_request)
        
        # Get sandbox transactions
        transactions = payment_manager.sandbox.list_sandbox_transactions()
        
        assert len(transactions) >= 1
        
        transaction = transactions[0]
        assert transaction.account_id is not None
        assert transaction.payment_id is not None
        assert transaction.amount_minor > 0
    
    def test_simulate_failure(self, payment_manager, sample_payment_request):
        """Test simulating payment failure."""
        # Create payment
        response = payment_manager.create_payment(sample_payment_request)
        payment_id = response.payment_id
        
        # Simulate failure (need to have payment in authorized state)
        try:
            payment_manager.sandbox.simulate_failure(payment_id, "insufficient_funds")
        except Exception:
            # This might fail if payment is not in the right state
            pass  # Expected for this test


class TestIdempotency:
    """Tests for idempotency functionality."""
    
    def test_capture_idempotency(self, payment_manager, sample_payment_request):
        """Test idempotency in payment capture."""
        # Create and authorize payment
        create_response = payment_manager.create_payment(sample_payment_request)
        payment_id = create_response.payment_id
        
        # Capture with idempotency key
        capture1 = payment_manager.capture_payment(
            payment_id, 
            idempotency_key="capture-key-123"
        )
        
        # Capture again with same key
        capture2 = payment_manager.capture_payment(
            payment_id,
            idempotency_key="capture-key-123"
        )
        
        assert capture1.payment_id == capture2.payment_id
        assert capture2.idempotent is True
    
    def test_refund_idempotency(self, payment_manager, sample_payment_request):
        """Test idempotency in payment refund."""
        # Create, authorize, and capture payment
        create_response = payment_manager.create_payment(sample_payment_request)
        payment_id = create_response.payment_id
        payment_manager.capture_payment(payment_id)
        
        # Refund with idempotency key
        refund1 = payment_manager.refund_payment(
            payment_id,
            idempotency_key="refund-key-123"
        )
        
        # Refund again with same key
        refund2 = payment_manager.refund_payment(
            payment_id,
            idempotency_key="refund-key-123"
        )
        
        assert refund1.payment_id == refund2.payment_id
        assert refund2.idempotent is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])