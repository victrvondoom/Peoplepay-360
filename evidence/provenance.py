"""
Provenance Tracker

Tracks the complete provenance chain for decisions, actions, and transactions.
"""

import hashlib
import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from evidence.models import (
    ProvenanceRecord,
    EvidenceItem,
)
from evidence.storage import get_evidence_storage, EvidenceStorage
from evidence.errors import EvidenceError, ProvenanceError


# Singleton instance
_provenance_instance: Optional["ProvenanceTracker"] = None


class ProvenanceTracker:
    """
    Tracks provenance for all business operations.
    
    Provides:
    - Decision provenance recording
    - Action history tracking
    - Evidence-to-decision linking
    - Tamper-evident hash chains
    - Historical decision reconstruction
    """
    
    def __init__(self, storage: Optional[EvidenceStorage] = None):
        """Initialize the provenance tracker."""
        self.storage = storage or get_evidence_storage()
    
    def record(
        self,
        action_id: str,
        action_type: str,
        evidence_items: List[str],
        claims_used: Optional[List[str]] = None,
        organization_id: Optional[str] = None,
        workflow_id: Optional[str] = None,
        step_number: int = 0,
        justification: str = "",
        uncertainty_level: float = 0.0,
        uncertainty_reasons: Optional[List[str]] = None,
        created_by: Optional[str] = None,
        previous_hash: Optional[str] = None,
    ) -> ProvenanceRecord:
        """
        Record a provenance entry for an action.
        
        Args:
            action_id: Unique identifier for the action/decision
            action_type: Type of action (e.g., "payment", "order", "approval")
            evidence_items: List of evidence IDs used in this action
            claims_used: List of claim IDs used (optional)
            organization_id: Organization that owns this action
            workflow_id: Workflow this action is part of
            step_number: Step number in the workflow
            justification: Human-readable justification
            uncertainty_level: 0.0 to 1.0, how uncertain this action is
            uncertainty_reasons: Reasons for uncertainty
            created_by: User or system that created this action
            previous_hash: Previous hash in the chain for tamper-evidence
            
        Returns:
            The created ProvenanceRecord
        """
        # Compute hash chain
        chain_data = {
            "action_id": action_id,
            "action_type": action_type,
            "evidence_items": sorted(evidence_items) if evidence_items else [],
            "claims_used": sorted(claims_used) if claims_used else [],
            "organization_id": organization_id,
            "workflow_id": workflow_id,
            "step_number": step_number,
            "justification": justification,
            "uncertainty_level": uncertainty_level,
            "created_at": datetime.utcnow().isoformat(),
            "created_by": created_by,
        }
        
        if previous_hash:
            chain_data["previous_hash"] = previous_hash
        
        hash_chain = hashlib.sha256(json.dumps(chain_data, sort_keys=True).encode()).hexdigest()
        
        record = ProvenanceRecord(
            id=str(uuid4()),
            action_id=action_id,
            action_type=action_type,
            evidence_items=evidence_items or [],
            claims_used=claims_used or [],
            created_at=datetime.utcnow(),
            created_by=created_by,
            organization_id=organization_id,
            workflow_id=workflow_id,
            step_number=step_number,
            justification=justification,
            uncertainty_level=uncertainty_level,
            uncertainty_reasons=uncertainty_reasons or [],
            hash_chain=hash_chain,
        )
        
        self.storage.create_provenance(record)
        return record
    
    def get_history(
        self,
        action_id: str,
    ) -> List[ProvenanceRecord]:
        """
        Get the complete provenance history for an action.
        
        Args:
            action_id: The action ID to get history for
            
        Returns:
            List of provenance records for this action, ordered by step number
        """
        return self.storage.get_provenance(action_id)
    
    def verify_chain(self, action_id: str) -> Tuple[bool, List[str]]:
        """
        Verify the integrity of the provenance chain for an action.
        
        Args:
            action_id: The action ID to verify
            
        Returns:
            Tuple of (is_valid, list_of_issues)
        """
        records = self.get_history(action_id)
        if not records:
            return False, [f"No provenance records found for action {action_id}"]
        
        issues: List[str] = []
        
        # Check if chain is complete
        for i, record in enumerate(records):
            if i == 0:
                # First record should not have previous_hash
                continue
            
            # Each subsequent record should have a hash that chains to the previous
            prev_record = records[i-1]
            
            # Recompute what the current record's hash should be
            chain_data = {
                "action_id": record.action_id,
                "action_type": record.action_type,
                "evidence_items": sorted(record.evidence_items),
                "claims_used": sorted(record.claims_used),
                "organization_id": record.organization_id,
                "workflow_id": record.workflow_id,
                "step_number": record.step_number,
                "justification": record.justification,
                "uncertainty_level": record.uncertainty_level,
                "created_at": record.created_at.isoformat(),
                "created_by": record.created_by,
                "previous_hash": prev_record.hash_chain,
            }
            
            expected_hash = hashlib.sha256(
                json.dumps(chain_data, sort_keys=True).encode()
            ).hexdigest()
            
            if record.hash_chain != expected_hash:
                issues.append(
                    f"Hash mismatch at step {record.step_number}: "
                    f"expected {expected_hash[:16]}..., got {record.hash_chain[:16]}..."
                )
        
        return len(issues) == 0, issues
    
    def get_evidence_for_action(
        self,
        action_id: str,
    ) -> List[EvidenceItem]:
        """
        Get all evidence items used in an action.
        
        Args:
            action_id: The action ID
            
        Returns:
            List of EvidenceItem objects
        """
        records = self.get_history(action_id)
        evidence_ids = set()
        for record in records:
            evidence_ids.update(record.evidence_items)
        
        evidence_items: List[EvidenceItem] = []
        for eid in evidence_ids:
            evidence = self.storage.get_evidence(eid)
            if evidence:
                evidence_items.append(evidence)
        
        return evidence_items
    
    def get_evidence_and_claims_for_action(
        self,
        action_id: str,
    ) -> Dict[str, Any]:
        """
        Get all evidence and claims used in an action with full details.
        
        Args:
            action_id: The action ID
            
        Returns:
            Dictionary with:
            - provenance: List of provenance records
            - evidence: List of evidence items
            - claims: List of claims
        """
        records = self.get_history(action_id)
        
        evidence_map: Dict[str, EvidenceItem] = {}
        claims_map: Dict[str, Any] = {}
        
        for record in records:
            for eid in record.evidence_items:
                evidence = self.storage.get_evidence(eid)
                if evidence and eid not in evidence_map:
                    evidence_map[eid] = evidence
                    for claim in evidence.claims:
                        claims_map[claim.id] = {
                            **{k: v for k, v in claim.__dict__.items() if not k.startswith('_')},
                            "evidence_id": evidence.id,
                            "evidence_title": evidence.title,
                        }
        
        return {
            "provenance": [
                {k: v for k, v in r.__dict__.items() if not k.startswith('_')}
                for r in records
            ],
            "evidence": [
                {k: v for k, v in e.__dict__.items() if not k.startswith('_')}
                for e in evidence_map.values()
            ],
            "claims": list(claims_map.values()),
        }
    
    def export_audit_trail(
        self,
        action_id: str,
        include_full_content: bool = False,
    ) -> Dict[str, Any]:
        """
        Export a complete, audit-ready trail for an action.
        
        Args:
            action_id: The action ID to export
            include_full_content: Whether to include full evidence content
            
        Returns:
            Complete audit trail as a dictionary
        """
        data = self.get_evidence_and_claims_for_action(action_id)
        
        # Add chain verification
        is_valid, issues = self.verify_chain(action_id)
        
        return {
            "action_id": action_id,
            "is_valid": is_valid,
            "integrity_issues": issues,
            "exported_at": datetime.utcnow().isoformat(),
            "provenance_count": len(data["provenance"]),
            "evidence_count": len(data["evidence"]),
            "claims_count": len(data["claims"]),
            "data": data,
        }
    
    def record_decision(
        self,
        decision_id: str,
        decision: Any,
        justification: str,
        evidence_ids: List[str],
        claims_used: Optional[List[str]] = None,
        organization_id: Optional[str] = None,
        workflow_id: Optional[str] = None,
        step_number: int = 0,
        created_by: Optional[str] = None,
        uncertainty: float = 0.0,
        uncertainty_reasons: Optional[List[str]] = None,
    ) -> ProvenanceRecord:
        """
        Record a decision with its provenance.
        
        Args:
            decision_id: Unique identifier for the decision
            decision: The actual decision value/content
            justification: Human-readable justification
            evidence_ids: Evidence IDs used
            claims_used: Claim IDs used
            organization_id: Organization
            workflow_id: Workflow ID
            step_number: Step number
            created_by: Who made the decision
            uncertainty: Uncertainty level
            uncertainty_reasons: Reasons for uncertainty
            
        Returns:
            ProvenanceRecord for this decision
        """
        # Store the decision as evidence first
        collector = get_evidence_storage()
        decision_evidence = collector.collect(
            content=decision,
            title=f"Decision: {decision_id}",
            evidence_type="decision",
            collector=created_by,
            is_synthetic=False,
        )
        
        # Include the decision evidence in the evidence list
        all_evidence_ids = evidence_ids + [decision_evidence.id]
        
        return self.record(
            action_id=decision_id,
            action_type="decision",
            evidence_items=all_evidence_ids,
            claims_used=claims_used or [],
            organization_id=organization_id,
            workflow_id=workflow_id,
            step_number=step_number,
            justification=justification,
            uncertainty_level=uncertainty,
            uncertainty_reasons=uncertainty_reasons or [],
            created_by=created_by,
        )


def get_provenance_tracker() -> ProvenanceTracker:
    """Get the singleton provenance tracker instance."""
    global _provenance_instance
    if _provenance_instance is None:
        _provenance_instance = ProvenanceTracker()
    return _provenance_instance
