# Bundled project intake for the ECHO extension platform

Inspected: 2026-10-05. Scope: the four existing bundled projects and the root
capability adapters. This is a code inspection; no application was modified,
deployed, installed, or contacted by this intake.

The extension brief contains example repository placeholders, but no new
external repository URLs. This dossier therefore covers the projects actually
present. It does not claim a new upstream clone, current upstream maintenance,
an upstream commit match, a vulnerability scan, or permission to redistribute
any unlicensed source. README links are author assertions, not verified clone
provenance.

## Snapshot identity and provenance

The enclosing checkout has remote
`https://github.com/victrvondoom/Peoplepay-360.git` and inspected HEAD
`b6f5e3ef25160a45f68be275430a0c29f9d4b3c6`. These folders are ordinary Git
trees in that checkout, not submodules; no nested `.git` directory was found.
The commit below is the latest **PeoplePay commit touching the folder**, not
an asserted upstream revision. ECHO and the product directory have additional
uncommitted workspace changes.

| Folder | Git tree at inspected HEAD | Last PeoplePay commit touching folder | Local provenance limitations |
|---|---|---|---|
| `GREENCHAIN-main` | `a231cf504a08e4efebbfc3b9e3d5025049c72114` | `b6f5e3ef25160a45f68be275430a0c29f9d4b3c6`, 2026-10-05 | Added as bundled files. No upstream URL or upstream commit established by this intake. |
| `Inflation-Forge-main` | `e563d5acf09f89a76fbc65aa9451fc0d3cf10762` | `8d28c49beed8c093cf6cdd5d3ac46e96fe1f93af`, 2026-10-02 | README links `KaushikSiva/Inflation-Forge`; local changes and tree identity do not establish upstream parity. |
| `CONSUMER-main` | `5406fc4b91469f2b221897191416f775de2f35a7` | `8d28c49beed8c093cf6cdd5d3ac46e96fe1f93af`, 2026-10-02 | README links `rakeshselvaraj0108/Proxy`; recovered corpus provenance is recorded separately in the existing review. |
| `rumi-main` | `848dbf65af6f9d0db7c0866ac1098ac6465c8152` | `8d28c49beed8c093cf6cdd5d3ac46e96fe1f93af`, 2026-10-02 | README credits a team and a hackathon submission. No upstream URL or upstream commit established here. |

Upstream activity and dependency publication age are **UNKNOWN**. Local
commit dates reflect changes to this combined checkout. Before accepting a
new upstream version, record its requested URL, resolved full commit,
license texts, lockfile, package/model hashes, and the inspected diff.

## Decisions, fit, duplication, and risk

`INTEGRATE` means a narrow independently written interface adapter; it does
not mean merge another application's core. `DEFER` preserves the existing
application and records the activation blockers. The ECHO core must validate
every result and own canonical IDs, graph writes, dependency links, scores,
decisions, approval, and transaction lineage.

| Project | Actual contribution | Primary category | Integration mode | Decision | Overlap with ECHO | Security classification |
|---|---|---|---|---|---|---|
| InflationForge | Sourced city/item USD observations, dates, archive receipts, price normalization, snapshot identity | `PRICE_INTELLIGENCE` | HTTP service adapter, read-only endpoints | **INTEGRATE** scoped observation ingestion; separate runtime; no copied source required | MEDIUM: existing `adapters/market.py` already fronts the service; ECHO adds graph ingestion | MODERATE for configured read-only use; unauthenticated mutation endpoints must remain outside the ECHO contract |
| GreenChain | Candidate supplier discovery and environmental model estimates | `SUSTAINABILITY_INTELLIGENCE` | HTTP service adapter | **DEFER activation** pending license confirmation and provenance completion; an independent adapter contract can be registered disabled | MEDIUM: discovery and ranking duplicate decision authority if accepted wholesale | HIGH for live discovery without egress controls; arbitrary HTTP fetch, permissive CORS, no route auth observed, model-loading trust boundary |
| PROXY / CONSUMER | Case-scoped research, evidence extraction, draft strategy/appeal, source citations | `DISPUTE_ASSISTANCE` | Authenticated HTTP service adapter | **DEFER activation** pending license and identity contract; retain a draft-only handoff design | HIGH for orchestration, memory, own graph and case workflow; useful narrow dispute capability | HIGH for production activation without verified identity/data boundaries; development bearer bypass and sensitive document/provider processing |
| Rumi | Merchant furniture discovery, measured/estimated dimensions, room revision, budget and placement constraints | `SUPPLIER_DISCOVERY` | Owner-operated service adapter to be designed; current search is internal Convex API | **DEFER activation** pending license and a supported external API | MEDIUM for discovery/ranking; LOW for room geometry | HIGH for activation before a constrained service API; broad URL fetch and hosted service identity/state boundaries |

