"""
main.py
-------
GreenChain API.

Endpoints:
  POST /search             — run Dedalus agents + ML scoring, return full JSON
  POST /search/stream      — same search, streamed as Server-Sent Events with
                             per-component progress
  POST /rescore-transport  — reprice transport mode server-side
  POST /score              — score pre-collected candidates (skip the agent)
  GET  /health             — liveness probe

Run:
  cd .. && uvicorn backend.main:app --reload --port 8000
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import os
import time
from collections.abc import AsyncIterator, Coroutine
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from . import machine_host
from .agents import DEFAULT_MODEL, run_supply_chain_research
from .db import audit_search, cache_get, cache_put, init_db
from .ml_scorer import compute_composite_scores, parse_agent_output
from .naics_classifier import NaicsMatch, classify_naics, lookup_naics
from .report_generation import (
    ReportGenerationConfigError,
    ReportGenerationProviderError,
    ScenarioReportRequestPayload,
    ScenarioReportResponsePayload,
    generate_scenario_report_with_gemini,
)
from .scenario_editing import (
    ScenarioEditConfigError,
    ScenarioEditProviderError,
    ScenarioEditRequestPayload,
    ScenarioEditResponsePayload,
    ScenarioEditValidationError,
    edit_scenario_with_k2,
    normalize_edited_scenario,
)
from .transport import rescore_transport
from .tools import (
    calculate_transport_emissions,
    lookup_emission_factor,
    score_certifications,
)

logger = logging.getLogger(__name__)
MIN_COMPONENT_ALTERNATIVES = 1
MAX_COMPONENT_SEARCH_ATTEMPTS = 3
SEARCH_HEARTBEAT_SECONDS = 15.0
DISCOVERY_CACHE_VERSION = "v1"
TRANSPORT_MODES = ("sea", "air", "rail", "road")
WEIGHT_KEYS = ("manufacturing", "transport", "grid_carbon", "certifications", "climate_risk")
DISCLOSURE_STATUSES = ("verified", "partial", "none")

load_dotenv(Path(__file__).parent / ".env")


def _allow_mock_component_search() -> bool:
    v = os.environ.get("GREENCHAIN_ALLOW_MOCK_COMPONENT_SEARCH", "").strip().lower()
    return v in ("1", "true", "yes")


def _missing_component_agent_keys() -> list[str]:
    return [
        key
        for key in ("DEDALUS_API_KEY", "ANTHROPIC_API_KEY", "BRAVE_API_KEY")
        if not os.environ.get(key, "").strip()
    ]


def _should_fallback_component_search(exc: BaseException) -> bool:
    if _allow_mock_component_search():
        return True

    if isinstance(exc, ModuleNotFoundError) and "dedalus" in str(exc).lower():
        return True

    if _missing_component_agent_keys():
        return True

    return False


def _warn_if_dedalus_sdk_missing() -> None:
    """The `dedalus-labs` pip package is required for /search; missing installs cause ModuleNotFoundError."""
    try:
        import dedalus_labs  # noqa: F401
    except ModuleNotFoundError:
        print(
            "[startup] dedalus_labs is not installed — /search will fail until you install deps in "
            "the SAME venv that runs uvicorn, e.g.\n"
            "  cd backend && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt",
            flush=True,
        )


def _component_search_failure_detail(exc: BaseException) -> str:
    base = f"Component agent pipeline failed ({type(exc).__name__}: {exc})."
    if isinstance(exc, ModuleNotFoundError) and "dedalus" in str(exc).lower():
        return (
            f"{base} Install the Dedalus SDK in the Python environment that runs the API: "
            "`cd backend && source .venv/bin/activate && pip install -r requirements.txt` "
            "(package name: dedalus-labs). Then restart uvicorn."
        )
    return (
        f"{base} Configure DEDALUS_API_KEY, ANTHROPIC_API_KEY, and BRAVE_API_KEY in "
        "backend/.env and check the backend terminal for the full traceback. "
        "Set GREENCHAIN_ALLOW_MOCK_COMPONENT_SEARCH=1 only for offline demos without real agent keys."
    )


def _warn_if_search_tools_misconfigured() -> None:
    """Log once at startup — most 'always mock data' reports are missing API keys."""
    if not os.environ.get("BRAVE_API_KEY", "").strip():
        print(
            "[startup] BRAVE_API_KEY is not set — web_search returns {\"error\": ...} "
            "to the agent (no real manufacturer discovery).",
            flush=True,
        )
    if not os.environ.get("DEDALUS_API_KEY", "").strip():
        print(
            "[startup] DEDALUS_API_KEY is not set — Dedalus runs will fail unless "
            "the SDK sources credentials another way.",
            flush=True,
        )
    if not os.environ.get("ANTHROPIC_API_KEY", "").strip():
        print(
            "[startup] ANTHROPIC_API_KEY is not set — Claude calls via Dedalus may fail.",
            flush=True,
        )
    if not os.environ.get("GEMINI_API_KEY", "").strip():
        print(
            "[startup] GEMINI_API_KEY is not set — downloadable report generation will fail.",
            flush=True,
        )


def _startup() -> None:
    init_db()
    _warn_if_dedalus_sdk_missing()
    _warn_if_search_tools_misconfigured()
    # Prime the XGBoost models so the first /search doesn't pay the model load.
    try:
        from .ml_bridge import get_emissions_model
        get_emissions_model()
    except Exception as exc:  # noqa: BLE001
        print(f"[startup] EmissionsModel preload failed: {exc}")
    # Provision the Dedalus Machine used by fetch_url (no-op unless the flag is set).
    machine_host.init_machine()


def _shutdown() -> None:
    machine_host.destroy_machine()


@asynccontextmanager
async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
    _startup()
    try:
        yield
    finally:
        _shutdown()


app = FastAPI(
    title="GreenChain API",
    version="0.2.0",
    description=(
        "Environmental supply chain comparator. Submit a product + source "
        "countries + transport mode; get a ranked list of real manufacturers "
        "scored across 5 environmental dimensions."
    ),
    lifespan=_lifespan,
)

# CORS open for hackathon — tighten for prod.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
#  Request / response models
# ---------------------------------------------------------------------------


def _normalise_transport_mode(value: str) -> str:
    mode = (value or "").strip().lower()
    if mode not in TRANSPORT_MODES:
        raise ValueError(f"transport mode must be one of: {', '.join(TRANSPORT_MODES)}.")
    return mode


def _normalise_weights(value: dict[str, float] | None) -> dict[str, float] | None:
    """Validate a weight override; missing dimensions default to 0."""
    if value is None:
        return None
    unknown = sorted(set(value) - set(WEIGHT_KEYS))
    if unknown:
        raise ValueError(
            f"Unknown weight key(s): {', '.join(unknown)}. "
            f"Expected any of: {', '.join(WEIGHT_KEYS)}."
        )
    weights = {key: float(value.get(key, 0.0)) for key in WEIGHT_KEYS}
    if any(not math.isfinite(weight) or weight < 0 for weight in weights.values()):
        raise ValueError("Weights must be non-negative numbers.")
    if sum(weights.values()) <= 0:
        raise ValueError("At least one weight must be greater than zero.")
    return weights


class SearchRequest(BaseModel):
    product: str = Field(
        ...,
        description="Product name, e.g. 'cotton t-shirts' or the parent product for a scenario search",
    )
    quantity: int = Field(..., ge=1, description="Unit count")
    destination: str = Field(..., description="ISO country code of final destination")
    components: list["ScenarioComponentRequest"] = Field(
        default_factory=list,
        description=(
            "Optional component rows for a multi-component scenario search. "
            "When present, the backend scores each current supplier plus global "
            "alternatives for that component."
        ),
    )
    countries: list[str] = Field(
        default_factory=list,
        description=(
            "ISO country codes to source from. Leave empty for a GLOBAL search "
            "where the agent picks the best countries itself."
        ),
    )
    transport_mode: str = Field("sea", description="sea | air | rail | road")
    require_certifications: list[str] = Field(
        default_factory=list,
        description="Optional filter: require at least one of these certs",
    )
    target_count: int | None = Field(
        None,
        ge=1,
        le=30,
        description=(
            "Optional manufacturer count. In per-country mode, splits across "
            "the country list (min 1 each). In global mode, total worldwide. "
            "Defaults: 5/country (per-country), 6 (global). When `components` "
            "is present this applies per component."
        ),
    )
    weights: dict[str, float] | None = Field(
        None,
        description=(
            "Optional override for dimension weights "
            "(manufacturing, transport, grid_carbon, certifications, climate_risk). "
            "Non-negative; normalised to sum to 1."
        ),
    )
    use_cache: bool = Field(
        True,
        description=(
            "Reuse agent discovery results cached within "
            "GREENCHAIN_DISCOVERY_CACHE_TTL_HOURS (default 24h). Scores are "
            "always recomputed."
        ),
    )

    @field_validator("transport_mode")
    @classmethod
    def _check_transport_mode(cls, value: str) -> str:
        return _normalise_transport_mode(value)

    @field_validator("destination")
    @classmethod
    def _check_destination(cls, value: str) -> str:
        code = value.strip().upper()
        if not code:
            raise ValueError("destination is required.")
        return code

    @field_validator("weights")
    @classmethod
    def _check_weights(cls, value: dict[str, float] | None) -> dict[str, float] | None:
        return _normalise_weights(value)


class ScenarioComponentRequest(BaseModel):
    component: str = Field(..., description="Component or material label, e.g. 'adhesive'")
    current_manufacturer: str = Field(..., description="Current supplier name")
    current_country: str = Field(..., description="ISO country code of the current supplier")
    current_city: str | None = Field(
        None,
        description="Optional city of the current supplier",
    )
    current_website: str | None = Field(
        None,
        description="Optional website or sustainability page URL",
    )
    current_certifications: list[str] = Field(
        default_factory=list,
        description="Known certifications for the current supplier",
    )
    current_disclosure_status: str = Field(
        "none",
        description="verified | partial | none",
    )
    current_revenue_usd_m: float | None = Field(
        None,
        ge=0.01,
        description="Optional annual revenue estimate in USD millions",
    )
    current_renewable_pct: float | None = Field(
        None,
        ge=0,
        le=100,
        description="Optional renewable energy percentage for the current supplier",
    )

    @field_validator("current_country")
    @classmethod
    def _check_current_country(cls, value: str) -> str:
        code = value.strip().upper()
        if len(code) != 2 or not code.isalpha():
            raise ValueError("current_country must be an ISO-2 country code, e.g. 'CN'.")
        return code


SearchRequest.model_rebuild()

class SearchResponse(BaseModel):
    product: str
    destination: str
    transport_mode: str
    countries: list[str]
    duration_seconds: float
    count: int
    results: list[dict[str, Any]]
    cache_hits: int = Field(
        0, description="Number of components whose discovery came from the cache."
    )
    fallback_components: list[str] = Field(
        default_factory=list,
        description="Components that used offline placeholder manufacturers.",
    )


class RescoreRequest(BaseModel):
    manufacturers: list[dict[str, Any]]
    mode: str

    @field_validator("mode")
    @classmethod
    def _check_mode(cls, value: str) -> str:
        return _normalise_transport_mode(value)


class ScoreRequest(BaseModel):
    """Run ML scoring on candidates you've already collected elsewhere."""
    manufacturers: list[dict[str, Any]]
    transport_mode: str = "sea"
    weights: dict[str, float] | None = None

    @field_validator("transport_mode")
    @classmethod
    def _check_transport_mode(cls, value: str) -> str:
        return _normalise_transport_mode(value)

    @field_validator("weights")
    @classmethod
    def _check_weights(cls, value: dict[str, float] | None) -> dict[str, float] | None:
        return _normalise_weights(value)


