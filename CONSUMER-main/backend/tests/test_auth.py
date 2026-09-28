import time
from datetime import datetime, timedelta, timezone

import jwt
import asyncio
import pytest
from fastapi.testclient import TestClient

from app.auth.jwt import JwtVerificationError, verify_supabase_jwt
from app.core.config import get_settings
from app.database.postgres.repositories import CaseRepository
from app.main import app
from app.models.domain import Domain
from app.schemas.cases import CaseCreate


JWT_SECRET = "test-supabase-jwt-secret-for-proxy"


@pytest.fixture(autouse=True)
def auth_env(monkeypatch):
    monkeypatch.setenv("SUPABASE_JWT_SECRET", JWT_SECRET)
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
    from app.rag.retrieval import factory as vector_factory
    from app.knowledge_graph import factory as graph_factory

    vector_factory.get_vector_store.cache_clear()
    graph_factory.get_graph_store.cache_clear()


def _token(sub: str = "user-a", email: str = "a@example.com", expired: bool = False, secret: str = JWT_SECRET) -> str:
    now = datetime.now(timezone.utc)
    exp = now - timedelta(minutes=5) if expired else now + timedelta(hours=1)
    payload = {"sub": sub, "email": email, "aud": "authenticated", "exp": int(exp.timestamp())}
    return jwt.encode(payload, secret, algorithm="HS256")


def test_valid_jwt_succeeds() -> None:
    claims = verify_supabase_jwt(_token())
    assert claims["sub"] == "user-a"


def test_expired_jwt_rejected() -> None:
    with pytest.raises(JwtVerificationError):
        verify_supabase_jwt(_token(expired=True))


def test_tampered_jwt_rejected() -> None:
    with pytest.raises(JwtVerificationError):
        verify_supabase_jwt(_token(secret="wrong-secret"))


def test_case_access_is_user_scoped() -> None:
    async def setup_case() -> dict:
        from app.database.postgres.repositories import case_repository

        return await case_repository.create_case(
            "user-a",
            CaseCreate(
                domain=Domain.HEALTH_INSURANCE,
                title="Denied MRI",
                institution_name="Star Health",
                summary="MRI denied.",
            ),
        )

    case = asyncio.run(setup_case())
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get(
        f"/api/v1/cases/{case['id']}",
        headers={"Authorization": f"Bearer {_token(sub='user-b')}"},
    )
    assert response.status_code == 404
