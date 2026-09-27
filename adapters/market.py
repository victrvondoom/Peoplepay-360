"""Market / price evidence, fronting InflationForge (spec Sec. 11, Sec. 12).

InflationForge is a real, running system: it collects city price observations,
keeps the source receipt for each one, and distinguishes a live reading from an
Internet Archive reading.  This adapter uses those real endpoints:

    GET /health                                 -> provider modes
    GET /api/dashboard                          -> items, cities, comparisons
    GET /api/snapshots/{snapshot_id}/observations

Two things this adapter must be honest about, both found during the audit:

**1. InflationForge stores money as a float** (``price_usd: float``).  Beacon's
``Money`` rejects floats at construction, deliberately, because precision is
already lost by then.  We convert via ``Decimal(str(value))`` -- the only
lossless route out of a float -- and attach a note saying the value arrived as
a float.  We never pretend the original was exact.

**2. Its scope is a city basket, not a product catalogue.**  It tracks rent,
milk, eggs, bread, chicken, gas, transit, coffee and apples across US cities in
USD.  It therefore cannot price an iPhone, and asking it to would be the
fabrication the spec forbids.  When the requested item is not a tracked item,
this adapter returns ``UNAVAILABLE`` for that field -- an honest miss, not a
guess.  Product-level pricing comes from the commerce capability instead.
"""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from beacon.assurance.evidence import EvidenceClass, Observation, content_hash
from beacon.assurance.money import Money

from adapters.base import Capability, CapabilityMode, CapabilityResult, HealthReport

__all__ = ["MarketAdapter", "PriceAssessment", "money_from_float"]


#: How the upstream's own observation kind maps onto our evidence classes.
#: ARCHIVED is genuinely older data, so it is STALE rather than VERIFIED.
_KIND_TO_CLASS = {
    "LIVE": EvidenceClass.VERIFIED,
    "ARCHIVED": EvidenceClass.STALE,
}


def money_from_float(value: float | int | str, currency: str) -> tuple[Money, str]:
    """Convert an upstream float price into exact ``Money``.

    Returns the money *and* a note recording that the value crossed a float
    boundary, so the provenance keeps that fact instead of hiding it.

    ``Decimal(str(x))`` is used rather than ``Decimal(x)``: the former takes the
    shortest decimal representation that round-trips, which is what the upstream
    meant to store; the latter would expose binary float noise.
    """
    note = ""
    if isinstance(value, float):
        note = (
            "upstream stored this amount as a float; converted via its shortest "
            "round-trip decimal form, so treat the final digit as approximate"
        )
    try:
        return Money.of(Decimal(str(value)), currency), note
    except (InvalidOperation, ArithmeticError) as exc:
        raise ValueError(f"cannot represent {value!r} as money: {exc}") from exc


@dataclass(frozen=True, slots=True)
class PriceAssessment:
    """The answer to "is this price normal?" -- evidence, never a verdict.

    Deliberately carries no recommendation.  Spec Sec. 12 forbids telling the
    user "buy this because AI says it is good"; we return the observed range and
    a stable code, and the UI shows the evidence.
    """

    code: str
    """One of PRICE_WITHIN_EXPECTED_RANGE, PRICE_ABOVE_OBSERVED_RANGE,
    PRICE_BELOW_OBSERVED_RANGE, INSUFFICIENT_EVIDENCE."""

    quoted: Money | None
    observed_low: Money | None
    observed_high: Money | None
    observed_median: Money | None
    sample_size: int
    delta_vs_median_pct: Decimal | None
    sources: tuple[str, ...]
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        def m(value: Money | None) -> dict[str, Any] | None:
            return value.to_dict() if value else None

        return {
            "code": self.code,
            "quoted": m(self.quoted),
            "observed_low": m(self.observed_low),
            "observed_high": m(self.observed_high),
            "observed_median": m(self.observed_median),
            "sample_size": self.sample_size,
            "delta_vs_median_pct": (
                str(self.delta_vs_median_pct)
                if self.delta_vs_median_pct is not None
                else None
            ),
            "sources": list(self.sources),
            "note": self.note,
        }


