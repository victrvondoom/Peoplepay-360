from pathlib import Path

import pytest

from backend.db import Database
from backend.models.domain import ItemCategory, SourceCatalogItem, TrackedItemCreate
from backend.services.factory import ItemCapabilityFactory


@pytest.fixture
def factory(tmp_path: Path) -> ItemCapabilityFactory:
    return ItemCapabilityFactory(Database(tmp_path / "inflation.db"), tmp_path / "artifacts")


def test_factory_seeds_common_household_items(factory: ItemCapabilityFactory):
    active_ids = {item.id for item in factory.active()}

    assert {"rent-1br-center", "milk-gallon", "eggs-dozen", "gas-gallon", "apples-pound"} <= active_ids


def test_factory_adds_discovered_item_without_code_change(factory: ItemCapabilityFactory):
    catalog = [SourceCatalogItem(label="Banana (1 lb)", example_price_usd=0.92, city_id="san-francisco")]
    item = factory.create(
        TrackedItemCreate(
            name="Bananas", category=ItemCategory.GROCERIES, unit="1 lb",
            source_label="Banana (1 lb)", conversion_multiplier=1,
        ),
        catalog,
    )

    assert item.status == "ACTIVE"
    assert all(check.passed for check in item.validation)
    assert (factory.artifacts_dir / item.id / item.version / "manifest.json").exists()
    assert factory.matches(item, "Banana (1kg)")
    assert factory.multiplier_for(item, "Banana (1kg)") == 0.453592


def test_factory_rejects_unverified_source_binding(factory: ItemCapabilityFactory):
    with pytest.raises(ValueError, match="exact row"):
        factory.create(
            TrackedItemCreate(
                name="Imaginary basket", category=ItemCategory.OTHER, unit="each",
                source_label="Not present in source", conversion_multiplier=1,
            ),
            [],
        )


def test_retire_preserves_item_and_restore_reactivates(factory: ItemCapabilityFactory):
    retired = factory.retire("milk-gallon", "research-lead")
    assert retired.status == "RETIRED"
    assert factory.get("milk-gallon").status == "RETIRED"

    restored = factory.restore("milk-gallon", "research-lead")
    assert restored.status == "ACTIVE"
