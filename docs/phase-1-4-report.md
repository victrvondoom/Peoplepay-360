# Phase 1–4 report

**Date:** 2026-09-27
**Scope:** Transaction aggregate, typed nodes, personal memory vault, thin agent shell.
**Status:** Complete and tested. Stopped here, per §40.

---

## 1. Test results

Measured, not recalled. All figures from runs on 2026-09-27.

| Suite | Baseline (before) | Now | Delta |
|---|---|---|---|
| `test_assurance_core.py` | **79 passed** | **79 passed** | **unchanged** |
| `test_peoplepay_invariants.py` | — | **70 passed** | +70 new |
| Full offline suite | 307 passed, 1 failed | **377 passed, 1 failed** | +70 passed |
| `ruff check` (new code) | — | **clean** | — |
| `mypy` (new code) | — | **clean, 6 files** | — |

**The 79 assurance tests were not modified and still pass.** No test was deleted,
skipped or relaxed.

### The one failing test is pre-existing and unrelated

`tests/test_hardening.py::test_image_requirement_pins_match_the_tested_environment`
fails on a Docker base-image pin mismatch. Verified failing at the baseline
commit with a clean working tree, before any change here. Not caused by this
work and not fixed by it.

### Excluded from the offline run

Seven files need live AWS and fail at *collection* with SSL errors in this
environment: `test_budget`, `test_handler`, `test_handler_pipeline`,
`test_prefetch`, `test_triage`, `test_voice_handler`, `test_local_server`. Also
pre-existing. They were excluded from the comparison, not from the repository —
the baseline and the current run exclude exactly the same set, so the comparison
is like-for-like.

---

## 2. What was implemented

New package `beacon.peoplepay`, a **sibling** of `beacon.assurance`. 1,906 lines
of source, 773 of tests.

| File | Lines | Phase | Contents |
|---|---|---|---|
| `transaction.py` | 465 | 1 | `Transaction` aggregate, `CONTEXT_SLOTS`, ownership |
| `nodes.py` | 154 | 2 | `PeoplePayNodeKind` (18), `SourceType` (10), `Visibility`, `Retention` |
| `authority.py` | 229 | 2 | `Permission` (5), `PermissionSet`, `ConditionalGrant`, `TransactionType` (9), `PaymentMethod` (7) |
| `memory.py` | 410 | 3 | `MemoryVault`, `MemoryItem`, `MemoryScope`, promotion wall |
| `agent.py` | 558 | 4 | `PeoplePayAgent`, `ToolRegistry` (9 tools), `AgentResponse`, language/budget parsing |
| `__init__.py` | 90 | — | public surface |
| `tests/test_peoplepay_invariants.py` | 773 | — | 70 tests, one class per invariant |

### `beacon.assurance` — one additive change

**Correction.** An earlier draft of this report said the package was untouched.
That is wrong: `assurance/evidence.py` was extended in commit `d3f2f6e` (earlier
in this same session, before the PeoplePay modules landed) with **new
`NodeKind` and `EdgeKind` members only** — `SPATIAL_CONTEXT`,
`PLACEMENT_CHECK`, `PROPERTY`, `DOCUMENT`, `SCAN`, `MARKET_EVIDENCE`,
`BASKET`, `BOOKING`, `RESOLUTION`, plus edges `CONSTRAINS`, `SATISFIES`,
`CLASSIFIED_AS`, `RESOLVES`.

No existing member was moved, renamed or removed, and no logic changed — which
is why the 79 assurance tests still pass unmodified against it. This is the
additive extension §9 asks for, applied to `NodeKind` directly.

`peoplepay/nodes.py` additionally defines `PeoplePayNodeKind` for the
user-centric kinds (`USER_FACT` / `USER_PREFERENCE` / `USER_INFERENCE`), where
the *type-level* separation of preference from inference is the point.

Otherwise the aggregate *composes* `EvidenceGraph`, `TransactionLedger`,
`State`, `IntentMandate`, `Money` and `Observation` and reimplements none of them.

---

## 3. The ten invariants

Each has tests. Each was checked by attempting the violation.

| # | Invariant | How it is enforced | Tests |
|---|---|---|---|
| 1 | One canonical `transaction_id` | Graph and ledger constructed from it; id immutable | 4 |
| 2 | Raw utterance never overwritten | `capture_intent` **refuses a mandate whose `raw_utterance` differs** | 4 |
| 3 | Inference ≠ preference | Different node kinds; `promote_inference` creates a new item, never mutates | 8 |
| 4 | Sandbox never becomes production | `Observation.__post_init__` downgrades to `SANDBOX`; plan validation refuses | 4 |
| 5 | Private stays private | `PRIVATE` default; `share()` requires a consent reference | 5 |
| 6 | Search ⇏ payment | Permissions are an unordered set; default is discovery+planning only | 7 |
| 7 | Planning ⇏ execution | Same; no `pay`/`book` tool exists at all | (in 6) |
| 8 | Payment authorization explicit | `ConditionalGrant.covers()` checks cap, currency, expiry | 8 |
| 9 | Small cohorts not exposed | Price/date are separate items, each privately scoped | 3 |
| 10 | Evidence retains provenance | `source_type` stored per node; missing values cannot carry numbers | 6 |

