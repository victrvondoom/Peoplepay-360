"""The resolution adapter, and the line it must not cross.

PROXY drafts appeals and argues cases well.  What it does not do -- and what this
adapter must never let it appear to do -- is settle a transaction.  An appeal
letter is an argument; a strategy is a plan.  Moving a transaction to ``RESOLVED``
is a lifecycle decision taken on evidence, never a status copied from a drafting
agent.

PROXY is unlicensed, so every test here drives the adapter through its HTTP
boundary with a stubbed transport.  No PROXY source is imported or reproduced.
"""

from __future__ import annotations

from typing import Any

import pytest

from adapters.base import CapabilityMode
from adapters.bridge import attach_capability_result
from adapters.resolution import DISPUTE_DOMAINS, ResolutionAdapter
from beacon.assurance import EvidenceClass, IntentMandate, Money, State
from beacon.peoplepay.authority import Permission, TransactionType
from beacon.peoplepay.transaction import Transaction

CASE_ID = "case-8842"

#: Shaped like PROXY's ``AgentRunResponse``.  Synthetic text.
RUN_BODY: dict[str, Any] = {
    "case_id": CASE_ID,
    "status": "completed",
    "evidence_summary": "invoice and delivery photo attached",
    "research_summary": "two consumer-protection provisions apply",
    "strategy": "cite the 30-day return right, then escalate to the regulator",
    "appeal_draft": "Dear Sir or Madam, I am writing about order 8842...",
    "review_notes": ["one citation could not be confirmed"],
    "citations": ["Consumer Protection Act s.12", "E-Commerce Rules 2020 r.6"],
    "route": "ecommerce",
    "llm_call_count": 7,
    "workflow_engine": "langgraph",
}


def _live(monkeypatch: pytest.MonkeyPatch, response: Any) -> ResolutionAdapter:
    adapter = ResolutionAdapter("http://proxy.test", mode_override=CapabilityMode.LIVE)
    monkeypatch.setattr(
        ResolutionAdapter, "_request", lambda *a, **k: response, raising=True
    )
    return adapter


def _failed_delivery_txn(user: str = "u1") -> Transaction:
    """A transaction that has reached the failure path.

    Built by walking the real lifecycle rather than assigning ``state``, so the
    test would break if the declared transitions stopped allowing this route.
    """
    utterance = "the headphones arrived broken, I want my money back"
    txn = Transaction.create(
        user_id=user,
        raw_utterance=utterance,
        transaction_type=TransactionType.PURCHASE,
    )
    txn.capture_intent(
        IntentMandate.create(
            user_id=user,
            raw_utterance=utterance,
            product_query="refund",
            max_amount=Money.of("14999", "INR"),
        ),
        normalized_intent="obtain a refund for a damaged delivery",
    )
    for target in (
        State.DISCOVERING,
        State.EVIDENCE_COLLECTION,
        State.EVALUATING,
        State.AWAITING_AUTHORIZATION,
        State.AUTHORIZED,
        State.EXECUTING,
        State.PAYMENT_PENDING,
        State.PAYMENT_AUTHORIZED,
        State.PAYMENT_COMPLETED,
        State.FULFILLMENT_PENDING,
        State.FULFILLMENT_IN_PROGRESS,
        State.DELIVERY_FAILED,
    ):
        txn.transition_to(target, actor="test")
    return txn


