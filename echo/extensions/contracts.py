"""ECHO extension API v1: bounded proposals, never canonical graph mutations."""

from __future__ import annotations

import json
import math
import re
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal, Protocol
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

API_VERSION = "1"
MAX_REQUEST_BYTES = 65_536
MAX_RESULT_BYTES = 262_144
MAX_COLLECTION_ITEMS = 100
IDENTIFIER = r"^[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,127}$"
CAPABILITY = r"^[a-z][a-z0-9_]{0,63}$"
SECRET_KEYS = re.compile(r"^(authorization|password|secret|api_key|access_token|refresh_token|bearer_token|private_key|graph_password)$", re.I)


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True, allow_inf_nan=False)


def validate_json(value: Any, *, maximum_bytes: int) -> Any:
    """Reject non-JSON objects, excessive nesting and credential-bearing envelopes."""
    def visit(item: Any, depth: int) -> None:
        if depth > 12:
            raise ValueError("JSON envelope exceeds the nesting limit")
        if isinstance(item, dict):
            if len(item) > 100:
                raise ValueError("JSON object has too many fields")
            for key, child in item.items():
                if not isinstance(key, str) or len(key) > 128:
                    raise ValueError("JSON object keys must be bounded strings")
                if SECRET_KEYS.fullmatch(key):
                    raise ValueError("credentials must not appear in extension envelopes")
                visit(child, depth + 1)
        elif isinstance(item, list):
            if len(item) > MAX_COLLECTION_ITEMS:
                raise ValueError("JSON array has too many items")
            for child in item:
                visit(child, depth + 1)
        elif isinstance(item, str):
            if len(item) > 16_384 or "\x00" in item:
                raise ValueError("JSON strings must be bounded and contain no null bytes")
        elif isinstance(item, float):
            if not math.isfinite(item):
                raise ValueError("JSON numbers must be finite")
        elif item is not None and not isinstance(item, (bool, int)):
            raise ValueError("extension envelopes must contain JSON values only")
    visit(value, 0)
    if len(json.dumps(value, allow_nan=False, separators=(",", ":")).encode("utf-8")) > maximum_bytes:
        raise ValueError("extension envelope exceeds the byte limit")
    return value


def aware_time(value: datetime | None) -> datetime | None:
    if value is not None and (value.tzinfo is None or value.utcoffset() is None):
        raise ValueError("timestamps must include an explicit timezone")
    return value


def contains_secret(value: Any, secrets: list[str]) -> bool:
    """Check decoded strings, so JSON escaping cannot hide a credential echo."""
    if isinstance(value, str):
        return any(secret in value for secret in secrets if secret)
    if isinstance(value, dict):
        return any(contains_secret(key, secrets) or contains_secret(item, secrets) for key, item in value.items())
    if isinstance(value, list):
        return any(contains_secret(item, secrets) for item in value)
    return False


class ExtensionCategory(StrEnum):
    SOURCE_DISCOVERY = "SOURCE_DISCOVERY"
    SUPPLIER_DISCOVERY = "SUPPLIER_DISCOVERY"
    PRICE_INTELLIGENCE = "PRICE_INTELLIGENCE"
    SUSTAINABILITY_INTELLIGENCE = "SUSTAINABILITY_INTELLIGENCE"
    ENTITY_RESOLUTION = "ENTITY_RESOLUTION"
    DOCUMENT_INGESTION = "DOCUMENT_INGESTION"
    CLAIM_EXTRACTION = "CLAIM_EXTRACTION"
    EVIDENCE_VERIFICATION = "EVIDENCE_VERIFICATION"
    PROVENANCE_ANALYSIS = "PROVENANCE_ANALYSIS"
    CONTRADICTION_DETECTION = "CONTRADICTION_DETECTION"
    TEMPORAL_MONITORING = "TEMPORAL_MONITORING"
    RISK_ANALYSIS = "RISK_ANALYSIS"
    LOGISTICS_ANALYSIS = "LOGISTICS_ANALYSIS"
    POLICY_ENGINE = "POLICY_ENGINE"
    OPTIMIZATION = "OPTIMIZATION"
    GRAPH_ANALYTICS = "GRAPH_ANALYTICS"
    AGENT_TOOL = "AGENT_TOOL"
    MEMORY_PROVIDER = "MEMORY_PROVIDER"
    SEARCH_PROVIDER = "SEARCH_PROVIDER"
    RERANKER = "RERANKER"
    GEOSPATIAL = "GEOSPATIAL"
    OBSERVABILITY = "OBSERVABILITY"
    DISPUTE_ASSISTANCE = "DISPUTE_ASSISTANCE"
    VISUALIZATION = "VISUALIZATION"
    DATA_CONNECTOR = "DATA_CONNECTOR"