### Two real defects the tests caught

**A sandbox leak in my own code.** `add_evidence(sandbox=True)` initially set a
payload flag only. But `EvidenceNode.is_sandbox` reads provenance off the
*observations*, so a node declared sandbox with no observations attached looked
**clean** to `has_sandbox_evidence()` — invariant 4 was bypassable. Fixed by
attaching a sandbox-provenance marker observation where the graph actually looks.

**A wrong test, not wrong code.** `detect_language` returned `ta-Latn` for the
demo utterance and I had asserted `ta`. The function was right: the sentence
contains the Latin word "laptop", so it is genuinely mixed script. The
assertion was corrected and a pure-Tamil case added. Reporting `ta` would have
overstated what was detected.

---

## 4. Architecture decisions worth recording

**Context slots are dicts, not classes.** `Transaction.context` is
`dict[str, dict]` over seven named slots. A `RumiTransaction` class is what §2
forbids, and a dict cannot accrete authority the way a class can. Unknown slot
names are refused so a typo cannot create a phantom capability.

**Permissions are a set, not a scale.** There is no ordering along which a caller
could round `DISCOVERY` up to `PAYMENT`. `CONSEQUENTIAL_PERMISSIONS` names the
three a third party would notice.

**`SourceType` is separate from `Provenance.source`.** *Which* provider answered
and *what its word is worth* are different questions. `DECISION_CAPABLE_SOURCES`
deliberately excludes creator content, community discussion and marketplace
listings — they inform a person, they do not settle a fact.

**A capped grant does not cover an unknown amount.** "Buy if under ₹45,000" is
not consent to buy at an unknown price. `covers(None)` returns `False`.

**Inferences are withheld from prompts.** `format_for_prompt` renders preferences
and facts but not inferences — a model that reads its own earlier guess as
context restates it with more confidence than it earned.

**`und` rather than a guess.** `detect_language` returns ISO 639-2 `und` when
there is no signal, instead of defaulting to English.

---

## 5. Security findings

| Finding | Severity | Status |
|---|---|---|
| Sandbox evidence could bypass `has_sandbox_evidence` | **High** | **Fixed** (§3 above) |
| Cross-user transaction access | High | Blocked by `assert_owned_by`; 4 tests |
| Permission denials were unlogged | Medium | Now appended to the ledger with `outcome: DENIED` |
| `ToolRegistry` has no `pay`/`book`/`execute` | — | **By design.** An absent tool beats a disabled one. |
| No rate limiting | Medium | **Not implemented.** §26 asks for it; in-memory Phase 4 has no request boundary to attach it to. Belongs with the HTTP surface. |
| Memory vault is in-memory only | Medium | Deliberate for Phase 4. No persistence means no at-rest encryption story yet. |

**Honest limitation:** §26 lists rate limits and audit logging. Audit logging is
done (the hash-chained ledger). **Rate limiting is not** — it needs a transport
layer that does not exist yet. Flagged rather than faked.

---

## 6. Remaining blockers

| # | Blocker | Status |
|---|---|---|
| **B1** | No licence on `rumi-main`, `CONSUMER-main` | **OPEN.** See `licensing-blockers.md`. |
| **B2** | No booking/purchase execution | Not started (§31 defers) |
| **B3** | No payment provider | Not started (§31 defers) |
| B10 | `inheir.ai` has zero tests | Unchanged |

**B1 shaped Phase 3.** PROXY is unlicensed, so its memory *implementation* could
not be copied. `memory.py` was written from scratch in Beacon's Apache-2.0 tree,
matching PROXY's method names so a later adapter is a thin bridge. No line of
PROXY or Rumi source is in `beacon/peoplepay/`. No licence was added to anyone
else's project (§37).

---

## 7. §38 demonstration — verified

Turn 1, `"எனக்கு ₹50,000 குள்ள ஒரு நல்ல laptop தேவை."`

| # | Criterion | Result |
|---|---|---|
| 1 | Raw Tamil preserved | ✓ byte-identical |
| 2 | Language detected | ✓ `ta-Latn` (mixed script, correctly) |
| 3 | Transaction created | ✓ one id |
| 4 | Normalized intent | ✓ `laptop`, stored separately |
| 5 | Budget stored | ✓ `{minor: 5000000, currency: INR}` |
| 6 | Currency INR | ✓ |
| 7 | Preference/inference correct | ✓ separate kinds |
| 8 | Private memory retrieved | ✓ 1 ref |
| 9 | Plan created | ✓ `executed: False` |
| 10 | Nothing purchased | ✓ |
| 11 | Explains what it may do | ✓ "I can search and put together a plan" |
| 12 | Asks before consequential action | ✓ `AUTHORIZATION_REQUEST` |

