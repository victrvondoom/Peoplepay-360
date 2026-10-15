"""
from typing import Any, Dict, List, Optional
Evidence Storage Backend

Provides persistent storage for evidence items, sources, and provenance records.
Uses SQLite as the default storage backend.
"""

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import threading

from evidence.models import (
    EvidenceItem,
    EvidenceSource,
    Claim,
    VerificationResult,
    EvidenceVersion,
    ProvenanceRecord,
    Contradiction,
    ConfidenceScore,
)
from evidence.errors import StorageError


# Singleton instance
_storage_instance: Optional["EvidenceStorage"] = None
_storage_lock = threading.Lock()


class EvidenceStorage:
    """
    SQLite-based storage for evidence and provenance data.
    
    Provides thread-safe operations for storing and retrieving:
    - Evidence items
    - Evidence sources
    - Claims
    - Verification results
    - Provenance records
    - Contradictions
    - Confidence scores
    """
    
    def __init__(self, db_path: str = "peoplepay-evidence.sqlite3"):
        """Initialize the evidence storage."""
        self.db_path = Path(db_path)
        self._lock = threading.Lock()
        self._initialize_database()
    
    @contextmanager
    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection with proper context management."""
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    
    def _initialize_database(self):
        """Create database tables if they don't exist."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Evidence sources table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS evidence_sources (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    source_type TEXT DEFAULT 'PRIMARY',
                    url TEXT,
                    authority TEXT,
                    trust_score REAL DEFAULT 0.0,
                    last_accessed TEXT,
                    is_active BOOLEAN DEFAULT 1,
                    metadata TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            
            # Evidence items table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS evidence_items (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT,
                    content TEXT NOT NULL,
                    evidence_type TEXT NOT NULL,
                    source_id TEXT,
                    collector TEXT,
                    collected_at TEXT NOT NULL,
                    version TEXT DEFAULT '1.0',
                    hash_value TEXT NOT NULL,
                    previous_version TEXT,
                    is_synthetic BOOLEAN DEFAULT 0,
                    synthetic_purpose TEXT,
                    tags TEXT,
                    metadata TEXT,
                    FOREIGN KEY (source_id) REFERENCES evidence_sources(id)
                )
            """)
            
            # Claims table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS claims (
                    id TEXT PRIMARY KEY,
                    statement TEXT NOT NULL,
                    evidence_id TEXT NOT NULL,
                    claim_type TEXT NOT NULL,
                    value TEXT,
                    unit TEXT,
                    confidence TEXT DEFAULT 'NONE',
                    verification_status TEXT DEFAULT 'PENDING',
                    source_id TEXT,
                    extracted_at TEXT NOT NULL,
                    verified_at TEXT,
                    verified_by TEXT,
                    verification_method TEXT,
                    supporting_evidence TEXT,
                    contradicting_evidence TEXT,
                    metadata TEXT,
                    FOREIGN KEY (evidence_id) REFERENCES evidence_items(id),
                    FOREIGN KEY (source_id) REFERENCES evidence_sources(id)
                )
            """)
            
            # Verification results table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS verification_results (
                    id TEXT PRIMARY KEY,
                    claim_id TEXT,
                    evidence_id TEXT,
                    status TEXT NOT NULL,
                    method TEXT NOT NULL,
                    checked_at TEXT NOT NULL,
                    checked_by TEXT,
                    findings TEXT,
                    issues TEXT,
                    confidence_score REAL DEFAULT 0.0,
                    evidence_used TEXT,
                    duration_ms INTEGER DEFAULT 0,
                    FOREIGN KEY (claim_id) REFERENCES claims(id),
                    FOREIGN KEY (evidence_id) REFERENCES evidence_items(id)
                )
            """)
            
            # Provenance records table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS provenance_records (
                    id TEXT PRIMARY KEY,
                    action_id TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    evidence_items TEXT,
                    claims_used TEXT,
                    created_at TEXT NOT NULL,
                    created_by TEXT,
                    organization_id TEXT,
                    workflow_id TEXT,
                    step_number INTEGER DEFAULT 0,
                    justification TEXT,
                    uncertainty_level REAL DEFAULT 0.0,
                    uncertainty_reasons TEXT,
                    hash_chain TEXT NOT NULL
                )
            """)
            
            # Contradictions table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS contradictions (
                    id TEXT PRIMARY KEY,
                    claim_a_id TEXT NOT NULL,
                    claim_b_id TEXT NOT NULL,
                    evidence_a_id TEXT NOT NULL,
                    evidence_b_id TEXT NOT NULL,
                    contradiction_type TEXT NOT NULL,
                    severity TEXT DEFAULT 'low',
                    description TEXT,
                    detected_at TEXT NOT NULL,
                    detected_by TEXT,
                    resolution_status TEXT DEFAULT 'unresolved',
                    resolution_notes TEXT,
                    resolved_at TEXT,
                    resolved_by TEXT
                )
            """)
            
            # Confidence scores table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS confidence_scores (
                    item_id TEXT NOT NULL,
                    item_type TEXT NOT NULL DEFAULT 'evidence',
                    overall_score REAL DEFAULT 0.0,
                    source_reliability REAL DEFAULT 0.0,
                    verification_history REAL DEFAULT 0.0,
                    recency REAL DEFAULT 0.0,
                    completeness REAL DEFAULT 0.0,
                    consistency REAL DEFAULT 0.0,
                    calculated_at TEXT NOT NULL,
                    factors TEXT,
                    PRIMARY KEY (item_id, item_type)
                )
            """)
            
            # Create indexes for performance
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_evidence_source ON evidence_items(source_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_claims_evidence ON claims(evidence_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_provenance_action ON provenance_records(action_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_contradictions_status ON contradictions(resolution_status)")
    
    def _serialize_dict(self, data: Dict[str, Any]) -> str:
        """Serialize a dictionary to JSON string."""
        return json.dumps(data) if data else "{}"
    
    def _deserialize_dict(self, data: Optional[str]) -> Dict[str, Any]:
        """Deserialize JSON string to dictionary."""
        return json.loads(data) if data else {}
    
    def _serialize_list(self, data: List[str]) -> str:
        """Serialize a list to JSON string."""
        return json.dumps(data) if data else "[]"
    
    def _deserialize_list(self, data: Optional[str]) -> List[str]:
        """Deserialize JSON string to list."""
        return json.loads(data) if data else []
    
    def _compute_hash(self, content: Any) -> str:
        """Compute SHA256 hash of content."""
        if content is None:
            return ""
        content_str = str(content) if not isinstance(content, str) else content
        return hashlib.sha256(content_str.encode()).hexdigest()
    
    # Evidence Source Operations
    
    def create_source(self, source: EvidenceSource) -> EvidenceSource:
        """Create or update an evidence source."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO evidence_sources 
                    (id, name, description, source_type, url, authority, 
                     trust_score, last_accessed, is_active, metadata, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    source.id,
                    source.name,
                    source.description,
                    source.source_type.value,
                    source.url,
                    source.authority,
                    source.trust_score,
                    source.last_accessed.isoformat() if source.last_accessed else None,
                    int(source.is_active),
                    self._serialize_dict(source.metadata),
                    source.created_at.isoformat(),
                    datetime.utcnow().isoformat(),
                ))
                return source
    
    def get_source(self, source_id: str) -> Optional[EvidenceSource]:
        """Get an evidence source by ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM evidence_sources WHERE id = ?", (source_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return EvidenceSource(
                id=row["id"],
                name=row["name"],
                description=row["description"],
                source_type=row["source_type"],
                url=row["url"],
                authority=row["authority"],
                trust_score=row["trust_score"],
                last_accessed=datetime.fromisoformat(row["last_accessed"]) if row["last_accessed"] else None,
                is_active=bool(row["is_active"]),
                metadata=self._deserialize_dict(row["metadata"]),
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.fromisoformat(row["updated_at"]),
            )
    
    def list_sources(self, limit: int = 100, offset: int = 0) -> List[EvidenceSource]:
        """List all evidence sources with pagination."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM evidence_sources 
                ORDER BY created_at DESC 
                LIMIT ? OFFSET ?
            """, (limit, offset))
            rows = cursor.fetchall()
            return [
                EvidenceSource(
                    id=row["id"],
                    name=row["name"],
                    description=row["description"],
                    source_type=row["source_type"],
                    url=row["url"],
                    authority=row["authority"],
                    trust_score=row["trust_score"],
                    last_accessed=datetime.fromisoformat(row["last_accessed"]) if row["last_accessed"] else None,
                    is_active=bool(row["is_active"]),
                    metadata=self._deserialize_dict(row["metadata"]),
                    created_at=datetime.fromisoformat(row["created_at"]),
                    updated_at=datetime.fromisoformat(row["updated_at"]),
                )
                for row in rows
            ]
    
    # Evidence Item Operations
    
    def create_evidence(self, evidence: EvidenceItem) -> EvidenceItem:
        """Create an evidence item."""
        with self._lock:
            # Compute hash if not provided
            if not evidence.hash_value:
                evidence.hash_value = self._compute_hash(evidence.content)
            
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO evidence_items 
                    (id, title, description, content, evidence_type, source_id,
                     collector, collected_at, version, hash_value, previous_version,
                     is_synthetic, synthetic_purpose, tags, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    evidence.id,
                    evidence.title,
                    evidence.description,
                    str(evidence.content) if evidence.content else "",
                    evidence.evidence_type.value,
                    evidence.source_id,
                    evidence.collector,
                    evidence.collected_at.isoformat(),
                    evidence.version,
                    evidence.hash_value,
                    evidence.previous_version,
                    int(evidence.is_synthetic),
                    evidence.synthetic_purpose,
                    self._serialize_list(evidence.tags),
                    self._serialize_dict(evidence.metadata),
                ))
                
                # Store claims if they exist
                for claim in evidence.claims:
                    self._store_claim(conn, claim, evidence.id)
                
                # Store verification results if they exist
                for result in evidence.verification_results:
                    self._store_verification_result(conn, result, evidence.id)
                
                return evidence
    
    def _store_claim(self, conn: sqlite3.Connection, claim: Claim, evidence_id: str):
        """Store a claim in the database."""
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO claims 
            (id, statement, evidence_id, claim_type, value, unit, confidence,
             verification_status, source_id, extracted_at, verified_at, verified_by,
             verification_method, supporting_evidence, contradicting_evidence, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            claim.id,
            claim.statement,
            evidence_id,
            claim.claim_type,
            str(claim.value) if claim.value else None,
            claim.unit,
            claim.confidence.value,
            claim.verification_status.value,
            claim.source_id,
            claim.extracted_at.isoformat(),
            claim.verified_at.isoformat() if claim.verified_at else None,
            claim.verified_by,
            claim.verification_method,
            self._serialize_list(claim.supporting_evidence),
            self._serialize_list(claim.contradicting_evidence),
            self._serialize_dict(claim.metadata),
        ))
        
        # Store verification results for this claim
        for result in claim.verification_results:
            self._store_verification_result(conn, result, evidence_id, claim.id)
    
    def _store_verification_result(
        self, 
        conn: sqlite3.Connection, 
        result: VerificationResult, 
        evidence_id: str, 
        claim_id: Optional[str] = None
    ):
        """Store a verification result in the database."""
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO verification_results 
            (id, claim_id, evidence_id, status, method, checked_at, checked_by,
             findings, issues, confidence_score, evidence_used, duration_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            result.id,
            claim_id,
            evidence_id,
            result.status.value,
            result.method,
            result.checked_at.isoformat(),
            result.checked_by,
            result.findings,
            self._serialize_list(result.issues),
            result.confidence_score,
            self._serialize_list(result.evidence_used),
            result.duration_ms,
        ))
    
    def get_evidence(self, evidence_id: str) -> Optional[EvidenceItem]:
        """Get an evidence item by ID with all related data."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM evidence_items WHERE id = ?", (evidence_id,))
            row = cursor.fetchone()
            if not row:
                return None
            
            evidence = EvidenceItem(
                id=row["id"],
                title=row["title"],
                description=row["description"],
                content=row["content"],
                evidence_type=row["evidence_type"],
                source_id=row["source_id"],
                collector=row["collector"],
                collected_at=datetime.fromisoformat(row["collected_at"]),
                version=row["version"],
                hash_value=row["hash_value"],
                previous_version=row["previous_version"],
                is_synthetic=bool(row["is_synthetic"]),
                synthetic_purpose=row["synthetic_purpose"],
                tags=self._deserialize_list(row["tags"]),
                metadata=self._deserialize_dict(row["metadata"]),
            )
            
            # Load claims
            cursor.execute("SELECT * FROM claims WHERE evidence_id = ?", (evidence_id,))
            evidence.claims = []
            for claim_row in cursor.fetchall():
                claim = Claim(
                    id=claim_row["id"],
                    statement=claim_row["statement"],
                    evidence_id=claim_row["evidence_id"],
                    claim_type=claim_row["claim_type"],
                    value=claim_row["value"],
                    unit=claim_row["unit"],
                    confidence=claim_row["confidence"],
                    verification_status=claim_row["verification_status"],
                    source_id=claim_row["source_id"],
                    extracted_at=datetime.fromisoformat(claim_row["extracted_at"]),
                    verified_at=datetime.fromisoformat(claim_row["verified_at"]) if claim_row["verified_at"] else None,
                    verified_by=claim_row["verified_by"],
                    verification_method=claim_row["verification_method"],
                    supporting_evidence=self._deserialize_list(claim_row["supporting_evidence"]),
                    contradicting_evidence=self._deserialize_list(claim_row["contradicting_evidence"]),
                    metadata=self._deserialize_dict(claim_row["metadata"]),
                )
                
                # Load verification results for this claim
                cursor.execute("SELECT * FROM verification_results WHERE claim_id = ?", (claim.id,))
                claim.verification_results = [
                    VerificationResult(
                        id=vr["id"],
                        claim_id=vr["claim_id"],
                        evidence_id=vr["evidence_id"],
                        status=vr["status"],
                        method=vr["method"],
                        checked_at=datetime.fromisoformat(vr["checked_at"]),
                        checked_by=vr["checked_by"],
                        findings=vr["findings"],
                        issues=self._deserialize_list(vr["issues"]),
                        confidence_score=vr["confidence_score"],
                        evidence_used=self._deserialize_list(vr["evidence_used"]),
                        duration_ms=vr["duration_ms"],
                    )
                    for vr in cursor.fetchall()
                ]
                evidence.claims.append(claim)
            
            # Load verification results for evidence
            cursor.execute("SELECT * FROM verification_results WHERE evidence_id = ? AND claim_id IS NULL", (evidence_id,))
            evidence.verification_results = [
                VerificationResult(
                    id=vr["id"],
                    claim_id=vr["claim_id"],
                    evidence_id=vr["evidence_id"],
                    status=vr["status"],
                    method=vr["method"],
                    checked_at=datetime.fromisoformat(vr["checked_at"]),
                    checked_by=vr["checked_by"],
                    findings=vr["findings"],
                    issues=self._deserialize_list(vr["issues"]),
                    confidence_score=vr["confidence_score"],
                    evidence_used=self._deserialize_list(vr["evidence_used"]),
                    duration_ms=vr["duration_ms"],
                )
                for vr in cursor.fetchall()
            ]
            
            return evidence
    
    def list_evidence(self, limit: int = 100, offset: int = 0) -> List[EvidenceItem]:
        """List evidence items with pagination (summary only)."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, title, description, evidence_type, source_id, 
                       collector, collected_at, version, hash_value, 
                       previous_version, is_synthetic, synthetic_purpose, tags, metadata
                FROM evidence_items 
                ORDER BY collected_at DESC 
                LIMIT ? OFFSET ?
            """, (limit, offset))
            return [
                EvidenceItem(
                    id=row["id"],
                    title=row["title"],
                    description=row["description"],
                    evidence_type=row["evidence_type"],
                    source_id=row["source_id"],
                    collector=row["collector"],
                    collected_at=datetime.fromisoformat(row["collected_at"]),
                    version=row["version"],
                    hash_value=row["hash_value"],
                    previous_version=row["previous_version"],
                    is_synthetic=bool(row["is_synthetic"]),
                    synthetic_purpose=row["synthetic_purpose"],
                    tags=self._deserialize_list(row["tags"]),
                    metadata=self._deserialize_dict(row["metadata"]),
                )
                for row in cursor.fetchall()
            ]
    
    # Provenance Operations
    
    def create_provenance(self, record: ProvenanceRecord) -> ProvenanceRecord:
        """Create a provenance record."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO provenance_records 
                    (id, action_id, action_type, evidence_items, claims_used,
                     created_at, created_by, organization_id, workflow_id, step_number,
                     justification, uncertainty_level, uncertainty_reasons, hash_chain)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    record.id,
                    record.action_id,
                    record.action_type,
                    self._serialize_list(record.evidence_items),
                    self._serialize_list(record.claims_used),
                    record.created_at.isoformat(),
                    record.created_by,
                    record.organization_id,
                    record.workflow_id,
                    record.step_number,
                    record.justification,
                    record.uncertainty_level,
                    self._serialize_list(record.uncertainty_reasons),
                    record.hash_chain,
                ))
                return record
    
    def get_provenance(self, action_id: str) -> List[ProvenanceRecord]:
        """Get all provenance records for a given action."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM provenance_records WHERE action_id = ? ORDER BY step_number", (action_id,))
            return [
                ProvenanceRecord(
                    id=row["id"],
                    action_id=row["action_id"],
                    action_type=row["action_type"],
                    evidence_items=self._deserialize_list(row["evidence_items"]),
                    claims_used=self._deserialize_list(row["claims_used"]),
                    created_at=datetime.fromisoformat(row["created_at"]),
                    created_by=row["created_by"],
                    organization_id=row["organization_id"],
                    workflow_id=row["workflow_id"],
                    step_number=row["step_number"],
                    justification=row["justification"],
                    uncertainty_level=row["uncertainty_level"],
                    uncertainty_reasons=self._deserialize_list(row["uncertainty_reasons"]),
                    hash_chain=row["hash_chain"],
                )
                for row in cursor.fetchall()
            ]
    
    # Contradiction Operations
    
    def create_contradiction(self, contradiction: Contradiction) -> Contradiction:
        """Create a contradiction record."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO contradictions 
                    (id, claim_a_id, claim_b_id, evidence_a_id, evidence_b_id,
                     contradiction_type, severity, description, detected_at, detected_by,
                     resolution_status, resolution_notes, resolved_at, resolved_by)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    contradiction.id,
                    contradiction.claim_a_id,
                    contradiction.claim_b_id,
                    contradiction.evidence_a_id,
                    contradiction.evidence_b_id,
                    contradiction.contradiction_type,
                    contradiction.severity,
                    contradiction.description,
                    contradiction.detected_at.isoformat(),
                    contradiction.detected_by,
                    contradiction.resolution_status,
                    contradiction.resolution_notes,
                    contradiction.resolved_at.isoformat() if contradiction.resolved_at else None,
                    contradiction.resolved_by,
                ))
                return contradiction
    
    def list_contradictions(self, status: Optional[str] = None, limit: int = 100) -> List[Contradiction]:
        """List contradictions with optional filtering."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT * FROM contradictions"
            params: List[Any] = []
            if status:
                query += " WHERE resolution_status = ?"
                params.append(status)
            query += " ORDER BY detected_at DESC LIMIT ?"
            params.append(limit)
            cursor.execute(query, params)
            return [
                Contradiction(
                    id=row["id"],
                    claim_a_id=row["claim_a_id"],
                    claim_b_id=row["claim_b_id"],
                    evidence_a_id=row["evidence_a_id"],
                    evidence_b_id=row["evidence_b_id"],
                    contradiction_type=row["contradiction_type"],
                    severity=row["severity"],
                    description=row["description"],
                    detected_at=datetime.fromisoformat(row["detected_at"]),
                    detected_by=row["detected_by"],
                    resolution_status=row["resolution_status"],
                    resolution_notes=row["resolution_notes"],
                    resolved_at=datetime.fromisoformat(row["resolved_at"]) if row["resolved_at"] else None,
                    resolved_by=row["resolved_by"],
                )
                for row in cursor.fetchall()
            ]
    
    # Confidence Score Operations
    
    def create_confidence_score(self, score: ConfidenceScore) -> ConfidenceScore:
        """Create or update a confidence score."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO confidence_scores 
                    (item_id, item_type, overall_score, source_reliability,
                     verification_history, recency, completeness, consistency,
                     calculated_at, factors)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    score.item_id,
                    score.item_type,
                    score.overall_score,
                    score.source_reliability,
                    score.verification_history,
                    score.recency,
                    score.completeness,
                    score.consistency,
                    score.calculated_at.isoformat(),
                    self._serialize_dict(score.factors),
                ))
                return score
    
    def get_confidence_score(self, item_id: str, item_type: str = "evidence") -> Optional[ConfidenceScore]:
        """Get confidence score for an item."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM confidence_scores WHERE item_id = ? AND item_type = ?", (item_id, item_type))
            row = cursor.fetchone()
            if not row:
                return None
            return ConfidenceScore(
                item_id=row["item_id"],
                item_type=row["item_type"],
                overall_score=row["overall_score"],
                source_reliability=row["source_reliability"],
                verification_history=row["verification_history"],
                recency=row["recency"],
                completeness=row["completeness"],
                consistency=row["consistency"],
                calculated_at=datetime.fromisoformat(row["calculated_at"]),
                factors=self._deserialize_dict(row["factors"]),
            )


def get_evidence_storage(db_path: Optional[str] = None) -> EvidenceStorage:
    """Get the singleton evidence storage instance."""
    global _storage_instance, _storage_lock
    if _storage_instance is None:
        with _storage_lock:
            if _storage_instance is None:
                _storage_instance = EvidenceStorage(db_path or "peoplepay-evidence.sqlite3")
    return _storage_instance
