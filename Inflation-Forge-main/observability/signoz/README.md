# Self-hosted SigNoz

This uses SigNoz's Foundry-based Docker installation. It exposes:

- UI/API: `http://localhost:8080`
- OTLP/gRPC: `http://localhost:4317`
- OTLP/HTTP: `http://localhost:4318`

```bash
make signoz-install
make signoz-up
make signoz-status
make demo-signoz
```

Search for service `inflationforge`. Local admin credentials remain only in the ignored `.env`. Create an `inflationforge-automation` service account if API query access is required; its key is not an OTLP ingestion key.
