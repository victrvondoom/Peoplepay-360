from __future__ import annotations

import asyncio
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
import re
from typing import Any
from urllib.parse import quote_plus

import httpx

from backend.models.domain import City


NUMBEO_BASE = "https://www.numbeo.com/cost-of-living/in"
WAYBACK_CDX = "https://web.archive.org/cdx/search/cdx"
WAYBACK_WEB = "https://web.archive.org/web"


CITY_CATALOG = [
    City(id="san-francisco", name="San Francisco", state="CA", latitude=37.7749, longitude=-122.4194, source_slug="San-Francisco"),
    City(id="new-york", name="New York", state="NY", latitude=40.7128, longitude=-74.0060, source_slug="New-York"),
    City(id="los-angeles", name="Los Angeles", state="CA", latitude=34.0522, longitude=-118.2437, source_slug="Los-Angeles"),
    City(id="chicago", name="Chicago", state="IL", latitude=41.8781, longitude=-87.6298, source_slug="Chicago"),
    City(id="austin", name="Austin", state="TX", latitude=30.2672, longitude=-97.7431, source_slug="Austin"),
    City(id="miami", name="Miami", state="FL", latitude=25.7617, longitude=-80.1918, source_slug="Miami"),
    City(id="seattle", name="Seattle", state="WA", latitude=47.6062, longitude=-122.3321, source_slug="Seattle"),
    City(id="boston", name="Boston", state="MA", latitude=42.3601, longitude=-71.0589, source_slug="Boston"),
    City(id="denver", name="Denver", state="CO", latitude=39.7392, longitude=-104.9903, source_slug="Denver"),
    City(id="phoenix", name="Phoenix", state="AZ", latitude=33.4484, longitude=-112.0740, source_slug="Phoenix"),
    City(id="dallas", name="Dallas", state="TX", latitude=32.7767, longitude=-96.7970, source_slug="Dallas"),
    City(id="houston", name="Houston", state="TX", latitude=29.7604, longitude=-95.3698, source_slug="Houston"),
    City(id="nashville", name="Nashville", state="TN", latitude=36.1627, longitude=-86.7816, source_slug="Nashville"),
    City(id="philadelphia", name="Philadelphia", state="PA", latitude=39.9526, longitude=-75.1652, source_slug="Philadelphia"),
    City(id="washington", name="Washington", state="DC", latitude=38.9072, longitude=-77.0369, source_slug="Washington"),
    City(id="minneapolis", name="Minneapolis", state="MN", latitude=44.9778, longitude=-93.2650, source_slug="Minneapolis"),
]


@dataclass(frozen=True)
class ParsedPriceRow:
    label: str
    price_usd: float


@dataclass(frozen=True)
class CityCollection:
    city: City
    current_rows: list[ParsedPriceRow]
    previous_rows: list[ParsedPriceRow]
    current_url: str
    archive_url: str
    archive_timestamp: str


class _PriceTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.in_row = False
        self.in_cell = False
        self.cells: list[str] = []
        self.cell_parts: list[str] = []
        self.rows: list[ParsedPriceRow] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self.in_row = True
            self.cells = []
        elif tag == "td" and self.in_row:
            self.in_cell = True
            self.cell_parts = []

    def handle_data(self, data: str) -> None:
        if self.in_cell:
            self.cell_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "td" and self.in_cell:
            self.cells.append(" ".join("".join(self.cell_parts).split()))
            self.in_cell = False
        elif tag == "tr" and self.in_row:
            self._finish_row()
            self.in_row = False

    def _finish_row(self) -> None:
        if len(self.cells) < 2:
            return
        label = self.cells[0].strip()
        price_text = self.cells[1].replace(",", "")
        match = re.search(r"(?:\$\s*)?([0-9]+(?:\.[0-9]+)?)", price_text)
        if label and match and ("$" in self.cells[1] or "USD" in self.cells[1].upper()):
            value = float(match.group(1))
            if value > 0:
                self.rows.append(ParsedPriceRow(label=label, price_usd=value))