class UpstreamMetadata(ContractModel):
    repository: str | None = Field(default=None, max_length=500)
    commit: str | None = Field(default=None, max_length=128)


class LicenseMetadata(ContractModel):
    spdx: str = Field(default="LICENSE_UNKNOWN", max_length=128)
    notice_required: bool = False
    source_reused: bool = False


class RuntimeConfig(ContractModel):
    mode: Literal["builtin", "service"]
    language: str = Field(default="python", max_length=64)
    url_env: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]{0,127}$")
    allowed_hosts: list[str] = Field(default_factory=list, max_length=20)
    auth_secret_env: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]{0,127}$")
    timeout_seconds: float = Field(default=8, ge=0.01, le=60)
    max_concurrency: int = Field(default=2, ge=1, le=16)
    max_failures: int = Field(default=3, ge=1, le=20)
    cooldown_seconds: float = Field(default=30, ge=0.01, le=3600)

    @field_validator("allowed_hosts")
    @classmethod
    def hosts_are_literal(cls, values: list[str]) -> list[str]:
        for value in values:
            if not value or any(char in value for char in "/@?#*") or value != value.strip():
                raise ValueError("allowed hosts must be literal hostnames or IP addresses")
        return [value.lower() for value in values]


class ExtensionPermissions(ContractModel):
    network: bool = False
    filesystem: bool = False
    subprocess: bool = False


class GraphPermissions(ContractModel):
    read: list[str] = Field(default_factory=list, max_length=20)
    write: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("read", "write")
    @classmethod
    def permitted_labels(cls, values: list[str]) -> list[str]:
        permitted = {"Requirement", "Supplier", "Product", "Organization", "Place", "Claim", "Evidence", "Source"}
        if set(values) - permitted:
            raise ValueError("manifest requests a graph label outside the proposal boundary")
        return values


class HealthcheckConfig(ContractModel):
    path: str = Field(default="/health", max_length=200)

    @field_validator("path")
    @classmethod
    def relative_path(cls, value: str) -> str:
        if not value.startswith("/") or value.startswith("//") or ".." in value or "?" in value or "#" in value:
            raise ValueError("healthcheck path must be a fixed absolute service path")
        return value


class ExtensionManifest(ContractModel):
    schema_version: Literal["1"] = "1"
    id: str = Field(pattern=r"^[a-z][a-z0-9-]{0,63}$")
    name: str = Field(min_length=1, max_length=160)
    version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][a-zA-Z0-9.-]+)?$")
    type: ExtensionCategory
    enabled: bool = False
    priority: int = Field(default=100, ge=0, le=1000)
    upstream: UpstreamMetadata = Field(default_factory=UpstreamMetadata)
    license: LicenseMetadata = Field(default_factory=LicenseMetadata)
    runtime: RuntimeConfig
    capabilities: list[str] = Field(min_length=1, max_length=20)
    permissions: ExtensionPermissions = Field(default_factory=ExtensionPermissions)
    graph: GraphPermissions = Field(default_factory=GraphPermissions)
    secrets: list[str] = Field(default_factory=list, max_length=10)
    healthcheck: HealthcheckConfig = Field(default_factory=HealthcheckConfig)
    dependencies: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("capabilities")
    @classmethod
    def valid_capabilities(cls, values: list[str]) -> list[str]:
        if len(set(values)) != len(values) or any(not re.fullmatch(CAPABILITY, value) for value in values):
            raise ValueError("capabilities must be unique bounded identifiers")
        return values

    @field_validator("secrets")
    @classmethod
    def valid_secrets(cls, values: list[str]) -> list[str]:
        if any(not re.fullmatch(r"[A-Z][A-Z0-9_]{0,127}", value) for value in values):
            raise ValueError("secrets must identify specific environment variables")
        return values

    @model_validator(mode="after")
    def supported_permissions(self) -> "ExtensionManifest":
        if self.permissions.filesystem or self.permissions.subprocess:
            raise ValueError("this platform does not enable filesystem or subprocess adapters")
        if self.runtime.mode == "service" and not self.permissions.network:
            raise ValueError("service adapters require explicit network permission")
        if self.runtime.mode == "builtin" and self.permissions.network:
            raise ValueError("builtin adapters cannot request service network permission")
        if self.runtime.auth_secret_env and self.runtime.auth_secret_env not in self.secrets:
            raise ValueError("service authentication secret must be declared in secrets")
        if self.id in self.dependencies:
            raise ValueError("an extension cannot depend on itself")
        if self.license.source_reused and self.license.spdx == "LICENSE_UNKNOWN":
            raise ValueError("unlicensed upstream source cannot be reused")
        return self


