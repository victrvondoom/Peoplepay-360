"""Translate SDK observations into ECHO proposals without assigning trust."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Literal
from urllib.parse import urlsplit

from peoplepay_sdk import ExtensionResult

from echo.extensions.contracts import (
    ClaimProposal, EntityProposal, EvidenceProposal, ExtensionManifest,
    NormalizedResult, SourceProposal,
)


def reviewed_manifest(extension_id: str) -> ExtensionManifest:
    """Ingestion permissions for two fixed, reviewed adapters; never loads code.

    Invocation uses the independently configured SDK service client. Builtin
    here identifies this local translation step, which itself performs no IO.
    """
    catalog = {
        "greenchain": ("GreenChain SDK observations", "SUPPLIER_DISCOVERY", "supplier_discovery", "LICENSE_UNKNOWN"),
        "inflationforge": ("InflationForge SDK observations", "PRICE_INTELLIGENCE", "price_intelligence", "MIT"),
    }
    if extension_id not in catalog:
        raise ValueError("journey adapter has not been reviewed")
    name, category, capability, license_id = catalog[extension_id]
    return ExtensionManifest.model_validate({
        "schema_version": "1", "id": extension_id, "name": name, "version": "1.0.0",
        "type": category, "enabled": True, "runtime": {"mode": "builtin"},
        "license": {"spdx": license_id, "source_reused": False,
                    "notice_required": extension_id == "inflationforge"},
        "capabilities": [capability], "graph": {"read": [], "write": ["Supplier", "Product", "Claim", "Evidence", "Source"]},
    })


def _time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("receipt timestamps must carry a timezone")
    return result


def to_echo_result(result: ExtensionResult) -> NormalizedResult:
    result = ExtensionResult.model_validate(result.model_dump(mode="json"))
    reviewed_manifest(result.extension_id)
    received_at = _time(result.raw_result.get("received_at"))
    reference = result.raw_result.get("mode") == "reference"
    evidence_index = {item.id: item for item in result.evidence}
    known: dict[str, bool] = {}
    sources: list[SourceProposal] = []
    for item in result.evidence:
        source_ref = "src-" + item.id
        synthetic_address = bool(item.source_uri and (urlsplit(item.source_uri).hostname or "").endswith(".example"))
        known[item.id] = item.provenance_state == "known" and not reference and not synthetic_address
        sources.append(SourceProposal(
            ref=source_ref, url=item.source_uri, publisher=item.source_name,
            source_type="reference" if reference else "provider_observation",
            provenance_state="KNOWN" if known[item.id] else "PROVENANCE_UNKNOWN",
            observed_at=item.observed_at, retrieved_at=received_at,
            # This is an adapter excerpt, not a capture of the publisher page.
            snapshot_text=item.excerpt,
        ))
    entities: list[EntityProposal] = []
    claims: list[ClaimProposal] = []
    evidence: list[EvidenceProposal] = []
    for entity in result.entities:
        if entity.entity_type not in {"supplier", "price_observation", "product", "organization", "place"}:
            raise ValueError("journey result has an unsupported entity type")
        entity_types: dict[str, Literal["Supplier", "Product", "Organization", "Place"]] = {
            "supplier": "Supplier", "price_observation": "Product", "product": "Product",
            "organization": "Organization", "place": "Place"}
        type_name = entity_types[entity.entity_type]
        aliases = dict(entity.identifiers)
        if "domain" in aliases:
            # Exact identity alias is not verification of the supplier or its claims.
            aliases["official_domain"] = aliases.pop("domain")
        entities.append(EntityProposal(ref=entity.id, type=type_name, name=entity.name, external_ids=aliases))
        proposals = list(entity.attributes.get("claims", []))
        for estimate in entity.attributes.get("estimates", []):
            proposals.append({"id": estimate["id"], "predicate": estimate["kind"], "value": estimate,
                              "kind": "estimate", "evidence_ids": estimate.get("evidence_ids", [])})
        for proposal in proposals:
            if not isinstance(proposal, dict):
                raise ValueError("SDK entity claim must be an object")
            support_ids = proposal.get("evidence_ids", [])
            if not isinstance(support_ids, list) or any(item not in evidence_index for item in support_ids):
                raise ValueError("SDK claim references missing evidence")
            kind = proposal.get("kind", "fact")
            if kind not in {"fact", "estimate", "inference", "model_output"}:
                raise ValueError("SDK claim kind is not supported")
            claim_known = bool(support_ids) and all(known[item] for item in support_ids)
            if entity.attributes.get("synthetic"):
                claim_known = False
            value = proposal.get("value")
            text = proposal.get("text") or f"{entity.name}: {proposal['predicate']} = {json.dumps(value, sort_keys=True, allow_nan=False)}"
            claims.append(ClaimProposal(
                ref=proposal["id"], entity_ref=entity.id, text=text[:1200],
                predicate=proposal["predicate"], value=value, kind=kind,
                provenance_state="KNOWN" if claim_known else "PROVENANCE_UNKNOWN",
            ))
            for evidence_id in support_ids:
                item = evidence_index[evidence_id]
                evidence.append(EvidenceProposal(
                    ref=proposal["id"] + "-" + str(support_ids.index(evidence_id)), claim_ref=proposal["id"],
                    source_ref="src-" + item.id, excerpt=item.excerpt,
                    observed_at=item.observed_at,
                    provenance_state="KNOWN" if claim_known and known[evidence_id] else "PROVENANCE_UNKNOWN",
                    # ECHO computes its own normalized excerpt hash. The SDK's
                    # optional provider hash is retained only in the raw receipt.
                ))
    return NormalizedResult(
        extension_id=result.extension_id, extension_version=result.extension_version,
        status=result.status, sources=sources, entities=entities, claims=claims,
        evidence=evidence, warnings=result.warnings, confidence=result.confidence,
        raw_reference=f"sdk:{result.extension_id}:{result.request_id}",
    )
