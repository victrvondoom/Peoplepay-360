# PeoplePay system catalog

## Current verified integration, 2026-10-06

The reference procurement lifecycle is now implemented and tested: GreenChain/InflationForge SDK receipts -> ECHO -> exact approval -> Gateway/reference merchant -> partial-delivery event -> PROXY draft. CivicMesh additionally supplies real deterministic U.S. assistance policy results through the SDK into ECHO and the portal, with versioned follow-up. Live provider, identity, payment and specialist session limits remain.

| Project | Capability | Current / target level | Adapter / SDK | ECHO / Gateway / UI | Events and health | Tests and license | Limits |
|---|---|---|---|---|---|---|---|
| CivicMesh | Policy eligibility, next question, proposed plan/routes | 3 / 4 | Real HTTP service, SDK v1 normalization | Canonical graph decisions; advisory workflow; /assistance | Correlated SDK events; engine/model health split | Native golden + guard + boundary + SDK + graph; MIT | U.S. only, heuristic scores, bundled policy, no native session/SSO federation |
| GreenChain | Supplier/environment/logistics observations | 3 / 4 | Native service + explicit reference capture, SDK | Procurement graph and approved sandbox journey | Provider health, correlated journey | Native suite; upstream license unresolved | Live credentials and provenance/license rights unresolved |
| InflationForge | Dated price context | 3 / 4 | Native receipt adapter, SDK; scoped ECHO adapter | Procurement and price evidence | Health, observation times and journey events | Native suite; MIT | City basket observations are not merchant quotes |
| PROXY | Dispute drafts | 3 / 4 | Typed transaction evidence packet; live/reference adapter | Downstream automatic sandbox discrepancy handoff | Draft failure and retry preserved | Native tests; upstream license unresolved | No official submission or legal adjudication |
| Rumi | Room/product selection | 1 / 3 | Existing bounded spatial adapter; no complete SDK provider | Separate specialist UI | Existing capability health | Native tests; upstream license unresolved | Convex/Clerk/service contract still needed for full handoff |
| InHeir | Property/legal evidence | 1 / 3 | Existing bounded property adapter; no complete SDK provider | Separate specialist UI | Existing capability health | New native service regressions; MIT backend | Azure/Mongo credentials and full live journey remain |
| Beacon | Operations assurance | Separate operations plane | Existing assurance/runtime APIs | Separate operational approval/UI | Incident lifecycle and health | Native suite; retain upstream notices | Does not share consumer action authority |

See [CivicMesh report](integration/CIVICMESH_INTEGRATION_REPORT.md), [technical map](integration/CIVICMESH_TECHNICAL_MAP.md), [source of truth](architecture/SOURCE_OF_TRUTH_MATRIX.md), and [unified journey](unified-journey-v1.md).

## Earlier catalog snapshot

The remaining tables record the earlier unification stage; the current matrix above supersedes their integration-level statements.

This catalog describes how the code in this checkout fits the single PeoplePay
product without collapsing the applications into one runtime or dependency
tree. Integration levels: **0 linked**, **1 shared navigation**, **2 shared
identity/context**, **3 typed data handoff**, **4 two-way events**, **5 full
workflow**. Levels describe observed implementation, not aspiration.

| Component | Existing purpose / users | PeoplePay role | Current integration level | Evidence boundary / next work |
|---|---|---|---:|---|
| Gateway (`gateway/`, `transaction/`) | User transaction plans, evidence, sandbox orders and disputes | Product action layer; transaction reference and authorization owner | 3 for its existing root capability APIs; 1 for specialist directory | Live checkout is unavailable; merchant/order/PSP connectors and verified identity federation remain future work. |
| ECHO (`echo/`) | Graph-backed provenance and decision audit | Canonical trust and decision layer | 3 with scoped Gateway approval planning and normalized extension intake | It owns evidence lineage, not merchant truth. Multi-worker coordination and production SSO remain future work. |
| GreenChain (`GREENCHAIN-main/`) | Supplier search/ranking and sustainability/logistics analysis | Discovery and sourcing intelligence | 1 | Separate gateway link and documented intake; no enabled ECHO adapter. Resolve the missing LICENSE and model/data rights before distributing source. |
| InflationForge (`Inflation-Forge-main/`) | US city/item basket observations and market context | Price context | 3 for ECHO read-only scoped observation adapter; 1 for gateway link | ECHO adapter is disabled by default. Basket price is not an SKU quote or merchant price. |
| PROXY / CONSUMER (`CONSUMER-main/`) | Case research, evidence retrieval and dispute/report workflows | After-sales dispute assistance | 1 via gateway directory and bounded gateway capability API | ECHO does not have an active adapter. Review missing upstream license, service identity, output citation/provenance and draft submission boundaries. |
| Rumi (`rumi-main/`) | Room capture/design, product discovery and validated room plans | Design and product discovery workspace | 1 | Clerk/Convex/OpenAI/Exa workflows remain separate. No ECHO adapter; checkout is paused. Preserve exact dimensions, listed/estimated prices and uncertainty. |
| Beacon (`Beacon-main/`) | Platform assurance, incident response and approved remediation | Internal operations plane | 1 via gateway directory; operational assurance remains separate | Preserve Beacon auth/deployment and approval boundaries. No ECHO authority over operational remediation. |
| InHeir.AI (`inheir.ai-main/`) | Property/legal cases, document workflows and risk | Specialized property/legal vertical | 1 via gateway directory | Keep outside ordinary shopping unless a user contextually links a property transaction; no ECHO adapter. |
| Capability adapter layer (`adapters/`, `extensions/`, `packages/peoplepay-extension-sdk/`) | HTTP/service boundaries and ECHO extension manifests | Registry, health, timeouts, normalized proposals | 3 for current local contracts; SDK v1 package now defines shared contract types | SDK contracts and conformance tests exist. Existing adapters are not all rewritten against the package; registry integration is staged and must keep provider loading reviewed. |
| Root docs/tests and LFS data | Operator and developer context, regression suite, source corpora | Shared contributor entrypoint and audit evidence | 1 | Keep per-project tools, tests, attribution, and LFS objects intact. |

