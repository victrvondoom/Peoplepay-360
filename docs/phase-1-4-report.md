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
| Beacon offline suite | 307 passed, 1 failed | **377 passed, 1 failed** | +70 passed |
| Root suite (`tests/`) | — | **210 passed** | +210 new |
| `ruff check` (all new code) | — | **clean** | — |
| `mypy` (`beacon.peoplepay`) | — | **clean, 6 files** | — |
| `mypy` (`adapters/ gateway/ transaction/`) | 6 errors | **clean, 15 files** | −6 |

Root suite breakdown, measured: integration layer 50, gateway 48, property
adapter 22, resolution adapter 23, SQLite store 32, auth 35.

The gateway file grew 17 → 48: body limits, environment-driven configuration,
dispatch shape checking, and four tests that bind a real loopback socket
because the connection bug in §5 is invisible to a stub.

**Total: 587 passing tests** (377 Beacon + 210 root), one pre-existing unrelated
failure (`test_hardening.py` — numpy pinned 2.5.3, environment has 1.26.4;
recorded in `test-baseline.md` before this work began).

Two suites, two runners, because the code lives at two levels:

```
cd Beacon-main && python -m pytest      # beacon.assurance + beacon.peoplepay
cd .           && python -m pytest      # transaction/, adapters/, gateway/
```

The root `pytest.ini` scopes collection to `tests/` and excludes the five
acquired projects — collecting them from the root fails on duplicate test
basenames and an `ImportPathMismatchError` in `CONSUMER-main`.

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
| No rate limiting | Medium | **Now closed.** The gateway (`c0539fe`) added a per-caller sliding-window limiter; `tests/test_gateway.py` pins it, including thread safety under 8 concurrent threads. |
| Memory vault is in-memory only | Medium | **Still open.** Transactions are now durable (`SqliteTransactionStore`); the *memory vault* is not. A restart keeps the transaction and loses the user's preferences. |
| No at-rest encryption on the SQLite file | Medium | **Open.** The file holds verbatim utterances and budgets in plaintext. SQLite has no built-in encryption; this needs filesystem-level protection or SQLCipher. |
| `/health/integrations` exposed internal `endpoint` values | Low → **closed** | **Fixed.** `HealthReport.to_dict(include_endpoint=False)` omits it by default; the gateway passes `include_endpoint=True` only for an authenticated caller. Unauthenticated readers get `endpoint_configured: true/false` — *whether*, never *where*. |
| Header-asserted identity (`X-Beacon-User` trusted as sent) | High → **closed** | **Fixed.** `gateway/auth.py` verifies an HMAC-signed bearer token; 35 tests. |
| Unbounded request body: `Content-Length` drove `rfile.read()` | Medium → **closed** | **Fixed.** Refused against `MAX_BODY_BYTES` *before* the read, so a declared length can no longer drive allocation. |
| Malformed `Content-Length` raised an unhandled `ValueError` | Low → **closed** | **Fixed.** `int()` on an attacker-controlled header now yields a 400 instead of a 500. |

### Closed: identity is now verified

`gateway/auth.py` issues and verifies `v1.<user-b64>.<expiry>.<hmac-sha256>`
against `BEACON_GATEWAY_SECRET`. Properties, each pinned by test:

- a forged user id **fails the signature** (the test keeps the original
  signature and swaps the id — refused)
- the signature covers the expiry, so it **cannot be extended** alone
- a token signed with a different secret is refused
- **in VERIFIED mode `X-Beacon-User` is ignored entirely**, so the header cannot
  bypass the check the token exists to perform
- `hmac.compare_digest` for constant-time comparison; one `InvalidToken` type for
  every rejection, so probing learns nothing about which check failed

**Open mode is retained deliberately and loudly.** With no secret set the bare
header is still accepted so local development is unaffected — but
`/health/integrations` reports `auth.mode: "OPEN"` with *"caller identity is
unverified, local use only"*, and `serve()` prints the same line at boot. A
deployment that forgets the secret can be *seen* to have forgotten it.

**This is symmetric-secret auth for a first-party gateway, not OIDC.** No issuer,
audience, key rotation or revocation list. Replacing `verify_caller` is the
single seam for a real IdP.

### Closed: the health page no longer leaks internal URLs

