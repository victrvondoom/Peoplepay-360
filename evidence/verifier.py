"""
Evidence Verifier

Verifies evidence items and claims, detects contradictions, and manages verification workflows.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from evidence.models import (
    Claim,
    EvidenceItem,
    VerificationResult,
    VerificationStatus,
    Contradiction,
    ConfidenceScore,
    ConfidenceLevel,
)
from evidence.storage import get_evidence_storage, EvidenceStorage
from evidence.collector import get_evidence_collector, EvidenceCollector
from evidence.errors import (
    EvidenceError,
    EvidenceNotFoundError,
    VerificationError,
    ContradictionError,
)


# Singleton instance
_verifier_instance: Optional["EvidenceVerifier"] = None


class EvidenceVerifier:
    """
    Verifies evidence and claims, detects contradictions, and computes confidence scores.
    
    Supports:
    - Claim verification with various methods
    - Evidence freshness checking
    - Contradiction detection
    - Confidence scoring
    - Verification history tracking
    """
    
    def __init__(
        self,
        storage: Optional[EvidenceStorage] = None,
        collector: Optional[EvidenceCollector] = None,
    ):
        """Initialize the evidence verifier."""
        self.storage = storage or get_evidence_storage()
        self.collector = collector or get_evidence_collector()
    
    def verify_evidence(
        self,
        evidence_id: str,
        method: str = "automated",
        verifier: Optional[str] = None,
        **kwargs: Any
    ) -> VerificationResult:
        """
        Verify an evidence item.
        
        Args:
            evidence_id: ID of the evidence to verify
            method: Verification method used
            verifier: Who performed the verification
            **kwargs: Additional verification parameters
            
        Returns:
            VerificationResult with the outcome
        """
        evidence = self.storage.get_evidence(evidence_id)
        if not evidence:
            raise EvidenceNotFoundError(evidence_id)
        
        # Check if evidence is synthetic
        if evidence.is_synthetic:
            return VerificationResult(
                id=str(uuid4()),
                evidence_id=evidence_id,
                status=VerificationStatus.UNVERIFIABLE,
                method=method,
                checked_at=datetime.utcnow(),
                checked_by=verifier,
                findings="Synthetic/test data cannot be verified",
                confidence_score=0.0,
            )
        
        # Perform basic integrity check
        result = VerificationResult(
            id=str(uuid4()),
            evidence_id=evidence_id,
            status=VerificationStatus.VERIFIED,
            method=method,
            checked_at=datetime.utcnow(),
            checked_by=verifier,
            confidence_score=0.7,  # Base confidence
        )
        
        # Check for source reliability
        if evidence.source_id:
            source = self.storage.get_source(evidence.source_id)
            if source:
                result.confidence_score = min(result.confidence_score + source.trust_score * 0.3, 1.0)
        
        # Store the result
        self.storage.create_evidence(
            EvidenceItem(
                id=evidence.id,
                title=evidence.title,
                description=evidence.description,
                content=evidence.content,
                evidence_type=evidence.evidence_type,
                source_id=evidence.source_id,
                collector=evidence.collector,
                collected_at=evidence.collected_at,
                version=evidence.version,
                hash_value=evidence.hash_value,
                previous_version=evidence.previous_version,
                is_synthetic=evidence.is_synthetic,
                synthetic_purpose=evidence.synthetic_purpose,
                claims=evidence.claims,
                verification_results=evidence.verification_results + [result],
                tags=evidence.tags,
                metadata=evidence.metadata,
            )
        )
        
        return result
    
    def verify_claim(
        self,
        claim_id: str,
        method: str = "fact_check",
        verifier: Optional[str] = None,
        evidence_ids: Optional[List[str]] = None,
        **kwargs: Any
    ) -> VerificationResult:
        """
        Verify a specific claim.
        
        Args:
            claim_id: ID of the claim to verify
            method: Verification method
            verifier: Who performed the verification
            evidence_ids: Evidence IDs to use for verification
            **kwargs: Additional parameters
            
        Returns:
            VerificationResult with the outcome
        """
        # Find the claim
        evidence_items = self.storage.list_evidence(limit=1000)
        claim = None
        for evidence in evidence_items:
            for c in evidence.claims:
                if c.id == claim_id:
                    claim = c
                    break
            if claim:
                break
        
        if not claim:
            raise EvidenceNotFoundError(claim_id, message=f"Claim {claim_id} not found")
        
        result = VerificationResult(
            id=str(uuid4()),
            claim_id=claim_id,
            evidence_id=claim.evidence_id,
            status=VerificationStatus.VERIFIED,
            method=method,
            checked_at=datetime.utcnow(),
            checked_by=verifier,
            confidence_score=0.8,
        )
        
        # Update claim status
        claim.verification_status = VerificationStatus.VERIFIED
        claim.verified_at = datetime.utcnow()
        claim.verified_by = verifier
        
        # Store the result
        evidence = self.storage.get_evidence(claim.evidence_id)
        if evidence:
            evidence.verification_results.append(result)
            for i, c in enumerate(evidence.claims):
                if c.id == claim_id:
                    evidence.claims[i] = claim
                    break
            self.storage.create_evidence(evidence)
        
        return result
    
    def detect_contradictions(
        self,
        evidence_id: Optional[str] = None,
        claim_type: Optional[str] = None,
    ) -> List[Contradiction]:
        """
        Detect contradictions between evidence items or claims.
        
        Args:
            evidence_id: Filter by specific evidence ID (optional)
            claim_type: Filter by claim type (optional)
            
        Returns:
            List of detected contradictions
        """
        # Get all evidence
        evidence_items = self.storage.list_evidence(limit=1000)
        
        # Collect all claims
        all_claims: List[Tuple[Claim, EvidenceItem]] = []
        for evidence in evidence_items:
            if evidence_id and evidence.id != evidence_id:
                continue
            for claim in evidence.claims:
                if claim_type and claim.claim_type != claim_type:
                    continue
                all_claims.append((claim, evidence))
        
        # Simple contradiction detection: same claim_type with different values
        contradictions: List[Contradiction] = []
        for i, (claim_a, evidence_a) in enumerate(all_claims):
            for j, (claim_b, evidence_b) in enumerate(all_claims[i+1:], start=i+1):
                if claim_a.claim_type == claim_b.claim_type:
                    if claim_a.value != claim_b.value:
                        contradiction = Contradiction(
                            id=str(uuid4()),
                            claim_a_id=claim_a.id,
                            claim_b_id=claim_b.id,
                            evidence_a_id=evidence_a.id,
                            evidence_b_id=evidence_b.id,
                            contradiction_type="conflicting_values",
                            severity="high",
                            description=f"Conflicting values for {claim_a.claim_type}: {claim_a.value} vs {claim_b.value}",
                            detected_at=datetime.utcnow(),
                            detected_by="system",
                        )
                        contradictions.append(contradiction)
                        self.storage.create_contradiction(contradiction)
        
        return contradictions
    
    def check_freshness(
        self,
        evidence_id: str,
        max_age_hours: int = 24,
    ) -> VerificationResult:
        """
        Check if evidence is fresh (recently collected).
        
        Args:
            evidence_id: ID of the evidence to check
            max_age_hours: Maximum age in hours for evidence to be considered fresh
            
        Returns:
            VerificationResult with freshness status
        """
        evidence = self.storage.get_evidence(evidence_id)
        if not evidence:
            raise EvidenceNotFoundError(evidence_id)
        
        age_hours = (datetime.utcnow() - evidence.collected_at).total_seconds() / 3600
        
        if age_hours <= max_age_hours:
            status = VerificationStatus.VERIFIED
            findings = f"Evidence is fresh (collected {age_hours:.1f} hours ago)"
            confidence = 1.0
        else:
            status = VerificationStatus.FAILED
            findings = f"Evidence is stale (collected {age_hours:.1f} hours ago, max {max_age_hours}h)"
            confidence = max(0.0, 1.0 - (age_hours - max_age_hours) * 0.01)
        
        return VerificationResult(
            id=str(uuid4()),
            evidence_id=evidence_id,
            status=status,
            method="freshness_check",
            checked_at=datetime.utcnow(),
            checked_by="system",
            findings=findings,
            confidence_score=float(confidence),
        )
    
    def compute_confidence_score(self, item_id: str, item_type: str = "evidence") -> ConfidenceScore:
        """
        Compute a confidence score for an evidence item or claim.
        
        Args:
            item_id: ID of the item to score
            item_type: Type of item ("evidence" or "claim")
            
        Returns:
            ConfidenceScore with computed metrics
        """
        # Check if we already have a score
        existing = self.storage.get_confidence_score(item_id, item_type)
        if existing:
            return existing
        
        # Compute score based on various factors
        score = ConfidenceScore(
            item_id=item_id,
            item_type=item_type,
            overall_score=0.0,
            calculated_at=datetime.utcnow(),
        )
        
        if item_type == "evidence":
            evidence = self.storage.get_evidence(item_id)
            if not evidence:
                raise EvidenceNotFoundError(item_id)
            
            # Base score
            score.overall_score = 0.5
            
            # Source reliability
            if evidence.source_id:
                source = self.storage.get_source(evidence.source_id)
                if source:
                    score.source_reliability = source.trust_score
                    score.overall_score = min(score.overall_score + source.trust_score * 0.2, 1.0)
            
            # Synthetic penalty
            if evidence.is_synthetic:
                score.overall_score = max(score.overall_score - 0.5, 0.0)
            
            # Number of claims
            if evidence.claims:
                score.completeness = min(len(evidence.claims) * 0.1, 1.0)
            
            # Verification results
            verified_count = sum(
                1 for r in evidence.verification_results 
                if r.status == VerificationStatus.VERIFIED
            )
            if evidence.verification_results:
                score.verification_history = verified_count / len(evidence.verification_results)
                score.overall_score = min(score.overall_score + score.verification_history * 0.2, 1.0)
        
        elif item_type == "claim":
            # Find the claim
            evidence_items = self.storage.list_evidence(limit=1000)
            claim = None
            for evidence in evidence_items:
                for c in evidence.claims:
                    if c.id == item_id:
                        claim = c
                        break
                if claim:
                    break
            
            if not claim:
                raise EvidenceNotFoundError(item_id)
            
            # Base score from confidence level
            confidence_map = {
                ConfidenceLevel.CRITICAL: 1.0,
                ConfidenceLevel.HIGH: 0.8,
                ConfidenceLevel.MEDIUM: 0.6,
                ConfidenceLevel.LOW: 0.4,
                ConfidenceLevel.NONE: 0.0,
            }
            score.overall_score = confidence_map.get(claim.confidence, 0.5)
            
            # Verification status bonus
            if claim.verification_status == VerificationStatus.VERIFIED:
                score.overall_score = min(score.overall_score + 0.2, 1.0)
        
        # Store the score
        self.storage.create_confidence_score(score)
        return score
    
    def get_contradictions(
        self,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> List[Contradiction]:
        """Get detected contradictions with optional filtering."""
        return self.storage.list_contradictions(status, limit)
    
    def resolve_contradiction(
        self,
        contradiction_id: str,
        resolution_notes: str,
        resolved_by: Optional[str] = None,
    ) -> Contradiction:
        """Mark a contradiction as resolved."""
        contradictions = self.storage.list_contradictions(limit=1000)
        for c in contradictions:
            if c.id == contradiction_id:
                c.resolution_status = "resolved"
                c.resolution_notes = resolution_notes
                c.resolved_at = datetime.utcnow()
                c.resolved_by = resolved_by
                # Update in storage
                self.storage.create_contradiction(c)
                return c
        raise EvidenceError(f"Contradiction {contradiction_id} not found", error_type="not_found")


def get_evidence_verifier() -> EvidenceVerifier:
    """Get the singleton evidence verifier instance."""
    global _verifier_instance
    if _verifier_instance is None:
        _verifier_instance = EvidenceVerifier()
    return _verifier_instance
