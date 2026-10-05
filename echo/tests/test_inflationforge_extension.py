"""Synthetic local HTTP receipts exercise the real InflationForge adapter boundary."""

from __future__ import annotations

import asyncio
import json
import threading
from contextlib import contextmanager
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest
import yaml

from echo.extensions.adapters.inflationforge import InflationForgeAdapter
from echo.extensions.contracts import ExtensionManifest, ExtensionRequest
from echo.extensions.transport import ExtensionTransportError


def manifest() -> ExtensionManifest:
    path = Path(__file__).resolve().parents[2] / "extensions" / "inflationforge" / "extension.yaml"
    return ExtensionManifest.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def receipt(**changes: Any) -> dict[str, Any]:
    row = {
        "id": "observation-001", "snapshot_id": "snapshot-001", "item_id": "milk", "city_id": "austin",
        "year": 2026, "price_usd": 3.125, "currency": "USD", "kind": "LIVE",
        "observed_at": "2026-10-01T12:00:00Z", "retrieved_at": "2026-10-02T12:00:00Z",
        "source": "Public city price table", "source_url": "https://www.numbeo.com/cost-of-living/in/Austin?displayCurrency=USD",
        "raw_label": "Milk (1 liter)", "raw_price": 3.125, "conversion_multiplier": 1,
        "archive_timestamp": None,
    }
    row.update(changes)
    return row


def request(**changes: Any) -> ExtensionRequest:
    body = {"snapshot_id": "snapshot-001", "item_id": "milk", "city_id": "austin"}
    body.update(changes)
    return ExtensionRequest(request_id="price-request", capability="price_intelligence", input=body)


@contextmanager
def mock_service(rows: Any, *, provider: str | None = "LIVE PUBLIC WEB", health_status: str = "ok",
                 protocol: str = "HTTP/1.1"):
    calls: list[tuple[str, str]] = []
    class Handler(BaseHTTPRequestHandler):
        protocol_version = protocol
        def log_message(self, *_: Any) -> None:
            pass

        def do_GET(self) -> None:
            calls.append(("GET", self.path))
            body = {"status": health_status, "modes": {"price_provider": provider}} if self.path == "/health" else rows
            encoded = json.dumps(body).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def do_POST(self) -> None:
            calls.append(("POST", self.path))
            self.send_response(405)
            self.end_headers()

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.02), daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", calls
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def execute(rows: Any, monkeypatch: pytest.MonkeyPatch, *, envelope: ExtensionRequest | None = None,
            provider: str | None = "LIVE PUBLIC WEB"):
    with mock_service(rows, provider=provider) as (address, calls):
        monkeypatch.setenv("ECHO_EXT_INFLATIONFORGE_URL", address)
        result = asyncio.run(InflationForgeAdapter(manifest()).execute(envelope or request()))
        return result, calls


def test_manifest_limits_service_and_records_unproven_upstream_commit() -> None:
    reviewed = manifest()
    assert reviewed.enabled is False
    assert reviewed.license.spdx == "MIT" and reviewed.license.source_reused is False
    assert reviewed.upstream.commit is None
    assert reviewed.runtime.url_env == "ECHO_EXT_INFLATIONFORGE_URL"
    assert set(reviewed.graph.write) == {"Product", "Claim", "Evidence", "Source"}
    assert reviewed.permissions.network and not reviewed.permissions.subprocess and not reviewed.permissions.filesystem


def test_exact_scope_read_only_receipt_keeps_money_units_and_producer(monkeypatch: pytest.MonkeyPatch) -> None:
    result, calls = execute([receipt()], monkeypatch)
    assert calls == [("GET", "/health"), ("GET", "/api/snapshots/snapshot-001/observations?city_id=austin&item_id=milk")]
    assert result.extension_id == "inflationforge" and result.extension_version == "1.0.0"
    assert result.entities[0].type == "Product"
    assert result.entities[0].external_ids == {"upstream_item_id": "milk"}
    assert result.claims[0].predicate == "observed_price"
    assert result.claims[0].value["amount_minor"] == 313
    assert result.claims[0].value["currency"] == "USD"
    assert result.claims[0].value["city_id"] == "austin"
    assert result.claims[0].confidence is None and result.evidence[0].confidence is None
    assert result.confidence is None and result.model_provenance is None
    assert result.evidence[0].provenance_state == "KNOWN"
    assert result.sources[0].content_hash is None and result.sources[0].snapshot_text is None
    assert result.sources[0].cache_age_seconds == 86_400
    assert result.sources[0].observed_at.isoformat() == "2026-10-01T12:00:00+00:00"
    assert result.sources[0].original_observed_at == result.evidence[0].observed_at
    assert "UPSTREAM_FLOAT_AMOUNT_ROUNDED_TO_MINOR_UNITS" in result.warnings
    assert "CITY_PRICE_OBSERVATION_NOT_SUPPLIER_QUOTE" in result.warnings
    assert "verification_state" not in result.model_dump_json()


def test_historical_receipt_preserves_old_time_instead_of_refreshing_it(monkeypatch: pytest.MonkeyPatch) -> None:
    result, _ = execute([receipt(year=2025, kind="ARCHIVED", observed_at="2025-10-01T12:00:00Z",
                                 archive_timestamp="20251001120000")], monkeypatch)
    assert result.status == "partial"
    assert "HISTORICAL_OBSERVATION_NOT_CURRENT_QUOTE" in result.warnings
    assert result.evidence[0].observed_at.year == 2025
    assert result.sources[0].retrieved_at.year == 2026
    assert result.claims[0].value["archive_timestamp"] == "20251001120000"
    assert not result.source_dependencies  # An archive URL alone does not prove a provenance edge.