Turn 2, `"₹45,000 குள்ள இருந்தா வாங்கலாம்."`

- Conditional grant recorded, autonomy → `CONDITIONAL`, cap ₹45,000
- ₹44,000 **allowed**; ₹47,500 **refused** — even though a ₹47,500 plan had
  already validated. Bounded authority holds.
- Payment still does not execute: `provider_status: NOT_CONFIGURED`,
  `executed: False`. No fake success event (§27).
- Ledger: 8 events, **hash chain intact**.

---

## 8. Success criteria (§39)

| Criterion | Status |
|---|---|
| Existing Beacon tests pass | ✓ 79/79 unchanged |
| Transaction aggregate exists | ✓ |
| One canonical transaction ID | ✓ |
| `raw_utterance` preserved | ✓ and substitution refused |
| INR default intact | ✓ |
| `EvidenceClass` semantics intact | ✓ reused, not replaced |
| Sandbox cannot become production | ✓ (defect found and fixed) |
| `USER_PREFERENCE` / `USER_INFERENCE` separate | ✓ |
| PROXY memory reused, not duplicated | ✓ interface mirrored; see B1 |
| Memory retention exists | ✓ 4 classes |
| Memory visibility exists | ✓ 4 scopes, private default |
| Social experience model, private by default | ✓ data model only |
| Conditional autonomy works | ✓ |
| Search vs payment authority separate | ✓ |
| Agent works through controlled tools | ✓ 9 tools |
| Agent cannot execute arbitrary code | ✓ no execute/pay/book tool |
| Documentation updated | ✓ |
| Licensing blockers documented | ✓ |
| No premature provider integration | ✓ none added |

**One criterion is partial:** "social experience model exists but is private by
default" — the *data model* exists and is private. The `Experience` object of §17
was **not** built as a standalone class; experiences are memory items with
separately-scoped price and date fields. That satisfies the privacy requirement
and invariant 9, but a future aggregation service will need a real `Experience`
type. Called out rather than ticked.

---

## 9. Already present alongside Phase 1–4

Work from earlier in this session (commits `d3f2f6e`..`6b29426`) sits outside
`beacon.peoplepay` and is **not** covered by the 70 invariant tests:

| Path | Purpose |
|---|---|
| `transaction/store.py` | Central store; imports the canonical aggregate |
| `transaction/eventbus.py` | Event bus (§27) |
| `transaction/aggregate.py` | **Re-export only** — see below |
| `adapters/base.py`, `bridge.py` | Capability contract and the join point |
| `adapters/market.py` | InflationForge (MIT, unblocked) |
| `adapters/spatial.py` | Rumi room context — **B1 applies, see below** |
| `gateway/__init__.py` | Placeholder |

**Two aggregates briefly existed and were converged.** Commit `415a371` removed
the competing `transaction/aggregate.py` implementation and made it a re-export
of `beacon.peoplepay.transaction.Transaction`, so that `transaction.aggregate`
and `beacon.peoplepay.transaction` are now **the same class object** (verified:
`A is B` → `True`). One id, one lifecycle, per §5.

**A licensing question this raises.** `adapters/spatial.py` targets Rumi, which
is unlicensed (B1). An adapter that only *calls* a service Rumi's owners run is
fine; one that embeds Rumi's logic or data structures is not. **This file should
be reviewed against `licensing-blockers.md` §3 before any distribution.** I did
not write it and have not audited it for copied expression.

## 10. Next integration candidates

1. **Test the adapter/store layer.** It has no invariant tests. The store, event
   bus and both adapters are unverified by the suite that guards everything else.
2. **Audit `adapters/spatial.py` for B1 compliance** (above).
3. **HTTP surface** — where rate limiting and per-request identity belong.
4. **InHeir** (property) — MIT, unblocked, but zero tests (B10).
5. **PROXY** (resolution) — blocked on B1. The `DISPUTE_REQUIRED → RESOLVED` path
   that `states.py` declares and nothing implements.

Only after those: YouTube, Telegram, community experiences, transport/NCMC, exam
booking, payment providers, real-money execution.

---

## 11. Stopping here

Per §40, no further implementation. The decisions needed before the next wave:

1. **Licences for `rumi-main` and `CONSUMER-main`** (B1) — blocks two of the four
   next candidates.
2. **Persistence choice** — DynamoDB matches Beacon; anything else means a second
   store in the system.
3. **Payment provider sandbox** (B3) — Razorpay suits INR; Stripe is easier to test.
4. **Cohort threshold** for invariant 9 — what is the minimum contributor count
   before an aggregate may be shown?
5. **`Experience` as a first-class type** — needed before any community feature.
