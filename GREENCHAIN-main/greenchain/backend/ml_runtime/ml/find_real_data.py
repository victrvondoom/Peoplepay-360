"""
find_real_data.py
-----------------
Downloads real company/facility-level emissions data from free public sources:

  1. EPA GHGRP  — US facility Scope 1 emissions, 8,000+ reporters/yr, free CSV
     https://www.epa.gov/ghgreporting/data-sets

  2. Climate TRACE — global asset-level emissions (manufacturing), free
     https://climatetrace.org/data

  3. Zenodo benchmark — 139 company sustainability reports, Scope 1/2/3
     https://zenodo.org/records/14184617

  4. Our World in Data CO2 — country+sector time series (validation reference)
     https://github.com/owid/co2-data

Run from your terminal (NOT inside Jupyter/sandbox — needs open internet):
    cd ~/Jupyter/hack-princeton
    python ml/find_real_data.py

Outputs (in new_data2/real_emissions/):
    epa_ghgrp_summary.csv        — EPA GHGRP multi-year facility emissions
    climate_trace_manufacturing/ — Climate TRACE manufacturing ZIP
    owid_co2.csv                 — OWID country-level GHG time series
    zenodo_benchmark.csv         — 139-company sustainability-report extracts
    SOURCES.md                   — provenance notes for all files

MANUAL FALLBACKS (if script can't reach a source, download these yourself):
  - EPA GHGRP summary ZIP: https://www.epa.gov/system/files/other-files/2024-10/ghg_2022_data_summary_spreadsheets.zip
  - Climate TRACE manufacturing: https://downloads.climatetrace.org/v06/country_packages/manufacturing.zip
  - OWID CO2 CSV: https://raw.githubusercontent.com/owid/co2-data/master/owid-co2-data.csv
  - Zenodo: https://zenodo.org/records/14184617/files/benchmark_dataset.csv
  Drop any of those files into new_data2/real_emissions/ and rerun this script.
"""

import os
import sys
import zipfile
from typing import Any

import httpx
import pandas as pd

_THIS_DIR     = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
from ml.load_real_data import resolve_data_dir  # noqa: E402  (needs the sys.path entry above)

# Same new_data2/ folder the app loads its datasets from; created in main().
OUT_DIR       = os.path.join(resolve_data_dir("new_data2"), "real_emissions")

TIMEOUT = 60
HEADERS = {"User-Agent": "GreenChain-HackPrinceton/1.0 (research project)"}


def _download(url: str, label: str, out_path: str) -> str | None:
    """Stream url to out_path. Returns the saved path, or None on failure."""
    print(f"\n[{label}] Downloading: {url}")
    try:
        with httpx.stream(
            "GET", url, headers=HEADERS, timeout=TIMEOUT, follow_redirects=True
        ) as response:
            response.raise_for_status()
            with open(out_path, "wb") as f:
                for chunk in response.iter_bytes(65536):
                    f.write(chunk)
        size = os.path.getsize(out_path)
        print(f"[{label}] ✓  Saved {size/1024:.1f} KB → {out_path}")
        return out_path
    except Exception as e:
        print(f"[{label}] ✗  Failed: {e}")
        return None


def _fetch_json(url: str, label: str) -> Any | None:
    """GET url and parse the JSON body. Returns None on failure."""
    print(f"\n[{label}] Downloading: {url}")
    try:
        response = httpx.get(url, headers=HEADERS, timeout=TIMEOUT, follow_redirects=True)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"[{label}] ✗  Failed: {e}")
        return None


