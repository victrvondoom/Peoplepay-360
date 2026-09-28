# PeoplePay Build Sequence

**Product:** evidence-backed transaction agent for room furnishing first, then
other high-stakes purchases and services.

**Rule:** a phase is complete only when its release gate is measured. Provider
credentials, legal approval, or production traffic must never be replaced by a
mock and called complete.

## Product invariant

Every consequential action carries a proof bundle:

```
user instruction + evidence snapshot + policy verdict + consent
+ exact cart/amount + execution receipt + resulting state
```

The bundle is attached to one `transaction_id` and preserved in the evidence
graph and hash-chained ledger.

## Status legend

- `DONE`: implemented and tested in this repository.
- `IN PROGRESS`: foundation exists; the phase still has open gates.
- `BLOCKED`: needs a licence, provider, credential, counsel, or external pilot.
- `NOT STARTED`: no production-capable implementation exists yet.

## Sequence

| Phase | Deliverable | Cons addressed | Status | Release gate |
|---|---|---|---|---|
| 0 | Licensing and product boundary | C1 scope, C4 licensing | **BLOCKED** | Written licence for Rumi and PROXY, or approved clean-room replacement plan. Only the furnishing journey is launch scope. |
| 1 | Canonical transaction foundation | C1 scope, C5 complexity, C12 testing | **DONE** | One aggregate/id, typed permissions, memory, evidence graph, ledger, stores, event bus, gateway, and adapters; root tests green. |
| 2 | Proof-carrying controls | C2 payment, C6 cost, C7 security, C8 regulation, C9 AI, C13 cold start | **DONE (core)** | Signed short-lived mandate capsules, exact cart hashes, risk-adaptive autonomy, hard cost budgets, revocable consent, and small-cohort suppression all pass deterministic tests. |
| 3 | Furniture wedge contract | C1 scope, C9 AI, C14 UX | **IN PROGRESS** | One normalized product/variant/merchant schema; exact dimensions and INR amounts; unknown shipping/tax visibly unresolved; no checkout yet. |
| 4 | Product Truth Passport | C3 dependencies, C9 AI, C13 cold start | **IN PROGRESS** | Required claims carry source, raw hash, retrieval time, freshness and evidence class. Conflicts and stale claims block consequential action. Add GS1 identifiers when available; never invent one. |
| 5 | Rumi spatial service | C4 licensing, C5 complexity, C9 AI | **BLOCKED** | Service-boundary integration until licensed. Real room scan, locked items, polygon/door clearance, and cart/room consistency pass end-to-end tests. |
| 6 | Market and catalog providers | C3 dependencies, C6 cost, C10 merchant automation, C13 cold start | **NOT STARTED** | At least two API/feed sources where practical; provider health and stale-cache behavior tested; SKU/variant-level INR evidence available. |
| 7 | Commerce protocol layer | C3 dependencies, C5 complexity, C10 merchant automation | **NOT STARTED** | API-first UCP/ACP connectors with typed quote, checkout, cancel, refund and status calls. Browser fallback is visible, user-controlled, allowlisted, and cannot bypass CAPTCHA. |
| 8 | Payment sandbox | C2 payment, C7 security, C8 regulation, C12 testing | **BLOCKED** | Licensed/provider-hosted sandbox selected. Credentials never enter model context. Durable atomic mandate consumption, idempotency, reconciliation and kill switch tested. |
| 9 | Fulfilment and compensation | C3 dependencies, C10 merchant automation, C12 testing | **NOT STARTED** | Multi-merchant partial success, duplicate callback, timeout, cancellation and refund simulations preserve exactly-once financial effects. |
| 10 | Resolution and legal handoff | C4 licensing, C8 regulation, C11 legal expectations | **BLOCKED** | PROXY remains a service or is clean-room rebuilt. Output is cited case preparation, not legal advice. Qualified-advocate handoff and user-reviewed filing are enforced. |
| 11 | Private outcome network | C7 security, C8 regulation, C13 cold start | **IN PROGRESS** | Product remains useful with zero community data. Separate consent for review, price and date; cohort threshold and query privacy budget enforced; withdrawal removes future eligibility. |
| 12 | Security and compliance gate | C7 security, C8 regulation | **NOT STARTED** | Threat model, independent penetration test, data-flow inventory, retention/deletion proof, incident drill, provider contracts and jurisdiction counsel sign-off. |
| 13 | Reliability and AI evaluation | C3 dependencies, C9 AI, C12 testing | **NOT STARTED** | Fault injection and adversarial suites cover stale prices, prompt injection, conflicting dimensions, replay, race, outage and refund failure. No unauthorized or duplicate action. |
| 14 | Guided user experience | C14 UX | **NOT STARTED** | Users can identify the exact items, total ceiling, evidence gaps, next action and cancellation path in moderated usability tests. Advanced evidence is progressive disclosure. |
| 15 | Closed furnishing pilot | All | **BLOCKED** | Limited users and merchants, strict spending caps, human-present payment, incident on-call, positive unit economics, and predefined rollback criteria. |
| 16 | Domain expansion | C1 scope | **BLOCKED** | Add one domain only after the furnishing flow meets safety, completion, dispute, satisfaction and cost targets for two consecutive release cycles. |

