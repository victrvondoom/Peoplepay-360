"""What the integration layer promises, as tests.

One class per promise.  These are the claims a reader should be able to check
without trusting a commit message: that a gap is never filled with a guess, that
sandbox data cannot fund a real decision, that one transaction id correlates
everything, and that the HTTP surface refuses what it should.
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

import pytest

from adapters.base import CapabilityMode, CapabilityResult
from adapters.bridge import (
    SLOT_FOR_CAPABILITY,
    SOURCE_TYPE_FOR_CAPABILITY,
    attach_capability_result,
)
from adapters.market import MarketAdapter, money_from_float
from adapters.spatial import RUMI_DOOR_CLEARANCE_M, RoomContext, SpatialAdapter
from beacon.assurance import EventKind, EvidenceClass, IntentMandate, Money
from beacon.peoplepay.authority import Permission, TransactionType
from beacon.peoplepay.nodes import DECISION_CAPABLE_SOURCES, SourceType
from beacon.peoplepay.transaction import CONTEXT_SLOTS, Transaction
from gateway.app import GatewayState
from transaction.eventbus import EventBus
from transaction.store import (
    InMemoryTransactionStore,
    JsonSnapshotStore,
    TransactionNotFound,
)

UTTERANCE = "upgrade my room for 50000 rupees"


def _txn(user: str = "u1") -> Transaction:
    txn = Transaction.create(
        user_id=user, raw_utterance=UTTERANCE, transaction_type=TransactionType.PURCHASE
    )
    txn.capture_intent(
        IntentMandate.create(
            user_id=user,
            raw_utterance=UTTERANCE,
            product_query="desk",
            max_amount=Money.of("50000", "INR"),
        ),
        normalized_intent="furnish a room, ceiling INR 50000",
    )
    return txn


class TestMoneyCrossesTheFloatBoundaryHonestly:
    """InflationForge stores prices as floats; Money refuses floats."""

    def test_a_float_price_converts_exactly_via_its_decimal_form(self) -> None:
        money, note = money_from_float(4.29, "USD")
        assert money == Money(429, "USD")
        assert money.major == Decimal("4.29")
        assert "float" in note

    def test_the_float_origin_is_recorded_rather_than_forgotten(self) -> None:
        _, note = money_from_float(6.7, "USD")
        assert note, "a float-derived amount must say so"

    def test_a_string_amount_carries_no_float_warning(self) -> None:
        _, note = money_from_float("6.70", "USD")
        assert note == ""

    def test_inr_uses_two_minor_digits(self) -> None:
        assert money_from_float(79999.0, "INR")[0] == Money(7_999_900, "INR")

    def test_an_unrepresentable_amount_raises_instead_of_rounding(self) -> None:
        with pytest.raises(ValueError):
            money_from_float(float("nan"), "USD")


class TestPriceEvidenceIsEvidenceNotAdvice:
    """Sec. 12: show the observed range and a code, never a recommendation."""

    @staticmethod
    def _verified_observations(adapter: MarketAdapter) -> tuple[Any, ...]:
        return tuple(
            adapter.observe(
                "observed_price",
                Money.of(amount, "INR").to_dict(),
                evidence_class=EvidenceClass.VERIFIED,
                source_url=f"https://shop.example/{index}",
            )
            for index, amount in enumerate(
                ["74999", "78500", "79999", "82999", "78000"]
            )
        )

    @pytest.fixture
    def live_market(self) -> MarketAdapter:
        return MarketAdapter("http://127.0.0.1:1", mode_override=CapabilityMode.LIVE)

    def test_a_quote_inside_the_observed_range_is_named_as_such(
        self, live_market: MarketAdapter
    ) -> None:
        assessment = live_market.price_assessment(
            Money.of("79999", "INR"), self._verified_observations(live_market)
        )
        assert assessment.code == "PRICE_WITHIN_EXPECTED_RANGE"
        assert assessment.observed_median == Money.of("78500", "INR")
        assert assessment.delta_vs_median_pct == Decimal("1.9")
        assert assessment.sample_size == 5

    def test_a_quote_above_every_observation_is_flagged(
        self, live_market: MarketAdapter
    ) -> None:
        assessment = live_market.price_assessment(
            Money.of("91000", "INR"), self._verified_observations(live_market)
        )
        assert assessment.code == "PRICE_ABOVE_OBSERVED_RANGE"

    def test_a_quote_below_every_observation_is_flagged(
        self, live_market: MarketAdapter
    ) -> None:
        assessment = live_market.price_assessment(
            Money.of("70000", "INR"), self._verified_observations(live_market)
        )
        assert assessment.code == "PRICE_BELOW_OBSERVED_RANGE"

    def test_no_evidence_yields_insufficient_rather_than_a_verdict(
        self, live_market: MarketAdapter
    ) -> None:
        assessment = live_market.price_assessment(Money.of("100", "INR"), ())
        assert assessment.code == "INSUFFICIENT_EVIDENCE"
        assert assessment.observed_median is None

    def test_cross_currency_evidence_is_refused_not_converted(
        self, live_market: MarketAdapter
    ) -> None:
        """No FX rate is ever invented (Sec. 11)."""
        usd = (
            live_market.observe(
                "observed_price",
                Money.of("6.70", "USD").to_dict(),
                evidence_class=EvidenceClass.VERIFIED,
            ),
        )
        assessment = live_market.price_assessment(Money.of("500", "INR"), usd)
        assert assessment.code == "INSUFFICIENT_EVIDENCE"
        assert "currency" in assessment.note

    def test_sandbox_observations_cannot_settle_a_price(self) -> None:
        sandbox = MarketAdapter(
            "http://127.0.0.1:1", mode_override=CapabilityMode.SANDBOX
        )
        observations = tuple(
            sandbox.observe(
                "observed_price",
                Money.of(a, "INR").to_dict(),
                evidence_class=EvidenceClass.VERIFIED,
            )
            for a in ["74999", "78500", "79999"]
        )
        assert all(o.evidence_class is EvidenceClass.SANDBOX for o in observations)
        assessment = sandbox.price_assessment(Money.of("79999", "INR"), observations)
        assert assessment.code == "INSUFFICIENT_EVIDENCE"


class TestAnUnreachableProviderNeverFabricates:
    """Sec. 24: report the mode, never a plausible-looking value."""

    def test_an_unconfigured_market_reports_not_configured(self) -> None:
        report = MarketAdapter("").health()
        assert report.mode is CapabilityMode.NOT_CONFIGURED
        assert "BEACON_MARKET_URL" in report.missing_config
        assert not report.decision_grade

    def test_an_unreachable_market_reports_unavailable_not_empty(self) -> None:
        report = MarketAdapter("http://127.0.0.1:1", timeout=0.05).health()
        assert report.mode is CapabilityMode.UNAVAILABLE
        assert report.detail

    def test_a_missing_value_carries_no_number(self) -> None:
        result = MarketAdapter("").price_evidence(item_query="milk")
        assert result.gaps == ("observed_price",)
        assert all(o.value is None for o in result.observations)
        assert all(
            o.evidence_class is EvidenceClass.UNAVAILABLE for o in result.observations
        )

    def test_health_never_raises_even_when_the_endpoint_is_nonsense(self) -> None:
        assert MarketAdapter("not-a-url").health().mode is CapabilityMode.UNAVAILABLE


class TestRoomGeometryIsNeverGuessed:
    def test_a_room_missing_a_dimension_raises(self, sample_room: dict) -> None:
        del sample_room["dimensions"]["depth"]
        with pytest.raises(ValueError, match="refusing to substitute"):
            RoomContext.from_rumi(sample_room)

    def test_confirmed_measurements_are_verified_evidence(
        self, sample_room: dict
    ) -> None:
        result = SpatialAdapter(mode_override=CapabilityMode.LIVE).room_context(
            sample_room
        )
        assert any(
            o.evidence_class is EvidenceClass.VERIFIED for o in result.observations
        )

    def test_estimated_measurements_are_weaker_than_confirmed(
        self, sample_room: dict
    ) -> None:
        sample_room["measurementSource"] = "estimated"
        result = SpatialAdapter(mode_override=CapabilityMode.LIVE).room_context(
            sample_room
        )
        assert all(
            o.evidence_class is not EvidenceClass.VERIFIED for o in result.observations
        )

    def test_the_rooms_own_door_width_sets_the_keepout(self, sample_room: dict) -> None:
        sample_room["openings"][0]["width"] = 1.4
        assert RoomContext.from_rumi(sample_room).door_keepout_m == 1.4

    def test_a_room_with_no_captured_door_still_reserves_the_default(
        self, sample_room: dict
    ) -> None:
        """Assuming no doorway is the optimistic guess that blocks one."""
        sample_room["openings"] = []
        assert RoomContext.from_rumi(sample_room).door_keepout_m == (
            RUMI_DOOR_CLEARANCE_M
        )

    def test_the_budget_keeps_rumis_currency(
        self, sample_room: dict, usd_brief: dict
    ) -> None:
        context = RoomContext.from_rumi(sample_room, brief=usd_brief)
        assert context.budget == Money(8_000_000, "USD")

    def test_owned_objects_are_identified_so_they_are_not_rebought(
        self, sample_room: dict
    ) -> None:
        assert RoomContext.from_rumi(sample_room).owned_object_ids == ("owned-bed",)


class TestPlacementScreeningIsNecessaryNotSufficient:
    @pytest.fixture
    def context(self, sample_room: dict) -> RoomContext:
        return RoomContext.from_rumi(sample_room)

    @pytest.fixture
    def adapter(self) -> SpatialAdapter:
        return SpatialAdapter(mode_override=CapabilityMode.LIVE)

    def test_an_oversized_product_is_rejected(
        self, adapter: SpatialAdapter, context: RoomContext
    ) -> None:
        result = adapter.placement_check(
            context=context,
            product_id="too-wide",
            dimensions_m={"width": 5.0, "depth": 0.6, "height": 2.0},
        )
        assert result.payload["verdict"] == "DOES_NOT_FIT"
        assert result.payload["failures"][0]["constraint"] == "fits_room_width"

    def test_a_product_that_would_eat_the_door_approach_is_rejected(
        self, adapter: SpatialAdapter, context: RoomContext
    ) -> None:
        result = adapter.placement_check(
            context=context,
            product_id="too-deep",
            dimensions_m={"width": 1.0, "depth": 3.6, "height": 1.0},
        )
        assert result.payload["verdict"] == "DOES_NOT_FIT"

    def test_a_passing_product_is_only_not_ruled_out(
        self, adapter: SpatialAdapter, context: RoomContext
    ) -> None:
        """Rumi owns the authoritative verdict; we must not claim it."""
        result = adapter.placement_check(
            context=context,
            product_id="desk",
            dimensions_m={"width": 1.2, "depth": 0.6, "height": 0.75},
        )
        assert result.payload["verdict"] == "NOT_RULED_OUT"
        assert result.payload["authoritative"] is False
        assert "findFreeFloorAreas" in result.payload["authority"]

    def test_unknown_dimensions_are_not_a_pass(
        self, adapter: SpatialAdapter, context: RoomContext
    ) -> None:
        result = adapter.placement_check(
            context=context, product_id="mystery", dimensions_m=None
        )
        assert result.payload["verdict"] == "UNKNOWN_DIMENSIONS"
        assert result.payload["placeable"] is False
        assert result.gaps == ("product_dimensions_m",)


class TestOneTransactionCorrelatesEveryCapability:
    def test_every_capability_maps_to_a_real_context_slot(self) -> None:
        for capability, slot in SLOT_FOR_CAPABILITY.items():
            assert slot in CONTEXT_SLOTS, f"{capability} -> {slot}"

    def test_an_unknown_capability_raises_rather_than_defaulting(self) -> None:
        txn = _txn()
        bogus = CapabilityResult(capability="telepathy", mode=CapabilityMode.LIVE)
        with pytest.raises(ValueError, match="no declared context slot"):
            attach_capability_result(txn, bogus)

    def test_a_live_result_becomes_evidence_on_the_transaction(
        self, stub_capability: Any
    ) -> None:
        txn = _txn()
        result = stub_capability(CapabilityMode.LIVE).price_evidence(item_query="milk")
        node_id = attach_capability_result(txn, result)
        assert node_id is not None
        assert txn.context["market"]["available"] is True
        assert txn.graph.get(node_id).payload["source_type"] == str(
            SOURCE_TYPE_FOR_CAPABILITY["market"]
        )

    def test_an_unconfigured_result_records_the_gap_and_no_finding(
        self, stub_capability: Any
    ) -> None:
        txn = _txn()
        result = stub_capability(CapabilityMode.NOT_CONFIGURED).price_evidence(
            item_query="milk"
        )
        assert attach_capability_result(txn, result) is None
        slot = txn.context["market"]
        assert slot["available"] is False
        assert slot["mode"] == "NOT_CONFIGURED"

    def test_a_sandbox_result_is_retyped_so_it_cannot_decide(
        self, stub_capability: Any
    ) -> None:
        txn = _txn()
        result = stub_capability(CapabilityMode.SANDBOX).price_evidence(
            item_query="milk"
        )
        node_id = attach_capability_result(txn, result)
        source_type = txn.graph.get(node_id).payload["source_type"]
        assert source_type == str(SourceType.SANDBOX)
        assert SourceType.SANDBOX not in DECISION_CAPABLE_SOURCES

    def test_market_is_a_listing_not_a_primary_source(self) -> None:
        """A published price table states an asking price, not a paid one."""
        assert SOURCE_TYPE_FOR_CAPABILITY["market"] is SourceType.MARKETPLACE_LISTING
        assert SourceType.MARKETPLACE_LISTING not in DECISION_CAPABLE_SOURCES

    def test_evidence_does_not_grant_payment_permission(
        self, stub_capability: Any
    ) -> None:
        txn = _txn()
        attach_capability_result(
            txn, stub_capability(CapabilityMode.LIVE).price_evidence(item_query="milk")
        )
        assert txn.permissions.allows(Permission.DISCOVERY)
        assert not txn.permissions.allows(Permission.PAYMENT)

    def test_the_ledger_chain_survives_every_attachment(
        self, stub_capability: Any
    ) -> None:
        txn = _txn()
        for mode in (
            CapabilityMode.LIVE,
            CapabilityMode.SANDBOX,
            CapabilityMode.UNAVAILABLE,
        ):
            attach_capability_result(
                txn, stub_capability(mode).price_evidence(item_query="milk")
            )
        intact, message = txn.ledger.verify_chain()
        assert intact, message


class TestTheEventBusKeepsCorrelation:
    def test_an_uncorrelated_event_is_refused(self) -> None:
        with pytest.raises(ValueError, match="must name its transaction"):
            EventBus().publish(
                EventKind.AGENT_ACTION, transaction_id="  ", source="x", actor="y"
            )

    def test_an_anonymous_event_is_refused(self) -> None:
        with pytest.raises(ValueError, match="must name an actor"):
            EventBus().publish(
                EventKind.AGENT_ACTION, transaction_id="txn-1", source="x", actor=" "
            )

    def test_a_broken_subscriber_is_reported_and_does_not_halt_the_path(self) -> None:
        bus = EventBus()
        delivered: list[str] = []

        def explodes(event: Any) -> None:
            raise RuntimeError("boom")

        bus.subscribe_all(explodes)
        bus.subscribe_all(lambda event: delivered.append(event.event_id))
        txn = _txn()
        bus.publish_ledger_tail(txn.ledger, source="test")
        assert delivered, "a later subscriber still ran"
        assert bus.failures and "boom" in bus.failures[0]["error"]

    def test_ledger_events_mirror_with_their_sequence_and_hash(self) -> None:
        bus = EventBus()
        txn = _txn()
        events = bus.publish_ledger_tail(txn.ledger, source="beacon-core")
        assert [e.ledger_seq for e in events] == list(range(1, len(txn.ledger) + 1))
        assert all(e.ledger_hash for e in events)
        assert all(e.transaction_id == txn.transaction_id for e in events)

    def test_only_new_events_are_mirrored_on_a_second_pass(self) -> None:
        bus = EventBus()
        txn = _txn()
        first = bus.publish_ledger_tail(txn.ledger, source="a")
        again = bus.publish_ledger_tail(
            txn.ledger, source="a", since_seq=len(txn.ledger)
        )
        assert first and not again


class TestTheStoreHoldsOneAggregatePerId:
    def test_a_missing_transaction_raises_a_named_error(self) -> None:
        with pytest.raises(TransactionNotFound):
            InMemoryTransactionStore().get("txn-nope")

    def test_two_different_objects_cannot_share_one_id(self) -> None:
        store = InMemoryTransactionStore()
        first = _txn()
        store.put(first)
        clash = Transaction.create(
            user_id="u1",
            raw_utterance=UTTERANCE,
            transaction_id=first.transaction_id,
        )
        with pytest.raises(ValueError, match="one aggregate per id"):
            store.put(clash)

    def test_users_are_isolated(self) -> None:
        store = InMemoryTransactionStore()
        store.put(_txn("alice"))
        store.put(_txn("bob"))
        assert len(store.for_user("alice")) == 1
        assert len(store.for_user("carol")) == 0

    def test_integrity_is_verified_across_the_whole_store(self) -> None:
        store = InMemoryTransactionStore()
        store.put(_txn())
        assert store.verify_all() == {}

    def test_a_snapshot_is_written_as_plain_data(self, tmp_path: Any) -> None:
        txn = _txn()
        path = JsonSnapshotStore(tmp_path).write(txn)
        body = json.loads(path.read_text(encoding="utf-8"))
        assert body["transaction_id"] == txn.transaction_id
        assert body["raw_utterance"] == UTTERANCE


class TestTheGatewayReportsHonestly:
    def test_an_unconfigured_capability_is_listed_not_hidden(self) -> None:
        state = GatewayState(capabilities={"spatial": SpatialAdapter("")})
        report = state.integrations()
        assert report["capabilities"][0]["mode"] == "NOT_CONFIGURED"
        assert report["summary"]["total"] == 1

    def test_a_capability_whose_health_raises_is_reported_unavailable(
        self, stub_capability: Any
    ) -> None:
        state = GatewayState(
            capabilities={"market": stub_capability(raises=True, name="market")}
        )
        report = state.integrations()
        assert report["capabilities"][0]["mode"] == "UNAVAILABLE"
        assert "raised" in report["capabilities"][0]["detail"]

    def test_sandbox_capabilities_do_not_make_the_system_money_ready(
        self, stub_capability: Any
    ) -> None:
        state = GatewayState(
            capabilities={"market": stub_capability(CapabilityMode.SANDBOX)}
        )
        report = state.integrations()
        assert report["summary"]["decision_grade"] == 0
        assert report["real_money_ready"] is False

    def test_a_live_non_payment_capability_is_still_not_money_ready(
        self, stub_capability: Any
    ) -> None:
        """Only a live payment provider can make this true."""
        state = GatewayState(
            capabilities={"market": stub_capability(CapabilityMode.LIVE)}
        )
        assert state.integrations()["real_money_ready"] is False

    def test_the_rate_limiter_refuses_past_the_window(self) -> None:
        state = GatewayState(capabilities={})
        allowed = sum(1 for _ in range(70) if state.allow_request("caller"))
        assert allowed == 60

    def test_rate_limits_are_per_caller(self) -> None:
        state = GatewayState(capabilities={})
        for _ in range(60):
            state.allow_request("noisy")
        assert state.allow_request("noisy") is False
        assert state.allow_request("quiet") is True