# ---------------------------------------------------------------------------
#  Search errors and outcomes
# ---------------------------------------------------------------------------


class SearchError(RuntimeError):
    """A search failure with the HTTP status it should surface as."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


@dataclass
class _SearchOutcome:
    results: list[dict[str, Any]]
    cached: bool
    used_fallback: bool


# ---------------------------------------------------------------------------
#  Manufacturer helpers
# ---------------------------------------------------------------------------


def _normalise_name(value: str) -> str:
    return " ".join((value or "").strip().lower().split())


def _dedupe_manufacturers(manufacturers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    deduped: list[dict[str, Any]] = []

    for manufacturer in manufacturers:
        key = (
            _normalise_name(str(manufacturer.get("name") or "")),
            str(manufacturer.get("country") or "").strip().upper(),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(manufacturer)

    return deduped


def _shipment_weight_kg(quantity: int, component_count: int = 1) -> float:
    # 0.5 kg/unit is a reasonable default for mixed hardgoods, split evenly
    # across the components of a multi-component scenario.
    return max(1.0, float(quantity) * 0.5 / max(component_count, 1))


def _bounded_number(value: Any, *, default: float, low: float, high: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(number):
        return default
    return min(max(number, low), high)


def _industry_for(raw: dict[str, Any], default: NaicsMatch) -> NaicsMatch:
    """Use the agent's NAICS code when it names a real USEEIO industry."""
    emission_factor = raw.get("emission_factor")
    if isinstance(emission_factor, dict):
        agent_code = emission_factor.get("naics4") or emission_factor.get("naics_code")
        agent_match = lookup_naics(str(agent_code or ""))
        if agent_match is not None:
            return agent_match
    return default


