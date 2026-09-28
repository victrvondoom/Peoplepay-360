# Beacon — Integration Map

> **Addendum, 2026-09-27 (later the same day).** Parts of the plan below are now
> built, and two of its assumptions changed. Read this box first.
>
> **The aggregate moved.** `beacon.peoplepay` is the canonical `Transaction`,
> not the `transaction/aggregate.py` proposed in §4. A second aggregate appeared
> during implementation with a stronger permission model (an unordered
> DISCOVERY/PLANNING/BOOKING/PAYMENT/SHARING set enforcing that "find me a
> laptop" is not "buy me a laptop"), so this layer converged onto it and deleted
> its own. `transaction/aggregate.py` is now a re-export.
>
> **B1 is confirmed and unresolved.** See `docs/licensing-blockers.md`:
> `rumi-main` and `CONSUMER-main` carry no licence at any level. Integration
> with both is therefore **service-boundary only** — no source vendored. The
> spatial adapter complies: it is Python, reads Rumi room JSON over HTTP, and
> copies no Rumi implementation.
>
> **Built and tested so far:** capability contract (`adapters/base.py`), market
> adapter (InflationForge, verified live on :8010), spatial adapter (Rumi room
> JSON), the capability bridge, the central store, the event bus, and the HTTP
> gateway with `/health/integrations`. 50 integration tests + 149 upstream.
>
> **Still open:** property (InHeir), resolution (PROXY), commerce and payment
> adapters — the last two remain `NOT_CONFIGURED` because no such code exists in
> any of the five projects (B2, B3).

**Status:** Discovery complete. No code modified.
**Date:** 2026-09-27
**Scope:** Audit of five projects found under `payment at critical situation/`, and the plan to unify them into one transaction-centric system.

> **Note (2026-09-27):** §4 (Proposed structure) and §5 (Implementation plan) below
> are **superseded by [`architecture.md`](architecture.md)**, which reframes the
> system around a single multilingual agent with Memory / Evidence / Action layers,
> and adds four pillars this audit did not assess (personal vault, cross-platform
> evidence connectors, user-to-user experience graph, transport).
> **§1–§3 and §6 of this file remain authoritative** — the per-project audit and the
> conflict register are unchanged and are referenced rather than duplicated there.

---

## 0. Executive summary — read this first

Five findings change the plan materially. They are stated up front because three of them are blockers.

| # | Finding | Severity |
|---|---|---|
| 1 | **Much of the requested transaction core already exists** in `Beacon-main/src/beacon/assurance/` — 2,752 lines, 79 passing tests. The lifecycle, evidence graph, contract/drift, mandate chain, hash-chained ledger and idempotency guard are already built, and match the brief almost clause for clause. **Build the integration layer, do not rewrite this.** | Informational, but decisive |
| 2 | **Two projects have no license.** `CONSUMER-main` and `rumi-main` carry no LICENSE file — default is "all rights reserved." §36 of the brief says stop rather than silently merge. **BLOCKER.** | Blocker |
| 3 | **Project #5 in the brief does not exist.** There is no "Agent Booking / Browser Proxy." `CONSUMER-main` is PROXY, a consumer-*dispute* system. There is no booking agent and no purchase automation anywhere in the five repos. | Blocker (scope) |
| 4 | **No payment provider exists in any repo.** Zero Stripe/Razorpay/UPI/PayPal SDKs. Payment is greenfield, not integration. | Blocker (scope) |
| 5 | **Beacon itself is not a payments orchestrator.** It is an AWS incident-remediation agent. Its *reusable asset* for this brief is the safety pattern plus the standalone `assurance` package — not its incident pipeline. | Informational, but decisive |

Two of the five projects also sit on different clouds (AWS vs Azure), four claim port 8000, four use different LLM providers, and money is represented three incompatible ways.

---

## 1. What is actually on disk

The five projects are **siblings in a container folder**, not nested inside Beacon. The container is **not a git repository**; four of the five have `.github/` but no `.git/`, so these are downloaded ZIP snapshots with no history.

```
payment at critical situation/          <- container, NOT a git repo
├── Beacon-main/            AWS incident remediation + assurance library (Python)
├── CONSUMER-main/          PROXY: consumer dispute resolution (Python + Next.js)
├── Inflation-Forge-main/   City price/inflation tracker (Python + frontend)
├── inheir.ai-main/         Property legal-dispute platform (Python/Azure + Next.js)
└── rumi-main/              Spatial furniture shopping agent (TypeScript + Swift)
```

---

## 2. Per-project audit

### 2.1 BEACON (`Beacon-main/`)

| Field | Value |
|---|---|
| **Purpose (actual)** | "Beacon Night Shift" — autonomous AWS on-call agent. Reads logs, correlates CloudTrail changes, proposes one allowlisted fix, dry-runs it, waits for voice approval, verifies recovery. Built for an AWS hackathon. |
| **Purpose (as brief assumes)** | "Autonomous secure agent execution / investigation / approval / sandbox / verification." Accurate as a *pattern*; the domain is cloud incidents, not commerce. |
| **Language / runtime** | Python **≥3.12** |
| **Package manager** | `uv` (+ `uv.lock`), npm for `web/` |
| **Entrypoints** | 5 AWS Lambdas: `triage.py`, `voice_turn.py`, `remediate.py`, `changes.py`, `dashboard_api.py`. Local: `scripts/local_server.py` on **:8000** |
| **Frontend** | `web/` — React **18.3** + Vite **5.4** |
| **Database** | DynamoDB (incidents, approvals, contracts w/ TTL, change ledger, idempotency) |
| **LLM** | AWS Bedrock — Nova 2 Lite + Nova Multimodal Embeddings; **Strands Agents SDK** |
| **HTTP layer** | AWS Lambda Powertools resolver — `@app.get("/incidents/<id>")`, **not** FastAPI |
| **API** | `/health`, `/incidents`, `/tally`, `/analytics`, `/audit`, `/contracts`, `/safety`, `/report/latest`, `POST /session`, `POST /turn` |
| **Agents** | One Strands voice agent, 7 tools (`voice_tools.py`) |
| **Security model** | **Strongest in the repo set.** Code allowlist (3 actions only), data allowlist (golden snapshot), dry-run under the executing role, consent checked against the *raw user transcript* not the model's claim, atomic single-execute, two IAM roles one direction, tag-scoped writes, verification requiring 3 independent conditions, scoped+expiring "Sleep Contracts", global kill switch (`APPLY_ENABLED=false`). `tests/test_template_safety.py` parses real CloudFormation and fails if IAM widens. |
| **Config** | 17 env vars, **all unprefixed** (`APPLY_ENABLED`, `TOKEN_BUDGET`, `SNS_TOPIC_ARN`) — collision-prone |
| **Tests** | 42 files, incl. `test_assurance_core.py` — **79/79 pass, 0.19s** (verified) |
| **Deployment** | 3 CloudFormation/SAM templates, 2 Dockerfiles, Makefile |
| **License** | **Apache-2.0** |

#### The critical asset: `src/beacon/assurance/`

A **self-contained, fully tested transaction assurance library, imported by nothing but its own tests.** It is a library waiting for an orchestrator — exactly the seam this integration needs.

| Module | Lines | Contents |
|---|---|---|
| `states.py` | 284 | **33-state lifecycle** + `TRANSITIONS` table, `EXCEPTION_STATES`, `TERMINAL_STATES`, `IRREVERSIBLE_AFTER`, `assert_transition` |
| `contract.py` | 642 | `TransactionContract` + 11-way drift `check`, `Authorization`, `CheckoutMandate`, `PaymentMandate`, `ViolationKind` |
| `policy.py` | 743 | `PolicyEngine`, `IntentMandate`, `AutonomyLevel`, `Decision`/`Reason` |
| `evidence.py` | 450 | `EvidenceGraph` (append-only), `EvidenceNode`/`EdgeKind`, `Provenance`, `EvidenceClass`, `content_hash` |
| `ledger.py` | 335 | `TransactionLedger` (hash-chained), `IdempotencyGuard`, `EventKind` |
| `money.py` | 172 | `Money` — integer minor units, **floats rejected at construction** |

**How closely it already satisfies the brief:**

| Brief section | Already implemented |
|---|---|
| §5 Universal transaction schema | Partially — all the *parts* exist; no single `Transaction` aggregate object |
| §6 Universal lifecycle | **Yes, fully.** 33 states incl. the whole failure path |
| §12 Price decision engine | `PolicyEngine` + `Decision.explain()` — evidence-based, no "AI says so" |
| §18 Transaction contract | **Yes, fully**, incl. expiry + re-evaluation on change |
| §23 Evidence graph | **Yes** — typed nodes/edges, append-only, hashed, provenance |
| §24 No fake integration | **Yes** — `SANDBOX` evidence class cannot launder itself into `VERIFIED` |
| §32 Failure handling | **Yes** — every failure is a declared state |
| §44 Demo: price changed → blocked | **Yes** — `ViolationKind` + `_RE_AUTHORIZABLE` |

**What is missing:** a `Transaction` aggregate, persistence, an orchestrator, subsystem adapters, and spatial/property node kinds in the evidence graph.

---

### 2.2 RUMI (`rumi-main/`)

| Field | Value |
|---|---|
| **Purpose** | AI interior shopping agent — room scan → 3D editable workspace → real furniture search → budget-constrained plan. HackMIT 2026. |
| **Brief's assumption** | Accurate. This is the one project the brief describes correctly. |
| **Language** | TypeScript (strict) + **Swift** (iOS RoomPlan) |
| **Package manager** | **Bun** (`bun.lock`) |
| **Entrypoints** | `index.html` → `src/main.tsx` (Vite, **:5173**); `convex/` serverless; `ios/RumiCapture.xcodeproj` |
| **Frontend** | React **19.3**, Vite **8.3**, Three.js + R3F/Drei, Tailwind 4, Zustand |
| **Database** | **Convex** (serverless) — 22 modules. Scans/history stay browser-local |
| **LLM** | `@ai-sdk/openai` + Vercel AI SDK; **Exa** for product search |
| **Auth** | **Clerk** |
| **Agents** | Design agent + Search agent (`convex/agent.ts`, `search.ts`, `planner.ts`) |
| **Security model** | **"The model proposes; code checks."** Zod contracts validate every proposal against budget, dimensions, doorway clearance, room revision. |
| **Config** | 4 env vars (`VITE_CONVEX_URL`, `VITE_CLERK_PUBLISHABLE_KEY`, `VITE_CAPTURE_PAIRING_ENABLED`) |
| **Tests** | 44 files, `bun test` |
| **License** | **NONE — blocker** |

**Capabilities to preserve (§7):** iOS RoomPlan capture, QR/browser pairing (`shared/capture/pairing.ts`), room reconstruction (`shared/reconstruction/*`), spatial planning (`shared/planner/{budget,free-floor,space,zones,limit,scope}.ts`), placement validation (`shared/geometry` — `placementIssue`, `findPlacement`), product search pipeline (`shared/search/*` — 11 modules incl. `retailers`, `shopify`, `jsonld`, `dimensions`, `rank`), parametric asset generation.

**Integration-relevant detail:** Rumi's `measurementSchema` already grades evidence — `confirmed | estimated | unknown`, with an `evidence.kind` of `structured | spec-text | image | mixed | none`, and a Zod refinement forbidding a dimension value when the source is `unknown`. That is **the same discipline as Beacon's `EvidenceClass`**, independently invented. Mapping is natural, not forced.

Prices are `priceCents` integers → maps cleanly to Beacon's `Money`. **But** `formatMoney` hardcodes `currency: "USD"`, while the brief's scenarios are all INR. Currency is a display-layer conflict to resolve.

---

### 2.3 INFLATIONFORGE (`Inflation-Forge-main/`)

| Field | Value |
|---|---|
| **Purpose (actual)** | Map-first **city-level inflation tracker** and "software factory for price intelligence." Compares this year vs last year for the same everyday item in the same US city, keeping source receipts. |
| **Brief's assumption** | **Partially wrong.** The brief expects retail/SKU price intelligence for products like headphones or an iPhone. InflationForge tracks a **9-item city basket** (rent, milk, eggs, bread, chicken, gas, transit, coffee, apples) across **US cities in USD**. It has no product catalog, no SKU concept, no merchant concept, and no INR. |
| **Language** | Python **≥3.11** (lowest of the three Python projects) |
| **Entrypoint** | `backend/main.py` (FastAPI), **:8000** |
| **Database** | **SQLite** (`sqlite3`, direct — no ORM) |
| **External services** | **Bright Data** SERP API (discovery), **Internet Archive Wayback** (history), **SigNoz** (OTLP observability), **Port** (catalog/control plane), OpenStreetMap + Leaflet |
| **Security model** | Evidence-first: "no generated prices or mocked comparisons in the product path. Missing evidence produces missing data or an explicitly named fallback — not a plausible-looking number." |
| **Config** | 25 env vars |
| **Tests** | 7 files |
| **License** | **MIT** |

**What genuinely transfers (and it is valuable):**
- `PriceObservation` — carries `source`, `source_url`, `raw_label`, `raw_price`, `conversion_multiplier`, `observed_at`, `retrieved_at`, `archive_timestamp`, `kind: LIVE|ARCHIVED`. **This is exactly the provenance record §11 demands.**
- `ObservationKind.LIVE|ARCHIVED` → maps to `EvidenceClass.VERIFIED|STALE`.
- `ModeStatus` (`price_provider`, `history_provider`, `telemetry`, `port`, `database`, `map_data`) → **already the `/health/integrations` LIVE/SANDBOX/UNAVAILABLE distinction of §25.**
- The "capability factory" pattern (validate → version → `spec_hash` → collect → catalog, with *soft* retirement preserving history) is a strong model for adding new evidence providers.

**Hard conflict:** `price_usd: float`, `raw_price: float`, `change_pct: float`. **InflationForge represents money as floats. Beacon's `Money` rejects floats at construction** — deliberately, because precision is already lost by then. An adapter must convert at the boundary and cannot pretend the float was exact.

---

### 2.4 INHEIR.AI (`inheir.ai-main/`)

| Field | Value |
|---|---|
| **Purpose (actual)** | Legal-tech platform for **property dispute management** for legal professionals and vulnerable communities. Case creation, document summarization, GIS analysis, legal knowledge base RAG, crowdsourced property risk reporting. 1st Prize, Microsoft Innovation Challenge June 2025. |
| **Brief's assumption** | Mostly accurate on capabilities (property/document/geo/risk), but the framing differs: it is about **disputes and inheritance rights**, not purchase due-diligence. It has no valuation engine and no seller/counterparty verification. |
| **Language** | Python **≥3.13** (highest — conflicts with Beacon's 3.12) |
| **Cloud** | **AZURE** — the only non-AWS backend |
| **Entrypoint** | `backend/src/inheir_backend/server.py` (FastAPI), **:8000**; frontend **:3000** |
| **Frontend** | **Next.js 15.3** + React 19.2, Biome, Bun |
| **Database** | **MongoDB** via `motor` (async) |
| **LLM** | **Azure OpenAI** + LangChain (`langchain-openai`, `langchain-community`) |
| **Azure services** | `azure-ai-formrecognizer` (documents), `azure-search-documents` (RAG), `azure-storage-blob`, `azure-ai-textanalytics`, `azure-cognitiveservices-speech`, `azure-ai-evaluation`, `azure-identity` |
| **Geo** | `geopandas`, `geopy` |
| **Serverless** | 2 **Azure Functions**: `ChatBotFunction`, `DeleteOldEntries` |
| **Auth** | PyJWT + bcrypt, custom middleware |
| **API** | Routers: `auth`, `case`, `chatbot`, `gis`, `report`, under `/api/v1` |
| **Security model** | Privacy-first — PII handling for sensitive legal data, responsible-AI practices, TLS via nginx + local certs |
| **Config** | 33 backend env vars, 1 frontend |
| **Tests** | **0** — `backend/tests/` contains only `__init__.py`. **No test coverage at all.** |
| **License** | **MIT** (3 copies: root, backend, frontend) |

**Reusable for §14/§21:** document understanding (Form Recognizer), GIS/location intelligence, property risk reporting, legal knowledge-base RAG.

---

### 2.5 CONSUMER / PROXY (`CONSUMER-main/`) — not the project the brief expected

| Field | Value |
|---|---|
| **Purpose (actual)** | **PROXY — "Agentic Autonomous AI for Consumer Justice."** Five autonomous agents that research regulation, extract evidence from uploaded documents, build a strategy, draft appeal/complaint/regulator letters, review their own output for hallucinations and self-correct. 8 dispute domains: airlines, banking, e-commerce, government, healthcare, health insurance, housing, telecom. |
| **Brief's assumption** | **Wrong.** The brief expects "AGENT BOOKING / BROWSER PROXY — secure browser-based agent execution for searching, booking, purchasing." PROXY does **not** book, purchase, or transact. The name collision ("Proxy" / "browser proxy") appears to be the source of the confusion. |
| **Language** | Python 3.12 (backend), TypeScript (frontend) |
| **Entrypoint** | `backend/app/main.py` (FastAPI), **:8000**; frontend **:3000** |
| **Frontend** | **Next.js 15.4** + React 19 — 3D knowledge graph, document vault |
| **Databases** | **Qdrant** (vector, :6333/:6334), **Neo4j** (knowledge graph, :7687/:7474), **Redis** (:6379), **Supabase/Postgres** (:5432) |
| **LLM** | **Google Gemini** (`google-generativeai`) + **LangGraph 1.0** + LangChain |
| **Agents** | **Its own supervisor/orchestrator** — `agents/orchestrator/{supervisor,case_workflow,multi_domain_workflow,case_analysis_workflow,specialist_dispatch}.py`, plus research / evidence / strategy / negotiation / review / graph / final_report agents and 8 domain specialist packages |
| **Browser automation** | **`playwright==1.49.1`** — `playwright_document_fetcher.py`, `insurer_document_collector.py`. Fetches insurer policy PDFs. Notably already takes an **`allowed_domains` allowlist** and a `max_links` cap. |
| **Security model** | Deterministic citation verification; a Review agent gates output and forces retry on hallucination; unverified citations flagged inline |
| **API** | `/health`, `/health/live`, component health router, domain routes |
| **Config** | **58 env vars** — the largest surface |
| **Tests** | 10 files |
| **License** | **NONE — blocker** |
| **Deployment** | Docker, docker-compose, **k8s/** manifests |

**The reframe worth making:** PROXY is a poor fit for §15/§20 (booking/purchase) but an *excellent* fit for the part of the lifecycle most systems skip — §32 failure handling, §45 delivery failure, and the `DISPUTE_REQUIRED → RESOLUTION_PENDING → RESOLVED` path that Beacon's `states.py` already declares but nothing implements. PROXY is a ready-made **Resolution Engine**. Its Playwright layer plus domain allowlist is also the most honest available seed for §15's controlled execution engine.

**Conflict with §28:** PROXY has its own LangGraph supervisor. The brief forbids each project running its own uncontrolled autonomous agent. PROXY's orchestrator must become a *capability invoked by* the Beacon orchestrator, scoped to one transaction — not a peer.

---

## 3. Conflict register (§48 — documented, not "fixed until it works")

### 3.1 Blockers — stop and decide

| ID | Conflict | Detail | Why it blocks |
|---|---|---|---|
| **B1** | **No license on 2 of 5 projects** | `CONSUMER-main`, `rumi-main` have no LICENSE. Default: all rights reserved. Beacon is Apache-2.0; InflationForge and InHeir are MIT. | §36: "If projects have incompatible licenses: STOP. Do not silently merge incompatible licensed code." Unlicensed code cannot be legally redistributed or combined. **Needs the owners to add a license.** |
| **B2** | **No booking/purchase agent exists** | Nothing in any repo books, reserves, or purchases. PROXY is a dispute system. | §15, §20, §43 assume this project exists. It must be **built from scratch** or the scope must change. |
| **B3** | **No payment provider anywhere** | Zero payment SDKs. Beacon's assurance layer deliberately stops at the mandate and states "What is deliberately not here: a payment network." | §19 says "do NOT build a fake payment system." So payment is new work against a real sandbox (e.g. Stripe/Razorpay test mode), not integration. |

### 3.2 Hard technical conflicts

| ID | Conflict | Detail | Smallest safe boundary |
|---|---|---|---|
| **C1** | **Money representation, 3 ways** | Beacon: integer minor units, floats **rejected**. Rumi: `priceCents` integer. InflationForge: `price_usd` **float**. | Beacon `Money` is canonical. Adapter converts at the edge and marks float-derived values as non-exact. **Never** relax `Money`. |
| **C2** | **Two clouds** | Beacon = AWS (Lambda/DynamoDB/Bedrock). InHeir = Azure (Functions/Cosmos/Azure OpenAI/Form Recognizer). | Keep both. Cross-cloud **HTTP service boundary**. Do not port either. |
| **C3** | **Python 3.11 / 3.12 / 3.13** | InflationForge ≥3.11, Beacon ≥3.12, InHeir ≥3.13. Beacon uses `StrEnum` (3.11+). | Separate venvs per service; **no shared Python process**. Contract is HTTP + JSON schema. |
| **C4** | **Port 8000 claimed 4×; port 3000 claimed 3×** | Beacon, PROXY, InflationForge, InHeir all default to :8000. PROXY, InHeir + others to :3000. | Central port allocation table (§below). Override via env only; no source edits. |
| **C5** | **4 LLM providers** | Bedrock/Nova (Beacon), Gemini (PROXY), Azure OpenAI (InHeir), OpenAI (Rumi). | Leave each. The orchestrator does not unify models; it unifies *authority*. No model is in any money path. |
| **C6** | **5 databases + 1 more** | DynamoDB, Convex, SQLite, MongoDB, Qdrant+Neo4j+Redis+Postgres. | §38: adapters, no migration. Central store owns `transactions`/`events`/`contracts`/`authorizations`/`evidence`; subsystems keep their own. |
| **C7** | **2 agent orchestrators** | Beacon Strands agent + PROXY LangGraph supervisor. | §28: Beacon orchestrates; PROXY's supervisor becomes a scoped capability. |
| **C8** | **React 18 vs 19; Vite 5 vs 8; Next 15 ×2** | Beacon web React 18.3/Vite 5.4; Rumi React 19.3/Vite 8.3; PROXY Next 15.4; InHeir Next 15.3. | Do **not** merge frontends into one bundle. Separate builds behind one shell/gateway. |
| **C9** | **3 package managers** | uv (Python), Bun (Rumi, InHeir fe), npm (Beacon web). | Keep per-project. One task runner (Make) delegating out. |
| **C10** | **HTTP frameworks differ** | Beacon = Lambda Powertools (`<param>`); others = FastAPI (`{param}`). | Gateway normalizes. Do not rewrite Beacon's handlers. |
| **C11** | **Currency: USD vs INR** | InflationForge is USD-only + US cities. Rumi formats USD. Brief's scenarios are INR. | `Money` already carries ISO-4217 and refuses cross-currency arithmetic. No FX invention; unavailable conversion = `UNAVAILABLE`. |

### 3.3 Domain-scope gaps (capability does not exist yet)

| Gap | Brief section | Reality |
|---|---|---|
| Product/SKU price intelligence | §10, §11, §41 | InflationForge does city baskets, not SKUs. Rumi's `shared/search/*` is the closer fit. |
| Merchant verification | §10, §12, §43 | Exists nowhere. `NodeKind.MERCHANT_EVIDENCE` is declared in Beacon but unpopulated. |
| Camera classification / ScanRouter | §9, §22, §29 | Exists nowhere. Rumi captures *rooms* only; no receipt/price-tag/QR/bill classifier. |
| Property valuation | §21, §42 | InHeir does disputes/risk/GIS, not valuation. |
| Historical INR product prices | §10, §41 | Not available. Per §11 → must report `UNKNOWN`, never fabricate. |
| MCP tool layer | §27 | No MCP server anywhere. Greenfield. |
| Spatial/property evidence nodes | §8, §23 | `NodeKind` has no ROOM/SPATIAL/PROPERTY/DOCUMENT members. Additive change needed. |

---

## 4. Proposed structure

Beacon is the orchestrator; everything else is a capability it invokes. Preserve each project runnable standalone (§4).

```
payment at critical situation/          <- git init here
├── docs/
│   └── integration-map.md              <- this file
│
├── beacon-core/                        (= Beacon-main, Apache-2.0)
│   └── src/beacon/assurance/           THE transaction core. Extend, never fork.
│
├── transaction/                        NEW — the only new "engine"
│   ├── aggregate.py                    Transaction object (the one missing piece)
│   ├── orchestrator.py                 §28 — decides which capability is needed
│   ├── store.py                        transactions/events/contracts/authorizations/evidence
│   ├── eventbus.py                     §26 — every event carries transaction_id
│   └── scan_router.py                  §22 — camera frame -> capability
│
├── adapters/                           NEW — thin, honest, health-reporting
│   ├── spatial/        -> rumi-main        (HTTP/Convex)
│   ├── market/         -> Inflation-Forge  (HTTP; float->Money at the edge)
│   ├── property/       -> inheir.ai-main   (HTTP, cross-cloud to Azure)
│   ├── resolution/     -> CONSUMER-main    (HTTP; dispute/refund path)
│   ├── commerce/       -> NOT BUILT (B2)   explicit NOT_CONFIGURED
│   └── payment/        -> NOT BUILT (B3)   explicit SANDBOX/NOT_CONFIGURED
│
├── gateway/                            NEW — one surface, /health/integrations
│
└── modules/                            originals, untouched, standalone-runnable
    ├── rumi-main/  Inflation-Forge-main/  inheir.ai-main/  CONSUMER-main/
```

### Port allocation (resolves C4)

| Service | Port |
|---|---|
| Gateway / unified UI | 8080 |
| Beacon core | 8000 |
| Spatial (Rumi web) | 5173 |
| Market (InflationForge) | 8010 |
| Property (InHeir) | 8020 |
| Resolution (PROXY) | 8030 |
| Existing infra (Qdrant 6333, Neo4j 7687, Redis 6379, Postgres 5432, Mongo 27017) | unchanged |

### Capability mapping (honest version)

| Brief's intent | Real source | Confidence |
|---|---|---|
| Spatial intelligence | Rumi | **Direct** |
| Security / approval / verification | Beacon core + assurance | **Direct** |
| Transaction state / evidence | `beacon.assurance` | **Direct** |
| Price *evidence* discipline & provenance | InflationForge | **Pattern + provenance model** |
| Product discovery & price | **Rumi `shared/search/*`**, not InflationForge | Partial |
| Property intelligence | InHeir | Partial (disputes/GIS, not valuation) |
| Commerce / booking execution | **nothing** | **Missing (B2)** |
| Payment | **nothing** | **Missing (B3)** |
| Dispute / refund / resolution | **PROXY** | **Direct — stronger than the brief assumed** |

---

## 5. Revised implementation plan

The brief's §47 assumed integration. Three of its steps are actually greenfield. Ordered so blockers surface before work depends on them.

| Step | Work | Depends on |
|---|---|---|
| 0 | **Resolve B1** — get licenses for `rumi-main`, `CONSUMER-main` | User/owners |
| 1 | `git init` the container; commit all five as-is as the baseline | — |
| 2 | Establish test baseline: run all five suites, record pass/fail | — |
| 3 | `Transaction` aggregate + store + event bus **on top of `beacon.assurance`** | 1 |
| 4 | Extend `NodeKind`/`EdgeKind` with SPATIAL/PROPERTY/DOCUMENT (additive) | 3 |
| 5 | Beacon orchestrator + `/health/integrations` with LIVE/SANDBOX/NOT_CONFIGURED | 3 |
| 6 | Rumi adapter — RoomContext → transaction context (§8) | 3,4 |
| 7 | Market adapter — provenance + float→`Money` boundary; `UNKNOWN` when absent | 3 |
| 8 | Property adapter — cross-cloud HTTP to Azure | 3,4 |
| 9 | Resolution adapter — PROXY on the dispute/refund path (§45) | 3 |
| 10 | **Build** commerce/booking agent, sandboxed, scoped token (B2, §15/§16) | 5 |
| 11 | **Build** payment adapter against a real provider sandbox (B3, §19) | 5,10 |
| 12 | ScanRouter + Beacon Lens (§22/§29) | 5 |
| 13 | MCP tool layer (§27) | 5 |
| 14 | Unified UI — one transaction workspace + timeline (§34/§35) | 5 |
| 15 | Cross-system integration test: Rumi → discovery → evidence → contract → approval → sandbox payment → verification (§39) | all |

---

## 6. Principles carried forward

All five projects independently converged on the same discipline — which is why this integration is viable at all:

| Project | Its own words |
|---|---|
| Beacon | "An LLM may *recommend* a transition, it may never perform one." |
| Rumi | "The model proposes; code checks." |
| InflationForge | "No generated prices... Missing evidence produces missing data, not a plausible-looking number." |
| PROXY | A Review agent gates output; unverified citations are flagged, not smoothed over. |
| InHeir | Responses backed by established legal procedure; privacy-first. |

Unified rule for the integrated system: **the model proposes, code checks, evidence decides, the user authorizes, and no gap is ever filled with a guess.**

---

## 7. Open questions for the user

1. **Licensing (B1)** — can licenses be added to `rumi-main` and `CONSUMER-main`? Nothing distributable can proceed without this.
2. **Booking agent (B2)** — build one from scratch, or drop §15/§20/§43 from scope?
3. **Payment (B3)** — which provider sandbox? (Razorpay/UPI suits the INR scenarios; Stripe is easiest to test.)
4. **PROXY's role** — accept the reframe from "booking" to "resolution engine"?
5. **Currency** — target INR? Then InflationForge's USD city data is background evidence only, not transaction price evidence.
6. **InHeir tests** — it has zero. Add coverage before wiring it into a money path?