The classification is based on reachable code boundaries, not verified CVEs.
No package audit, binary scan, or dependency advisory lookup was run. None of
the entries is a production security certification.

### Value scores

Scores are engineering estimates from the inspected snapshot, 0–10, where 10
is stronger fit or confidence. They do not imply statistical measurement.
Low maintenance scores reflect absent upstream verification; low license
scores reflect missing authorization evidence.

| Dimension | GreenChain | InflationForge | PROXY | Rumi |
|---|---:|---:|---:|---:|
| Capability uniqueness | 8 | 7 | 8 | 8 |
| ECHO relevance | 9 | 7 | 8 | 6 |
| Technical depth | 7 | 7 | 8 | 8 |
| Graph relevance | 7 | 8 | 8 | 6 |
| Demo value | 9 | 7 | 7 | 8 |
| Reliability confidence | 4 | 7 | 6 | 7 |
| Integration feasibility | 7 | 8 | 5 | 3 |
| Maintenance confidence | 3 | 4 | 4 | 4 |
| Security confidence | 3 | 5 | 4 | 4 |
| License confidence | 2 | 9 | 0 | 0 |

## License and supply-chain gate

This inventory describes the files found, not a legal compatibility opinion.
Application code, dependencies, datasets, models, images, and scraped content
need separate authorization records.

| Project | License evidence | SPDX status | Notice/redistribution implications | Separate data/model gate |
|---|---|---|---|---|
| InflationForge | [LICENSE](../../../Inflation-Forge-main/LICENSE), MIT, copyright Kaushik Sivakumar 2026 | `MIT` observed for application source | Preserve the copyright and permission notice with copied/substantial redistributed software. No separate application `NOTICE` observed. The file includes no express patent grant or network-use condition. | MIT application source does not establish rights to redistribute Numbeo data, Internet Archive captures, map tiles, or third-party HTML. Store receipts and permitted excerpts; record publisher terms before republishing datasets. |
| GreenChain | [README license statement](../../../GREENCHAIN-main/greenchain/README.md) says MIT, but its referenced LICENSE is absent | `LICENSE_UNKNOWN`; README assertion is unresolved evidence | Do not vendor more source or claim terms resolved. Record owner confirmation and actual license text before activation/distribution decisions. No app-level NOTICE established. | XGBoost files, generated/real training data, USEEIO/Ember/ND-GAIN/GLEC reference data, images and charts need independent source/version/license records. |
| PROXY | No application LICENSE/LICENCE found outside dependency directories | `LICENSE_UNKNOWN` | No copying or implicit permission claim. Existing HTTP adapter is independent code; that does not grant rights to redistribute the bundled server. | Indexed regulatory corpora, embeddings and uploaded personal documents have separate provenance, retention and redistribution concerns. Corpus recovery hashes do not establish current legal accuracy. |
| Rumi | No application LICENSE/LICENCE found outside dependency directories; `package.json` is private and has no license field | `LICENSE_UNKNOWN` | No copying of TypeScript/Swift/geometry/search source. A hosted-service API contract needs operator authorization and terms. | Merchant photos/models, product HTML, scans and generated previews are not covered by an absent application license. Keep synthetic assets explicit. |

Dependency directories contain their own license/NOTICE files; these are not
application licenses. See the existing [licensing blockers](../../licensing-blockers.md)
for the previous independent-adapter review.

## GreenChain dossier

### Purpose, runtime, and state

