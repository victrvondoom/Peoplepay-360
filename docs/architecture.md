# PeoplePay — Personal Transaction Intelligence Network

**Status:** Phases 1–4 implemented and tested. Phases 5+ not started.
**Date:** 2026-09-27
**Implementation:** `Beacon-main/src/beacon/peoplepay/` — see
[`phase-1-4-report.md`](phase-1-4-report.md) for measured results and
[`licensing-blockers.md`](licensing-blockers.md) for B1.

> **Phase 1–4 as built.** The plan below was followed, with these concrete
> outcomes:
>
> | Phase | Module | Result |
> |---|---|---|
> | 1 | `peoplepay/transaction.py` | `Transaction` aggregate, one id, 7 context slots |
> | 2 | `peoplepay/nodes.py`, `authority.py` | 18 node kinds, 10 source types, 5 permissions, 9 transaction types |
> | 3 | `peoplepay/memory.py` | 4-scope vault, retention + visibility, preference/inference wall |
> | 4 | `peoplepay/agent.py` | Thin shell, 9 controlled tools, no execute/pay/book |
>
> **Tests: 79/79 assurance unchanged, +70 new invariant tests, ruff and mypy
> clean.** One pre-existing unrelated failure (`test_hardening.py`, Docker pin).
>
> Three findings worth carrying forward:
>
> - **A sandbox leak existed and was fixed.** `EvidenceNode.is_sandbox` reads
>   provenance off *observations*, so declaring a node sandbox in its payload
>   alone left it looking clean. Any future adapter must attach sandbox
>   provenance to an observation, not just a flag.
> - **`beacon.assurance` changed additively, once.** `evidence.py` gained new
>   `NodeKind`/`EdgeKind` members (spatial, property, document, scan, market,
>   booking, resolution). No member moved or was removed and no logic changed,
>   which is why the 79 tests pass unmodified. Keep future changes additive.
> - **`transaction/aggregate.py` is a re-export, not a second aggregate.** A
>   competing implementation existed briefly and was converged onto
>   `beacon.peoplepay.transaction.Transaction`; both paths now yield the same
>   class object. Do not reintroduce a parallel aggregate.
> - **Rate limiting (§26) is not implemented.** It needs an HTTP boundary that
>   does not exist yet. Not faked.
**Supersedes:** the *structure* proposed in `integration-map.md` §4–5. That file's
per-project audit and conflict register (§2, §3) remain authoritative and are
referenced, not repeated, here.

---

## 0. What changed, and why it matters

The earlier plan treated this as five projects to be wired into a transaction
engine. This document treats it as **one agent that a user talks to**, which
happens to be backed by five projects.

That is not a rename. It changes what gets built first, and it adds four pillars
the earlier audit never assessed:

| New pillar | Status after verification |
|---|---|
| Personal memory / vault (§1–2) | **Partial foundation exists** — see below. Not greenfield. |
| Cross-platform evidence layer (§3–8) | Graph exists; **connectors are greenfield**. |
| User-to-user experience network (§9–11) | **Entirely greenfield.** Highest privacy risk in the system. |
| Transport as a transaction type (§14–16) | **Entirely greenfield.** |

The single most important structural claim of the new design — that the agent is
the interface and the transaction engine is the brain — is **compatible with what
is already on disk**, because `beacon.assurance` was built as a library with no
orchestrator. It has been waiting for exactly this.

---

## 1. Verified ground truth

Re-verified against the working tree on 2026-09-27, not carried over on trust:

