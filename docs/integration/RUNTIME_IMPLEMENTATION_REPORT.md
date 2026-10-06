# Runtime implementation report — 2026-10-06

**Mission status: partially implemented. The full platformization success
criterion is not yet satisfied.** The changes are working code with regression
and browser evidence; this report does not assign aspirational integration levels.

Baseline HEAD: `68e22002c0902fdbfc4fbcc6cb242981a468c71b`, branch `master`, clean
before work. Existing tracked paths: 2,202 before; 18 new non-ignored files make
2,220 source paths after staging. The follow-up request authorized fixing errors,
committing and pushing to the existing `origin/master`. Publication does not
change the incomplete-platformization status above.
Zero-deletion baseline: 1,945 paths, zero missing. CivicMesh preservation:
1,987 pre-integration paths and 167 original CivicMesh files, zero missing/changed.

## Delivered

- Existing SDK v1 extended compatibly with dotted capability IDs, workflow and
  jurisdiction context, component and capability health. No replacement SDK.
- Validated runtime manifests and deterministic registry resolution, jurisdiction
  coverage, priority/fallback ordering, enable/disable and instance removal.
- Shared SDK invocation gate for procurement and assistance: input/constraint
  scopes, withheld identity, producer/version/request validation, injected run
  provenance, timeout, concurrency, cancellation, sanitized failures and traces.
- Independent fallback receipts and parallel capability collection. No automatic
  retry storms. Required/optional/enrichment workflow failure policies.
- Generic durable WorkflowEngine with owner-scoped snapshots, versioned events,
  information updates, preserved decision versions, exact scope approval and
  idempotent host callback execution. Absent ECHO/Gateway fails to review.
- Authenticated versioned catalog, capability resolution, workflow and timeline
  APIs. The provider page renders backend status safely and labels readiness.
- ECHO optional-manifest startup isolation; strict validation mode remains for
  compatibility and contract tests. Canonical graph write gates are preserved.
- Reusable benchmark command and runtime/workflow/journey architecture documents.

## Actual capability/provider coverage

| Stable runtime contract | SDK adapter capability | Provider | Current verified boundary |
|---|---|---|---|
| supplier.discovery | supplier_discovery | GreenChain | Shared SDK gate; ECHO procurement; reference merchant journey |
| price.observe | price_intelligence | InflationForge | Shared SDK gate; ECHO price evidence; reference procurement |
| policy.eligibility | assistance_eligibility | CivicMesh | Real local deterministic service; ECHO advisory decisions/follow-up |
| dispute.assist | Existing PROXY draft adapter | PROXY | Automatic reference aftersales; native session contract; not generic SDK runtime |
| design.generate / product.discover | Existing spatial adapter | Rumi | Specialist capability only; no generic SDK provider |
| property.analyze / legal.analyze | Existing property adapter | InHeir | Specialist capability only; no generic SDK provider |
| operations.diagnose / operations.remediate_proposal | Existing assurance APIs | Beacon | Separate operations authority; no generic SDK provider |

Using the mission's 0–5 scale: GreenChain/InflationForge reach level 4 in the
explicit reference workflow (level 5 only for that simulated lifecycle, not
live sourcing/payments). CivicMesh reaches 4 for its locally verified assistance
workflow. PROXY participates in automatic reference aftersales but has not reached
the requested *runtime registration* level. Rumi/InHeir/Beacon runtime targets
remain unmet; previous navigation/adapters do not count as their SDK integrations.
Licensing for GreenChain/PROXY/Rumi remains as recorded in THIRD_PARTY_NOTICES.

## Verification

| Scope | Result |
|---|---|
| Root + SDK integration suite | 415 passed in 24.28 seconds after publication fixes |
| ECHO suite | 140 passed, including optional-manifest isolation |
| New runtime/workflow/API boundaries | Owner separation, replay, stale scopes, disable, wrong jurisdiction, malformed result, producer binding, minimization, timeout, fallback, concurrency/cancellation |
| Beacon | 451 passed |
| GreenChain | 54 passed |
| InflationForge | 22 tests completed successfully |
| PROXY | 65 passed |
| Rumi | 438 passed |
| CivicMesh adapter/native guard | 11 + 28 passed |
| InHeir native-service subset | 15 passed in isolated Python 3.12 fallback; installed Python 3.13 SSL fails |
| Ruff | Available and passed on changed Python modules |
| JavaScript | `node --check gateway/web/extensions.js` passed |
| Preservation | Both checkers passed; no original CivicMesh source changes |
| Git LFS | `git lfs fsck`: OK |
| Browser | Procurement→approval→reference order→260/300 delivery→PROXY linked draft; medical-bill assistance→options/question; extensions page; no console errors |
| Responsive | 390px provider page: document width 390; procurement viewport capture |

The root baseline initially had one malformed-Content-Length socket timeout.
Its targeted rerun and the subsequent full suites passed. It remains a Windows
transport timing observation, not a claimed code fix. Dependency warnings are
not counted as failed tests. Native cloud/model/hosted identity integrations
were not certified by these deterministic tests.