The actual backend is a Python FastAPI application at
[backend/main.py](../../../GREENCHAIN-main/greenchain/backend/main.py), with a
separate Next/React frontend. It asks Dedalus-backed agents to discover
manufacturers, enriches their records, predicts manufacturing emissions with
XGBoost quantile models, calculates transport emissions, and ranks a weighted
environmental comparison. It does not provide supplier quotes, verified
carbon certificates, purchases, or ECHO correlation analysis.

The runtime uses FastAPI/Pydantic, Dedalus, Anthropic, httpx/BeautifulSoup,
NumPy/pandas/scikit-learn/XGBoost/joblib. `dedalus-labs` is unpinned and
Anthropic has a lower-bound range; many other backend requirements are
exact-pinned. No GPU requirement was established. The actual runtime SQLite
tables are discovery cache, search audit, scenario edit history, and dataset
intakes. Environmental reference values come from the ML layer; the legacy
SQLite lookup tables are not its authoritative runtime values. See
[db.py](../../../GREENCHAIN-main/greenchain/backend/db.py).

Live discovery needs `DEDALUS_API_KEY`, `ANTHROPIC_API_KEY`, and
`BRAVE_API_KEY`; scenario report generation needs Gemini configuration.
Optional OpenCorporates lookup uses `OPENCORPORATES_API_KEY`. Observed egress
includes Brave Search, Dedalus/Dedalus Cloud Services, provider-mediated
Anthropic calls, Gemini reports, `api.opencorporates.com`, `rdap.org`, and
agent-selected manufacturer URLs. Optional Dedalus machine provisioning can
create/destroy external compute, and its fetch path falls back to local httpx.

### Real contract boundary

| Call | Input | Output | Appropriate ECHO use |
|---|---|---|---|
| `GET /health` | None | `{status: "ok"}` | Liveness only; it does not prove model/provider readiness. |
| `POST /search` | `product`, positive integer `quantity`, `destination`, optional `countries`, `transport_mode`, required cert filters, target count, weights, components, use-cache flag | `product`, destination, mode, countries, duration, count, `results`, `cache_hits`, `fallback_components` | Candidate facts and environmental estimates, after core validation. |
| `POST /search/stream` | Same request | SSE `started`, `heartbeat`, `component`, `complete`, `error` | Progress only; import after complete validated response. |
| `POST /score` | `manufacturers[]`, mode, optional weights | `{count, results: [...]}` | Analysis of ECHO-supplied candidates; provider ranks remain extension output. |
| `POST /rescore-transport` | `manufacturers[]`, `mode` | `{count, mode, results: [...]}` | A scenario estimate with explicit mode and assumptions. |

Minimal actual request shape:

```json
{
  "product": "office chairs",
  "quantity": 300,
  "destination": "US",
  "countries": ["VN", "MX"],
  "transport_mode": "sea",
  "use_cache": true
}
```

Result records are dynamically shaped dictionaries. Code emits `name`,
`country`, optional `city`, `sustainability_url`, certifications,
`disclosure_status`, `industry`, `emission_factor`, `transport`,
`verification`, rank, `composite_score`, `scores`, `rank_scores`, and
sometimes `scoring_inputs`. Preserve model intervals and units rather than
flattening everything into a "confidence" number.

### Provenance and graph fit

The result normally does **not** supply an immutable source snapshot,
per-source observed timestamp/hash/excerpt, or derivation/citation edges.
An ECHO adapter should store the response hash and its receipt time, retain
the supplier's cited URL as a lead, and report missing provenance. A hash of
the result is not a hash of the publisher page. Extra URLs or agent calls
cannot establish independent roots.

