# Transaction Assurance Engine

Beacon's remediation loop governs one object — an incident — from intent to proven resolution. The assurance layer applies the same discipline to a different object: a **transaction**, governed from a user's intent to settlement or a resolved dispute.

The thesis in one line:

> We don't replace commerce, payment networks, or agents. We make an AI-executed transaction continuously provable, bounded, verifiable, and recoverable.

## What is deliberately not here

No payment network. No marketplace. No second application. This layer decides **why, what, for whom, how much, and under what conditions**; a payment provider moves the money. Beacon's existing incident path is untouched — the assurance package shares its conventions (append-only records, hash-bound approvals, deterministic gates) without importing or altering its code.

## The one object

Every capability operates on a transaction and its lifecycle. There is one source of truth for state; agents never hold private copies.

```
INTENT → DISCOVERY → EVIDENCE → EVALUATION → CONTRACT → AUTHORIZATION
       → EXECUTION → PAYMENT → FULFILLMENT → VERIFICATION → SETTLEMENT → CLOSED

any state → EXCEPTION → INVESTIGATION → REFUND / RECOVERY / DISPUTE → RESOLUTION → CLOSED
```

33 states, all declared in one table. `tests/test_assurance_core.py` proves every state appears in it, every state is reachable from `DRAFT`, and every exception state can reach a terminal state — so no transaction can be trapped forever.

## The layering that matters

A model may read, propose, and explain. It may never move money.

| Layer | Module | Model in the call path? |
|---|---|---|
| Amounts | `money.py` | No |
| Lifecycle | `states.py` | No |
| Provenance & evidence | `evidence.py` | No |
| Policy decisions | `policy.py` | No |
| Contract & drift | `contract.py` | No |
| Event log & idempotency | `ledger.py` | No |
| Intent interpretation | proposes an `IntentMandate` | **Yes — proposal only** |

An LLM's only structural privilege is proposing a reading of what the user said. `IntentMandate.interpreted_by` records which model proposed it, and that field grants no authority.

## Controls

