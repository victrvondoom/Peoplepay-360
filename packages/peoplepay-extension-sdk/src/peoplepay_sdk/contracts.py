"""SDK v1 contracts. Provider output remains a proposal until ECHO reviews it."""

from __future__ import annotations

import json
import math
import re
from datetime import datetime
from typing import Any, Literal, Protocol
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

API_VERSION = "1"
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_CAPABILITY = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_SECRET = re.compile(r"^(authorization|password|secret|api_key|access_token|refresh_token|bearer_token|private_key)$", re.I)


def _bounded_json(value: Any, *, maximum_bytes: int = 262_144) -> Any:
    def visit(item: Any, depth: int) -> None:
        if depth > 12:
            raise ValueError("JSON exceeds maximum nesting")
        if isinstance(item, dict):
            if len(item) > 100:
                raise ValueError("JSON object has too many fields")
            for key, child in item.items():
                if not isinstance(key, str) or len(key) > 128 or _SECRET.fullmatch(key):
                    raise ValueError("invalid key or credential in extension envelope")
                visit(child, depth + 1)
        elif isinstance(item, list):
            if len(item) > 100:
                raise ValueError("JSON array has too many items")
            for child in item:
                visit(child, depth + 1)
        elif isinstance(item, str):
            if len(item) > 16_384 or "\x00" in item:
                raise ValueError("JSON string is too large or contains a null byte")
        elif isinstance(item, float):
            if not math.isfinite(item):
                raise ValueError("JSON numbers must be finite")
        elif item is not None and not isinstance(item, (bool, int)):
            raise ValueError("value is not JSON-compatible")

    visit(value, 0)
    if len(json.dumps(value, allow_nan=False, separators=(",", ":")).encode()) > maximum_bytes:
        raise ValueError("extension envelope exceeds byte limit")
    return value


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Capability(Contract):
    name: str = Field(pattern=_CAPABILITY.pattern)
    description: str = Field(min_length=1, max_length=500)
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)


class ExtensionMetadata(Contract):
    schema_version: Literal["1"] = API_VERSION
    id: str = Field(pattern=r"^[a-z][a-z0-9-]{0,63}$")
    name: str = Field(min_length=1, max_length=160)
    version: str = Field(pattern=r"^\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)?$")
    description: str = Field(min_length=1, max_length=1000)
    capabilities: list[Capability] = Field(min_length=1, max_length=20)
    homepage: str | None = Field(default=None, max_length=500)

    @field_validator("homepage")
    @classmethod
    def safe_homepage(cls, value: str | None) -> str | None:
        if value is None:
            return value
        parts = urlsplit(value)
        if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password:
            raise ValueError("homepage must be an HTTP(S) URL without credentials")
        return value

    @model_validator(mode="after")
    def unique_capabilities(self) -> "ExtensionMetadata":
        names = [cap.name for cap in self.capabilities]
        if len(set(names)) != len(names):
            raise ValueError("capability names must be unique")
        return self


class ExtensionContext(Contract):
    tenant_id: str | None = Field(default=None, max_length=128)
    user_id: str | None = Field(default=None, max_length=128)
    transaction_id: str | None = Field(default=None, max_length=128)
    locale: str | None = Field(default=None, max_length=32)
    trace_id: str = Field(min_length=1, max_length=128)


class ExtensionRequest(Contract):
    schema_version: Literal["1"] = API_VERSION
    request_id: str = Field(pattern=_IDENTIFIER.pattern)
    capability: str = Field(pattern=_CAPABILITY.pattern)
    context: ExtensionContext
    input: dict[str, Any] = Field(default_factory=dict)
    constraints: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def bounded(self) -> "ExtensionRequest":
        _bounded_json(self.model_dump(mode="json"), maximum_bytes=65_536)
        return self


class Entity(Contract):
    id: str = Field(pattern=_IDENTIFIER.pattern)
    entity_type: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    identifiers: dict[str, str] = Field(default_factory=dict, max_length=10)
    attributes: dict[str, Any] = Field(default_factory=dict)


