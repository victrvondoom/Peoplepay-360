"""Validated ECHO records. IDs are stable identifiers, not display labels."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from hashlib import sha256
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import BaseModel, Field, HttpUrl


class SourceType(StrEnum):
    MANUFACTURER = "manufacturer"
    SUPPLIER = "supplier"
    MARKETPLACE = "marketplace"
    GOVERNMENT = "government"
    STANDARDS_BODY = "standards_body"
    CERTIFICATION_BODY = "certification_body"
    JOURNALISTIC = "journalistic"
    AGGREGATOR = "aggregator"
    BLOG = "blog"
    AI_GENERATED = "ai_generated"
    INTERNAL = "internal"
    SYNTHETIC_DEMO = "synthetic_demo"


class DependencyType(StrEnum):
    DERIVED_FROM = "DERIVED_FROM"
    CITES = "CITES"
    MIRRORS = "MIRRORS"


class Requirement(BaseModel):
    id: str
    user_id: str
    description: str = Field(min_length=1, max_length=1000)
    quantity: int = Field(gt=0, le=100000)
    budget_minor: int | None = Field(default=None, ge=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    delivery_days: int | None = Field(default=None, gt=0, le=3650)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Source(BaseModel):
    id: str
    source_url: HttpUrl | None = None
    publisher: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=500)
    source_type: SourceType
    published_at: datetime | None = None
    observed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    content_hash: str | None = None
    snapshot_text: str | None = Field(default=None, max_length=1200)
    demo_scope: str | None = None
    active: bool = True


class Evidence(BaseModel):
    id: str
    claim_id: str
    source_id: str
    agent_run_id: str
    observed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    confidence: float = Field(ge=0, le=1)
    verification_state: str = "UNVERIFIED"
    excerpt: str = Field(min_length=1, max_length=1200)
    content_hash: str
    active: bool = True


def normalize_source_url(value: str) -> str:
    """Canonicalize URL host/path and tracking noise without fetching it."""
    parts = urlsplit(value.strip())
    if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
        raise ValueError("source URL must be an absolute HTTP(S) URL")
    host = parts.hostname.lower()
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    port = parts.port
    if port and not ((parts.scheme.lower() == "http" and port == 80)
                     or (parts.scheme.lower() == "https" and port == 443)):
        host = f"{host}:{port}"
    path = parts.path.rstrip("/") or "/"
    tracking_prefixes = ("utm_",)
    query = urlencode(sorted((key, val) for key, val in parse_qsl(parts.query)
                             if not key.lower().startswith(tracking_prefixes)))
    return urlunsplit((parts.scheme.lower(), host, path, query, ""))


def stable_id(kind: str, *parts: str) -> str:
    material = "\x1f".join((kind, *parts))
    return f"{kind}_{sha256(material.encode('utf-8')).hexdigest()[:24]}"


def text_hash(value: str) -> str:
    normalized = " ".join(value.split())
    return sha256(normalized.encode("utf-8")).hexdigest()
