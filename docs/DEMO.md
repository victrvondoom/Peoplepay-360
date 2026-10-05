# PeoplePay ECHO demo

## Start

From the repository root in PowerShell:

```powershell
docker compose -f compose.echo.yaml up -d falkordb
python -m venv .venv-echo
.\.venv-echo\Scripts\python.exe -m pip install -r echo\requirements-dev.txt
$env:ECHO_FALKORDB_PORT = "16380"
.\.venv-echo\Scripts\python.exe -m uvicorn echo.api:app --host 127.0.0.1 --port 8090
```

Open `http://127.0.0.1:8090` and click **Run the false-consensus demo**. The service health endpoint at `/health` confirms the FalkorDB connection.

The browser also has **Run the cross-extension demo**, which sends two
first-party synthetic provider proposals through the same ECHO graph and shows
their combined provenance trace. Both demos are synthetic; neither calls a
real supplier service.

## Walkthrough

1. The demo seeds a marked synthetic requirement, three suppliers, agent runs, evidence, and source lineage into the `peoplepay_echo` graph.
2. Four Alpha citations and derivative pages plus one original are traversed back to one provenance root. Beta has three evidence paths terminating at three roots. Gamma has one root and is ineligible under the minimum-root policy.
3. The application compares raw and robust scores. Alpha's raw 94 drops to 71; Beta's raw 87 becomes 85. Beta is recommended because the raw-score leader has only one provenance root.
4. The UI displays the graph paths, score components, and root-removal counterfactuals. The decision and candidates are persisted for trace queries.

The score is `clamp(raw_score - 3 × max(0, evidence_count - root_count) - 20 × (1 - mean_confidence), 0, 100)`. It is a deterministic demonstration policy, not a trained model, calibrated probability, or statistical-independence test.

## Invalidate a source

Use the demo root `source-beta-root-1` and call:

```powershell
$echoHeaders = @{ "X-Beacon-User" = "echo-demo-user" }
$body = @{ reason = "Synthetic demo invalidation" } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8090/echo/sources/source-beta-root-1/invalidate -Headers $echoHeaders -ContentType application/json -Body $body
```

ECHO marks the source inactive, looks up decisions that used it, and records a reassessment linked to its parent decision. Completed transactions are not automatically reversed. This fixture operation is repeatable by clicking the demo button again, which resets only the dedicated demo namespace.

## APIs

- `POST /echo/demo/run`: seed and evaluate the synthetic fixture.
- `POST /echo/requirements`: persist a user requirement.
- `POST /echo/requirements/{id}/evaluate`: analyze currently linked evidence.
- `GET /echo/decisions/{id}/trace`: return graph-backed evidence traces.
- `POST /echo/sources/{id}/invalidate`: record invalidation and reassess impacts.
- `POST /echo/decisions/{id}/approve`: require `human_confirmation: true`, then create a non-executing plan through the configured PeoplePay gateway for a non-demo decision.

When `BEACON_GATEWAY_SECRET` is configured, ECHO requires the Gateway-issued
signed bearer token for caller identity. Without it, local mode trusts the
`X-Beacon-User` header; keep the service on loopback. Admin extension toggles
also require `ECHO_ADMIN_TOKEN` and `X-Echo-Admin-Token`. Configure
`PEOPLEPAY_GATEWAY_URL` for approval calls and pass the caller bearer token
through to the Gateway. The synthetic demo cannot be approved into a real
transaction. This identity wiring is not production SSO or multi-worker
approval coordination.
