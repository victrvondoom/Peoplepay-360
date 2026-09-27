from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import time
from typing import Any, Awaitable, Callable
from uuid import uuid4

from backend.config import Settings
from backend.db import Database
from backend.models.domain import (
    CityInflationSummary,
    CityPriceComparison,
    InflationDashboard,
    ItemStatus,
    ModeStatus,
    ObservationKind,
    PriceObservation,
    PriceSnapshot,
    PriceSyncJob,
    SourceCatalogItem,
    SyncJobStatus,
    TrackedItem,
    TrackedItemCreate,
)
from backend.services.factory import ItemCapabilityFactory
from backend.services.inflation.collector import CITY_CATALOG, CityCollection, CityPriceCollector, ParsedPriceRow
from backend.services.port.adapter import LocalPortAdapter, RemotePortAdapter
from backend.services.telemetry.otel import Telemetry
from backend.utils import stable_hash, write_json


class InflationForgeService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.db = Database(settings.db_path)
        self.telemetry = Telemetry(settings.artifacts_dir, settings.otel_endpoint, settings.otel_mode)
        self.factory = ItemCapabilityFactory(self.db, settings.artifacts_dir)
        self._bootstrap_real_snapshot()
        self.collector = CityPriceCollector(
            settings.bright_data_token, settings.bright_data_zone,
            settings.price_request_timeout_s, self.telemetry,
        )
        self.collector.load_archive_cache(self.db.get_state("archive_catalog_cache") or {})
        self.local_port = LocalPortAdapter(settings.artifacts_dir / "port-events.jsonl")
        self.port = (
            RemotePortAdapter(settings.port_client_id, settings.port_client_secret, settings.port_api_url, settings.port_api_token)
            if settings.port_api_token or (settings.port_client_id and settings.port_client_secret)
            else self.local_port
        )
        self.port_error: str | None = None
        self.last_port_error: str | None = self.db.get_state("port_last_error")
        self._sync_lock = asyncio.Lock()

    def create_sync_job(self, force: bool = True) -> PriceSyncJob:
        job = PriceSyncJob(id=f"sync-{uuid4().hex[:12]}", force=force)
        self.db.put("price_sync_job", job.id, job)
        self.telemetry.emit("inflationforge.sync.accepted", job_id=job.id, force=force)
        return job

    def sync_job(self, job_id: str) -> PriceSyncJob:
        raw = self.db.get("price_sync_job", job_id)
        if raw is None:
            raise KeyError("Price sync job not found")
        return PriceSyncJob.model_validate(raw)

    async def run_sync_job(self, job_id: str) -> None:
        job = self.sync_job(job_id).model_copy(update={
            "status": SyncJobStatus.RUNNING,
            "started_at": datetime.now(timezone.utc),
        })
        self.db.put("price_sync_job", job.id, job)
        try:
            snapshot = await self.sync(force=job.force)
            job = job.model_copy(update={
                "status": SyncJobStatus.SUCCEEDED,
                "completed_at": datetime.now(timezone.utc),
                "snapshot_id": snapshot.id,
            })
            self.telemetry.emit(
                "inflationforge.sync_job.completed",
                job_id=job.id,
                snapshot_id=snapshot.id,
            )
        except Exception as exc:
            job = job.model_copy(update={
                "status": SyncJobStatus.FAILED,
                "completed_at": datetime.now(timezone.utc),
                "error": str(exc)[:1000],
            })
            self.telemetry.emit(
                "inflationforge.sync_job.failed",
                severity=40,
                job_id=job.id,
                error=job.error,
            )
        self.db.put("price_sync_job", job.id, job)

    def _bootstrap_real_snapshot(self) -> None:
        """Load a pinned, sourced snapshot when an ephemeral deployment starts empty."""
        if self.db.get_state("latest_price_snapshot_id"):
            return
        path = self.settings.root / "data" / "bootstrap_snapshot.json"
        if not path.exists():
            return
        try:
            payload = json.loads(path.read_text())
            snapshot = PriceSnapshot.model_validate(payload["snapshot"])
            observations = [PriceObservation.model_validate(row) for row in payload["observations"]]
            comparisons = [CityPriceComparison.model_validate(row) for row in payload["comparisons"]]
            self.db.put("price_snapshot", snapshot.id, snapshot)
            for observation in observations:
                self.db.put("price_observation", observation.id, observation, parent_id=snapshot.id)
            for comparison in comparisons:
                comparison_id = f"{snapshot.id}-{comparison.city.id}-{comparison.item_id}"
                self.db.put("city_comparison", comparison_id, comparison, parent_id=snapshot.id)

            reference_city = CITY_CATALOG[0].id
            source_catalog: dict[str, SourceCatalogItem] = {}
            archive_cache: dict[str, dict[str, Any]] = {}
            for observation in observations:
                if observation.year == snapshot.current_year and observation.city_id == reference_city:
                    source_catalog.setdefault(observation.raw_label, SourceCatalogItem(
                        label=observation.raw_label,
                        example_price_usd=observation.raw_price,
                        city_id=observation.city_id,
                    ))
                if observation.year == snapshot.previous_year and observation.archive_timestamp:
                    cache_key = f"{observation.city_id}:{snapshot.previous_year}"
                    cached = archive_cache.setdefault(cache_key, {
                        "timestamp": observation.archive_timestamp,
                        "url": observation.source_url,
                        "rows": [],
                    })
                    if observation.raw_label not in {row["label"] for row in cached["rows"]}:
                        cached["rows"].append({"label": observation.raw_label, "price_usd": observation.raw_price})

            self.db.set_state("source_catalog", [row.model_dump(mode="json") for row in source_catalog.values()])
            self.db.set_state("archive_catalog_cache", archive_cache)
            self.db.set_state("latest_price_snapshot_id", snapshot.id)
            self.db.set_state("source_status", {
                "last_success_at": snapshot.retrieved_at.isoformat(),
                "provider": snapshot.provider_mode,
                "history_provider": "Internet Archive Wayback",
                "city_count": snapshot.city_count,
                "comparison_count": snapshot.comparison_count,
                "fallback_reason": "Pinned real snapshot loaded for ephemeral startup; refresh remains live.",
            })
            self.telemetry.emit(
                "inflationforge.bootstrap.loaded",
                snapshot_id=snapshot.id,
                observation_count=len(observations),
                comparison_count=len(comparisons),
            )
        except Exception as exc:
            self.telemetry.emit("inflationforge.bootstrap.error", severity=40, error=str(exc))

    def modes(self) -> ModeStatus:
        port_mode = self.local_port.mode + " · PORT FALLBACK ACTIVE" if (self.port_error or self.last_port_error) else self.port.mode
        latest = self.latest_snapshot()
        return ModeStatus(
            price_provider=latest.provider_mode if latest else self.collector.mode,
            telemetry=self.telemetry.mode,
            port=port_mode,
        )

    async def _sync_port(self, method: str, payload: Any, *args: Any) -> None:
        adapter = self.local_port if self.port_error else self.port
        try:
            await getattr(adapter, method)(payload, *args)
            if adapter is self.port and self.port is not self.local_port:
                self.last_port_error = None
                self.db.set_state("port_last_error", None)
        except Exception as exc:
            self.port_error = str(exc)[:1000]
            self.last_port_error = self.port_error
            self.db.set_state("port_last_error", self.port_error)
            await getattr(self.local_port, method)(payload, *args)

    async def sync(self, force: bool = False) -> PriceSnapshot:
        async with self._sync_lock:
            started = time.perf_counter()
            now = datetime.now(timezone.utc)
            current_year, previous_year = now.year, now.year - 1
            active_items = self.factory.active()
            latest = self.latest_snapshot()
            if not force and self._snapshot_is_fresh(latest, now, len(active_items), len(CITY_CATALOG)):
                with self.telemetry.span("inflationforge.sync.cache_hit", {
                    "snapshot_id": latest.id, "age_seconds": (now - latest.retrieved_at).total_seconds(),
                }):
                    return latest
            with self.telemetry.span("inflationforge.sync", {
                "current_year": current_year, "previous_year": previous_year,
                "city_count": len(CITY_CATALOG), "item_count": len(active_items), "forced": force,
            }):
                trace_id = self.telemetry.trace_id()
                with self.telemetry.span("context.collect", {"cities": len(CITY_CATALOG)}):
                    collections = await self.collector.collect(current_year, previous_year)
                snapshot_id = f"prices-{now:%Y%m%d%H%M%S}-{uuid4().hex[:6]}"
                observations: list[PriceObservation] = []
                comparisons: list[CityPriceComparison] = []
                with self.telemetry.span("price.normalize", {"city_pages": len(collections)}):
                    for collection in collections:
                        city_observations = self._observations_for(snapshot_id, collection, active_items, now, previous_year)
                        observations.extend(city_observations)
                        comparisons.extend(self._comparisons_for(collection, active_items, city_observations, previous_year, current_year))
                content_hash = stable_hash([observation.model_dump(mode="json") for observation in observations], 20)
                collected_ids = {collection.city.id for collection in collections}
                snapshot = PriceSnapshot(
                    id=snapshot_id, current_year=current_year, previous_year=previous_year,
                    provider_mode=self.collector.mode, content_hash=content_hash,
                    city_count=len(collected_ids), item_count=len(active_items),
                    observation_count=len(observations), comparison_count=len(comparisons),
                    failed_cities=[city.name for city in CITY_CATALOG if city.id not in collected_ids],
                    source_urls=sorted({collection.current_url for collection in collections}), trace_id=trace_id,
                )
                with self.telemetry.span("snapshot.persist", {"snapshot_id": snapshot.id, "comparisons": len(comparisons)}):
                    self.db.put("price_snapshot", snapshot.id, snapshot)
                    for observation in observations:
                        self.db.put("price_observation", observation.id, observation, parent_id=snapshot.id)
                    for comparison in comparisons:
                        comparison_id = f"{snapshot.id}-{comparison.city.id}-{comparison.item_id}"
                        self.db.put("city_comparison", comparison_id, comparison, parent_id=snapshot.id)
                    catalog = self._source_catalog(collections)
                    self.db.set_state("source_catalog", [item.model_dump(mode="json") for item in catalog])
                    self.db.set_state("archive_catalog_cache", self.collector.archive_cache)
                    self.db.set_state("latest_price_snapshot_id", snapshot.id)
                    self.db.set_state("source_status", {
                        "last_success_at": snapshot.retrieved_at.isoformat(),
                        "provider": snapshot.provider_mode, "history_provider": "Internet Archive Wayback",
                        "city_count": snapshot.city_count, "comparison_count": snapshot.comparison_count,
                        "fallback_reason": self.collector.provider_error,
                    })
                    write_json(self.settings.artifacts_dir / "manifests" / f"{snapshot.id}.json", {
                        "snapshot": snapshot, "active_items": active_items,
                        "observations": observations, "comparisons": comparisons,
                    })
                with self.telemetry.span("port.sync", {"snapshot_id": snapshot.id, "port_mode": self.port.mode}):
                    for item in active_items:
                        await self._sync_port("sync_item", item)
                    await self._sync_port("sync_snapshot", snapshot)
                    for comparison in comparisons:
                        await self._sync_port("sync_comparison", comparison, snapshot.id)
            self.telemetry.record_sync(snapshot, comparisons, time.perf_counter() - started)
            return snapshot

    def _snapshot_is_fresh(
        self,
        snapshot: PriceSnapshot | None,
        now: datetime,
        active_item_count: int,
        configured_city_count: int,
    ) -> bool:
        if snapshot is None:
            return False
        age_seconds = max(0.0, (now - snapshot.retrieved_at).total_seconds())
        return (
            snapshot.current_year == now.year
            and snapshot.item_count == active_item_count
            and snapshot.city_count == configured_city_count
            and snapshot.comparison_count == active_item_count * configured_city_count
            and age_seconds < self.settings.price_sync_min_interval_s
        )

    def dashboard(self) -> InflationDashboard:
        now = datetime.now(timezone.utc)
        snapshot = self.latest_snapshot()
        comparisons = (
            [CityPriceComparison.model_validate(row) for row in self.db.list("city_comparison", parent_id=snapshot.id, limit=500)]
            if snapshot else []
        )
        return InflationDashboard(
            current_year=now.year, previous_year=now.year - 1, modes=self.modes(),
            cities=CITY_CATALOG, items=self.factory.list(), snapshot=snapshot,
            comparisons=comparisons, overall_comparisons=self._overall_comparisons(comparisons),
            source_catalog=self.source_catalog(), factory_events=self.factory.events(),
            source_status=self.db.get_state("source_status") or {
                "last_success_at": None, "provider": self.collector.mode,
                "history_provider": "Internet Archive Wayback", "city_count": 0,
                "comparison_count": 0, "fallback_reason": None,
            },
        )

    def latest_snapshot(self) -> PriceSnapshot | None:
        snapshot_id = self.db.get_state("latest_price_snapshot_id")
        raw = self.db.get("price_snapshot", snapshot_id) if snapshot_id else None
        return PriceSnapshot.model_validate(raw) if raw else None

    def source_catalog(self) -> list[SourceCatalogItem]:
        return [SourceCatalogItem.model_validate(row) for row in (self.db.get_state("source_catalog") or [])]

    async def create_item(self, request: TrackedItemCreate) -> TrackedItem:
        with self.telemetry.span("capability.item.create", {"name": request.name, "category": request.category}):
            item = self.factory.create(request, self.source_catalog())
            await self._sync_port("sync_item", item)
            return item

    async def retire_item(self, item_id: str, actor: str) -> TrackedItem:
        with self.telemetry.span("capability.item.retire", {"item_id": item_id, "actor": actor}):
            item = self.factory.retire(item_id, actor)
            await self._sync_port("sync_item", item)
            return item

    async def restore_item(self, item_id: str, actor: str) -> TrackedItem:
        with self.telemetry.span("capability.item.restore", {"item_id": item_id, "actor": actor}):
            item = self.factory.restore(item_id, actor)
            await self._sync_port("sync_item", item)
            return item

    def telemetry_tail(self, limit: int = 40) -> list[dict[str, Any]]:
        path: Path = self.telemetry.local_path
        if not path.exists():
            return []
        import json
        return [json.loads(line) for line in path.read_text().splitlines()[-limit:] if line.strip()]

    def _observations_for(self, snapshot_id: str, collection: CityCollection, items: list[TrackedItem], now: datetime, previous_year: int) -> list[PriceObservation]:
        observations: list[PriceObservation] = []
        archive_at = datetime.strptime(collection.archive_timestamp, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
        for item in items:
            for year, kind, rows, source, source_url, observed_at in [
                (now.year, ObservationKind.LIVE, collection.current_rows, "Numbeo public city price table", collection.current_url, now),
                (previous_year, ObservationKind.ARCHIVED, collection.previous_rows, "Internet Archive capture of Numbeo", collection.archive_url, archive_at),
            ]:
                row = self._find_row(item, rows)
                if row is None:
                    continue
                multiplier = self.factory.multiplier_for(item, row.label)
                observations.append(PriceObservation(
                    id=f"obs-{snapshot_id}-{collection.city.id}-{item.id}-{year}", snapshot_id=snapshot_id,
                    city_id=collection.city.id, item_id=item.id, year=year,
                    price_usd=round(row.price_usd * multiplier, 2), kind=kind,
                    observed_at=observed_at, source=source, source_url=source_url,
                    raw_label=row.label, raw_price=row.price_usd, conversion_multiplier=multiplier,
                    archive_timestamp=collection.archive_timestamp if kind == ObservationKind.ARCHIVED else None,
                ))
        return observations

    @staticmethod
    def _comparisons_for(collection: CityCollection, items: list[TrackedItem], observations: list[PriceObservation], previous_year: int, current_year: int) -> list[CityPriceComparison]:
        comparisons: list[CityPriceComparison] = []
        for item in items:
            current = next((row for row in observations if row.item_id == item.id and row.year == current_year), None)
            previous = next((row for row in observations if row.item_id == item.id and row.year == previous_year), None)
            if not current or not previous:
                continue
            change = current.price_usd - previous.price_usd
            pct = change / previous.price_usd * 100
            comparisons.append(CityPriceComparison(
                city=collection.city, item_id=item.id, previous_year=previous_year, current_year=current_year,
                previous_price_usd=previous.price_usd, current_price_usd=current.price_usd,
                change_usd=round(change, 2), change_pct=round(pct, 1),
                direction="UP" if pct > 0.05 else "DOWN" if pct < -0.05 else "FLAT",
                current_observation_id=current.id, previous_observation_id=previous.id,
            ))
        return comparisons

    @staticmethod
    def _overall_comparisons(comparisons: list[CityPriceComparison]) -> list[CityInflationSummary]:
        """Create an equal-weight geometric basket index for each city.

        Price relatives are used instead of raw dollars so rent cannot dominate milk,
        eggs, transit, or the rest of the basket merely because its unit price is larger.
        """
        grouped: dict[str, list[CityPriceComparison]] = {}
        for comparison in comparisons:
            if comparison.previous_price_usd > 0 and comparison.current_price_usd > 0:
                grouped.setdefault(comparison.city.id, []).append(comparison)

        summaries: list[CityInflationSummary] = []
        for city_rows in grouped.values():
            log_mean = sum(
                math.log(row.current_price_usd / row.previous_price_usd)
                for row in city_rows
            ) / len(city_rows)
            ratio = math.exp(log_mean)
            inflation_pct = (ratio - 1) * 100
            summaries.append(CityInflationSummary(
                city=city_rows[0].city,
                previous_year=city_rows[0].previous_year,
                current_year=city_rows[0].current_year,
                current_index=round(ratio * 100, 2),
                inflation_pct=round(inflation_pct, 1),
                direction="UP" if inflation_pct > 0.05 else "DOWN" if inflation_pct < -0.05 else "FLAT",
                item_count=len(city_rows),
            ))
        return sorted(summaries, key=lambda row: row.city.id)

    def _find_row(self, item: TrackedItem, rows: list[ParsedPriceRow]) -> ParsedPriceRow | None:
        return next((row for row in rows if self.factory.matches(item, row.label)), None)

    @staticmethod
    def _source_catalog(collections: list[CityCollection]) -> list[SourceCatalogItem]:
        if not collections:
            return []
        reference = collections[0]
        return [SourceCatalogItem(label=row.label, example_price_usd=row.price_usd, city_id=reference.city.id) for row in reference.current_rows]
