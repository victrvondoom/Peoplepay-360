"""Core-owned proposal normalization and idempotent graph ingestion.

Adapters return references. This layer assigns canonical IDs, preserves
observations and versions, and never accepts decisions or utility scores.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from collections import defaultdict
from hashlib import sha256
from threading import RLock
from typing import Any
from urllib.parse import urlsplit

from echo.extensions.contracts import ExtensionExecution, ExtensionManifest, ExtensionRequest
from echo.graph_store import EchoGraphStore
from echo.models import normalize_source_url, stable_id, text_hash

DEMO_EXTENSIONS = frozenset({"demo-source-a", "demo-source-b"})
INGESTION_LOCK = RLock()


class IngestionRejected(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def request_hash(request: ExtensionRequest) -> str:
    return sha256(canonical_json(request.model_dump(mode="json")).encode()).hexdigest()


def ingestion_event_id(manifest: ExtensionManifest, request: ExtensionRequest) -> str:
    return stable_id("ingestion", manifest.id, manifest.version,
                     request.context.requirement_id or "", request.request_id)


def utc_iso(value: datetime | None) -> str | None:
    return value.astimezone(timezone.utc).isoformat() if value is not None else None


def domain_identity(value: str) -> str:
    parts = urlsplit(value if "://" in value else "https://" + value)
    if not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
        raise IngestionRejected("INVALID_ENTITY", "official_domain must identify one hostname")
    if parts.path not in {"", "/"} or parts.port is not None:
        raise IngestionRejected("INVALID_ENTITY", "official_domain cannot include a path or port")
    domain = parts.hostname.lower().encode("idna").decode("ascii")
    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?", domain) or "." not in domain:
        raise IngestionRejected("INVALID_ENTITY", "official_domain must be a domain name")
    return domain


class ExtensionIngestor:
    def __init__(self, store: EchoGraphStore) -> None:
        self.store = store

    def existing(self, manifest: ExtensionManifest, request: ExtensionRequest) -> dict[str, Any] | None:
        rows = self.store.read_only_rows(
            "MATCH (event:IngestionEvent {id: $id}) RETURN event.request_hash, event.applied, event.summary_json",
            {"id": ingestion_event_id(manifest, request)},
        )
        if not rows:
            return None
        if rows[0][0] != request_hash(request):
            raise IngestionRejected("IDEMPOTENCY_CONFLICT", "request_id was already used with another input")
        if rows[0][1]:
            summary = json.loads(rows[0][2])
            return {**summary, "idempotent_replay": True}
        return None

    def ingest(self, manifest: ExtensionManifest, request: ExtensionRequest,
               execution: ExtensionExecution) -> dict[str, Any]:
        with INGESTION_LOCK:
            return self._ingest(manifest, request, execution)

    def _ingest(self, manifest: ExtensionManifest, request: ExtensionRequest,
                execution: ExtensionExecution) -> dict[str, Any]:
        requirement_id, user_id = request.context.requirement_id, request.context.user_id
        if not requirement_id or not user_id:
            raise IngestionRejected("INVALID_CONTEXT", "owned requirement context is required")
        requirement = self.store.read_only_rows(
            "MATCH (r:Requirement {id: $id, user_id: $user}) RETURN r.demo_scope",
            {"id": requirement_id, "user": user_id},
        )
        if not requirement:
            raise IngestionRejected("REQUIREMENT_NOT_FOUND", "owned requirement was not found")
        demo_scope = requirement[0][0]
        if manifest.id in DEMO_EXTENSIONS and not demo_scope:
            raise IngestionRejected("DEMO_ONLY", "synthetic extensions require a synthetic requirement")
        if execution.extension_id != manifest.id or execution.extension_version != manifest.version:
            raise IngestionRejected("INVALID_OUTPUT", "execution provider does not match the registered version")
        if execution.request_id != request.request_id or execution.capability != request.capability:
            raise IngestionRejected("INVALID_OUTPUT", "execution is not bound to this request")
        result = execution.result
        if result is None:
            self._record_failure(manifest, request, execution, demo_scope)
            return {"status": "error", "run_id": execution.run_id, "ingested": False,
                    "error": execution.error.model_dump() if execution.error else {"code": "INVALID_OUTPUT"}}
        replay = self.existing(manifest, request)
        if replay:
            return replay
        permitted = set(manifest.graph.write)
        proposed = set()
        for name, label in (("sources", "Source"), ("claims", "Claim"), ("evidence", "Evidence")):
            if getattr(result, name):
                proposed.add(label)
        proposed.update(entity.type for entity in result.entities)
        if result.source_dependencies:
            proposed.add("Source")
        if result.observations:
            proposed.add("Claim")
        if not proposed.issubset(permitted):
            raise IngestionRejected("PERMISSION_DENIED", "result proposes labels outside manifest graph permissions")
        nodes: dict[str, list[dict[str, Any]]] = defaultdict(list)
        edges: list[dict[str, Any]] = []

        def node(label: str, props: dict[str, Any]) -> None:
            shared = {"Extension", "ExtensionVersion", "Source", "SourceSnapshot", "Supplier", "Organization"}
            nodes[label].append({**props, **({"demo_scope": demo_scope} if label not in shared else {})})

        def edge(from_label: str, from_id: str, relationship: str,
                 to_label: str, to_id: str, props: dict[str, Any] | None = None) -> None:
            identifier = stable_id("edge", relationship, from_id, to_id)
            edges.append({"id": identifier, "from_label": from_label, "from_id": from_id,
                          "type": relationship, "to_label": to_label, "to_id": to_id,
                          "props": {**(props or {}), "id": identifier, "demo_scope": demo_scope}})

        version_id = stable_id("extension-version", manifest.id, manifest.version)
        node("Extension", {"id": manifest.id, "name": manifest.name})
        node("ExtensionVersion", {"id": version_id, "version": manifest.version,
                                  "upstream_repository": manifest.upstream.repository,
                                  "upstream_commit": manifest.upstream.commit,
                                  "license_spdx": manifest.license.spdx})
        node("ExtensionRun", self._run_record(manifest, request, execution))
        edge("Extension", manifest.id, "HAS_VERSION", "ExtensionVersion", version_id)
        edge("ExtensionVersion", version_id, "EXECUTED", "ExtensionRun", execution.run_id)
        edge("Requirement", requirement_id, "HAS_EVENT", "ExtensionRun", execution.run_id)

        entity_ids: dict[str, tuple[str, str]] = {}
        resolved: dict[str, str] = {}
        unresolved: list[str] = []
        for entity in result.entities:
            representation_id = stable_id("representation", execution.run_id, entity.ref)
            props = {"id": representation_id, "name": entity.name, "proposed_type": entity.type,
                     "external_ids_json": canonical_json(entity.external_ids), "requirement_id": requirement_id,
                     "match_status": "UNRESOLVED", "match_confidence": 0.0}
            identity = entity.external_ids.get("official_domain")
            if entity.type in {"Supplier", "Organization"} and identity:
                domain = domain_identity(identity)
                identifier = stable_id(entity.type.lower(), domain)
                node(entity.type, {"id": identifier, "name": entity.name, "official_domain": domain,
                                   "identity_status": "MATCHED", "identity_method": "EXACT_DOMAIN_IDENTIFIER",
                                   "synthetic": domain.endswith(".example")})
                entity_ids[entity.ref] = (entity.type, identifier)
                resolved[entity.ref] = identifier
                props.update(match_status="IDENTIFIER_MATCH", match_confidence=1.0)
                edge("EntityRepresentation", representation_id, "RESOLVES_TO", entity.type, identifier)
            else:
                # A display name never silently becomes a canonical supplier.
                entity_ids[entity.ref] = ("EntityRepresentation", representation_id)
                unresolved.append(entity.ref)
            node("EntityRepresentation", props)
            edge("ExtensionRun", execution.run_id, "PRODUCED", "EntityRepresentation", representation_id)

        source_ids: dict[str, str] = {}
        snapshot_ids: dict[str, str] = {}
        for source in result.sources:
            address = normalize_source_url(source.url) if source.url else None
            if address:
                identifier = stable_id("source", address)
            elif source.upstream_document_id:
                identifier = stable_id("source", manifest.id, source.upstream_document_id)
            else:
                identifier = stable_id("source-unknown", manifest.id, source.ref, requirement_id)
            source_ids[source.ref] = identifier
            computed_hash = text_hash(source.snapshot_text) if source.snapshot_text else None
            if source.content_hash and computed_hash and source.content_hash.lower() != computed_hash:
                raise IngestionRejected("SNAPSHOT_HASH_MISMATCH", "source content hash does not match the normalized excerpt")
            content_hash = computed_hash or source.content_hash
            snapshot_id = stable_id("snapshot", identifier, content_hash or "NOT_CAPTURED",
                                    utc_iso(source.original_observed_at or source.observed_at) or "unknown")
            snapshot_ids[source.ref] = snapshot_id
            observed = source.original_observed_at or source.observed_at
            node("Source", {"id": identifier, "source_url": address, "publisher": source.publisher,
                            "title": source.title, "source_type": source.source_type,
                            "provenance_state": source.provenance_state, "active": True,
                            "synthetic": bool(address and (urlsplit(address).hostname or "").endswith(".example"))})
            node("SourceSnapshot", {"id": snapshot_id, "source_id": identifier,
                                    "content_hash": content_hash,
                                    "hash_origin": "CORE_EXCERPT" if computed_hash else ("UPSTREAM_ASSERTED" if source.content_hash else "NOT_CAPTURED"),
                                    "snapshot_text": " ".join((source.snapshot_text or "").split()),
                                    "snapshot_state": "CAPTURED" if content_hash else "NOT_CAPTURED",
                                    "observed_at": utc_iso(observed),
                                    "source_published_at": utc_iso(source.published_at),
                                    "retrieved_at": utc_iso(source.retrieved_at),
                                    "cache_age_seconds": source.cache_age_seconds})
            edge("Source", identifier, "OBSERVED_AT", "SourceSnapshot", snapshot_id)
            edge("ExtensionRun", execution.run_id, "OBSERVED", "SourceSnapshot", snapshot_id)
        for dependency in result.source_dependencies:
            if source_ids[dependency.from_source_ref] == source_ids[dependency.to_source_ref]:
                raise IngestionRejected("INVALID_DEPENDENCY", "source URL normalization produced a self-dependency")
            edge("Source", source_ids[dependency.from_source_ref], dependency.type,
                 "Source", source_ids[dependency.to_source_ref], {
                     "evidence_mode": dependency.evidence_mode,
                     "relationship_confidence": dependency.confidence or 0.0,
                     "explanation": " ".join(dependency.explanation.split()),
                     "extension_run_id": execution.run_id})

        claim_ids: dict[str, str] = {}
        for claim in result.claims:
            label, entity_id = entity_ids[claim.entity_ref]
            value_json = canonical_json(claim.value)
            identifier = stable_id("claim", requirement_id, entity_id, claim.predicate, value_json, claim.kind)
            claim_ids[claim.ref] = identifier
            conflicts = self.store.read_only_rows(
                "MATCH (claim:Claim {requirement_id: $req, predicate: $predicate})-[:ABOUT]->(entity {id: $entity}) "
                "WHERE claim.value_json <> $value RETURN claim.id",
                {"req": requirement_id, "predicate": claim.predicate, "entity": entity_id, "value": value_json},
            )
            same_result_conflicts = [other for other in result.claims
                                     if other.ref != claim.ref and entity_ids[other.entity_ref][1] == entity_id
                                     and other.predicate == claim.predicate and canonical_json(other.value) != value_json]
            node("Claim", {"id": identifier, "requirement_id": requirement_id,
                           "predicate": claim.predicate, "value_json": value_json,
                           "text": " ".join(claim.text.split()), "kind": claim.kind,
                           "provenance_state": claim.provenance_state, "conflict_open": bool(conflicts or same_result_conflicts)})
            for conflicting_id in [row[0] for row in conflicts]:
                node("Claim", {"id": conflicting_id, "conflict_open": True})
                edge("Claim", identifier, "CONTRADICTS", "Claim", conflicting_id)
            for other in same_result_conflicts:
                other_id = stable_id("claim", requirement_id, entity_id, other.predicate, canonical_json(other.value), other.kind)
                edge("Claim", identifier, "CONTRADICTS", "Claim", other_id)
            edge("Claim", identifier, "ABOUT", label, entity_id)
            if label == "Supplier":
                edge("Supplier", entity_id, "HAS_CLAIM", "Claim", identifier)
            edge("ExtensionRun", execution.run_id, "PRODUCED", "Claim", identifier,
                 {"kind": claim.kind, "claim_confidence": claim.confidence,
                  "provenance_state": claim.provenance_state})
        evidence_ids: list[str] = []
        for evidence in result.evidence:
            claim_id = claim_ids[evidence.claim_ref]
            source_id = source_ids.get(evidence.source_ref or "")
            evidence_snapshot_id = snapshot_ids.get(evidence.source_ref or "")
            evidence_source = next((s for s in result.sources if s.ref == evidence.source_ref), None)
            observed = (evidence_source.original_observed_at if evidence_source else None) or evidence.observed_at
            content_hash = evidence.content_hash or text_hash(evidence.excerpt)
            identifier = stable_id("evidence", requirement_id, claim_id, source_id or "unknown",
                                   content_hash, utc_iso(observed) or "unknown")
            evidence_ids.append(identifier)
            known = evidence.provenance_state == "KNOWN" and evidence_source is not None and evidence_source.provenance_state == "KNOWN"
            if not source_id:
                source_id = stable_id("source-unknown", requirement_id, claim_id, evidence.ref)
                node("Source", {"id": source_id, "provenance_state": "PROVENANCE_UNKNOWN", "active": True})
            claim = next(c for c in result.claims if c.ref == evidence.claim_ref)
            state = "SYNTHETIC_DEMO" if demo_scope else ("MODEL_OUTPUT" if claim.kind == "model_output" else "UNVERIFIED")
            node("Evidence", {"id": identifier, "claim_id": claim_id, "source_id": source_id,
                              "snapshot_id": evidence_snapshot_id, "content_hash": content_hash,
                              "excerpt": " ".join(evidence.excerpt.split()),
                              "observed_at": utc_iso(observed),
                              "valid_from": utc_iso(evidence.valid_from),
                              "valid_until": utc_iso(evidence.valid_until),
                              "confidence": evidence.confidence if evidence.confidence is not None else 0.0,
                              "provenance_state": "KNOWN" if known else "PROVENANCE_UNKNOWN",
                              "verification_state": state, "active": evidence.active})
            edge("Claim", claim_id, "SUPPORTED_BY", "Evidence", identifier)
            edge("ExtensionRun", execution.run_id, "OBSERVED", "Evidence", identifier)
            if source_id:
                edge("Evidence", identifier, "FROM_SOURCE", "Source", source_id)
            if evidence_snapshot_id:
                edge("Evidence", identifier, "OBSERVED_AT", "SourceSnapshot", evidence_snapshot_id)
        for observation in result.observations:
            identifier = stable_id("observation", execution.run_id, observation.ref)
            node("ExtensionObservation", {"id": identifier, "requirement_id": requirement_id,
                                          "text": " ".join(observation.text.split()), "kind": observation.kind,
                                          "observed_at": utc_iso(observation.observed_at),
                                          "confidence": observation.confidence})
            edge("ExtensionRun", execution.run_id, "PRODUCED", "ExtensionObservation", identifier)
            if observation.entity_ref:
                label, entity_id = entity_ids[observation.entity_ref]
                edge("ExtensionObservation", identifier, "ABOUT", label, entity_id)
            if observation.source_ref:
                edge("ExtensionObservation", identifier, "FROM_SOURCE", "Source", source_ids[observation.source_ref])
        result_hash = sha256(canonical_json(result.model_dump(mode="json")).encode()).hexdigest()
        event_id = ingestion_event_id(manifest, request)
        summary = {"status": "applied", "run_id": execution.run_id, "event_id": event_id,
                   "idempotent_replay": False, "ingested": True,
                   "claim_count": len(set(claim_ids.values())), "evidence_count": len(set(evidence_ids)),
                   "source_count": len(set(source_ids.values())), "resolved_entities": resolved,
                   "unresolved_entity_refs": unresolved, "source_ids": source_ids,
                   "extension_id": manifest.id, "extension_version": manifest.version}
        event = {"id": event_id, "request_hash": request_hash(request), "schema_version": "1",
                 "occurred_at": execution.finished_at.isoformat(), "summary_json": canonical_json(summary),
                 "requirement_id": requirement_id, "user_id": user_id, "demo_scope": demo_scope}
        edge("ExtensionRun", execution.run_id, "INGESTED", "IngestionEvent", event_id)
        applied = self.store.apply_extension_batch(requirement_id=requirement_id, user_id=user_id,
                                                  event_id=event_id, result_hash=result_hash,
                                                  nodes=dict(nodes), edges=edges, event=event)
        if not applied:
            replay = self.existing(manifest, request)
            if replay:
                return replay
            raise IngestionRejected("INGESTION_FAILED", "validated batch could not be recorded")
        return summary

    @staticmethod
    def _run_record(manifest: ExtensionManifest, request: ExtensionRequest,
                    execution: ExtensionExecution) -> dict[str, Any]:
        model = execution.result.model_provenance if execution.result else None
        return {"id": execution.run_id, "extension_id": manifest.id, "extension_version": manifest.version,
                "request_id": request.request_id, "capability": request.capability,
                "requirement_id": request.context.requirement_id, "user_id": request.context.user_id,
                "started_at": execution.started_at.isoformat(), "finished_at": execution.finished_at.isoformat(),
                "duration_ms": execution.duration_ms, "status": execution.status,
                "input_bytes": execution.input_bytes, "output_count": execution.output_count,
                "error_code": execution.error.code if execution.error else None,
                "model_provenance_json": canonical_json(model.model_dump(mode="json")) if model else None}

    def _record_failure(self, manifest: ExtensionManifest, request: ExtensionRequest,
                        execution: ExtensionExecution, demo_scope: str | None) -> None:
        version_id = stable_id("extension-version", manifest.id, manifest.version)
        self.store.upsert_node("Extension", {"id": manifest.id, "name": manifest.name})
        self.store.upsert_node("ExtensionVersion", {"id": version_id, "version": manifest.version})
        self.store.upsert_node("ExtensionRun", {**self._run_record(manifest, request, execution), "demo_scope": demo_scope})
        self.store.link("Extension", manifest.id, "HAS_VERSION", "ExtensionVersion", version_id)
        self.store.link("ExtensionVersion", version_id, "EXECUTED", "ExtensionRun", execution.run_id)
