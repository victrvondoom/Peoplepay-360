import pytest

from journey.extension_runtime import CapabilityRuntime
from journey.workflow import WorkflowEngine, fingerprint
from tests.test_platform_runtime import Provider, register


def engine(**kwargs):
    runtime = CapabilityRuntime()
    register(runtime, Provider())
    return WorkflowEngine(runtime, **kwargs)


def decision(record):
    return {"decision_id": "decision-"+str(len(record["decisions"])+1), "version": len(record["decisions"])+1,
        "action_scope": {"amount_minor": 100, "currency": "USD"}, "status": "REQUIRES_APPROVAL", "evidence_references": ["receipt-1"]}


def create(host):
    return host.create("owner", intent="Price context", jurisdiction="US", steps=[{"capability": "price.observe", "input": {"product": "chairs"}}])


def test_workflow_is_owner_scoped_and_replay_does_not_invoke_twice():
    host = engine(evaluate=decision)
    record = create(host)
    with pytest.raises(KeyError):
        host.run(record["id"], "other", event_id="run-1")
    first = host.run(record["id"], "owner", event_id="run-1")
    second = host.run(record["id"], "owner", event_id="run-1")
    assert first == second and len(host.runtime.registry.get("sample").received) == 1
    assert first["state"] == "WAITING_FOR_APPROVAL"


def test_new_input_revises_decision_and_invalidates_old_approval():
    host = engine(evaluate=decision)
    record = host.run(create(host)["id"], "owner", event_id="run-1")
    old = record["decisions"][-1]
    host.input(record["id"], "owner", step_index=0, values={"product": "desks"}, event_id="input-1")
    revised = host.run(record["id"], "owner", event_id="run-2")
    assert len(revised["decisions"]) == 2 and revised["decisions"][0] == old
    with pytest.raises(ValueError, match="stale"):
        host.approve(record["id"], "owner", decision_id=old["decision_id"], version=1, scope_hash=fingerprint(old["action_scope"]), event_id="approve-1")


def test_approval_exact_scope_and_execution_replay():
    calls = []
    def gateway(record, key):
        calls.append(key)
        return {"external_authority_reference": "merchant:order-1"}
    host = engine(evaluate=decision, execute=gateway)
    record = host.run(create(host)["id"], "owner", event_id="run-1")
    with pytest.raises(ValueError):
        host.execute_authorized(record["id"], "owner", event_id="action-1")
    d = record["decisions"][-1]
    host.approve(record["id"], "owner", decision_id=d["decision_id"], version=1, scope_hash=fingerprint(d["action_scope"]), event_id="approve-1")
    first = host.execute_authorized(record["id"], "owner", event_id="action-1")
    assert host.execute_authorized(record["id"], "owner", event_id="action-1") == first
    assert calls == ["action-1"]


def test_no_echo_or_required_provider_failure_never_authorizes():
    host = engine()
    record = host.run(create(host)["id"], "owner", event_id="run-1")
    assert record["state"] == "REVIEW_REQUIRED" and not record["approval"]
    host.runtime.set_enabled("sample", False)
    record = host.run(record["id"], "owner", event_id="run-2")
    assert record["state"] == "PARTIAL"
    host.cancel(record["id"], "owner", event_id="cancel-1")
    with pytest.raises(ValueError):
        host.run(record["id"], "owner", event_id="run-3")


@pytest.mark.parametrize("action_key", ["approve-1", "run-1", "", "invalid key"])
def test_invalid_or_reused_action_key_is_rejected_before_external_execution(action_key):
    calls = []
    host = engine(evaluate=decision, execute=lambda record, key: calls.append(key))
    record = host.run(create(host)["id"], "owner", event_id="run-1")
    d = record["decisions"][-1]
    host.approve(record["id"], "owner", decision_id=d["decision_id"], version=1,
        scope_hash=fingerprint(d["action_scope"]), event_id="approve-1")
    with pytest.raises(ValueError):
        host.execute_authorized(record["id"], "owner", event_id=action_key)
    assert calls == []
    assert host.store.get(record["id"], "owner")["state"] == "AUTHORIZED"
