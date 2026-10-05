"""Native service adapters for the first PeoplePay procurement journey.

The SDK carries observations, never purchase authority. Reference replay is
explicit; failed live requests cannot silently fall back to example data.
"""

from __future__ import annotations

import json
import math
import re
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Literal, Protocol
from urllib.parse import quote, urlsplit

import httpx
from peoplepay_sdk import (
    Capability, Entity, Evidence, ExtensionHealth, ExtensionMetadata,
    ExtensionRequest, ExtensionResult,
)

REFERENCE_WARNING = "REFERENCE_DATA: synthetic supplier inputs; no real discovery, certification, quote or payment."
MAX_RESPONSE_BYTES = 262_144


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _id(prefix: str, *values: Any) -> str:
    return prefix + "-" + sha256(_json(values).encode()).hexdigest()[:24]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("upstream observation time lacks timezone")
    return parsed


def _number(value: Any, *, nonnegative: bool = True) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("upstream number is not finite")
    if nonnegative and value < 0:
        raise ValueError("upstream quantity is negative")
    return float(value)


def _url(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str) or len(value) > 2000:
        raise ValueError("invalid upstream source URL")
    parts = urlsplit(value)
    if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password:
        raise ValueError("upstream source URL must be HTTP(S) without credentials")
    return value


def _contains(value: Any, secret: str) -> bool:
    if isinstance(value, str):
        return bool(secret and secret in value)
    if isinstance(value, dict):
        return any(_contains(key, secret) or _contains(child, secret) for key, child in value.items())
    if isinstance(value, list):
        return any(_contains(child, secret) for child in value)
    return False


class SourceClient(Protocol):
    origin: str

    async def request(self, method: str, path: str, *, json: dict[str, Any] | None = None,
                      params: dict[str, Any] | None = None) -> Any: ...


class HttpSourceClient:
    """An operator chooses one origin; provider input cannot change it.

    Redirects are disabled. Service authentication stays in the transport.
    HTTP is allowed only on loopback; remote services must use HTTPS.
    """

    def __init__(self, origin: str, *, token: str | None = None, timeout_seconds: float = 20,
                 transport: httpx.AsyncBaseTransport | None = None) -> None:
        parts = urlsplit(origin)
        if (parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password
                or parts.path not in {"", "/"} or parts.query or parts.fragment):
            raise ValueError("configure one HTTP(S) service origin without credentials or path")
        if parts.scheme == "http" and parts.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("remote provider origins require HTTPS")
        if not 0 < timeout_seconds <= 60:
            raise ValueError("provider timeout must be between 0 and 60 seconds")
        self.origin = origin.rstrip("/")
        self._token = token or ""
        self._timeout = timeout_seconds
        self._transport = transport

    async def request(self, method: str, path: str, *, json: dict[str, Any] | None = None,
                      params: dict[str, Any] | None = None) -> Any:
        if (not path.startswith("/") or path.startswith("//") or ".." in path
                or urlsplit(path).scheme or "?" in path or "#" in path):
            raise ValueError("provider path must be a relative API path")
        headers = {"Accept": "application/json"}
        if self._token:
            headers["Authorization"] = "Bearer " + self._token
        async with httpx.AsyncClient(timeout=self._timeout, follow_redirects=False,
                                     transport=self._transport, trust_env=False) as client:
            async with client.stream(method, self.origin + path, json=json, params=params, headers=headers) as response:
                if 300 <= response.status_code < 400:
                    raise ValueError("provider redirects are not followed")
                response.raise_for_status()
                if "application/json" not in response.headers.get("content-type", "").lower():
                    raise ValueError("provider response must be JSON")
                chunks = bytearray()
                async for chunk in response.aiter_bytes():
                    chunks.extend(chunk)
                    if len(chunks) > MAX_RESPONSE_BYTES:
                        raise ValueError("provider response exceeds byte limit")
        value = __import__("json").loads(chunks)
        if _contains(value, self._token):
            raise ValueError("provider echoed transport credentials")
        _json(value)  # reject nonfinite decoded numbers
        return value


