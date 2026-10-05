"""
generate_training_data.py
--------------------------
Generates a realistic synthetic CDP Supply Chain dataset (~15,000 records).

The CDP dataset structure:
  - supplier_name, country_iso, naics_code, year, revenue_$M,
    reported_scope1_tCO2e, reported_scope2_tCO2e, total_tCO2e,
    tCO2e_per_$M_spend   (target variable for our model)

We use:
  - USEEIO sector base intensities  (industry signal)
  - Ember grid carbon intensity      (country-year signal)
  - Country emission multiplier      (manufacturing context)
  - Lognormal noise (realistic spread; CDP actual data has high variance)

Run:
    python ml/generate_training_data.py
Outputs:
    data/raw/cdp_synthetic.csv        (raw)
    data/processed/cdp_features.csv   (model-ready)
"""

import os
import sys
from typing import cast

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from ml.reference_data import (
    NAICS_DETAIL, EMBER_GRID_INTENSITY,
    COUNTRY_EMISSION_MULTIPLIER
)

RAW_OUT   = "data/raw/cdp_synthetic.csv"
FEAT_OUT  = "data/processed/cdp_features.csv"

SEED = 42
N_RECORDS = 15_000
YEARS = [2018, 2019, 2020, 2021, 2022, 2023]

# Countries in CDP supply-chain reports (with rough frequency weights)
COUNTRY_WEIGHTS = {
    "CN": 0.20, "IN": 0.10, "US": 0.08, "DE": 0.06, "JP": 0.06,
    "VN": 0.05, "BD": 0.05, "KR": 0.04, "TW": 0.04, "MX": 0.04,
    "BR": 0.03, "ID": 0.03, "TH": 0.03, "TR": 0.03, "PK": 0.02,
    "PL": 0.02, "IT": 0.02, "ES": 0.02, "FR": 0.02, "GB": 0.02,
    "PT": 0.01, "NL": 0.01, "BE": 0.01, "MY": 0.01, "PH": 0.01,
}

REVENUE_BANDS = {
    "small":  (5,   50,   0.35),   # $M range, weight
    "medium": (50,  500,  0.45),
    "large":  (500, 5000, 0.20),
}

def pick_revenue() -> float:
    rng = np.random.default_rng(None)
    band = rng.choice(["small", "medium", "large"],
                      p=[v[2] for v in REVENUE_BANDS.values()])
    lo, hi, _ = REVENUE_BANDS[band]
    return float(rng.uniform(lo, hi))

def simulate_intensity(naics4: str, country: str, year: int, rng) -> float:
    """
    Simulate tCO2e per $1M spend for a supplier.
    = base_useeio_intensity × grid_factor × country_multiplier × noise
    """
    parent2, _, base_kg = NAICS_DETAIL[naics4]
    base = base_kg / 1_000  # convert to tCO2e per $1M

    # Grid carbon factor (higher grid → higher scope 2 burden)
    grid = EMBER_GRID_INTENSITY.get(country, 450)  # gCO2/kWh
    grid_factor = grid / 400.0  # normalised to world avg ~400 gCO2/kWh

    # Country manufacturing multiplier
    country_mult = COUNTRY_EMISSION_MULTIPLIER.get(country, 1.0)

    # Year trend: slight efficiency improvement ~1.5%/yr since 2018
    year_factor = 0.985 ** (year - 2018)

    mu = base * grid_factor * country_mult * year_factor

    # Lognormal noise — CDP data has sigma ~0.6 on log scale (realistic)
    log_mu = np.log(max(mu, 0.1))
    log_sigma = 0.55 + rng.uniform(-0.1, 0.1)
    intensity = float(np.exp(rng.normal(log_mu, log_sigma)))
    return round(intensity, 2)


def generate(n: int = N_RECORDS, seed: int = SEED) -> pd.DataFrame:
    rng = np.random.default_rng(seed)

    naics_codes = list(NAICS_DETAIL.keys())
    countries   = list(COUNTRY_WEIGHTS.keys())
    country_p   = np.array(list(COUNTRY_WEIGHTS.values()))
    country_p  /= country_p.sum()

    records = []
    for i in range(n):
        country  = rng.choice(countries, p=country_p)
        naics4   = rng.choice(naics_codes)
        year     = int(rng.choice(YEARS))
        revenue  = pick_revenue()

        # Revenue band (log-scaled, 0=tiny, 4=huge)
        rev_band = np.log10(revenue)

        intensity = simulate_intensity(naics4, country, year, rng)
        total_tco2e = intensity * revenue

        # Scope split: roughly 30% scope1, 70% scope2+3 (upstream)
        scope1 = total_tco2e * rng.uniform(0.15, 0.45)
        scope2 = total_tco2e - scope1

        records.append({
            "supplier_id":       f"SUP{i:06d}",
            "country_iso":       country,
            "naics4":            naics4,
            "naics2":            NAICS_DETAIL[naics4][0],
            "sector":            NAICS_DETAIL[naics4][1],
            "year":              year,
            "revenue_usd_m":     round(revenue, 2),
            "log_revenue":       round(rev_band, 4),
            "grid_intensity_gco2_kwh": EMBER_GRID_INTENSITY.get(country, 450),
            "scope1_tco2e":      round(scope1, 1),
            "scope2_tco2e":      round(scope2, 1),
            "total_tco2e":       round(total_tco2e, 1),
            "tco2e_per_usdm":    intensity,   # TARGET variable
        })

    return pd.DataFrame(records)


def main():
    os.makedirs("data/raw",       exist_ok=True)
    os.makedirs("data/processed", exist_ok=True)

    print(f"Generating {N_RECORDS} synthetic CDP supplier records...")
    df = generate()

    df.to_csv(RAW_OUT, index=False)
    print(f"  Saved raw  → {RAW_OUT}  ({len(df)} rows)")

    # Feature-engineered version (one-hot encode naics2, country)
    feat = df[[
        "supplier_id", "country_iso", "naics4", "naics2", "year",
        "log_revenue", "grid_intensity_gco2_kwh", "tco2e_per_usdm",
        "total_tco2e", "revenue_usd_m"
    ]].copy()

    # One-hot encode country
    country_dummies = pd.get_dummies(feat["country_iso"], prefix="ctry")
    # One-hot encode naics2
    naics2_dummies  = pd.get_dummies(feat["naics2"],      prefix="nac")

    feat_encoded = pd.concat([
        cast(pd.DataFrame, feat[["supplier_id", "year", "log_revenue", "grid_intensity_gco2_kwh",
                                 "tco2e_per_usdm", "total_tco2e", "revenue_usd_m"]]),
        country_dummies,
        naics2_dummies,
    ], axis=1)

    feat_encoded.to_csv(FEAT_OUT, index=False)
    print(f"  Saved feat → {FEAT_OUT}  ({len(feat_encoded)} rows, {len(feat_encoded.columns)} cols)")

    # Summary stats
    print("\n── Intensity distribution (tCO2e/$1M) ──")
    print(df["tco2e_per_usdm"].describe().round(1))
    print("\n── Top 5 countries by mean intensity ──")
    country_means = cast(pd.Series, df.groupby("country_iso")["tco2e_per_usdm"].mean())
    print(country_means.sort_values(ascending=False).head(5).round(1))
    print("\n── Bottom 5 countries (cleanest) ──")
    print(country_means.sort_values().head(5).round(1))


if __name__ == "__main__":
    main()
