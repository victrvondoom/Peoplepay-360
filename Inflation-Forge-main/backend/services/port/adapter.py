from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import httpx

from backend.models.domain import CityPriceComparison, PriceSnapshot, TrackedItem


class PortAdapter(ABC):
    mode: str

    @abstractmethod
    async def sync_item(self, item: TrackedItem) -> None: ...

    @abstractmethod
    async def sync_snapshot(self, snapshot: PriceSnapshot) -> None: ...

    @abstractmethod
    async def sync_comparison(self, comparison: CityPriceComparison, snapshot_id: str) -> None: ...


class LocalPortAdapter(PortAdapter):
    mode = "LOCAL PORT EVENT LOG"

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _write(self, event: str, payload: Any) -> None:
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(), "event": event,
            "integration_mode": self.mode,
            "payload": payload.model_dump(mode="json") if hasattr(payload, "model_dump") else payload,
        }
        with self.path.open("a") as stream:
            stream.write(json.dumps(record, sort_keys=True, default=str) + "\n")

    async def sync_item(self, item: TrackedItem) -> None:
        self._write("port.inflation_item.upsert", item)

    async def sync_snapshot(self, snapshot: PriceSnapshot) -> None:
        self._write("port.inflation_snapshot.upsert", snapshot)

    async def sync_comparison(self, comparison: CityPriceComparison, snapshot_id: str) -> None:
        self._write("port.city_price_comparison.upsert", {"snapshot_id": snapshot_id, **comparison.model_dump(mode="json")})


class RemotePortAdapter(PortAdapter):
    mode = "PORT API CONFIGURED"

    def __init__(self, client_id: str, client_secret: str, api_base: str = "https://api.port.io/v1", api_token: str = ""):
        self.client_id = client_id
        self.client_secret = client_secret
        self.api_base = api_base.rstrip("/")
        self.api_token = api_token
        if api_token:
            self.mode = "PORT API TOKEN CONFIGURED"

    async def _token(self, client: httpx.AsyncClient) -> str:
        if self.api_token:
            return self.api_token
        response = await client.post(f"{self.api_base}/auth/access_token", json={"clientId": self.client_id, "clientSecret": self.client_secret})
        response.raise_for_status()
        return response.json()["accessToken"]

    async def _upsert(self, blueprint: str, identifier: str, title: str, properties: dict[str, Any], relations: dict[str, Any] | None = None) -> None:
        async with httpx.AsyncClient(timeout=20) as client:
            token = await self._token(client)
            response = await client.post(
                f"{self.api_base}/blueprints/{blueprint}/entities", params={"upsert": "true"},
                headers={"Authorization": f"Bearer {token}"},
                json={"identifier": identifier, "title": title, "properties": properties, "relations": relations or {}},
            )
            response.raise_for_status()
            self.mode = "PORT API"

    async def sync_item(self, item: TrackedItem) -> None:
        await self._upsert("inflationforge_item", item.id, f"{item.name} · {item.status}", {
            "category": item.category, "unit": item.unit, "status": item.status, "owner": item.owner,
            "version": item.version, "source_method": item.source_method,
            "spec_hash": item.spec_hash, "updated_at": item.updated_at.isoformat(),
        })

    async def sync_snapshot(self, snapshot: PriceSnapshot) -> None:
        await self._upsert("inflationforge_price_snapshot", snapshot.id, f"{snapshot.previous_year} → {snapshot.current_year}", {
            "provider_mode": snapshot.provider_mode, "current_year": snapshot.current_year,
            "previous_year": snapshot.previous_year, "city_count": snapshot.city_count,
            "item_count": snapshot.item_count, "observation_count": snapshot.observation_count,
            "comparison_count": snapshot.comparison_count, "content_hash": snapshot.content_hash,
            "trace_id": snapshot.trace_id, "retrieved_at": snapshot.retrieved_at.isoformat(),
        })

    async def sync_comparison(self, comparison: CityPriceComparison, snapshot_id: str) -> None:
        identifier = f"{snapshot_id}-{comparison.city.id}-{comparison.item_id}"
        await self._upsert("inflationforge_city_comparison", identifier, f"{comparison.city.name} · {comparison.item_id}", {
            "city": comparison.city.name, "state": comparison.city.state,
            "item_id": comparison.item_id, "previous_price_usd": comparison.previous_price_usd,
            "current_price_usd": comparison.current_price_usd, "change_pct": comparison.change_pct,
            "direction": comparison.direction,
        }, {"snapshot": snapshot_id, "item": comparison.item_id})
