"""
load_real_data.py
-----------------
Loads and normalises the three real datasets from new_data/ and new_data2/.

Provides:
  load_ember()    -> dict  {iso2: gCO2/kWh}   214 countries, latest year
  load_ndgain()   -> dict  {iso2: risk_score}  192 countries, 2023
  load_useeio()   -> dict  {naics6: (title, kgco2e_per_usdM)}  1016 codes

ISO3 -> ISO2 mapping is handled internally.
"""

import math
import os
import warnings
from typing import cast

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

_THIS_DIR     = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
# Repo layout: <repo>/backend/ml_runtime/ml/ -> datasets live in <repo>/data/.
_REPO_DATA    = os.path.join(os.path.dirname(os.path.dirname(_PROJECT_ROOT)), "data")


# A file each dataset folder must contain to count as the real one.
_DATA_MARKERS = {
    "new_data2": "yearly_full_release_long_format.csv",
    "new_data":  "SupplyChainGHGEmissionFactors_v1.3.0_NAICS_CO2e_USD2022.csv",
}


def resolve_data_dir(subdir: str) -> str:
    """
    Locate a dataset folder (``new_data`` or ``new_data2``).

    Checks, in order: $GREENCHAIN_DATA_DIR, the original ml_runtime/ layout,
    then the repo-level data/ folder. Prefers the first candidate that holds
    the dataset's marker file (an empty folder left by a download script must
    not shadow the real data), then the first that exists, then the
    ml_runtime/ path so error messages still point somewhere sensible.
    """
    candidates = []
    env_dir = os.environ.get("GREENCHAIN_DATA_DIR", "").strip()
    if env_dir:
        candidates.append(os.path.join(os.path.expanduser(env_dir), subdir))
    candidates.append(os.path.join(_PROJECT_ROOT, subdir))
    candidates.append(os.path.join(_REPO_DATA, subdir))

    marker = _DATA_MARKERS.get(subdir)
    if marker:
        for candidate in candidates:
            if os.path.isfile(os.path.join(candidate, marker)):
                return candidate
    for candidate in candidates:
        if os.path.isdir(candidate):
            return candidate
    return os.path.join(_PROJECT_ROOT, subdir)


_NEW_DATA     = resolve_data_dir("new_data2")
_NEW_DATA_OLD = resolve_data_dir("new_data")