Fixed at the source rather than the caller: `HealthReport.to_dict()` takes
`include_endpoint=False` and the value is **never serialized** for an
unauthenticated reader, rather than written and then blanked. `missing_config`
stays visible either way — it names environment variables, which is a deployment
hint rather than a network target.

**§26 status — now complete.** Audit logging: done (hash-chained ledger). Rate
limiting: done, per-caller sliding window, thread-safe under contention.
Per-request identity: **done and verified**.

### Closed: the request body is bounded, and a refusal is readable

`_body` read `Content-Length` straight into `int()` and then into
`rfile.read(length)`. Both halves of that were wrong on a surface that fronts
money: a non-numeric header became an unhandled `ValueError` (a 500 that tells a
prober the parse crashed), and a large one was an allocation the caller chose.

Now the header is treated as a claim at every step — non-numeric, negative, over
`MAX_BODY_BYTES`, or shorter than declared are each a 400 — and the size check
happens before the read.

**A bug the fix introduced, found only by running the server.** Refusing without
reading leaves the body in the socket, so under `HTTP/1.1` keep-alive the next
request parses mid-body. Setting `close_connection` was not enough either:
`send_response` advertises keep-alive regardless, so the server closed a socket
the client still believed it could reuse — and closing with unread data in the
receive buffer sends RST, which destroys the 400 before the caller can read it.
The limit was protective and unusable at the same time.

The working shape is all three together: drain the refused body in bounded chunks
(never buffered whole, capped by `DRAIN_LIMIT`), send an explicit
`Connection: close`, and set `close_connection`.

**Worth recording because of how it was caught.** The unit tests were green
throughout — they drive `_body` with a `SimpleNamespace` stub, which has no
socket to desynchronize. Only an end-to-end run against a live server surfaced
it, and reproducing it in the suite needed `http.client` with a *reused*
connection; `urllib.request` opens a fresh one per request and never reads the
corrupted socket. `TestRefusalOnAReusedConnection` pins it, and was confirmed to
fail with the drain removed.

### Configuration is read from the environment, and bad values are visible

`RATE_LIMIT`, the rate window, the body limit, the drain cap, the bind host, the
port and all four adapter timeouts now come from the environment, defaulting to
the values that were previously hardcoded — so an unset environment changes
nothing.

The failure mode worth designing against is not a typo, it is a typo that
silently disables a control: `BEACON_GATEWAY_RATE_LIMIT=sixty` must not yield an
unlimited gateway, and `=0` must not either. So `_env_int` / `_env_float` keep the
default, refuse values below a floor, and record what they rejected — surfaced in
`/health/integrations` as `config_warnings` and printed at boot, not only logged.

The bind host stays `127.0.0.1` by default. This surface has an `OPEN` auth mode,
so it must not become externally reachable merely because it was deployed
somewhere with a public interface.

Every knob, with the default it falls back to:

| Variable | Default | Effect |
|---|---|---|
| `BEACON_GATEWAY_SECRET` | *unset* | HMAC secret. Unset → `OPEN` mode, reported on the health page. |
| `BEACON_GATEWAY_HOST` | `127.0.0.1` | Bind interface. |
| `BEACON_GATEWAY_PORT` | `8080` | Bind port. |
| `BEACON_GATEWAY_RATE_LIMIT` | `60` | Requests per caller per window. Floor 1. |
| `BEACON_GATEWAY_RATE_WINDOW_SECONDS` | `60.0` | Sliding window length. |
| `BEACON_GATEWAY_MAX_BODY_BYTES` | `1048576` | Largest accepted request body. Floor 1024. |
| `BEACON_GATEWAY_DRAIN_LIMIT` | `8388608` | How much of a refused body is drained so the 400 is readable. |
| `BEACON_GATEWAY_VERBOSE` | *unset* | Request logging to stderr. |
| `BEACON_SPATIAL_URL` / `_TIMEOUT` | *unset* / `15.0` | Rumi endpoint and timeout. |
| `BEACON_MARKET_URL` / `_TIMEOUT` | *unset* / `15.0` | InflationForge endpoint and timeout. |
| `BEACON_PROPERTY_URL` / `_TIMEOUT` | *unset* / `20.0` | InHeir endpoint and timeout. |
| `BEACON_RESOLUTION_URL` / `_TIMEOUT` | *unset* / `60.0` | PROXY endpoint and timeout. |

