from datetime import datetime, timezone

import pytest

from peoplepay_sdk import (
    ActionProposal, Capability, Entity, Evidence, ExtensionContext,
    ExtensionMetadata, ExtensionRequest, ExtensionResult, ProviderRegistry,
    ExtensionHealth, PeoplePayEvent,
)


def metadata():
    return ExtensionMetadata(
        id="sample-provider", name="Sample", version="1.0.0", description="Test provider",
        capabilities=[Capability(name="supplier_search", description="Find suppliers")],
    )


def test_v1_request_and_result_preserve_typed_evidence_and_raw_data():
    request = ExtensionRequest(
        request_id="req-1", capability="supplier_search",
        context=ExtensionContext(trace_id="trace-1"), input={"query": "chairs"},
    )
    result = ExtensionResult(
        request_id=request.request_id, extension_id="sample-provider", extension_version="1.0.0",
        status="success", entities=[Entity(id="supplier-1", entity_type="Supplier", name="Example")],
        evidence=[Evidence(id="evidence-1", source_uri="https://example.test", excerpt="Listing",
                           observed_at=datetime.now(timezone.utc), provenance_state="known")],
        action_proposals=[ActionProposal(id="action-1", action_type="review_supplier", summary="Review")],
        raw_result={"provider_record": "abc"},
    )
    assert request.schema_version == result.schema_version == "1"
    assert result.action_proposals[0].requires_human_approval
    assert result.raw_result["provider_record"] == "abc"


def test_known_evidence_without_source_and_timestamp_fails_closed():
    with pytest.raises(ValueError):
        Evidence(id="e-1", excerpt="claim", provenance_state="known")
    with pytest.raises(ValueError):
        Evidence(id="e-2", source_uri="https://user:pass@example.test", excerpt="claim")


def test_request_rejects_credentials_and_oversized_payloads():
    with pytest.raises(ValueError):
        ExtensionRequest(request_id="req-1", capability="supplier_search",
                         context=ExtensionContext(trace_id="trace"), input={"api_key": "no"})
    with pytest.raises(ValueError):
        ExtensionRequest(request_id="req-1", capability="supplier_search",
                         context=ExtensionContext(trace_id="trace"), input={"text": "x" * 70_000})


def test_registry_requires_explicit_matching_capability_implementation():
    class Sample:
        def metadata(self):
            return metadata()

        def capabilities(self):
            return metadata().capabilities

    registry = ProviderRegistry()
    registry.register(Sample())
    assert len(registry.providers_for("supplier_search")) == 1
    with pytest.raises(ValueError):
        registry.register(Sample())


def test_event_is_versioned_and_requires_timezone_and_correlation():
    event = PeoplePayEvent(
        event_id="evt-1", event_type="transaction.approved", occurred_at=datetime.now(timezone.utc),
        producer="peoplepay-gateway", subject_id="txn-1", correlation_id="trace-1", actor_id="user-1",
    )
    assert event.schema_version == "1"
    with pytest.raises(ValueError):
        PeoplePayEvent(
            event_id="evt-2", event_type="transaction.approved", occurred_at=datetime.now(),
            producer="peoplepay-gateway", subject_id="txn-1", correlation_id="trace-1", actor_id="user-1",
        )
    with pytest.raises(ValueError):
        ExtensionHealth(extension_id="sample-provider", status="healthy", checked_at=datetime.now())
