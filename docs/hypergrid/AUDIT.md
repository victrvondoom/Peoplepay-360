# Repository audit (2026-10-08)

Method: read the code and docs named below; ran the test suites; verified licence files on disk. README statements were not treated as evidence of runtime behaviour.

## Layout and runtime

| Area | What exists (verified) |
|---|---|
| `gateway/` | Dependency-free stdlib HTTP server (transactions, workflows, journeys, assistance, and since the previous change `/api/v1/models/*`, `/api/v1/chat`). Pages `/ask`, `/models`. Rate limiting, optional signed tokens. |
| `echo/` | FastAPI + FalkorDB: sources, claims, evidence (valid/observed time), provenance roots, decisions, source invalidation with impact query and sequential revaluation. Tests need a live FalkorDB. |
| `journey/` | Workflow engine, extension runtime, SDK bridge, capability router. |
| `packages/peoplepay-extension-sdk` | SDK v1 contracts. |
| `packages/peoplepay-model-gateway` | Provider-agnostic model layer (previous change): mock/contract verified, no live provider. |
| `Inflation-Forge-main` | Separate MIT project: item/price collection "factory" with its own UI and tests. Not an economic time-series evidence service; not wired to ECHO in this repo. |
| `GREENCHAIN-main` | Separate project; added 2026-10-05; README claims MIT but no LICENSE file. |
| `CivicMesh-main`, `Beacon-main`, `CONSUMER-main`, `rumi-main`, `inheir.ai-main` | Separate projects with their own runtimes; see MIGRATION.md for their AI clients. |
| CI | `.github/workflows/civicmesh-integration.yml`, `model-gateway.yml`. No GitLab configuration existed. |

## Test baseline (this machine)

* Root suite (`pytest`): 549 passed, 15 skipped, 0 failed before HYPERGRID.
* ECHO suite: 73 passed, 60 skipped, 7 errors (`ConnectionRefusedError` to FalkorDB on 127.0.0.1:16380): environmental.
* Specialist projects' own suites were not re-run in this change (see `docs/test-baseline.md` for their recorded state).

## Bottlenecks and redundancy found by inspection

1. ECHO source invalidation revalues every dependent decision sequentially inside the HTTP handler (not measured).
2. No result cache and no pricing awareness before the Model Gateway work; no deterministic-first path for explanations.
3. No knowledge-time revision history for numeric observations.
4. Repeated independent AI clients across specialist projects, each with its own retry/fallback chain (see MIGRATION.md).

## Licensing inventory (verified by reading LICENSE files / metadata)

| Component | Licence | Note |
|---|---|---|
| Repository root | **none** | no LICENSE file |
| Beacon-main | Apache-2.0 | |
| Inflation-Forge-main | MIT (Kaushik Sivakumar, 2026) | attribution on redistribution |
| CivicMesh-main | MIT (Anbu, 2026) | |
| inheir.ai-main | MIT (InHeir.AI, 2025) | |
| CONSUMER-main (PROXY), rumi-main | **none** | all rights reserved by default; no code may be copied |
| GREENCHAIN-main | README says MIT; **no LICENSE file** | confirm with owners |
| FalkorDB container image | SSPLv1 (per registry metadata, recorded in docs/licensing-blockers.md) | external dependency |
| World Bank fixture | CC BY 4.0 | attribution recorded in THIRD_PARTY_NOTICES.md |
| HYPERGRID, Model Gateway | new code; depend on NumPy (BSD-3) / optional `cryptography` | no licence file added; the author decides |
