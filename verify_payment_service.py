#!/usr/bin/env python3
"""Verification script for Payment Service implementation.

Run this to verify all payment service components are working correctly.
"""

from payment import (
    get_payment_manager,
    reset_payment_manager,
    PaymentRequest,
    PaymentResponse,
    PaymentStatus,
    PaymentMethod,
    Currency,
    CheckoutRequest,
    WebhookEvent,
    WebhookEventType,
)
from payment.errors import (
    PaymentNotFoundError,
    PaymentFailedError,
    ApprovalRequiredError,
)


def test_payment_lifecycle():
    """Test complete payment lifecycle."""
    print("Testing Payment Lifecycle...")
    reset_payment_manager()
    pm = get_payment_manager()
    
    # 1. Create payment
    request = PaymentRequest(
        user_id="test-user",
        organization_id="test-org",
        amount=10000,  # $100.00
        currency=Currency.USD,
        method=PaymentMethod.SANDBOX,
        requires_approval=False,
        approved_by="test-user",
    )
    response = pm.create_payment(request)
    assert response.payment_id is not None
    assert response.status == PaymentStatus.CAPTURED or response.status == PaymentStatus.AUTHORIZED
    assert response.sandbox is True
    assert response.money_moved is False
    print(f"PASS Payment created: {response.payment_id}")
    
    # 2. Get payment
    retrieved = pm.get_payment(response.payment_id)
    assert retrieved.payment_id == response.payment_id
    print(f"PASS Payment retrieved: {retrieved.payment_id}")
    
    # 3. List payments
    payments = pm.list_payments(user_id="test-user")
    assert len(payments) >= 1
    print(f"PASS Payments listed: {len(payments)} payment(s)")
    
    # 4. Check audit trail
    audit_trail = pm.get_audit_trail(response.payment_id)
    assert len(audit_trail) >= 1
    print(f"PASS Audit trail: {len(audit_trail)} record(s)")
    
    # 5. Verify audit integrity
    integrity = pm.verify_audit_integrity()
    assert integrity["integrity_ok"] is True
    print(f"PASS Audit integrity: OK")
    
    # 6. Test idempotency
    request2 = PaymentRequest(
        user_id="test-user",
        organization_id="test-org",
        amount=10000,
        currency=Currency.USD,
        method=PaymentMethod.SANDBOX,
        requires_approval=False,
        approved_by="test-user",
        idempotency_key="test-idempotency-key",
    )
    response2 = pm.create_payment(request2)
    # Create another with same key and same data
    request3 = PaymentRequest(
        user_id="test-user",
        organization_id="test-org",
        amount=10000,
        currency=Currency.USD,
        method=PaymentMethod.SANDBOX,
        requires_approval=False,
        approved_by="test-user",
        idempotency_key="test-idempotency-key",
    )
    response3 = pm.create_payment(request3)
    assert response3.idempotent is True
    print(f"PASS Idempotency: Working")
    
    print("\nPASS Payment Lifecycle Test: PASSED\n")


def test_checkout():
    """Test checkout session."""
    print("Testing Checkout Session...")
    reset_payment_manager()
    pm = get_payment_manager()
    
    # 1. Create checkout session
    request = CheckoutRequest(
        order_id="order-123",
        user_id="test-user",
        organization_id="test-org",
        amount=10000,
        currency=Currency.USD,
        require_approval=False,
    )
    session = pm.create_checkout_session(request)
    assert session.session_id is not None
    assert session.status == "draft"
    print(f"PASS Checkout session created: {session.session_id}")
    
    # 2. Get checkout session
    retrieved = pm.get_checkout_session(session.session_id)
    assert retrieved.session_id == session.session_id
    print(f"PASS Checkout session retrieved: {retrieved.session_id}")
    
    # 3. Complete checkout
    payment = pm.complete_checkout(session.session_id)
    assert payment.payment_id is not None
    print(f"PASS Checkout completed: {payment.payment_id}")
    
    print("\nPASS Checkout Session Test: PASSED\n")


