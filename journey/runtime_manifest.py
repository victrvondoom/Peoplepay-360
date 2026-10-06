"""Host policy for SDK providers. Manifests describe code, never import it."""
from pathlib import Path
from typing import Literal

import yaml
from pydantic import Field, field_validator
from peoplepay_sdk.contracts import Contract, _CAPABILITY


class RuntimeManifest(Contract):
    schema_version: Literal["1"] = "1"
    id: str = Field(pattern=r"^[a-z][a-z0-9-]{0,63}$")
    version: str = Field(pattern=r"^\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)?$")
    integration_version: str = "1.0.0"
    runtime_type: Literal["HTTP_SERVICE", "LOCAL_LIBRARY"] = "LOCAL_LIBRARY"
    endpoint_env: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]*$")
    enabled: bool = True
    capabilities: dict[str, str] = Field(min_length=1, max_length=20)
    jurisdictions: list[str] = Field(min_length=1, max_length=100)
    input_fields: list[str] = Field(default_factory=list, max_length=100)
    constraint_fields: list[str] = Field(default_factory=list, max_length=100)
    permissions: list[str] = Field(default_factory=list, max_length=20)
    priority: int = Field(default=100, ge=0, le=1000)
    fallback_rank: int = Field(default=0, ge=0, le=1000)
    timeout_seconds: float = Field(default=15, ge=.01, le=60)
    max_concurrency: int = Field(default=2, ge=1, le=16)
    upstream: str = Field(min_length=1, max_length=500)
    license_reference: str = Field(min_length=1, max_length=500)
    readiness: Literal["DEMO", "EXPERIMENTAL", "SANDBOX", "BETA", "PRODUCTION_READY"] = "EXPERIMENTAL"

    @field_validator("capabilities")
    @classmethod
    def valid_capabilities(cls, value):
        if any(not _CAPABILITY.fullmatch(k) or not _CAPABILITY.fullmatch(v) for k, v in value.items()):
            raise ValueError("invalid capability identifier")
        return value

    @field_validator("jurisdictions")
    @classmethod
    def valid_jurisdictions(cls, value):
        import re
        if any(v != "*" and not re.fullmatch(r"[A-Z]{2}", v) for v in value):
            raise ValueError("jurisdictions require ISO country codes")
        return value

    @field_validator("permissions")
    @classmethod
    def permitted(cls, value):
        if set(value) - {"network.http", "workflow.context", "echo.read_limited", "transaction.reference.read"}:
            raise ValueError("PERMISSION_DENIED: unsupported provider authority")
        return value


def load_manifests(directory):
    root = Path(directory).resolve(strict=True)
    accepted, rejected = {}, {}
    for path in sorted(root.glob("*/runtime.yaml")):
        try:
            if path.is_symlink() or path.parent.is_symlink() or not path.resolve().is_relative_to(root):
                raise ValueError("manifest escapes configured directory")
            if path.stat().st_size > 32768 or len(accepted) >= 64:
                raise ValueError("manifest limit exceeded")
            manifest = RuntimeManifest.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
            if manifest.id != path.parent.name or manifest.id in accepted:
                raise ValueError("duplicate or mismatched extension id")
            accepted[manifest.id] = manifest
        except Exception:
            rejected[path.parent.name] = {"status": "INVALID_CONFIGURATION"}
    return accepted, rejected