## Phase 2 implementation

The first new controls live in `Beacon-main/src/beacon/peoplepay/`:

- `mandate.py`: exact cart snapshots and HMAC-signed mandate capsules. A changed
  cart, merchant, currency, ceiling, user, transaction, signature or expiry is
  rejected. Alternatives must be approved as exact additional cart hashes.
- `governance.py`: deterministic risk disposition, transaction-level provider
  budgets, purpose-bound consent, withdrawal, community cohort suppression and
  a bounded aggregate-query budget.
- `evidence_gate.py`: Product Truth Passports that require fresh, consistent,
  sufficiently corroborated claims and record every pass or block in the graph.

The current mandate consumption registry is intentionally in-memory. It is a
sandbox implementation, not a production payment primitive. Phase 8 requires a
durable atomic claim in the transaction store before any live payment connector
may be enabled.

## Architecture boundaries

1. The PeoplePay agent interprets language and proposes tool calls. It never
   performs money arithmetic, grants itself authority, or holds credentials.
2. The transaction engine checks evidence, permissions, risk, cost and mandate
   bindings using deterministic code.
3. Capability services expose typed contracts and honest health states:
   `LIVE`, `SANDBOX`, `MOCK`, `NOT_CONFIGURED`, or `UNAVAILABLE`.
4. Payment providers host credential entry and authentication. PeoplePay stores
   provider references and receipts, not primary payment secrets.
5. Legal output stops at evidence organization and user-editable drafts. Legal
   interpretation or representation routes to a qualified professional.
6. Community data is private input to aggregates. Contributor identity is never
   part of an aggregate response.

## Required scorecard

| Area | Launch metric |
|---|---|
| Authority | 0 unauthorized consequential actions |
| Money | 0 duplicate captures; 100% reconciliation |
| Evidence | 100% of required checkout claims sourced and fresh |
| Reliability | Successful recovery from every tested partial-failure scenario |
| Privacy | 0 aggregate responses below cohort threshold |
| Cost | Provider cost recorded for 100% of transactions; hard cap enforced |
| UX | At least 90% comprehension of cart, ceiling, uncertainty and cancellation |
| Resolution | Every failed order has a visible next action and owner |

## Definition of final product readiness

PeoplePay is ready only when a user can scan one room, approve a constrained
design, inspect the evidence behind every item, authorize one exact checkout,
complete provider-hosted payment, observe each merchant order, and start a
return or dispute without losing the original intent, evidence or receipts.

Until every phase-15 gate passes, the product is a controlled prototype and
must label sandbox and unavailable capabilities as such.
