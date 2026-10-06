from __future__ import annotations

import builtins
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any
from uuid import uuid4

from backend.db import Database
from backend.models.domain import (
    FactoryEvent,
    ItemCategory,
    ItemStatus,
    PriceNormalization,
    SourceCatalogItem,
    TrackedItem,
    TrackedItemCreate,
    ValidationCheck,
)
from backend.utils import stable_hash, write_json


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:48] or "tracked-item"


BUILTINS: list[dict[str, Any]] = [
    {"id": "rent-1br-center", "name": "1 bed · city center", "category": ItemCategory.HOUSING, "unit": "per month", "match_terms": ["Apartment (1 bedroom) in City Centre", "1 Bedroom Apartment in City Centre"], "normalizations": [("Apartment", 1.0)]},
    {"id": "milk-gallon", "name": "Milk", "category": ItemCategory.GROCERIES, "unit": "1 gallon", "match_terms": ["Milk (Regular, 1 Liter)", "Milk (regular), (1 gallon)"], "normalizations": [("1 Liter", 3.78541), ("1 gallon", 1.0)]},
    {"id": "eggs-dozen", "name": "Eggs", "category": ItemCategory.GROCERIES, "unit": "dozen", "match_terms": ["Eggs (12, Large Size)", "Eggs (regular) (12)"], "normalizations": [("Eggs", 1.0)]},
    {"id": "bread-pound", "name": "White bread", "category": ItemCategory.GROCERIES, "unit": "1 lb", "match_terms": ["Loaf of Fresh White Bread (1 lb)", "Loaf of Fresh White Bread (500g)", "Fresh White Bread (1 lb Loaf)"], "normalizations": [("500g", 0.907185), ("1 lb", 1.0)]},
    {"id": "chicken-pound", "name": "Chicken fillets", "category": ItemCategory.GROCERIES, "unit": "1 lb", "match_terms": ["Chicken Fillets (1 lb)", "Chicken Fillets (1kg)"], "normalizations": [("1kg", 0.453592), ("1 lb", 1.0)]},
    {"id": "gas-gallon", "name": "Gasoline", "category": ItemCategory.TRANSPORT, "unit": "1 gallon", "match_terms": ["Gasoline (1 gallon)", "Gasoline (1 liter)"], "normalizations": [("1 liter", 3.78541), ("1 gallon", 1.0)]},
    {"id": "transit-ticket", "name": "Local transit", "category": ItemCategory.TRANSPORT, "unit": "one-way ticket", "match_terms": ["One-way Ticket (Local Transport)"], "normalizations": [("One-way Ticket", 1.0)]},
    {"id": "cappuccino", "name": "Cappuccino", "category": ItemCategory.DINING, "unit": "regular", "match_terms": ["Cappuccino (regular)"], "normalizations": [("Cappuccino", 1.0)]},
    {"id": "apples-pound", "name": "Apples", "category": ItemCategory.GROCERIES, "unit": "1 lb", "match_terms": ["Apples (1 lb)", "Apples (1kg)"], "normalizations": [("1kg", 0.453592), ("1 lb", 1.0)]},
]