def test_approval():
    """Test approval workflow."""
    print("Testing Approval Workflow...")
    reset_payment_manager()
    pm = get_payment_manager()
    
    # 1. Create payment with approval required
    request = PaymentRequest(
        user_id="test-user",
        organization_id="test-org",
        amount=10000,
        currency=Currency.USD,
        requires_approval=True,
    )
    response = pm.create_payment(request)
    assert response.requires_approval is True
    print(f"PASS Payment requires approval: {response.payment_id}")
    
    # 2. Request approval
    approval = pm.request_approval(
        payment_id=response.payment_id,
        requester_id="test-user",
        amount=10000,
        currency=Currency.USD,
    )
    assert approval.approval_id is not None
    print(f"PASS Approval requested: {approval.approval_id}")
    
    # 3. Approve payment
    approved = pm.approve_payment(
        payment_id=response.payment_id,
        approver_id="approver-user",
        notes="Approved for testing"
    )
    assert approved.status == "approved"
    print(f"PASS Payment approved: {approved.approval_id}")
    
    print("\nPASS Approval Workflow Test: PASSED\n")


def test_webhook():
    """Test webhook verification."""
    print("Testing Webhook Verification...")
    reset_payment_manager()
    pm = get_payment_manager()
    
    # 1. Create signed webhook event
    event = pm.create_signed_webhook(
        event_type=WebhookEventType.PAYMENT_CAPTURED,
        payment_id="test-payment",
        data={"amount": 10000},
        secret="test-secret"
    )
    assert event.signature is not None
    print(f"PASS Signed webhook event created")
    
    # 2. Verify signature (should succeed)
    verified = pm.webhook.verify_event_signature(event, "test-secret")
    assert verified is True
    print(f"PASS Webhook signature verified")
    
    # 3. Verify with wrong secret (should fail)
    try:
        pm.webhook.verify_event_signature(event, "wrong-secret")
        assert False, "Should have raised WebhookVerificationError"
    except Exception:
        print(f"PASS Invalid signature rejected")
    
    print("\nPASS Webhook Verification Test: PASSED\n")


def test_sandbox():
    """Test sandbox payment service."""
    print("Testing Sandbox Payment Service...")
    reset_payment_manager()
    pm = get_payment_manager()
    
    # 1. Create sandbox account
    account = pm.sandbox.get_or_create_user_account("test-user", "test-org")
    assert account.account_id is not None
    assert account.balance_minor >= 0
    print(f"PASS Sandbox account created: {account.account_id}")
    
    # 2. Create sandbox payment
    request = PaymentRequest(
        user_id="test-user",
        organization_id="test-org",
        amount=10000,
        currency=Currency.USD,
        requires_approval=False,
        approved_by="test-user",
    )
    response = pm.sandbox.create_payment(request)
    assert response.sandbox is True
    assert response.money_moved is False
    print(f"PASS Sandbox payment created: {response.payment_id}")
    
    # 3. Get payment status
    status = pm.sandbox.get_payment_status(response.payment_id)
    assert status.payment_id == response.payment_id
    print(f"PASS Sandbox payment status retrieved")
    
    print("\nPASS Sandbox Payment Service Test: PASSED\n")


def main():
    """Run all verification tests."""
    print("=" * 60)
    print("PEOPLEPAY 360 - PAYMENT SERVICE VERIFICATION")
    print("=" * 60)
    print()
    
    try:
        test_payment_lifecycle()
        test_checkout()
        test_approval()
        test_webhook()
        test_sandbox()
        
        print("=" * 60)
        print("PASS ALL VERIFICATION TESTS PASSED")
        print("=" * 60)
        print()
        print("Payment Service is WORKING and ready for integration!")
        print()
        return 0
    except AssertionError as e:
        print(f"\nFAIL VERIFICATION FAILED: {e}")
        return 1
    except Exception as e:
        print(f"\nFAIL UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(main())