The `source_count()` function in
[verification.py](../../../GREENCHAIN-main/greenchain/backend/verification.py)
counts a sustainability URL as one and the agent's `disclosure_status ==
"verified"` as another. It is not a count of fetched domains or independent
evidence. Its registry lookup accepts any returned company record, not a
confirmed identity match. Neither signal may become ECHO `VERIFIED` truth.

Graph candidates are `Entity`/supplier, environment `Claim`, an
`ExtensionRun` and generated `Evidence` tied to a response artifact. The
original publisher source must remain unresolved/unverified until ECHO has
an actual excerpt/snapshot and dependency record. Model estimates must be
marked estimated; supplier certification mentions remain unverified leads.

### Failure and security findings

Missing component-search credentials can trigger offline alternatives;
these are named synthetic manufacturers and appear in `fallback_components`.
The adapter must classify the whole relevant component as synthetic and
prevent it supporting a live approval. The scoring path has defaults for
missing revenue/renewable/weight values; assumptions must be carried into
the evidence rather than presented as measured data.

`fetch_url()` allows HTTP(S) URLs, follows redirects and does not visibly
block private/link-local targets. Input URL validation is not an SSRF control.
No authentication dependency was observed on the principal search/score
routes; CORS permits all origins. Native `.ubj` model loading is preferred,
but missing files fall back to joblib deserialization, which requires trusted
model artifacts. Run the service separately with constrained network and
artifact access; no privileged core/graph credentials belong in it.

Tests exist for scoring/search, scenario editing, and report generation.
This intake did not rerun them or install XGBoost/Dedalus. Provider reachability
and output provenance remain unverified by this dossier.

## InflationForge dossier

### Purpose, runtime, and state

The Python FastAPI service at
[backend/main.py](../../../Inflation-Forge-main/backend/main.py) compares
sourced current and previous-year city price observations. It serves a static
map UI, a governed item factory, SQLite evidence and sync jobs, OpenTelemetry,
and optional Port catalog writes. It is a US city cost-of-living basket in USD,
not a merchant SKU quote engine or a supplier purchase price source.

Dependencies include FastAPI/Pydantic, httpx, python-dotenv and OpenTelemetry;
requirements mix exact pins with bounded ranges. SQLite stores snapshots,
observations, tracked capabilities, factory events, jobs and state. Artifact
files retain telemetry and local Port fallback events. No GPU or browser
automation requirement was established for the backend collector.

Observed network destinations are `www.numbeo.com`, `web.archive.org`,
`r.jina.ai` fallback, Bright Data/Google SERP discovery, configurable Port API,
and configurable OTLP collector. The frontend requests OpenStreetMap tiles.
`BRIGHT_DATA_API_TOKEN`, Port credentials and telemetry endpoint are optional
configured services; live/archived collection still needs publisher access.

### Real read-only adapter contract

| Call | Output | ECHO handling |
|---|---|---|
| `GET /health` | Status, product, provider modes | Reachability and declared mode; do not turn a healthy process into verified prices. |
| `GET /api/dashboard` | Items, cities, snapshot, comparisons, provider modes/source status | Resolve requested tracked item and actual snapshot. |
| `GET /api/snapshots` | Up to 50 snapshots | Select explicit snapshot identity; do not invent an empty snapshot. |
| `GET /api/snapshots/{id}/observations?item_id=...&city_id=...` | Observation rows, up to 1000 before filters | Import scoped receipts; mark missing coverage instead of inventing prices. |

The exact
[PriceObservation](../../../Inflation-Forge-main/backend/models/domain.py)
fields are `id`, `snapshot_id`, `city_id`, `item_id`, `year`, `price_usd`,
`currency`, `kind` (`LIVE`/`ARCHIVED`), `observed_at`, `retrieved_at`,
`source`, `source_url`, `raw_label`, `raw_price`, `conversion_multiplier`,
and optional `archive_timestamp`. The enclosing snapshot has `content_hash`
and `trace_id`; a row does not provide a publisher page hash or full page text.

The existing [market adapter](../../../adapters/market.py) provides
`price_evidence(item_query, city_id)` and returns unavailable evidence for an
untracked item. It converts upstream float money through a decimal string
and carries the approximation note. Preserve USD and that note; no implied
INR conversion. Its mapping of upstream `LIVE` to `VERIFIED` is too broad to
reuse as ECHO truth: live means collection kind, not independent verification.

### Provenance and graph fit

Observation and snapshot IDs, URLs, archive timestamps, normalization and
receipt times form a useful reproducible evidence chain. Preserve the
upstream observation ID separately from ECHO's canonical ID. Hash the received
row for a response artifact; keep the snapshot hash labeled as an upstream
aggregate hash, not an independently computed publisher hash.

An archive capture and a live or Jina-proxied view of the same publisher are
temporally different observations of that publisher. Model the archive/proxy
as `MIRRORS`/`DERIVED_FROM` when the actual original URL is established; these
must not become independent corroboration solely because their hosts differ.
A city/item price claim should carry year, unit, currency, locality and
normalization so ECHO does not compare different items or seasons.

### Failure and security findings

Missing cities/observations are explicit; live-reader and local Port fallbacks
are declared modes. Publisher/network failures must remain unavailable.
The source collector extracts remote HTML using parsing rather than executing
scripts. The configured API has open CORS and no route authentication observed;
mutation routes (`/api/items`, retirement/restore, sync) can modify internal
state and trigger network costs. Exclude them from the ECHO read-only contract.
Keep Port and OTLP credentials in the separate service.

Backend tests cover parsing, comparison, normalization, factory lifecycle,
sync jobs, bootstrap and telemetry. The existing
[project review](../../project-review.md) records 18 passing tests in its
earlier review; this intake does not claim a fresh run or live collection.

## PROXY / CONSUMER dossier

### Purpose, runtime, and state

The Python FastAPI backend and Next frontend run a consumer case workflow:
research, uploaded-document extraction, strategy, appeal drafts and agent
review. It covers consumer dispute domains; it is not a booking or browser
purchase agent. Internal LangGraph orchestration, memories and Neo4j/JSONL
graph are capability internals, never a competing ECHO decision core.

Dependencies are largely pinned: FastAPI/Pydantic, LangGraph/LangChain,
Supabase, Qdrant, Neo4j, Redis, Gemini SDK, httpx, PDF/image libraries,
PyJWT, Playwright, and file locks. Default local storage includes JSONL app
records and vector/graph fallback stores; configured installations use
Supabase/Postgres/storage, Qdrant, Neo4j and Redis. Case documents, drafts,
events and agent runs are persisted. Chromium is needed for the optional
Playwright document collector; no GPU requirement was established.

Provider and network boundaries include configured Gemini or NVIDIA
(`integrate.api.nvidia.com`), Tavily search, Supabase, vector/graph/cache
services, and curated/government/institution document URLs. OCR can send
document imagery to a model provider. An ECHO extension must receive only the
authorized case bundle, with provider data processing/retention disclosed.

### Exact authenticated API contract

The default prefix is `/api/v1` in
[core/config.py](../../../CONSUMER-main/backend/app/core/config.py). Supply
`Authorization: Bearer <verified user token>` for user routes. Development mode
without a JWT secret accepts the bearer string as the user ID; this is an
explicit development identity shortcut and must not be used as production
authentication.

| Call | Input/output | ECHO boundary |
|---|---|---|
| `GET /health` | Component status and environment | Liveness/readiness declaration only. |
| `POST /api/v1/cases` | `domain`, `title`, `institution_name`, `summary`, `jurisdiction`; returns owned case ID/status | Explicit case creation after user authorization; stores ECHO transaction reference in controlled metadata/event, not a second canonical transaction. |
| `POST /api/v1/case/upload` | Multipart `case_id`, `file`, optional `document_type` | Authorized evidence copy only; document parsing is a separate sensitive-data operation. |
| `POST /api/v1/case/analyze` | `{ "case_id": "..." }`; research/evidence/strategy/draft/review output | Draft assistance; no automatic send or `RESOLVED` transition. |
| `POST /api/v1/agents/run-case` | `case_id`, `include_negotiation_draft` | Existing-case workflow, same draft boundary. |
| `POST /api/v1/agents/ask` | `domain`, `question`, `institution_name` | Case-independent research; no shared-user memory or graph access from ECHO. |
| `GET /api/v1/case/{case_id}` | Owned case, documents, latest saved analysis, appeals | Read persisted trace/provenance. |
| `GET /api/v1/case/{case_id}/history` | Events, agent runs, appeals | Case audit copy only; ECHO owns transaction lineage. |

The existing
[resolution adapter](../../../adapters/resolution.py) calls `/run-case` and
`/ask` relative to its configured URL and does not send a bearer token.
An operator could include `/api/v1/agents` in its base URL, but that still does
not satisfy route auth and breaks root `/health` resolution. Reuse requires
separate origin/API prefix and token handling. Its health reports LIVE on
reachability even for degraded or development backing services; do not reuse
this as extension readiness proof.

### Provenance and graph fit

Normalize cited regulation/source records as external observations and drafts
as generated artifacts from an `ExtensionRun`. Preserve the transaction,
decision and prior evidence IDs supplied by ECHO; keep PROXY case IDs only as
external references. Source excerpts and retrieval facts must survive the
handoff. Draft conclusions must not become independent source roots.

`case_ai._analysis_response()` produces `structured_citations`, graph patterns
and review history, but its typed `CaseAnalysisResponse` does not declare
those fields. FastAPI response filtering can omit them from the typed analyze
route. They are stored in the saved analysis and can be read via case detail;
the untyped `/api/v1/analyze` alias also returns the richer dict. Explicitly
check actual response shape rather than assume every endpoint preserves the
same provenance.

The deterministic
[citation verifier](../../../CONSUMER-main/backend/app/services/citation_verification.py)
checks phrase/significant-word occurrence; for fewer than two significant
words it returns true. That is a corpus occurrence heuristic, not a proof of
legal validity, jurisdiction, entailment or independent corroboration. Keep
its outcome labeled as upstream verification metadata and require ECHO's
own evidence gates.

### Failure and security findings

JWT verification and owner checks exist for user routes, but production needs
actual JWT configuration rather than the development shortcut. Uploads,
PDF/image parsing, provider calls and browser collection widen the processing
surface. The Playwright PDF collector applies domain checks to one anchor
collection path, while a subsequent locator loop can add PDF links without
that check; do not expose it as a general safe fetch capability. Admin
operations, ingestion/reindex, internal graph and other users' cases are
outside the extension contract.

Tests cover auth, APIs, provider/router behavior, OCR, case analysis, corpora,
vector stores, collection registry and graph events. The existing project
review records 65 passing backend tests. This intake did not rerun them or
prove provider/legal-document freshness.

## Rumi dossier

### Purpose, runtime, and state

Rumi's React/Vite/TypeScript/Three.js application creates an editable room
workspace from iOS RoomPlan/imported scans, uses a Convex/OpenAI design agent
and Exa-backed merchant search, and validates room geometry and budgets.
It adds spatial product constraints, not general B2B supplier procurement,
checkout or a new ECHO approval authority.

The shared contracts use Zod, metres, USD integer cents and explicit
confirmed/estimated/unknown dimensions. The browser retains scans/editor
history; authenticated messages, snapshots, products and plans persist in
Convex. Clerk identity drives ownership. Dependencies include React,
Three.js, Convex/Clerk, AI SDK/OpenAI, Zod and Bun tooling, with many version
ranges plus a lockfile. iOS capture requires compatible Apple hardware and
native build tooling; live search does not require the iOS capture path.

`OPENAI_API_KEY` and `EXA_API_KEY` remain in the Convex environment; Clerk
issuer and hosted Convex configuration are separate identity/deployment
boundaries. Network includes OpenAI, `api.exa.ai`, Convex/Clerk and merchant
pages/images/JSON/Shopify endpoints. No GPU requirement was established.

### Actual contract and missing external endpoint

[convex/search.ts](../../../rumi-main/convex/search.ts) exposes
`searchProducts` and `searchCategories` as **internalAction**, not public HTTP
endpoints. The internal search persists products and returns only the first
candidate per category after pipeline ranking. It cannot be invoked directly
through a claimed `/search` URL.

The actual [HTTP router](../../../rumi-main/convex/http.ts) provides image and
capture pairing/upload routes. Capture bearer tokens authorize capture
uploads, not ECHO product search. A live ECHO adapter requires an owner-added,
authenticated and scoped service endpoint; this intake does not deploy it.

The internal
[SearchTask contract](../../../rumi-main/shared/contracts/index.ts) includes
`query`, `category`, `maxPriceCents`, nullable `maxFootprint`/`maxHeight`,
`styleTerms`, `palette`, `miscellaneous`, and `excludeTags`. Results include
category/query, ranked candidates, explanation and stage-specific failures.
Each product includes IDs/variant, name/category/merchant, `sourceUrl`, images,
`priceCents`, literal currency `USD`, `measurement`, tags, availability,
asset ID and `synthetic`. Measurement evidence includes kind
(`structured`, `spec-text`, `image`, `mixed`, `none`) and detail.

The existing [spatial adapter](../../../adapters/spatial.py) already accepts
room JSON, retains room ID/revision, uses metres and USD, and performs necessary
constraint screening locally. Its health attempts JSON parsing of `GET /`
and reports LIVE on success; the frontend root normally returns HTML, and the
inspected Convex HTTP router has no root health route. Its placement check is
not Rumi's full geometry engine. Use this adapter as a payload boundary only;
do not advertise it as a deployed Rumi search service.

### Provenance and graph fit

Product source URLs and measurement details are valuable claims, but the
product schema has no source snapshot hash/observed time or explicit citation
dependencies. Store the response artifact and retrieval time in ECHO, keep
dimensions unknown when null, and preserve synthetic status and price units.
Product/room revisions and measurement claims can connect to an ECHO decision;
multiple extraction stages reading one listing still count as one provenance
root unless separate publisher evidence is established.

### Failure and security findings

Rumi's storefront URL check limits scheme/asset-like hosts and its fetch
timeouts/content types constrain responses, but it does not establish a
private-network/redirect egress policy. Provider keys stay server-side;
Clerk ownership checks exist for public authenticated flows. Internal Convex
APIs require operator-controlled bridges, not leaked admin credentials.
Room scans and inspiration photos can contain sensitive personal context.
Never connect ECHO by deploying to an unverified Convex project.

The repository has extensive Bun contract/search/geometry/capture/agent
tests; full checks need generated Convex bindings. The existing project
review records 438 passing tests, with live chat/capture still unverified.
This intake did not rerun tests, deploy Convex, or configure Clerk.

## Adapter acceptance requirements for every project

1. Configure only a trusted service origin in backend environment settings;
   request bodies cannot select arbitrary service URLs, commands, imports or
   graph queries. Restrict egress separately from cited source URLs.
2. Validate a bounded versioned result. Preserve extension ID/version,
   upstream snapshot identity, run ID, receipt timestamp, source URL/publisher,
   evidence excerpt/hash where available, missing fields, units and synthetic
   status. A received JSON hash must be labeled as a response hash.
3. Treat upstream confidence, verification, rank and source count as
   untrusted metadata. ECHO recomputes root diversity from actual graph links
   and owns decision scoring. No extension writes to FalkorDB directly.
4. Assign ECHO canonical IDs; keep upstream IDs as aliases. Import a repeated
   observation idempotently. Do not fabricate publisher snapshots or
   derivation edges to fill missing data.
5. Reject/inhibit live approval for synthetic, malformed, stale or insufficient
   provenance. A timeout, unavailable dependency or disabled license gate
   returns a visible gap, never a fixture disguised as live output.
6. Keep each service's internal cache/index/agent state separate. Only ECHO
   can approve/plan/execute a transaction or decide its dispute lifecycle.
   PROXY drafts require explicit review and a separate send decision.
7. Preserve transport/receipt metadata without converting it into source
   truth. In particular, `LIVE`, a registry search hit, short-text citation
   occurrence and a working health endpoint are not verification of a claim.

## Duplicate authority excluded from the platform

| Existing capability | Preserve inside service | Exclude from ECHO extension authority |
|---|---|---|
| GreenChain Dedalus agents and environmental ranking | Discovery execution and model outputs | Canonical supplier identity, source independence, final procurement winner |
| InflationForge factory/Port catalog | Item collection/versioning and own telemetry | ECHO extension registry, approval policy, supplier price quote |
| PROXY LangGraph/Neo4j/memory | Case-local assistance, retrieval and draft review | ECHO orchestration, shared-user memory, independent legal truth, transaction resolution |
| Rumi design agent/Convex plans | Room-local search, editing and placement validation | ECHO requirement truth, canonical decision, purchase approval |
| Root capability adapters | Existing Beacon lifecycle compatibility | Automatic reuse of VERIFIED classes, unverified LIVE modes or incorrect service route/auth assumptions |

The useful product sequence is supplier/price leads, normalized evidence,
graph dependence analysis, robust decision, human approval, and a traceable
Gateway plan. An extension that cannot provide enough provenance still
contributes a clearly marked lead; it does not become decision-grade support
by adding another agent or dashboard.
