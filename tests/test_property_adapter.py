"""The property adapter, and the one thing it must never do.

InHeir's ten location scores come from an Azure OpenAI completion at
``temperature=0.7`` prompted with an address string -- no flood dataset, no
crime statistic, no air-quality feed (``inheir/routers/gis.py``).  The tests
below exist mainly to make that non-negotiable in code: a model's impression of
a neighbourhood must never reach the evidence graph as a measurement, and no
future edit should be able to promote one quietly.
"""

from __future__ import annotations

from typing import Any

import pytest

from adapters.base import CapabilityMode
from adapters.bridge import attach_capability_result
from adapters.property import MODEL_GENERATED_FIELDS, PropertyAdapter
from beacon.assurance import EvidenceClass, IntentMandate, Money
from beacon.peoplepay.authority import Permission, TransactionType
from beacon.peoplepay.nodes import DECISION_CAPABLE_SOURCES, SourceType
from beacon.peoplepay.transaction import Transaction

ADDRESS = "12 Nungambakkam High Road, Chennai 600034"

#: A response shaped exactly like InHeir's ``GISResponse``.  Synthetic values.
GIS_BODY: dict[str, Any] = {
    "coordinates": {"latitude": 13.0604, "longitude": 80.2496},
    "property_buying_risk": 0.42,
    "property_renting_risk": 0.31,
    "flood_risk": 0.66,
    "crime_rate": 0.28,
    "air_quality_index": 0.55,
    "proximity_to_amenities": 0.81,
    "transportation_score": 0.74,
    "neighborhood_rating": 0.69,
    "environmental_hazards": 0.22,
    "economic_growth_potential": 0.77,
}


def _live(monkeypatch: pytest.MonkeyPatch, response: Any) -> PropertyAdapter:
    """A property adapter pinned LIVE, with its transport stubbed."""
    adapter = PropertyAdapter("http://inheir.test", mode_override=CapabilityMode.LIVE)
    monkeypatch.setattr(
        PropertyAdapter, "_request", lambda *a, **k: response, raising=True
    )
    return adapter


def _txn(user: str = "u1") -> Transaction:
    utterance = "I want to buy this property"
    txn = Transaction.create(
        user_id=user,
        raw_utterance=utterance,
        transaction_type=TransactionType.PROPERTY,
    )
    txn.capture_intent(
        IntentMandate.create(
            user_id=user,
            raw_utterance=utterance,
            product_query="property",
            max_amount=Money.of("9000000", "INR"),
        ),
        normalized_intent="buy a property, ceiling INR 90 lakh",
    )
    return txn


