from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import time
from typing import Any, Iterator

from opentelemetry import metrics, trace
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor


_CONFIGURED = False
_LOGGER_PROVIDER: Any | None = None


class Telemetry:
    """InflationForge traces and metrics, always mirrored to a durable local audit."""

    def __init__(self, artifacts_dir: Path, endpoint: str = "", mode: str = "console"):
        self.artifacts_dir = artifacts_dir
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self.local_path = self.artifacts_dir / "telemetry.jsonl"
        self.mode = "SIGNOZ OTLP + LOCAL AUDIT" if endpoint else ("LOCAL JSONL" if mode == "local" else "OTEL CONSOLE")
        self._configure(endpoint, mode)
        self.logger = logging.getLogger("inflationforge")
        self.tracer = trace.get_tracer("inflationforge.control_plane", "1.0.0")
        self.meter = metrics.get_meter("inflationforge.control_plane", "1.0.0")
        self.observations = self.meter.create_counter("inflationforge_price_observations")
        self.sync_duration = self.meter.create_histogram("inflationforge_sync_duration", unit="s")
        self.yoy_change = self.meter.create_histogram("inflationforge_yoy_change", unit="%")
        self.source_failures = self.meter.create_counter("inflationforge_source_failures")
        self.tracked_items = self.meter.create_histogram("inflationforge_tracked_items", unit="{item}")
        self.emit("inflationforge.telemetry.ready", telemetry_mode=self.mode)

    @staticmethod
    def _configure(endpoint: str, mode: str) -> None:
        global _CONFIGURED, _LOGGER_PROVIDER
        if _CONFIGURED:
            return
        resource = Resource.create({
            "service.name": os.getenv("OTEL_SERVICE_NAME", "inflationforge"),
            "service.version": "1.0.0",
            "deployment.environment": os.getenv("DEPLOYMENT_ENVIRONMENT", "hackathon-demo"),
        })
        tracer_provider = TracerProvider(resource=resource)
        if endpoint:
            try:
                from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
                from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
                from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
                from opentelemetry._logs import set_logger_provider
                from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
                from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
                from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

                base = endpoint.rstrip("/")
                tracer_provider.add_span_processor(SimpleSpanProcessor(OTLPSpanExporter(endpoint=f"{base}/v1/traces")))
                meter_provider = MeterProvider(resource=resource, metric_readers=[PeriodicExportingMetricReader(OTLPMetricExporter(endpoint=f"{base}/v1/metrics"), export_interval_millis=5000)])
                _LOGGER_PROVIDER = LoggerProvider(resource=resource)
                _LOGGER_PROVIDER.add_log_record_processor(BatchLogRecordProcessor(OTLPLogExporter(endpoint=f"{base}/v1/logs")))
                set_logger_provider(_LOGGER_PROVIDER)
                app_logger = logging.getLogger("inflationforge")
                handler = LoggingHandler(level=logging.INFO, logger_provider=_LOGGER_PROVIDER)
                app_logger.addHandler(handler)
                app_logger.setLevel(logging.INFO)
                app_logger.propagate = False
            except Exception as exc:
                tracer_provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
                meter_provider = MeterProvider(resource=resource)
                print(f"[InflationForge] SigNoz unavailable; local audit remains active: {exc}")
        else:
            if mode != "local":
                tracer_provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
            meter_provider = MeterProvider(resource=resource)
        trace.set_tracer_provider(tracer_provider)
        metrics.set_meter_provider(meter_provider)
        _CONFIGURED = True

    @contextmanager
    def span(self, name: str, attributes: dict[str, Any] | None = None) -> Iterator[Any]:
        safe = {key: self._attribute(value) for key, value in (attributes or {}).items()}
        started = time.perf_counter()
        status = "OK"
        error: str | None = None
        with self.tracer.start_as_current_span(name, attributes=safe) as span:
            try:
                yield span
            except Exception as exc:
                status, error = "ERROR", str(exc)
                span.record_exception(exc)
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(exc)))
                raise
            finally:
                record = {
                    "timestamp": datetime.now(timezone.utc).isoformat(), "span": name,
                    "trace_id": format(span.get_span_context().trace_id, "032x"),
                    "span_id": format(span.get_span_context().span_id, "016x"),
                    "status": status, "duration_ms": round((time.perf_counter() - started) * 1000, 3),
                    "attributes": safe,
                }
                if error:
                    record["error"] = error
                self.emit(
                    f"span.{name}.{'ok' if status == 'OK' else 'error'}",
                    severity=logging.INFO if status == "OK" else logging.ERROR,
                    span_name=name,
                    span_status=status,
                    duration_ms=record["duration_ms"],
                    trace_id=record["trace_id"],
                    span_id=record["span_id"],
                    error=error or "",
                    **{f"span_attr_{key.replace('.', '_')}": value for key, value in safe.items()},
                )
                with self.local_path.open("a") as stream:
                    stream.write(json.dumps(record, sort_keys=True, default=str) + "\n")

    def trace_id(self) -> str:
        return format(trace.get_current_span().get_span_context().trace_id, "032x")

    def record_sync(self, snapshot: Any, comparisons: list[Any], duration_s: float) -> None:
        attributes = {"snapshot_id": snapshot.id, "provider": snapshot.provider_mode}
        self.observations.add(snapshot.observation_count, attributes)
        self.sync_duration.record(duration_s, attributes)
        self.tracked_items.record(snapshot.item_count, attributes)
        self.source_failures.add(len(snapshot.failed_cities), attributes)
        for comparison in comparisons:
            self.yoy_change.record(abs(comparison.change_pct), {
                **attributes, "city": comparison.city.id, "item": comparison.item_id,
                "direction": comparison.direction,
            })

        self.emit(
            "inflationforge.sync.completed",
            snapshot_id=snapshot.id,
            city_count=snapshot.city_count,
            item_count=snapshot.item_count,
            observation_count=snapshot.observation_count,
            comparison_count=snapshot.comparison_count,
            failed_city_count=len(snapshot.failed_cities),
            provider=snapshot.provider_mode,
            duration_ms=round(duration_s * 1000, 3),
            trace_id=snapshot.trace_id,
        )

    def emit(self, event_name: str, severity: int = logging.INFO, **attributes: Any) -> None:
        """Emit a searchable structured log through Python logging and OTLP."""
        safe = {key: self._attribute(value) for key, value in attributes.items()}
        self.logger.log(severity, event_name, extra={"event_name": event_name, **safe})

    def flush(self, timeout_millis: int = 5000) -> bool:
        """Flush batched OTLP logs before a short-lived command exits."""
        if _LOGGER_PROVIDER is None:
            return True
        return bool(_LOGGER_PROVIDER.force_flush(timeout_millis=timeout_millis))

    @staticmethod
    def _attribute(value: Any) -> str | bool | int | float:
        return value if isinstance(value, (str, bool, int, float)) else json.dumps(value, sort_keys=True, default=str)