| Claim | Verified |
|---|---|
| `beacon.assurance` is 2,752 lines across 6 modules | **Yes**, exactly |
| Its test suite passes | **Yes** — 79/79 in 0.23s, run independently |
| 33-state lifecycle incl. dispute/refund path | **Yes** — 19 happy-path + 14 exception states |
| `EvidenceClass` models graded confidence | **Yes** — and includes `CONFLICTING` and `UNAVAILABLE` |
| `Provenance` carries source + hash + timestamps | **Yes** — `source_url`, `raw_hash`, `retrieved_at`, `sandbox` |
| `IntentMandate` keeps the user's verbatim words | **Yes** — `raw_utterance` |
| `IntentMandate` currency default | **`"INR"`** — already correct for the target market |
| `AutonomyLevel` has 3 human-in-the-loop modes | **Yes** — `HUMAN_PRESENT`, `CONDITIONAL`, `AUTONOMOUS` |
| No LICENSE on `rumi-main`, `CONSUMER-main` | **Still true.** Blocker B1 stands. |
| No YouTube / Telegram / Reddit connector anywhere | **Confirmed absent** |
| No NCMC / UPI / transit-fare code anywhere | **Confirmed absent** |

### The find that changes the memory plan

`CONSUMER-main/backend/app/services/memory_service.py` (94 lines) already
implements **three tiers of memory**, and does so on top of the existing
`CaseRepository` rather than a new store:

- `get_conversation_memory(case_id)` — chronological event history
- `get_case_memory(case_id, user_id)` — one case's documents, agent runs, drafts
- long-term user memory — a user's prior cases, capped at `MAX_USER_HISTORY_CASES = 5`

This is the same layering §1–2 of the new brief asks for, and it independently
confirms the design instinct. **Reuse the pattern; do not invent a fourth memory
concept.** What it does not yet have: retention controls, expiry, per-field
sharing consent, or the fact/preference/inference distinction of §2.

---

## 2. The architecture

```
                         PEOPLEPAY AGENT
              (multilingual; the only interface)
                              │
        ┌─────────────────────┼─────────────────────┐
        ↓                     ↓                     ↓
     MEMORY               EVIDENCE                ACTION
   my history            the world              secure agents
        │                     │                     │
        └─────────────────────┼─────────────────────┘
                              ↓
                    TRANSACTION ENGINE
                  (= beacon.assurance + aggregate)
                              ↓
                  VERIFY → EXECUTE → MONITOR
```

Every layer operates on **one `transaction_id`**. That is the load-bearing
invariant: it is what makes a room scan, a metro journey and an exam booking the
same kind of object rather than four applications.

### Layer map to real code

| Layer | Source | Reality |
|---|---|---|
| Agent / language / voice | — | **Greenfield.** Thin: intent → mandate. No money logic. |
| Memory | PROXY `memory_service` pattern | Extend with retention + consent |
| Evidence graph | `beacon.assurance.evidence` | **Exists.** Add node kinds. |
| Evidence connectors | — | **Greenfield** (YouTube, Telegram, Reddit, community) |
| World intelligence | Rumi, InflationForge, InHeir | Exists; adapters needed |
| Transaction + policy | `beacon.assurance` | **Exists, tested** |
| Security / sandbox | Beacon safety model | **Exists** — strongest asset in the repo set |
| Execution / payment | — | **Greenfield.** Blockers B2, B3. |
| Resolution / dispute | PROXY | Exists; stronger than the old brief assumed |
| Social / experience graph | — | **Greenfield.** Privacy-critical. |

---

## 3. Where the new design needs the engine extended

All additive. None requires touching the 79 passing tests.

### 3.1 `NodeKind` — new members

The graph has 25 node kinds, all commerce-shaped. The new architecture needs:

```
ROOM_SCAN         SPATIAL_PLAN      PROPERTY        LEGAL_DOCUMENT
RECEIPT           BILL              CASH_PAYMENT    TRANSIT_JOURNEY
EXAM_REGISTRATION BOOKING           SUBSCRIPTION
COMMUNITY_EXPERIENCE                CREATOR_REVIEW
USER_MEMORY       USER_PREFERENCE   USER_INFERENCE
```

