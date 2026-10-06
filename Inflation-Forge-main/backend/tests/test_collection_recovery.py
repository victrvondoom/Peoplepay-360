import asyncio
from datetime import datetime, timezone
from typing import get_type_hints

import httpx
import pytest

from backend.models.domain import TrackedItem
from backend.services.factory.items import ItemCapabilityFactory
from backend.services.inflation import collector as collector_module
from backend.services.inflation.collector import CITY_CATALOG, CityCollection, CityPriceCollector


def test_item_factory_public_annotations_resolve_after_list_method():
    assert get_type_hints(ItemCapabilityFactory.active)["return"] == list[TrackedItem]
    assert get_type_hints(ItemCapabilityFactory.list)["return"] == list[TrackedItem]


def test_cancelled_city_collection_is_propagated_not_returned_as_price_data(monkeypatch):
    cities = CITY_CATALOG[:2]
    monkeypatch.setattr(collector_module, "CITY_CATALOG", cities)
    collector = CityPriceCollector()

    async def discover():
        return False

    async def collect_city(city, previous_year):
        if city.id == cities[0].id:
            raise asyncio.CancelledError()
        return CityCollection(city, [], [], "https://example.test/current", "", "")

    monkeypatch.setattr(collector, "_discover_sources", discover)
    monkeypatch.setattr(collector, "_collect_city", collect_city)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(collector.collect(2024, 2023))


def test_previous_year_capture_on_leap_day_uses_last_valid_day(monkeypatch):
    class LeapDay(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2024, 2, 29, 12, tzinfo=timezone.utc)

    monkeypatch.setattr(collector_module, "datetime", LeapDay)
    collector = CityPriceCollector()

    async def get(client, url, params=None):
        return httpx.Response(200, json=[
            ["timestamp", "original", "statuscode"],
            ["20230228120000", "https://example.test/prices", "200"],
            ["20230301000000", "https://example.test/prices", "200"],
        ])

    monkeypatch.setattr(collector, "_get", get)

    async def capture():
        async with httpx.AsyncClient() as client:
            return await collector._closest_capture(client, "https://example.test/prices", 2023)

    assert asyncio.run(capture()) == "20230228120000"


def test_query_params_preserve_all_archive_filters():
    def handler(request):
        assert request.url.params.get_list("filter") == ["statuscode:200", "mimetype:text/html"]
        return httpx.Response(200, request=request)

    async def request():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await CityPriceCollector()._get(client, "https://example.test/archive", [
                ("filter", "statuscode:200"), ("filter", "mimetype:text/html"),
            ])

    assert asyncio.run(request()).status_code == 200