class TestModelGeneratedScoresAreNeverEvidence:
    """The finding: these ten numbers have no dataset behind them."""

    def test_every_score_is_flagged_as_model_generated(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        result = _live(monkeypatch, GIS_BODY).location_intelligence(address=ADDRESS)
        assert result.payload["risk_is_model_generated"] is True
        assert "temperature=0.7" in result.payload["risk_generator"]
        assert set(result.payload["model_generated_fields"]) == MODEL_GENERATED_FIELDS

    def test_no_score_is_ever_decision_grade(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A fabricated number must not be usable by a deterministic policy."""
        result = _live(monkeypatch, GIS_BODY).location_intelligence(address=ADDRESS)
        scores = [o for o in result.observations if o.field in MODEL_GENERATED_FIELDS]
        assert len(scores) == len(MODEL_GENERATED_FIELDS)
        assert all(o.evidence_class is not EvidenceClass.VERIFIED for o in scores)

    def test_each_score_says_in_words_where_it_came_from(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        result = _live(monkeypatch, GIS_BODY).location_intelligence(address=ADDRESS)
        scores = [o for o in result.observations if o.field in MODEL_GENERATED_FIELDS]
        assert all("MODEL-GENERATED" in o.note for o in scores)
        assert all("not a measurement" in o.note for o in scores)

    def test_the_scores_are_not_folded_into_a_risk_number(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``policy._check_risk`` takes a risk score as advisory input.

        Feeding it a model's guess would give a real decision false precision, so
        no aggregate risk value is produced at all.
        """
        result = _live(monkeypatch, GIS_BODY).location_intelligence(address=ADDRESS)
        assert "risk_score" not in result.payload
        assert "aggregate_risk" not in result.payload
        # Confidence must not be derived from the fabricated numbers either.
        assert result.confidence == 0.5

    def test_a_high_flood_risk_does_not_become_a_transaction_verdict(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        body = {**GIS_BODY, "flood_risk": 0.99}
        result = _live(monkeypatch, body).location_intelligence(address=ADDRESS)
        assert "verdict" not in result.payload
        assert result.gaps == ()


class TestRealGeocodingIsTreatedAsEvidence:
    def test_coordinates_become_an_observation(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        result = _live(monkeypatch, GIS_BODY).location_intelligence(address=ADDRESS)
        coords = [o for o in result.observations if o.field == "coordinates"]
        assert coords and coords[0].value["latitude"] == 13.0604
        assert "OpenCage" in coords[0].note

    def test_a_failed_geocode_is_a_gap_not_a_zero(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        body = {k: v for k, v in GIS_BODY.items() if k != "coordinates"}
        result = _live(monkeypatch, body).location_intelligence(address=ADDRESS)
        assert result.gaps == ("coordinates",)
        coords = [o for o in result.observations if o.field == "coordinates"]
        assert coords[0].value is None
        assert coords[0].evidence_class is EvidenceClass.UNAVAILABLE

    def test_an_empty_address_is_refused_before_any_call(self) -> None:
        with pytest.raises(ValueError, match="address is required"):
            PropertyAdapter(
                "http://inheir.test", mode_override=CapabilityMode.LIVE
            ).location_intelligence(address="   ")


class TestCrowdsourcedReportsKeepTheirHumanVerdict:
    ROWS = [
        {"address": ADDRESS, "report": "boundary dispute", "verdict": "Verified"},
        {"address": ADDRESS, "report": "unclear title", "verdict": "Pending"},
        {"address": ADDRESS, "report": "not our land", "verdict": "Not Verified"},
        {"address": "9 Other Street, Chennai", "report": "x", "verdict": "Verified"},
    ]

    def test_a_verified_report_is_verified_evidence(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        result = _live(monkeypatch, self.ROWS).property_reports(address=ADDRESS)
        classes = {o.value["verdict"]: o.evidence_class for o in result.observations}
        assert classes["Verified"] is EvidenceClass.VERIFIED

    def test_an_unchecked_report_is_only_unverified(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        result = _live(monkeypatch, self.ROWS).property_reports(address=ADDRESS)
        classes = {o.value["verdict"]: o.evidence_class for o in result.observations}
        assert classes["Pending"] is EvidenceClass.UNVERIFIED

    def test_a_rejected_report_is_conflicting_not_absent(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A human looked and disagreed; that is a conflict, not a blank."""
        result = _live(monkeypatch, self.ROWS).property_reports(address=ADDRESS)
        classes = {o.value["verdict"]: o.evidence_class for o in result.observations}
        assert classes["Not Verified"] is EvidenceClass.CONFLICTING

    def test_another_propertys_dispute_is_not_attached(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        result = _live(monkeypatch, self.ROWS).property_reports(address=ADDRESS)
        assert result.payload["match_count"] == 3

    def test_address_punctuation_and_case_do_not_defeat_matching(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        result = _live(monkeypatch, self.ROWS).property_reports(
            address="12  NUNGAMBAKKAM HIGH ROAD,  CHENNAI 600034."
        )
        assert result.payload["match_count"] == 3

    def test_no_report_says_so_without_implying_the_property_is_sound(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        result = _live(monkeypatch, []).property_reports(address=ADDRESS)
        assert result.payload["match_count"] == 0
        assert "not evidence that the property is sound" in result.payload["note"]
        assert result.gaps == ("property_reports",)


class TestUnavailableInHeirNeverFabricates:
    def test_an_unconfigured_adapter_reports_not_configured(self) -> None:
        report = PropertyAdapter("").health()
        assert report.mode is CapabilityMode.NOT_CONFIGURED
        assert "BEACON_PROPERTY_URL" in report.missing_config

    def test_a_transport_failure_yields_unavailable_and_no_values(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def boom(*args: Any, **kwargs: Any) -> None:
            raise TimeoutError("azure unreachable")

        adapter = PropertyAdapter(
            "http://inheir.test", mode_override=CapabilityMode.LIVE
        )
        monkeypatch.setattr(PropertyAdapter, "_request", boom, raising=True)
        result = adapter.location_intelligence(address=ADDRESS)
        assert result.mode is CapabilityMode.UNAVAILABLE
        assert all(o.value is None for o in result.observations)

    def test_health_never_raises(self) -> None:
        assert (
            PropertyAdapter("http://127.0.0.1:1", timeout=0.05).health().mode
            is CapabilityMode.UNAVAILABLE
        )


class TestPropertyJoinsTheOneTransaction:
    def test_it_fills_the_property_slot(self, monkeypatch: pytest.MonkeyPatch) -> None:
        txn = _txn()
        result = _live(monkeypatch, GIS_BODY).location_intelligence(address=ADDRESS)
        node_id = attach_capability_result(txn, result)
        assert node_id is not None
        assert txn.context["property"]["available"] is True

    def test_the_model_flag_survives_onto_the_evidence_node(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A reviewer reading the graph must see the scores are generated."""
        txn = _txn()
        result = _live(monkeypatch, GIS_BODY).location_intelligence(address=ADDRESS)
        node_id = attach_capability_result(txn, result)
        assert txn.graph.get(node_id).payload["risk_is_model_generated"] is True

    def test_property_evidence_carries_an_official_record_source_type(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        txn = _txn()
        result = _live(monkeypatch, GIS_BODY).location_intelligence(address=ADDRESS)
        node_id = attach_capability_result(txn, result)
        assert txn.graph.get(node_id).payload["source_type"] == str(
            SourceType.OFFICIAL_RECORD
        )
        assert SourceType.OFFICIAL_RECORD in DECISION_CAPABLE_SOURCES

    def test_property_evidence_does_not_grant_payment(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        txn = _txn()
        attach_capability_result(
            txn, _live(monkeypatch, GIS_BODY).location_intelligence(address=ADDRESS)
        )
        assert not txn.permissions.allows(Permission.PAYMENT)

    def test_the_ledger_chain_stays_intact(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        txn = _txn()
        attach_capability_result(
            txn, _live(monkeypatch, GIS_BODY).location_intelligence(address=ADDRESS)
        )
        intact, message = txn.ledger.verify_chain()
        assert intact, message
