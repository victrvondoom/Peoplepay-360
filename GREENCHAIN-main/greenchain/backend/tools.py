"""
tools.py
--------
Plain Python functions passed to Dedalus as agent tools. Dedalus extracts the
JSON schema from type hints + docstrings automatically, so these need accurate
signatures and useful docstrings.

All tools are SYNCHRONOUS because the underlying ML calls are CPU-bound
(XGBoost inference + lookup tables). They return plain dicts that the agent
can thread back into its final JSON output.

These tools are thin wrappers over the real ML layer in
`/machine_learning/ml/inference.py`. The wiring happens via `ml_bridge`.
"""

from __future__ import annotations

import os
import time
from typing import Optional

import httpx
from bs4 import BeautifulSoup

# ml_bridge must be imported first to set up sys.path before ml.* imports.
from . import ml_bridge  # noqa: F401  (side-effect: configures sys.path)
from . import machine_host
from .ml_bridge import (
    get_emissions_model,
    get_transport_calculator,
)
from .naics_classifier import classify_naics


# Realistic UA — corporate sustainability pages reject obvious bots.
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# Brave's free tier rate-limits to 1 request/second.
_LAST_BRAVE_CALL = 0.0


# ---------------------------------------------------------------------------
#  NAICS inference — see naics_classifier.py (curated phrases + lexical match
#  over all USEEIO industry titles; generic manufacturing "33" as fallback).
# ---------------------------------------------------------------------------


def infer_naics(product: str) -> str:
    """Best-effort product-name → NAICS code mapping."""
    return classify_naics(product).code


# ---------------------------------------------------------------------------
#  Tool 1 — lookup_emission_factor
# ---------------------------------------------------------------------------

def lookup_emission_factor(
    naics_code: str,
    country_iso: str,
    revenue_usd_m: float = 25.0,
    year: int = 2023,
    region: Optional[str] = None,
    renewable_pct: float = 0.0,
) -> dict:
    """
    Look up manufacturing emission intensity for a supplier.

    Runs the trained XGBoost quantile model (q10/q50/q90) to estimate
    tCO2e for the given industry (NAICS), country, and revenue.

    Args:
        naics_code:    NAICS code of the industry (any length, e.g. "315220",
                       "3152", or "31"). Use the `infer_naics` helper or pass
                       the most specific code you can determine.
        country_iso:   Two-letter ISO country code, e.g. "CN", "US", "VN".
        revenue_usd_m: Annual revenue in USD millions. Defaults to 25.0 for
                       unknown small/mid manufacturers.
        year:          Reporting year (default 2023).
        region:        Optional sub-national region for finer grid accuracy,
                       e.g. "GD" (Guangdong) or "CA" (California).
        renewable_pct: 0.0-1.0. Fraction of energy from renewables.

    Returns:
        dict with q10_tco2e, q50_tco2e, q90_tco2e, intensity_tco2e_per_usdm,
        grid_gco2_kwh, and echoed inputs.
    """
    model = get_emissions_model()
    return model.predict(
        country_iso=country_iso,
        naics4=naics_code,
        revenue_usd_m=revenue_usd_m,
        year=year,
        region=region,
        renewable_pct=renewable_pct,
    )


# ---------------------------------------------------------------------------
#  Tool 2 — calculate_transport_emissions
# ---------------------------------------------------------------------------

