"""
PeoplePay 360 - Evidence and Provenance Engine

This module provides a comprehensive evidence management system supporting:
- Evidence collection and storage
- Source identification and versioning
- Claim extraction and verification
- Contradiction detection
- Source dependency analysis
- Confidence and uncertainty reporting
- Evidence-to-decision linking
- Historical decision reconstruction
- Audit-ready evidence exports
- Tamper-evident event records

The distinction between verified facts, derived estimates, simulated examples,
and unsupported claims is always preserved.
"""

from evidence.models import (
    EvidenceSource,
    EvidenceItem,
    Claim,
    VerificationResult,
    EvidenceGraph,
    EvidenceVersion,
    ProvenanceRecord,
    Contradiction,
    ConfidenceScore,
)
from evidence.service import EvidenceService, get_evidence_service
from evidence.collector import EvidenceCollector, get_evidence_collector
from evidence.verifier import EvidenceVerifier, get_evidence_verifier
from evidence.storage import EvidenceStorage, get_evidence_storage
from evidence.provenance import ProvenanceTracker, get_provenance_tracker
from evidence.errors import (
    EvidenceError,
    EvidenceNotFoundError,
    VerificationError,
    SourceUnavailableError,
    IntegrityError,
    ContradictionError,
)

__all__ = [
    # Models
    "EvidenceSource",
    "EvidenceItem",
    "Claim",
    "VerificationResult",
    "EvidenceGraph",
    "EvidenceVersion",
    "ProvenanceRecord",
    "Contradiction",
    "ConfidenceScore",
    # Services
    "EvidenceService",
    "get_evidence_service",
    "EvidenceCollector",
    "get_evidence_collector",
    "EvidenceVerifier",
    "get_evidence_verifier",
    "EvidenceStorage",
    "get_evidence_storage",
    "ProvenanceTracker",
    "get_provenance_tracker",
    # Errors
    "EvidenceError",
    "EvidenceNotFoundError",
    "VerificationError",
    "SourceUnavailableError",
    "IntegrityError",
    "ContradictionError",
]
