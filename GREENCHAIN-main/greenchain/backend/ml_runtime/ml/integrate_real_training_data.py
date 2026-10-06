"""
integrate_real_training_data.py
--------------------------------
Scans new_data2/real_emissions/ for any downloaded files and converts them
into GreenChain's training format (same schema as cdp_synthetic.csv):

  supplier_id, country_iso, naics4, naics2, sector, year,
  revenue_usd_m, log_revenue, grid_intensity_gco2_kwh,
  scope1_tco2e, scope2_tco2e, total_tco2e, tco2e_per_usdm

Handles:
  - EPA GHGRP: facility-level Scope 1, NAICS codes, no revenue → imputed
  - Climate TRACE: facility-level emissions, lat/lon → country mapped
  - Zenodo benchmark: company-level Scope 1+2, sector
  - OWID: country-sector → used only for validation, not training

Run:
    python ml/integrate_real_training_data.py

Output:
    data/raw/cdp_real.csv        — real records in training format
    data/raw/cdp_combined.csv    — real + synthetic (padded to 15k min)
"""

import glob
import os
import sys
import warnings
from typing import cast

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

_THIS_DIR     = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
DATA_DIR      = os.path.join(_PROJECT_ROOT, "data", "raw")
SEED          = 42
rng           = np.random.default_rng(SEED)

sys.path.insert(0, _PROJECT_ROOT)
from ml.load_real_data import resolve_data_dir  # noqa: E402  (needs the sys.path entry above)
from ml.reference_data import (  # noqa: E402
    EMBER_GRID_INTENSITY, USEEIO_FACTORS, NAICS_DETAIL,
)

# find_real_data.py downloads into the same new_data2/ folder the app loads from.
REAL_DIR      = os.path.join(resolve_data_dir("new_data2"), "real_emissions")

# NAICS4 → naics2, sector name lookup
_N4_META: dict[str, tuple[str, str]] = {}
for code, (n2, title, val) in NAICS_DETAIL.items():
    n4 = code[:4]
    _N4_META.setdefault(n4, (n2, title))


def _naics4_meta(n4):
    s = str(n4)[:4]
    return _N4_META.get(s, ("99", "Unknown"))


def _grid(iso2):
    return EMBER_GRID_INTENSITY.get(str(iso2).upper(), 450.0)


def _impute_revenue(scope1, naics4):
    """
    Impute revenue from emissions using USEEIO intensity as anchor.
    revenue ≈ scope1 / (useeio_intensity / 1e6) with lognormal noise.
    """
    n4 = str(naics4)[:4]
    # Find closest USEEIO code
    intensity = None
    for length in [6, 5, 4, 3, 2]:
        key = n4[:length] + "0" * (6 - length) if length < 6 else n4 + "00"
        if key in USEEIO_FACTORS:
            intensity = USEEIO_FACTORS[key][1]  # kgCO2e per $1M
            break
    if intensity is None:
        intensity = 500_000  # fallback ~$500k tCO2e/$1M

    # tco2e_per_usdm = scope1_tco2e / revenue_usdm
    # → revenue_usdm = scope1_tco2e / (intensity / 1e6)
    tco2e_per_usdm_expected = intensity / 1_000  # kg → tonnes: /1000
    rev = scope1 / max(tco2e_per_usdm_expected, 0.001)
    # Add lognormal noise σ=0.4
    rev = rev * float(rng.lognormal(0, 0.4, 1)[0])
    return max(rev, 0.1)