def _enrich_manufacturer(
    raw: dict[str, Any],
    *,
    destination: str,
    transport_mode: str,
    weight_kg: float,
    industry: NaicsMatch,
) -> dict[str, Any] | None:
    """
    Recompute every derived field of a discovered manufacturer.

    The agent is trusted only for facts it found (name, country, city, URL,
    certifications, disclosure status, optional revenue/NAICS hints).
    Emissions, transport, and certification scores are recomputed here so
    results are reproducible, cacheable, and never depend on tool output the
    agent might have skipped or garbled. Returns None for records without a
    usable name or ISO-2 country.
    """
    name = str(raw.get("name") or "").strip()
    country = str(raw.get("country") or "").strip().upper()
    if not name or len(country) != 2 or not country.isalpha():
        return None

    emission_hints = raw.get("emission_factor")
    if not isinstance(emission_hints, dict):
        emission_hints = {}
    revenue_usd_m = _bounded_number(
        emission_hints.get("revenue_usd_m"), default=25.0, low=0.1, high=1_000_000.0
    )
    renewable_pct = _bounded_number(
        emission_hints.get("renewable_pct"), default=0.0, low=0.0, high=1.0
    )
    certifications = [
        str(cert).strip()
        for cert in (raw.get("certifications") or [])
        if str(cert or "").strip()
    ]
    disclosure = str(raw.get("disclosure_status") or "none").strip().lower()
    industry_match = _industry_for(raw, industry)

    return {
        **raw,
        "name": name,
        "country": country,
        "certifications": certifications,
        "disclosure_status": disclosure if disclosure in DISCLOSURE_STATUSES else "none",
        "industry": industry_match.as_dict(),
        "emission_factor": lookup_emission_factor(
            naics_code=industry_match.code,
            country_iso=country,
            revenue_usd_m=revenue_usd_m,
            year=2023,
            renewable_pct=renewable_pct,
        ),
        "transport": calculate_transport_emissions(
            origin_country=country,
            destination_country=destination,
            weight_kg=weight_kg,
            mode=transport_mode,
        ),
        "cert_score": score_certifications(certifications),
    }