# ---------------------------------------------------------------------------
# ISO3 <-> ISO2 mapping  (covers all countries in Ember + ND-GAIN)
# ---------------------------------------------------------------------------
ISO3_TO_ISO2 = {
    "AFG":"AF","ALB":"AL","DZA":"DZ","AND":"AD","AGO":"AO","ARG":"AR","ARM":"AM",
    "AUS":"AU","AUT":"AT","AZE":"AZ","BHS":"BS","BHR":"BH","BGD":"BD","BLR":"BY",
    "BEL":"BE","BLZ":"BZ","BEN":"BJ","BTN":"BT","BOL":"BO","BIH":"BA","BWA":"BW",
    "BRA":"BR","BRN":"BN","BGR":"BG","BFA":"BF","BDI":"BI","CPV":"CV","KHM":"KH",
    "CMR":"CM","CAN":"CA","CAF":"CF","TCD":"TD","CHL":"CL","CHN":"CN","COL":"CO",
    "COD":"CD","COG":"CG","CRI":"CR","HRV":"HR","CUB":"CU","CYP":"CY","CZE":"CZ",
    "DNK":"DK","DJI":"DJ","DOM":"DO","ECU":"EC","EGY":"EG","SLV":"SV","GNQ":"GQ",
    "ERI":"ER","EST":"EE","SWZ":"SZ","ETH":"ET","FJI":"FJ","FIN":"FI","FRA":"FR",
    "GAB":"GA","GMB":"GM","GEO":"GE","DEU":"DE","GHA":"GH","GRC":"GR","GTM":"GT",
    "GIN":"GN","GNB":"GW","GUY":"GY","HTI":"HT","HND":"HN","HUN":"HU","ISL":"IS",
    "IND":"IN","IDN":"ID","IRN":"IR","IRQ":"IQ","IRL":"IE","ISR":"IL","ITA":"IT",
    "JAM":"JM","JPN":"JP","JOR":"JO","KAZ":"KZ","KEN":"KE","PRK":"KP","KOR":"KR",
    "KWT":"KW","KGZ":"KG","LAO":"LA","LVA":"LV","LBN":"LB","LSO":"LS","LBR":"LR",
    "LBY":"LY","LTU":"LT","LUX":"LU","MDG":"MG","MWI":"MW","MYS":"MY","MDV":"MV",
    "MLI":"ML","MLT":"MT","MRT":"MR","MUS":"MU","MEX":"MX","MDA":"MD","MNG":"MN",
    "MNE":"ME","MAR":"MA","MOZ":"MZ","MMR":"MM","NAM":"NA","NPL":"NP","NLD":"NL",
    "NZL":"NZ","NIC":"NI","NER":"NE","NGA":"NG","MKD":"MK","NOR":"NO","OMN":"OM",
    "PAK":"PK","PAN":"PA","PNG":"PG","PRY":"PY","PER":"PE","PHL":"PH","POL":"PL",
    "PRT":"PT","QAT":"QA","ROU":"RO","RUS":"RU","RWA":"RW","SAU":"SA","SEN":"SN",
    "SRB":"RS","SLE":"SL","SGP":"SG","SVK":"SK","SVN":"SI","SOM":"SO","ZAF":"ZA",
    "SSD":"SS","ESP":"ES","LKA":"LK","SDN":"SD","SUR":"SR","SWE":"SE","CHE":"CH",
    "SYR":"SY","TWN":"TW","TJK":"TJ","TZA":"TZ","THA":"TH","TLS":"TL","TGO":"TG",
    "TTO":"TT","TUN":"TN","TUR":"TR","TKM":"TM","UGA":"UG","UKR":"UA","ARE":"AE",
    "GBR":"GB","USA":"US","URY":"UY","UZB":"UZ","VEN":"VE","VNM":"VN","YEM":"YE",
    "ZMB":"ZM","ZWE":"ZW","XKX":"XK","FLK":"FK","MSR":"MS","SHN":"SH",
    "TCA":"TC","VIR":"VI","PRI":"PR","GUM":"GU","ASM":"AS","COK":"CK","NIU":"NU",
}
ISO2_TO_ISO3 = {v: k for k, v in ISO3_TO_ISO2.items()}


# ---------------------------------------------------------------------------
# 1.  Ember Climate — real CO2 intensity (gCO2/kWh), latest year per country
# ---------------------------------------------------------------------------
def load_ember() -> dict:
    path = os.path.join(_NEW_DATA, "yearly_full_release_long_format.csv")
    wanted = {"ISO 3 code", "Year", "Variable", "Value"}
    df = pd.read_csv(path, usecols=lambda column: column in wanted)
    intensity = cast(pd.DataFrame, df[df["Variable"] == "CO2 intensity"])
    ci = (intensity
            .dropna(subset="Value")
            .sort_values("Year", ascending=False)
            .groupby("ISO 3 code")
            .first()
            .reset_index()[["ISO 3 code", "Value"]])

    result = {}
    for _, row in ci.iterrows():
        iso2 = ISO3_TO_ISO2.get(str(row["ISO 3 code"]))
        if iso2:
            result[iso2] = round(float(row["Value"]), 1)

    print(f"[Ember] Loaded {len(result)} countries  "
          f"(range: {min(result.values()):.0f}–{max(result.values()):.0f} gCO2/kWh)")
    return result


# ---------------------------------------------------------------------------
# 2.  ND-GAIN — real country readiness/vulnerability score, 2023
#     gain.csv: higher score = better adapted = LOWER risk
#     We return risk = 100 - gain_score  (higher = riskier)
# ---------------------------------------------------------------------------
def load_ndgain(year: str = "2023") -> dict:
    path = os.path.join(_NEW_DATA, "resources", "gain", "gain.csv")
    gain = pd.read_csv(path)

    if year not in gain.columns:
        year = [c for c in gain.columns if c.isdigit()][-1]

    result = {}
    for _, row in gain.iterrows():
        iso3 = str(row["ISO3"]).strip()
        iso2 = ISO3_TO_ISO2.get(iso3)
        value = row.get(year)
        if value is None:
            continue
        try:
            score = float(value)
        except (TypeError, ValueError):
            continue
        if iso2 and not math.isnan(score):
            risk = round(100.0 - score, 1)   # invert: higher = riskier
            result[iso2] = risk

    print(f"[ND-GAIN] Loaded {len(result)} countries for year {year}  "
          f"(risk range: {min(result.values()):.1f}–{max(result.values()):.1f})")
    return result