The last three carry §2's discipline into the type system: **`USER_PREFERENCE`
and `USER_INFERENCE` are different node kinds**, so an inference cannot silently
become a preference. It would have to be re-created as a different type, by an
actor, with provenance — which is auditable.

### 3.2 `EvidenceClass` — no change needed

`CONFLICTING` already covers §3's "don't just average everything", and
`UNAVAILABLE`/`UNKNOWN` already cover §11's "never fabricate". `SANDBOX` already
prevents a simulated result from laundering itself into a real claim.

For §6 (YouTube is evidence, not proof), the honest mapping is:
creator content → `UNVERIFIED` with `Provenance.source_url` retained, **never**
`VERIFIED`. Sponsorship disclosure becomes an `Observation` on the node, with
`detected | undetected | unknown` — not a boolean, because absence of detection
is not absence of sponsorship.

### 3.3 New: `TransactionType`

```
PURCHASE  BOOKING  EXAM  TRANSPORT  PROPERTY
SERVICE   BILL     TRANSFER  SUBSCRIPTION
```

### 3.4 New: `PaymentMethod` — including CASH

```
UPI  CARD  BANK  WALLET  NCMC  CASH  OTHER
```

`CASH` is not a degenerate case, it is a first-class path (§18–19): the receipt
is the evidence, the camera is the capture device, and reconciliation compares
`expected` against `observed`. `Money` already refuses to invent precision, so a
cash mismatch surfaces as a real state rather than a rounding difference.

### 3.5 Context separation: personal vs business (§17)

Same engine, different policy context. `PolicyEngine` already branches on values,
so this is configuration, not a second engine:

| | Personal | Business |
|---|---|---|
| Limits | personal | policy + approval chain |
| Evidence | personal history | + cost centre, invoice, tax |
| Authority | the user | delegated, with chain |

**Never share a vault across contexts.** A business expense must not teach the
personal recommender, and vice versa.

---

## 4. The privacy design for §9–11 — the riskiest new pillar

The user-to-user network is the most valuable idea in the new architecture and
the one most likely to cause real harm if built naively. §10 is right, and the
constraint should be structural rather than a policy promise:

1. **Default is anonymous verified experience.** Ownership period, rating,
   comment, purchase-verified flag. No identity, no price, no date.
2. **Price and date are separate opt-ins** from the experience itself. They are
   the two fields most able to deanonymise a user in a small cohort.
3. **Suppress small cohorts.** Below a threshold of contributors, aggregate
   statistics are `UNAVAILABLE` — not shown with a caveat. With 3 buyers in one
   city, "average price paid" identifies people.
4. **Routing a question (§9) never reveals the asker or answerer.** Consent is
   per-question, revocable, and not a standing subscription.
5. **Verified purchase is a claim about a transaction, not about a person.**

This maps onto existing machinery: a community experience is an
`EvidenceNode` with `Provenance`, so it is already append-only, hashed and
attributable — the graph cannot quietly rewrite what someone said.

---

## 5. Connector layer (§20–21)

One interface, per §20. The engine calls capabilities; it does not know brands.

```
search()  get_details()  verify()  quote()
book()    pay()          cancel()  refund()   status()
```

Every connector must additionally report its own honesty:

```
health() -> LIVE | SANDBOX | NOT_CONFIGURED | UNAVAILABLE
```

InflationForge's `ModeStatus` already does exactly this per-provider, so the
pattern is proven in this codebase rather than imported from theory.

**A connector that cannot do something returns `NOT_CONFIGURED`. It never
returns a plausible-looking result.** This is the rule that keeps a demo from
becoming a lie.

---

## 6. What is honestly missing

Unchanged from the prior audit, and the new scope adds to it. Stated plainly
because the new architecture is broader than the old one, not narrower:

