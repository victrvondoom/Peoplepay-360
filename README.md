# PeoplePay 360

PeoplePay is an **evidence-aware transaction operating system for AI agents**.
It brings discovery, analysis, verification, decision review, transaction
records, and after-sales resolution into one product journey while keeping
specialist apps and services independently runnable.

## Unified Journey v1

The portal now carries one procurement requirement through the existing
Extension SDK, GreenChain and InflationForge adapters, ECHO on FalkorDB, exact
human approval, a persistent reference merchant, and a PROXY dispute draft.
Open `/journey` on the Gateway. [Run the journey](docs/unified-journey-v1.md).

The acceptance scenario orders 300 chairs from Supplier B for INR 17.7 lakh,
records a simulated delivery of 260, and retains the approved evidence in the
draft for the 40 missing chairs. Historical explanations use the sealed ECHO
decision; refreshing evidence creates a new version. No money moves.
Reference suppliers are fictitious. InflationForge does not track chairs;
the system records that gap instead of inventing price observations.

## ECHO: evidence correlation and decision audit

PeoplePay ECHO is the canonical trust, provenance, and decision service. It
stores sources, dependencies, claims, evidence, supplier representations,
decisions, approvals, and transaction references in FalkorDB. Reviewed
extensions propose intelligence; ECHO applies evidence and policy checks; the
Gateway mediates consequential actions. Merchants and their payment providers
remain authoritative for their own order and payment records.

The demo is synthetic. Its raw scores select Supplier Alpha (94); eight observations trace to one source root. Supplier Beta has a lower raw score (87), but three provenance roots, so its robust score is higher (85 versus 71) and it becomes the recommendation. These values demonstrate the algorithm; they are not supplier facts or validated procurement advice.

## Run the ECHO demo on Windows PowerShell

```powershell
docker compose -f compose.echo.yaml up -d falkordb
python -m venv .venv-echo
.\.venv-echo\Scripts\python.exe -m pip install -r echo\requirements-dev.txt
$env:ECHO_FALKORDB_PORT = "16380"
.\.venv-echo\Scripts\python.exe -m uvicorn echo.api:app --host 127.0.0.1 --port 8090
```

Open `http://127.0.0.1:8090`, then run the synthetic demo. The service health endpoint is `/health`; the OpenAPI page is `/docs`. ECHO APIs bind to loopback in this local setup. Stop FalkorDB with `docker compose -f compose.echo.yaml down` (persistent data remains in its named volume).

The PeoplePay gateway remains a separate service on port 8080. Set
`PEOPLEPAY_ECHO_URL=http://127.0.0.1:8090` when running the gateway to list ECHO
in the suite directory. ECHO's approval API creates a Gateway draft and
planning record only after explicit human confirmation and fresh reevaluation;
it never executes payment. Synthetic demo decisions are barred from approval.

## Product map and limits

See [the unified product plan](docs/unified-product-plan.md),
[ECHO architecture](docs/echo-architecture.md), [project review](docs/project-review.md),
and [integration map](docs/integration-map.md). The existing
[PeoplePay Extension SDK v1](packages/peoplepay-extension-sdk/README.md) now
carries the [Unified Journey v1](docs/unified-journey-v1.md).
GreenChain, Rumi, InflationForge, PROXY, Beacon, and InHeir remain separate
services with separate data and runtime boundaries. The suite directory is
navigation, not shared sign-in or a common database. The journey has explicit
data handoffs for GreenChain, InflationForge and PROXY. External provider and
supplier verification is not implied by either reference demo.

Run instructions and current limitations are in [running PeoplePay](docs/running-peoplepay.md) and [licensing blockers](docs/licensing-blockers.md). See [the ECHO demo guide](docs/DEMO.md) and [judge Q&A](docs/JUDGE_QA.md) for a reproducible walkthrough and claim boundaries.


## CivicMesh assistance integration

PeoplePay now routes relevant U.S. assistance needs through the original CivicMesh deterministic Jac engine, SDK normalization, ECHO evidence/versioned decisions and the `/assistance` portal. Procurement stays connected to GreenChain, InflationForge, the sandbox merchant and PROXY. No live payment is enabled.

Run core: `python scripts/dev_peoplepay.py`. Run assistance: `python scripts/dev_peoplepay.py --assistance`. Run all integrated runtime services: `python scripts/dev_peoplepay.py --all`. Install the isolated environments first. [Run guide](extensions/civicmesh/README.md), [integration report](docs/integration/CIVICMESH_INTEGRATION_REPORT.md), [documentation index](docs/INDEX.md).
# Extension Runtime and workflow engine

The SDK v1 runtime now supplies manifest-based capability resolution, jurisdiction
and input permission gates, validated provider receipts, host provenance, bounded
invocation and provider transparency at `/extensions`. Procurement and assistance
share this invocation path. The reusable workflow engine and versioned APIs are
experimental; their generic ECHO/Gateway callbacks and full specialist migration
are not yet connected. Existing reference procurement/aftersales and local
CivicMesh assistance remain the verified journeys. No production payments occur.

See [implementation evidence and remaining work](docs/integration/RUNTIME_IMPLEMENTATION_REPORT.md),
[runtime architecture](docs/architecture/EXTENSION_RUNTIME.md),
[workflow engine](docs/architecture/WORKFLOW_ENGINE.md), and
[journey ownership](docs/architecture/UNIFIED_JOURNEYS.md).

Run core with `.\.venv-journey-review\Scripts\python.exe scripts/dev_peoplepay.py`;
add `--all` for all currently integrated local services. FalkorDB must be running
first. Specialist projects retain their separate dependencies and run commands.