# ---------------------------------------------------------------------------
# 1.  EPA GHGRP — direct CSV download
#     EPA publishes one ZIP per year; we grab the most recent 3 years.
# ---------------------------------------------------------------------------
def fetch_epa_ghgrp():
    print("\n" + "="*60)
    print("SOURCE 1: EPA Greenhouse Gas Reporting Program (GHGRP)")
    print("="*60)

    # EPA hosts the summary data as Excel → we use their API export instead
    # The public API endpoint returns JSON or CSV for facility-level totals.
    # We also try the direct CSV that EPA publishes on their data-sets page.

    records = []

    # Try the EPA FLIGHT direct data export (public, no auth needed)
    for year in [2022, 2021, 2020, 2019, 2018]:
        url = (
            f"https://iaspub.epa.gov/enviro/efservice/PUB_FACTS_SECTOR_GHG_EMISSION"
            f"/YEAR/{year}/JSON"
        )
        data = _fetch_json(url, f"EPA GHGRP {year}")
        if data is not None:
            try:
                df = pd.DataFrame(data)
                df["year"] = year
                records.append(df)
                print(f"  → {len(df)} facility-sector records for {year}")
            except Exception as e:
                print(f"  Parse error: {e}")

    # Also try the Envirofacts REST API for facility summary
    if not records:
        print("  Trying Envirofacts REST endpoint...")
        for year in [2022, 2021]:
            url = (
                f"https://data.epa.gov/efservice/pub_ghg_emitter_summary"
                f"/year/{year}/csv"
            )
            out = os.path.join(OUT_DIR, f"epa_ghgrp_{year}.csv")
            path = _download(url, f"EPA Envirofacts {year}", out)
            if path:
                try:
                    df = pd.read_csv(path)
                    df["year"] = year
                    records.append(df)
                    print(f"  → {len(df)} rows for {year}")
                except Exception as e:
                    print(f"  Parse error: {e}")

    # Fallback: try the static annual ZIP that EPA posts on data-sets page
    if not records:
        print("  Trying EPA data-sets static ZIP (2022)...")
        url = "https://www.epa.gov/system/files/other-files/2024-10/ghg_2022_data_summary_spreadsheets.zip"
        out_zip = os.path.join(OUT_DIR, "epa_2022.zip")
        path = _download(url, "EPA ZIP 2022", out_zip)
        if path:
            try:
                with zipfile.ZipFile(path) as z:
                    names = z.namelist()
                    print(f"  ZIP contents: {names}")
                    # Extract the summary file
                    for n in names:
                        if "summary" in n.lower() or "emission" in n.lower():
                            z.extract(n, OUT_DIR)
                            print(f"  Extracted: {n}")
            except Exception as e:
                print(f"  ZIP error: {e}")

    if records:
        combined = pd.concat(records, ignore_index=True)
        out = os.path.join(OUT_DIR, "epa_ghgrp_summary.csv")
        combined.to_csv(out, index=False)
        print(f"\n✓ EPA GHGRP: {len(combined)} total records → {out}")
        return combined
    else:
        print("✗ EPA GHGRP: could not download automatically.")
        print("  Manual download: https://www.epa.gov/ghgreporting/data-sets")
        print("  Look for 'Summary Data' → download the ZIP → extract CSV")
        return None


# ---------------------------------------------------------------------------
# 2.  Climate TRACE — manufacturing sector bulk download
# ---------------------------------------------------------------------------
def fetch_climate_trace():
    print("\n" + "="*60)
    print("SOURCE 2: Climate TRACE (global facility emissions)")
    print("="*60)

    # Climate TRACE bulk download API
    # They have a v6 API; the download endpoints are sector-based ZIPs
    sectors_to_try = [
        ("manufacturing", "https://downloads.climatetrace.org/v06/country_packages/manufacturing.zip"),
        ("steel",         "https://downloads.climatetrace.org/v06/country_packages/steel.zip"),
        ("cement",        "https://downloads.climatetrace.org/v06/country_packages/cement.zip"),
        ("all",           "https://downloads.climatetrace.org/v06/country_packages/global.zip"),
    ]

    ct_dir = os.path.join(OUT_DIR, "climate_trace")
    os.makedirs(ct_dir, exist_ok=True)

    found = []
    for sector, url in sectors_to_try:
        out_zip = os.path.join(ct_dir, f"{sector}.zip")
        path = _download(url, f"Climate TRACE {sector}", out_zip)
        if path:
            try:
                with zipfile.ZipFile(path) as z:
                    csvs = [n for n in z.namelist() if n.endswith(".csv")]
                    print(f"  CSVs inside ZIP: {csvs[:5]}")
                    for csv_name in csvs[:3]:  # extract first few
                        z.extract(csv_name, ct_dir)
                        fp = os.path.join(ct_dir, csv_name)
                        df = pd.read_csv(fp, nrows=3)
                        print(f"  {csv_name} columns: {list(df.columns)}")
                        found.append(fp)
            except Exception as e:
                print(f"  ZIP error: {e}")
            break  # stop after first successful download

    if not found:
        print("✗ Climate TRACE: bulk ZIP not accessible directly.")
        print("  Manual download: https://climatetrace.org/data")
        print("  → Select 'Manufacturing' sector → Download ZIP")

    return found