class TestDraftsAreNeverFindings:
    def test_the_result_says_its_artifacts_are_drafts(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        result = _live(monkeypatch, RUN_BODY).run_case(case_id=CASE_ID)
        assert result.payload["artifacts_are_drafts"] is True
        assert result.payload["requires_human_review"] is True

    def test_no_drafted_artifact_is_verified_evidence(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        result = _live(monkeypatch, RUN_BODY).run_case(case_id=CASE_ID)
        drafts = [
            o for o in result.observations if o.field in ("strategy", "appeal_draft")
        ]
        assert len(drafts) == 2
        assert all(o.evidence_class is not EvidenceClass.VERIFIED for o in drafts)
        assert all("DRAFTED BY AN AGENT" in o.note for o in drafts)

    def test_confidence_stays_low_so_a_draft_does_not_look_settled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        result = _live(monkeypatch, RUN_BODY).run_case(case_id=CASE_ID)
        assert result.confidence == 0.4

    def test_proxys_own_completed_status_is_not_a_resolution(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """PROXY saying 'completed' means it finished drafting, nothing more."""
        result = _live(monkeypatch, RUN_BODY).run_case(case_id=CASE_ID)
        assert result.payload["proxy_status"] == "completed"
        assert "does not settle a transaction" in result.payload["resolution_note"]

    def test_running_a_case_does_not_move_the_transaction_to_resolved(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The decisive test: attaching a dispute draft changes no state."""
        txn = _failed_delivery_txn()
        before = txn.state
        attach_capability_result(
            txn, _live(monkeypatch, RUN_BODY).run_case(case_id=CASE_ID)
        )
        assert txn.state is before is State.DELIVERY_FAILED


class TestCitationsCarryTheirRealWeight:
    def test_corpus_confirmed_is_not_regulator_confirmed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        result = _live(monkeypatch, RUN_BODY).run_case(case_id=CASE_ID)
        cites = [o for o in result.observations if o.field == "citations"]
        assert cites and cites[0].evidence_class is EvidenceClass.UNVERIFIED
        assert "not regulator-confirmed" in cites[0].note

    def test_no_citations_is_recorded_as_a_gap(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        body = {**RUN_BODY, "citations": []}
        result = _live(monkeypatch, body).run_case(case_id=CASE_ID)
        assert result.gaps == ("verified_citations",)
        missing = [o for o in result.observations if o.field == "verified_citations"]
        assert missing and missing[0].value is None

    def test_review_flags_are_surfaced_not_swallowed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        result = _live(monkeypatch, RUN_BODY).run_case(case_id=CASE_ID)
        notes = [o for o in result.observations if o.field == "review_notes"]
        assert notes and notes[0].value == ["one citation could not be confirmed"]
        assert result.payload["review_note_count"] == 1

    def test_a_missing_draft_is_a_gap_not_an_empty_string(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        body = {**RUN_BODY, "appeal_draft": ""}
        result = _live(monkeypatch, body).run_case(case_id=CASE_ID)
        drafts = [o for o in result.observations if o.field == "appeal_draft"]
        assert drafts[0].value is None
        assert result.payload["has_appeal_draft"] is False


class TestAskingAboutRights:
    ASK_BODY = {
        "final_answer": "a damaged item may be returned within 30 days",
        "citations": ["E-Commerce Rules 2020 r.6"],
    }

    def test_an_answer_is_a_summary_not_the_rule(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        result = _live(monkeypatch, self.ASK_BODY).ask(
            question="can I return a damaged item?", domain="ecommerce"
        )
        answer = [o for o in result.observations if o.field == "regulation_answer"][0]
        assert answer.evidence_class is EvidenceClass.UNVERIFIED
        assert "not the rule" in answer.note
        assert "not legal advice" in answer.note

    def test_an_unknown_domain_is_refused_rather_than_defaulted(self) -> None:
        with pytest.raises(ValueError, match="unknown dispute domain"):
            ResolutionAdapter(
                "http://proxy.test", mode_override=CapabilityMode.LIVE
            ).ask(question="anything?", domain="astrology")

    def test_every_declared_domain_is_accepted(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        adapter = _live(monkeypatch, self.ASK_BODY)
        for domain in sorted(DISPUTE_DOMAINS):
            assert adapter.ask(question="what are my rights?", domain=domain).mode is (
                CapabilityMode.LIVE
            )

    def test_an_empty_question_is_refused(self) -> None:
        with pytest.raises(ValueError, match="question is required"):
            ResolutionAdapter(
                "http://proxy.test", mode_override=CapabilityMode.LIVE
            ).ask(question="  ")

    def test_an_answerless_response_is_a_gap(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        result = _live(monkeypatch, {"citations": []}).ask(
            question="what are my rights?", domain="banking"
        )
        assert result.gaps == ("regulation_answer",)


class TestUnavailableProxyNeverFabricates:
    def test_unconfigured_names_the_licensing_reason(self) -> None:
        report = ResolutionAdapter("").health()
        assert report.mode is CapabilityMode.NOT_CONFIGURED
        assert "unlicensed" in report.detail
        assert "BEACON_RESOLUTION_URL" in report.missing_config

    def test_a_transport_failure_produces_no_draft(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def boom(*args: Any, **kwargs: Any) -> None:
            raise ConnectionResetError("proxy went away")

        adapter = ResolutionAdapter(
            "http://proxy.test", mode_override=CapabilityMode.LIVE
        )
        monkeypatch.setattr(ResolutionAdapter, "_request", boom, raising=True)
        result = adapter.run_case(case_id=CASE_ID)
        assert result.mode is CapabilityMode.UNAVAILABLE
        assert all(o.value is None for o in result.observations)

    def test_an_empty_case_id_is_refused_before_any_call(self) -> None:
        with pytest.raises(ValueError, match="case_id is required"):
            ResolutionAdapter(
                "http://proxy.test", mode_override=CapabilityMode.LIVE
            ).run_case(case_id=" ")

    def test_health_never_raises(self) -> None:
        assert (
            ResolutionAdapter("http://127.0.0.1:1", timeout=0.05).health().mode
            is CapabilityMode.UNAVAILABLE
        )


class TestResolutionJoinsTheOneTransaction:
    def test_it_fills_the_fulfillment_slot(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        txn = _failed_delivery_txn()
        node_id = attach_capability_result(
            txn, _live(monkeypatch, RUN_BODY).run_case(case_id=CASE_ID)
        )
        assert node_id is not None
        assert txn.context["fulfillment"]["available"] is True

    def test_the_draft_warning_survives_onto_the_evidence_node(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        txn = _failed_delivery_txn()
        node_id = attach_capability_result(
            txn, _live(monkeypatch, RUN_BODY).run_case(case_id=CASE_ID)
        )
        assert node_id is not None
        payload = txn.graph.get(node_id).payload
        assert payload["artifacts_are_drafts"] is True
        assert payload["requires_human_review"] is True

    def test_a_dispute_draft_does_not_grant_payment_permission(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        txn = _failed_delivery_txn()
        attach_capability_result(
            txn, _live(monkeypatch, RUN_BODY).run_case(case_id=CASE_ID)
        )
        assert not txn.permissions.allows(Permission.PAYMENT)

    def test_the_ledger_chain_stays_intact_through_the_failure_path(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        txn = _failed_delivery_txn()
        attach_capability_result(
            txn, _live(monkeypatch, RUN_BODY).run_case(case_id=CASE_ID)
        )
        intact, message = txn.ledger.verify_chain()
        assert intact, message

    def test_a_paid_transaction_cannot_be_rewound_by_a_dispute(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Money that moved is refunded or disputed, never un-moved."""
        txn = _failed_delivery_txn()
        attach_capability_result(
            txn, _live(monkeypatch, RUN_BODY).run_case(case_id=CASE_ID)
        )
        with pytest.raises(Exception):
            txn.transition_to(State.CANCELLED, actor="test")