| # | Gap | Status |
|---|---|---|
| **B1** | No licence on `rumi-main`, `CONSUMER-main` | **BLOCKER.** Verified still true. |
| **B2** | No booking / purchase execution anywhere | Greenfield |
| **B3** | No payment provider anywhere | Greenfield |
| B4 | No YouTube / Telegram / Reddit connector | Greenfield |
| B5 | No transport, NCMC or UPI integration | Greenfield |
| B6 | No experience graph / user-to-user layer | Greenfield |
| B7 | No speech or translation layer | Greenfield |
| B8 | No SKU-level or INR price intelligence | Greenfield (InflationForge is USD city baskets) |
| B9 | No receipt / bill / price-tag classifier | Greenfield (Rumi scans rooms only) |
| B10 | `inheir.ai` has zero tests | Fix before any money path |

Two scope notes carried forward because they remain true and remain
load-bearing: **PROXY is a dispute engine, not a booking agent**, and **Beacon is
an AWS incident responder** whose reusable assets are its safety pattern and the
`assurance` library.

Agentic UPI, NCMC interoperability and UCP are real directions, but they are
**external dependencies on provider availability**, not things this repo can
assume. Until a provider is actually connected, the honest state is
`NOT_CONFIGURED`.

---

## 7. Build order

Ordered so that blockers surface before work depends on them, and so the agent
becomes demonstrable early on one narrow path rather than late on all of them.

| Phase | Work | Why here |
|---|---|---|
| 0 | Resolve **B1** (licences) | Nothing distributable until then |
| 1 | `Transaction` aggregate + store + event bus on `beacon.assurance` | The one missing piece of the core |
| 2 | Additive `NodeKind` / `TransactionType` / `PaymentMethod` | Cheap, unblocks everything |
| 3 | Personal vault, extending PROXY's 3-tier pattern, **with retention + fact/preference/inference separation** | Memory is first-class per §1 |
| 4 | Agent shell: intent → `IntentMandate`, preserving `raw_utterance` | The interface; thin by design |
| 5 | Evidence connectors — start with **one** (YouTube), graded `UNVERIFIED` | Proves §3–6 without breadth |
| 6 | Adapters: Rumi, InflationForge, InHeir, PROXY + `/health/integrations` | Existing capability, honestly labelled |
| 7 | Multilingual + voice (Tamil / Tanglish / English) | Needs the mandate path first |
| 8 | Commerce execution, sandboxed (**B2**) | Highest risk; after policy + evidence |
| 9 | Payment against a real provider sandbox (**B3**) | Never before phase 8 |
| 10 | Cash + receipt reconciliation | Depends on capture + `Money` |
| 11 | Experience graph, anonymous-by-default (**B6**) | Needs real transactions to aggregate |
| 12 | Transport (**B5**), exam booking, business context | Provider-gated |
| 13 | End-to-end: intent → evidence → contract → authorize → sandbox pay → verify → remember | The actual proof |

Phases 1–4 are the smallest set that makes the central claim of this document
real: one agent, one transaction id, one memory.

---

## 8. The unified rule

All five projects independently converged on the same discipline, which is the
reason this integration is viable at all:

> **The model proposes, code checks, evidence decides, the user authorizes,
> and no gap is ever filled with a guess.**

The new architecture adds one clause, for the memory and social layers:

> **And nothing about a person is shared, inferred into a preference, or
> aggregated into a statistic without that person's explicit, revocable consent.**

---

## 9. Open questions

Carried forward unresolved, plus new ones the expanded scope raises:

1. **Licences (B1)** — can `rumi-main` and `CONSUMER-main` be licensed?
2. **Payment provider (B3)** — Razorpay/UPI suits INR; Stripe is easiest to test.
3. **Booking (B2)** — build, or narrow scope?
4. **Cohort threshold (§10)** — minimum contributors before an aggregate is shown?
5. **Retention defaults (§1)** — what expires, and after how long, by default?
6. **Languages** — Tamil + English + Tanglish first, or wider?
7. **Voice** — on-device or cloud speech? Different privacy properties.
8. **InHeir tests (B10)** — add coverage before wiring into a money path?