class ExtensionContext(ContractModel):
    requirement_id: str | None = Field(default=None, pattern=IDENTIFIER)
    user_id: str | None = Field(default=None, min_length=1, max_length=128)


class ExtensionRequest(ContractModel):
    schema_version: Literal["1"] = "1"
    request_id: str = Field(pattern=IDENTIFIER)
    capability: str = Field(pattern=CAPABILITY)
    context: ExtensionContext = Field(default_factory=ExtensionContext)
    input: dict[str, Any] = Field(default_factory=dict)
    constraints: dict[str, Any] = Field(default_factory=dict)
    trace: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def bounded_request(self) -> "ExtensionRequest":
        validate_json({"input": self.input, "constraints": self.constraints, "trace": self.trace}, maximum_bytes=MAX_REQUEST_BYTES)
        validate_json(self.model_dump(mode="json"), maximum_bytes=MAX_REQUEST_BYTES)
        return self


class SourceProposal(ContractModel):
    ref: str = Field(pattern=IDENTIFIER)
    url: str | None = Field(default=None, max_length=2000)
    publisher: str | None = Field(default=None, max_length=200)
    title: str | None = Field(default=None, max_length=500)
    source_type: str = Field(default="internal", max_length=64)
    upstream_document_id: str | None = Field(default=None, max_length=256)
    provenance_state: Literal["KNOWN", "PROVENANCE_UNKNOWN"] = "PROVENANCE_UNKNOWN"
    published_at: datetime | None = None
    observed_at: datetime | None = None
    original_observed_at: datetime | None = None
    retrieved_at: datetime | None = None
    cache_age_seconds: float | None = Field(default=None, ge=0)
    content_hash: str | None = Field(default=None, pattern=r"^[a-fA-F0-9]{64}$")
    snapshot_text: str | None = Field(default=None, max_length=1200)

    _timestamps = field_validator("published_at", "observed_at", "original_observed_at", "retrieved_at")(aware_time)

    @field_validator("url")
    @classmethod
    def source_address(cls, value: str | None) -> str | None:
        if value is None:
            return value
        parts = urlsplit(value)
        if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password:
            raise ValueError("source URL must use HTTP(S) and contain no credentials")
        return value

    @model_validator(mode="after")
    def known_source_has_provenance(self) -> "SourceProposal":
        if self.provenance_state == "KNOWN" and (not (self.url or self.upstream_document_id) or self.observed_at is None):
            raise ValueError("known sources require an address or document id and observed_at")
        if self.cache_age_seconds is not None and (self.original_observed_at is None or self.retrieved_at is None):
            raise ValueError("cached sources require original and retrieval timestamps")
        return self


class EntityProposal(ContractModel):
    ref: str = Field(pattern=IDENTIFIER)
    type: Literal["Supplier", "Product", "Organization", "Place"]
    name: str = Field(min_length=1, max_length=200)
    external_ids: dict[str, str] = Field(default_factory=dict, max_length=10)