# ---------------------------------------------------------------------------
# 1.  EPA GHGRP loader
# ---------------------------------------------------------------------------
def load_epa_ghgrp() -> pd.DataFrame:
    """Load EPA GHGRP summary CSV(s) from real_emissions/"""
    patterns = [
        os.path.join(REAL_DIR, "epa_ghgrp*.csv"),
        os.path.join(REAL_DIR, "**", "*.csv"),  # extracted from ZIP
    ]
    files = []
    for pat in patterns:
        files.extend(glob.glob(pat, recursive=True))
    files = list(set(files))

    records = []
    for fp in files:
        try:
            df = pd.read_csv(fp, low_memory=False)
            cols = [c.lower() for c in df.columns]
            df.columns = pd.Index(cols)

            # Detect EPA GHGRP format
            ghg_col = next((c for c in cols if "ghg" in c and "quant" in c), None)
            naics_col = next((c for c in cols if "naics" in c), None)
            year_col  = next((c for c in cols if "year" in c or "report" in c), None)

            if ghg_col and naics_col:
                print(f"  [EPA] Found GHGRP file: {os.path.basename(fp)} ({len(df)} rows)")
                print(f"        Columns: {list(df.columns)[:8]}")
                sub = cast(pd.DataFrame, df[[naics_col, ghg_col]]).copy()
                sub.columns = pd.Index(["naics_raw", "scope1_tco2e"])
                if year_col:
                    sub["year"] = df[year_col]
                else:
                    sub["year"] = 2022
                sub["country_iso"] = "US"  # GHGRP is US-only
                sub = sub.dropna(subset="scope1_tco2e")
                sub["scope1_tco2e"] = pd.to_numeric(sub["scope1_tco2e"], errors="coerce")
                sub = sub[sub["scope1_tco2e"] > 0]
                records.append(sub)
        except Exception as e:
            print(f"  [EPA] Could not parse {fp}: {e}")

    if not records:
        return pd.DataFrame()

    df = pd.concat(records, ignore_index=True)

    # Normalise NAICS → 4-digit
    df["naics4"] = df["naics_raw"].astype(str).str[:4].str.zfill(4)
    df["naics4"] = pd.to_numeric(df["naics4"], errors="coerce")
    df["naics4"] = df["naics4"].fillna(9999).astype(int)

    # Scope 2 estimated from grid + operational energy (rough)
    df["scope2_tco2e"] = df["scope1_tco2e"] * rng.uniform(0.05, 0.4, len(df))
    df["total_tco2e"]  = df["scope1_tco2e"] + df["scope2_tco2e"]

    # Revenue imputed from USEEIO
    df["revenue_usd_m"] = [
        _impute_revenue(s1, n4) for s1, n4 in zip(df["scope1_tco2e"], df["naics4"])
    ]
    df["tco2e_per_usdm"] = df["total_tco2e"] / df["revenue_usd_m"].clip(lower=0.01)

    # Grid intensity
    df["grid_intensity_gco2_kwh"] = df["country_iso"].map(_grid)

    print(f"  [EPA] → {len(df)} records processed")
    return df


# ---------------------------------------------------------------------------
# 2.  Climate TRACE loader
# ---------------------------------------------------------------------------
def load_climate_trace() -> pd.DataFrame:
    """Load Climate TRACE CSV files from real_emissions/climate_trace/"""
    ct_dir  = os.path.join(REAL_DIR, "climate_trace")
    files   = glob.glob(os.path.join(ct_dir, "**", "*.csv"), recursive=True)
    records = []

    for fp in files:
        try:
            df = pd.read_csv(fp, low_memory=False)
            cols = [c.lower().strip() for c in df.columns]
            df.columns = pd.Index(cols)

            # Climate TRACE columns: asset_id, asset_name, country, year, co2, ...
            country_col = next((c for c in cols if c in ["iso3_country","country","iso"]), None)
            emiss_col   = next((c for c in cols if "co2" in c and "emiss" in c), None)
            year_col    = next((c for c in cols if c == "year"), None)
            sector_col  = next((c for c in cols if "sector" in c or "subsector" in c), None)

            if country_col and emiss_col:
                print(f"  [CT] Found: {os.path.basename(fp)} ({len(df)} rows)")
                print(f"       Columns: {list(df.columns)[:8]}")
                sub = pd.DataFrame()
                sub["country_raw"]   = df[country_col]
                sub["scope1_tco2e"]  = pd.to_numeric(df[emiss_col], errors="coerce")
                sub["year"]          = df[year_col] if year_col else 2022
                sub["sector_raw"]    = df[sector_col].astype(str) if sector_col else "manufacturing"
                sub = sub.dropna(subset="scope1_tco2e")
                sub = sub[sub["scope1_tco2e"] > 0]
                records.append(sub)
        except Exception as e:
            print(f"  [CT] Could not parse {fp}: {e}")

    if not records:
        return pd.DataFrame()

    # ISO3 → ISO2
    from ml.load_real_data import ISO3_TO_ISO2
    df = pd.concat(records, ignore_index=True)
    df["country_iso"] = df["country_raw"].map(
        lambda x: ISO3_TO_ISO2.get(str(x).upper(), str(x).upper()[:2])
    )

    # Sector → NAICS4 (rough mapping)
    SECTOR_NAICS = {
        "steel": 3312, "cement": 3273, "aluminum": 3313,
        "chemicals": 3251, "pulp": 3221, "glass": 3272,
        "manufacturing": 3390, "oil": 3241, "gas": 2111,
        "power": 2211, "agriculture": 1110, "shipping": 4831,
    }
    def _sector_to_naics(s):
        s = str(s).lower()
        for k, v in SECTOR_NAICS.items():
            if k in s:
                return v
        return 3390  # generic manufacturing

    df["naics4"] = df["sector_raw"].map(_sector_to_naics)
    df["scope2_tco2e"] = df["scope1_tco2e"] * rng.uniform(0.03, 0.25, len(df))
    df["total_tco2e"]  = df["scope1_tco2e"] + df["scope2_tco2e"]
    df["revenue_usd_m"] = [
        _impute_revenue(s1, n4) for s1, n4 in zip(df["scope1_tco2e"], df["naics4"])
    ]
    df["tco2e_per_usdm"]        = df["total_tco2e"] / df["revenue_usd_m"].clip(lower=0.01)
    df["grid_intensity_gco2_kwh"] = df["country_iso"].map(_grid)

    print(f"  [CT] → {len(df)} records processed")
    return df


