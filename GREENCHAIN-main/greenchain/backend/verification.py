"""
verification.py
----------------
Cheap, best-effort credibility signals for agent-discovered manufacturers.
Never raises, never blocks the pipeline — every check degrades to "unknown"
on any failure (missing key, network error, rate limit).

Produces a `verification` block per manufacturer:
{
  "registry_match": true|false|null,   # OpenCorporates hit
  "source_count": int,                 # distinct domains cited for this mfr
  "domain_age_days": int|null,         # None if unknown
  "domain_flag": bool,                 # True if domain looks very new (<30d)
  "confidence": "verified"|"partial"|"unverified"
}
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import httpx

_OPENCORP_URL = "https://api.opencorporates.com/v0.4/companies/search"
_TIMEOUT = 6.0


def _domain_of(url: str | None) -> str | None:
    if not url:
        return None
    try:
        netloc = urlparse(url if "://" in url else f"//{url}", scheme="https").netloc
        return netloc.lower().removeprefix("www.") or None
    except Exception:
        return None


def registry_match(name: str, country_iso: str | None) -> bool | None:
    """Best-effort OpenCorporates lookup. None = couldn't check (no crash)."""
    if not name:
        return None
    api_key = os.environ.get("OPENCORPORATES_API_KEY", "").strip()
    params: dict[str, Any] = {"q": name, "order": "score"}
    if country_iso:
        params["jurisdiction_code"] = country_iso.lower()
    if api_key:
        params["api_token"] = api_key
    try:
        resp = httpx.get(_OPENCORP_URL, params=params, timeout=_TIMEOUT)
        if resp.status_code == 429:
            return None  # rate-limited, not "not found"
        resp.raise_for_status()
        data = resp.json()
        companies = (data.get("results") or {}).get("companies") or []
        return len(companies) > 0
    except Exception:
        return None


def domain_age_days(url: str | None) -> int | None:
    """Best-effort domain age via RDAP (no extra dependency, free, no key)."""
    domain = _domain_of(url)
    if not domain:
        return None
    try:
        resp = httpx.get(f"https://rdap.org/domain/{domain}", timeout=_TIMEOUT)
        if resp.status_code != 200:
            return None
        events = resp.json().get("events") or []
        for ev in events:
            if ev.get("eventAction") == "registration":
                created = datetime.fromisoformat(ev["eventDate"].replace("Z", "+00:00"))
                return (datetime.now(timezone.utc) - created).days
    except Exception:
        return None
    return None


def source_count(sustainability_url: str | None, disclosure_status: str | None) -> int:
    """Approximate corroborating-source count from what the agent actually
    emits: a sustainability page (1) plus the agent's own disclosure verdict
    counting as a second independent signal when it says "verified"."""
    n = 1 if sustainability_url else 0
    if (disclosure_status or "").lower() == "verified":
        n += 1
    return n


def confidence_tier(*, registry_hit: bool | None, sources: int, domain_flag: bool) -> str:
    if registry_hit is True and sources >= 2 and not domain_flag:
        return "verified"
    if registry_hit is False and sources < 1:
        return "unverified"
    if sources >= 1 or registry_hit is True:
        return "partial"
    return "unverified"


def verify_manufacturer(
    name: str,
    country_iso: str | None,
    sustainability_url: str | None,
    disclosure_status: str | None = None,
) -> dict[str, Any]:
    """Run all checks for one manufacturer. Never raises."""
    reg = registry_match(name, country_iso)
    age = domain_age_days(sustainability_url)
    flag = age is not None and age < 30
    n_sources = source_count(sustainability_url, disclosure_status)

    return {
        "registry_match":   reg,
        "source_count":     n_sources,
        "domain_age_days":  age,
        "domain_flag":      flag,
        "confidence":       confidence_tier(registry_hit=reg, sources=n_sources, domain_flag=flag),
    }


def verify_all(
    manufacturers: list[dict[str, Any]],
    max_workers: int = 6,
) -> None:
    """Mutates each dict in-place, adding a `verification` key. Runs in
    parallel threads since these are blocking HTTP calls; caps concurrency
    to stay polite to free-tier APIs. Never raises."""
    from concurrent.futures import ThreadPoolExecutor

    def _one(m: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        try:
            v = verify_manufacturer(
                m.get("name", ""),
                m.get("country"),
                m.get("sustainability_url"),
                m.get("disclosure_status"),
            )
        except Exception:
            v = {
                "registry_match": None, "source_count": 0,
                "domain_age_days": None, "domain_flag": False,
                "confidence": "unverified",
            }
        return m, v

    if not manufacturers:
        return
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        for m, v in ex.map(_one, manufacturers):
            m["verification"] = v