## Benchmark

50 runs, explicit captured-provider replay, no models:

| Component | Median ms | p95 ms |
|---|---:|---:|
| Two capability resolutions | 0.013 | 0.030 |
| Parallel provider invocation/validation/provenance | 1.832 | 4.544 |
| ECHO normalization bridge | 0.600 | 1.074 |

These measure deterministic platform overhead. HTTP, graph evaluation, Gateway
authorization, merchant latency and live models are excluded. Separate ECHO and
Gateway latency distributions have not been measured; no production p95 claim.

## Findings and unresolved work

| Finding | Disposition |
|---|---|
| Procurement bypassed SDK runtime health/scopes | Fixed: uses shared invocation gate |
| Provider-supplied run provenance could be trusted | Fixed at runtime: host stamps independent provenance |
| Wrong-jurisdiction provider invocation | Excluded before health/execute; regression tested |
| Malformed result or forged producer | Rejected before receipt acceptance; regression tested |
| Local adapter exceptions could crash assistance | Isolated as sanitized structured failure |
| Optional malformed ECHO manifest could break startup | Fixed in startup isolation mode |
| Replay/stale workflow approvals | Event/payload conflict checks and exact decision/version/scope binding |
| Reattaching an unregistered runtime provider | Fixed: detach the SDK instance while preserving source/manifest; regression tested |
| Malformed resolution capability/jurisdiction | Fixed: validate SDK contracts before candidate lookup |
| Reused/invalid action event ID detected after external side effect | Fixed: validate and reject conflicting event IDs before invoking Gateway |
| Empty scope/evidence or boolean decision version | Fixed: reject malformed decision/approval contracts |
| Invalid optional provider endpoint breaks catalog startup | Fixed: mark only that provider INVALID_CONFIGURATION and retain usable providers |
| Generic API ECHO/Gateway integration | **Incomplete:** host callbacks not attached; stops at review |
| One engine behind all primary journeys | **Incomplete:** procurement/assistance still have domain coordinators and stores |
| Extension #20 without ECHO edits | Invocation possible with adapter+manifest+tests; new canonical domains still require reviewed translator/policy |
| Runtime SDK PROXY/Rumi/InHeir/Beacon providers | **Incomplete:** adapt existing real contracts, preserving specialist authority and session ownership |
| Malicious local Python code | Contract permissions are not an OS sandbox; unreviewed executable plugins remain prohibited |
| Distributed concurrency/exactly-once/outbox | Process-local limits and SQLite revision guards only; multi-process rollout needs durable coordination |
| SDK raw debug retention | Bounded receipt data retained in workflow/decision; no general retention/erasure policy yet |
| Python 3.13 InHeir verification environment | `ssl.create_default_context()` exits with OPENSSL_Uplink / no OPENSSL_Applink; Python 3.12 subset passed; declared 3.13 deployment unverified |
| Production actions | No production payments; merchant and reference PROXY remain simulators; native provider endpoints/credentials/session federation required |
| Compose profile expansion | Existing graph/assistance compose retained; discovery/property/operations/all profile expansion not implemented |
| UX | Provider transparency added; unified generic workflow home and Rumi/property/operations journeys remain outstanding |

## Run and reproduce

From repository root, after installing documented isolated dependencies and
starting the existing FalkorDB service:

```powershell
$env:ECHO_FALKORDB_PORT='16380'
.\.venv-journey-review\Scripts\python.exe scripts/dev_peoplepay.py
# All currently integrated local core/assistance services:
.\.venv-journey-review\Scripts\python.exe scripts/dev_peoplepay.py --all
.\.venv-journey-review\Scripts\python.exe scripts/benchmark_runtime.py --runs 50
.\.venv-journey-review\Scripts\python.exe -m pytest -q
.\.venv-echo\Scripts\python.exe -m pytest -q echo/tests
python scripts/verify_zero_deletion.py
python scripts/verify_civicmesh_preservation.py
git lfs fsck
```

Ports: Gateway 8080, ECHO 8090, CivicMesh 8092, graph 16380; launcher validates
conflicts. `--all` means all currently integrated local services, not every
bundled specialist UI/cloud backend. Core starts without optional providers.
The review launcher used temporary SQLite paths and graph `peoplepay_runtime_review`.

InHeir fallback subset:

```powershell
uv venv --python 3.12 .venv-inheir-runtime-review
uv --native-tls pip install --python .venv-inheir-runtime-review/Scripts/python.exe -r requirements-inheir-dev.txt
$env:PYTHONPATH='inheir.ai-main/backend/src'
.\.venv-inheir-runtime-review\Scripts\python.exe -m pytest -q inheir.ai-main/backend/tests/test_native_services.py
```

Architecture, event lifecycle, ownership and failure-isolation diagrams are in
`docs/architecture/EXTENSION_RUNTIME.md`, `WORKFLOW_ENGINE.md` and
`UNIFIED_JOURNEYS.md`. Adding the next provider is documented in the runtime
architecture. No CLI was added because the existing developer entrypoint is the
launcher. No claim of production readiness or complete platformization is made.