# ---------------------------------------------------------------------------
# 3.  Zenodo benchmark loader
# ---------------------------------------------------------------------------
def load_zenodo() -> pd.DataFrame:
    """Load the 139-company benchmark dataset."""
    patterns = [
        os.path.join(REAL_DIR, "*benchmark*"),
        os.path.join(REAL_DIR, "*zenodo*"),
        os.path.join(REAL_DIR, "*.csv"),
    ]
    files = []
    for pat in patterns:
        files.extend(glob.glob(pat))
    # The patterns overlap (e.g. zenodo_benchmark.csv matches all three), so
    # de-duplicate or the same records are loaded several times.
    files = [f for f in dict.fromkeys(files)
             if "epa" not in f.lower() and "owid" not in f.lower()
             and "sources" not in f.lower()]

    records = []
    for fp in files:
        if not fp.endswith(".csv"):
            continue
        try:
            df = pd.read_csv(fp, low_memory=False)
            cols = [c.lower() for c in df.columns]
            df.columns = pd.Index(cols)

            scope1_col  = next((c for c in cols if "scope1" in c or "scope_1" in c), None)
            scope2_col  = next((c for c in cols if "scope2" in c or "scope_2" in c), None)
            country_col = next((c for c in cols if "country" in c or "iso" in c), None)
            revenue_col = next((c for c in cols if "revenue" in c or "turnover" in c), None)
            sector_col  = next((c for c in cols if "sector" in c or "industry" in c or "naics" in c), None)

            if scope1_col:
                print(f"  [Zenodo] Found: {os.path.basename(fp)} ({len(df)} rows)")
                sub = pd.DataFrame()
                sub["scope1_tco2e"] = pd.to_numeric(df[scope1_col], errors="coerce")
                sub["scope2_tco2e"] = pd.to_numeric(df[scope2_col], errors="coerce") if scope2_col else 0
                sub["scope2_tco2e"] = sub["scope2_tco2e"].fillna(0)
                sub["country_iso"]  = df[country_col].astype(str).str[:2].str.upper() if country_col else "US"
                sub["revenue_usd_m"]= pd.to_numeric(df[revenue_col], errors="coerce") if revenue_col else np.nan
                sub["sector_raw"]   = df[sector_col].astype(str) if sector_col else "Unknown"
                sub["year"]         = 2022
                sub = sub.dropna(subset="scope1_tco2e")
                sub = sub[sub["scope1_tco2e"] > 0]
                records.append(sub)
        except Exception as e:
            print(f"  [Zenodo] Could not parse {fp}: {e}")

    if not records:
        return pd.DataFrame()

    df = pd.concat(records, ignore_index=True)
    df["total_tco2e"] = df["scope1_tco2e"] + df["scope2_tco2e"]
    df["naics4"] = 3390  # generic manufacturing (sector mapping would need lookup table)

    # Impute revenue where missing
    mask = df["revenue_usd_m"].isna()
    df.loc[mask, "revenue_usd_m"] = [
        _impute_revenue(s1, n4)
        for s1, n4 in zip(df.loc[mask, "scope1_tco2e"], df.loc[mask, "naics4"])
    ]
    df["tco2e_per_usdm"]          = df["total_tco2e"] / df["revenue_usd_m"].clip(lower=0.01)
    df["grid_intensity_gco2_kwh"] = df["country_iso"].map(_grid)
    print(f"  [Zenodo] → {len(df)} records processed")
    return df


