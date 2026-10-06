"""Native service regressions with cloud/database clients replaced before import.

These exercise the actual service functions without Azure keys or Mongo writes.
They are not an integration test of the configured cloud deployment.
"""

import asyncio
import importlib
import io
import sys
import time
from contextlib import nullcontext
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import jwt
import pytest
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient
from starlette.datastructures import UploadFile


@pytest.fixture
def native_modules(monkeypatch):
    config = SimpleNamespace(
        env=SimpleNamespace(
            jwt_secret="inheir-unit-test-key-" + "x" * 64,
            uploads_endpoint="https://storage.example/uploads/",
            knowledge_base_endpoint="https://storage.example/knowledge/",
        ),
        uploads=Mock(),
        knowledge_base=Mock(),
        search=Mock(),
        langchain_llm=Mock(),
        llm=SimpleNamespace(),
    )
    replacement = ModuleType("inheir_backend.config")
    replacement.AppConfig = lambda: config
    replacement.get_config = lambda: config
    monkeypatch.setitem(sys.modules, "inheir_backend.config", replacement)
    modules = {}
    for name in ("services.rag", "services.storage", "helpers.auth", "middleware.auth", "models.auth"):
        qualified = f"inheir_backend.{name}"
        monkeypatch.delitem(sys.modules, qualified, raising=False)
        modules[name] = importlib.import_module(qualified)
        # Restore the module inventory at fixture exit, including modules that
        # were absent before this fixture imported them.
        monkeypatch.delitem(sys.modules, qualified)
        monkeypatch.setitem(sys.modules, qualified, modules[name])
    return config, modules


def test_text_document_has_same_index_schema_as_pdf(native_modules):
    config, modules = native_modules
    blob = config.knowledge_base.get_blob_client.return_value
    blob.get_blob_properties.return_value = SimpleNamespace(metadata={"id": "doc-1", "filename": "law.txt"})
    blob.download_blob.return_value.readall.return_value = b"Preserved title evidence"
    result = modules["services.rag"].process_document("https://storage.example/knowledge/doc.txt")
    assert result["id"] == "doc-1"
    assert result["content"] == "Preserved title evidence"
    assert result["metadata_filename"] == "law.txt"
    assert "updated" in result
    assert "username" not in result


@pytest.mark.parametrize("succeeded, expected", [(True, "success"), (False, "error")])
def test_ingestion_reports_authoritative_index_result(native_modules, monkeypatch, succeeded, expected):
    config, modules = native_modules
    rag = modules["services.rag"]
    monkeypatch.setattr(rag, "process_document", lambda _: {"id": "doc-1", "content": "Evidence"})
    config.search.upload_documents.return_value = [SimpleNamespace(succeeded=succeeded, key="doc-1")]
    result = rag.ingest_document("https://storage.example/knowledge/doc.txt")
    assert result["status"] == expected


def test_ingestion_rejects_empty_index_acknowledgement(native_modules, monkeypatch):
    config, modules = native_modules
    monkeypatch.setattr(modules["services.rag"], "process_document", lambda _: {"id": "doc-1"})
    config.search.upload_documents.return_value = []
    assert modules["services.rag"].ingest_document("doc.txt")["status"] == "error"


def test_generation_uses_configured_langchain_client(native_modules, monkeypatch):
    config, modules = native_modules
    monkeypatch.setattr(modules["services.rag"], "get_openai_callback", nullcontext)
    config.langchain_llm.invoke.return_value = SimpleNamespace(content="  Evidence-grounded response  ")
    assert modules["services.rag"].generate_response("Who owns it?", ["Title deed"]) == "Evidence-grounded response"
    assert "Title deed" in config.langchain_llm.invoke.call_args.args[0]


def test_upload_omits_unset_azure_metadata(native_modules):
    config, modules = native_modules
    file = UploadFile(filename="deed.txt", file=io.BytesIO(b"Title evidence"))
    result = asyncio.run(modules["services.storage"].upload_user_file(file, "user-1", None, None))
    metadata = config.uploads.get_blob_client.return_value.upload_blob.call_args.kwargs["metadata"]
    assert metadata["user_id"] == "user-1"
    assert "case_id" not in metadata
    assert "chat_id" not in metadata
    assert all(isinstance(value, str) for value in metadata.values())
    assert result["status"] == "success"


def test_metadata_update_preserves_unset_existing_links(native_modules):
    config, modules = native_modules
    blob = config.uploads.get_blob_client.return_value
    blob.get_blob_properties.return_value = SimpleNamespace(metadata={"case_id": "case-1", "user_id": "user-1"})
    result = modules["services.storage"].update_user_metadata("hash.txt", None, "chat-2")
    assert result["url"].endswith("hash.txt")
    assert blob.set_blob_metadata.call_args.args[0] == {"case_id": "case-1", "user_id": "user-1", "chat_id": "chat-2"}


def _app_with_auth(modules):
    app = FastAPI()
    app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000"], allow_methods=["GET"])
    app.add_middleware(modules["middleware.auth"].JWTMiddleware)

    @app.get("/api/v1/protected")
    async def protected(request: Request):
        return {"user": request.state.user}

    return app


def test_legacy_expired_jwt_is_rejected_by_middleware(native_modules):
    config, modules = native_modules
    token = jwt.encode({"user_id": "user-1", "username": "owner", "expires": int(time.time()) - 60}, config.env.jwt_secret, algorithm="HS512")
    with TestClient(_app_with_auth(modules)) as client:
        client.cookies.set("token", token)
        assert client.get("/api/v1/protected").status_code == 401


def test_jwt_has_standard_expiry_and_preserves_legacy_expiry(native_modules):
    config, modules = native_modules
    token, expiry = modules["helpers.auth"].sign_jwt("user-1", "owner", "User")
    payload = jwt.decode(token, config.env.jwt_secret, algorithms=["HS512"])
    assert payload["exp"] == expiry == payload["expires"]


def test_preflight_does_not_fail_on_expired_cookie(native_modules):
    config, modules = native_modules
    token = jwt.encode({"user_id": "user-1", "expires": int(time.time()) - 60, "exp": int(time.time()) - 60}, config.env.jwt_secret, algorithm="HS512")
    with TestClient(_app_with_auth(modules)) as client:
        client.cookies.set("token", token)
        response = client.options("/api/v1/protected", headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"})
        assert response.status_code == 200


@pytest.mark.parametrize("password", ["tiny", "x" * 73, "é" * 37])
def test_password_constraints_reject_bcrypt_invalid_input(native_modules, password):
    _, modules = native_modules
    with pytest.raises(ValueError):
        modules["models.auth"].SignUpRequest(username="owner", full_name="Test User", email="owner@example.com", password=password)


def test_wrong_oversized_password_returns_false(native_modules):
    _, modules = native_modules
    auth = modules["helpers.auth"]
    hashed = auth.get_hashed_password("valid-password")
    assert auth.verify_password("x" * 73, hashed) is False


def test_malformed_hash_returns_false(native_modules):
    _, modules = native_modules
    assert modules["helpers.auth"].verify_password("valid-password", "not-a-bcrypt-hash") is False