def _current_manufacturer_facts(component: ScenarioComponentRequest) -> dict[str, Any]:
    renewable_pct = (
        float(component.current_renewable_pct) / 100.0
        if component.current_renewable_pct is not None
        else 0.0
    )
    return {
        "name": component.current_manufacturer,
        "country": component.current_country,
        "city": component.current_city,
        "sustainability_url": component.current_website,
        "certifications": component.current_certifications,
        "disclosure_status": component.current_disclosure_status,
        "emission_factor": {
            "revenue_usd_m": component.current_revenue_usd_m or 25.0,
            "renewable_pct": renewable_pct,
        },
        "component": component.component,
        "is_current": True,
    }


def _fallback_alternatives(
    req: SearchRequest, component: ScenarioComponentRequest
) -> list[dict[str, Any]]:
    """Offline placeholder manufacturers (names are clearly synthetic)."""
    excluded = {component.current_country, req.destination}
    countries = [
        code
        for code in ("VN", "MX", "PT", "PL", "TR", "IN", "ID", "TH")
        if code not in excluded
    ]
    count = max(2, min(req.target_count or 3, 4))
    return [
        {
            "name": f"{component.component.title()} Collective {country}",
            "country": country,
            "city": None,
            "sustainability_url": None,
            "certifications": ["iso14001"] if index % 2 == 0 else ["sbt_committed"],
            "disclosure_status": "partial",
            "component": component.component,
            "is_current": False,
        }
        for index, country in enumerate(countries[:count])
    ]