# ---------------------------------------------------------------------------
# 3.  EPA USEEIO v1.3 — real emission factors, 1016 six-digit NAICS codes
#     Returns: {naics6_str: (title, kgco2e_per_usdM)}
# ---------------------------------------------------------------------------
def load_useeio(version: str = "v1.3") -> dict:
    fname = ("SupplyChainGHGEmissionFactors_v1.3.0_NAICS_CO2e_USD2022.csv"
             if version == "v1.3" else
             "SupplyChainGHGEmissionFactors_v1.2_NAICS_CO2e_USD2021.csv")
    path = os.path.join(_NEW_DATA_OLD, fname)
    df = pd.read_csv(path)
    df = df[df["GHG"] == "All GHGs"].copy()
    df["kgco2e_per_usdM"] = df["Supply Chain Emission Factors with Margins"] * 1_000_000

    result = {}
    for _, row in df.iterrows():
        code  = str(int(row["2017 NAICS Code"]))
        title = str(row["2017 NAICS Title"])
        val   = float(row["kgco2e_per_usdM"])
        result[code] = (title, val)

    print(f"[USEEIO {version}] Loaded {len(result)} NAICS codes  "
          f"(range: {min(v[1] for v in result.values()):.0f}–{max(v[1] for v in result.values()):.0f} kgCO2e/$1M)")
    return result


# ---------------------------------------------------------------------------
# 4.  Aggregate USEEIO to NAICS2 level (for one-hot encoding in model)
# ---------------------------------------------------------------------------
def load_useeio_naics2() -> dict:
    """Returns {naics2: (sector_name, mean_kgco2e_per_usdM)} — 20 sectors."""
    full = load_useeio()
    by2: dict[str, list[float]] = {}
    for code, (title, val) in full.items():
        n2 = code[:2]
        if n2 not in by2:
            by2[n2] = []
        by2[n2].append(val)

    # Sector labels
    sector_names = {
        "11":"Agriculture","21":"Mining","22":"Utilities","23":"Construction",
        "31":"Food & Textile Mfg","32":"Chemical & Paper Mfg","33":"Metal & Electronics Mfg",
        "42":"Wholesale Trade","44":"Retail Trade","45":"Retail Trade (misc)",
        "48":"Transportation","49":"Warehousing","51":"Information","52":"Finance",
        "53":"Real Estate","54":"Professional Services","55":"Management","56":"Admin Services",
        "61":"Education","62":"Health Care","71":"Arts & Entertainment",
        "72":"Food Services","81":"Other Services","92":"Public Admin",
    }
    result = {}
    for n2, vals in by2.items():
        result[n2] = (sector_names.get(n2, f"Sector {n2}"), float(np.mean(vals)))
    return result


if __name__ == "__main__":
    ember  = load_ember()
    ndgain = load_ndgain()
    useeio = load_useeio()
    naics2 = load_useeio_naics2()

    print("\nKey country grid intensities (gCO2/kWh):")
    for iso2 in ["SE","PT","FR","DE","US","CN","IN","BD","ZA"]:
        print(f"  {iso2}: {ember.get(iso2,'N/A')}")

    print("\nKey country risk scores (0=safe, 100=risky):")
    for iso2 in ["NO","DE","PT","US","CN","IN","BD","ZA"]:
        print(f"  {iso2}: {ndgain.get(iso2,'N/A')}")

    print("\nApparel NAICS codes:")
    for code, (title, val) in sorted(useeio.items()):
        if "apparel" in title.lower() or "cut and sew" in title.lower():
            print(f"  {code}: {title} = {val:,.0f} kgCO2e/$1M")
