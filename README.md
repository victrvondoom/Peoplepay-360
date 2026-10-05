# PeoplePay 360

PeoplePay is an **evidence-aware transaction operating system for AI agents**.
It brings discovery, analysis, verification, decision review, transaction
records, and after-sales resolution into one product journey while keeping
specialist apps and services independently runnable.

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
and [integration map](docs/integration-map.md). The next platform milestone is
[PeoplePay Extension SDK v1](docs/unified-product-plan.md#next-milestone-peoplepay-extension-sdk-v1).
GreenChain, Rumi, InflationForge, PROXY, Beacon, and InHeir remain separate
services with separate data and runtime boundaries. The suite directory is
navigation, not shared sign-in or a common database. External provider and
supplier integrations are not implied by the ECHO demo.

Run instructions and current limitations are in [running PeoplePay](docs/running-peoplepay.md) and [licensing blockers](docs/licensing-blockers.md). See [the ECHO demo guide](docs/DEMO.md) and [judge Q&A](docs/JUDGE_QA.md) for a reproducible walkthrough and claim boundaries.