class Evidence(Contract):
    id: str = Field(pattern=_IDENTIFIER.pattern)
    source_uri: str | None = Field(default=None, max_length=2000)
    source_name: str | None = Field(default=None, max_length=200)
    excerpt: str = Field(min_length=1, max_length=1200)
    observed_at: datetime | None = None
    content_hash: str | None = Field(default=None, pattern=r"^[a-fA-F0-9]{64}$")
    provenance_state: Literal["known", "unknown"] = "unknown"
    uncertainty: str | None = Field(default=None, max_length=500)

    @field_validator("source_uri")
    @classmethod
    def safe_source_uri(cls, value: str | None) -> str | None:
        if value is None:
            return value
        parts = urlsplit(value)
        if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password:
            raise ValueError("evidence source must be an HTTP(S) URL without credentials")
        return value

    @model_validator(mode="after")
    def provenance_is_explicit(self) -> "Evidence":
        if self.provenance_state == "known" and (not self.source_uri or not self.observed_at):
            raise ValueError("known evidence requires a source URI and timezone-aware observation time")
        if self.observed_at and (self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None):
            raise ValueError("evidence timestamps must include a timezone")
        return self


class ActionProposal(Contract):
    id: str = Field(pattern=_IDENTIFIER.pattern)
    action_type: str = Field(min_length=1, max_length=64)
    summary: str = Field(min_length=1, max_length=500)
    parameters: dict[str, Any] = Field(default_factory=dict)
    requires_human_approval: bool = True


class ExtensionHealth(Contract):
    extension_id: str
    status: Literal["healthy", "degraded", "unavailable"]
    checked_at: datetime
    message: str = Field(default="", max_length=200)

    @model_validator(mode="after")
    def timezone_required(self) -> "ExtensionHealth":
        if self.checked_at.tzinfo is None or self.checked_at.utcoffset() is None:
            raise ValueError("health timestamps must include a timezone")
        return self


class PeoplePayEvent(Contract):
    """Versioned service-to-service event; transport and durable outbox are host-owned."""

    schema_version: Literal["1"] = API_VERSION
    event_id: str = Field(pattern=_IDENTIFIER.pattern)
    event_type: str = Field(pattern=r"^[a-z][a-z0-9_.-]{0,127}$")
    occurred_at: datetime
    producer: str = Field(pattern=r"^[a-z][a-z0-9-]{0,63}$")
    subject_id: str = Field(min_length=1, max_length=128)
    correlation_id: str = Field(min_length=1, max_length=128)
    actor_id: str = Field(min_length=1, max_length=128)
    payload: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def bounded_event(self) -> "PeoplePayEvent":
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise ValueError("event time must include a timezone")
        _bounded_json(self.model_dump(mode="json"), maximum_bytes=65_536)
        return self


class ExtensionResult(Contract):
    schema_version: Literal["1"] = API_VERSION
    request_id: str = Field(pattern=_IDENTIFIER.pattern)
    extension_id: str = Field(pattern=r"^[a-z][a-z0-9-]{0,63}$")
    extension_version: str
    status: Literal["success", "partial"]
    entities: list[Entity] = Field(default_factory=list, max_length=100)
    evidence: list[Evidence] = Field(default_factory=list, max_length=100)
    action_proposals: list[ActionProposal] = Field(default_factory=list, max_length=100)
    raw_result: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list, max_length=30)
    confidence: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def bounded_result(self) -> "ExtensionResult":
        ids = [item.id for group in (self.entities, self.evidence, self.action_proposals) for item in group]
        if len(ids) != len(set(ids)):
            raise ValueError("result object ids must be unique")
        _bounded_json(self.model_dump(mode="json"))
        return self


class Extension(Protocol):
    """A provider implements methods; the host owns loading and permissions."""

    def metadata(self) -> ExtensionMetadata: ...
    def capabilities(self) -> list[Capability]: ...
    async def health(self) -> ExtensionHealth: ...
    async def execute(self, request: ExtensionRequest) -> ExtensionResult: ...


class ProviderRegistry:
    """Explicit in-process registrations; manifests never trigger code loading."""

    def __init__(self) -> None:
        self._providers: dict[str, Extension] = {}

    def register(self, provider: Extension) -> None:
        metadata = ExtensionMetadata.model_validate(provider.metadata().model_dump(mode="json"))
        if metadata.id in self._providers:
            raise ValueError("extension id is already registered")
        if len(self._providers) >= 64:
            raise ValueError("provider registry limit reached")
        advertised = {item.name for item in metadata.capabilities}
        implemented = {item.name for item in provider.capabilities()}
        if not advertised or advertised != implemented:
            raise ValueError("provider capability implementation must match its metadata")
        self._providers[metadata.id] = provider

    def get(self, extension_id: str) -> Extension:
        return self._providers[extension_id]

    def providers_for(self, capability: str) -> list[Extension]:
        return [provider for provider in self._providers.values()
                if capability in {item.name for item in provider.capabilities()}]