The mapped architecture is one user journey and audit lineage across bounded
services. It is not one database, a shared login, or merchant-of-record
authority. Details and per-project repository evidence are in
[`extensions/intake/bundled-projects.md`](extensions/intake/bundled-projects.md)
and [`integration-map.md`](integration-map.md).

## Capability lifecycle

```text
Discover / analyze / verify / resolve
        -> versioned extension request and raw provider receipt
        -> normalized PeoplePay proposal with provenance and uncertainty
        -> ECHO graph, correlation/identity/temporal checks and policy decision
        -> user / organization authorization
        -> Gateway action plan and transaction reference
        -> merchant/PSP remains authoritative for external order/payment
        -> authenticated lifecycle events, evidence timeline and after-sales
```

An extension failure should affect only that capability. ECHO or Gateway
failure blocks new trust-sensitive decisions or external actions, while
already-saved transaction records remain readable according to their owner
service. No extension receives general graph, transaction, or payment rights.

## Roadmap status

1. **SDK v1 contract package and conformance tests are implemented** at
   [`../packages/peoplepay-extension-sdk/`](../packages/peoplepay-extension-sdk/).
   They specify metadata, capabilities, context, request/result, health,
   evidence, entities, action proposals, and a correlated event envelope.
2. Connect reviewed provider implementations to this package through ECHO's
   core-owned registry. Preserve raw receipts separately from normalized ECHO
   claims, and do not make manifests executable code.
3. The existing Gateway `/` workspace is the unified product shell. Its
   `/product/modules` directory deep-links only to configured service URLs;
   unconfigured workspaces are shown disabled, and existing standalone UIs are
   preserved. Service health and cross-product identity are not yet federated.
4. Add per-domain handoff adapters only after exact upstream APIs, license,
   authentication, and data rights are verified. GreenChain, Rumi, PROXY,
   Beacon, and InHeir currently remain separate specialist workspaces.
5. Gateway already has a correlated in-process event bus and transaction
   ledger. Cross-service durable delivery, authenticated merchant webhooks,
   order reconciliation, and idempotent merchant adapters remain future work.
   Payment execution remains unavailable until a provider sandbox is selected
   and verified.

## Workflow map

| User journey | Implemented path | Current limit |
|---|---|---|
| Open a specialist workspace | Gateway `GET /product/modules` exposes configured URLs; the root UI displays cards. | Navigation/deep links only; no unified session across Clerk, Beacon, PROXY or InHeir. |
| Create and manage a purchase record | Gateway owns transaction state, evidence, plan, cart and sandbox order record. | Live checkout returns 503; sandbox records do not move money. |
| Evaluate evidence | ECHO accepts versioned extension requests, normalizes evidence proposals, and records provenance/decisions in FalkorDB. | Only reviewed/implemented adapters are usable; GreenChain and PROXY have no active ECHO provider. |
| Approve a consequential action | Human approval is explicit in ECHO-to-Gateway plan handoff and Gateway authorization. | No merchant payment/order execution or verified external completion. |
| Deliver, dispute, resolve | Gateway stores local lifecycle/dispute events; PROXY can be opened as a separate workspace. | No active automated cross-service handoff or authenticated delivery/webhook reconciliation. |
| Property and operations workflows | InHeir and Beacon open as dedicated workspaces when configured. | They retain separate identity, databases and policy authority. |

The intended complete journey is Rumi discovery → GreenChain sourcing →
InflationForge context → ECHO evidence decision → human approval → Gateway
transaction → merchant-authoritative order events → PROXY assistance for a
dispute. Today, those services do not yet form an end-to-end transaction. The
catalog keeps this distinction visible rather than presenting links as a live
integration.

The [pre-unification baseline](integration/PRE_UNIFICATION_BASELINE.md),
[preservation manifest](integration/PRESERVATION_MANIFEST.md),
[zero-deletion audit](integration/zero-deletion-audit.md), and
[Extension SDK v1 package README](../packages/peoplepay-extension-sdk/README.md)
provide the actionable integration entrypoints.
