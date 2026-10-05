"""
agents.py
---------
Dedalus runner call. One `runner.run()` per /search — Dedalus handles all
tool use, the web_search MCP, and final JSON shaping.

The function signature is what main.py imports.
"""

from __future__ import annotations

import inspect
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# Configure ML path before the tools module imports anything from ml.*
from . import ml_bridge  # noqa: F401
from .tools import DEDALUS_TOOLS, infer_naics


load_dotenv(Path(__file__).parent / ".env")


# Dedalus is imported lazily so backend modules can still be imported (for
# testing, linting, etc.) on machines where the SDK isn't installed.
def _load_dedalus():
    from dedalus_labs import AsyncDedalus, DedalusRunner  # type: ignore

    return AsyncDedalus, DedalusRunner


DEFAULT_MODEL = os.environ.get("GREENCHAIN_MODEL", "anthropic/claude-sonnet-4-6")


_TOOL_MENU = """\
You have these tools — use them, do not hallucinate manufacturers:
  • web_search(query)             — Brave search; returns title + url + snippet
  • fetch_url(url)                — retrieves text content of a webpage
  • lookup_emission_factor        — XGBoost manufacturing emissions estimate
  • calculate_transport_emissions — GLEC framework transport CO2
  • score_certifications          — sustainability certification scoring"""


_OUTPUT_SCHEMA = """\
Return ONLY a JSON array (no markdown fences, no prose, no commentary)
with this exact schema:

[
  {
    "name": "Manufacturer Name",
    "country": "ISO two-letter country code",
    "city": "city name or null",
    "sustainability_url": "URL or null",
    "certifications": ["iso14001", "cdp_b"],
    "emission_factor": { ...result from lookup_emission_factor },
    "transport":       { ...result from calculate_transport_emissions },
    "cert_score":      { ...result from score_certifications },
    "disclosure_status": "verified | partial | none"
  }
]"""


def _build_per_country_prompt(
    *, product, countries, destination, transport_mode,
    naics_hint, total_weight_kg, per_country, cert_clause, product_context,
    current_manufacturer, min_alternatives, retry_guidance,
) -> str:
    product_context_clause = (
        f'This search is for the component/material "{product}" used in the finished product "{product_context}".'
        if product_context
        else ""
    )
    return f"""
You are a supply chain researcher. Research manufacturers of "{product}" in
these countries: {', '.join(countries)}.

{product_context_clause}

{_TOOL_MENU}

You must return at least {min_alternatives} ALTERNATIVE manufacturers that are
not the incumbent supplier "{current_manufacturer}".
Do not return "{current_manufacturer}" unless it is impossible to identify any
alternatives after exhaustive searching.
Every returned manufacturer must be a distinct company, not a duplicate brand,
division, or alias of another returned result.
{retry_guidance}

For EACH country:
  1. Call web_search with queries like
     "{product} manufacturer <country name>" and
     "{product} supplier <country name> sustainability".
     Pick {per_country}-{per_country + 1} real manufacturers from the results
     (use the URL domain to identify the company; ignore directory/aggregator
     sites like alibaba, thomasnet, panjiva).
  2. For each manufacturer, try to find their sustainability or ESG page —
     either from a result snippet or by calling
     web_search("<company name> sustainability report"), then call
     fetch_url on the most relevant URL. If fetch_url returns
     "FETCH_FAILED", just skip that page and move on.
  3. From the fetched page text, extract any certifications mentioned:
     ISO 14001, CDP rating (A/B/C/D), Science Based Targets
     (committed/achieved), B Corp.
  4. Call lookup_emission_factor with:
       naics_code="{naics_hint}" (or a more specific code if you know one),
       country_iso="<the manufacturer's ISO country code>",
       revenue_usd_m=25 (use a better estimate if you find one),
       year=2023.
  5. Call calculate_transport_emissions with:
       origin_country="<the manufacturer's ISO country code>",
       destination_country="{destination}",
       weight_kg={total_weight_kg},
       mode="{transport_mode}".
  6. Call score_certifications with the list of certification keys found.
     Normalise keys to lowercase with underscores, e.g. "iso14001", "cdp_b",
     "sbt_committed", "bcorp".

{cert_clause}

{_OUTPUT_SCHEMA}
"""


