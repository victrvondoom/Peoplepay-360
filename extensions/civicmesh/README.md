# PeoplePay CivicMesh extension

Real typed service integration over the supplied CivicMesh Jac engine. U.S. policy coverage only; estimates are advisory and uncalibrated. The original application remains independently runnable and unchanged.

## Run locally

From the PeoplePay root:

```powershell
python -m venv .venv-civicmesh
.\.venv-civicmesh\Scripts\python.exe -m pip install -r extensions/civicmesh/requirements.txt
docker compose -f compose.echo.yaml up -d
python scripts/dev_peoplepay.py --assistance
```

Existing ECHO/Gateway environments must be installed using `requirements-journey-dev.txt` and `echo/requirements-dev.txt` as documented in `docs/running-peoplepay.md`. The launcher generates a dedicated in-memory service token when unset; no model key is needed. Ports: Gateway 8080, ECHO 8090, CivicMesh deterministic service 8092. Open `/assistance`.

Core only: `python scripts/dev_peoplepay.py`. All integrated runtime services: `python scripts/dev_peoplepay.py --all`. This does not automatically start every bundled specialist UI or configure hosted identities/providers. Native CivicMesh UI instructions remain in `CivicMesh-main/README.md`; its original guarded server defaults to 7860.

Optional container: set a dedicated `PEOPLEPAY_CIVICMESH_TOKEN` then run `docker compose -f compose.assistance.yaml --profile assistance up --build`. The profile/config, isolated image build, HTTP smoke check, boundary tests and native evaluator passed locally; production deployment remains unverified. On a proxy with a custom trusted CA, use `docker build --secret id=peoplepay_build_ca,src=C:/path/to/trusted-ca-bundle.pem -f extensions/civicmesh/Dockerfile -t paymentatcriticalsituation-civicmesh .`. The optional public trust bundle is mounted only during build; TLS verification stays enabled and the bundle is not included in the image.

## Contracts and trace

`ExtensionRequest(capability="assistance_eligibility")` contains `jurisdiction`, controlled `need`, reply `language`, `facts` and explicit `consent`. Facts allow age, annual income, household size, state/city and voluntary status. Extra fields, original text, payment data and credentials are rejected.

Service `POST /api/v1/evaluate` adds `workflow_id` and `request_id`. It returns real native program rankings, rule references, criteria, policy version/date/source references, plan, routes, next question, source fingerprint and timing. No visitor graph or profile is returned.

Adapter returns SDK program entities with claim/estimate/evidence references and ActionProposals. Next question, routes, policy metadata and producer trace live in the bounded `raw_result` envelope; SDK v1 remains compatible. ECHO's bridge validates them and creates canonical Program nodes, Claim/Evidence/Source/ExtensionRun nodes and Decision `USED_CLAIM` links.

Programs are identified by provider-scoped rule IDs. Matching names across unrelated policy engines never silently establishes identity. Bundled reference URLs are **PROVENANCE_UNKNOWN**, with explicit live-verification uncertainty. Scores, capacity priors and route success estimates must not be presented as calibrated probabilities.

Gateway `POST /api/v1/assistance`, `/{id}/answer`, `/{id}/retry`, `GET /{id}/explain` preserve one workflow and immutable ECHO versions. `GET /providers` exposes configured capability/version/jurisdiction and cached health. Procurement routes skip assistance. Provider or ECHO failure preserves the workflow and cannot authorize a payment.

## Checks

```powershell
$env:PYTHONUTF8='1'
.\.venv-civicmesh\Scripts\python.exe -m pytest extensions/civicmesh/tests CivicMesh-main/civicmesh/tests/test_cmguard.py -q
# From CivicMesh-main/civicmesh:
..\..\.venv-civicmesh\Scripts\jac.exe run tests/eval_engine.jac
# From PeoplePay root, with FalkorDB running:
$env:REQUIRE_JOURNEY_GRAPH='1'
.\.venv-echo\Scripts\python.exe -m pytest echo/tests/test_assistance_decisions.py -q
.\.venv-journey-review\Scripts\python.exe -m pytest tests/test_civicmesh_integration.py -q
python scripts/verify_civicmesh_preservation.py
```

Retention: minimal structured facts and normalized decisions persist in local SQLite/FalkorDB. This integration does not promise cross-service deletion or original CivicMesh visitor-session synchronization. Never put real sensitive profiles into this local OPEN-mode demonstration.

Integration level: **3, real typed handoff plus versioned follow-up**, not a full specialist session/SSO federation. See the technical map, upstream record and source-of-truth matrix for precise ownership.

The income follow-up accepts annual USD household income even when the native question mentions monthly income; the portal labels the monthly-to-annual conversion. Other native question types outside the allowlist require native intake or program support. English intent routing is conservative; native EN/ES messages are available, while optional model enrichment stays disabled in this service.

The launcher keeps core services alive if the optional CivicMesh process exits. Its safe recovery procedure is restarting the launcher with the same database/graph configuration, then retrying the saved workflow. A core service exit stops the supervised group. `scripts/benchmark_assistance.py` measures local fictional profiles and writes only ignored diagnostic output.
