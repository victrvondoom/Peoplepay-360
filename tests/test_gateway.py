"""Tests for the gateway's security boundary.

`phase-1-4-report.md` §5 recorded "no rate limiting" as an open medium finding,
because Phase 4 had no request boundary to attach one to.  The gateway
(`c0539fe`) added that boundary, so the control is now testable -- and a limiter
that fronts money is worth pinning rather than trusting.

These tests drive `GatewayState` directly rather than binding a socket.  That is
what the class was made injectable for, and it keeps the suite offline and fast.
"""

from __future__ import annotations

import http.client
import io
import json
import os
import threading
from contextlib import contextmanager
from http.server import ThreadingHTTPServer
from types import SimpleNamespace
from typing import Any, cast

import pytest

from adapters.base import (
    Capability,
    CapabilityMode,
    HealthReport,
    MarketCapability,
    PropertyCapability,
    ResolutionCapability,
    SpatialCapability,
)
from beacon.peoplepay import Transaction
from gateway.app import (
    DRAIN_LIMIT,
    MAX_BODY_BYTES,
    RATE_LIMIT,
    RATE_WINDOW_SECONDS,
    GatewayState,
    _env_float,
    _env_int,
    build_capabilities,
    config_warnings,
    make_handler,
)

TAMIL = "எனக்கு ₹50,000 குள்ள ஒரு நல்ல laptop தேவை."


@pytest.fixture(autouse=True)
def _no_provider_env(monkeypatch):
    for var in ("BEACON_MARKET_URL", "BEACON_SPATIAL_URL", "BEACON_RUMI_URL"):
        monkeypatch.delenv(var, raising=False)