def parse_price_rows(html: str) -> list[ParsedPriceRow]:
    parser = _PriceTableParser()
    parser.feed(html)
    unique: dict[str, ParsedPriceRow] = {}
    for row in parser.rows:
        unique.setdefault(row.label, row)
    # Reader fallbacks return the same live table as Markdown. Parsing that
    # representation keeps upstream throttling explicit without inventing data.
    for line in html.splitlines():
        if not line.lstrip().startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 2 or not cells[0] or cells[0] in {"---", "Range"}:
            continue
        match = re.fullmatch(r"\$\s*([0-9]+(?:,[0-9]{3})*(?:\.[0-9]+)?)", cells[1])
        if not match:
            continue
        label = re.sub(r"\[([^]]+)]\([^)]+\)", r"\1", cells[0]).strip(" *_")
        value = float(match.group(1).replace(",", ""))
        if label and value > 0:
            unique.setdefault(label, ParsedPriceRow(label=label, price_usd=value))
    return list(unique.values())


class CityPriceCollector:
    """Collects current pages and same-season prior-year captures with explicit provenance."""

    def __init__(self, bright_token: str = "", bright_zone: str = "", timeout_s: int = 35, telemetry: Any | None = None):
        self.bright_token = bright_token
        self.bright_zone = bright_zone
        self.timeout_s = timeout_s
        self.provider_error: str | None = None
        self.discovery_ok = False
        self.discovery_attempted = False
        self.reader_fallback_ok = False
        self.telemetry = telemetry
        self.archive_cache: dict[str, dict[str, Any]] = {}
        self._semaphore = asyncio.Semaphore(4)

    @property
    def mode(self) -> str:
        if self.discovery_ok and self.reader_fallback_ok:
            return "BRIGHT DATA SERP + JINA LIVE READER FALLBACK"
        if self.discovery_ok:
            return "BRIGHT DATA SERP DISCOVERY + LIVE WEB"
        if self.reader_fallback_ok:
            return "JINA LIVE READER FALLBACK · BRIGHT DATA UNAVAILABLE"
        if self.bright_token and self.discovery_attempted:
            return "LIVE WEB · BRIGHT DATA FALLBACK ACTIVE"
        if self.bright_token:
            return "BRIGHT DATA SERP CONFIGURED · AWAITING SYNC"
        return "LIVE PUBLIC WEB"

    async def collect(self, current_year: int, previous_year: int) -> list[CityCollection]:
        self.provider_error = None
        self.reader_fallback_ok = False
        with self._span("bright_data.discover", {"zone": self.bright_zone, "configured": bool(self.bright_token)}):
            self.discovery_ok = await self._discover_sources()
        results = await asyncio.gather(
            *(self._collect_city(city, previous_year) for city in CITY_CATALOG),
            return_exceptions=True,
        )
        collections: list[CityCollection] = []
        errors: list[str] = []
        for city, result in zip(CITY_CATALOG, results, strict=True):
            if isinstance(result, Exception):
                detail = str(result) or type(result).__name__
                errors.append(f"{city.name}: {detail}")
            else:
                collections.append(result)
        if not collections:
            raise RuntimeError("No city price pages could be collected: " + "; ".join(errors))
        if errors:
            self.provider_error = "; ".join(errors)[:1000]
        return collections

    async def _collect_city(self, city: City, previous_year: int) -> CityCollection:
        current_url = f"{NUMBEO_BASE}/{city.source_slug}?displayCurrency=USD"
        async with self._semaphore:
            async with httpx.AsyncClient(timeout=self.timeout_s, follow_redirects=True) as client:
                with self._span("city.fetch.current", {"city": city.id, "url": current_url}):
                    current_response = await self._get_current(client, current_url, city.id)
                    current_rows = parse_price_rows(current_response.text)
                    if not current_rows:
                        raise RuntimeError("current price table was empty")
                cache_key = f"{city.id}:{previous_year}"
                cached = self.archive_cache.get(cache_key)
                if cached:
                    with self._span("archive.cache_hit", {"city": city.id, "year": previous_year}):
                        timestamp = str(cached["timestamp"])
                        archive_url = str(cached["url"])
                        previous_rows = [ParsedPriceRow(**row) for row in cached["rows"]]
                else:
                    with self._span("archive.resolve", {"city": city.id, "year": previous_year}):
                        timestamp = await self._closest_capture(client, current_url, previous_year)
                    archive_url = f"{WAYBACK_WEB}/{timestamp}id_/{current_url.split('?')[0]}"
                    with self._span("city.fetch.previous", {"city": city.id, "archive_timestamp": timestamp}):
                        archive_response = await self._get(client, archive_url)
                        previous_rows = parse_price_rows(archive_response.text)
                        if not previous_rows:
                            raise RuntimeError("archived price table was empty")
                    self.archive_cache[cache_key] = {
                        "timestamp": timestamp, "url": archive_url,
                        "rows": [{"label": row.label, "price_usd": row.price_usd} for row in previous_rows],
                    }
        return CityCollection(
            city=city,
            current_rows=current_rows,
            previous_rows=previous_rows,
            current_url=current_url,
            archive_url=archive_url,
            archive_timestamp=timestamp,
        )

    async def _get_current(self, client: httpx.AsyncClient, url: str, city_id: str) -> httpx.Response:
        try:
            response = await client.get(url, headers=self._headers())
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError as exc:
            fallback_statuses = {403, 408, 425, 429, 500, 502, 503, 504}
            if exc.response.status_code not in fallback_statuses:
                raise
            reader_url = "https://r.jina.ai/http://" + url.removeprefix("https://").removeprefix("http://")
            with self._span("city.fetch.reader_fallback", {
                "city": city_id, "reason": f"upstream_{exc.response.status_code}",
            }):
                response = await self._get(client, reader_url)
            self.reader_fallback_ok = True
            return response

    async def _closest_capture(self, client: httpx.AsyncClient, url: str, year: int) -> str:
        response = await self._get(
            client,
            WAYBACK_CDX,
            params=[
                ("url", url.split("?")[0]),
                ("from", str(year)),
                ("to", str(year)),
                ("output", "json"),
                ("filter", "statuscode:200"),
                ("filter", "mimetype:text/html"),
                ("fl", "timestamp,original,statuscode"),
                ("collapse", "digest"),
                ("limit", "100"),
            ],
        )
        rows: list[list[str]] = response.json()
        timestamps = [row[0] for row in rows[1:] if row and re.fullmatch(r"\d{14}", row[0])]
        if not timestamps:
            raise RuntimeError(f"no {year} archive capture")
        target = datetime(year, datetime.now(timezone.utc).month, datetime.now(timezone.utc).day, tzinfo=timezone.utc)
        return min(timestamps, key=lambda value: abs((datetime.strptime(value, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc) - target).total_seconds()))

    async def _get(
        self,
        client: httpx.AsyncClient,
        url: str,
        params: list[tuple[str, str]] | None = None,
    ) -> httpx.Response:
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                response = await client.get(url, params=params, headers=self._headers())
                response.raise_for_status()
                return response
            except (httpx.TimeoutException, httpx.HTTPStatusError, httpx.TransportError) as exc:
                last_error = exc
                retryable = not isinstance(exc, httpx.HTTPStatusError) or exc.response.status_code in {404, 408, 425, 429, 500, 502, 503, 504}
                if attempt == 2 or not retryable:
                    raise
                await asyncio.sleep(1.25 * (attempt + 1))
        raise RuntimeError(str(last_error) if last_error else "price request failed")

    async def _discover_sources(self) -> bool:
        self.discovery_attempted = True
        if not self.bright_token or not self.bright_zone:
            return False
        query = quote_plus("Numbeo cost of living United States city prices")
        try:
            async with httpx.AsyncClient(timeout=self.timeout_s, follow_redirects=True) as client:
                response = await client.post(
                    "https://api.brightdata.com/request",
                    headers={"Authorization": f"Bearer {self.bright_token}", "Content-Type": "application/json"},
                    json={"zone": self.bright_zone, "url": f"https://www.google.com/search?q={query}", "format": "json"},
                )
                response.raise_for_status()
                payload: Any = response.json()
                if isinstance(payload, dict) and int(payload.get("status_code", 200)) >= 400:
                    raise RuntimeError(payload.get("headers", {}).get("x-brd-error", "Bright Data query failed"))
                return True
        except Exception as exc:
            self.provider_error = f"Bright Data discovery: {exc}"[:1000]
            return False

    @staticmethod
    def _headers() -> dict[str, str]:
        return {
            "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
            "Accept-Encoding": "gzip, deflate",
            "User-Agent": "InflationForge/1.0 (+item-level inflation research)",
        }

    def _span(self, name: str, attributes: dict[str, Any]):
        return self.telemetry.span(name, attributes) if self.telemetry else nullcontext()

    def load_archive_cache(self, payload: dict[str, Any]) -> None:
        self.archive_cache = {
            key: value for key, value in payload.items()
            if isinstance(value, dict) and value.get("timestamp") and value.get("url") and isinstance(value.get("rows"), list)
        }