| # | Control | Where | Proven by |
|---|---|---|---|
| 1 | **Money is exact.** Integer minor units plus an ISO-4217 code. Floats are rejected at construction — `Money.of(1099.99, "INR")` raises, because precision is already lost by then. Zero-decimal currencies (JPY, KRW) and 3-decimal ones (KWD, BHD) carry correct exponents. Cross-currency arithmetic and comparison raise rather than guess. | `money.py` | `test_money_is_exact_where_a_float_would_drift`, `test_money_respects_zero_decimal_currencies`, `test_money_refuses_to_mix_currencies` |
| 2 | **Transitions are declared, not improvised.** `assert_transition` is plain Python. Every status is a `State` member; no module may invent a status string. | `states.py` | `test_every_state_is_declared_in_the_transition_table`, `test_illegal_transition_names_what_was_allowed` |
| 3 | **Payment success is not completion.** A transaction stays open through fulfilment, verification and settlement. | `states.is_open` | `test_payment_success_does_not_close_the_transaction` |
| 4 | **Money that moved cannot be un-moved.** Once past `PAYMENT_COMPLETED`, `CANCELLED` is unreachable; the only exits are a refund or a dispute. | `states.IRREVERSIBLE_AFTER` | `test_a_paid_transaction_can_never_simply_be_cancelled` |
| 5 | **Nothing is asserted without a source.** An `Observation` cannot exist without a `Provenance`. A missing fact is `UNAVAILABLE`/`UNKNOWN` with `value=None` — enforced in `__post_init__`, so a fabricated value raises rather than persisting. | `evidence.py` | `test_a_missing_fact_may_not_carry_a_value`, `test_unavailable_is_an_answer_rather_than_a_guess` |
| 6 | **Sandbox data can never pass as real.** A sandbox `Provenance` forces `evidence_class` to `SANDBOX` even if the caller asked for `VERIFIED`. Sandbox evidence is not decision-grade, and a policy must opt in explicitly to act on it at all — which still yields `REVIEW`, never a clean `ALLOW`. The flag propagates through contract → checkout mandate → payment mandate. | `evidence.Observation.__post_init__`, `policy._check_evidence` | `test_sandbox_evidence_cannot_launder_itself_into_verified`, `test_sandbox_evidence_cannot_buy_anything_under_a_real_policy`, `test_sandbox_provenance_propagates_all_the_way_to_the_payment_mandate` |
| 7 | **Disagreement and staleness are named, not guessed away.** `conflicting()` keeps every candidate value in the note and picks no winner. Evidence past the policy's freshness window becomes `STALE` and cannot authorize a purchase on its own. | `evidence.conflicting`, `Observation.aged` | `test_conflicting_sources_do_not_silently_pick_a_winner`, `test_stale_price_evidence_cannot_authorize_a_purchase_on_its_own` |
| 8 | **The evidence graph is append-only.** No update, no delete. A superseded claim is a new node joined by a `SUPERSEDES` edge, so what we believed and when survives for a dispute. | `evidence.EvidenceGraph` | `test_the_evidence_graph_is_append_only`, `test_superseded_nodes_stay_in_the_graph_but_leave_the_present` |
| 9 | **Silence is not consent.** A mandate with no stated ceiling yields `REVIEW`, never unlimited spend. A contract written without a ceiling uses the quoted amount rather than inventing headroom. | `policy._check_amount`, `TransactionContract.create` | `test_an_unstated_ceiling_is_not_an_unlimited_one`, `test_a_contract_without_a_stated_ceiling_does_not_invent_headroom` |
| 10 | **An amount must match its own evidence.** Checked *before* the evidence-class branches, so a sandbox or stale observation cannot be used to skip the comparison. | `policy._check_evidence` | `test_an_amount_that_contradicts_its_own_evidence_is_blocked` |
| 11 | **A risk score adds friction and never removes it.** Advisory only, `[0,1]`, and never the sole ground for an irreversible act. A reassuring score cannot lift a hard block. Out-of-range is a bug, not a decision. | `policy._check_risk` | `test_a_high_risk_score_can_add_friction_but_never_remove_it`, `test_a_risk_score_outside_the_unit_interval_is_a_bug_not_a_decision` |
| 12 | **Outcomes only tighten.** `BLOCK` beats `REVIEW` beats `ALLOW`, so adding a rule can never accidentally loosen the engine. | `policy.PolicyEngine._worst` | `test_every_decision_explains_itself` |
| 13 | **A policy typo cannot silently widen a limit.** `Policy.from_dict` rejects unknown keys instead of ignoring them. | `policy.Policy.from_dict` | `test_a_policy_typo_raises_instead_of_silently_widening_a_limit` |
| 14 | **Drift is caught at the edge of execution.** `TransactionContract.check` compares the live cart against frozen terms and reports **every** violation at once: price above ceiling, price changed (in either direction — a surprise discount can mean a swapped item), merchant swapped, product variant swapped, quantity changed, currency switched, delivery slipped, payment method substituted, line items that don't sum to the total, contract expired. | `contract.TransactionContract.check` | `test_all_violations_are_reported_together_not_one_at_a_time` and the ten sibling drift tests |
| 15 | **Recoverable drift is distinguished from disqualifying drift.** A price move is re-authorizable; a silently swapped merchant is not, and cannot be waved through by the agent that failed to notice. | `contract._RE_AUTHORIZABLE` | `test_a_price_rise_after_authorization_is_caught_and_re_authorizable`, `test_a_swapped_merchant_is_caught_and_is_not_re_authorizable` |
| 16 | **Consent is the user's words.** An `Authorization` cannot be granted with an empty quote. It is bound to one contract by `binding_hash`; if the terms change afterwards it dies. It expires, it is single-use by default, and it can be revoked. | `contract.Authorization` | `test_consent_requires_the_users_actual_words`, `test_an_authorization_dies_when_the_terms_it_covered_change`, and three more |
| 17 | **A payment authorization is not a blank cheque.** A `PaymentMandate` carries the `checkout_hash` of the cart it was minted for. Replay against any other cart fails `covers()`. This mirrors the `params_hash` binding in `beacon/approvals.py` — the same principle, applied to money. | `contract.PaymentMandate.covers` | `test_a_payment_mandate_cannot_be_replayed_against_a_different_cart`, `test_a_payment_mandate_expires` |
| 18 | **Nothing important happens without an event.** The ledger assigns `seq` itself, chains each event to the previous by hash, and has no update or delete. `verify_chain()` names the sequence number where tampering or deletion occurred. Anonymous writes are refused. | `ledger.TransactionLedger` | `test_editing_an_event_after_the_fact_breaks_the_chain`, `test_deleting_an_event_breaks_the_chain`, `test_every_event_names_an_actor` |
| 19 | **A duplicate payment replays instead of charging twice.** Claim-then-run: the key is reserved *before* the external call, so a crash leaves a visible in-flight record rather than an invisible maybe-charge. Reusing one key for a different operation fails loudly. | `ledger.IdempotencyGuard` | `test_a_duplicate_payment_replays_instead_of_charging_twice`, `test_reusing_one_key_for_a_different_operation_fails_loudly`, `test_an_interrupted_payment_stays_visible_as_in_flight` |
| 20 | **Every decision explains itself.** A `Decision` carries its `Reason` list — stable code, human detail, outcome, and the evidence sources consulted — plus the `policy_hash` it was evaluated against. The explanation is assembled from the reasons actually used, not written by a model. | `policy.Decision.explain` | `test_every_decision_explains_itself` |

## Mandate chain

Checkout authorization is separated from payment authorization, and the payment is bound to the checkout — the architectural principle the Agent Payments Protocol draws, implemented with our own abstractions rather than a copy of anyone's code:

```
IntentMandate     what the user wants, in their words
      │
CheckoutMandate   the exact cart: product, merchant, amount, quantity
      │           → checkout_hash
PaymentMandate    authority to pay for that checkout and no other
                  → carries checkout_hash; replay elsewhere fails
```

## Running it

```bash
python -m pytest tests/test_assurance_core.py -q     # 79 tests, ~0.2s
python -m mypy src/beacon/assurance/                 # strict, clean
python -m ruff check src/beacon/assurance/
```

No AWS, no network, no model, no credentials. The invariants above are properties of ordinary Python, which is the point: they hold in a unit test and they hold in production for the same reason.

## What is built, and what is not

**Built and tested** — the deterministic core: money, lifecycle, evidence and provenance, policy engine, transaction contract with drift detection, scoped authorization, the mandate chain, the hash-chained ledger, idempotency.

**Not yet built, and not claimed:** the provider adapters (`PaymentProvider`, `DiscoveryProvider`, `MerchantVerifier`, `ShippingProvider`) and their labelled sandbox implementations; the orchestrator that drives the state machine; the verification and reconciliation engines; the refund and dispute engines; the transaction-scoped tool surface; and the UI.

The core above is the layer all of those sit on, and each is a seam the core already anticipates — but none of it exists yet, and the end-to-end demo cannot be shown until the orchestrator and at least one sandbox provider set are written.
