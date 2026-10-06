"""Real original Jac policy functions behind the thin service HTTP boundary."""
import json
import os

import pytest
from fastapi.testclient import TestClient

from extensions.civicmesh.service import app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("PEOPLEPAY_CIVICMESH_TOKEN", "boundary-test-" + "x" * 32)
    with TestClient(app) as client:
        yield client


def request(**overrides):
    return {"workflow_id": "native-http-test", "request_id": "native-http-test-v1", "jurisdiction": "US",
            "need": "eviction", "consent": True, "facts": {"age": 72, "income_annual": 14400}, **overrides}


def post(client, body):
    return client.post("/api/v1/evaluate", json=body, headers={"Authorization": "Bearer " + os.environ["PEOPLEPAY_CIVICMESH_TOKEN"]})


def test_real_engine_no_model_required(client, monkeypatch):
    for name in ("NVIDIA_API_KEY", "GROQ_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    response = post(client, request())
    assert response.status_code == 200
    result = response.json()
    assert result["programs"] and result["question"]["text"] and result["plan"]["steps"]
    assert result["calibrated_probability"] is False
    assert "income_annual" not in json.dumps(result)
    assert result["policy_date"] and result["policy_last_verified"]
    assert client.get("/health").json()["engine"] == "ENGINE_OK"


@pytest.mark.parametrize("bad", [{"message": "raw-sensitive-unrelated-text"}, {"payment_account": "secret"}, {"facts": {"age": -1}}, {"consent": False}])
def test_structured_permission_boundary(client, bad):
    assert post(client, request(**bad)).status_code == 422


def test_auth_and_jurisdiction(client):
    assert client.post("/api/v1/evaluate", json=request()).status_code == 401
    assert post(client, request(jurisdiction="IN")).json()["detail"] == "UNSUPPORTED_JURISDICTION"


def test_question_and_language_are_stable(client):
    one = post(client, request()).json()
    two = post(client, request()).json()
    es = post(client, request(language="es")).json()
    assert one["question"] == two["question"]
    assert [i["p_eligible"] for i in one["programs"]] == [i["p_eligible"] for i in es["programs"]]


def test_native_crisis_is_pinned(client):
    result = post(client, request(need="crisis")).json()
    assert result["crisis"] is True
    assert "988" in result["programs"][0]["resource_name"]


def test_effective_policy_date_stays_explicit(client, monkeypatch):
    monkeypatch.setenv("CIVICMESH_POLICY_DATE", "2026-09-27")
    first = post(client, request(need="healthcare", facts={"citizenship": "refugee", "age": 35, "income_annual": 10000, "state": "CA"})).json()
    monkeypatch.setenv("CIVICMESH_POLICY_DATE", "2026-10-06")
    second = post(client, request(need="healthcare", facts={"citizenship": "refugee", "age": 35, "income_annual": 10000, "state": "CA"})).json()
    assert first["policy_date"] == "2026-09-27" and second["policy_date"] == "2026-10-06"
    assert first["programs"] != second["programs"]


def test_body_limit_precedes_json_parsing(client):
    assert client.post("/api/v1/evaluate", content=b"{" + b"x" * 16_384).status_code == 413


def test_rate_registry_does_not_grow_after_capacity(client, monkeypatch):
    import time
    from collections import defaultdict, deque
    from extensions.civicmesh import service

    hits = defaultdict(deque, {f"workflow-{i}": deque([time.monotonic()]) for i in range(1000)})
    monkeypatch.setattr(service, "_hits", hits)
    assert post(client, request(workflow_id="new-workflow")).status_code == 429
    assert len(hits) == 1000
