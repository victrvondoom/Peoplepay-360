from unittest.mock import Mock

from backend.services.telemetry.otel import Telemetry


def test_span_emits_a_searchable_structured_log(tmp_path):
    telemetry = Telemetry(tmp_path, mode="local")
    telemetry.logger = Mock()

    with telemetry.span("inflationforge.test", {"snapshot_id": "prices-1"}):
        pass

    severity, event_name = telemetry.logger.log.call_args.args
    attributes = telemetry.logger.log.call_args.kwargs["extra"]
    assert event_name == "span.inflationforge.test.ok"
    assert severity > 0
    assert attributes["event_name"] == event_name
    assert attributes["span_status"] == "OK"
    assert attributes["span_attr_snapshot_id"] == "prices-1"
    assert len(attributes["trace_id"]) == 32
