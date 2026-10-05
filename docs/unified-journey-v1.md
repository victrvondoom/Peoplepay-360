# PeoplePay Unified Journey v1

## What runs

One portal requirement travels through this chain without retyping context:

```text
/journey -> Gateway -> existing Extension SDK
                       | GreenChain native-output adapter
                       | InflationForge native-output adapter
                       v
                 ECHO / FalkorDB
                 normalized claims, evidence, identity aliases, policy
                       v
                 exact human approval / AuthorizedAction
                       v
                 Gateway -> reference merchant session -> order
                       v
                 final delivery event -> discrepancy -> PROXY draft
```

ECHO seals each decision with provider receipts, normalized results, graph
references, raw scores, alternatives, warnings, policy and a SHA-256 hash.
Approval binds the actor, transaction, decision version/hash and exact terms.
The reference merchant owns its catalog, checkout state and order events.
Gateway preserves the lifecycle; a dispute uses the **approved** snapshot even
after new evidence is evaluated. The existing SDK remains version 1.0.0.

## Run on Windows

Run all commands from the repository root with Python 3.12. Existing project
environments can be used if they already contain the required dependencies.
Keep the Gateway and ECHO environments separate from the bundled apps.

Install the Gateway dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e Beacon-main -e packages/peoplepay-extension-sdk -r journey/requirements.txt
```

Start FalkorDB and install ECHO:

```powershell
docker compose -f compose.echo.yaml up -d falkordb
python -m venv .venv-echo
.\.venv-echo\Scripts\python.exe -m pip install -r echo/requirements-dev.txt
```

In an ECHO terminal:

```powershell
$env:ECHO_FALKORDB_PORT = "16380"
$env:ECHO_GRAPH_NAME = "peoplepay_echo"
.\.venv-echo\Scripts\python.exe -m uvicorn echo.api:app --host 127.0.0.1 --port 8090
```

In a Gateway terminal:

```powershell
$env:PEOPLEPAY_ECHO_URL = "http://127.0.0.1:8090"
$env:PEOPLEPAY_JOURNEY_DB = "peoplepay-journey.sqlite3"
$env:BEACON_GATEWAY_DB = "peoplepay.sqlite3"
.\.venv\Scripts\python.exe -m gateway.app
```

Open `http://127.0.0.1:8080/journey`. These services use the existing local
PeoplePay actor. OPEN identity is for loopback development only. If using
signed bearer authentication, set the same `BEACON_GATEWAY_SECRET` in both
service terminals and enter an operator-issued token in the portal. The token
is forwarded to ECHO and retained only in browser memory. This is not SSO.

SQLite records and FalkorDB's named volume persist across restarts. Keep those
stores together when backing up the workflow. `docker compose -f compose.echo.yaml down`
stops the graph container without deleting its volume.

## Acceptance walkthrough

1. Use the preset: 300 ergonomic office chairs, INR 20 lakh, 30 days,
   sustainability prioritized. Select the explicitly labelled reference mode.
2. Create the journey. Inspect both SDK receipts, normalized evidence and policy.
3. Supplier B is recommended at INR 5,900 per chair: INR 17.7 lakh total,
   25-day delivery. Supplier C fails the 30-day limit. Supplier A remains an
   eligible alternative. The reference tax and shipping amounts are zero.
4. Confirm human review and the reference-only terms, then approve B. Gateway
   automatically creates and completes the reference checkout; the portal
   displays session, transaction and merchant order references.
5. Record the simulated final delivery as 260. The 40-chair discrepancy
   automatically creates an unsubmitted draft containing the original
   requirement, selected supplier, decision, evidence, approved terms and event.
6. Use **Why this selection?** to read the preserved approval-time decision.
   Use **What changed?** to collect current context into a new decision version
   and compare it with the historical snapshot. The order and approved terms
   remain tied to the old version. Reload and reopen the saved journey to check
   persistence.

## Native service configuration

The adapters call real service interfaces. Operator-configured HTTP origins
must be loopback; remote origins require HTTPS. Provider failures do not switch
to reference data.

| Setting / provider | Native interface and limits |
|---|---|
| `PEOPLEPAY_GREENCHAIN_API_URL` | `POST /search`, using product, quantity, destination and transport mode. Converts supplier outputs, source URLs, scores and emissions intervals into SDK entities, claims, evidence and estimates. GreenChain needs its own provider credentials and dependencies. |
| `PEOPLEPAY_INFLATIONFORGE_API_URL` | `/api/items`, `/api/snapshots`, and snapshot observations, scoped to an exact item and city. Preserves product identity, location, USD currency, source and observation/retrieval time. Chairs are not in the bundled basket; returns `NOT_TRACKED`. No currency conversion or supplier quote is inferred. |
| `PEOPLEPAY_PROXY_API_URL` + `PEOPLEPAY_PROXY_SESSION_FILE` | Actor-scoped native session mapping for authenticated case creation, JSON evidence upload and appeal drafting. Requires both settings. It does not submit the appeal. |