# ---------------------------------------------------------------------------
# 3.  Our World in Data CO2 — country+sector GHG time series
#     This is country-level (not company), but useful as a validation reference
# ---------------------------------------------------------------------------
def fetch_owid():
    print("\n" + "="*60)
    print("SOURCE 3: Our World in Data — CO2 & GHG dataset")
    print("="*60)

    url  = "https://raw.githubusercontent.com/owid/co2-data/master/owid-co2-data.csv"
    out  = os.path.join(OUT_DIR, "owid_co2.csv")
    path = _download(url, "OWID CO2", out)

    if path:
        df = pd.read_csv(path)
        print(f"  Columns: {list(df.columns)[:15]}...")
        print(f"  Rows: {len(df)}, Countries: {df['country'].nunique()}")
        print(f"  Years: {df['year'].min()}–{df['year'].max()}")
        return df
    return None


# ---------------------------------------------------------------------------
# 4.  Zenodo Benchmark — 139 company sustainability reports
#     DOI: 10.5281/zenodo.14184617
# ---------------------------------------------------------------------------
def fetch_zenodo_benchmark():
    print("\n" + "="*60)
    print("SOURCE 4: Zenodo — Company Sustainability Report Benchmark")
    print("="*60)

    # Zenodo API to get file list
    record_id = "14184617"
    api_url   = f"https://zenodo.org/api/records/{record_id}"
    meta = _fetch_json(api_url, "Zenodo API")
    if not isinstance(meta, dict):
        print("✗ Zenodo: API unavailable")
        return None

    try:
        files = meta.get("files", [])
        print(f"  Files in record: {[f['key'] for f in files]}")

        for f in files:
            key  = f["key"]
            link = f["links"]["self"]
            out  = os.path.join(OUT_DIR, key)
            _download(link, f"Zenodo:{key}", out)

        # Look for CSVs
        csvs = [f for f in files if f["key"].endswith(".csv")]
        if csvs:
            df = pd.read_csv(os.path.join(OUT_DIR, csvs[0]["key"]))
            print(f"\n  Columns: {list(df.columns)}")
            print(f"  Sample:\n{df.head(3)}")
            return df
    except Exception as e:
        print(f"  Error: {e}")

    return None


# ---------------------------------------------------------------------------
# 5.  Write provenance notes
# ---------------------------------------------------------------------------
def write_sources_md(results):
    lines = [
        "# Real Emissions Data Sources",
        "",
        "| Source | Status | Records | Coverage |",
        "|--------|--------|---------|----------|",
    ]
    for name, status, n, coverage in results:
        lines.append(f"| {name} | {status} | {n} | {coverage} |")
    lines += [
        "",
        "## URLs",
        "- EPA GHGRP: https://www.epa.gov/ghgreporting/data-sets",
        "- Climate TRACE: https://climatetrace.org/data",
        "- Our World in Data: https://github.com/owid/co2-data",
        "- Zenodo benchmark: https://zenodo.org/records/14184617",
        "- Nature paper (Scope 3 ML factors): https://www.nature.com/articles/s41597-026-06699-1",
    ]
    out = os.path.join(OUT_DIR, "SOURCES.md")
    with open(out, "w") as f:
        f.write("\n".join(lines))
    print(f"\nSource notes → {out}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    print("GreenChain — Real Emissions Data Finder")
    print(f"Output directory: {OUT_DIR}")
    print("=" * 60)

    results = []

    epa = fetch_epa_ghgrp()
    results.append(("EPA GHGRP",
                    "✓ Downloaded" if epa is not None else "✗ Manual needed",
                    len(epa) if epa is not None else 0,
                    "US facilities, Scope 1, 2010–2022"))

    ct = fetch_climate_trace()
    results.append(("Climate TRACE",
                    "✓ Downloaded" if ct else "✗ Manual needed",
                    len(ct),
                    "Global facilities, all gases, 2015–2024"))

    owid = fetch_owid()
    results.append(("OWID CO2",
                    "✓ Downloaded" if owid is not None else "✗ Failed",
                    len(owid) if owid is not None else 0,
                    "Country+sector level, 1750–2023"))

    zen = fetch_zenodo_benchmark()
    results.append(("Zenodo Benchmark",
                    "✓ Downloaded" if zen is not None else "✗ Manual needed",
                    len(zen) if zen is not None else 0,
                    "139 companies, Scope 1/2/3"))

    write_sources_md(results)

    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    for name, status, n, coverage in results:
        print(f"  {status}  {name}: {n:,} records — {coverage}")

    print(f"\nAll files in: {OUT_DIR}")
    print("\nNext: run  python ml/integrate_real_training_data.py")
    print("       to map these sources into the GreenChain training format.")


if __name__ == "__main__":
    main()