def calculate_transport_emissions(
    origin_country: str,
    destination_country: str,
    weight_kg: float,
    mode: str = "sea",
) -> dict:
    """
    Calculate transport CO2 emissions using GLEC factors and port distances.

    Formula: tCO2e = GLEC_factor × weight_tonnes × distance_km / 1000

    Args:
        origin_country:      Two-letter ISO country code of manufacturing origin.
        destination_country: Two-letter ISO country code of final destination.
        weight_kg:           Total shipment weight in kilograms.
        mode:                One of "sea" | "air" | "rail" | "road".

    Returns:
        dict with transport_tco2e, distance_km, mode, glec_factor, weight_kg.
    """
    TransportCalculator = get_transport_calculator()
    mode = (mode or "sea").lower()
    weight_tonnes = max(weight_kg, 0.0) / 1000.0

    result = TransportCalculator.compute(
        origin_country=origin_country,
        destination_country=destination_country,
        weight_tonnes=weight_tonnes,
        mode=mode,
    )
    # Normalise key names to match the CLAUDE.md contract the agent expects.
    return {
        "transport_tco2e": result["tco2e"],
        "distance_km":     result["distance_km"],
        "mode":            result["mode"],
        "glec_factor":     result["glec_factor"],
        "weight_kg":       weight_kg,
        "origin_port":     result["origin_port"],
        "dest_port":       result["dest_port"],
    }


# ---------------------------------------------------------------------------
#  Tool 3 — score_certifications
# ---------------------------------------------------------------------------

def score_certifications(certifications: list[str]) -> dict:
    """
    Score a supplier's sustainability certifications.

    Recognised certifications (spelling-insensitive, e.g. "ISO 14001:2015",
    "CDP A-", "Science Based Targets", "B Corp"): iso14001, cdp_a, cdp_b,
    cdp_c, sbt_committed, sbt_achieved, bcorp. Within CDP and SBTi only the
    strongest credential counts.

    A supplier that discloses no certifications at all incurs a
    non-disclosure penalty (multiplier > 1). Multiplier is clamped to
    [0.5, 1.2].

    Args:
        certifications: list of certification strings, e.g. ["iso14001", "cdp_b"].

    Returns:
        dict with multiplier (float), cert_score (0-100), matched_certs (list),
        and disclosure_penalty (bool).
    """
    # Same normalisation and adjustment table the composite scorer uses, so
    # the agent sees the multiplier that will actually be applied.
    from ml.inference import certification_adjustment, normalise_certification  # type: ignore

    weights = {
        "iso14001": 20, "cdp_a": 40, "cdp_b": 25, "cdp_c": 10,
        "sbt_achieved": 35, "sbt_committed": 25, "bcorp": 15,
    }
    family = {
        "cdp_a": "cdp", "cdp_b": "cdp", "cdp_c": "cdp",
        "sbt_achieved": "sbt", "sbt_committed": "sbt",
    }

    labels = [str(c) for c in (certifications or []) if str(c or "").strip()]
    matched: list[str] = []
    best_weight_by_family: dict[str, int] = {}
    for label in labels:
        normalised = normalise_certification(label)
        if normalised is None:
            continue
        key: str = normalised
        if key in matched:
            continue
        matched.append(key)
        group = family.get(key, key)
        best_weight_by_family[group] = max(best_weight_by_family.get(group, 0), weights[key])

    multiplier = certification_adjustment(labels)

    return {
        "multiplier":          round(max(0.5, min(1.2, multiplier)), 3),
        "cert_score":          min(100, sum(best_weight_by_family.values())),
        "matched_certs":       matched,
        "disclosure_penalty":  not labels,
    }


# ---------------------------------------------------------------------------
#  Tool 4 — web_search (Brave Search API; requires BRAVE_API_KEY)
# ---------------------------------------------------------------------------

