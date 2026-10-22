"""
from typing import Any, Dict, List, Optional
Evidence Collector

Handles collection of evidence from various sources and formats.
"""

import hashlib
import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Union
from uuid import uuid4

from evidence.models import (
    EvidenceSource,
    EvidenceItem,
    EvidenceType,
    SourceType,
)
from evidence.storage import get_evidence_storage, EvidenceStorage
from evidence.errors import EvidenceError, SourceUnavailableError


# Singleton instance
_collector_instance: Optional["EvidenceCollector"] = None


class EvidenceCollector:
    """
    Collects evidence from various sources and stores it for verification.
    
    Supports:
    - Document ingestion
    - API response capture
    - Web page scraping (metadata only)
    - Database record extraction
    - User input recording
    - Calculation/estimation logging
    """
    
    def __init__(self, storage: Optional[EvidenceStorage] = None):
        """Initialize the evidence collector."""
        self.storage = storage or get_evidence_storage()
        self._registered_sources: Dict[str, EvidenceSource] = {}
    
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
        source = EvidenceSource(
            id=str(uuid4()),
            name=name,
            description=description,
            source_type=source_type,
            url=url,
            authority=authority,
            trust_score=trust_score,
            metadata=metadata,
        )
        self._registered_sources[source.id] = source
        self.storage.create_source(source)
        return source
    
    def get_source(self, source_id: str) -> Optional[EvidenceSource]:
        """Get a registered source by ID."""
        if source_id in self._registered_sources:
            return self._registered_sources[source_id]
        return self.storage.get_source(source_id)
    
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
        """
        Collect evidence from any source.
        
        Args:
            content: The actual evidence content (text, JSON, data)
            title: Human-readable title for this evidence
            evidence_type: Type of evidence being collected
            source_id: ID of the source this evidence came from
            collector: Who collected this evidence
            description: Optional description
            is_synthetic: Whether this is synthetic/test data
            synthetic_purpose: Purpose if synthetic
            tags: Tags for categorization
            **metadata: Additional metadata
            
        Returns:
            The stored EvidenceItem with generated ID and hash
        """
        # Compute hash of content
        content_str = str(content) if content is not None else ""
        hash_value = hashlib.sha256(content_str.encode()).hexdigest()
        
        evidence = EvidenceItem(
            id=str(uuid4()),
            title=title,
            description=description,
            content=content,
            evidence_type=evidence_type,
            source_id=source_id,
            collector=collector or "system",
            collected_at=datetime.utcnow(),
            version="1.0",
            hash_value=hash_value,
            is_synthetic=is_synthetic,
            synthetic_purpose=synthetic_purpose,
            tags=tags or [],
            metadata=metadata,
        )
        
        return self.storage.create_evidence(evidence)
    
    def collect_document(
        self,
        text: str,
        title: str,
        source_url: Optional[str] = None,
        source_name: Optional[str] = None,
        **kwargs: Any
    ) -> EvidenceItem:
        """Collect a document as evidence."""
        source_id = None
        if source_url or source_name:
            source = self.register_source(
                name=source_name or source_url or title,
                source_type=SourceType.PRIMARY,
                url=source_url,
            )
            source_id = source.id
        
        return self.collect(
            content=text,
            title=title,
            evidence_type=EvidenceType.DOCUMENT,
            source_id=source_id,
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
        source = self.register_source(
            name=source_name,
            source_type=SourceType.PRIMARY,
            url=endpoint,
        )
        
        return self.collect(
            content=response,
            title=f"API Response: {source_name}",
            evidence_type=EvidenceType.API_RESPONSE,
            source_id=source.id,
            collector="api_client",
            **kwargs
        )
    
    def collect_user_input(
        self,
        data: Any,
        user_id: str,
        input_type: str,
        **kwargs: Any
    ) -> EvidenceItem:
        """Collect user-provided input as evidence."""
        return self.collect(
            content=data,
            title=f"User Input: {input_type}",
            evidence_type=EvidenceType.USER_INPUT,
            collector=user_id,
            **kwargs
        )
    
    def collect_calculation(
        self,
        inputs: Dict[str, Any],
        output: Any,
        method: str,
        **kwargs: Any
    ) -> EvidenceItem:
        """Collect a calculation or estimation as evidence."""
        evidence_data = {
            "method": method,
            "inputs": inputs,
            "output": output,
            "timestamp": datetime.utcnow().isoformat(),
        }
        return self.collect(
            content=evidence_data,
            title=f"Calculation: {method}",
            evidence_type=EvidenceType.CALCULATION,
            collector="calculator",
            is_synthetic=False,  # Calculations are derived but not synthetic
            **kwargs
        )
    
    def collect_synthetic(
        self,
        data: Any,
        purpose: str,
        data_type: str = "test_data",
        **kwargs: Any
    ) -> EvidenceItem:
        """Collect synthetic/test data as evidence (clearly marked)."""
        return self.collect(
            content=data,
            title=f"Synthetic: {data_type}",
            evidence_type=EvidenceType.TEST_DATA,
            is_synthetic=True,
            synthetic_purpose=purpose,
            collector="test_system",
            **kwargs
        )
    
    def list_sources(self, limit: int = 100) -> List[EvidenceSource]:
        """List all registered sources."""
        return self.storage.list_sources(limit)
    
    def get_evidence(self, evidence_id: str) -> Optional[EvidenceItem]:
        """Get collected evidence by ID."""
        return self.storage.get_evidence(evidence_id)
    
    def list_evidence(self, limit: int = 100, offset: int = 0) -> List[EvidenceItem]:
        """List all collected evidence."""
        return self.storage.list_evidence(limit, offset)
    
    def verify_integrity(self, evidence_id: str) -> bool:
        """Verify the integrity of stored evidence."""
        evidence = self.get_evidence(evidence_id)
        if not evidence:
            raise EvidenceError(f"Evidence {evidence_id} not found", error_type="evidence_not_found")
        
        current_hash = self._compute_hash(evidence.content)
        return current_hash == evidence.hash_value
    
    def _compute_hash(self, content: Any) -> str:
        """Compute SHA256 hash of content."""
        content_str = str(content) if content is not None else ""
        return hashlib.sha256(content_str.encode()).hexdigest()


def get_evidence_collector() -> EvidenceCollector:
    """Get the singleton evidence collector instance."""
    global _collector_instance
    if _collector_instance is None:
        _collector_instance = EvidenceCollector()
    return _collector_instance
