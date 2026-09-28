# SigNoz / OpenTelemetry

InflationForge sends OTLP/HTTP traces, structured Python logs, and metrics to the self-hosted SigNoz deployment and always mirrors spans to `artifacts/telemetry.jsonl`.

```bash
make signoz-install
make signoz-up
make signoz-status
make demo-signoz
```

Open `http://localhost:8080`. Search service `inflationforge`.

In **Logs**, filter `service.name = inflationforge`. Expected event bodies include:

- `inflationforge.telemetry.ready`
- `span.context.collect.ok`
- `span.price.normalize.ok`
- `span.snapshot.persist.ok`
- `span.port.sync.ok`
- `span.inflationforge.sync.ok`
- `inflationforge.sync.completed`

Span log records carry `trace_id`, `span_id`, `span_name`, `span_status`, and `duration_ms`, so a sync can be followed from a log record into its trace. Logs are emitted through an OpenTelemetry `LoggingHandler` while the span is still current.

Metrics:

- `inflationforge_price_observations`
- `inflationforge_sync_duration`
- `inflationforge_yoy_change` (magnitude with `direction` attribute)
- `inflationforge_source_failures`
- `inflationforge_tracked_items`

Suggested panels: sync p95, observations per snapshot, failures by provider, absolute YoY change by item/city, and active tracked-item count.

Self-hosted ingestion is keyless. `SIGNOZ_API_KEY` is only for service-account queries and automation.