class _Provider:
    extension_id: str
    capability: str
    name: str
    description: str

    def __init__(self, client: SourceClient, *, mode: Literal["live", "reference"] = "live") -> None:
        self.client = client
        self.mode = mode

    def capabilities(self) -> list[Capability]:
        return [Capability(name=self.capability, description=self.description)]

    def metadata(self) -> ExtensionMetadata:
        return ExtensionMetadata(id=self.extension_id, name=self.name, version="1.0.0",
                                 description=self.description, capabilities=self.capabilities())

    async def health(self) -> ExtensionHealth:
        if self.mode == "reference":
            return ExtensionHealth(extension_id=self.extension_id, status="degraded", checked_at=_now(),
                                   message="Explicit reference replay; external service discovery is not active.")
        status: Literal["healthy", "degraded", "unavailable"]
        try:
            response = await self.client.request("GET", "/health")
            status = "healthy" if response.get("status") in {"ok", "healthy"} else "degraded"
        except Exception:
            status = "unavailable"
        return ExtensionHealth(extension_id=self.extension_id, status=status, checked_at=_now(),
                               message="Service liveness only; provider/data readiness remains unverified.")

    def _result(self, request: ExtensionRequest, *, entities: list[Entity] | None = None,
                evidence: list[Evidence] | None = None, raw: dict[str, Any] | None = None,
                warnings: list[str] | None = None) -> ExtensionResult:
        warning_list = list(warnings or [])
        if self.mode == "reference":
            warning_list.insert(0, REFERENCE_WARNING if self.extension_id == "greenchain" else
                                "REFERENCE_REPLAY: bundled InflationForge snapshot; no live price refresh.")
        return ExtensionResult(request_id=request.request_id, extension_id=self.extension_id,
                               extension_version="1.0.0", status="partial" if warning_list else "success",
                               entities=entities or [], evidence=evidence or [],
                               raw_result=raw or {}, warnings=warning_list)

    def _failure(self, request: ExtensionRequest, exc: Exception) -> ExtensionResult:
        # Do not persist URLs, credentials or an upstream server's exception text.
        code = "PROVIDER_TIMEOUT" if isinstance(exc, (httpx.TimeoutException, TimeoutError)) else "PROVIDER_INVALID_OR_UNAVAILABLE"
        return self._result(request, warnings=[code + ": " + type(exc).__name__],
                            raw={"mode": self.mode, "received_at": _now().isoformat(), "error_type": type(exc).__name__})