class ClaimProposal(ContractModel):
    ref: str = Field(pattern=IDENTIFIER)
    entity_ref: str = Field(pattern=IDENTIFIER)
    text: str = Field(min_length=1, max_length=1200)
    predicate: str = Field(pattern=CAPABILITY)
    value: Any = None
    kind: Literal["fact", "estimate", "inference", "model_output"]
    confidence: float | None = Field(default=None, ge=0, le=1)
    provenance_state: Literal["KNOWN", "PROVENANCE_UNKNOWN"] = "PROVENANCE_UNKNOWN"

    @field_validator("value")
    @classmethod
    def bounded_value(cls, value: Any) -> Any:
        return validate_json(value, maximum_bytes=16_384)


class EvidenceProposal(ContractModel):
    ref: str = Field(pattern=IDENTIFIER)
    claim_ref: str = Field(pattern=IDENTIFIER)
    source_ref: str | None = Field(default=None, pattern=IDENTIFIER)
    excerpt: str = Field(min_length=1, max_length=1200)
    observed_at: datetime | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    content_hash: str | None = Field(default=None, pattern=r"^[a-fA-F0-9]{64}$")
    provenance_state: Literal["KNOWN", "PROVENANCE_UNKNOWN"] = "PROVENANCE_UNKNOWN"
    active: bool = True

    _timestamps = field_validator("observed_at", "valid_from", "valid_until")(aware_time)

    @model_validator(mode="after")
    def temporal_and_provenance_rules(self) -> "EvidenceProposal":
        if self.provenance_state == "KNOWN" and (self.source_ref is None or self.observed_at is None):
            raise ValueError("known evidence requires source_ref and observed_at")
        if self.valid_from and self.valid_until and self.valid_until < self.valid_from:
            raise ValueError("evidence validity ends before it begins")
        return self


class SourceDependency(ContractModel):
    from_source_ref: str = Field(pattern=IDENTIFIER)
    to_source_ref: str = Field(pattern=IDENTIFIER)
    type: Literal["DERIVED_FROM", "CITES", "MIRRORS"]
    evidence_mode: Literal["explicit", "inferred"] = "explicit"
    confidence: float | None = Field(default=None, ge=0, le=1)
    explanation: str = Field(min_length=1, max_length=500)


class ObservationProposal(ContractModel):
    ref: str = Field(pattern=IDENTIFIER)
    entity_ref: str | None = Field(default=None, pattern=IDENTIFIER)
    text: str = Field(min_length=1, max_length=1200)
    kind: Literal["fact", "estimate", "inference", "model_output"]
    observed_at: datetime | None = None
    source_ref: str | None = Field(default=None, pattern=IDENTIFIER)
    confidence: float | None = Field(default=None, ge=0, le=1)

    _timestamp = field_validator("observed_at")(aware_time)


class ModelProvenance(ContractModel):
    provider: str | None = Field(default=None, max_length=128)
    model: str | None = Field(default=None, max_length=128)
    generated_at: datetime | None = None
    prompt_version: str | None = Field(default=None, max_length=128)

    _timestamp = field_validator("generated_at")(aware_time)


