from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)


class ItemCategory(StrEnum):
    HOUSING = "HOUSING"
    GROCERIES = "GROCERIES"
    TRANSPORT = "TRANSPORT"
    DINING = "DINING"
    UTILITIES = "UTILITIES"
    OTHER = "OTHER"


class ItemStatus(StrEnum):
    ACTIVE = "ACTIVE"
    RETIRED = "RETIRED"


class ObservationKind(StrEnum):
    LIVE = "LIVE"
    ARCHIVED = "ARCHIVED"


class ValidationCheck(StrictModel):
    id: str
    name: str
    passed: bool
    detail: str


class City(StrictModel):
    id: str
    name: str
    state: str
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    source_slug: str


class PriceNormalization(StrictModel):
    label_contains: str
    multiplier: float = Field(gt=0, le=100)


class TrackedItemCreate(StrictModel):
    name: str = Field(min_length=2, max_length=80)
    category: ItemCategory
    unit: str = Field(min_length=1, max_length=40)
    source_label: str = Field(min_length=3, max_length=180)
    conversion_multiplier: float = Field(default=1.0, gt=0, le=100)
    owner: str = Field(default="inflation-research", min_length=2, max_length=120)


class TrackedItem(StrictModel):
    id: str
    slug: str
    name: str
    category: ItemCategory
    unit: str
    match_terms: list[str]
    normalizations: list[PriceNormalization]
    source_method: str = "CITY_PRICE_TABLE"
    status: ItemStatus = ItemStatus.ACTIVE
    owner: str = "inflation-research"
    version: str = "1.0.0"
    spec_hash: str
    validation: list[ValidationCheck] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class PriceObservation(StrictModel):
    id: str
    snapshot_id: str
    city_id: str
    item_id: str
    year: int = Field(ge=2000, le=2100)
    price_usd: float = Field(gt=0)
    currency: str = "USD"
    kind: ObservationKind
    observed_at: datetime
    retrieved_at: datetime = Field(default_factory=utc_now)
    source: str
    source_url: str
    raw_label: str
    raw_price: float = Field(gt=0)
    conversion_multiplier: float = Field(gt=0)
    archive_timestamp: str | None = None


class CityPriceComparison(StrictModel):
    city: City
    item_id: str
    previous_year: int
    current_year: int
    previous_price_usd: float
    current_price_usd: float
    change_usd: float
    change_pct: float
    direction: str
    current_observation_id: str
    previous_observation_id: str


class CityInflationSummary(StrictModel):
    city: City
    previous_year: int
    current_year: int
    previous_index: float = 100.0
    current_index: float
    inflation_pct: float
    direction: str
    item_count: int


class PriceSnapshot(StrictModel):
    id: str
    current_year: int
    previous_year: int
    retrieved_at: datetime = Field(default_factory=utc_now)
    provider_mode: str
    content_hash: str
    city_count: int
    item_count: int
    observation_count: int
    comparison_count: int
    failed_cities: list[str] = Field(default_factory=list)
    source_urls: list[str] = Field(default_factory=list)
    trace_id: str = ""


class SyncJobStatus(StrEnum):
    ACCEPTED = "ACCEPTED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class PriceSyncJob(StrictModel):
    id: str
    status: SyncJobStatus = SyncJobStatus.ACCEPTED
    force: bool = True
    requested_at: datetime = Field(default_factory=utc_now)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    snapshot_id: str | None = None
    error: str | None = None


class SourceCatalogItem(StrictModel):
    label: str
    example_price_usd: float = Field(gt=0)
    city_id: str


class FactoryEvent(StrictModel):
    id: str
    item_id: str
    event: str
    actor: str
    note: str
    created_at: datetime = Field(default_factory=utc_now)


class ModeStatus(StrictModel):
    price_provider: str
    history_provider: str = "INTERNET ARCHIVE WAYBACK"
    telemetry: str
    port: str
    database: str = "SQLITE"
    map_data: str = "OPENSTREETMAP"


class InflationDashboard(StrictModel):
    product: str = "InflationForge"
    tagline: str = "See what changed. City by city. Item by item."
    current_year: int
    previous_year: int
    modes: ModeStatus
    cities: list[City]
    items: list[TrackedItem]
    snapshot: PriceSnapshot | None
    comparisons: list[CityPriceComparison]
    overall_comparisons: list[CityInflationSummary]
    source_catalog: list[SourceCatalogItem]
    factory_events: list[FactoryEvent]
    source_status: dict[str, Any]
