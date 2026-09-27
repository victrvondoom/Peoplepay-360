"""Tests for the gateway's security boundary.

`phase-1-4-report.md` §5 recorded "no rate limiting" as an open medium finding,
because Phase 4 had no request boundary to attach one to.  The gateway
(`c0539fe`) added that boundary, so the control is now testable -- and a limiter
that fronts money is worth pinning rather than trusting.

These tests drive `GatewayState` directly rather than binding a socket.  That is
what the class was made injectable for, and it keeps the suite offline and fast.
"""

from __future__ import annotations

import pytest

from adapters.base import Capability, CapabilityMode, HealthReport
from beacon.peoplepay import Transaction
from gateway.app import (
    RATE_LIMIT,
    RATE_WINDOW_SECONDS,
    GatewayState,
    build_capabilities,
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