class MarketAdapter(Capability):
    """Price and market evidence from InflationForge."""

    name = "market"
    upstream = "InflationForge (MIT)"

    def __init__(
        self,
        base_url: str | None = None,
        *,
        timeout: float = 15.0,
        mode_override: CapabilityMode | None = None,
    ) -> None:
        self.base_url = (base_url or os.getenv("BEACON_MARKET_URL") or "").rstrip("/")
        self.timeout = timeout
        self._mode_override = mode_override

    # ------------------------------------------------------------------
    # health
    # ------------------------------------------------------------------

    def health(self) -> HealthReport:
        """Never raises.  Reports what we can actually reach right now."""
        if self._mode_override is not None:
            return HealthReport(
                name=self.name,
                mode=self._mode_override,
                detail="mode pinned by caller",
                endpoint=self.base_url or None,
                upstream=self.upstream,
            )
        if not self.base_url:
            return HealthReport(
                name=self.name,
                mode=CapabilityMode.NOT_CONFIGURED,
                detail="no InflationForge endpoint configured",
                missing_config=("BEACON_MARKET_URL",),
                upstream=self.upstream,
            )
        try:
            body = self._get("/health")
        except Exception as exc:  # noqa: BLE001 - health must not raise
            return HealthReport(
                name=self.name,
                mode=CapabilityMode.UNAVAILABLE,
                detail=f"{type(exc).__name__}: {exc}",
                endpoint=self.base_url,
                upstream=self.upstream,
            )
        modes = body.get("modes", {}) if isinstance(body, dict) else {}
        provider = str(modes.get("price_provider", "")).upper()
        # The upstream names its own fallbacks; a live-reader fallback is not a
        # live provider, and we refuse to report it as one.
        sandboxish = any(
            token in provider for token in ("FALLBACK", "LOCAL", "SAMPLE", "SANDBOX")
        )
        return HealthReport(
            name=self.name,
            mode=CapabilityMode.SANDBOX if sandboxish else CapabilityMode.LIVE,
            detail=f"price_provider={provider or 'UNKNOWN'}",
            endpoint=self.base_url,
            upstream=self.upstream,
        )

    # ------------------------------------------------------------------
    # evidence
    # ------------------------------------------------------------------

    def price_evidence(
        self,
        *,
        item_query: str,
        city_id: str | None = None,
    ) -> CapabilityResult:
        """Observations for a tracked item, with each source receipt attached.

        Returns ``UNAVAILABLE`` for an item InflationForge does not track --
        which is most retail products, by design.
        """
        report = self.health()
        if report.mode in (CapabilityMode.NOT_CONFIGURED, CapabilityMode.UNAVAILABLE):
            return self.unconfigured_result(gaps=("observed_price",))

        try:
            dashboard = self._get("/api/dashboard")
        except Exception as exc:  # noqa: BLE001
            # Distinguish "provider did not answer" from "item not tracked":
            # a timeout is an outage to fix, not an absent data point.
            detail = f"{type(exc).__name__}: {exc}"
            return CapabilityResult(
                capability=self.name,
                mode=CapabilityMode.UNAVAILABLE,
                payload={"error": detail, "endpoint": f"{self.base_url}/api/dashboard"},
                observations=(
                    self.missing(
                        "observed_price",
                        note=f"InflationForge did not answer: {detail}",
                    ),
                ),
                gaps=("observed_price",),
            )

        item = self._match_item(dashboard.get("items", []), item_query)
        if item is None:
            tracked = sorted(str(i.get("name", "")) for i in dashboard.get("items", []))
            return CapabilityResult(
                capability=self.name,
                mode=report.mode,
                payload={
                    "reason": "ITEM_NOT_TRACKED",
                    "item_query": item_query,
                    "tracked_items": tracked,
                    "scope_note": (
                        "InflationForge tracks a city cost-of-living basket, not a "
                        "product catalogue; this item is outside its scope"
                    ),
                },
                observations=(
                    self.missing(
                        "observed_price",
                        note=(
                            f"{item_query!r} is not a tracked InflationForge item; "
                            "product-level pricing must come from the commerce "
                            "capability"
                        ),
                    ),
                ),
                gaps=("observed_price",),
            )

        snapshot = dashboard.get("snapshot") or {}
        snapshot_id = snapshot.get("id")
        rows: list[dict[str, Any]] = []
        if snapshot_id:
            query: dict[str, Any] = {"item_id": item["id"]}
            if city_id:
                query["city_id"] = city_id
            try:
                rows = self._get(
                    f"/api/snapshots/{snapshot_id}/observations", params=query
                )
            except Exception as exc:  # noqa: BLE001
                rows = []
                snapshot = {**snapshot, "observation_error": str(exc)}

        observations = tuple(self._to_observations(rows))
        return CapabilityResult(
            capability=self.name,
            mode=report.mode,
            payload={
                "item": {
                    "id": item["id"],
                    "name": item.get("name"),
                    "unit": item.get("unit"),
                },
                "snapshot_id": snapshot_id,
                "city_id": city_id,
                "row_count": len(rows),
                "provider_mode": snapshot.get("provider_mode"),
            },
            observations=observations,
            gaps=() if observations else ("observed_price",),
            subsystem_ref=str(snapshot_id) if snapshot_id else None,
        )

    def _to_observations(self, rows: list[dict[str, Any]]) -> list[Observation]:
        """One observation per upstream price row, provenance intact."""
        out: list[Observation] = []
        for row in rows:
            raw_price = row.get("price_usd")
            currency = str(row.get("currency") or "USD")
            if raw_price is None:
                out.append(
                    self.missing(
                        "observed_price",
                        note=f"row {row.get('id')} carried no price",
                    )
                )
                continue
            try:
                amount, float_note = money_from_float(raw_price, currency)
            except ValueError as exc:
                out.append(self.missing("observed_price", note=str(exc)))
                continue
            kind = str(row.get("kind") or "").upper()
            notes = [n for n in (float_note, f"kind={kind}" if kind else "") if n]
            out.append(
                self.observe(
                    "observed_price",
                    amount.to_dict(),
                    evidence_class=_KIND_TO_CLASS.get(kind, EvidenceClass.UNVERIFIED),
                    normalized_value=amount.minor,
                    source_url=row.get("source_url"),
                    raw_reference=str(row.get("id") or ""),
                    raw_hash=content_hash(row),
                    note="; ".join(notes),
                )
            )
        return out

    # ------------------------------------------------------------------
    # assessment
    # ------------------------------------------------------------------

    def price_assessment(
        self, quoted: Money, observations: tuple[Observation, ...]
    ) -> PriceAssessment:
        """Compare a quote to observed prices.  Evidence only, no advice.

        Refuses to answer at all when the observations are in another currency:
        we do not invent an exchange rate (spec Sec. 11).
        """
        amounts: list[Money] = []
        sources: list[str] = []
        wrong_currency = 0
        for obs in observations:
            if obs.value is None or not obs.is_decision_grade:
                continue
            value = obs.value
            if not isinstance(value, dict):
                continue
            money = Money(int(value["minor"]), str(value["currency"]))
            if money.currency != quoted.currency:
                wrong_currency += 1
                continue
            amounts.append(money)
            sources.append(obs.provenance.source_url or obs.provenance.source)

        if not amounts:
            note = "no decision-grade observations in the quoted currency"
            if wrong_currency:
                note = (
                    f"{wrong_currency} observation(s) are in another currency; "
                    "no exchange rate is invented here"
                )
            return PriceAssessment(
                code="INSUFFICIENT_EVIDENCE",
                quoted=quoted,
                observed_low=None,
                observed_high=None,
                observed_median=None,
                sample_size=0,
                delta_vs_median_pct=None,
                sources=(),
                note=note,
            )

        ordered = sorted(amounts, key=lambda m: m.minor)
        low, high = ordered[0], ordered[-1]
        mid = len(ordered) // 2
        median = (
            ordered[mid]
            if len(ordered) % 2 == 1
            else Money(
                (ordered[mid - 1].minor + ordered[mid].minor) // 2, quoted.currency
            )
        )
        delta = (
            (
                Decimal(quoted.minor - median.minor) / Decimal(median.minor) * 100
            ).quantize(Decimal("0.1"))
            if median.minor
            else None
        )
        if quoted.minor > high.minor:
            code = "PRICE_ABOVE_OBSERVED_RANGE"
        elif quoted.minor < low.minor:
            code = "PRICE_BELOW_OBSERVED_RANGE"
        else:
            code = "PRICE_WITHIN_EXPECTED_RANGE"
        return PriceAssessment(
            code=code,
            quoted=quoted,
            observed_low=low,
            observed_high=high,
            observed_median=median,
            sample_size=len(ordered),
            delta_vs_median_pct=delta,
            sources=tuple(dict.fromkeys(sources)),
        )

    # ------------------------------------------------------------------
    # transport
    # ------------------------------------------------------------------

    @staticmethod
    def _match_item(items: list[dict[str, Any]], query: str) -> dict[str, Any] | None:
        """Exact-ish match against tracked items.  No fuzzy guessing."""
        needle = query.strip().lower()
        if not needle:
            return None
        for item in items:
            if str(item.get("status", "ACTIVE")).upper() != "ACTIVE":
                continue
            name = str(item.get("name", "")).lower()
            slug = str(item.get("slug", "")).lower()
            if needle in (name, slug):
                return item
            terms = [str(t).lower() for t in item.get("match_terms", []) or []]
            if needle in terms:
                return item
        return None

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        url = f"{self.base_url}{path}"
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"
        if not url.startswith(("http://", "https://")):
            raise ValueError(f"refusing non-http endpoint {url!r}")
        request = urllib.request.Request(  # noqa: S310 - scheme checked above
            url, headers={"Accept": "application/json"}, method="GET"
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:  # noqa: S310
            return json.loads(response.read().decode("utf-8"))