class ItemCapabilityFactory:
    """Adds and retires tracked price items without changing application code."""

    def __init__(self, db: Database, artifacts_dir: Path):
        self.db = db
        self.artifacts_dir = artifacts_dir / "item-capabilities"
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_builtins()

    def list(self, include_retired: bool = True) -> builtins.list[TrackedItem]:
        items = [TrackedItem.model_validate(row) for row in self.db.list("tracked_item", limit=250)]
        return items if include_retired else [item for item in items if item.status == ItemStatus.ACTIVE]

    def active(self) -> builtins.list[TrackedItem]:
        return self.list(include_retired=False)

    def get(self, item_id: str) -> TrackedItem:
        raw = self.db.get("tracked_item", item_id)
        if raw is None:
            raise KeyError("Tracked item not found")
        return TrackedItem.model_validate(raw)

    def create(self, request: TrackedItemCreate, catalog: builtins.list[SourceCatalogItem]) -> TrackedItem:
        normalized_label = self._normalized(request.source_label)
        duplicate = next((item for item in self.list() if normalized_label in {self._normalized(term) for term in item.match_terms}), None)
        if duplicate:
            raise ValueError(f"{request.source_label} is already tracked as {duplicate.name}")
        catalog_match = next((row for row in catalog if self._normalized(row.label) == normalized_label), None)
        checks = self._validate(request, bool(catalog_match))
        if not all(check.passed for check in checks):
            raise ValueError(next(check.detail for check in checks if not check.passed))
        slug = _slug(request.name)
        item = TrackedItem(
            id=f"item-{slug}-{uuid4().hex[:7]}", slug=slug, name=request.name,
            category=request.category, unit=request.unit, match_terms=[request.source_label],
            normalizations=[PriceNormalization(label_contains=request.source_label, multiplier=request.conversion_multiplier)],
            owner=request.owner, spec_hash=stable_hash(request, 20), validation=checks,
        )
        self._persist(item)
        self._record(item, "ACTIVATED", request.owner, "Source row validated and item tracking activated.")
        return item

    def retire(self, item_id: str, actor: str) -> TrackedItem:
        item = self.get(item_id)
        if item.status == ItemStatus.RETIRED:
            return item
        item = item.model_copy(update={"status": ItemStatus.RETIRED, "updated_at": datetime.now(timezone.utc)})
        self._persist(item)
        self._record(item, "RETIRED", actor, "Future collection disabled; historical evidence retained.")
        return item

    def restore(self, item_id: str, actor: str) -> TrackedItem:
        item = self.get(item_id).model_copy(update={"status": ItemStatus.ACTIVE, "updated_at": datetime.now(timezone.utc)})
        self._persist(item)
        self._record(item, "RESTORED", actor, "Item returned to the active collection set.")
        return item

    def events(self) -> builtins.list[FactoryEvent]:
        return [FactoryEvent.model_validate(row) for row in self.db.list("factory_event", limit=100)]

    def counts(self) -> dict[str, int]:
        items = self.list()
        return {"total": len(items), "active": sum(item.status == ItemStatus.ACTIVE for item in items), "retired": sum(item.status == ItemStatus.RETIRED for item in items)}

    @staticmethod
    def multiplier_for(item: TrackedItem, raw_label: str) -> float:
        label = raw_label.lower()
        for normalization in item.normalizations:
            if normalization.label_contains.lower() in label:
                return normalization.multiplier
        if "lb" in item.unit.lower() or "pound" in item.unit.lower():
            compact = re.sub(r"\s+", "", label)
            if "1kg" in compact:
                return 0.453592
            if "500g" in compact:
                return 0.907185
        return 1.0

    @staticmethod
    def matches(item: TrackedItem, raw_label: str) -> bool:
        normalized = ItemCapabilityFactory._normalized(raw_label)
        if any(ItemCapabilityFactory._normalized(term) in normalized for term in item.match_terms):
            return True
        if "lb" not in item.unit.lower() and "pound" not in item.unit.lower():
            return False
        raw_base = ItemCapabilityFactory._without_weight_unit(raw_label)
        return any(
            len(term_base) >= 4 and (term_base in raw_base or raw_base in term_base)
            for term in item.match_terms
            if (term_base := ItemCapabilityFactory._without_weight_unit(term))
        )

    @staticmethod
    def _normalized(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()

    @staticmethod
    def _without_weight_unit(value: str) -> str:
        normalized = ItemCapabilityFactory._normalized(value)
        return re.sub(r"\b(?:1\s*(?:lb|kg|pound)|500\s*g)\b", "", normalized).strip()

    @staticmethod
    def _validate(request: TrackedItemCreate, catalog_match: bool) -> builtins.list[ValidationCheck]:
        return [
            ValidationCheck(id="source-binding", name="Live source binding", passed=catalog_match, detail=f"Matched live source row: {request.source_label}." if catalog_match else "Choose an exact row discovered from the live city source."),
            ValidationCheck(id="normalization", name="Unit normalization", passed=0 < request.conversion_multiplier <= 100, detail=f"Multiplier {request.conversion_multiplier:g} converts the source row into {request.unit}."),
            ValidationCheck(id="ownership", name="Capability ownership", passed=bool(request.owner.strip()), detail=f"Owned by {request.owner}."),
        ]

    def _persist(self, item: TrackedItem) -> None:
        self.db.put("tracked_item", item.id, item)
        write_json(self.artifacts_dir / item.id / item.version / "manifest.json", item)

    def _record(self, item: TrackedItem, event: str, actor: str, note: str) -> None:
        record = FactoryEvent(id=f"factory-{uuid4().hex[:10]}", item_id=item.id, event=event, actor=actor, note=note)
        self.db.put("factory_event", record.id, record, parent_id=item.id)

    def _ensure_builtins(self) -> None:
        existing = self.list()
        for definition in BUILTINS:
            source_terms = {self._normalized(term) for term in definition["match_terms"]}
            if self.db.get("tracked_item", definition["id"]) or any(
                source_terms & {self._normalized(term) for term in item.match_terms}
                for item in existing
            ):
                continue
            item = TrackedItem(
                id=definition["id"], slug=definition["id"], name=definition["name"],
                category=definition["category"], unit=definition["unit"], match_terms=definition["match_terms"],
                normalizations=[PriceNormalization(label_contains=label, multiplier=multiplier) for label, multiplier in definition["normalizations"]],
                owner="inflationforge-core", spec_hash=stable_hash(definition, 20),
                validation=[ValidationCheck(id="builtin-contract", name="Built-in source contract", passed=True, detail="Versioned source labels and unit conversions are deterministic.")],
            )
            self._persist(item)
            self._record(item, "SEEDED", "system-bootstrap", "Common household item activated.")
            existing.append(item)
        self.db.set_state("inflation_builtin_items_v3_seeded", True)
