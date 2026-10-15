"""Sandbox payment service for PeoplePay 360.

This module provides a complete sandbox payment implementation that:
- Never moves real money
- Supports all payment lifecycle operations
- Provides realistic sandbox accounts and transactions
- Handles idempotency, retries, and failures
- Maintains audit trails
- Supports testing scenarios
"""

from __future__ import annotations

import hashlib
import threading
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from payment.errors import (
    IdempotencyConflictError,
    PaymentAlreadyProcessedError,
    PaymentFailedError,
    PaymentNotFoundError,
    SandboxAccountNotFoundError,
    SandboxLimitExceededError,
)
from payment.models import (
    Currency,
    PaymentAction,
    PaymentMethod,
    PaymentRequest,
    PaymentResponse,
    PaymentStatus,
    SandboxAccount,
    SandboxTransaction,
)


class SandboxPaymentService:
    """Sandbox payment service that simulates all payment operations.
    
    This service:
    - Never moves real money
    - Provides deterministic sandbox behavior
    - Supports successful and failed scenarios
    - Handles idempotency and retries
    - Maintains complete audit trails
    - Supports testing and development
    """
    
    def __init__(self):
        self._lock = threading.RLock()
        self._accounts: dict[str, SandboxAccount] = {}
        self._transactions: dict[str, SandboxTransaction] = {}
        self._payments: dict[str, PaymentResponse] = {}
        self._idempotency: dict[str, dict[str, Any]] = {}
        self._initialized = False
        
    def _initialize_default_accounts(self) -> None:
        """Initialize default sandbox accounts for testing."""
        with self._lock:
            if self._initialized:
                return
            
            # Create default system account
            system_account = SandboxAccount(
                account_id="sandbox-system",
                user_id="system",
                account_type="system",
                name="System Sandbox Account",
                balance_minor=10_000_000,  # 100,000 USD in cents
                currency=Currency.USD,
                daily_limit_minor=None,
                transaction_limit_minor=None,
                status="active",
                metadata={"description": "Default system sandbox account"}
            )
            self._accounts[system_account.account_id] = system_account
            
            self._initialized = True
    
    def _generate_id(self, prefix: str = "sandbox") -> str:
        """Generate a unique identifier."""
        return f"{prefix}-{uuid.uuid4().hex[:12]}"
    
    def _get_account(self, account_id: str) -> SandboxAccount:
        """Get a sandbox account by ID."""
        with self._lock:
            if account_id not in self._accounts:
                raise SandboxAccountNotFoundError(account_id)
            return self._accounts[account_id]
    
    def get_or_create_user_account(self, user_id: str, organization_id: str | None = None) -> SandboxAccount:
        """Get or create a sandbox account for a user."""
        with self._lock:
            account_id = f"sandbox-user-{user_id}"
            if organization_id:
                account_id = f"sandbox-org-{organization_id}-user-{user_id}"
            
            if account_id in self._accounts:
                return self._accounts[account_id]
            
            # Create new account with default balance
            account = SandboxAccount(
                account_id=account_id,
                user_id=user_id,
                organization_id=organization_id,
                account_type="user",
                name=f"Sandbox Account for {user_id}",
                balance_minor=10_000_000,  # 100,000 USD in cents
                currency=Currency.USD,
                daily_limit_minor=None,  # No daily limit for sandbox
                transaction_limit_minor=None,  # No transaction limit for sandbox
                status="active",
                metadata={"created_by": "system"}
            )
            self._accounts[account_id] = account
            return account
    
    def _check_idempotency(self, key: str, request_data: dict[str, Any]) -> bool:
        """Check if request is idempotent."""
        with self._lock:
            if key not in self._idempotency:
                # Store the request hash
                request_hash = self._hash_request(request_data)
                self._idempotency[key] = {
                    "request_hash": request_hash,
                    "response": None,
                    "created_at": datetime.now(timezone.utc),
                    "usage_count": 0
                }
                return False
            
            # Check if same request
            record = self._idempotency[key]
            current_hash = self._hash_request(request_data)
            
            if current_hash == record["request_hash"]:
                # Same request - return cached response
                record["usage_count"] += 1
                return True
            else:
                # Different request with same key - conflict
                raise IdempotencyConflictError(
                    key, 
                    "Idempotency key reused with different request"
                )
    
    def _hash_request(self, data: dict[str, Any]) -> str:
        """Hash request data for idempotency."""
        # Sort keys and convert to string for consistent hashing
        sorted_data = dict(sorted(data.items()))
        data_str = str(sorted_data).encode()
        return hashlib.sha256(data_str).hexdigest()
    
    def _get_payment(self, payment_id: str) -> PaymentResponse:
        """Get a payment by ID."""
        with self._lock:
            if payment_id not in self._payments:
                raise PaymentNotFoundError(payment_id)
            return self._payments[payment_id]
    
    def _validate_amount(self, account: SandboxAccount, amount: int, currency: Currency) -> None:
        """Validate payment amount against account limits."""
        if amount <= 0:
            raise PaymentFailedError("Payment amount must be positive")
        
        if account.currency != currency:
            raise PaymentFailedError(
                f"Currency mismatch: account is {account.currency}, payment is {currency}"
            )
        
        if account.transaction_limit_minor and amount > account.transaction_limit_minor:
            raise SandboxLimitExceededError(
                "transaction_limit",
                amount,
                account.transaction_limit_minor
            )
        
        if account.status != "active":
            raise PaymentFailedError(f"Account {account.account_id} is not active")
        
        if account.balance_minor < amount:
            raise PaymentFailedError("Insufficient sandbox funds")
    
    def create_payment(self, request: PaymentRequest) -> PaymentResponse:
        """Create a new payment in sandbox mode."""
        self._initialize_default_accounts()
        
        # Use user's sandbox account
        account = self.get_or_create_user_account(
            request.user_id, 
            request.organization_id
        )
        
        # Check idempotency
        idempotency_key = request.idempotency_key or self._generate_id("idemp")
        request_data = request.model_dump(exclude={"idempotency_key"})
        
        with self._lock:
            is_idempotent = self._check_idempotency(idempotency_key, request_data)
            
            if is_idempotent:
                # Return cached response
                cached = self._idempotency[idempotency_key]["response"]
                return PaymentResponse(**cached)
            
            # Validate amount
            self._validate_amount(account, request.amount, request.currency)
            
            # Generate payment ID if not provided
            payment_id = request.payment_id or self._generate_id("payment")
            
            # Create payment response
            now = datetime.now(timezone.utc)
            
            if request.requires_approval and not request.approved_by:
                # Payment requires approval
                response = PaymentResponse(
                    payment_id=payment_id,
                    order_id=request.order_id,
                    transaction_id=request.transaction_id,
                    amount=request.amount,
                    currency=request.currency,
                    method=PaymentMethod.SANDBOX,
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
                    reference=f"sandbox-auth-{self._generate_id()}",
                    metadata=request.metadata,
                    error_message=None,
                    state_transition=False
                )
            else:
                # Process payment (sandbox mode - no real money)
                response = PaymentResponse(
                    payment_id=payment_id,
                    order_id=request.order_id,
                    transaction_id=request.transaction_id,
                    amount=request.amount,
                    currency=request.currency,
                    method=PaymentMethod.SANDBOX,
                    status=PaymentStatus.AUTHORIZED,
                    action=PaymentAction.AUTHORIZE,
                    processed_at=now,
                    user_id=request.user_id,
                    organization_id=request.organization_id,
                    sandbox=True,
                    money_moved=False,
                    idempotent=False,
                    requires_approval=False,
                    approved_by=request.approved_by,
                    approved_at=now,
                    approval_required=False,
                    reference=f"sandbox-auth-{self._generate_id()}",
                    metadata=request.metadata,
                    error_message=None,
                    state_transition=True
                )
                
                # Record sandbox transaction
                sandbox_txn = SandboxTransaction(
                    transaction_id=self._generate_id("txn"),
                    account_id=account.account_id,
                    amount_minor=request.amount,
                    currency=request.currency,
                    description=f"Sandbox payment for order {request.order_id}",
                    status=PaymentStatus.AUTHORIZED,
                    type="debit",
                    payment_id=payment_id,
                    order_id=request.order_id,
                    processed_at=now,
                    metadata={"sandbox": True, "user_id": request.user_id}
                )
                self._transactions[sandbox_txn.transaction_id] = sandbox_txn
            
            # Store payment
            self._payments[payment_id] = response
            
            # Cache response for idempotency
            self._idempotency[idempotency_key]["response"] = response.model_dump()
            
            return response
    
    def authorize_payment(self, payment_id: str, request: PaymentRequest) -> PaymentResponse:
        """Authorize a payment."""
        self._initialize_default_accounts()
        
        with self._lock:
            existing = self._get_payment(payment_id)
            
            if existing.status != PaymentStatus.PENDING:
                raise PaymentAlreadyProcessedError(payment_id, existing.status.value)
            
            # Check idempotency
            idempotency_key = request.idempotency_key or existing.idempotency_key or self._generate_id("auth-idemp")
            request_data = request.model_dump(exclude={"idempotency_key"})
            is_idempotent = self._check_idempotency(idempotency_key, request_data)
            
            if is_idempotent:
                return existing
            
            # Update to authorized
            now = datetime.now(timezone.utc)
            response = PaymentResponse(
                payment_id=existing.payment_id,
                order_id=existing.order_id,
                transaction_id=existing.transaction_id,
                amount=existing.amount,
                currency=existing.currency,
                method=existing.method,
                status=PaymentStatus.AUTHORIZED,
                action=PaymentAction.AUTHORIZE,
                processed_at=now,
                authorization_code=f"sandbox-auth-{self._generate_id()}",
                user_id=existing.user_id,
                organization_id=existing.organization_id,
                sandbox=existing.sandbox,
                money_moved=existing.money_moved,
                idempotent=False,
                requires_approval=False,
                approved_by=request.approved_by or existing.approved_by,
                approved_at=now,
                approval_required=False,
                reference=existing.reference,
                metadata=existing.metadata,
                error_message=None,
                state_transition=True
            )
            
            # Update storage
            self._payments[payment_id] = response
            if idempotency_key:
                self._idempotency[idempotency_key]["response"] = response.model_dump()
            
            return response
    
    def capture_payment(self, payment_id: str, amount: int | None = None) -> PaymentResponse:
        """Capture a previously authorized payment."""
        self._initialize_default_accounts()
        
        with self._lock:
            existing = self._get_payment(payment_id)
            
            if existing.status != PaymentStatus.AUTHORIZED:
                raise PaymentAlreadyProcessedError(
                    payment_id, 
                    f"Expected AUTHORIZED, got {existing.status.value}"
                )
            
            # Use full amount if not specified
            capture_amount = amount or existing.amount
            
            # Update to captured
            now = datetime.now(timezone.utc)
            response = PaymentResponse(
                payment_id=existing.payment_id,
                order_id=existing.order_id,
                transaction_id=existing.transaction_id,
                amount=existing.amount,
                currency=existing.currency,
                method=existing.method,
                status=PaymentStatus.CAPTURED,
                action=PaymentAction.CAPTURE,
                processed_at=now,
                captured_at=now,
                capture_reference=f"sandbox-capture-{self._generate_id()}",
                user_id=existing.user_id,
                organization_id=existing.organization_id,
                sandbox=existing.sandbox,
                money_moved=False,  # Sandbox never moves real money
                idempotent=False,
                requires_approval=existing.requires_approval,
                approved_by=existing.approved_by,
                approved_at=existing.approved_at,
                approval_required=False,
                reference=existing.reference,
                authorization_code=existing.authorization_code,
                metadata=existing.metadata,
                error_message=None,
                state_transition=True
            )
            
            # Update storage
            self._payments[payment_id] = response
            
            # Record sandbox transaction for capture
            account = self.get_or_create_user_account(
                existing.user_id, 
                existing.organization_id
            )
            sandbox_txn = SandboxTransaction(
                transaction_id=self._generate_id("txn"),
                account_id=account.account_id,
                amount_minor=capture_amount,
                currency=existing.currency,
                description=f"Sandbox capture for payment {payment_id}",
                status=PaymentStatus.CAPTURED,
                type="capture",
                payment_id=payment_id,
                order_id=existing.order_id,
                processed_at=now,
                metadata={"sandbox": True, "capture_amount": capture_amount}
            )
            self._transactions[sandbox_txn.transaction_id] = sandbox_txn
            
            return response
    
    def refund_payment(self, payment_id: str, amount: int | None = None, reason: str | None = None) -> PaymentResponse:
        """Refund a previously captured payment."""
        self._initialize_default_accounts()
        
        with self._lock:
            existing = self._get_payment(payment_id)
            
            if existing.status not in (PaymentStatus.CAPTURED, PaymentStatus.PARTIAL_REFUNDED):
                raise PaymentAlreadyProcessedError(
                    payment_id,
                    f"Cannot refund payment in status {existing.status.value}"
                )
            
            # Use full amount if not specified
            refund_amount = amount or existing.amount
            
            # Determine new status
            if refund_amount >= existing.amount:
                new_status = PaymentStatus.REFUNDED
            else:
                new_status = PaymentStatus.PARTIAL_REFUNDED
            
            # Update to refunded
            now = datetime.now(timezone.utc)
            response = PaymentResponse(
                payment_id=existing.payment_id,
                order_id=existing.order_id,
                transaction_id=existing.transaction_id,
                amount=existing.amount,
                currency=existing.currency,
                method=existing.method,
                status=new_status,
                action=PaymentAction.REFUND,
                processed_at=now,
                user_id=existing.user_id,
                organization_id=existing.organization_id,
                sandbox=existing.sandbox,
                money_moved=False,  # Sandbox never moves real money
                idempotent=False,
                requires_approval=existing.requires_approval,
                approved_by=existing.approved_by,
                approved_at=existing.approved_at,
                approval_required=False,
                reference=existing.reference,
                authorization_code=existing.authorization_code,
                capture_reference=existing.capture_reference,
                metadata=existing.metadata,
                error_message=None,
                state_transition=True
            )
            
            # Update storage
            self._payments[payment_id] = response
            
            # Record sandbox transaction for refund
            account = self.get_or_create_user_account(
                existing.user_id, 
                existing.organization_id
            )
            sandbox_txn = SandboxTransaction(
                transaction_id=self._generate_id("txn"),
                account_id=account.account_id,
                amount_minor=refund_amount,
                currency=existing.currency,
                description=f"Sandbox refund for payment {payment_id}" + (f": {reason}" if reason else ""),
                status=new_status,
                type="credit",
                payment_id=payment_id,
                order_id=existing.order_id,
                processed_at=now,
                metadata={"sandbox": True, "refund_amount": refund_amount, "reason": reason}
            )
            self._transactions[sandbox_txn.transaction_id] = sandbox_txn
            
            return response
    
    def cancel_payment(self, payment_id: str, reason: str | None = None) -> PaymentResponse:
        """Cancel a payment."""
        self._initialize_default_accounts()
        
        with self._lock:
            existing = self._get_payment(payment_id)
            
            if existing.status in (PaymentStatus.CAPTURED, PaymentStatus.REFUNDED, PaymentStatus.CANCELLED):
                raise PaymentAlreadyProcessedError(
                    payment_id,
                    f"Cannot cancel payment in status {existing.status.value}"
                )
            
            # Update to cancelled
            now = datetime.now(timezone.utc)
            response = PaymentResponse(
                payment_id=existing.payment_id,
                order_id=existing.order_id,
                transaction_id=existing.transaction_id,
                amount=existing.amount,
                currency=existing.currency,
                method=existing.method,
                status=PaymentStatus.CANCELLED,
                action=PaymentAction.CANCEL,
                processed_at=now,
                user_id=existing.user_id,
                organization_id=existing.organization_id,
                sandbox=existing.sandbox,
                money_moved=existing.money_moved,
                idempotent=False,
                requires_approval=existing.requires_approval,
                approved_by=existing.approved_by,
                approved_at=existing.approved_at,
                approval_required=existing.approval_required,
                reference=existing.reference,
                authorization_code=existing.authorization_code,
                capture_reference=existing.capture_reference,
                metadata=existing.metadata,
                error_message=reason,
                state_transition=True
            )
            
            # Update storage
            self._payments[payment_id] = response
            
            return response
    
    def get_payment_status(self, payment_id: str) -> PaymentResponse:
        """Get the current status of a payment."""
        return self._get_payment(payment_id)
    
    def list_payments(
        self, 
        user_id: str | None = None,
        organization_id: str | None = None,
        status: PaymentStatus | None = None,
        limit: int = 100,
        offset: int = 0
    ) -> list[PaymentResponse]:
        """List payments with optional filtering."""
        with self._lock:
            payments = list(self._payments.values())
            
            if user_id:
                payments = [p for p in payments if p.user_id == user_id]
            
            if organization_id:
                payments = [p for p in payments if p.organization_id == organization_id]
            
            if status:
                payments = [p for p in payments if p.status == status]
            
            # Sort by processed_at descending
            payments.sort(key=lambda p: p.processed_at, reverse=True)
            
            return payments[offset:offset + limit]
    
    def get_sandbox_account(self, account_id: str) -> SandboxAccount:
        """Get sandbox account details."""
        return self._get_account(account_id)
    
    def list_sandbox_accounts(self, user_id: str | None = None) -> list[SandboxAccount]:
        """List sandbox accounts."""
        with self._lock:
            accounts = list(self._accounts.values())
            if user_id:
                accounts = [a for a in accounts if a.user_id == user_id]
            return accounts
    
    def get_sandbox_transaction(self, transaction_id: str) -> SandboxTransaction:
        """Get sandbox transaction details."""
        with self._lock:
            if transaction_id not in self._transactions:
                raise PaymentNotFoundError(transaction_id)
            return self._transactions[transaction_id]
    
    def list_sandbox_transactions(
        self,
        account_id: str | None = None,
        payment_id: str | None = None,
        limit: int = 100
    ) -> list[SandboxTransaction]:
        """List sandbox transactions."""
        with self._lock:
            transactions = list(self._transactions.values())
            
            if account_id:
                transactions = [t for t in transactions if t.account_id == account_id]
            
            if payment_id:
                transactions = [t for t in transactions if t.payment_id == payment_id]
            
            transactions.sort(key=lambda t: t.created_at, reverse=True)
            return transactions[:limit]
    
    def simulate_failure(self, payment_id: str, failure_type: str = "insufficient_funds") -> PaymentResponse:
        """Simulate a payment failure for testing."""
        self._initialize_default_accounts()
        
        with self._lock:
            existing = self._get_payment(payment_id)
            
            if existing.status != PaymentStatus.AUTHORIZED:
                raise PaymentAlreadyProcessedError(payment_id, existing.status.value)
            
            # Update to failed
            now = datetime.now(timezone.utc)
            response = PaymentResponse(
                payment_id=existing.payment_id,
                order_id=existing.order_id,
                transaction_id=existing.transaction_id,
                amount=existing.amount,
                currency=existing.currency,
                method=existing.method,
                status=PaymentStatus.FAILED,
                action=PaymentAction.AUTHORIZE,
                processed_at=now,
                user_id=existing.user_id,
                organization_id=existing.organization_id,
                sandbox=existing.sandbox,
                money_moved=existing.money_moved,
                idempotent=False,
                requires_approval=existing.requires_approval,
                approved_by=existing.approved_by,
                approved_at=existing.approved_at,
                approval_required=existing.approval_required,
                reference=existing.reference,
                authorization_code=existing.authorization_code,
                capture_reference=existing.capture_reference,
                metadata=existing.metadata,
                error_message=f"Sandbox simulated failure: {failure_type}",
                state_transition=True
            )
            
            # Update storage
            self._payments[payment_id] = response
            
            return response
    
    def reset(self) -> None:
        """Reset the sandbox service (for testing)."""
        with self._lock:
            self._accounts.clear()
            self._transactions.clear()
            self._payments.clear()
            self._idempotency.clear()
            self._initialized = False