class GreenChainProvider(_Provider):
    extension_id = "greenchain"
    capability = "supplier_discovery"
    name = "GreenChain sourcing observations"
    description = "Native supplier discovery with environmental estimates; no purchase or certification authority."

    async def execute(self, request: ExtensionRequest) -> ExtensionResult:
        if request.capability != self.capability:
            raise ValueError("GreenChain does not implement the requested capability")
        try:
            product, quantity = request.input.get("product"), request.input.get("quantity")
            destination = request.input.get("destination", "IN")
            if not isinstance(product, str) or not product.strip() or len(product) > 200:
                raise ValueError("product is required")
            if isinstance(quantity, bool) or not isinstance(quantity, int) or not 1 <= quantity <= 1_000_000:
                raise ValueError("quantity must be a bounded positive integer")
            if not isinstance(destination, str) or not re.fullmatch(r"[A-Z]{2}", destination):
                raise ValueError("destination must be an ISO country code")
            payload = {"product": product, "quantity": quantity, "destination": destination,
                       "transport_mode": request.input.get("transport_mode", "road"), "target_count": 3,
                       "use_cache": True}
            if payload["transport_mode"] not in {"sea", "air", "rail", "road"}:
                raise ValueError("unsupported transport mode")
            response = await self.client.request("POST", "/search", json=payload)
            if not isinstance(response, dict) or not isinstance(response.get("results"), list):
                raise ValueError("GreenChain did not return results")
            if len(response["results"]) > 10 or response.get("count") != len(response["results"]):
                raise ValueError("GreenChain candidate count is inconsistent or exceeds journey limit")
            # A response cannot swap the requested product/destination context.
            if response.get("product") != product or response.get("destination") != destination:
                raise ValueError("GreenChain response does not match the requested context")
            received = _now()
            evidence: list[Evidence] = []
            entities: list[Entity] = []
            for index, row in enumerate(response["results"]):
                if not isinstance(row, dict):
                    raise ValueError("invalid GreenChain candidate")
                name, country = row.get("name"), row.get("country")
                if not isinstance(name, str) or not name.strip() or not isinstance(country, str):
                    raise ValueError("supplier identity is missing")
                source = _url(row.get("sustainability_url"))
                domain = (urlsplit(source).hostname or "").lower() if source else None
                entity_id = _id("greenchain-supplier", index, name, country, domain)
                evidence_id = _id("greenchain-evidence", request.request_id, index)
                score = _number(row.get("composite_score"))
                if score is not None and score > 100:
                    raise ValueError("GreenChain score exceeds its 0-100 scale")
                emission = row.get("emission_factor") or {}
                transport = row.get("transport") or {}
                if not isinstance(emission, dict) or not isinstance(transport, dict):
                    raise ValueError("invalid GreenChain estimate")
                lower, middle, upper = [_number(emission.get(key)) for key in ("q10_tco2e", "q50_tco2e", "q90_tco2e")]
                if lower is not None and middle is not None and upper is not None and not lower <= middle <= upper:
                    raise ValueError("GreenChain estimate quantiles are unordered")
                excerpt = f"GreenChain reported {name} ({country}), environmental score {score}; model estimates are not carbon certificates."
                evidence.append(Evidence(id=evidence_id, source_uri=source, source_name="GreenChain response",
                                         excerpt=excerpt, observed_at=_time(row.get("observed_at")),
                                         provenance_state="unknown",
                                         uncertainty="Supplier-source snapshot was not captured; receipt time is separate from source observation time."))
                claims = [{"id": _id("gc-score", entity_id), "subject_id": entity_id,
                           "predicate": "environmental_score", "value": score, "unit": "score_0_100",
                           "evidence_ids": [evidence_id], "kind": "model_output"}]
                estimates: list[dict[str, Any]] = []
                if middle is not None:
                    estimates.append({"id": _id("gc-manufacturing", entity_id), "kind": "manufacturing_emissions",
                                      "value": middle, "lower": lower, "upper": upper, "unit": "tCO2e",
                                      "basis": "GreenChain provider manufacturing model; not certified or per-chair life-cycle emissions.",
                                      "certified": False, "evidence_ids": [evidence_id]})
                transport_emissions = _number(transport.get("transport_tco2e"))
                if transport_emissions is not None:
                    estimates.append({"id": _id("gc-transport", entity_id), "kind": "transport_emissions",
                                      "value": transport_emissions, "unit": "tCO2e",
                                      "basis": {key: transport.get(key) for key in ("mode", "distance_km", "weight_kg")},
                                      "certified": False, "evidence_ids": [evidence_id]})
                entities.append(Entity(id=entity_id, entity_type="supplier", name=name,
                                       identifiers={"domain": domain} if domain else {},
                                       attributes={"country": country, "city": row.get("city"),
                                                   "certifications": row.get("certifications", []),
                                                   "provider_score": score, "provider_rank": row.get("rank"),
                                                   "score_direction": "higher_is_better", "claims": claims,
                                                   "estimates": estimates, "evidence_ids": [evidence_id],
                                                   "synthetic": self.mode == "reference" or bool(row.get("synthetic")) or bool(domain and domain.endswith(".example")),
                                                   "upstream_verification": row.get("verification")}))
            warnings = ["ESTIMATED_NOT_CERTIFIED: GreenChain scores and emissions are provider estimates, not verified supplier facts."]
            if response.get("fallback_components"):
                warnings.append("UPSTREAM_PLACEHOLDERS: GreenChain used offline fallback manufacturers.")
                for entity in entities:
                    entity.attributes["synthetic"] = True
            if not entities:
                warnings.append("NO_SUPPLIERS: discovery produced no candidates.")
            return self._result(request, entities=entities, evidence=evidence, warnings=warnings,
                                raw={"mode": self.mode, "received_at": received.isoformat(), "native_endpoint": "/search",
                                     "response_sha256": sha256(_json(response).encode()).hexdigest(), "response": response})
        except Exception as exc:
            return self._failure(request, exc)


