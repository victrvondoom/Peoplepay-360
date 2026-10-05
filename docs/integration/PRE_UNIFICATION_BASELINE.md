# Pre-unification repository baseline

Recorded 5 October 2026 before the zero-deletion unification mission.

| Field | Baseline |
|---|---|
| Repository | PeoplePay-360 workspace, `https://github.com/victrvondoom/Peoplepay-360.git` |
| Branch / commit | `master` / `634dd3db73586076bf92648d7e6c32b6260fc9eb` |
| Working tree | Clean before this mission's changes |
| Tracked paths | 1,945 |
| Git LFS paths | 16; `git lfs fsck` passed |
| Top-level tracked groups | `CONSUMER-main` 752; `GREENCHAIN-main` 385; `rumi-main` 265; `Beacon-main` 237; `inheir.ai-main` 129; `Inflation-Forge-main` 65; `echo` 46; `docs` 25; `gateway` 7; `adapters` 7; `extensions` 6; `transaction` 5; root configuration/readmes 6 |
| Existing shared-root test baseline | `python -m pytest -q`: **225 passed** on this baseline |

Tracked path counts are from `git ls-files`; ignored virtual environments,
caches, generated code, local databases, Playwright output, and local build
outputs are not counted. The complete initial path set can be reconstructed
from this commit with `git ls-tree -r --name-only 634dd3db73586076bf92648d7e6c32b6260fc9eb`.

## Projects and services found

| Area | Entrypoint / default local address | Data and integration notes |
|---|---|---|
| PeoplePay Gateway | `python -m gateway.app`; `127.0.0.1:8080` | SQLite transaction/evidence store; local identity fallback or signed Gateway bearer tokens. Sandbox order records do not move money; live checkout returns 503. |
| ECHO | `uvicorn echo.api:app`; `127.0.0.1:8090` | Dedicated `peoplepay_echo` FalkorDB graph, normally reached on loopback port 16380. Its graph is not the Gateway transaction database. |
| GreenChain | `GREENCHAIN-main/greenchain`; backend docs use port 8000 and frontend README uses port 3000 | Python backend and frontend. README claims MIT; no LICENSE file is present in the bundled tree. |
| InflationForge | `Inflation-Forge-main`; backend defaults to port 8000 | Python service with local database configured by `INFLATIONFORGE_DB`; SigNoz/OTel and Port are optional integrations. ECHO's accepted adapter is read-only and disabled by default. |
| PROXY / CONSUMER | `CONSUMER-main` | Python/Next-based dispute/research system with configured PostgreSQL/Supabase, Qdrant, Neo4j and Redis integrations. It has 16 LFS datasets. The PeoplePay gateway already exposes a bounded capability adapter; no ECHO adapter is active. |
| Rumi | `rumi-main`; frontend development uses Vite | React/TypeScript, Convex, Clerk, OpenAI, Exa, and Swift/RoomPlan support. Payments are paused. Convex generated bindings are deployment-owned. |
| Beacon | `Beacon-main` | Python operations/assurance service with AWS/DynamoDB deployment paths and a React/Vite operator UI; UI Vite defaults to 5173. Keep operational approval separate from customer purchasing approval. |
| InHeir.AI | `inheir.ai-main`; frontend docs use port 3000 | Next.js frontend and Python backend, MongoDB/Azure integrations described by its project docs; property/legal work remains a specialized workspace. |
| Root transaction modules | `transaction/`, `adapters/`, `gateway/`, `tests/` | Python transaction lifecycle, capability adapters, gateway API/UI and 225-test root suite. |

The project catalog and preservation commitments are in
[`../SYSTEM_CATALOG.md`](../SYSTEM_CATALOG.md) and
[`PRESERVATION_MANIFEST.md`](PRESERVATION_MANIFEST.md). Service addresses above
are documented development defaults, not a claim that every service is
running together or production configured.

## Verification commands discovered

| Scope | Command | Baseline evidence / caveat |
|---|---|---|
| Root Gateway/transaction suite | `python -m pytest -q` | 225 passed on this baseline. |
| Root static checks | `python -m ruff check transaction adapters gateway tests`; `python -m mypy --check-untyped-defs transaction adapters gateway tests`; `node --check gateway/web/app.js` | Existing review reported these passing. |
| ECHO | `.venv-echo/Scripts/python.exe -m pytest -q echo/tests` | 107 passed on the prior integrated commit with graph tests required; requires local FalkorDB. |
| Beacon | `Beacon-main` dedicated environment, `python -m pytest` | Earlier review reported 451 passed; use Beacon's pinned environment. |
| GreenChain | Backend pytest and frontend npm scripts | Earlier review recorded 48 passed, 6 failures due missing `xgboost`; frontend checks are separate. |
| InflationForge | `Inflation-Forge-main` isolated Python environment, `pytest` | Earlier review reported 18 passed. |
| PROXY / CONSUMER | `CONSUMER-main` backend pytest and frontend TypeScript checks | Earlier review reported 65 passed after local corpus recovery. |
| Rumi | From `rumi-main`: `bun run typecheck`, `bun run lint`, `bun test` | Earlier review reported 438 passed. Some full checks need deployment-generated Convex bindings; offline codegen is not live deployment verification. |
| InHeir.AI | Project frontend/backend commands | Existing backend test directory had no substantive tests in the last review. |

Project-level verification history and current limitations are also recorded
in [`../project-review.md`](../project-review.md) and
[`../test-baseline.md`](../test-baseline.md). Historical results are not
substitutes for rerunning checks after a project-specific change.

## Identity and environment boundary

Gateway owns its local user id, signed token verification, transaction IDs,
and transaction database. ECHO reuses signed Gateway caller identity when
`BEACON_GATEWAY_SECRET` is configured; without it, ECHO and Gateway have a
loopback-only user-header fallback. Rumi uses Clerk/Convex identity and other
specialist services retain their own authentication. There is no repository
wide SSO federation or common organization/RBAC service at this baseline.

Representative server-side configuration names include `BEACON_GATEWAY_PORT`,
`BEACON_GATEWAY_DB`, `BEACON_GATEWAY_SECRET`, `PEOPLEPAY_*_URL`,
`PEOPLEPAY_ECHO_URL`, `ECHO_FALKORDB_PORT`, `ECHO_EXT_*_URL`,
`ECHO_ADMIN_TOKEN`, `INFLATIONFORGE_DB`, `DATABASE_URL`, `SUPABASE_URL`,
`QDRANT_URL`, `NEO4J_URI`, `REDIS_URL`, `VITE_CONVEX_URL`,
`CLERK_JWT_ISSUER_DOMAIN`, `OPENAI_API_KEY`, `EXA_API_KEY`, and
`CHAT_ALLOWED_ORIGINS`. Exact per-service examples are authoritative. No secret
values are recorded here.

## Baseline safety checks

- No changes were present before inventory and baseline verification.
- Git LFS consistency passed before editing.
- No service database or generated output was removed or migrated as part of
  baseline capture.
- Zero-deletion comparison is tied to this exact baseline commit by
  [`scripts/verify_zero_deletion.py`](../../scripts/verify_zero_deletion.py).
