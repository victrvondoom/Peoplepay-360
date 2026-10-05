"""Provider boundaries: native HTTP shapes, coverage gaps and trust preservation."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import subprocess
import sys
from contextlib import contextmanager
from copy import deepcopy
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from peoplepay_sdk import ExtensionContext, ExtensionRequest

from journey.providers import (
    GreenChainProvider, HttpSourceClient, InflationForgeProvider,
    ReferenceSourceClient, reference_provider_clients,
)
from journey.sdk_bridge import reviewed_manifest, to_echo_result

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "journey" / "fixtures"


def request(capability="supplier_discovery", **overrides):
    return ExtensionRequest(request_id="journey-provider-test", capability=capability,
                            context=ExtensionContext(user_id="procurement-user", transaction_id="txn-test", trace_id="trace-test"),
                            input={"product": "ergonomic office chairs", "quantity": 300,
                                   "destination": "IN", "transport_mode": "road", **overrides})


@contextmanager
def native_wire_server(project: str):
    """Native responses travel over actual local HTTP, independent of adapter code."""
    data = json.loads((FIXTURES / f"{project}_native.json").read_text(encoding="utf-8"))
    seen = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            seen.append(("POST", self.path, body))
            self.respond(data["response"] if project == "greenchain" and self.path == "/search" else {}, 200)

        def do_GET(self):
            parts = urlsplit(self.path)
            seen.append(("GET", parts.path, parse_qs(parts.query)))
            if parts.path == "/api/items":
                value = data["items"]
            elif parts.path == "/api/snapshots":
                value = [data["snapshot"]]
            elif parts.path.endswith("/observations"):
                args = parse_qs(parts.query)
                value = [row for row in data["observations"] if row["item_id"] == args.get("item_id", [None])[0]
                         and row["city_id"] == args.get("city_id", [None])[0]]
            elif parts.path == "/health":
                value = {"status": "ok"}
            else:
                self.respond({}, 404)
                return
            self.respond(value, 200)

        def respond(self, value, status):
            body = json.dumps(value).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield HttpSourceClient(f"http://127.0.0.1:{server.server_port}"), data, seen
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_greenchain_native_http_preserves_scores_units_raw_receipt_and_provenance():
    with native_wire_server("greenchain") as (client, capture, seen):
        result = asyncio.run(GreenChainProvider(client).execute(request()))
    assert result.entities and not result.action_proposals
    assert seen[0] == ("POST", "/search", {"product": "ergonomic office chairs", "quantity": 300,
                       "destination": "IN", "transport_mode": "road", "target_count": 3, "use_cache": True})
    assert result.raw_result["response"] == capture["response"]
    best = result.entities[0]
    assert best.name == "Supplier B Inc."
    assert best.attributes["provider_score"] == capture["response"]["results"][0]["composite_score"]
    estimate = best.attributes["estimates"][0]
    assert estimate["unit"] == "tCO2e" and estimate["certified"] is False
    assert estimate["lower"] <= estimate["value"] <= estimate["upper"]
    assert all(item.provenance_state == "unknown" for item in result.evidence)
    assert all(entity.attributes["synthetic"] for entity in result.entities)


def test_native_captures_record_preserved_source_hashes_and_no_real_discovery():
    greenchain = json.loads((FIXTURES / "greenchain_native.json").read_text(encoding="utf-8"))
    assert greenchain["capture"]["native_source_sha256"] == sha256(
        (ROOT / "GREENCHAIN-main/greenchain/backend/ml_scorer.py").read_bytes()).hexdigest()
    assert greenchain["capture"]["discovery_performed"] is False
    assert greenchain["capture"]["verification_performed"] is False
    inflation = json.loads((FIXTURES / "inflationforge_native.json").read_text(encoding="utf-8"))
    assert inflation["capture"]["snapshot_file_sha256"] == sha256(
        (ROOT / "Inflation-Forge-main/data/bootstrap_snapshot.json").read_bytes()).hexdigest()
    assert inflation["capture"]["live_sync_performed"] is False


def test_captured_greenchain_scores_match_real_native_scoring_function():
    if any(importlib.util.find_spec(name) is None for name in ("numpy", "pandas", "joblib", "dotenv")):
        pytest.skip("Native GreenChain scoring dependencies are unavailable; replay boundary tests still run.")
    completed = subprocess.run(
        [sys.executable, "-c", "import json;from journey.fixtures.capture_greenchain import capture;print(json.dumps(capture()['response']['results']))"],
        cwd=ROOT, check=True, capture_output=True, text=True, timeout=30,
    )
    native = json.loads(completed.stdout.splitlines()[-1])
    captured = json.loads((FIXTURES / "greenchain_native.json").read_text(encoding="utf-8"))["response"]["results"]
    assert [(row["name"], row["composite_score"], row["scores"], row["rank"]) for row in native] == [
        (row["name"], row["composite_score"], row["scores"], row["rank"]) for row in captured]


def test_inflationforge_chairs_have_visible_coverage_gap_and_no_fake_inr_quote():
    with native_wire_server("inflationforge") as (client, _, seen):
        result = asyncio.run(InflationForgeProvider(client).execute(request("price_intelligence", currency="INR", city_id="bengaluru")))
    assert result.status == "partial" and not result.entities and not result.evidence
    assert any(warning.startswith("NOT_TRACKED:") for warning in result.warnings)
    assert [path for _, path, _ in seen] == ["/api/items"]
    assert result.raw_result["requested_product"] == "ergonomic office chairs"


def test_inflationforge_native_http_keeps_price_identity_city_currency_and_observation_time():
    with native_wire_server("inflationforge") as (client, capture, seen):
        result = asyncio.run(InflationForgeProvider(client).execute(
            request("price_intelligence", product="Milk", item_id="milk-gallon", city_id="chicago", currency="INR")))
    assert result.entities
    for observation in result.entities:
        attrs = observation.attributes
        assert attrs["item_id"] == "milk-gallon" and attrs["location"]["city_id"] == "chicago"
        assert attrs["currency"] == "USD" and attrs["is_merchant_quote"] is False
        assert attrs["snapshot_id"] == capture["snapshot"]["id"]
        assert attrs["observed_at"] and attrs["retrieved_at"] and attrs["price"] > 0
    assert any(warning.startswith("CURRENCY_MISMATCH:") for warning in result.warnings)
    assert seen[-1][2] == {"item_id": ["milk-gallon"], "city_id": ["chicago"]}


def test_reference_replay_is_explicit_and_is_not_a_generic_fallback():
    greenchain, inflation = reference_provider_clients()
    result = asyncio.run(GreenChainProvider(greenchain, mode="reference").execute(request()))
    assert result.raw_result["mode"] == "reference"
    assert result.warnings[0].startswith("REFERENCE_DATA:")
    mismatch = asyncio.run(GreenChainProvider(greenchain, mode="reference").execute(request(quantity=301)))
    assert not mismatch.entities and any(w.startswith("PROVIDER_INVALID_OR_UNAVAILABLE") for w in mismatch.warnings)
    coverage = asyncio.run(InflationForgeProvider(inflation, mode="reference").execute(request("price_intelligence")))
    assert coverage.warnings[0].startswith("REFERENCE_REPLAY:")
    assert not coverage.entities


class AlteredSource:
    origin = "https://trusted-provider.example"

    def __init__(self, response):
        self.response = response

    async def request(self, *args, **kwargs):
        if isinstance(self.response, Exception):
            raise self.response
        return deepcopy(self.response)


@pytest.mark.parametrize("change", ["nan", "quantiles", "product", "count", "url_credentials"])
def test_malformed_greenchain_results_never_become_candidates(change):
    response = json.loads((FIXTURES / "greenchain_native.json").read_text(encoding="utf-8"))["response"]
    row = response["results"][0]
    if change == "nan":
        row["composite_score"] = float("nan")
    elif change == "quantiles":
        row["emission_factor"]["q10_tco2e"] = 500
    elif change == "product":
        response["product"] = "unrelated product"
    elif change == "count":
        response["count"] = 400
    else:
        row["sustainability_url"] = "https://username:secret@example.com/"
    result = asyncio.run(GreenChainProvider(AlteredSource(response)).execute(request()))
    assert result.status == "partial" and not result.entities and not result.evidence
    assert result.warnings[0].startswith("PROVIDER_INVALID_OR_UNAVAILABLE:")


def test_live_timeout_stays_unavailable_and_contains_no_upstream_error_message():
    result = asyncio.run(GreenChainProvider(AlteredSource(httpx.ReadTimeout("hidden-secret"))).execute(request()))
    assert not result.entities and result.raw_result["mode"] == "live"
    assert "hidden-secret" not in result.model_dump_json()
    assert result.warnings == ["PROVIDER_TIMEOUT: ReadTimeout"]


@pytest.mark.parametrize("failure", ["redirect", "credentials", "oversize", "wrong_content_type"])
def test_http_transport_refuses_redirect_secret_echo_large_response_and_non_json(failure):
    def handler(_):
        if failure == "redirect":
            return httpx.Response(302, headers={"location": "http://127.0.0.1/private"})
        if failure == "credentials":
            return httpx.Response(200, json={"message": "do-not-persist-this-token"})
        if failure == "oversize":
            return httpx.Response(200, json={"payload": "x" * 262_145})
        return httpx.Response(200, text="not JSON")
    client = HttpSourceClient("https://operator-configured.example", token="do-not-persist-this-token",
                              transport=httpx.MockTransport(handler))
    with pytest.raises(ValueError):
        asyncio.run(client.request("GET", "/health"))


def test_bridge_retains_unknown_provenance_estimates_and_exact_domain_alias():
    sdk_result = asyncio.run(GreenChainProvider(ReferenceSourceClient("greenchain"), mode="reference").execute(request()))
    result = to_echo_result(sdk_result)
    assert result.entities[0].external_ids["official_domain"] == "supplier-b.example"
    assert {claim.kind for claim in result.claims} == {"model_output", "estimate"}
    assert all(source.provenance_state == "PROVENANCE_UNKNOWN" for source in result.sources)
    assert all(claim.provenance_state == "PROVENANCE_UNKNOWN" for claim in result.claims)
    assert all(item.provenance_state == "PROVENANCE_UNKNOWN" for item in result.evidence)
    assert not result.source_dependencies
    manifest = reviewed_manifest("greenchain")
    assert manifest.license.spdx == "LICENSE_UNKNOWN" and not manifest.license.source_reused
    assert not manifest.permissions.network and manifest.runtime.mode == "builtin"
    assert sdk_result.raw_result["response"]  # kept outside ECHO's bounded normalized artifact


def test_bridge_rejects_invented_evidence_link():
    result = asyncio.run(GreenChainProvider(ReferenceSourceClient("greenchain"), mode="reference").execute(request()))
    result.entities[0].attributes["claims"][0]["evidence_ids"] = ["missing-evidence"]
    with pytest.raises(ValueError, match="missing evidence"):
        to_echo_result(result)
