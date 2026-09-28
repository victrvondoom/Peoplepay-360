import asyncio
from datetime import datetime, timezone

from backend.config import Settings
from backend.models.domain import PriceSnapshot, SyncJobStatus
from backend.services.inflation.service import InflationForgeService


def make_service(tmp_path) -> InflationForgeService:
    return InflationForgeService(Settings(
        root=tmp_path,
        db_path=tmp_path / "inflation.db",
        otel_mode="local",
    ))


def test_async_sync_job_persists_success(tmp_path, monkeypatch):
    service = make_service(tmp_path)
    snapshot = PriceSnapshot(
        id="prices-test", current_year=2026, previous_year=2025,
        retrieved_at=datetime.now(timezone.utc), provider_mode="TEST",
        content_hash="hash", city_count=1, item_count=1,
        observation_count=2, comparison_count=1,
    )

    async def sync(force: bool = False):
        assert force is True
        return snapshot

    monkeypatch.setattr(service, "sync", sync)
    accepted = service.create_sync_job(force=True)

    assert accepted.status == SyncJobStatus.ACCEPTED
    asyncio.run(service.run_sync_job(accepted.id))

    completed = service.sync_job(accepted.id)
    assert completed.status == SyncJobStatus.SUCCEEDED
    assert completed.snapshot_id == snapshot.id
    assert completed.started_at is not None
    assert completed.completed_at is not None


def test_async_sync_job_persists_failure(tmp_path, monkeypatch):
    service = make_service(tmp_path)

    async def sync(force: bool = False):
        raise RuntimeError("source unavailable")

    monkeypatch.setattr(service, "sync", sync)
    accepted = service.create_sync_job(force=True)
    asyncio.run(service.run_sync_job(accepted.id))

    failed = service.sync_job(accepted.id)
    assert failed.status == SyncJobStatus.FAILED
    assert failed.error == "source unavailable"
    assert failed.completed_at is not None