class InflationForgeProvider(_Provider):
    extension_id = "inflationforge"
    capability = "price_intelligence"
    name = "InflationForge price observations"
    description = "Timestamped city/item USD observations; coverage gaps are explicit and never become merchant quotes."

    async def execute(self, request: ExtensionRequest) -> ExtensionResult:
        if request.capability != self.capability:
            raise ValueError("InflationForge does not implement the requested capability")
        try:
            product = request.input.get("product", "")
            item_id = request.input.get("item_id")
            if not isinstance(product, str) or len(product) > 200:
                raise ValueError("product must be a bounded name")
            items = await self.client.request("GET", "/api/items", params={"include_retired": "false"})
            if not isinstance(items, list) or len(items) > 50 or any(not isinstance(item, dict) for item in items):
                raise ValueError("invalid InflationForge catalog")
            match = [item for item in items if item.get("status", "ACTIVE") == "ACTIVE" and
                     (item.get("id") == item_id if item_id else product.casefold().strip() in
                      {str(item.get("id", "")).casefold(), str(item.get("name", "")).casefold()})]
            catalog_raw = {"mode": self.mode, "received_at": _now().isoformat(), "requested_product": product,
                           "catalog": items, "native_endpoints": ["/api/items"]}
            if len(match) != 1:
                return self._result(request, raw=catalog_raw, warnings=[
                    "NOT_TRACKED: InflationForge has no exact tracked item for the requested product; no chair price or INR conversion is supplied."])
            item = match[0]
            city_id = request.input.get("city_id")
            if not isinstance(city_id, str) or not re.fullmatch(r"[a-z][a-z0-9-]{0,63}", city_id):
                return self._result(request, raw=catalog_raw, warnings=["LOCATION_REQUIRED: specify an exact InflationForge city_id; no location is inferred."])
            snapshots = await self.client.request("GET", "/api/snapshots")
            if not isinstance(snapshots, list) or len(snapshots) > 50 or any(not isinstance(row, dict) for row in snapshots):
                raise ValueError("invalid InflationForge snapshots")
            if not snapshots:
                return self._result(request, raw=catalog_raw, warnings=["NO_SNAPSHOT: no price observation is available."])
            snapshot = max(snapshots, key=lambda row: _time(row.get("retrieved_at")) or datetime.min.replace(tzinfo=timezone.utc))
            snapshot_id = snapshot.get("id")
            if not isinstance(snapshot_id, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", snapshot_id):
                raise ValueError("invalid snapshot identifier")
            path = "/api/snapshots/" + quote(snapshot_id, safe="") + "/observations"
            observations = await self.client.request("GET", path, params={"item_id": item["id"], "city_id": city_id})
            if not isinstance(observations, list) or len(observations) > 20:
                raise ValueError("unbounded InflationForge observations")
            entities: list[Entity] = []
            evidence: list[Evidence] = []
            warnings = ["NOT_MERCHANT_QUOTE: observations describe a city/item basket; they do not bind supplier price, stock, tax or fulfillment."]
            for row in observations:
                if not isinstance(row, dict) or (row.get("snapshot_id"), row.get("item_id"), row.get("city_id")) != (snapshot_id, item["id"], city_id):
                    raise ValueError("InflationForge observation context mismatch")
                if row.get("currency") != "USD":
                    raise ValueError("native price_usd observation must carry USD")
                price = _number(row.get("price_usd"))
                observed, retrieved = _time(row.get("observed_at")), _time(row.get("retrieved_at"))
                if price is None or price <= 0 or observed is None or retrieved is None:
                    raise ValueError("price or observation time is missing")
                if observed > retrieved:
                    raise ValueError("observation time is after retrieval time")
                source = _url(row.get("source_url"))
                if not source:
                    raise ValueError("price observation source is missing")
                evidence_id = _id("if-evidence", row.get("id"), snapshot_id)
                entity_id = _id("if-observation", row.get("id"), snapshot_id)
                excerpt = f"{item['name']}: USD {price:g} per {item.get('unit', 'unknown unit')} in {city_id}, observed {observed.isoformat()}; {row.get('kind')}."
                synthetic = self.mode == "reference" or (urlsplit(source).hostname or "").endswith(".example")
                evidence.append(Evidence(id=evidence_id, source_uri=source, source_name=str(row.get("source", "InflationForge")),
                                         excerpt=excerpt, observed_at=observed,
                                         provenance_state="unknown" if synthetic else "known",
                                         uncertainty="Bundled snapshot replay; not refreshed." if self.mode == "reference" else
                                         "Provider-reported observation; underlying publisher snapshot not independently checked."))
                entities.append(Entity(id=entity_id, entity_type="price_observation", name=str(item["name"]),
                                       identifiers={"item_id": str(item["id"]), "snapshot_id": snapshot_id},
                                       attributes={"item_id": item["id"], "product_name": item["name"],
                                                   "location": {"city_id": city_id}, "currency": "USD", "price": price,
                                                   "unit": item.get("unit"), "observed_at": observed.isoformat(),
                                                   "retrieved_at": retrieved.isoformat(), "snapshot_id": snapshot_id,
                                                   "kind": row.get("kind"), "evidence_ids": [evidence_id],
                                                   "synthetic": synthetic, "is_merchant_quote": False,
                                                   "claims": [{"id": _id("if-price", entity_id), "subject_id": entity_id,
                                                               "predicate": "city_item_price", "value": {"price": price, "currency": "USD", "city_id": city_id,
                                                               "item_id": item["id"], "unit": item.get("unit"), "observed_at": observed.isoformat()},
                                                               "kind": "fact", "evidence_ids": [evidence_id]}]}))
            if request.input.get("currency", "USD") != "USD":
                warnings.append("CURRENCY_MISMATCH: native observations are USD; no exchange rate or INR quote was inferred.")
            if not observations:
                warnings.append("NOT_OBSERVED: tracked item has no observation in the requested city.")
            catalog_raw.update({"snapshot": snapshot, "observations": observations, "native_endpoints": ["/api/items", "/api/snapshots", path]})
            return self._result(request, entities=entities, evidence=evidence, warnings=warnings, raw=catalog_raw)
        except Exception as exc:
            return self._failure(request, exc)


class ReferenceSourceClient:
    """Explicit captured native wire shapes; never selected after a live failure."""

    origin = "https://reference.peoplepay.example"

    def __init__(self, project: Literal["greenchain", "inflationforge"]) -> None:
        self.project = project
        fixtures = Path(__file__).with_name("fixtures")
        self.data = __import__("json").loads((fixtures / f"{project}_native.json").read_text(encoding="utf-8"))

    async def request(self, method: str, path: str, *, json: dict[str, Any] | None = None,
                      params: dict[str, Any] | None = None) -> Any:
        if path == "/health" and method == "GET":
            return {"status": "ok", "mode": "reference"}
        if self.project == "greenchain" and method == "POST" and path == "/search":
            if not json or (json.get("product"), json.get("quantity"), json.get("destination"), json.get("transport_mode")) != (
                    "ergonomic office chairs", 300, "IN", "road"):
                raise ValueError("reference fixture only covers 300 ergonomic office chairs to IN by road")
            return deepcopy(self.data["response"])
        if self.project == "inflationforge" and method == "GET":
            if path == "/api/items":
                return deepcopy(self.data["items"])
            if path == "/api/snapshots":
                return [deepcopy(self.data["snapshot"])]
            if path == f"/api/snapshots/{self.data['snapshot']['id']}/observations":
                return [deepcopy(row) for row in self.data["observations"]
                        if row["item_id"] == (params or {}).get("item_id") and row["city_id"] == (params or {}).get("city_id")]
        raise ValueError("reference source has no captured response for this path")


def reference_provider_clients() -> tuple[ReferenceSourceClient, ReferenceSourceClient]:
    return ReferenceSourceClient("greenchain"), ReferenceSourceClient("inflationforge")
