"""
Evidence and Provenance Data Models
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional, List, Dict
from uuid import UUID, uuid4


class EvidenceType(Enum):
    """Types of evidence that can be stored."""
    DOCUMENT = "document"
    API_RESPONSE = "api_response"
    WEB_PAGE = "web_page"
    DATABASE_RECORD = "database_record"
    USER_INPUT = "user_input"
    CALCULATION = "calculation"
    ESTIMATE = "estimate"
    SIMULATION = "simulation"
    TEST_DATA = "test_data"
    MANUAL_ENTRY = "manual_entry"


class VerificationStatus(Enum):
    """Status of evidence verification."""
    PENDING = "pending"
    VERIFIED = "verified"
    FAILED = "failed"
    PARTIAL = "partial"
    UNVERIFIABLE = "unverifiable"
    DISPUTED = "disputed"


class ConfidenceLevel(Enum):
    """Confidence levels for evidence."""
    CRITICAL = "critical"  # Verified from authoritative source
    HIGH = "high"  # Verified from reliable source
    MEDIUM = "medium"  # Verified but may have limitations
    LOW = "low"  # Unverified or estimated
    NONE = "none"  # Purely synthetic/test data


class SourceType(Enum):
    """Types of evidence sources."""
    PRIMARY = "primary"
    SECONDARY = "secondary"
    TERTIARY = "tertiary"
    AGGREGATED = "aggregated"
    DERIVED = "derived"


@dataclass
class EvidenceSource:
    """Represents a source of evidence."""
    name: str
    id: str = field(default_factory=lambda: str(uuid4()))
    description: Optional[str] = None
    source_type: SourceType = SourceType.PRIMARY
    url: Optional[str] = None
    authority: Optional[str] = None
    trust_score: float = 0.0  # 0.0 to 1.0
    last_accessed: Optional[datetime] = None
    is_active: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Claim:
    """A verifiable claim extracted from evidence."""
    statement: str
    evidence_id: str
    id: str = field(default_factory=lambda: str(uuid4()))
    claim_type: str = ""  # e.g., "price", "supplier_rating", "availability"
    value: Optional[Any] = None
    unit: Optional[str] = None
    confidence: ConfidenceLevel = ConfidenceLevel.NONE
    verification_status: VerificationStatus = VerificationStatus.PENDING
    source_id: Optional[str] = None
    extracted_at: datetime = field(default_factory=datetime.utcnow)
    verified_at: Optional[datetime] = None
    verified_by: Optional[str] = None  # User or system ID
    verification_method: Optional[str] = None
    supporting_evidence: List[str] = field(default_factory=list)
    contradicting_evidence: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class VerificationResult:
    """Result of verifying a claim or evidence item."""
    method: str
    id: str = field(default_factory=lambda: str(uuid4()))
    claim_id: Optional[str] = None
    evidence_id: Optional[str] = None
    status: VerificationStatus = VerificationStatus.PENDING
    checked_at: datetime = field(default_factory=datetime.utcnow)
    checked_by: Optional[str] = None
    findings: str = ""
    issues: List[str] = field(default_factory=list)
    confidence_score: float = 0.0  # 0.0 to 1.0
    evidence_used: List[str] = field(default_factory=list)
    duration_ms: int = 0


@dataclass
class EvidenceItem:
    """A single piece of evidence with full provenance."""
    title: str
    id: str = field(default_factory=lambda: str(uuid4()))
    description: Optional[str] = None
    content: Any = None  # Can be text, JSON, binary data
    evidence_type: EvidenceType = EvidenceType.DOCUMENT
    source_id: Optional[str] = None
    collector: Optional[str] = None  # Who collected this evidence
    collected_at: datetime = field(default_factory=datetime.utcnow)
    version: str = "1.0"
    hash_value: str = ""  # For integrity verification
    previous_version: Optional[str] = None
    is_synthetic: bool = False  # True for test/simulated data
    synthetic_purpose: Optional[str] = None  # Why this is synthetic
    claims: List[Claim] = field(default_factory=list)
    verification_results: List[VerificationResult] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EvidenceVersion:
    """Version history for an evidence item."""
    evidence_id: str
    version: str
    id: str = field(default_factory=lambda: str(uuid4()))
    content_hash: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)
    created_by: Optional[str] = None
    change_description: str = ""
    diff_from_previous: Optional[Dict[str, Any]] = None


@dataclass
class ProvenanceRecord:
    """Complete provenance trail for a decision or action."""
    action_id: str
    action_type: str
    id: str = field(default_factory=lambda: str(uuid4()))
    evidence_items: List[str] = field(default_factory=list)  # Evidence IDs
    claims_used: List[str] = field(default_factory=list)  # Claim IDs
    created_at: datetime = field(default_factory=datetime.utcnow)
    created_by: Optional[str] = None
    organization_id: Optional[str] = None
    workflow_id: Optional[str] = None
    step_number: int = 0
    justification: str = ""
    uncertainty_level: float = 0.0  # 0.0 to 1.0
    uncertainty_reasons: List[str] = field(default_factory=list)
    hash_chain: str = ""  # For tamper-evidence


@dataclass
class Contradiction:
    """A detected contradiction between evidence items or claims."""
    claim_a_id: str
    claim_b_id: str
    evidence_a_id: str
    evidence_b_id: str
    id: str = field(default_factory=lambda: str(uuid4()))
    contradiction_type: str = "conflicting_values"
    severity: str = "low"  # low, medium, high, critical
    description: str = ""
    detected_at: datetime = field(default_factory=datetime.utcnow)
    detected_by: Optional[str] = None
    resolution_status: str = "unresolved"  # unresolved, resolved, dismissed
    resolution_notes: Optional[str] = None
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None


@dataclass
class ConfidenceScore:
    """Confidence scoring for evidence or claims."""
    item_id: str  # Evidence or Claim ID
    item_type: str = "evidence"  # "evidence" or "claim"
    id: str = field(default_factory=lambda: str(uuid4()))
    overall_score: float = 0.0  # 0.0 to 1.0
    source_reliability: float = 0.0
    verification_history: float = 0.0
    recency: float = 0.0
    completeness: float = 0.0
    consistency: float = 0.0
    calculated_at: datetime = field(default_factory=datetime.utcnow)
    factors: Dict[str, float] = field(default_factory=dict)


@dataclass
class EvidenceGraph:
    """Graph representation of evidence relationships."""
    id: str = field(default_factory=lambda: str(uuid4()))
    name: str = ""
    nodes: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    relationships: List[Dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    description: str = ""
