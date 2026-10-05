"""Read-only InflationForge receipts; no upstream source or ranking is reused."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Literal
from urllib.parse import quote, urlencode, urlsplit

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from echo.extensions.contracts import (
    IDENTIFIER, MAX_COLLECTION_ITEMS, ClaimProposal, EntityProposal,
    EvidenceProposal, ExtensionHealth, ExtensionManifest, ExtensionRequest,
    ManifestAdapter, NormalizedResult, SourceProposal,
)
from echo.extensions.transport import ExtensionTransportError, ServiceTransport
from echo.models import stable_id


class _PriceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    snapshot_id: str = Field(pattern=IDENTIFIER)
    item_id: str = Field(pattern=IDENTIFIER)
    city_id: str = Field(pattern=IDENTIFIER)


class _PriceRow(BaseModel):
    """The inspected upstream receipt schema, with one optional capture field."""

    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    id: str = Field(pattern=IDENTIFIER)
    snapshot_id: str = Field(pattern=IDENTIFIER)
    city_id: str = Field(pattern=IDENTIFIER)
    item_id: str = Field(pattern=IDENTIFIER)
    year: int = Field(ge=2000, le=2100)
    price_usd: float | int = Field(gt=0, le=1_000_000_000)
    currency: Literal["USD"]
    kind: Literal["LIVE", "ARCHIVED"]
    raw_label: str = Field(min_length=1, max_length=180)
    raw_price: float | int = Field(gt=0, le=1_000_000_000)
    conversion_multiplier: float | int = Field(gt=0, le=100)
    source: Any = None
    source_url: Any = None
    observed_at: Any = None
    retrieved_at: Any = None
    archive_timestamp: str | None = Field(default=None, max_length=32)
    # This field is absent from the inspected ordinary upstream schema.
    # It is accepted only as an explicitly supplied publisher receipt hash.
    source_content_hash: str | None = Field(default=None, pattern=r"^[a-fA-F0-9]{64}$")


def _timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo is not None and parsed.utcoffset() is not None else None
    except ValueError:
        return None


def _source_url(value: Any) -> str | None:
    if not isinstance(value, str) or len(value) > 2000 or any(char.isspace() or ord(char) < 32 for char in value):
        return None
    try:
        parts = urlsplit(value)
        if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password:
            return None
        _ = parts.port  # Invalid ports are not valid source addresses.
        return value
    except ValueError:
        return None


def _amount_minor(value: float | int) -> int:
    if isinstance(value, bool):
        raise ValueError("prices must be numbers")
    amount = Decimal(str(value))
    if not amount.is_finite() or amount <= 0:
        raise ValueError("prices must be finite and positive")
    result = int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    if result <= 0:
        raise ValueError("price is below the minor-unit precision")
    return result


class InflationForgeAdapter(ManifestAdapter):
    """Supply observed city/item prices as proposals for ECHO core ingestion."""

    def __init__(self, manifest: ExtensionManifest) -> None:
        super().__init__(manifest)
        self.transport = ServiceTransport(manifest)

    async def _provider_warnings(self) -> list[str]:
        body = await self.transport.request(self.manifest.healthcheck.path)
        if not isinstance(body, dict) or body.get("status") != "ok":
            raise ExtensionTransportError("EXTENSION_UNAVAILABLE", "Price observation service is not healthy")
        modes = body.get("modes")
        provider = modes.get("price_provider") if isinstance(modes, dict) else None
        if not isinstance(provider, str) or not provider.strip() or len(provider) > 250:
            return ["PROVIDER_MODE_UNKNOWN"]
        if any(token in provider.upper() for token in ("FALLBACK", "LOCAL", "SAMPLE", "SANDBOX", "MOCK")):
            return ["PROVIDER_MODE_REQUIRES_REVIEW"]
        return []

    async def health(self) -> ExtensionHealth:
        warnings = await self._provider_warnings()
        return ExtensionHealth(
            extension_id=self.manifest.id, status="healthy",
            message="Reachable; provider provenance requires review" if warnings else "Price observation service reachable",
        )

    async def execute(self, request: ExtensionRequest) -> NormalizedResult:
        if request.capability != "price_intelligence":
            raise ExtensionTransportError("CAPABILITY_UNAVAILABLE", "This adapter provides scoped price observations")
        try:
            selected = _PriceRequest.model_validate(request.input)
        except ValidationError as exc:
            raise ExtensionTransportError("INVALID_INPUT", "Explicit snapshot, item and city identifiers are required") from exc
        warnings = await self._provider_warnings()
        provider_unknown = bool(warnings)
        path = f"/api/snapshots/{quote(selected.snapshot_id, safe='')}/observations?" + urlencode(
            {"city_id": selected.city_id, "item_id": selected.item_id}
        )
        raw_rows = await self.transport.request(path, expected_response="array")
        if not isinstance(raw_rows, list) or len(raw_rows) > MAX_COLLECTION_ITEMS:
            raise ExtensionTransportError("INVALID_OUTPUT", "Price observation response exceeds its reviewed schema")
        if not raw_rows:
            return NormalizedResult(
                extension_id=self.manifest.id, extension_version=self.manifest.version,
                status="partial", warnings=warnings + ["NOT_TRACKED_OR_NO_OBSERVATIONS"],
                raw_reference=f"inflationforge:snapshot:{selected.snapshot_id}",
            )
        entities: list[EntityProposal] = []
        sources: list[SourceProposal] = []
        claims: list[ClaimProposal] = []
        evidence: list[EvidenceProposal] = []
        seen: set[str] = set()
        for raw in raw_rows:
            try:
                row = _PriceRow.model_validate(raw)
                amount_minor = _amount_minor(row.price_usd)
                if (row.snapshot_id != selected.snapshot_id or row.item_id != selected.item_id
                        or row.city_id != selected.city_id or row.id in seen):
                    raise ValueError("out-of-scope or duplicate receipt")
                seen.add(row.id)
            except (ValidationError, ValueError, InvalidOperation, TypeError) as exc:
                raise ExtensionTransportError("INVALID_OUTPUT", "Price observation response failed its reviewed schema") from exc
            if isinstance(row.price_usd, float):
                warnings.append("UPSTREAM_FLOAT_AMOUNT_ROUNDED_TO_MINOR_UNITS")
            if row.kind == "ARCHIVED":
                warnings.append("HISTORICAL_OBSERVATION_NOT_CURRENT_QUOTE")
            observed = _timestamp(row.observed_at)
            retrieved = _timestamp(row.retrieved_at)
            address = _source_url(row.source_url)
            publisher = row.source if isinstance(row.source, str) and 0 < len(row.source) <= 200 else None
            known = bool(address and observed and retrieved and publisher and not provider_unknown)
            if retrieved and observed and retrieved < observed:
                known = False
                warnings.append("INVALID_SOURCE_TIMESTAMP_ORDER")
            now = datetime.now(timezone.utc)
            if any(timestamp and timestamp > now for timestamp in (observed, retrieved)):
                known = False
                warnings.append("FUTURE_SOURCE_TIMESTAMP")
            if not known:
                warnings.append("SOURCE_UNKNOWN")
            if not row.source_content_hash:
                warnings.append("PUBLISHER_CAPTURE_NOT_PROVIDED")
            else:
                warnings.append("SOURCE_CAPTURE_HASH_UPSTREAM_ASSERTED")
            provenance: Literal["KNOWN", "PROVENANCE_UNKNOWN"] = "KNOWN" if known else "PROVENANCE_UNKNOWN"
            ref = stable_id("receipt", row.id)
            entity_ref = stable_id("item", row.item_id)
            if not entities:
                entities.append(EntityProposal(ref=entity_ref, type="Product", name=selected.item_id,
                                               external_ids={"upstream_item_id": row.item_id}))
            source_ref, claim_ref = f"{ref}:source", f"{ref}:claim"
            sources.append(SourceProposal(
                ref=source_ref, url=address, publisher=publisher, title=row.raw_label,
                source_type="aggregator", upstream_document_id=row.id,
                observed_at=observed, original_observed_at=observed, retrieved_at=retrieved,
                cache_age_seconds=max(0.0, (retrieved - observed).total_seconds()) if observed and retrieved else None,
                content_hash=row.source_content_hash, provenance_state=provenance,
            ))
            # This excerpt describes a received structured receipt, not captured publisher text.
            excerpt = f"Upstream receipt {row.id}: {row.raw_label}; {row.price_usd} USD; year {row.year}; city {row.city_id}; kind {row.kind}."
            claims.append(ClaimProposal(
                ref=claim_ref, entity_ref=entity_ref, predicate="observed_price",
                text=f"InflationForge recorded {amount_minor} USD minor units for {row.item_id} in {row.city_id} during {row.year}.",
                value={"currency": "USD", "year": row.year, "city_id": row.city_id, "item_id": row.item_id,
                       "amount_minor": amount_minor, "observation_kind": row.kind,
                       "raw_label": row.raw_label, "raw_price": row.raw_price,
                       "conversion_multiplier": row.conversion_multiplier,
                       "archive_timestamp": row.archive_timestamp},
                kind="fact", confidence=None, provenance_state=provenance,
            ))
            evidence.append(EvidenceProposal(
                ref=f"{ref}:evidence", claim_ref=claim_ref, source_ref=source_ref, excerpt=excerpt,
                observed_at=observed, confidence=None, provenance_state=provenance,
            ))
        warnings.append("CITY_PRICE_OBSERVATION_NOT_SUPPLIER_QUOTE")
        unique_warnings = list(dict.fromkeys(warnings))
        return NormalizedResult(
            extension_id=self.manifest.id, extension_version=self.manifest.version,
            status="partial" if unique_warnings else "success", sources=sources, entities=entities,
            claims=claims, evidence=evidence, warnings=unique_warnings, confidence=None,
            raw_reference=f"inflationforge:snapshot:{selected.snapshot_id}",
        )