class TestRateLimiting:
    """§26: the surface that fronts money must not be unlimited."""

    def test_requests_under_the_limit_are_allowed(self):
        state = GatewayState(capabilities={})
        assert all(state.allow_request("user-a") for _ in range(RATE_LIMIT))

    def test_the_request_after_the_limit_is_refused(self):
        state = GatewayState(capabilities={})
        for _ in range(RATE_LIMIT):
            state.allow_request("user-a")
        assert state.allow_request("user-a") is False

    def test_the_limit_is_per_caller_not_global(self):
        """One noisy user must not lock everyone else out."""
        state = GatewayState(capabilities={})
        for _ in range(RATE_LIMIT):
            state.allow_request("user-a")
        assert state.allow_request("user-a") is False
        assert state.allow_request("user-b") is True

    def test_the_window_slides(self, monkeypatch):
        """Old hits expire, so a limited caller recovers rather than being banned."""
        import gateway.app as app

        clock = {"now": 1000.0}
        monkeypatch.setattr(app.time, "monotonic", lambda: clock["now"])
        state = GatewayState(capabilities={})
        for _ in range(RATE_LIMIT):
            state.allow_request("user-a")
        assert state.allow_request("user-a") is False
        clock["now"] += RATE_WINDOW_SECONDS + 1
        assert state.allow_request("user-a") is True

    def test_the_limiter_is_thread_safe_under_contention(self):
        """The gateway serves concurrently; a racy counter would over-admit."""
        import threading

        state = GatewayState(capabilities={})
        admitted: list[bool] = []
        lock = threading.Lock()

        def hammer() -> None:
            for _ in range(40):
                ok = state.allow_request("user-a")
                with lock:
                    admitted.append(ok)

        threads = [threading.Thread(target=hammer) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        # Exactly RATE_LIMIT admissions, never more, regardless of interleaving.
        assert sum(admitted) == RATE_LIMIT


class TestHealthReporting:
    """§25: the health page must not be a lie by omission."""

    def test_an_unconfigured_capability_is_still_listed(self):
        report = GatewayState().integrations()
        names = {c["name"] for c in report["capabilities"]}
        assert {"market", "spatial", "property"} <= names

    def test_nothing_is_decision_grade_without_a_live_provider(self):
        report = GatewayState().integrations()
        assert report["summary"]["decision_grade"] == 0
        assert report["summary"]["usable"] == 0

    def test_a_raising_health_check_is_reported_not_propagated(self):
        """A broken adapter must not take the health page down."""

        class Exploding(Capability):
            name = "market"
            upstream = "test"

            def health(self) -> HealthReport:
                raise RuntimeError("provider client blew up")

        report = GatewayState(capabilities={"market": Exploding()}).integrations()
        entry = report["capabilities"][0]
        assert entry["mode"] == str(CapabilityMode.UNAVAILABLE)
        assert entry["usable"] is False
        assert "blew up" in entry["detail"]

    def test_a_live_capability_is_counted_as_decision_grade(self):
        class Live(Capability):
            name = "market"
            upstream = "test"

            def health(self) -> HealthReport:
                return HealthReport(name=self.name, mode=CapabilityMode.LIVE)

        report = GatewayState(capabilities={"market": Live()}).integrations()
        assert report["summary"]["decision_grade"] == 1

    def test_a_sandbox_capability_is_usable_but_not_decision_grade(self):
        class Sandboxed(Capability):
            name = "market"
            upstream = "test"

            def health(self) -> HealthReport:
                return HealthReport(name=self.name, mode=CapabilityMode.SANDBOX)

        report = GatewayState(capabilities={"market": Sandboxed()}).integrations()
        assert report["summary"]["usable"] == 1
        assert report["summary"]["decision_grade"] == 0

    def test_build_capabilities_lists_both_adapters(self):
        assert {"market", "spatial", "property"} <= set(build_capabilities())


class TestUnauthenticatedHealthSurface:
    """`/health/integrations` is served before the auth check, by design.

    That is defensible for liveness, but it means whatever the payload contains
    is public.  These tests pin what it exposes today so that a future change
    which starts leaking internal endpoints fails here rather than in production.

    Recorded as an open finding in `phase-1-4-report.md` §5 rather than fixed in
    passing: moving the auth check is the gateway author's call.
    """

    def test_no_secret_shaped_values_are_exposed(self):
        report = GatewayState().integrations()
        blob = repr(report).lower()
        # The OPEN-mode warning legitimately names BEACON_GATEWAY_SECRET as a
        # variable that is *unset*; naming a missing setting is the point of
        # that message. What must never appear is a value.
        for marker in ("password=", "secret=", "token=", "api_key=", "bearer "):
            assert marker not in blob
        assert "v1." not in blob, "an issued token must never reach this payload"

    def test_the_public_payload_never_carries_an_endpoint(self):
        """Fixed: endpoint is withheld from the unauthenticated health page."""
        report = GatewayState().integrations()
        assert all("endpoint" not in c for c in report["capabilities"])

    def test_a_configured_internal_host_is_not_disclosed(self, monkeypatch):
        """The exposure this test used to document has been closed.

        An internal hostname is a map of the private network. The health page is
        unauthenticated on purpose -- an operator must reach it mid-incident --
        so the host is withheld and only its presence is reported.
        """
        monkeypatch.setenv("BEACON_MARKET_URL", "http://internal-market.svc:8010")
        from adapters.market import MarketAdapter

        report = GatewayState(
            capabilities={"market": MarketAdapter(timeout=0.05)}
        ).integrations()
        row = report["capabilities"][0]
        assert "endpoint" not in row
        assert row["endpoint_configured"] is True
        assert "internal-market" not in repr(report)


class TestStoreIntegration:
    """The gateway must not become a second source of truth."""

    def test_transactions_are_scoped_to_the_caller(self):
        state = GatewayState(capabilities={})
        mine = Transaction.create(user_id="user-a", raw_utterance=TAMIL)
        theirs = Transaction.create(user_id="user-b", raw_utterance=TAMIL)
        state.store.put(mine)
        state.store.put(theirs)
        assert state.store.for_user("user-a") == (mine,)

    def test_the_gateway_shares_the_canonical_aggregate(self):
        state = GatewayState(capabilities={})
        tx = Transaction.create(user_id="user-a", raw_utterance=TAMIL)
        state.store.put(tx)
        assert state.store.get(tx.transaction_id) is tx

    def test_a_fresh_transaction_cannot_pay_through_the_gateway_store(self):
        """The permission model survives being reached through the HTTP layer."""
        from beacon.peoplepay import Permission

        state = GatewayState(capabilities={})
        tx = Transaction.create(user_id="user-a", raw_utterance=TAMIL)
        state.store.put(tx)
        stored = state.store.get(tx.transaction_id)
        assert stored.permissions.allows(Permission.DISCOVERY) is True
        assert stored.permissions.allows(Permission.PAYMENT) is False


class TestBodyLimits:
    """A declared Content-Length is a claim, not an allocation budget.

    ``_body`` reads an attacker-controlled header.  Before this, a non-numeric
    value raised an unhandled ``ValueError`` out of ``int()``, and a large one
    was passed straight to ``rfile.read()`` -- so the header alone decided how
    much memory the gateway would try to take.  These pin both.

    The handler is driven unbound with a stub, which is how these paths are
    reached without binding a socket.
    """

    @staticmethod
    def _parse(headers, body=b""):
        handler = cast(Any, make_handler(GatewayState(capabilities={})))
        stub = SimpleNamespace(headers=headers, rfile=io.BytesIO(body))
        return handler._body(stub)

    def test_a_missing_content_length_is_an_empty_body(self):
        assert self._parse({}) == {}

    def test_a_blank_content_length_is_an_empty_body(self):
        assert self._parse({"Content-Length": "   "}) == {}

    def test_a_zero_content_length_is_an_empty_body(self):
        assert self._parse({"Content-Length": "0"}) == {}

    def test_a_valid_body_parses(self):
        raw = b'{"item_query": "laptop"}'
        assert self._parse({"Content-Length": str(len(raw))}, raw) == {
            "item_query": "laptop"
        }

    def test_a_non_numeric_content_length_is_a_caller_error(self):
        """Not an unhandled ValueError: the POST path turns this into a 400."""
        with pytest.raises(ValueError, match="not an integer"):
            self._parse({"Content-Length": "sixty"})

    def test_a_negative_content_length_is_refused(self):
        with pytest.raises(ValueError, match="negative"):
            self._parse({"Content-Length": "-1"})

    def test_a_body_over_the_limit_is_refused_by_its_declared_size(self):
        """The refusal is decided by the header, before any body is buffered.

        The oversized body is then drained rather than left in the socket -- see
        ``TestRefusalOnAReusedConnection`` for why -- so what this pins is that
        the *decision* needs only the header: the stub carries no body at all and
        the refusal still happens.
        """
        handler = cast(Any, make_handler(GatewayState(capabilities={})))
        stub = SimpleNamespace(
            headers={"Content-Length": str(MAX_BODY_BYTES + 1)},
            rfile=io.BytesIO(b""),
        )
        stub._drain = lambda length: None
        with pytest.raises(ValueError, match="exceeds"):
            handler._body(stub)

    def test_the_drain_is_bounded_rather_than_trusting_the_declared_length(self):
        """A client that declares a huge body must not make us read it all."""
        handler = cast(Any, make_handler(GatewayState(capabilities={})))
        # Far more data than DRAIN_LIMIT allows, so the cap is what stops it.
        rfile = io.BytesIO(b"x" * (DRAIN_LIMIT + 4096))
        stub = SimpleNamespace(headers={}, rfile=rfile)
        handler._drain(stub, DRAIN_LIMIT + 4096)
        assert rfile.tell() == DRAIN_LIMIT

    def test_the_drain_stops_early_when_the_client_sent_less(self):
        """A short body ends the drain rather than blocking on a closed stream."""
        handler = cast(Any, make_handler(GatewayState(capabilities={})))
        rfile = io.BytesIO(b"x" * 10)
        stub = SimpleNamespace(headers={}, rfile=rfile)
        handler._drain(stub, 100_000)
        assert rfile.tell() == 10

    def test_a_body_shorter_than_declared_is_reported_not_parsed(self):
        """A truncated body must not be reported as invalid JSON."""
        with pytest.raises(ValueError, match="declared"):
            self._parse({"Content-Length": "100"}, b'{"a": 1}')

    def test_invalid_json_is_a_caller_error(self):
        raw = b"{not json"
        with pytest.raises(ValueError, match="not valid JSON"):
            self._parse({"Content-Length": str(len(raw))}, raw)

    def test_a_json_scalar_is_refused(self):
        """The routes index into the body, so it has to be an object."""
        raw = b"42"
        with pytest.raises(ValueError, match="must be a JSON object"):
            self._parse({"Content-Length": str(len(raw))}, raw)


class TestEnvConfig:
    """Limits and timeouts come from the environment, and bad input is loud.

    The failure mode worth guarding is not a typo -- it is a typo that silently
    disables a control.  The readers keep the default and record why, so
    ``/health/integrations`` can say so.
    """

    def test_a_value_is_read_from_the_environment(self, monkeypatch):
        monkeypatch.setenv("BEACON_TEST_LIMIT", "5")
        assert _env_int("BEACON_TEST_LIMIT", 60) == 5

    def test_an_unset_value_uses_the_default(self, monkeypatch):
        monkeypatch.delenv("BEACON_TEST_LIMIT", raising=False)
        assert _env_int("BEACON_TEST_LIMIT", 60) == 60

    def test_a_blank_value_uses_the_default(self, monkeypatch):
        monkeypatch.setenv("BEACON_TEST_LIMIT", "  ")
        assert _env_int("BEACON_TEST_LIMIT", 60) == 60

    def test_an_unparseable_value_keeps_the_default_and_warns(self, monkeypatch):
        monkeypatch.setenv("BEACON_TEST_LIMIT", "sixty")
        assert _env_int("BEACON_TEST_LIMIT", 60) == 60
        assert any("BEACON_TEST_LIMIT" in w for w in config_warnings())

    def test_a_zero_limit_is_refused_rather_than_disabling_the_control(
        self, monkeypatch
    ):
        """A limit of 0 must not silently mean no requests, or no limit."""
        monkeypatch.setenv("BEACON_TEST_LIMIT", "0")
        assert _env_int("BEACON_TEST_LIMIT", 60) == 60
        assert any("BEACON_TEST_LIMIT" in w for w in config_warnings())

    def test_a_negative_limit_is_refused(self, monkeypatch):
        monkeypatch.setenv("BEACON_TEST_LIMIT", "-5")
        assert _env_int("BEACON_TEST_LIMIT", 60) == 60

    def test_a_float_timeout_is_read(self, monkeypatch):
        monkeypatch.setenv("BEACON_TEST_TIMEOUT", "2.5")
        assert _env_float("BEACON_TEST_TIMEOUT", 15.0) == 2.5

    def test_a_zero_timeout_is_refused(self, monkeypatch):
        """A zero timeout would make every upstream call fail instantly."""
        monkeypatch.setenv("BEACON_TEST_TIMEOUT", "0")
        assert _env_float("BEACON_TEST_TIMEOUT", 15.0) == 15.0

    def test_config_warnings_appear_on_the_health_page(self, monkeypatch):
        """An operator finds out from the health page, not only from the logs."""
        monkeypatch.setenv("BEACON_TEST_SURFACED", "not-a-number")
        _env_int("BEACON_TEST_SURFACED", 60)
        report = GatewayState(capabilities={}).integrations()
        assert any("BEACON_TEST_SURFACED" in w for w in report["config_warnings"])

    def test_adapter_timeouts_come_from_the_environment(self, monkeypatch):
        monkeypatch.setenv("BEACON_RESOLUTION_TIMEOUT", "3.5")
        assert getattr(build_capabilities()["resolution"], "timeout") == 3.5

    def test_adapter_timeouts_default_when_unset(self, monkeypatch):
        """An unset environment must not change the adapters' own defaults."""
        for var in (
            "BEACON_SPATIAL_TIMEOUT",
            "BEACON_MARKET_TIMEOUT",
            "BEACON_PROPERTY_TIMEOUT",
            "BEACON_RESOLUTION_TIMEOUT",
        ):
            monkeypatch.delenv(var, raising=False)
        built = build_capabilities()
        assert getattr(built["spatial"], "timeout") == 15.0
        assert getattr(built["market"], "timeout") == 15.0
        assert getattr(built["property"], "timeout") == 20.0
        assert getattr(built["resolution"], "timeout") == 60.0


class TestDispatchShapeChecking:
    """A route may only call an adapter that actually implements its shape.

    ``GatewayState(capabilities=...)`` is injectable, so the adapter behind a
    name is not guaranteed to be the one ``build_capabilities`` put there.  A
    mismatch has to read as a caller error (400), not as an upstream provider
    failure (502) -- the latter would blame a provider never contacted.
    """

    def test_each_built_adapter_satisfies_its_own_shape(self):
        built = build_capabilities()
        assert isinstance(built["spatial"], SpatialCapability)
        assert isinstance(built["market"], MarketCapability)
        assert isinstance(built["property"], PropertyCapability)
        assert isinstance(built["resolution"], ResolutionCapability)

    def test_an_adapter_missing_the_shape_is_not_accepted(self):
        """The negative case: presence of the method is what is checked."""
        assert not isinstance(build_capabilities()["market"], SpatialCapability)

    def test_a_wrong_shaped_adapter_is_a_caller_error_not_a_502(self):
        class Bare(Capability):
            name = "market"

            def health(self):
                return HealthReport(name=self.name, mode=CapabilityMode.LIVE)

        handler = cast(Any, make_handler(GatewayState(capabilities={"market": Bare()})))
        with pytest.raises(NotImplementedError, match="does not implement"):
            handler._dispatch(Bare(), "market", {"item_query": "laptop"})

    def test_an_unknown_capability_name_has_no_dispatch(self):
        handler = cast(Any, make_handler(GatewayState(capabilities={})))
        with pytest.raises(NotImplementedError, match="no gateway dispatch"):
            handler._dispatch(build_capabilities()["market"], "nope", {})


class TestRefusalOnAReusedConnection:
    """Refusing a body must not corrupt the connection it was refused on.

    ``_body`` rejects an oversized body *without reading it*, so those bytes are
    still in the request stream.  Under ``HTTP/1.1`` keep-alive the next request
    on that connection would start parsing mid-body.  Two things are therefore
    required, and only the pair is sufficient:

    * ``close_connection`` -- so the handler stops serving that socket, and
    * an explicit ``Connection: close`` header -- because ``send_response``
      advertises keep-alive for HTTP/1.1 regardless of that flag.  With the flag
      alone the server closes a socket the client still believes it may reuse,
      and the caller sees ``RemoteDisconnected`` on its *next* request.

    These tests drive ``http.client`` directly and reuse one connection across
    requests.  That reuse is the whole point: a client that opens a fresh
    connection each time (``urllib.request`` does) never reads the desynchronized
    socket and cannot observe the bug at all.
    """

    @staticmethod
    @contextmanager
    def _server(**env):
        """A gateway on an ephemeral port, with *env* applied to the module."""
        import importlib

        import gateway.app as app

        previous = {k: os.environ.get(k) for k in env}
        os.environ.update(env)
        try:
            importlib.reload(app)
            srv = ThreadingHTTPServer(
                ("127.0.0.1", 0), app.make_handler(app.GatewayState())
            )
            thread = threading.Thread(target=srv.serve_forever, daemon=True)
            thread.start()
            conn = http.client.HTTPConnection(
                "127.0.0.1", srv.server_address[1], timeout=10
            )
            try:
                yield conn
            finally:
                conn.close()
                srv.shutdown()
                srv.server_close()
                thread.join(timeout=5)
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
            importlib.reload(app)

    @staticmethod
    def _post(conn, path, payload, *, content_length=None):
        """POST on the shared connection; returns (status, body, will_close)."""
        headers = {"Content-Type": "application/json", "X-Beacon-User": "user-a"}
        if content_length is not None:
            headers["Content-Length"] = content_length
        conn.request("POST", path, json.dumps(payload), headers)
        response = conn.getresponse()
        will_close = response.will_close
        raw = response.read()
        return response.status, json.loads(raw), will_close

    def _open_transaction(self, conn):
        status, created, _ = self._post(conn, "/transactions", {"raw_utterance": TAMIL})
        assert status == 201
        return created["transaction_id"]

    def test_an_oversized_body_is_refused_and_says_the_connection_will_close(self):
        with self._server(BEACON_GATEWAY_MAX_BODY_BYTES="2048") as conn:
            tid = self._open_transaction(conn)
            status, body, will_close = self._post(
                conn,
                f"/transactions/{tid}/capabilities/market",
                {"item_query": "x" * 5000},
            )
            assert status == 400
            assert "exceeds" in body["error"]
            # Without the explicit header the client would believe it may reuse
            # a socket the server has already given up on.
            assert will_close is True

    def test_the_next_request_after_a_refusal_still_succeeds(self):
        """The refusal must be recoverable, not the end of the client's session."""
        with self._server(BEACON_GATEWAY_MAX_BODY_BYTES="2048") as conn:
            tid = self._open_transaction(conn)
            self._post(
                conn,
                f"/transactions/{tid}/capabilities/market",
                {"item_query": "x" * 5000},
            )
            # http.client honours Connection: close and reconnects underneath.
            status, body, _ = self._post(
                conn,
                f"/transactions/{tid}/capabilities/market",
                {"item_query": "laptop"},
            )
            assert status == 200
            # No endpoint is configured in the suite, so the honest answer is
            # NOT_CONFIGURED with a named gap -- never an invented price.
            assert body["mode"] == str(CapabilityMode.NOT_CONFIGURED)
            assert body["gaps"]

    def test_a_malformed_content_length_is_refused_the_same_way(self):
        with self._server(BEACON_GATEWAY_MAX_BODY_BYTES="2048") as conn:
            tid = self._open_transaction(conn)
            status, body, will_close = self._post(
                conn,
                f"/transactions/{tid}/capabilities/market",
                {"item_query": "laptop"},
                content_length="not-a-number",
            )
            assert status == 400
            assert "not an integer" in body["error"]
            assert will_close is True

    def test_an_accepted_body_keeps_the_connection_alive(self):
        """Only a refusal closes: the ordinary path must stay keep-alive."""
        with self._server(BEACON_GATEWAY_MAX_BODY_BYTES="2048") as conn:
            tid = self._open_transaction(conn)
            status, _, will_close = self._post(
                conn,
                f"/transactions/{tid}/capabilities/market",
                {"item_query": "laptop"},
            )
            assert status == 200
            assert will_close is False


@pytest.mark.parametrize("value", ["nan", "inf", "-inf"])
def test_timeout_rejects_nonfinite_values(monkeypatch, value):
    monkeypatch.setenv("BEACON_TEST_TIMEOUT", value)
    assert _env_float("BEACON_TEST_TIMEOUT", 15.0) == 15.0
