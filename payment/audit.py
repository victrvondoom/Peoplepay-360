"""Audit service for payment and commerce operations.

This module provides:
- Comprehensive audit trail for all payment operations
- Immutable audit records
- Provenance tracking
- Tamper-evident logging
- Audit trail querying and filtering
- Compliance reporting
"""

from __future__ import annotations

import hashlib
import json
import threading
import uuid
from datetime import datetime, timezone
from typing import Any

from payment.models import (
    AuditAction,
    AuditRecord,
    PaymentRequest,
    PaymentResponse,
    PaymentStatus,
)


class AuditService:
    """Service for maintaining audit trails of payment operations.
    
    Features:
    - Automatic audit record creation for all payment operations
    - Immutable, tamper-evident audit trail
    - Provenance tracking
    - Querying and filtering capabilities
    - Export for compliance
    """
    
    def __init__(self):
        self._lock = threading.RLock()
        self._records: list[AuditRecord] = []
        self._indexes: dict[str, list[str]] = {
            'payment_id': [],
            'order_id': [],
            'user_id': [],
            'organization_id': [],
            'action': [],
            'timestamp': [],
            'correlation_id': [],
        }
        
    def _add_to_indexes(self, record: AuditRecord) -> None:
        """Add a record to all relevant indexes."""
        if record.payment_id:
            self._indexes['payment_id'].append(record.record_id)
        if record.order_id:
            self._indexes['order_id'].append(record.record_id)
        if record.user_id:
            self._indexes['user_id'].append(record.record_id)
        if record.organization_id:
            self._indexes['organization_id'].append(record.record_id)
        if record.action:
            self._indexes['action'].append(record.record_id)
        if record.timestamp:
            self._indexes['timestamp'].append(record.record_id)
        if record.correlation_id:
            self._indexes['correlation_id'].append(record.record_id)
    
    def _compute_record_hash(self, record: AuditRecord) -> str:
        """Compute a hash of the audit record for integrity verification.
        
        Excludes metadata to avoid circular dependency with integrity_hash.
        """
        record_data = record.model_dump(exclude={'record_id', 'metadata'})
        record_str = json.dumps(record_data, sort_keys=True, default=str)
        return hashlib.sha256(record_str.encode()).hexdigest()
    
    def record_action(
        self,
        action: AuditAction,
        payment_id: str | None = None,
        order_id: str | None = None,
        user_id: str | None = None,
        organization_id: str | None = None,
        details: dict[str, Any] | None = None,
        previous_state: str | None = None,
        new_state: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        correlation_id: str | None = None,
        evidence_references: list[str] | None = None
    ) -> AuditRecord:
        """Record an audit action."""
        record = AuditRecord(
            record_id=f"audit-{uuid.uuid4().hex[:12]}",
            payment_id=payment_id,
            order_id=order_id,
            action=action,
            timestamp=datetime.now(timezone.utc),
            user_id=user_id,
            organization_id=organization_id,
            details=details or {},
            previous_state=previous_state,
            new_state=new_state,
            ip_address=ip_address,
            user_agent=user_agent,
            correlation_id=correlation_id,
            evidence_references=evidence_references or []
        )
        
        with self._lock:
            # Add integrity hash to metadata
            record.metadata['integrity_hash'] = self._compute_record_hash(record)
            record.metadata['sequence_number'] = len(self._records) + 1
            
            self._records.append(record)
            self._add_to_indexes(record)
        
        return record
    
    def record_payment_created(
        self,
        payment: PaymentResponse,
        request: PaymentRequest | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        correlation_id: str | None = None
    ) -> AuditRecord:
        """Record payment creation."""
        details = {
            'amount': payment.amount,
            'currency': payment.currency.value,
            'method': payment.method.value,
            'sandbox': payment.sandbox,
            'requires_approval': payment.requires_approval,
        }
        
        if request:
            details['request_metadata'] = request.metadata
        
        return self.record_action(
            action=AuditAction.PAYMENT_CREATED,
            payment_id=payment.payment_id,
            order_id=payment.order_id,
            user_id=payment.user_id,
            organization_id=payment.organization_id,
            details=details,
            new_state=payment.status.value,
            ip_address=ip_address,
            user_agent=user_agent,
            correlation_id=correlation_id,
            evidence_references=payment.metadata.get('evidence_references', [])
        )
    
    def record_payment_authorized(
        self,
        payment: PaymentResponse,
        authorized_by: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        correlation_id: str | None = None
    ) -> AuditRecord:
        """Record payment authorization."""
        details = {
            'amount': payment.amount,
            'currency': payment.currency.value,
            'authorization_code': payment.authorization_code,
            'approved_by': authorized_by,
            'sandbox': payment.sandbox,
        }
        
        return self.record_action(
            action=AuditAction.PAYMENT_AUTHORIZED,
            payment_id=payment.payment_id,
            order_id=payment.order_id,
            user_id=payment.user_id,
            organization_id=payment.organization_id,
            details=details,
            previous_state=payment.previous_status.value if payment.previous_status else None,
            new_state=payment.status.value,
            ip_address=ip_address,
            user_agent=user_agent,
            correlation_id=correlation_id
        )
    
    def record_payment_captured(
        self,
        payment: PaymentResponse,
        captured_amount: int | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        correlation_id: str | None = None
    ) -> AuditRecord:
        """Record payment capture."""
        details = {
            'amount': payment.amount,
            'captured_amount': captured_amount or payment.amount,
            'currency': payment.currency.value,
            'capture_reference': payment.capture_reference,
            'sandbox': payment.sandbox,
            'money_moved': payment.money_moved,
        }
        
        return self.record_action(
            action=AuditAction.PAYMENT_CAPTURED,
            payment_id=payment.payment_id,
            order_id=payment.order_id,
            user_id=payment.user_id,
            organization_id=payment.organization_id,
            details=details,
            previous_state=payment.previous_status.value if payment.previous_status else None,
            new_state=payment.status.value,
            ip_address=ip_address,
            user_agent=user_agent,
            correlation_id=correlation_id
        )
    
    def record_payment_failed(
        self,
        payment_id: str,
        order_id: str | None = None,
        user_id: str | None = None,
        organization_id: str | None = None,
        error_message: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        correlation_id: str | None = None
    ) -> AuditRecord:
        """Record payment failure."""
        details = {
            'error_message': error_message,
        }
        
        return self.record_action(
            action=AuditAction.PAYMENT_FAILED,
            payment_id=payment_id,
            order_id=order_id,
            user_id=user_id,
            organization_id=organization_id,
            details=details,
            new_state=PaymentStatus.FAILED.value,
            ip_address=ip_address,
            user_agent=user_agent,
            correlation_id=correlation_id
        )
    
    def record_payment_refunded(
        self,
        payment: PaymentResponse,
        refund_amount: int,
        reason: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        correlation_id: str | None = None
    ) -> AuditRecord:
        """Record payment refund."""
        details = {
            'refund_amount': refund_amount,
            'currency': payment.currency.value,
            'reason': reason,
            'sandbox': payment.sandbox,
            'full_refund': refund_amount >= payment.amount,
        }
        
        return self.record_action(
            action=AuditAction.PAYMENT_REFUNDED,
            payment_id=payment.payment_id,
            order_id=payment.order_id,
            user_id=payment.user_id,
            organization_id=payment.organization_id,
            details=details,
            previous_state=payment.previous_status.value if payment.previous_status else None,
            new_state=payment.status.value,
            ip_address=ip_address,
            user_agent=user_agent,
            correlation_id=correlation_id
        )
    
    def record_approval_requested(
        self,
        payment_id: str,
        user_id: str,
        amount: int,
        currency: str,
        order_id: str | None = None,
        organization_id: str | None = None,
        reason: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        correlation_id: str | None = None
    ) -> AuditRecord:
        """Record approval request."""
        details = {
            'amount': amount,
            'currency': currency,
            'reason': reason,
        }
        
        return self.record_action(
            action=AuditAction.APPROVAL_REQUESTED,
            payment_id=payment_id,
            order_id=order_id,
            user_id=user_id,
            organization_id=organization_id,
            details=details,
            new_state="approval_pending",
            ip_address=ip_address,
            user_agent=user_agent,
            correlation_id=correlation_id
        )
    
    def record_approval_granted(
        self,
        payment_id: str,
        user_id: str,
        approver_id: str,
        amount: int,
        currency: str,
        order_id: str | None = None,
        organization_id: str | None = None,
        approval_token: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        correlation_id: str | None = None
    ) -> AuditRecord:
        """Record approval granted."""
        details = {
            'amount': amount,
            'currency': currency,
            'approver_id': approver_id,
            'approval_token': approval_token,
        }
        
        return self.record_action(
            action=AuditAction.APPROVAL_GRANTED,
            payment_id=payment_id,
            order_id=order_id,
            user_id=user_id,
            organization_id=organization_id,
            details=details,
            previous_state="approval_pending",
            new_state="approved",
            ip_address=ip_address,
            user_agent=user_agent,
            correlation_id=correlation_id
        )
    
    def get_records(
        self,
        payment_id: str | None = None,
        order_id: str | None = None,
        user_id: str | None = None,
        organization_id: str | None = None,
        action: AuditAction | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        correlation_id: str | None = None,
        limit: int = 100,
        offset: int = 0
    ) -> list[AuditRecord]:
        """Query audit records with filtering."""
        with self._lock:
            candidate_ids: set[str] = set()
            
            if payment_id:
                candidate_ids.update(self._indexes['payment_id'])
            elif order_id:
                candidate_ids.update(self._indexes['order_id'])
            elif user_id:
                candidate_ids.update(self._indexes['user_id'])
            elif organization_id:
                candidate_ids.update(self._indexes['organization_id'])
            elif action:
                candidate_ids.update(self._indexes['action'])
            elif correlation_id:
                candidate_ids.update(self._indexes['correlation_id'])
            else:
                # No filters - return all
                candidate_ids.update(record.record_id for record in self._records)
            
            # Filter by time if specified
            if start_time or end_time:
                filtered_records = []
                for record in self._records:
                    if start_time and record.timestamp < start_time:
                        continue
                    if end_time and record.timestamp > end_time:
                        continue
                    filtered_records.append(record)
                return filtered_records[offset:offset + limit]
            
            # If we have candidate IDs, filter by them
            if candidate_ids:
                records = [
                    record for record in self._records 
                    if record.record_id in candidate_ids
                ]
            else:
                records = list(self._records)
            
            # Sort by timestamp descending
            records.sort(key=lambda r: r.timestamp, reverse=True)
            
            return records[offset:offset + limit]
    
    def get_payment_audit_trail(self, payment_id: str) -> list[AuditRecord]:
        """Get all audit records for a specific payment."""
        return self.get_records(payment_id=payment_id, limit=1000)
    
    def get_order_audit_trail(self, order_id: str) -> list[AuditRecord]:
        """Get all audit records for a specific order."""
        return self.get_records(order_id=order_id, limit=1000)
    
    def verify_integrity(self) -> dict[str, Any]:
        """Verify the integrity of the audit trail.
        
        Returns a report on any integrity issues.
        """
        with self._lock:
            issues = []
            verified_count = 0
            total_count = len(self._records)
            
            for i, record in enumerate(self._records):
                # Recompute hash
                expected_hash = self._compute_record_hash(record)
                actual_hash = record.metadata.get('integrity_hash')
                
                if actual_hash != expected_hash:
                    issues.append({
                        'record_id': record.record_id,
                        'sequence': i + 1,
                        'issue': 'integrity_hash_mismatch',
                        'expected': expected_hash,
                        'actual': actual_hash
                    })
                else:
                    verified_count += 1
                
                # Check sequence
                expected_sequence = i + 1
                actual_sequence = record.metadata.get('sequence_number')
                if actual_sequence != expected_sequence:
                    issues.append({
                        'record_id': record.record_id,
                        'sequence': i + 1,
                        'issue': 'sequence_number_mismatch',
                        'expected': expected_sequence,
                        'actual': actual_sequence
                    })
            
            return {
                'total_records': total_count,
                'verified_records': verified_count,
                'integrity_issues': len(issues),
                'issues': issues,
                'integrity_ok': len(issues) == 0
            }
    
    def export_audit_trail(
        self,
        payment_id: str | None = None,
        order_id: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None
    ) -> list[dict[str, Any]]:
        """Export audit trail for compliance reporting.
        
        Returns a list of audit records as dictionaries.
        """
        records = self.get_records(
            payment_id=payment_id,
            order_id=order_id,
            start_time=start_time,
            end_time=end_time,
            limit=10000
        )
        
        return [record.model_dump() for record in records]
    
    def reset(self) -> None:
        """Reset the audit service (for testing)."""
        with self._lock:
            self._records.clear()
            for key in self._indexes:
                self._indexes[key].clear()