# ---------------------------------------------------------------------------
# Final assembly → training format
# ---------------------------------------------------------------------------
def assemble(frames: list) -> pd.DataFrame:
    if not frames:
        return pd.DataFrame()

    df = pd.concat(frames, ignore_index=True)

    # Add naics2 + sector name
    df["naics4"] = pd.to_numeric(df["naics4"], errors="coerce")
    df["naics4"] = df["naics4"].fillna(9999).astype(int)
    metas = [_naics4_meta(n4) for n4 in df["naics4"]]
    df["naics2"] = [m[0] for m in metas]
    df["sector"] = [m[1] for m in metas]

    # Log features
    df["log_revenue"] = np.log10(df["revenue_usd_m"].clip(lower=0.01))  # log10 to match training
    df["year"] = pd.to_numeric(df["year"], errors="coerce")
    df["year"] = df["year"].fillna(2022).astype(int)

    # Remove outliers (>99.5th percentile)
    p995 = df["tco2e_per_usdm"].quantile(0.995)
    df = df[df["tco2e_per_usdm"] <= p995].copy()

    # Assign supplier IDs
    df.insert(0, "supplier_id", pd.Series([f"REAL{i:06d}" for i in range(len(df))], index=df.index))

    cols = ["supplier_id", "country_iso", "naics4", "naics2", "sector", "year",
            "revenue_usd_m", "log_revenue", "grid_intensity_gco2_kwh",
            "scope1_tco2e", "scope2_tco2e", "total_tco2e", "tco2e_per_usdm"]
    return cast(pd.DataFrame, df[[c for c in cols if c in df.columns]])


def main():
    print("GreenChain — Integrate Real Training Data")
    print("=" * 60)

    frames = []

    print("\nScanning EPA GHGRP...")
    epa = load_epa_ghgrp()
    if len(epa):
        frames.append(epa)

    print("\nScanning Climate TRACE...")
    ct = load_climate_trace()
    if len(ct):
        frames.append(ct)

    print("\nScanning Zenodo benchmark...")
    zen = load_zenodo()
    if len(zen):
        frames.append(zen)

    if not frames:
        print("\n⚠️  No real data files found in new_data2/real_emissions/")
        print("   Run: python ml/find_real_data.py  (from your Mac terminal)")
        print("   OR manually download from the URLs in find_real_data.py")
        return

    real = assemble(frames)
    real_path = os.path.join(DATA_DIR, "cdp_real.csv")
    real.to_csv(real_path, index=False)
    print(f"\n✓ Real records: {len(real)} → {real_path}")
    print(f"  Countries: {real['country_iso'].nunique()}")
    print(f"  NAICS2 sectors: {real['naics2'].nunique()}")
    print(f"  Years: {real['year'].min()}–{real['year'].max()}")
    print(f"  tco2e_per_usdm range: {real['tco2e_per_usdm'].min():.1f}–{real['tco2e_per_usdm'].max():.1f}")

    # Combine with synthetic to pad to at least 10k records
    synth_path = os.path.join(DATA_DIR, "cdp_synthetic.csv")
    if os.path.exists(synth_path):
        synth = pd.read_csv(synth_path)
        # Use synthetic only to pad if real < 10k
        target = max(len(real) * 2, 10_000)
        n_synth = max(0, target - len(real))
        synth_sample = synth.sample(min(n_synth, len(synth)), random_state=SEED)
        combined = pd.concat([real, synth_sample], ignore_index=True)
        combined_path = os.path.join(DATA_DIR, "cdp_combined.csv")
        combined.to_csv(combined_path, index=False)
        print(f"\n✓ Combined (real + {len(synth_sample)} synthetic): {len(combined)} → {combined_path}")
        print("  → Use cdp_combined.csv as RAW_CSV in train_model.py")
    else:
        print("  (no synthetic file found to combine with)")

    print("\nNext step: update RAW_CSV in ml/train_model.py to:")
    print('   RAW_CSV = "data/raw/cdp_combined.csv"')
    print("Then: python ml/train_model.py")


if __name__ == "__main__":
    main()