class NormalizedResult(ContractModel):
    schema_version: Literal["1"] = "1"
    extension_id: str = Field(pattern=r"^[a-z][a-z0-9-]{0,63}$")
    extension_version: str = Field(max_length=100)
    status: Literal["success", "partial"] = "success"
    sources: list[SourceProposal] = Field(default_factory=list, max_length=MAX_COLLECTION_ITEMS)
    entities: list[EntityProposal] = Field(default_factory=list, max_length=MAX_COLLECTION_ITEMS)
    claims: list[ClaimProposal] = Field(default_factory=list, max_length=MAX_COLLECTION_ITEMS)
    evidence: list[EvidenceProposal] = Field(default_factory=list, max_length=MAX_COLLECTION_ITEMS)
    source_dependencies: list[SourceDependency] = Field(default_factory=list, max_length=MAX_COLLECTION_ITEMS)
    observations: list[ObservationProposal] = Field(default_factory=list, max_length=MAX_COLLECTION_ITEMS)
    warnings: list[str] = Field(default_factory=list, max_length=30)
    confidence: float | None = Field(default=None, ge=0, le=1)
    raw_reference: str | None = Field(default=None, max_length=500)
    model_provenance: ModelProvenance | None = None

    @model_validator(mode="after")
    def valid_proposals(self) -> "NormalizedResult":
        validate_json(self.model_dump(mode="json"), maximum_bytes=MAX_RESULT_BYTES)
        indices: dict[str, dict[str, Any]] = {}
        for field in ("sources", "entities", "claims", "evidence", "observations"):
            records = getattr(self, field)
            index = {record.ref: record for record in records}
            if len(index) != len(records):
                raise ValueError(f"duplicate {field} reference")
            indices[field] = index
        for claim in self.claims:
            if claim.entity_ref not in indices["entities"]:
                raise ValueError("claim references an entity absent from its result")
            supports = [item for item in self.evidence if item.claim_ref == claim.ref]
            if claim.provenance_state == "KNOWN" and not any(item.provenance_state == "KNOWN" for item in supports):
                raise ValueError("known claims must have known supporting evidence")
        for evidence in self.evidence:
            if evidence.claim_ref not in indices["claims"] or (evidence.source_ref and evidence.source_ref not in indices["sources"]):
                raise ValueError("evidence references a missing claim or source")
            if evidence.provenance_state == "KNOWN" and (not evidence.source_ref or indices["sources"][evidence.source_ref].provenance_state != "KNOWN"):
                raise ValueError("known evidence cannot rely on unknown source provenance")
        adjacency: dict[str, list[str]] = {}
        for dependency in self.source_dependencies:
            if dependency.from_source_ref not in indices["sources"] or dependency.to_source_ref not in indices["sources"]:
                raise ValueError("dependency references a source absent from its result")
            adjacency.setdefault(dependency.from_source_ref, []).append(dependency.to_source_ref)
        visited: set[str] = set()
        visiting: set[str] = set()
        def visit(ref: str) -> None:
            if ref in visiting:
                raise ValueError("source dependency proposals must not contain cycles")
            if ref in visited:
                return
            visiting.add(ref)
            for upstream in adjacency.get(ref, []):
                visit(upstream)
            visiting.remove(ref)
            visited.add(ref)
        for ref in adjacency:
            visit(ref)
        for observation in self.observations:
            if observation.entity_ref and observation.entity_ref not in indices["entities"]:
                raise ValueError("observation references a missing entity")
            if observation.source_ref and observation.source_ref not in indices["sources"]:
                raise ValueError("observation references a missing source")
        return self


class ExtensionError(ContractModel):
    code: Literal["EXTENSION_DISABLED", "EXTENSION_UNAVAILABLE", "EXTENSION_TIMEOUT", "INVALID_INPUT", "INVALID_OUTPUT", "CAPABILITY_UNAVAILABLE", "DEPENDENCY_UNAVAILABLE", "PERMISSION_DENIED", "CIRCUIT_OPEN", "RATE_LIMITED", "AUTH_REQUIRED", "CONFIGURATION_REQUIRED"]
    message: str = Field(min_length=1, max_length=200)


class ExtensionHealth(ContractModel):
    extension_id: str
    status: Literal["healthy", "unavailable", "disabled", "unconfigured", "circuit_open"]
    message: str = Field(default="", max_length=200)


class ExtensionExecution(ContractModel):
    run_id: str
    request_id: str
    capability: str
    extension_id: str | None
    extension_version: str | None
    status: Literal["success", "partial", "error"]
    result: NormalizedResult | None = None
    error: ExtensionError | None = None
    started_at: datetime
    finished_at: datetime
    duration_ms: float
    input_bytes: int = 0
    output_count: int = 0


class ExtensionAdapter(Protocol):
    def metadata(self) -> dict[str, Any]: ...
    def capabilities(self) -> list[str]: ...
    async def health(self) -> ExtensionHealth: ...
    async def execute(self, request: ExtensionRequest) -> NormalizedResult | dict[str, Any]: ...


class ManifestAdapter:
    """Metadata helpers for core-reviewed adapters; no upstream code loading."""

    def __init__(self, manifest: ExtensionManifest) -> None:
        self.manifest = manifest

    def metadata(self) -> dict[str, Any]:
        return self.manifest.model_dump(mode="json", exclude={"secrets"})

    def capabilities(self) -> list[str]:
        return list(self.manifest.capabilities)

    async def health(self) -> ExtensionHealth:
        return ExtensionHealth(extension_id=self.manifest.id, status="healthy")
