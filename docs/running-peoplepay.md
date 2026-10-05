# Running the PeoplePay gateway

From the repository root, with the Beacon Python package installed:

```powershell
python -m gateway.app
```

The default address is http://127.0.0.1:8080. Set
`BEACON_GATEWAY_PORT` to change the port and `BEACON_GATEWAY_DB` to select
the SQLite database path. Existing schema-version-1 databases require migration
before this version can open them; retain the original file.

The workspace includes a PeoplePay product directory. Configure any deployed
specialist frontend URL on the gateway server to enable its link:
`PEOPLEPAY_GREENCHAIN_URL`, `PEOPLEPAY_RUMI_URL`,
`PEOPLEPAY_INFLATIONFORGE_URL`, `PEOPLEPAY_INHEIR_URL`,
`PEOPLEPAY_PROXY_URL`, and `PEOPLEPAY_BEACON_URL`. Unset URLs appear as
`SERVICE NOT CONFIGURED`. These links do not provide shared sign-in or transfer
data between services.

Local requests use `X-Beacon-User`. When `BEACON_GATEWAY_SECRET` is configured,
the existing signed bearer token authentication is required instead.

| Method | Route | Result |
|---|---|---|
| GET | `/health/integrations` | Current provider availability |
| POST | `/transactions` | Create with `raw_utterance` |
| GET | `/transactions` | List the caller's transactions |
| POST | `/transactions/{id}/plan` | Save `summary`, `steps`, integer `amount_minor`, and `currency` |
| POST | `/transactions/{id}/validate` | Check plan budget and required checkout evidence |
| POST | `/transactions/{id}/cancel` | Cancel through the transaction lifecycle |
| GET | `/transactions/{id}/evidence` | Full evidence graph |
| GET | `/transactions/{id}/context` | Capability results |
| GET | `/transactions/{id}/timeline` | Audit events and chain integrity |
| POST | `/transactions/{id}/capabilities/{name}` | Invoke a configured capability and persist its result |

Open the default address in a browser for the unified workspace. It supports
transaction creation, plans, editable carts, sandbox checkout, manual delivery
updates, dispute drafts, evidence exports, and capability requests. Records
persist in SQLite across restarts. The browser stores a local user identifier;
bearer tokens remain in memory and must be entered again after a reload.

Additional POST routes under `/transactions/{id}/`:

| Action | Result |
|---|---|
| `cart` | Save items, currency, shipping and tax in integer minor units |
| `sandbox-checkout` | Confirm `cart_hash` with `confirm_sandbox: true`; repeated requests return the same order |
| `delivery` | Record a permitted status transition and a user-supplied note |
| `dispute` | Save an issue, requested remedy and an unsubmitted draft |
| `checkout` | Returns 503; live payment execution is unavailable |

Amounts are minor units: INR 1,000 is `100000`. Cart prices are self-reported,
not merchant-verified. Plan validation is not payment authorization. Sandbox
orders send nothing to merchants and move no money. Delivery updates are not
courier tracking. Drafts are not legal advice and are never automatically sent.
The four project adapters require their own configured upstream services for
live data; missing configuration is displayed rather than replaced with fake data.

OPEN authentication is only for a trusted local machine. Do not expose this
development server publicly; production requires verified identity, TLS, a
production HTTP server, and configured payment/merchant/courier integrations.


## Verification and current limitations

Run the gateway checks separately from the bundled projects:

```powershell
python -m pytest -q
python -m ruff check transaction adapters gateway tests
python -m mypy --check-untyped-defs transaction adapters gateway tests
node --check gateway/web/app.js
```

See [the project review](project-review.md) for fixes, verified results, remaining
upstream test blockers and production limitations from 2 October 2026.


For Rumi's complete local checks without a deployment, run from `rumi-main`:

```powershell
bun run convex:codegen:offline
bun run typecheck
bun run lint
bun test
```

The offline command creates ignored bindings only. See
[Rumi's workflow](../rumi-main/convex-workflow.md) for its limits and live setup.

Beacon's image requirements need their own environment. This checkout's
`.venv-beacon-review` contains the pinned image requirements as an overlay on
installed development dependencies; the shared Python installation is unchanged.
Run Beacon tests from `Beacon-main` using that environment's Python. A fresh CI
setup should install Beacon's development dependencies and image requirements
in a dedicated environment rather than combine all five projects in one Python.

## ECHO graph and API

Start FalkorDB with `docker compose -f compose.echo.yaml up -d falkordb`.
The compose file binds the graph to `127.0.0.1:16380` to avoid colliding with
the repository's existing CLINI-CASE Redis container on port 16379. Run the
FastAPI process from the repository root with `.venv-echo` and
`ECHO_FALKORDB_PORT=16380`; see [the ECHO demo guide](DEMO.md). The database
volume is persistent. `down` stops containers but keeps that volume; add
`-v` only when intentionally removing the local ECHO graph data.

Git LFS is required for the bundled vector/graph datasets. Run `git lfs pull`
after cloning; `.gitattributes` records the original LFS paths. Recovered source
corpus provenance is recorded in `recovered-corpus-provenance.json`.