def web_search(query: str, max_results: int = 8) -> list[dict]:
    """
    Search the public web via the Brave Search API.

    Use this to discover real manufacturers, e.g.
        web_search("cotton t-shirt manufacturer Bangladesh sustainability")

    Args:
        query:       Free-text search query.
        max_results: Max number of result links to return (default 8, hard-cap 20).

    Returns:
        list of dicts with keys: title, url, snippet. Returns [{"error": ...}]
        on failure; never raises — Dedalus tools must not crash the agent.
    """
    global _LAST_BRAVE_CALL

    max_results = max(1, min(int(max_results or 8), 20))
    api_key = os.environ.get("BRAVE_API_KEY", "").strip()
    if not api_key:
        return [{"error": "no_brave_api_key — set BRAVE_API_KEY in backend/.env"}]

    # Throttle to 1 req/s for Brave's free tier.
    elapsed = time.monotonic() - _LAST_BRAVE_CALL
    if elapsed < 1.05:
        time.sleep(1.05 - elapsed)

    try:
        resp = httpx.get(
            "https://api.search.brave.com/res/v1/web/search",
            params={"q": query, "count": max_results, "safesearch": "moderate"},
            headers={
                "Accept": "application/json",
                "Accept-Encoding": "gzip",
                "X-Subscription-Token": api_key,
            },
            timeout=12.0,
        )
        _LAST_BRAVE_CALL = time.monotonic()
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        return [{"error": f"brave_http_{exc.response.status_code}: {exc.response.text[:200]}"}]
    except Exception as exc:  # noqa: BLE001
        return [{"error": f"search_failed: {type(exc).__name__}: {exc}"}]

    payload = resp.json()
    web_results = (payload.get("web") or {}).get("results") or []
    out: list[dict] = []
    for r in web_results[:max_results]:
        out.append({
            "title": r.get("title", "").strip(),
            "url": r.get("url", "").strip(),
            "snippet": (r.get("description") or "").strip(),
        })
    return out


# ---------------------------------------------------------------------------
#  Tool 5 — fetch_url (httpx + BeautifulSoup text extraction)
# ---------------------------------------------------------------------------

def _local_fetch(url: str) -> str:
    """Local httpx fetch. Returns raw HTML or raises."""
    resp = httpx.get(
        url,
        headers={
            "User-Agent": _UA,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
        },
        timeout=12.0,
        follow_redirects=True,
    )
    resp.raise_for_status()
    return resp.text


def fetch_url(url: str, max_chars: int = 4000) -> str:
    """
    Fetch a URL and return the visible text content.

    Use this to read a manufacturer's sustainability or ESG page after finding
    it via `web_search`. Strips scripts/styles/nav and returns just the prose.

    When GREENCHAIN_USE_DEDALUS_MACHINE=1, the raw HTTP egress runs inside a
    provisioned Dedalus Machine (KVM-isolated VM); HTML parsing always runs
    in-process. Falls back to local httpx if the Machine path errors.

    Args:
        url:       Absolute URL (must include https://).
        max_chars: Truncate the returned text to this many characters
                   (default 4000, hard-cap 16000).

    Returns:
        Plain text content, or "FETCH_FAILED: ..." on any error.
    """
    max_chars = max(500, min(int(max_chars or 4000), 16000))
    if not url or not url.startswith(("http://", "https://")):
        return f"FETCH_FAILED: invalid_url — {url}"

    html: str
    if machine_host.is_enabled():
        try:
            html = machine_host.fetch_via_machine(url, timeout=15.0)
        except machine_host.MachineFetchError as exc:
            print(
                f"[tools.fetch_url] machine path failed ({exc}); "
                "falling back to local httpx.",
                flush=True,
            )
            try:
                html = _local_fetch(url)
            except Exception as exc2:  # noqa: BLE001
                return f"FETCH_FAILED: {type(exc2).__name__}: {exc2} — {url}"
    else:
        try:
            html = _local_fetch(url)
        except Exception as exc:  # noqa: BLE001
            return f"FETCH_FAILED: {type(exc).__name__}: {exc} — {url}"

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "header", "footer", "nav"]):
        tag.decompose()

    parts: list[str] = []
    for el in soup.find_all(["h1", "h2", "h3", "p", "li"]):
        text = el.get_text(" ", strip=True)
        if text and len(text) > 2:
            parts.append(text)

    body = "\n".join(parts).strip()
    if not body:
        body = soup.get_text(" ", strip=True)
    return body[:max_chars]


# ---------------------------------------------------------------------------
#  Public tool list — passed to Dedalus runner.run(tools=...)
# ---------------------------------------------------------------------------

DEDALUS_TOOLS = [
    web_search,
    fetch_url,
    lookup_emission_factor,
    calculate_transport_emissions,
    score_certifications,
]