The PROXY mapping file is private backend configuration outside the repository:
an object keyed by PeoplePay actor ID, whose value contains `proxy_user_id` and
`bearer_token` for that actor's native PROXY session. Tokens are not copied into
decision receipts or evidence bundles. A failed or interrupted native handoff
retains the bundle and any known case ID, and requires reconciliation before
another case can be created. Automatic reconciliation is not implemented.

Selecting native research mode can acquire evidence from configured services.
It **cannot authorize commerce** in v1: supplier/merchant verification and a
live merchant connector are still required. The reference merchant is the only
checkout implementation, and all orders record `money_moved: false`.

## Evidence and authority limits

- GreenChain's reference fixture is generated by its actual
  `compute_composite_scores` function using fictitious suppliers. It proves the
  native output conversion, not live discovery, trained-model inference or a
  carbon certificate. The reproducible capture scripts are in `journey/fixtures/`.
- InflationForge's reference fixture comes from its native service factory on
  a disposable local database. Its observations describe a USD city basket.
  The chair scenario intentionally has no price observation; its price comes
  from the reference merchant catalog.
- Identity reconciliation merges aliases using exact identifiers. Display
  names alone do not merge, and an identifier match is not identity verification.
- The reference decision uses a fixed sustainability/price weighting. It is
  separate from ECHO's existing correlation benchmark. Scores remain estimates
  with explicit provenance warnings.
- The merchant implements create/update/get/complete/cancel, request IDs,
  idempotency, repricing and order events, with a durable one-order-per-transaction
  constraint. It follows checkout lifecycle semantics but is not an ACP
  implementation or a payment provider. The external reference is the
  [Agentic Checkout specification](https://developers.openai.com/commerce/specs/checkout).
- Reference PROXY creates a local draft from the automatic evidence bundle.
  Native endpoint contract tests do not prove the native app's database, LLM
  generation, legal accuracy or external filing. Human review remains required.
- No live payment, refund, courier tracking, verified supplier identity,
  federated SSO or production deployment is claimed. Legacy routes and bundled
  project sources remain available.

## Verification

Start FalkorDB first. Run the root suite from its existing development
environment, and ECHO tests from the isolated environment:

```powershell
$env:REQUIRE_JOURNEY_GRAPH = "1"
python -m pytest -q
.\.venv-echo\Scripts\python.exe -m pytest -q echo/tests
python -m mypy --check-untyped-defs transaction adapters gateway tests
ruff check transaction adapters gateway journey tests echo/journey.py echo/tests/test_journey_decisions.py
node --check gateway/web/journey.js
python scripts/verify_zero_deletion.py
```

Verified on 5 October 2026: **299 root tests and 115 ECHO tests passed**.
The HTTP integration suite runs real Gateway and ECHO processes against
FalkorDB, with UUID test graphs and temporary SQLite stores. Missing graph
infrastructure is a failure when `REQUIRE_JOURNEY_GRAPH=1`. Tests cover exact
approval, ownership, cold graph startup, retries, repricing, cancellation,
restart persistence, concurrent write protection, duplicate-order prevention,
and an ambiguous native PROXY failure. ECHO history tests advance the clock
six days and confirm that refresh does not overwrite the original evidence.

The browser completed the preset, approval, 260-chair delivery, dispute draft,
history and refresh. Desktop and mobile were inspected, with no console errors
and no page overflow at 390 pixels. Two dependency warnings remain: Pydantic's
protected namespace warning in the existing ECHO contract and Starlette's
test-client deprecation. Tests passed with these warnings.

## API entry points

Gateway authenticates all `/api/v1/journeys` routes:

| Method | Route | Operation |
|---|---|---|
| GET / POST | `/api/v1/journeys` | List owned records / create and evaluate a requirement |
| GET | `/api/v1/journeys/{id}` | Read the owned persisted workflow |
| POST | `/api/v1/journeys/{id}/approve` | Bind exact decision/version/supplier and explicit confirmations; run reference checkout |
| POST | `/api/v1/journeys/{id}/delivery` | Record a final reference delivery event; hand off discrepancy evidence |
| POST | `/api/v1/journeys/{id}/refresh` | Evaluate current evidence as a new version and preserve history |
| GET | `/api/v1/journeys/{id}/explain` | Retrieve the sealed approved decision from ECHO |

ECHO exposes `/echo/v1/journeys/evaluate`, `/echo/v1/journeys/{id}/current`,
`/echo/v1/journeys/decisions/{id}` and its `/approve` operation. The service
reuses PeoplePay caller verification and owner-scoped graph reads.
