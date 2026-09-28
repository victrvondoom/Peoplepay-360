"""Adversarial tests for the transaction assurance core.

These are the attacks the design has to survive: a price that moves after
authorization, a merchant that swaps at checkout, a payment replayed, an
agent reaching past its scope, sandbox data trying to pass as real, and a
ledger edited after the fact.  Each is a property of the deterministic layer,
so none of these tests needs a model or a network.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

import pytest

from beacon.assurance.contract import (
    Authorization,
    CheckoutMandate,
    ObservedCheckout,
    PaymentMandate,
    TransactionContract,
    ViolationKind,
)
from beacon.assurance.evidence import (
    EdgeKind,
    EvidenceClass,
    EvidenceGraph,
    NodeKind,
    Observation,
    Provenance,
    conflicting,
    unavailable,
    utcnow,
)
from beacon.assurance.ledger import (
    EventKind,
    IdempotencyConflict,
    IdempotencyGuard,
    TransactionLedger,
)
from beacon.assurance.money import CurrencyMismatch, Money
from beacon.assurance.policy import (
    Candidate,
    IntentMandate,
    Outcome,
    Policy,
    PolicyEngine,
)
from beacon.assurance.states import (
    EXCEPTION_STATES,
    IRREVERSIBLE_AFTER,
    TERMINAL_STATES,
    TRANSITIONS,
    IllegalTransition,
    State,
    assert_transition,
    can_transition,
    is_open,
    reachable_from,
)

PRODUCT = "iphone-17-pro-256"
MERCHANT = "abc-electronics"


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def inr(amount: str) -> Money:
    return Money.of(amount, "INR")


def price_obs(
    amount: Money,
    *,
    age_minutes: int = 0,
    sandbox: bool = False,
    evidence_class: EvidenceClass = EvidenceClass.VERIFIED,
) -> Observation:
    return Observation(
        field="price",
        value=amount,
        provenance=Provenance(
            source="sandbox.catalog" if sandbox else "merchant.api",
            retrieved_at=utcnow() - timedelta(minutes=age_minutes),
            sandbox=sandbox,
        ),
        evidence_class=evidence_class,
    )


def a_mandate(**kwargs: object) -> IntentMandate:
    defaults: dict[str, object] = {
        "max_amount": inr("120000"),
        "max_delivery_days": 3,
    }
    defaults.update(kwargs)
    return IntentMandate.create(
        user_id="user-1",
        raw_utterance="Buy an iPhone 17 Pro under 120000 from a legitimate seller",
        product_query="iPhone 17 Pro 256GB",
        **defaults,  # type: ignore[arg-type]
    )


def a_contract(
    mandate: IntentMandate | None = None,
    policy: Policy | None = None,
    **kwargs: object,
) -> TransactionContract:
    mandate = mandate or a_mandate()
    policy = policy or Policy.from_mandate(mandate)
    defaults: dict[str, object] = {
        "product_id": PRODUCT,
        "merchant_id": MERCHANT,
        "expected_amount": inr("109999"),
    }
    defaults.update(kwargs)
    return TransactionContract.create(
        transaction_id="tx-1",
        mandate=mandate,
        policy=policy,
        **defaults,  # type: ignore[arg-type]
    )


def a_cart(**kwargs: object) -> ObservedCheckout:
    defaults: dict[str, object] = {
        "product_id": PRODUCT,
        "merchant_id": MERCHANT,
        "unit_amount": inr("109999"),
        "quantity": 1,
        "total_amount": inr("109999"),
        "currency": "INR",
        "delivery_days": 2,
        "payment_method_id": "pm_card_1",
    }
    defaults.update(kwargs)
    return ObservedCheckout(**defaults)  # type: ignore[arg-type]


def a_candidate(**kwargs: object) -> Candidate:
    defaults: dict[str, object] = {
        "amount": inr("109999"),
        "merchant_id": MERCHANT,
        "merchant_verified": True,
        "delivery_days": 2,
        "price_observation": price_obs(inr("109999")),
    }
    defaults.update(kwargs)
    return Candidate(**defaults)  # type: ignore[arg-type]


# --------------------------------------------------------------------------
# money
# --------------------------------------------------------------------------


def test_money_is_exact_where_a_float_would_drift() -> None:
    # 0.1 + 0.2 != 0.3 in binary floating point; minor units make it exact.
    total = Money.of("0.10", "USD") + Money.of("0.20", "USD")
    assert total == Money.of("0.30", "USD")
    assert total.minor == 30


def test_money_refuses_floats_because_precision_is_already_lost() -> None:
    with pytest.raises(TypeError):
        Money.of(1099.99, "INR")  # type: ignore[arg-type]


def test_money_respects_zero_decimal_currencies() -> None:
    assert Money.of("5000", "JPY").minor == 5000
    assert Money.of("5000", "INR").minor == 500000


def test_money_accepts_decimal_and_round_trips_through_dict() -> None:
    original = Money.of(Decimal("109999.50"), "INR")
    assert Money.from_dict(original.to_dict()) == original


def test_money_refuses_to_mix_currencies() -> None:
    with pytest.raises(CurrencyMismatch):
        _ = inr("1") + Money.of("1", "USD")
    with pytest.raises(CurrencyMismatch):
        _ = inr("1") < Money.of("1", "USD")


# --------------------------------------------------------------------------
# state machine
# --------------------------------------------------------------------------


def test_every_state_is_declared_in_the_transition_table() -> None:
    assert set(TRANSITIONS) == set(State)


def test_transition_targets_are_all_real_states() -> None:
    for source, targets in TRANSITIONS.items():
        for target in targets:
            assert isinstance(target, State), f"{source} -> {target!r}"


def test_no_state_declares_itself_as_a_successor() -> None:
    for source, targets in TRANSITIONS.items():
        assert source not in targets, f"{source} loops to itself"


def test_terminal_states_have_no_exits_except_a_late_dispute() -> None:
    assert TRANSITIONS[State.RESOLVED] == frozenset()
    assert TRANSITIONS[State.CANCELLED] == frozenset()
    # A chargeback can arrive after completion, so that one edge exists.
    assert TRANSITIONS[State.COMPLETED] == frozenset({State.DISPUTE_REQUIRED})


def test_a_paid_transaction_can_never_simply_be_cancelled() -> None:
    # Once money has moved the only way back is a refund or a dispute.
    for state in IRREVERSIBLE_AFTER:
        assert not can_transition(state, State.CANCELLED), state


def test_illegal_transition_names_what_was_allowed() -> None:
    with pytest.raises(IllegalTransition) as caught:
        assert_transition(State.DRAFT, State.PAYMENT_COMPLETED)
    message = str(caught.value)
    assert "DRAFT -> PAYMENT_COMPLETED" in message
    assert "INTENT_CAPTURED" in message


def test_payment_success_does_not_close_the_transaction() -> None:
    assert is_open(State.PAYMENT_COMPLETED)
    assert is_open(State.FULFILLMENT_COMPLETED)
    assert is_open(State.VERIFIED)
    assert not is_open(State.COMPLETED)


def test_every_state_is_reachable_from_draft() -> None:
    assert reachable_from(State.DRAFT) | {State.DRAFT} == set(State)


def test_every_exception_state_can_reach_a_terminal_state() -> None:
    # An exception that cannot be resolved would trap a transaction forever.
    for state in EXCEPTION_STATES:
        assert reachable_from(state) & TERMINAL_STATES, f"{state} is a dead end"


# --------------------------------------------------------------------------
# evidence and provenance
# --------------------------------------------------------------------------


def test_sandbox_evidence_cannot_launder_itself_into_verified() -> None:
    observation = price_obs(inr("109999"), sandbox=True)
    assert observation.evidence_class is EvidenceClass.SANDBOX
    assert not observation.is_decision_grade


def test_a_missing_fact_may_not_carry_a_value() -> None:
    with pytest.raises(ValueError, match="must not be filled in"):
        Observation(
            field="price",
            value=inr("1"),
            provenance=Provenance(source="s", retrieved_at=utcnow()),
            evidence_class=EvidenceClass.UNAVAILABLE,
        )


def test_unavailable_is_an_answer_rather_than_a_guess() -> None:
    observation = unavailable("price", "merchant.api", note="404 from catalog")
    assert observation.value is None
    assert not observation.is_decision_grade


def test_conflicting_sources_do_not_silently_pick_a_winner() -> None:
    folded = conflicting("price", [price_obs(inr("109999")), price_obs(inr("112499"))])
    assert folded.evidence_class is EvidenceClass.CONFLICTING
    assert folded.value is None
    assert "sources disagree" in folded.note


def test_evidence_goes_stale_once_past_the_freshness_window() -> None:
    observation = price_obs(inr("109999"), age_minutes=60)
    assert observation.aged(timedelta(minutes=30)).evidence_class is EvidenceClass.STALE
    assert observation.aged(timedelta(hours=2)).evidence_class is EvidenceClass.VERIFIED


def test_the_evidence_graph_is_append_only() -> None:
    graph = EvidenceGraph("tx-1")
    node = graph.add(NodeKind.PRICE_EVIDENCE, actor="evidence-agent")
    with pytest.raises(ValueError, match="append-only"):
        graph.add(NodeKind.PRICE_EVIDENCE, actor="x", node_id=node.node_id)


def test_superseded_nodes_stay_in_the_graph_but_leave_the_present() -> None:
    graph = EvidenceGraph("tx-1")
    old = graph.add(NodeKind.PRICE_EVIDENCE, actor="a", payload={"v": 1})
    new = graph.add(NodeKind.PRICE_EVIDENCE, actor="a", payload={"v": 2})
    graph.link(new.node_id, old.node_id, EdgeKind.SUPERSEDES)
    assert graph.latest(NodeKind.PRICE_EVIDENCE) == new
    assert len(graph) == 2, "history must not be deleted"


def test_the_graph_reports_when_any_of_its_evidence_is_sandboxed() -> None:
    graph = EvidenceGraph("tx-1")
    graph.add(
        NodeKind.PRICE_EVIDENCE,
        actor="a",
        observations=[price_obs(inr("1"), sandbox=True)],
    )
    assert graph.has_sandbox_evidence()
    assert graph.reconstruct()["contains_sandbox_evidence"] is True


def test_linking_an_unknown_node_fails() -> None:
    graph = EvidenceGraph("tx-1")
    node = graph.add(NodeKind.CONTRACT, actor="a")
    with pytest.raises(KeyError):
        graph.link(node.node_id, "does-not-exist", EdgeKind.SUPPORTS)


# --------------------------------------------------------------------------
# policy engine
# --------------------------------------------------------------------------


def test_an_amount_within_the_ceiling_is_allowed() -> None:
    mandate = a_mandate()
    decision = PolicyEngine().evaluate(
        a_candidate(), Policy.from_mandate(mandate), mandate
    )
    assert decision.outcome is Outcome.ALLOW


def test_an_amount_above_the_ceiling_is_blocked() -> None:
    mandate = a_mandate()
    candidate = a_candidate(
        amount=inr("124999"), price_observation=price_obs(inr("124999"))
    )
    decision = PolicyEngine().evaluate(candidate, Policy.from_mandate(mandate), mandate)
    assert decision.outcome is Outcome.BLOCK
    assert {r.code for r in decision.blocking_reasons} == {"AMOUNT_ABOVE_MAX"}


def test_an_unstated_ceiling_is_not_an_unlimited_one() -> None:
    candidate = a_candidate(
        amount=inr("500000"), price_observation=price_obs(inr("500000"))
    )
    decision = PolicyEngine().evaluate(candidate, Policy())
    assert decision.outcome is Outcome.REVIEW
    assert "NO_AMOUNT_CEILING" in {r.code for r in decision.reasons}


def test_an_amount_that_contradicts_its_own_evidence_is_blocked() -> None:
    mandate = a_mandate()
    candidate = a_candidate(
        amount=inr("99999"), price_observation=price_obs(inr("109999"))
    )
    decision = PolicyEngine().evaluate(candidate, Policy.from_mandate(mandate), mandate)
    assert decision.outcome is Outcome.BLOCK
    assert "AMOUNT_NOT_EVIDENCED" in {r.code for r in decision.blocking_reasons}


def test_sandbox_evidence_cannot_buy_anything_under_a_real_policy() -> None:
    mandate = a_mandate()
    candidate = a_candidate(price_observation=price_obs(inr("109999"), sandbox=True))
    decision = PolicyEngine().evaluate(candidate, Policy.from_mandate(mandate), mandate)
    assert decision.outcome is Outcome.BLOCK
    assert "SANDBOX_EVIDENCE_REFUSED" in {r.code for r in decision.blocking_reasons}


def test_sandbox_evidence_still_adds_friction_when_explicitly_permitted() -> None:
    mandate = a_mandate()
    policy = Policy.from_mandate(mandate, allow_sandbox_evidence=True)
    candidate = a_candidate(price_observation=price_obs(inr("109999"), sandbox=True))
    assert PolicyEngine().evaluate(candidate, policy, mandate).outcome is Outcome.REVIEW


def test_stale_price_evidence_cannot_authorize_a_purchase_on_its_own() -> None:
    mandate = a_mandate()
    candidate = a_candidate(price_observation=price_obs(inr("109999"), age_minutes=120))
    decision = PolicyEngine().evaluate(candidate, Policy.from_mandate(mandate), mandate)
    assert decision.outcome is Outcome.REVIEW
    assert "PRICE_EVIDENCE_STALE" in {r.code for r in decision.reasons}


def test_a_missing_price_observation_blocks_rather_than_assumes() -> None:
    mandate = a_mandate()
    candidate = a_candidate(price_observation=None)
    decision = PolicyEngine().evaluate(candidate, Policy.from_mandate(mandate), mandate)
    assert decision.outcome is Outcome.BLOCK
    assert "PRICE_EVIDENCE_MISSING" in {r.code for r in decision.blocking_reasons}


def test_conflicting_price_evidence_blocks() -> None:
    mandate = a_mandate()
    folded = conflicting("price", [price_obs(inr("109999")), price_obs(inr("112499"))])
    candidate = a_candidate(price_observation=folded)
    decision = PolicyEngine().evaluate(candidate, Policy.from_mandate(mandate), mandate)
    assert decision.outcome is Outcome.BLOCK


def test_a_refurbished_substitute_is_not_the_new_item_the_user_asked_for() -> None:
    mandate = a_mandate(required_condition="new")
    candidate = a_candidate(condition="refurbished")
    decision = PolicyEngine().evaluate(candidate, Policy.from_mandate(mandate), mandate)
    assert decision.outcome is Outcome.BLOCK
    assert "CONDITION_MISMATCH" in {r.code for r in decision.blocking_reasons}


def test_an_expired_mandate_authorizes_nothing() -> None:
    mandate = a_mandate(valid_for=timedelta(seconds=-1))
    candidate = a_candidate(amount=inr("1"), price_observation=price_obs(inr("1")))
    decision = PolicyEngine().evaluate(candidate, Policy.from_mandate(mandate), mandate)
    assert decision.outcome is Outcome.BLOCK
    assert "MANDATE_EXPIRED" in {r.code for r in decision.blocking_reasons}


def test_a_blocked_merchant_cannot_be_rescued_by_a_low_price() -> None:
    mandate = a_mandate(blocked_merchants=("shady-seller",))
    candidate = a_candidate(
        amount=inr("1"),
        merchant_id="shady-seller",
        price_observation=price_obs(inr("1")),
    )
    decision = PolicyEngine().evaluate(candidate, Policy.from_mandate(mandate), mandate)
    assert decision.outcome is Outcome.BLOCK
    assert "MERCHANT_BLOCKED" in {r.code for r in decision.blocking_reasons}


def test_a_merchant_outside_the_allowlist_is_blocked() -> None:
    mandate = a_mandate(allowed_merchants=(MERCHANT,))
    candidate = a_candidate(merchant_id="someone-else")
    decision = PolicyEngine().evaluate(candidate, Policy.from_mandate(mandate), mandate)
    assert decision.outcome is Outcome.BLOCK
    assert "MERCHANT_NOT_ALLOWLISTED" in {r.code for r in decision.blocking_reasons}


def test_an_unverified_merchant_needs_a_human() -> None:
    mandate = a_mandate()
    candidate = a_candidate(merchant_verified=False)
    decision = PolicyEngine().evaluate(candidate, Policy.from_mandate(mandate), mandate)
    assert decision.outcome is Outcome.REVIEW
    assert "MERCHANT_UNVERIFIED" in {r.code for r in decision.reasons}


def test_a_high_risk_score_can_add_friction_but_never_remove_it() -> None:
    mandate = a_mandate()
    policy = Policy.from_mandate(mandate)
    engine = PolicyEngine()

    assert engine.evaluate(a_candidate(), policy, mandate).outcome is Outcome.ALLOW
    assert (
        engine.evaluate(a_candidate(risk_score=0.9), policy, mandate).outcome
        is Outcome.REVIEW
    )
    # A reassuring score cannot lift a block that a hard rule imposed.
    blocked = a_candidate(
        amount=inr("124999"),
        price_observation=price_obs(inr("124999")),
        risk_score=0.0,
    )
    assert engine.evaluate(blocked, policy, mandate).outcome is Outcome.BLOCK


def test_a_risk_score_outside_the_unit_interval_is_a_bug_not_a_decision() -> None:
    mandate = a_mandate()
    with pytest.raises(ValueError, match=r"\[0,1\]"):
        PolicyEngine().evaluate(
            a_candidate(risk_score=7.0), Policy.from_mandate(mandate), mandate
        )


def test_a_policy_typo_raises_instead_of_silently_widening_a_limit() -> None:
    with pytest.raises(ValueError, match="unknown policy keys"):
        Policy.from_dict({"max_amt": {"minor": 1, "currency": "INR"}})


def test_a_policy_round_trips_through_its_machine_readable_form() -> None:
    policy = Policy.from_mandate(a_mandate(), allow_sandbox_evidence=True)
    assert Policy.from_dict(policy.to_dict()) == policy


def test_every_decision_explains_itself() -> None:
    mandate = a_mandate()
    candidate = a_candidate(
        amount=inr("124999"),
        merchant_verified=False,
        delivery_days=9,
        price_observation=price_obs(inr("124999")),
    )
    decision = PolicyEngine().evaluate(candidate, Policy.from_mandate(mandate), mandate)
    explanation = decision.explain()
    assert "AMOUNT_ABOVE_MAX" in explanation
    assert "DELIVERY_TOO_SLOW" in explanation
    assert decision.policy_hash


# --------------------------------------------------------------------------
# the contract: drift between authorization and checkout
# --------------------------------------------------------------------------


def test_a_matching_cart_produces_no_violations() -> None:
    assert a_contract().check(a_cart()) == ()


def test_a_price_rise_after_authorization_is_caught_and_re_authorizable() -> None:
    violations = a_contract().check(
        a_cart(unit_amount=inr("119999"), total_amount=inr("119999"))
    )
    assert [v.kind for v in violations] == [ViolationKind.PRICE_CHANGED]
    assert violations[0].is_re_authorizable


def test_a_price_above_the_ceiling_is_a_hard_stop() -> None:
    violations = a_contract().check(
        a_cart(unit_amount=inr("124999"), total_amount=inr("124999"))
    )
    assert [v.kind for v in violations] == [ViolationKind.PRICE_ABOVE_MAX]


def test_a_price_drop_is_still_a_change_the_user_should_hear_about() -> None:
    # A surprise discount can mean a swapped or counterfeit item.
    violations = a_contract().check(
        a_cart(unit_amount=inr("9999"), total_amount=inr("9999"))
    )
    assert [v.kind for v in violations] == [ViolationKind.PRICE_CHANGED]


def test_a_tolerance_absorbs_small_movement_but_not_large() -> None:
    contract = a_contract(price_tolerance=inr("100"))
    assert (
        contract.check(a_cart(unit_amount=inr("110050"), total_amount=inr("110050")))
        == ()
    )
    assert contract.check(a_cart(unit_amount=inr("110500"), total_amount=inr("110500")))


def test_a_swapped_merchant_is_caught_and_is_not_re_authorizable() -> None:
    violations = a_contract().check(a_cart(merchant_id="shady-seller"))
    assert [v.kind for v in violations] == [ViolationKind.MERCHANT_CHANGED]
    assert not violations[0].is_re_authorizable


def test_a_swapped_product_variant_is_caught() -> None:
    violations = a_contract().check(a_cart(product_id="iphone-17-pro-128"))
    assert [v.kind for v in violations] == [ViolationKind.PRODUCT_CHANGED]


def test_a_changed_quantity_is_caught() -> None:
    violations = a_contract().check(a_cart(quantity=2, total_amount=inr("109999")))
    assert ViolationKind.QUANTITY_CHANGED in {v.kind for v in violations}


def test_a_currency_switch_stops_the_comparison_entirely() -> None:
    violations = a_contract().check(
        a_cart(
            currency="USD",
            unit_amount=Money.of("1300", "USD"),
            total_amount=Money.of("1300", "USD"),
        )
    )
    # Amount comparisons across currencies are meaningless, so only the
    # currency violation is reported.
    assert [v.kind for v in violations] == [ViolationKind.CURRENCY_CHANGED]


def test_an_unauthorized_payment_method_is_caught() -> None:
    contract = a_contract(allowed_payment_methods=("pm_card_1",))
    violations = contract.check(a_cart(payment_method_id="pm_stolen"))
    assert [v.kind for v in violations] == [ViolationKind.PAYMENT_METHOD_CHANGED]


def test_all_violations_are_reported_together_not_one_at_a_time() -> None:
    violations = a_contract().check(
        a_cart(
            merchant_id="shady-seller",
            unit_amount=inr("124999"),
            total_amount=inr("124999"),
            delivery_days=9,
        )
    )
    assert {v.kind for v in violations} == {
        ViolationKind.MERCHANT_CHANGED,
        ViolationKind.PRICE_ABOVE_MAX,
        ViolationKind.DELIVERY_TOO_SLOW,
    }


def test_line_items_that_do_not_add_up_to_the_total_are_caught() -> None:
    violations = a_contract().check(
        a_cart(unit_amount=inr("100000"), fees=inr("500"), total_amount=inr("109999"))
    )
    assert ViolationKind.FEES_UNDISCLOSED in {v.kind for v in violations}


def test_an_expired_contract_cannot_be_executed() -> None:
    contract = a_contract(valid_for=timedelta(seconds=-1))
    assert ViolationKind.CONTRACT_EXPIRED in {v.kind for v in contract.check(a_cart())}


def test_a_contract_cannot_be_written_above_the_authorized_ceiling() -> None:
    with pytest.raises(ValueError, match="exceeds the authorized"):
        a_contract(mandate=a_mandate(max_amount=inr("100000")))


def test_a_contract_without_a_stated_ceiling_does_not_invent_headroom() -> None:
    contract = a_contract(mandate=a_mandate(max_amount=None))
    assert contract.max_amount == inr("109999")


# --------------------------------------------------------------------------
# authorization and mandate binding
# --------------------------------------------------------------------------


def test_consent_requires_the_users_actual_words() -> None:
    with pytest.raises(ValueError, match="not consent"):
        Authorization.grant(a_contract(), transcript_quote="   ", channel="voice")


def test_an_authorization_does_not_cover_a_different_contract() -> None:
    first, second = a_contract(), a_contract()
    authorization = Authorization.grant(
        first, transcript_quote="yes, buy it", channel="voice"
    )
    assert authorization.invalid_reason(first) is None
    assert authorization.invalid_reason(second) == (
        "authorization is for a different contract"
    )


def test_an_authorization_dies_when_the_terms_it_covered_change() -> None:
    contract = a_contract()
    authorization = Authorization.grant(
        contract, transcript_quote="yes, buy it", channel="voice"
    )
    amended = replace(contract, max_amount=inr("200000"))
    assert authorization.invalid_reason(amended) == (
        "the contract terms changed after this authorization was granted"
    )


def test_an_authorization_expires() -> None:
    contract = a_contract()
    authorization = Authorization.grant(
        contract,
        transcript_quote="yes",
        channel="voice",
        valid_for=timedelta(seconds=-1),
    )
    assert authorization.invalid_reason(contract) == "authorization expired"


def test_a_single_use_authorization_cannot_be_spent_twice() -> None:
    contract = a_contract()
    spent = replace(
        Authorization.grant(contract, transcript_quote="yes", channel="voice"), uses=1
    )
    assert spent.invalid_reason(contract) == "authorization already used"


def test_a_revoked_authorization_stops_working() -> None:
    contract = a_contract()
    revoked = replace(
        Authorization.grant(contract, transcript_quote="yes", channel="voice"),
        revoked_at=utcnow(),
        revoked_reason="user changed their mind",
    )
    reason = revoked.invalid_reason(contract)
    assert reason is not None and "revoked" in reason


def test_a_payment_mandate_cannot_be_replayed_against_a_different_cart() -> None:
    contract, cart = a_contract(), a_cart()
    mandate = PaymentMandate.create(
        CheckoutMandate.create(contract, cart), payment_method_id="pm_card_1"
    )
    assert mandate.covers(cart) is None

    reason = mandate.covers(
        a_cart(unit_amount=inr("119999"), total_amount=inr("119999"))
    )
    assert reason is not None and "different checkout" in reason


def test_a_payment_mandate_expires() -> None:
    contract, cart = a_contract(), a_cart()
    mandate = PaymentMandate.create(
        CheckoutMandate.create(contract, cart),
        payment_method_id="pm_card_1",
        valid_for=timedelta(seconds=-1),
    )
    assert mandate.covers(cart) == "payment mandate expired"


def test_sandbox_provenance_propagates_all_the_way_to_the_payment_mandate() -> None:
    checkout_mandate = CheckoutMandate.create(a_contract(sandbox=True), a_cart())
    payment_mandate = PaymentMandate.create(
        checkout_mandate, payment_method_id="pm_card_1"
    )
    assert checkout_mandate.sandbox
    assert payment_mandate.sandbox


# --------------------------------------------------------------------------
# ledger and idempotency
# --------------------------------------------------------------------------


def test_the_ledger_assigns_sequence_numbers_itself() -> None:
    ledger = TransactionLedger("tx-1")
    for _ in range(3):
        ledger.append(EventKind.AGENT_ACTION, actor="discovery-agent")
    assert [e.seq for e in ledger] == [1, 2, 3]


def test_an_intact_chain_verifies() -> None:
    ledger = TransactionLedger("tx-1")
    ledger.append(EventKind.TRANSACTION_CREATED, actor="orchestrator")
    ledger.append(EventKind.INTENT_CAPTURED, actor="intent-agent")
    ok, message = ledger.verify_chain()
    assert ok, message


def test_editing_an_event_after_the_fact_breaks_the_chain() -> None:
    ledger = TransactionLedger("tx-1")
    ledger.append(EventKind.TRANSACTION_CREATED, actor="orchestrator")
    ledger.append(EventKind.PAYMENT_CAPTURED, actor="psp", detail={"minor": 10999900})
    ledger._events[1] = replace(ledger._events[1], detail={"minor": 1})
    ok, message = ledger.verify_chain()
    assert not ok
    assert "seq=2" in message


def test_deleting_an_event_breaks_the_chain() -> None:
    ledger = TransactionLedger("tx-1")
    for index in range(4):
        ledger.append(EventKind.AGENT_ACTION, actor="a", detail={"i": index})
    del ledger._events[1]
    ok, _ = ledger.verify_chain()
    assert not ok


def test_every_event_names_an_actor() -> None:
    with pytest.raises(ValueError, match="needs an actor"):
        TransactionLedger("tx-1").append(EventKind.AGENT_ACTION, actor="  ")


def test_a_duplicate_payment_replays_instead_of_charging_twice() -> None:
    guard = IdempotencyGuard()
    operation = {"amount_minor": 10999900, "method": "pm_card_1"}

    first = guard.claim("pay-tx-1", operation)
    assert not first.is_complete
    guard.complete("pay-tx-1", {"charge_id": "ch_1", "status": "captured"})

    second = guard.claim("pay-tx-1", operation)
    assert second.is_complete
    assert second.result == {"charge_id": "ch_1", "status": "captured"}


def test_reusing_one_key_for_a_different_operation_fails_loudly() -> None:
    guard = IdempotencyGuard()
    guard.claim("pay-tx-1", {"amount_minor": 10999900})
    with pytest.raises(IdempotencyConflict):
        guard.claim("pay-tx-1", {"amount_minor": 500})


def test_an_interrupted_payment_stays_visible_as_in_flight() -> None:
    guard = IdempotencyGuard()
    guard.claim("pay-tx-1", {"amount_minor": 10999900})
    assert guard.in_flight() == ("pay-tx-1",)
    guard.complete("pay-tx-1", {"status": "captured"})
    assert guard.in_flight() == ()


def test_completing_without_claiming_is_a_programming_error() -> None:
    with pytest.raises(KeyError):
        IdempotencyGuard().complete("never-claimed", {})


def test_an_idempotency_key_is_mandatory() -> None:
    with pytest.raises(ValueError, match="idempotency key is required"):
        IdempotencyGuard().claim("", {})


# --------------------------------------------------------------------------
# the full lifecycle, end to end, with no model and no network
# --------------------------------------------------------------------------


def test_the_happy_path_walks_intent_to_completed() -> None:
    path = [
        State.INTENT_CAPTURED,
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
        State.FULFILLMENT_COMPLETED,
        State.VERIFYING,
        State.VERIFIED,
        State.SETTLED,
        State.COMPLETED,
    ]
    current = State.DRAFT
    for target in path:
        assert_transition(current, target)
        current = target
    assert not is_open(current)


def test_the_price_change_recovery_path_is_walkable() -> None:
    # AUTHORIZED -> price moved -> re-evaluate -> ask again -> proceed.
    for current, target in (
        (State.AUTHORIZED, State.PRICE_CHANGED),
        (State.PRICE_CHANGED, State.EVALUATING),
        (State.EVALUATING, State.AWAITING_AUTHORIZATION),
        (State.AWAITING_AUTHORIZATION, State.AUTHORIZED),
    ):
        assert_transition(current, target)


def test_the_wrong_item_delivered_path_reaches_a_resolution() -> None:
    for current, target in (
        (State.FULFILLMENT_COMPLETED, State.VERIFYING),
        (State.VERIFYING, State.VERIFICATION_FAILED),
        (State.VERIFICATION_FAILED, State.REFUND_REQUIRED),
        (State.REFUND_REQUIRED, State.RESOLUTION_PENDING),
        (State.RESOLUTION_PENDING, State.RESOLVED),
    ):
        assert_transition(current, target)
    assert not is_open(State.RESOLVED)