The four timeouts differ because the upstreams do: PROXY runs a multi-agent case
workflow and is slow by nature, while a price lookup either answers quickly or is
down. An unset `*_URL` is `NOT_CONFIGURED` — still listed on the health page,
because hiding it would make that page a lie by omission.

### The gateway dispatch is now type-checked

`_dispatch` was annotated `Capability`, the abstract base, while calling
`room_context`, `price_evidence`, `location_intelligence`, `property_reports`,
`run_case` and `ask` — none of which it declares. Six `attr-defined` errors, and
correct only because each route happened to be paired with the right adapter.

Four `runtime_checkable` protocols now name the four call shapes
(`SpatialCapability`, `MarketCapability`, `PropertyCapability`,
`ResolutionCapability`), following `TransactionStore`. The explicit per-route
dispatch is unchanged — a generic `getattr` would still let a request name any
method — but it now narrows through the protocol first. Since `capabilities` is
injectable, a substituted adapter that lacks the call reads as a 400 rather than
surfacing as an `AttributeError` dressed up as a 502 from a provider that was
never contacted.

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

**Items 1–3 are now done.**

1. ~~Test the adapter/store layer~~ — **done.** 53 tests in
   `tests/test_integration_layer.py` covering the store's one-aggregate-per-id
   guard, tamper detection on the hash chain, the event bus, the capability
   contract, the float→`Money` boundary (audited conflict C1), and the bridge.
2. ~~Audit `adapters/spatial.py` for B1~~ — **done, cleared.** See
   `licensing-blockers.md` §2a. No copied expression; it is an HTTP client with
   no geometry implementation. Three tests now enforce that property so a future
   inlining of Rumi's planner fails the suite.
3. ~~HTTP surface~~ — **exists** (`gateway/app.py`, `c0539fe`) and is now tested:
   14 tests covering the rate limiter, health reporting, and the unauthenticated
   health surface. One new open finding (§5).

4. ~~Decide the `/health/integrations` exposure~~ — **done.** Redacted for
   unauthenticated callers, at the source (`HealthReport.to_dict`).
5. ~~Replace header-asserted identity~~ — **done.** `gateway/auth.py`, 35 tests.
6. ~~Persistence~~ — **done.** `transaction/sqlite_store.py`, event-sourced, 32
   tests. See below.
7. **InHeir** (property) and **PROXY** (resolution) adapters now exist with tests
   (22 and 23). Both were added in parallel with this work; **neither has been
   reviewed by me**, and PROXY remains **blocked by B1** for distribution.

### Persistence, as built

`SqliteTransactionStore` implements the existing `TransactionStore` protocol, so
swapping it for the in-memory store is a constructor change.

**Event-sourced on purpose.** Each ledger event is a row; `get()` replays them
and calls `verify_chain()` *before* returning the aggregate. Storing only current
state would mean trusting a row someone could have edited. Pinned by five
tamper tests: editing an actor, deleting an event, and rewriting a `detail` blob
are each caught on load, and `verify_all()` names the broken transaction while
leaving the intact one alone.

**A bug this found in my own code.** The first version persisted no mandate at
all, so a reloaded transaction came back with `max_amount = None` — the user's
stated budget cap silently gone. A dropped constraint *widens* what the agent may
do, which is the worst direction for a persistence bug to fail in, so all 20
`IntentMandate` fields are now serialized explicitly and a test asserts the
restrictive ones (`blocked_merchants`, `required_condition`, `require_warranty`)
survive.

Money is stored as integer minor units inside JSON (`{"minor": 5000000,
"currency": "INR"}`); a test greps the raw row to prove no float representation
appears.

Remaining, in order:

8. **Review the property and resolution adapters.** They arrived with tests but
   without my audit — the spatial adapter needed a B1 licensing review, and
   PROXY is the *other* unlicensed project, so the resolution adapter needs the
   same check before any distribution.
9. **Durable memory vault.** Transactions survive a restart; the user's
   preferences do not.
10. **At-rest protection for the SQLite file** — it holds verbatim utterances and
    budgets in plaintext.

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