# ---------------------------------------------------------------------------
#  Discovery cache
# ---------------------------------------------------------------------------


def _discovery_cache_key(**params: Any) -> str:
    payload = json.dumps(
        {"version": DISCOVERY_CACHE_VERSION, "model": DEFAULT_MODEL, **params},
        sort_keys=True,
        separators=(",", ":"),
    )
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _cache_read(cache_key: str) -> list[dict[str, Any]] | None:
    try:
        payload = cache_get(cache_key)
    except Exception as exc:  # noqa: BLE001
        logger.warning("discovery cache read failed: %s", exc)
        return None
    if not payload:
        return None
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, list):
        return None
    manufacturers = [item for item in data if isinstance(item, dict)]
    return manufacturers or None


def _cache_write(cache_key: str, manufacturers: list[dict[str, Any]]) -> None:
    try:
        cache_put(cache_key, json.dumps(manufacturers, separators=(",", ":")))
    except Exception as exc:  # noqa: BLE001
        logger.warning("discovery cache write failed: %s", exc)


def _certification_filter_key(certifications: list[str]) -> list[str]:
    return sorted({cert.strip().lower() for cert in certifications if cert.strip()})


# ---------------------------------------------------------------------------
#  Search pipeline
# ---------------------------------------------------------------------------


async def _discover_component_alternatives(
    req: SearchRequest,
    component: ScenarioComponentRequest,
    component_count: int,
) -> tuple[list[dict[str, Any]], bool]:
    """Agent discovery of alternates for one component. Returns (alternatives, from_cache)."""
    incumbent_name = component.current_manufacturer.strip()
    incumbent_country = component.current_country
    target_count = max(req.target_count or 6, 6)
    cache_key = _discovery_cache_key(
        kind="component",
        component=_normalise_name(component.component),
        product_context=_normalise_name(req.product),
        incumbent=_normalise_name(incumbent_name),
        incumbent_country=incumbent_country,
        require_certifications=_certification_filter_key(req.require_certifications),
        target_count=target_count,
    )
    if req.use_cache:
        cached = _cache_read(cache_key)
        if cached is not None:
            return cached, True

    shipment_weight_kg = _shipment_weight_kg(req.quantity, component_count)
    alternatives: list[dict[str, Any]] = []

    for attempt in range(1, MAX_COMPONENT_SEARCH_ATTEMPTS + 1):
        retry_guidance = ""
        if attempt > 1:
            retry_guidance = (
                f"This is retry attempt {attempt}. The previous search returned "
                f"{len(alternatives)} usable alternatives. Broaden geography and "
                "query wording, and keep searching until you find distinct alternatives."
            )

        raw_output = await run_supply_chain_research(
            product=component.component,
            product_context=req.product,
            quantity=req.quantity,
            countries=[],
            destination=req.destination,
            transport_mode=req.transport_mode,
            require_certifications=req.require_certifications or None,
            shipment_weight_kg=shipment_weight_kg,
            target_count=target_count,
            current_manufacturer=incumbent_name,
            min_alternatives=MIN_COMPONENT_ALTERNATIVES,
            retry_guidance=retry_guidance,
        )

        parsed_alternatives: list[dict[str, Any]] = []
        for manufacturer in parse_agent_output(raw_output):
            if not isinstance(manufacturer, dict):
                continue
            manufacturer_name = str(manufacturer.get("name") or "").strip()
            manufacturer_country = str(manufacturer.get("country") or "").strip().upper()
            if (
                manufacturer_name.lower() == incumbent_name.lower()
                and manufacturer_country == incumbent_country
            ):
                continue

            parsed_alternatives.append(
                {
                    **manufacturer,
                    "component": component.component,
                    "is_current": False,
                }
            )

        alternatives = _dedupe_manufacturers(parsed_alternatives)
        if len(alternatives) >= MIN_COMPONENT_ALTERNATIVES:
            break

        logger.warning(
            "component_search returned too few alternatives; retrying",
            extra={
                "component": component.component,
                "attempt": attempt,
                "alternatives": len(alternatives),
            },
        )

    if alternatives:
        _cache_write(cache_key, alternatives)
    return alternatives, False