def _build_global_prompt(
    *, product, destination, transport_mode,
    naics_hint, total_weight_kg, target_count, cert_clause, product_context,
    current_manufacturer, min_alternatives, retry_guidance,
) -> str:
    product_context_clause = (
        f'This search is for the component/material "{product}" used in the finished product "{product_context}".'
        if product_context
        else ""
    )
    return f"""
You are a supply chain researcher. Find the {target_count} most relevant
manufacturers of "{product}" anywhere in the WORLD — pick whichever countries
make the most sense. Aim for geographic diversity (don't put them all in one
country) and prefer manufacturers that publish sustainability information.

{product_context_clause}

{_TOOL_MENU}

You must return at least {min_alternatives} ALTERNATIVE manufacturers that are
not the incumbent supplier "{current_manufacturer}".
Do not return "{current_manufacturer}" unless it is impossible to identify any
alternatives after exhaustive searching.
Every returned manufacturer must be a distinct company, not a duplicate brand,
division, or alias of another returned result.
If the first search wave is thin, broaden queries with synonyms, e.g.
"producer", "converter", "industrial supplier", material-specific phrases,
and country/region terms.
{retry_guidance}

Workflow:
  1. Run at least 4 broad web_search queries to find candidate manufacturers globally.
     Examples: "{product} manufacturer sustainability",
     "{product} top exporter country", "ethical {product} factory".
     Ignore directory/aggregator sites (alibaba, thomasnet, panjiva).
  2. Pick up to {target_count} real manufacturers, ideally from different countries.
     Do not stop after finding one valid company; continue until you have found
     at least {min_alternatives} alternatives or have exhausted credible search leads.
  3. For each manufacturer, optionally fetch_url their main site or
     sustainability page to extract certifications. If fetch_url returns
     "FETCH_FAILED", just skip it.
  4. Extract certifications: ISO 14001, CDP rating (A/B/C/D),
     Science Based Targets (committed/achieved), B Corp.
  5. For each manufacturer, call:
       lookup_emission_factor(naics_code="{naics_hint}",
                              country_iso="<their ISO code>",
                              revenue_usd_m=25, year=2023)
       calculate_transport_emissions(origin_country="<their ISO code>",
                              destination_country="{destination}",
                              weight_kg={total_weight_kg},
                              mode="{transport_mode}")
       score_certifications(<list of cert keys, lowercase with underscores>)

{cert_clause}

{_OUTPUT_SCHEMA}
"""


async def run_supply_chain_research(
    product: str,
    quantity: int,
    countries: list[str],
    destination: str,
    transport_mode: str,
    require_certifications: list[str] | None = None,
    product_context: str | None = None,
    shipment_weight_kg: float | None = None,
    target_count: int | None = None,
    current_manufacturer: str | None = None,
    min_alternatives: int = 1,
    retry_guidance: str | None = None,
) -> str:
    """
    Kick off the Dedalus supply-chain research agent.

    Two modes:
      • per-country: ``countries`` is non-empty. Agent finds N manufacturers
        per country (default 5; if ``target_count`` is given it splits across
        the country list).
      • global: ``countries`` is empty (or None). Agent picks ``target_count``
        manufacturers worldwide, biased toward geographic diversity (default 6).

    Returns the raw agent output (a JSON string — `ml_scorer` is responsible
    for parsing it, including stripping any markdown fences the agent emits).
    """
    AsyncDedalus, DedalusRunner = _load_dedalus()
    client = AsyncDedalus()
    runner = DedalusRunner(client)

    cert_clause = (
        f"Only return manufacturers that have at least one of these "
        f"certifications: {require_certifications}."
        if require_certifications
        else ""
    )

    naics_hint = infer_naics(product)
    # 0.5 kg/unit is a reasonable default for mixed hardgoods.
    total_weight_kg = max(
        1.0,
        shipment_weight_kg
        if shipment_weight_kg is not None
        else float(quantity) * 0.5,
    )

    if countries:
        per_country = (
            max(1, target_count // len(countries))
            if target_count
            else 5
        )
        prompt = _build_per_country_prompt(
            product=product, countries=countries,
            destination=destination, transport_mode=transport_mode,
            naics_hint=naics_hint, total_weight_kg=total_weight_kg,
            per_country=per_country, cert_clause=cert_clause,
            product_context=product_context,
            current_manufacturer=current_manufacturer or "the incumbent supplier",
            min_alternatives=min_alternatives,
            retry_guidance=retry_guidance or "",
        )
    else:
        prompt = _build_global_prompt(
            product=product, destination=destination,
            transport_mode=transport_mode, naics_hint=naics_hint,
            total_weight_kg=total_weight_kg,
            target_count=target_count or 6,
            cert_clause=cert_clause,
            product_context=product_context,
            current_manufacturer=current_manufacturer or "the incumbent supplier",
            min_alternatives=min_alternatives,
            retry_guidance=retry_guidance or "",
        )

    outcome = runner.run(
        input=prompt.strip(),
        model=DEFAULT_MODEL,
        tools=DEDALUS_TOOLS,
        max_tokens=4096,
        max_steps=14,
    )
    # With AsyncDedalus and no streaming, run() returns a coroutine that
    # resolves to the run result (the SDK leaves the return type unannotated).
    if not inspect.isawaitable(outcome):
        raise TypeError(
            f"DedalusRunner.run returned {type(outcome).__name__}, expected an awaitable."
        )
    response: Any = await outcome

    return response.final_output
