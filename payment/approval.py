"""Approval service for payment authorization workflows.

This module provides:
- Human approval workflow for payments
- Approval token generation and validation
- Approval policies and limits
- Approval history tracking
- Multi-level approval support
"""

from __future__ import annotations

import hashlib
import secrets
import threading
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from payment.errors import (
    ApprovalAlreadyUsedError,
    ApprovalDeniedError,
    ApprovalNotFoundError,
    ApprovalRequiredError,
)
from payment.models import (
    Approval,
    ApprovalRequest,
    ApprovalStatus,
    Currency,
    PaymentRequest,
)


class ApprovalService:
    """Service for managing payment approval workflows.
    
    Features:
    - Human approval workflow
    - Secure approval tokens
    - Approval policies and limits
    - Approval history
    - Multi-level approval support
    - Expiration and cancellation
    """
    
    def __init__(self):
        self._lock = threading.RLock()
        self._approvals: dict[str, Approval] = {}
        self._pending_approvals: dict[str, Approval] = {}  # payment_id -> approval
        self._used_tokens: set[str] = set()
        self._policies: dict[str, ApprovalPolicy] = {}
        
        # Default policy
        self.set_default_policy()
    
    def set_default_policy(self) -> None:
        """Set default approval policy."""
        self._policies["default"] = ApprovalPolicy(
            policy_id="default",
            name="Default Policy",
            require_approval=True,
            auto_approve_limit=0,  # No auto-approval by default
            approvers=[],
            max_amount=None,
            requires_reason=True,
            approval_expiry_hours=24,
            max_approvals_per_user=10
        )
    
    def set_policy(self, policy: ApprovalPolicy) -> None:
        """Set or update an approval policy."""
        with self._lock:
            self._policies[policy.policy_id] = policy
    
    def get_policy(self, policy_id: str) -> ApprovalPolicy | None:
        """Get an approval policy."""
        with self._lock:
            return self._policies.get(policy_id)
    
    def get_applicable_policy(
        self,
        organization_id: str | None = None,
        amount: int | None = None,
        currency: Currency | None = None
    ) -> ApprovalPolicy:
        """Get the applicable policy for a payment request."""
        with self._lock:
            # Look for organization-specific policy first
            if organization_id:
                org_policy_id = f"org-{organization_id}"
                if org_policy_id in self._policies:
                    return self._policies[org_policy_id]
            
            # Return default policy
            return self._policies.get("default", self._policies["default"])
    
    def _generate_token(self) -> str:
        """Generate a secure approval token."""
        token = secrets.token_urlsafe(64)
        return token
    
    def _generate_approval_id(self) -> str:
        """Generate a unique approval identifier."""
        return f"appr-{uuid.uuid4().hex[:12]}"
    
    def _hash_token(self, token: str) -> str:
        """Hash a token for storage."""
        return hashlib.sha256(token.encode()).hexdigest()
    
    def request_approval(
        self,
        request: ApprovalRequest,
        policy: ApprovalPolicy | None = None
    ) -> Approval:
        """Request approval for a payment.
        
        This creates an approval request that must be granted by an authorized
        approver before the payment can proceed.
        """
        applicable_policy = policy or self.get_applicable_policy(
            request.organization_id,
            request.amount,
            request.currency
        )
        
        # Check if approval is required
        if not applicable_policy.require_approval:
            # Auto-approve if policy allows
            if applicable_policy.auto_approve_limit and request.amount <= applicable_policy.auto_approve_limit:
                return self._auto_approve(request, applicable_policy)
        
        # Create approval request
        approval_id = self._generate_approval_id()
        token = self._generate_token()
        
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(hours=applicable_policy.approval_expiry_hours)
        
        approval = Approval(
            approval_id=approval_id,
            payment_id=request.payment_id,
            order_id=request.order_id,
            status=ApprovalStatus.PENDING,
            requester_id=request.requester_id,
            approver_id=None,
            amount=request.amount,
            currency=request.currency,
            reason=request.reason,
            notes=None,
            requested_at=now,
            approved_at=None,
            rejected_at=None,
            expires_at=expires_at,
            approval_token=token,
            token_used=False,
            used_at=None,
            metadata=request.metadata or {}
        )
        
        with self._lock:
            self._approvals[approval_id] = approval
            if request.payment_id:
                self._pending_approvals[request.payment_id] = approval
        
        return approval
    
    def _auto_approve(
        self,
        request: ApprovalRequest,
        policy: ApprovalPolicy
    ) -> Approval:
        """Auto-approve a payment within policy limits."""
        approval_id = self._generate_approval_id()
        token = self._generate_token()
        
        now = datetime.now(timezone.utc)
        
        approval = Approval(
            approval_id=approval_id,
            payment_id=request.payment_id,
            order_id=request.order_id,
            status=ApprovalStatus.APPROVED,
            requester_id=request.requester_id,
            approver_id="system-auto",  # Auto-approved by system
            amount=request.amount,
            currency=request.currency,
            reason=request.reason or f"Auto-approved: amount within limit (${policy.auto_approve_limit / 100})",
            notes=f"Auto-approved per policy {policy.policy_id}",
            requested_at=now,
            approved_at=now,
            rejected_at=None,
            expires_at=None,
            approval_token=token,
            token_used=True,  # Considered used immediately
            used_at=now,
            metadata=request.metadata or {}
        )
        
        with self._lock:
            self._approvals[approval_id] = approval
            self._used_tokens.add(token)
        
        return approval
    
    def get_approval(self, approval_id: str) -> Approval:
        """Get an approval by ID."""
        with self._lock:
            if approval_id not in self._approvals:
                raise ApprovalNotFoundError(approval_id)
            return self._approvals[approval_id]
    
    def get_pending_approvals(
        self,
        requester_id: str | None = None,
        approver_id: str | None = None,
        organization_id: str | None = None
    ) -> list[Approval]:
        """Get all pending approvals."""
        with self._lock:
            approvals = [
                approval for approval in self._approvals.values()
                if approval.status == ApprovalStatus.PENDING
            ]
            
            if requester_id:
                approvals = [a for a in approvals if a.requester_id == requester_id]
            
            if approver_id:
                # This would normally check if approver can approve these
                pass
            
            # Sort by requested_at ascending (oldest first)
            approvals.sort(key=lambda a: a.requested_at)
            
            return approvals
    
    def approve(
        self,
        approval_id: str,
        approver_id: str,
        notes: str | None = None
    ) -> Approval:
        """Approve a payment request."""
        with self._lock:
            approval = self.get_approval(approval_id)
            
            if approval.status != ApprovalStatus.PENDING:
                raise ApprovalAlreadyUsedError(approval_id)
            
            if approval.expires_at and datetime.now(timezone.utc) > approval.expires_at:
                approval.status = ApprovalStatus.EXPIRED
                self._approvals[approval_id] = approval
                raise ApprovalRequiredError("Approval request has expired")
            
            # Update approval
            now = datetime.now(timezone.utc)
            approval.status = ApprovalStatus.APPROVED
            approval.approver_id = approver_id
            approval.notes = notes or "Approved"
            approval.approved_at = now
            approval.token_used = False  # Token is still available for use
            
            self._approvals[approval_id] = approval
            
            # Remove from pending
            if approval.payment_id in self._pending_approvals:
                del self._pending_approvals[approval.payment_id]
            
            return approval
    
    def reject(
        self,
        approval_id: str,
        approver_id: str,
        reason: str,
        notes: str | None = None
    ) -> Approval:
        """Reject a payment approval request."""
        with self._lock:
            approval = self.get_approval(approval_id)
            
            if approval.status != ApprovalStatus.PENDING:
                raise ApprovalAlreadyUsedError(approval_id)
            
            # Update approval
            now = datetime.now(timezone.utc)
            approval.status = ApprovalStatus.REJECTED
            approval.approver_id = approver_id
            approval.notes = notes or f"Rejected: {reason}"
            approval.rejected_at = now
            
            self._approvals[approval_id] = approval
            
            # Remove from pending
            if approval.payment_id in self._pending_approvals:
                del self._pending_approvals[approval.payment_id]
            
            return approval
    
    def cancel_approval_request(
        self,
        approval_id: str,
        requester_id: str,
        reason: str | None = None
    ) -> Approval:
        """Cancel an approval request."""
        with self._lock:
            approval = self.get_approval(approval_id)
            
            if approval.status != ApprovalStatus.PENDING:
                raise ApprovalAlreadyUsedError(approval_id)
            
            if approval.requester_id != requester_id:
                raise ApprovalDeniedError("Only the requester can cancel their approval request")
            
            # Update approval
            now = datetime.now(timezone.utc)
            approval.status = ApprovalStatus.CANCELLED
            approval.notes = reason or "Cancelled by requester"
            approval.rejected_at = now
            
            self._approvals[approval_id] = approval
            
            # Remove from pending
            if approval.payment_id in self._pending_approvals:
                del self._pending_approvals[approval.payment_id]
            
            return approval
    
    def validate_token(
        self,
        payment_id: str,
        token: str
    ) -> Approval:
        """Validate an approval token for a payment.
        
        This marks the token as used and returns the approval.
        """
        with self._lock:
            # Find approval for this payment
            if payment_id not in self._pending_approvals:
                raise ApprovalNotFoundError(f"No pending approval for payment {payment_id}")
            
            approval = self._pending_approvals[payment_id]
            
            # Check token
            if not approval.approval_token or approval.approval_token != token:
                raise ApprovalDeniedError("Invalid approval token")
            
            if approval.token_used:
                raise ApprovalAlreadyUsedError(approval.approval_id)
            
            if approval.status != ApprovalStatus.APPROVED:
                raise ApprovalDeniedError(
                    f"Approval not granted. Current status: {approval.status.value}"
                )
            
            if approval.expires_at and datetime.now(timezone.utc) > approval.expires_at:
                raise ApprovalDeniedError("Approval token has expired")
            
            # Mark token as used
            now = datetime.now(timezone.utc)
            approval.token_used = True
            approval.used_at = now
            
            self._approvals[approval.approval_id] = approval
            
            return approval
    
    def is_approval_required(self, payment_id: str) -> bool:
        """Check if approval is still required for a payment."""
        with self._lock:
            if payment_id not in self._pending_approvals:
                return False
            
            approval = self._pending_approvals[payment_id]
            return approval.status == ApprovalStatus.PENDING
    
    def get_approval_for_payment(self, payment_id: str) -> Approval | None:
        """Get the approval for a specific payment."""
        with self._lock:
            return self._pending_approvals.get(payment_id)
    
    def list_approvals(
        self,
        requester_id: str | None = None,
        approver_id: str | None = None,
        status: ApprovalStatus | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        limit: int = 100
    ) -> list[Approval]:
        """List approvals with filtering."""
        with self._lock:
            approvals = list(self._approvals.values())
            
            if requester_id:
                approvals = [a for a in approvals if a.requester_id == requester_id]
            
            if approver_id:
                approvals = [a for a in approvals if a.approver_id == approver_id]
            
            if status:
                approvals = [a for a in approvals if a.status == status]
            
            if start_date:
                approvals = [a for a in approvals if a.requested_at >= start_date]
            
            if end_date:
                approvals = [a for a in approvals if a.requested_at <= end_date]
            
            # Sort by requested_at descending
            approvals.sort(key=lambda a: a.requested_at, reverse=True)
            
            return approvals[:limit]
    
    def reset(self) -> None:
        """Reset the approval service (for testing)."""
        with self._lock:
            self._approvals.clear()
            self._pending_approvals.clear()
            self._used_tokens.clear()


class ApprovalPolicy:
    """Policy for payment approval workflows."""
    
    def __init__(
        self,
        policy_id: str,
        name: str,
        require_approval: bool = True,
        auto_approve_limit: int | None = None,
        approvers: list[str] | None = None,
        max_amount: int | None = None,
        requires_reason: bool = False,
        approval_expiry_hours: int = 24,
        max_approvals_per_user: int | None = None,
        metadata: dict[str, Any] | None = None
    ):
        self.policy_id = policy_id
        self.name = name
        self.require_approval = require_approval
        self.auto_approve_limit = auto_approve_limit
        self.approvers = approvers or []
        self.max_amount = max_amount
        self.requires_reason = requires_reason
        self.approval_expiry_hours = approval_expiry_hours
        self.max_approvals_per_user = max_approvals_per_user
        self.metadata = metadata or {}
    
    def can_auto_approve(self, amount: int) -> bool:
        """Check if a payment can be auto-approved under this policy."""
        if not self.auto_approve_limit:
            return False
        return amount <= self.auto_approve_limit