def _score_manufacturers(
    manufacturers: list[dict[str, Any]], req: SearchRequest, label: str
) -> list[dict[str, Any]]:
    try:
        return compute_composite_scores(
            manufacturers,
            transport_mode=req.transport_mode,
            weights=req.weights,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("scoring failed for %s", label)
        raise SearchError(
            500, f"Scoring failed for {label!r}: {type(exc).__name__}: {exc}"
        ) from exc


async def _search_component(
    req: SearchRequest,
    component: ScenarioComponentRequest,
    component_count: int,
) -> _SearchOutcome:
    try:
        alternatives, from_cache = await _discover_component_alternatives(
            req, component, component_count
        )
        used_fallback = False
    except Exception as exc:  # noqa: BLE001
        if not _should_fallback_component_search(exc):
            logger.exception("component_search failed for %s", component.component)
            raise SearchError(502, _component_search_failure_detail(exc)) from exc
        # Expected when agent keys are missing or mock mode is on: the one-line
        # message below explains it, so no traceback.
        reason = f"{type(exc).__name__}: {exc}"
        missing_keys = _missing_component_agent_keys()
        if missing_keys:
            reason = f"{reason}; missing keys: {', '.join(missing_keys)}"
        print(
            f"[component_search] using mock manufacturers for {component.component!r} ({reason}).",
            flush=True,
        )
        alternatives = _fallback_alternatives(req, component)
        from_cache, used_fallback = False, True

    industry = classify_naics(component.component)
    weight_kg = _shipment_weight_kg(req.quantity, component_count)
    enriched = [
        record
        for record in (
            _enrich_manufacturer(
                raw,
                destination=req.destination,
                transport_mode=req.transport_mode,
                weight_kg=weight_kg,
                industry=industry,
            )
            for raw in [_current_manufacturer_facts(component), *alternatives]
        )
        if record is not None
    ]
    scored = _score_manufacturers(
        _dedupe_manufacturers(enriched), req, component.component
    )
    return _SearchOutcome(results=scored, cached=from_cache, used_fallback=used_fallback)


async def _search_product(req: SearchRequest) -> _SearchOutcome:
    """Single-product search (per-country or global), without component rows."""
    countries = sorted({code.strip().upper() for code in req.countries if code.strip()})
    cache_key = _discovery_cache_key(
        kind="product",
        product=_normalise_name(req.product),
        countries=countries,
        require_certifications=_certification_filter_key(req.require_certifications),
        target_count=req.target_count,
    )
    manufacturers = _cache_read(cache_key) if req.use_cache else None
    from_cache = manufacturers is not None

    if manufacturers is None:
        try:
            raw_output = await run_supply_chain_research(
                product=req.product,
                quantity=req.quantity,
                countries=req.countries,
                destination=req.destination,
                transport_mode=req.transport_mode,
                require_certifications=req.require_certifications or None,
                target_count=req.target_count,
            )
        except Exception as exc:  # noqa: BLE001
            raise SearchError(
                502, f"Agent call failed: {type(exc).__name__}: {exc}"
            ) from exc
        manufacturers = _dedupe_manufacturers(
            [item for item in parse_agent_output(raw_output) if isinstance(item, dict)]
        )
        if manufacturers:
            _cache_write(cache_key, manufacturers)

    industry = classify_naics(req.product)
    weight_kg = _shipment_weight_kg(req.quantity)
    enriched = [
        record
        for record in (
            _enrich_manufacturer(
                raw,
                destination=req.destination,
                transport_mode=req.transport_mode,
                weight_kg=weight_kg,
                industry=industry,
            )
            for raw in manufacturers
        )
        if record is not None
    ]
    scored = _score_manufacturers(_dedupe_manufacturers(enriched), req, req.product)
    return _SearchOutcome(results=scored, cached=from_cache, used_fallback=False)


def _audit(req: SearchRequest, duration: float, result_count: int) -> None:
    try:
        audit_search(
            product=req.product,
            countries=[] if req.components else req.countries,
            transport_mode=req.transport_mode,
            destination=req.destination,
            duration_seconds=duration,
            result_count=result_count,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[audit_search] non-fatal failure: {exc}")


async def _iter_search(req: SearchRequest) -> AsyncIterator[dict[str, Any]]:
    """
    Run a search and yield progress events:

      {"type": "started",   "total", "components"}
      {"type": "heartbeat", "elapsed_seconds"}              (while waiting)
      {"type": "component", "index", "component", "completed", "total",
                            "count", "cached", "fallback", "elapsed_seconds",
                            "results"}  (that component's scored manufacturers)
      {"type": "complete",  "response": SearchResponse}

    Components run concurrently and are reported as each one finishes.
    Raises SearchError if any component fails without a fallback.
    """
    start = time.monotonic()
    if req.components:
        labels = [component.component for component in req.components]
        jobs: list[Coroutine[Any, Any, _SearchOutcome]] = [
            _search_component(req, component, len(labels))
            for component in req.components
        ]
    else:
        labels = [req.product]
        jobs = [_search_product(req)]

    total = len(labels)
    tasks = {asyncio.create_task(job): index for index, job in enumerate(jobs)}
    outcomes: dict[int, _SearchOutcome] = {}
    pending = set(tasks)

    try:
        yield {"type": "started", "total": total, "components": labels}

        while pending:
            done, pending = await asyncio.wait(
                pending,
                timeout=SEARCH_HEARTBEAT_SECONDS,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if not done:
                yield {
                    "type": "heartbeat",
                    "elapsed_seconds": round(time.monotonic() - start, 1),
                }
                continue

            for task in sorted(done, key=lambda item: tasks[item]):
                index = tasks[task]
                outcome = task.result()
                outcomes[index] = outcome
                yield {
                    "type": "component",
                    "index": index,
                    "component": labels[index],
                    "completed": len(outcomes),
                    "total": total,
                    "count": len(outcome.results),
                    "cached": outcome.cached,
                    "fallback": outcome.used_fallback,
                    "elapsed_seconds": round(time.monotonic() - start, 1),
                    # Lets clients render this component before the rest finish.
                    "results": outcome.results,
                }
    finally:
        # Cancel whatever is still running (client disconnect or a failed
        # sibling) and mark finished tasks' exceptions as retrieved. No awaits
        # here: this also runs while the surrounding task is being cancelled.
        for task in tasks:
            if not task.done():
                task.cancel()
            elif not task.cancelled():
                task.exception()

    ordered = [outcomes[index] for index in range(total)]
    results = [result for outcome in ordered for result in outcome.results]
    duration = round(time.monotonic() - start, 2)
    _audit(req, duration, len(results))

    yield {
        "type": "complete",
        "response": SearchResponse(
            product=req.product,
            destination=req.destination,
            transport_mode=req.transport_mode,
            countries=[] if req.components else req.countries,
            duration_seconds=duration,
            count=len(results),
            results=results,
            cache_hits=sum(1 for outcome in ordered if outcome.cached),
            fallback_components=[
                labels[index]
                for index, outcome in enumerate(ordered)
                if outcome.used_fallback
            ],
        ),
    }


def _sse(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(jsonable_encoder(event), separators=(',', ':'))}\n\n"


# ---------------------------------------------------------------------------
#  Routes
# ---------------------------------------------------------------------------


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/search", response_model=SearchResponse)
async def search(req: SearchRequest) -> SearchResponse:
    """Run the Dedalus agent + ML scoring pipeline and return the full result."""
    response: SearchResponse | None = None
    try:
        async for event in _iter_search(req):
            if event["type"] == "complete":
                response = event["response"]
    except SearchError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    if response is None:
        raise HTTPException(status_code=500, detail="Search finished without a result.")
    return response


@app.post("/search/stream")
async def search_stream(req: SearchRequest) -> StreamingResponse:
    """
    Same pipeline as /search, streamed as Server-Sent Events. Each event is a
    JSON object on a `data:` line (see `_iter_search` for event types); a
    failure is reported as {"type": "error", "status", "detail"}.
    """

    async def events() -> AsyncIterator[str]:
        try:
            async for event in _iter_search(req):
                yield _sse(event)
        except SearchError as exc:
            yield _sse({"type": "error", "status": exc.status_code, "detail": exc.detail})
        except Exception as exc:  # noqa: BLE001
            logger.exception("search stream failed")
            yield _sse(
                {
                    "type": "error",
                    "status": 500,
                    "detail": f"Search failed: {type(exc).__name__}: {exc}",
                }
            )

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/score")
async def score(req: ScoreRequest) -> dict[str, Any]:
    """
    Score a pre-collected candidate list — useful for testing the ML layer
    without paying for an agent call.

    Each candidate must carry at minimum `name`, `country`, `certifications`,
    `emission_factor`, and `transport`. See /search response for the full shape.
    """
    try:
        scored = compute_composite_scores(
            req.manufacturers,
            transport_mode=req.transport_mode,
            weights=req.weights,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail=f"Scoring failed: {type(exc).__name__}: {exc}",
        )
    return {"count": len(scored), "results": scored}


@app.post("/rescore-transport")
async def rescore_transport_endpoint(req: RescoreRequest) -> dict[str, Any]:
    """Recompute transport emissions for the given manufacturers under a new mode."""
    rescored = rescore_transport(req.manufacturers, req.mode)
    rescored.sort(key=lambda x: x.get("scores", {}).get("total_tco2e", float("inf")))
    for i, m in enumerate(rescored, 1):
        m["rank"] = i
    return {"count": len(rescored), "mode": req.mode, "results": rescored}


@app.post("/scenario/edit", response_model=ScenarioEditResponsePayload)
async def edit_scenario_endpoint(
    req: ScenarioEditRequestPayload,
) -> ScenarioEditResponsePayload:
    """Apply a safe, non-structural prompt edit to the current scenario JSON."""
    prompt = req.prompt.strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="Prompt cannot be empty.")

    try:
        model_response = await edit_scenario_with_k2(prompt, req.scenario)
    except ScenarioEditConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ScenarioEditProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if model_response.status == "rejected":
        return model_response

    if model_response.scenario is None:
        return ScenarioEditResponsePayload(
            status="rejected",
            message=(
                "The edit model returned an applied response without a scenario payload."
            ),
        )

    try:
        normalized = normalize_edited_scenario(req.scenario, model_response.scenario)
    except ScenarioEditValidationError as exc:
        return ScenarioEditResponsePayload(status="rejected", message=str(exc))

    return ScenarioEditResponsePayload(
        status="applied",
        message=model_response.message,
        scenario=normalized,
    )


@app.post("/scenario/report", response_model=ScenarioReportResponsePayload)
async def generate_scenario_report_endpoint(
    req: ScenarioReportRequestPayload,
) -> ScenarioReportResponsePayload:
    """Generate a downloadable LaTeX-backed report for the scenario."""
    try:
        return await generate_scenario_report_with_gemini(
            req.scenario,
            selected_by_component=req.selectedManufacturerByComponent,
            scoring=req.scoring,
        )
    except ReportGenerationConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ReportGenerationProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
