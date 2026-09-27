from datetime import datetime, timedelta, timezone

from backend.config import Settings
from backend.db import Database
from backend.models.domain import (
    CityPriceComparison,
    ItemCategory,
    ObservationKind,
    PriceNormalization,
    PriceObservation,
    TrackedItem,
    ValidationCheck,
)
from backend.services.factory import ItemCapabilityFactory
from backend.services.inflation.collector import CITY_CATALOG, CityCollection
from backend.services.inflation.service import InflationForgeService


def observation(year: int, price: float, kind: ObservationKind) -> PriceObservation:
    return PriceObservation(
        id=f"obs-{year}", snapshot_id="snapshot", city_id="san-francisco",
        item_id="milk-gallon", year=year, price_usd=price, kind=kind,
        observed_at=datetime(year, 8, 22, tzinfo=timezone.utc), source="source",
        source_url="https://example.test", raw_label="Milk", raw_price=price,
        conversion_multiplier=1,
    )


def test_city_comparison_is_deterministic():
    item = TrackedItem(
        id="milk-gallon", slug="milk-gallon", name="Milk", category=ItemCategory.GROCERIES,
        unit="1 gallon", match_terms=["Milk"],
        normalizations=[PriceNormalization(label_contains="Milk", multiplier=1)],
        spec_hash="hash", validation=[ValidationCheck(id="x", name="x", passed=True, detail="x")],
    )
    collection = CityCollection(
        city=CITY_CATALOG[0], current_rows=[], previous_rows=[], current_url="https://current.test",
        archive_url="https://archive.test", archive_timestamp="20250822000000",
    )
    comparisons = InflationForgeService._comparisons_for(
        collection, [item], [observation(2025, 5.0, ObservationKind.ARCHIVED), observation(2026, 5.5, ObservationKind.LIVE)], 2025, 2026,
    )

    assert comparisons[0].change_usd == 0.5
    assert comparisons[0].change_pct == 10.0
    assert comparisons[0].direction == "UP"


def test_overall_inflation_is_an_equal_weight_price_index():
    city = CITY_CATALOG[0]
    rows = [
        CityPriceComparison(
            city=city, item_id="rent", previous_year=2025, current_year=2026,
            previous_price_usd=100, current_price_usd=110, change_usd=10,
            change_pct=10, direction="UP", current_observation_id="rent-now",
            previous_observation_id="rent-before",
        ),
        CityPriceComparison(
            city=city, item_id="milk", previous_year=2025, current_year=2026,
            previous_price_usd=5, current_price_usd=6, change_usd=1,
            change_pct=20, direction="UP", current_observation_id="milk-now",
            previous_observation_id="milk-before",
        ),
    ]

    summary = InflationForgeService._overall_comparisons(rows)[0]

    assert summary.previous_index == 100
    assert summary.current_index == 114.89
    assert summary.inflation_pct == 14.9
    assert summary.item_count == 2
    assert summary.direction == "UP"


def test_builtin_milk_normalizes_liters_to_gallons(tmp_path):
    factory = ItemCapabilityFactory(Database(tmp_path / "db.sqlite"), tmp_path / "artifacts")
    item = factory.get("milk-gallon")

    assert round(factory.multiplier_for(item, "Milk (Regular, 1 Liter)"), 5) == 3.78541
    assert factory.multiplier_for(item, "Milk (regular), (1 gallon)") == 1


def test_recent_complete_snapshot_is_reused_for_traffic_spikes(tmp_path):
    service = InflationForgeService(Settings(
        root=tmp_path,
        db_path=tmp_path / "inflation.db",
        otel_mode="local",
        price_sync_min_interval_s=300,
    ))
    now = datetime.now(timezone.utc)
    from backend.models.domain import PriceSnapshot
    snapshot = PriceSnapshot(
        id="prices-current", current_year=now.year, previous_year=now.year - 1,
        retrieved_at=now - timedelta(seconds=30), provider_mode="TEST", content_hash="hash",
        city_count=len(CITY_CATALOG), item_count=len(service.factory.active()),
        observation_count=len(CITY_CATALOG) * len(service.factory.active()) * 2,
        comparison_count=len(CITY_CATALOG) * len(service.factory.active()),
    )

    assert service._snapshot_is_fresh(snapshot, now, len(service.factory.active()), len(CITY_CATALOG))
    assert not service._snapshot_is_fresh(snapshot, now + timedelta(minutes=6), len(service.factory.active()), len(CITY_CATALOG))
    assert not service._snapshot_is_fresh(snapshot, now, len(service.factory.active()), len(CITY_CATALOG) + 1)
