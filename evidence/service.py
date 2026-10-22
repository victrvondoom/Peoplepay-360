"""
Evidence Service

Main service interface for evidence and provenance operations.
Provides a unified API for all evidence-related functionality.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Union
from uuid import uuid4

from evidence.models import (
    EvidenceItem,
    EvidenceSource,
    Claim,
    VerificationResult,
    EvidenceVersion,
    ProvenanceRecord,
    Contradiction,
    ConfidenceScore,
    EvidenceType,
    SourceType,
    VerificationStatus,
    ConfidenceLevel,
)
from evidence.storage import get_evidence_storage, EvidenceStorage
from evidence.collector import get_evidence_collector, EvidenceCollector
from evidence.verifier import get_evidence_verifier, EvidenceVerifier
from evidence.provenance import get_provenance_tracker, ProvenanceTracker
from evidence.errors import (
    EvidenceError,
    EvidenceNotFoundError,
    SourceNotFoundError,
    VerificationError,
    SourceUnavailableError,
    IntegrityError,
    ContradictionError,
    ProvenanceError,
)


# Singleton instance
_evidence_service_instance: Optional["EvidenceService"] = None


class EvidenceService:
    """
    Main evidence service providing a unified API for:
    - Evidence collection and storage
    - Evidence verification
    - Claim extraction and management
    - Contradiction detection
    - Provenance tracking
    - Confidence scoring
    - Audit-ready exports
    """
    
    def __init__(
        self,
        storage: Optional[EvidenceStorage] = None,
        collector: Optional[EvidenceCollector] = None,
        verifier: Optional[EvidenceVerifier] = None,
        provenance: Optional[ProvenanceTracker] = None,
    ):
        """Initialize the evidence service with all components."""
        self.storage = storage or get_evidence_storage()
        self.collector = collector or get_evidence_collector()
        self.verifier = verifier or get_evidence_verifier()
        self.provenance = provenance or get_provenance_tracker()
    
    # Source Management
    
    def register_source(
        self,
        name: str,
        source_type: SourceType = SourceType.PRIMARY,
        description: Optional[str] = None,
        url: Optional[str] = None,
        authority: Optional[str] = None,
        trust_score: float = 0.0,
        **metadata: Any
    ) -> EvidenceSource:
        """Register a new evidence source."""
        return self.collector.register_source(
            name=name,
            source_type=source_type,
            description=description,
            url=url,
            authority=authority,
            trust_score=trust_score,
            **metadata
        )
    
    def get_source(self, source_id: str) -> Optional[EvidenceSource]:
        """Get an evidence source by ID."""
        return self.collector.get_source(source_id)
    
    def list_sources(self, limit: int = 100, offset: int = 0) -> List[EvidenceSource]:
        """List all evidence sources."""
        return self.collector.list_sources(limit)
    
    # Evidence Collection
    
    def collect(
        self,
        content: Any,
        title: str,
        evidence_type: EvidenceType = EvidenceType.DOCUMENT,
        source_id: Optional[str] = None,
        collector: Optional[str] = None,
        description: Optional[str] = None,
        is_synthetic: bool = False,
        synthetic_purpose: Optional[str] = None,
        tags: Optional[List[str]] = None,
        **metadata: Any
    ) -> EvidenceItem:
        """Collect evidence from any source."""
        return self.collector.collect(
            content=content,
            title=title,
            evidence_type=evidence_type,
            source_id=source_id,
            collector=collector,
            description=description,
            is_synthetic=is_synthetic,
            synthetic_purpose=synthetic_purpose,
            tags=tags,
            **metadata
        )
    
    def collect_document(
        self,
        text: str,
        title: str,
        source_url: Optional[str] = None,
        source_name: Optional[str] = None,
        **kwargs: Any
    ) -> EvidenceItem:
        """Collect a document as evidence."""
        return self.collector.collect_document(
            text=text,
            title=title,
            source_url=source_url,
            source_name=source_name,
            **kwargs
        )
    
    def collect_api_response(
        self,
        response: Dict[str, Any],
        endpoint: str,
        source_name: str,
        **kwargs: Any
    ) -> EvidenceItem:
        """Collect an API response as evidence."""
        return self.collector.collect_api_response(
            response=response,
            endpoint=endpoint,
            source_name=source_name,
            **kwargs
        )
    
    def collect_user_input(
        self,
        data: Any,
        user_id: str,
        input_type: str,
        **kwargs: Any
    ) -> EvidenceItem:
        """Collect user input as evidence."""
        return self.collector.collect_user_input(
            data=data,
            user_id=user_id,
            input_type=input_type,
            **kwargs
        )
    
    def collect_calculation(
        self,
        inputs: Dict[str, Any],
        output: Any,
        method: str,
        **kwargs: Any
    ) -> EvidenceItem:
        """Collect a calculation as evidence."""
        return self.collector.collect_calculation(
            inputs=inputs,
            output=output,
            method=method,
            **kwargs
        )
    
    def collect_synthetic(
        self,
        data: Any,
        purpose: str,
        data_type: str = "test_data",
        **kwargs: Any
    ) -> EvidenceItem:
        """Collect synthetic/test data as evidence."""
        return self.collector.collect_synthetic(
            data=data,
            purpose=purpose,
            data_type=data_type,
            **kwargs
        )
    
    # Evidence Retrieval
    
    def get_evidence(self, evidence_id: str) -> Optional[EvidenceItem]:
        """Get evidence by ID with all related data."""
        return self.storage.get_evidence(evidence_id)
    
    def list_evidence(self, limit: int = 100, offset: int = 0) -> List[EvidenceItem]:
        """List all evidence items."""
        return self.storage.list_evidence(limit, offset)
    
    def search_evidence(
        self,
        query: Optional[str] = None,
        evidence_type: Optional[EvidenceType] = None,
        source_id: Optional[str] = None,
        collector: Optional[str] = None,
        tags: Optional[List[str]] = None,
        limit: int = 100,
    ) -> List[EvidenceItem]:
        """Search evidence with filters."""
        evidence_list = self.list_evidence(limit * 2)
        
        results = []
        for evidence in evidence_list:
            if query and query.lower() not in evidence.title.lower() and \
               query.lower() not in (evidence.description or "").lower():
                continue
            if evidence_type and evidence.evidence_type != evidence_type:
                continue
            if source_id and evidence.source_id != source_id:
                continue
            if collector and evidence.collector != collector:
                continue
            if tags:
                if not any(tag in evidence.tags for tag in tags):
                    continue
            results.append(evidence)
            if len(results) >= limit:
                break
        
        return results
    
    def verify_integrity(self, evidence_id: str) -> bool:
        """Verify evidence integrity."""
        return self.collector.verify_integrity(evidence_id)
    
    # Claim Management
    
    def add_claim(
        self,
        evidence_id: str,
        statement: str,
        claim_type: str,
        value: Optional[Any] = None,
        unit: Optional[str] = None,
        confidence: ConfidenceLevel = ConfidenceLevel.NONE,
        source_id: Optional[str] = None,
        **metadata: Any
    ) -> Claim:
        """Add a claim to an evidence item."""
        evidence = self.get_evidence(evidence_id)
        if not evidence:
            raise EvidenceNotFoundError(evidence_id)
        
        claim = Claim(
            id=str(uuid4()),
            statement=statement,
            evidence_id=evidence_id,
            claim_type=claim_type,
            value=value,
            unit=unit,
            confidence=confidence,
            source_id=source_id,
            metadata=metadata,
        )
        
        evidence.claims.append(claim)
        self.storage.create_evidence(evidence)
        return claim
    
    def get_claim(self, claim_id: str) -> Optional[Claim]:
        """Get a claim by ID."""
        evidence_list = self.list_evidence(limit=1000)
        for evidence in evidence_list:
            for claim in evidence.claims:
                if claim.id == claim_id:
                    return claim
        return None
    
    def list_claims(
        self,
        evidence_id: Optional[str] = None,
        claim_type: Optional[str] = None,
        limit: int = 100,
    ) -> List[Claim]:
        """List claims with optional filtering."""
        claims = []
        evidence_list = self.list_evidence(limit=1000)
        
        for evidence in evidence_list:
            if evidence_id and evidence.id != evidence_id:
                continue
            for claim in evidence.claims:
                if claim_type and claim.claim_type != claim_type:
                    continue
                claims.append(claim)
                if len(claims) >= limit:
                    return claims
        
        return claims
    
    # Verification
    
    def verify_evidence(
        self,
        evidence_id: str,
        method: str = "automated",
        verifier: Optional[str] = None,
        **kwargs: Any
    ) -> VerificationResult:
        """Verify an evidence item."""
        return self.verifier.verify_evidence(
            evidence_id=evidence_id,
            method=method,
            verifier=verifier,
            **kwargs
        )
    
    def verify_claim(
        self,
        claim_id: str,
        method: str = "fact_check",
        verifier: Optional[str] = None,
        **kwargs: Any
    ) -> VerificationResult:
        """Verify a claim."""
        return self.verifier.verify_claim(
            claim_id=claim_id,
            method=method,
            verifier=verifier,
            **kwargs
        )
    
    def detect_contradictions(
        self,
        evidence_id: Optional[str] = None,
        claim_type: Optional[str] = None,
    ) -> List[Contradiction]:
        """Detect contradictions."""
        return self.verifier.detect_contradictions(
            evidence_id=evidence_id,
            claim_type=claim_type,
        )
    
    def check_freshness(
        self,
        evidence_id: str,
        max_age_hours: int = 24,
    ) -> VerificationResult:
        """Check if evidence is fresh."""
        return self.verifier.check_freshness(
            evidence_id=evidence_id,
            max_age_hours=max_age_hours,
        )
    
    def compute_confidence_score(
        self,
        item_id: str,
        item_type: str = "evidence",
    ) -> ConfidenceScore:
        """Compute confidence score."""
        return self.verifier.compute_confidence_score(
            item_id=item_id,
            item_type=item_type,
        )
    
    # Contradiction Management
    
    def get_contradictions(
        self,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> List[Contradiction]:
        """Get contradictions."""
        return self.verifier.get_contradictions(status, limit)
    
    def resolve_contradiction(
        self,
        contradiction_id: str,
        resolution_notes: str,
        resolved_by: Optional[str] = None,
    ) -> Contradiction:
        """Resolve a contradiction."""
        return self.verifier.resolve_contradiction(
            contradiction_id=contradiction_id,
            resolution_notes=resolution_notes,
            resolved_by=resolved_by,
        )
    
    # Provenance Tracking
    
    def record_provenance(
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
        """Record provenance for an action."""
        return self.provenance.record(
            action_id=action_id,
            action_type=action_type,
            evidence_items=evidence_items,
            claims_used=claims_used,
            organization_id=organization_id,
            workflow_id=workflow_id,
            step_number=step_number,
            justification=justification,
            uncertainty_level=uncertainty_level,
            uncertainty_reasons=uncertainty_reasons,
            created_by=created_by,
            previous_hash=previous_hash,
        )
    
    def get_provenance(self, action_id: str) -> List[ProvenanceRecord]:
        """Get provenance history for an action."""
        return self.provenance.get_history(action_id)
    
    def verify_provenance_chain(self, action_id: str) -> Tuple[bool, List[str]]:
        """Verify provenance chain integrity."""
        return self.provenance.verify_chain(action_id)
    
    def get_evidence_for_action(self, action_id: str) -> List[EvidenceItem]:
        """Get all evidence for an action."""
        return self.provenance.get_evidence_for_action(action_id)
    
    def export_audit_trail(
        self,
        action_id: str,
        include_full_content: bool = False,
    ) -> Dict[str, Any]:
        """Export complete audit trail."""
        return self.provenance.export_audit_trail(
            action_id=action_id,
            include_full_content=include_full_content,
        )
    
    # Decision Recording
    
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
        """Record a decision with full provenance."""
        return self.provenance.record_decision(
            decision_id=decision_id,
            decision=decision,
            justification=justification,
            evidence_ids=evidence_ids,
            claims_used=claims_used,
            organization_id=organization_id,
            workflow_id=workflow_id,
            step_number=step_number,
            created_by=created_by,
            uncertainty=uncertainty,
            uncertainty_reasons=uncertainty_reasons,
        )
    
    # Health Check
    
    def health_check(self) -> Dict[str, Any]:
        """Perform a health check on all evidence services."""
        return {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "components": {
                "storage": "OK",
                "collector": "OK",
                "verifier": "OK",
                "provenance": "OK",
            },
            "stats": {
                "sources_count": len(self.list_sources()),
                "evidence_count": len(self.list_evidence()),
                "claims_count": len(self.list_claims()),
                "contradictions_count": len(self.get_contradictions()),
            },
        }


def get_evidence_service() -> EvidenceService:
    """Get the singleton evidence service instance."""
    global _evidence_service_instance
    if _evidence_service_instance is None:
        _evidence_service_instance = EvidenceService()
    return _evidence_service_instance