@pytest.mark.parametrize("change", [
    {"source_url": None}, {"source_url": "file:///C:/private"},
    {"source_url": "https://user:password@publisher.test/page"},
    {"observed_at": None}, {"observed_at": "2026-10-01T12:00:00"},
    {"retrieved_at": "invalid"}, {"source": None},
    {"retrieved_at": "2025-01-01T00:00:00Z"},
    {"observed_at": "2099-01-01T00:00:00Z", "retrieved_at": "2099-01-02T00:00:00Z"},
])
def test_incomplete_or_invalid_source_becomes_unknown_without_invented_facts(change, monkeypatch: pytest.MonkeyPatch) -> None:
    result, _ = execute([receipt(**change)], monkeypatch)
    assert result.sources[0].provenance_state == "PROVENANCE_UNKNOWN"
    assert result.claims[0].provenance_state == "PROVENANCE_UNKNOWN"
    assert result.evidence[0].provenance_state == "PROVENANCE_UNKNOWN"
    assert "SOURCE_UNKNOWN" in result.warnings
    assert result.sources[0].content_hash is None


@pytest.mark.parametrize("change", [
    {"currency": "INR"}, {"price_usd": 0}, {"price_usd": -1},
    {"price_usd": "3.12"}, {"price_usd": 0.001}, {"price_usd": True},
    {"year": "2026"}, {"city_id": "other-city"},
    {"snapshot_id": "other-snapshot"}, {"item_id": "iphone"},
    {"new_unreviewed_field": "schema drift"}, {"extension_id": "producer-spoof"},
])
def test_bad_amount_currency_scope_schema_and_producer_are_rejected(change, monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ExtensionTransportError) as error:
        execute([receipt(**change)], monkeypatch)
    assert error.value.code == "INVALID_OUTPUT"


def test_malformed_array_and_duplicate_receipts_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    for rows in ({"results": [receipt()]}, [None], [receipt(), deepcopy(receipt())]):
        with pytest.raises(ExtensionTransportError) as error:
            execute(rows, monkeypatch)
        assert error.value.code == "INVALID_OUTPUT"


def test_empty_untracked_item_returns_visible_gap_no_price(monkeypatch: pytest.MonkeyPatch) -> None:
    result, calls = execute([], monkeypatch, envelope=request(item_id="iphone"))
    assert result.status == "partial" and "NOT_TRACKED_OR_NO_OBSERVATIONS" in result.warnings
    assert not result.entities and not result.claims and not result.evidence and not result.sources
    assert calls[-1][1].endswith("item_id=iphone")


@pytest.mark.parametrize("provider", ["JINA LIVE READER FALLBACK", "LOCAL CACHE", "SAMPLE", None])
def test_provider_mode_warning_does_not_launder_real_receipts_or_fabricate_synthetic_data(provider, monkeypatch: pytest.MonkeyPatch) -> None:
    result, _ = execute([receipt()], monkeypatch, provider=provider)
    assert result.status == "partial" and result.claims[0].kind == "fact"
    assert result.sources[0].provenance_state == "PROVENANCE_UNKNOWN"
    assert result.evidence[0].confidence is None
    assert "synthetic" not in result.model_dump_json()


def test_only_explicit_source_receipt_hash_survives(monkeypatch: pytest.MonkeyPatch) -> None:
    result, _ = execute([receipt(source_content_hash="a" * 64)], monkeypatch)
    assert result.sources[0].content_hash == "a" * 64
    assert result.sources[0].snapshot_text is None
    assert result.evidence[0].content_hash is None  # Receipt description is not publisher capture text.
    assert "SOURCE_CAPTURE_HASH_UPSTREAM_ASSERTED" in result.warnings


def test_invalid_request_cannot_select_other_paths_or_mutate_service(monkeypatch: pytest.MonkeyPatch) -> None:
    with mock_service([receipt()]) as (address, calls):
        monkeypatch.setenv("ECHO_EXT_INFLATIONFORGE_URL", address)
        adapter = InflationForgeAdapter(manifest())
        for invalid in (request(snapshot_id="../../sync"), request(url="http://private/"), request(item_id=123)):
            with pytest.raises(ExtensionTransportError) as error:
                asyncio.run(adapter.execute(invalid))
            assert error.value.code == "INVALID_INPUT"
        assert calls == []


def test_health_reports_provider_review_and_rejects_degraded_service(monkeypatch: pytest.MonkeyPatch) -> None:
    with mock_service([], provider="LIVE READER FALLBACK") as (address, _):
        monkeypatch.setenv("ECHO_EXT_INFLATIONFORGE_URL", address)
        health = asyncio.run(InflationForgeAdapter(manifest()).health())
        assert health.status == "healthy" and "requires review" in health.message
    with mock_service([], health_status="degraded") as (address, _):
        monkeypatch.setenv("ECHO_EXT_INFLATIONFORGE_URL", address)
        with pytest.raises(ExtensionTransportError) as error:
            asyncio.run(InflationForgeAdapter(manifest()).execute(request()))
        assert error.value.code == "EXTENSION_UNAVAILABLE"


def test_http_10_service_can_return_bounded_array_receipts(monkeypatch: pytest.MonkeyPatch) -> None:
    with mock_service([receipt()], protocol="HTTP/1.0") as (address, _):
        monkeypatch.setenv("ECHO_EXT_INFLATIONFORGE_URL", address)
        result = asyncio.run(InflationForgeAdapter(manifest()).execute(request()))
        assert result.claims[0].value["amount_minor"] == 313
