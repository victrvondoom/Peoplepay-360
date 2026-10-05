"""
reference_data.py
-----------------
All lookup tables — now loaded from REAL data files where available.

Real data sources (new_data/ and new_data2/):
  - Ember Climate yearly release    -> EMBER_GRID_INTENSITY  (179 countries)
  - ND-GAIN Country Index 2026      -> ND_GAIN_RISK          (167 countries)
  - EPA USEEIO v1.3 (2022 USD)      -> USEEIO_FACTORS        (1,016 NAICS codes)

Static (no free machine-readable source exists):
  - GLEC Framework v3 transport factors  (4 constants)
  - Port coordinates / distance matrix   (50 major ports)
  - Country default port mapping
  - Country manufacturing multiplier     (IEA-derived, kept as fallback)
"""

import math
import os

_THIS_DIR     = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)

# ---------------------------------------------------------------------------
# 1.  Ember Climate — real CO2 intensity, loaded from new_data2/
# ---------------------------------------------------------------------------
def _load_ember():
    try:
        from ml.load_real_data import load_ember
        return load_ember()
    except Exception as e:
        print(f"[reference_data] Ember load failed ({e}), using fallback constants")
        return _EMBER_FALLBACK

_EMBER_FALLBACK = {
    "AU": 540, "AT": 158, "BD": 574, "BE": 161, "BR": 118,
    "CA": 130, "CL": 295, "CN": 581, "CO": 185, "CZ": 424,
    "DE": 385, "DK":  84, "EG": 456, "ES": 169, "ET":  12,
    "FR":  56, "GB": 233, "GH": 291, "GR": 429, "HU": 233,
    "ID": 717, "IN": 713, "IT": 233, "JP": 471, "KE":  37,
    "KR": 415, "MA": 619, "MX": 438, "MY": 665, "NG": 458,
    "NL": 298, "NO":  26, "NZ":  99, "PE": 168, "PH": 623,
    "PK": 405, "PL": 764, "PT":  96, "RO": 281, "RS": 661,
    "RU": 344, "SA": 697, "SE":  13, "SG": 408, "TH": 511,
    "TR": 411, "TW": 510, "TZ":  50, "UA": 218, "US": 369,
    "VN": 480, "ZA": 817, "ZM":  25, "KH": 331, "MM": 376,
    "LK": 468, "UZ": 534, "AZ": 449, "AR": 316,
}

EMBER_GRID_INTENSITY = _load_ember()

# ---------------------------------------------------------------------------
# 2.  ND-GAIN — real climate physical risk, loaded from new_data2/
#     risk = 100 - gain_score  (higher = riskier)
# ---------------------------------------------------------------------------
def _load_ndgain():
    try:
        from ml.load_real_data import load_ndgain
        return load_ndgain()
    except Exception as e:
        print(f"[reference_data] ND-GAIN load failed ({e}), using fallback constants")
        return _NDGAIN_FALLBACK

_NDGAIN_FALLBACK = {
    "AU": 28.8, "AT": 27.2, "BD": 68.6, "BE": 29.9, "BR": 48.7,
    "CA": 25.2, "CL": 40.3, "CN": 51.8, "CO": 49.9, "CZ": 32.7,
    "DE": 27.5, "DK": 23.2, "EG": 63.8, "ES": 34.6, "ET": 75.5,
    "FR": 29.1, "GB": 27.6, "GH": 61.9, "GR": 39.7, "HU": 36.5,
    "ID": 62.8, "IN": 61.3, "IT": 36.2, "JP": 33.5, "KE": 70.7,
    "KR": 33.2, "MA": 58.5, "MX": 51.1, "MY": 46.8, "NG": 78.4,
    "NL": 27.9, "NO": 20.7, "NZ": 24.4, "PE": 54.2, "PH": 66.6,
    "PK": 72.2, "PL": 34.3, "PT": 35.8, "RO": 39.9, "RS": 42.7,
    "RU": 44.1, "SA": 52.7, "SE": 21.8, "SG": 27.4, "TH": 49.7,
    "TR": 48.2, "TW": 38.6, "TZ": 72.9, "UA": 46.8, "US": 28.6,
    "VN": 58.2, "ZA": 61.4, "ZM": 75.1,
}

ND_GAIN_RISK = _load_ndgain()

# ---------------------------------------------------------------------------
# 3.  EPA USEEIO v1.3 — real factors for 1,016 NAICS codes
#     {naics6_str: (title, kgco2e_per_usdM)}
# ---------------------------------------------------------------------------
def _load_useeio():
    try:
        from ml.load_real_data import load_useeio
        return load_useeio()
    except Exception as e:
        print(f"[reference_data] USEEIO load failed ({e}), using fallback")
        return _USEEIO_FALLBACK

# Fallback: 2-digit aggregates only
_USEEIO_FALLBACK = {
    "11": ("Agriculture",        840_000),
    "21": ("Mining",           2_100_000),
    "22": ("Utilities",        1_800_000),
    "23": ("Construction",       620_000),
    "31": ("Food & Textile Mfg", 560_000),
    "32": ("Chemical Mfg",       890_000),
    "33": ("Metal & Elec Mfg",   480_000),
    "42": ("Wholesale",          210_000),
    "44": ("Retail",             180_000),
    "48": ("Transportation",     540_000),
    "51": ("Information",        130_000),
    "52": ("Finance",             95_000),
    "54": ("Prof Services",      105_000),
    "62": ("Health Care",        220_000),
    "72": ("Food Services",      220_000),
    "81": ("Other Services",     180_000),
}

USEEIO_FACTORS = _load_useeio()   # 1,016 real codes when data files present

# Build NAICS2-level aggregates from the real data (used for model one-hot encoding)
def _build_naics2_from_real():
    import collections
    import statistics
    by2 = collections.defaultdict(list)
    sector_names = {}
    for code, (title, val) in USEEIO_FACTORS.items():
        n2 = str(code)[:2]
        by2[n2].append(val)
        # Use first title fragment as sector label
        sector_names.setdefault(n2, title.split(" ")[0])
    return {n2: (sector_names[n2], statistics.mean(vals)) for n2, vals in by2.items()}

USEEIO_NAICS2 = _build_naics2_from_real()

# NAICS_DETAIL: maps naics6 -> (naics2, title, kgco2e_per_usdM)
# Used by generate_training_data and inference
NAICS_DETAIL = {
    code: (str(code)[:2], title, val)
    for code, (title, val) in USEEIO_FACTORS.items()
}

# ---------------------------------------------------------------------------
# 4.  Sub-national / regional grid intensity (gCO2/kWh)
#     For large countries where national average masks huge internal variation.
#     Sources: China NEA provincial data, US EPA eGRID, India CEA 2023.
#     Key: "CN-GD" = China Guangdong, "US-CA" = USA California, etc.
# ---------------------------------------------------------------------------
REGIONAL_GRID_INTENSITY = {
    # China provinces (gCO2/kWh) — national avg ~555
    "CN-SC": 55,   # Sichuan      — hydro-dominated
    "CN-YN": 65,   # Yunnan       — hydro-dominated
    "CN-QH": 80,   # Qinghai      — hydro + solar
    "CN-XZ": 45,   # Tibet        — hydro
    "CN-GZ": 280,  # Guizhou      — mixed hydro/coal
    "CN-ZJ": 460,  # Zhejiang     — mixed
    "CN-GD": 500,  # Guangdong    — Pearl River Delta manufacturing hub
    "CN-FJ": 420,  # Fujian       — nuclear + hydro
    "CN-JS": 540,  # Jiangsu      — Yangtze Delta manufacturing
    "CN-SH": 560,  # Shanghai
    "CN-BJ": 490,  # Beijing
    "CN-SD": 640,  # Shandong     — coal-heavy
    "CN-HE": 660,  # Hebei        — steel belt
    "CN-SX": 680,  # Shanxi       — coal province
    "CN-NM": 580,  # Inner Mongolia
    "CN-XJ": 710,  # Xinjiang     — coal-heavy
    "CN-HB": 510,  # Hubei        — Three Gorges hydro
    "CN-HN": 530,  # Hunan
    "CN-AH": 590,  # Anhui
    "CN-LN": 610,  # Liaoning
    "CN-CQ": 380,  # Chongqing    — hydro-mixed

    # United States states (gCO2/kWh) — national avg ~369
    "US-CA": 190,  # California   — high renewables
    "US-WA": 95,   # Washington   — hydro-dominated
    "US-OR": 160,  # Oregon       — hydro + wind
    "US-NY": 210,  # New York
    "US-VT": 20,   # Vermont      — nearly zero carbon
    "US-ME": 130,  # Maine        — wind + hydro
    "US-ID": 110,  # Idaho        — hydro
    "US-NM": 420,  # New Mexico   — coal + gas
    "US-TX": 400,  # Texas        — mixed (growing wind)
    "US-FL": 450,  # Florida      — gas-heavy
    "US-GA": 410,  # Georgia
    "US-IL": 430,  # Illinois     — nuclear
    "US-PA": 470,  # Pennsylvania
    "US-OH": 580,  # Ohio         — coal
    "US-IN": 620,  # Indiana      — coal-heavy
    "US-KY": 720,  # Kentucky     — coal
    "US-WV": 790,  # West Virginia— coal-dominated
    "US-WI": 500,  # Wisconsin
    "US-MN": 350,  # Minnesota    — wind
    "US-CO": 430,  # Colorado

    # India states (gCO2/kWh) — national avg ~713
    "IN-KA": 230,  # Karnataka    — wind + solar belt
    "IN-TN": 280,  # Tamil Nadu   — wind + solar
    "IN-RJ": 350,  # Rajasthan    — solar
    "IN-GJ": 560,  # Gujarat
    "IN-MH": 600,  # Maharashtra  — Mumbai/Pune industry
    "IN-DL": 650,  # Delhi
    "IN-UP": 750,  # Uttar Pradesh
    "IN-MP": 700,  # Madhya Pradesh
    "IN-WB": 770,  # West Bengal
    "IN-JH": 850,  # Jharkhand    — coal belt
    "IN-OR": 820,  # Odisha       — coal + steel

    # Germany states (gCO2/kWh) — national avg ~385
    "DE-BY": 220,  # Bavaria      — nuclear + hydro legacy + solar
    "DE-BW": 240,  # Baden-Württemberg
    "DE-SH": 180,  # Schleswig-Holstein — wind-heavy
    "DE-BB": 620,  # Brandenburg  — lignite
    "DE-ST": 600,  # Saxony-Anhalt— lignite
    "DE-NW": 380,  # North Rhine-Westphalia — industrial core
}

def get_grid_intensity(country_iso: str, region_code: str | None = None,
                       renewable_pct: float = 0.0) -> float:
    """
    Returns effective grid intensity (gCO2/kWh) for a location.

    Args:
        country_iso:   2-letter country code e.g. "CN"
        region_code:   Optional sub-national code e.g. "CN-GD" or just "GD"
                       Also accepts US state codes like "CA", "TX"
                       or Chinese province codes like "GD", "SH"
        renewable_pct: 0.0–1.0. Fraction of energy from renewables.
                       Reduces effective grid intensity proportionally.
                       e.g. 0.8 = 80% renewable on-site or via REC

    Returns: gCO2/kWh (float)
    """
    # Normalise region_code → "XX-YY" format
    region_key = None
    if region_code:
        r = region_code.upper().strip()
        if "-" in r:
            region_key = r  # already "CN-GD" format
        else:
            region_key = f"{country_iso.upper()}-{r}"  # "GD" → "CN-GD"

    if region_key and region_key in REGIONAL_GRID_INTENSITY:
        base_intensity = float(REGIONAL_GRID_INTENSITY[region_key])
    else:
        base_intensity = float(EMBER_GRID_INTENSITY.get(country_iso.upper(), 450))

    # Apply renewable override: clean energy displaces grid at ~30 gCO2/kWh
    if renewable_pct > 0:
        CLEAN_INTENSITY = 30.0  # gCO2/kWh for wind/solar
        effective = base_intensity * (1 - renewable_pct) + CLEAN_INTENSITY * renewable_pct
        return round(effective, 1)

    return base_intensity


# ---------------------------------------------------------------------------
# 5.  GLEC Framework v3 — transport emission factors (kgCO2e per tonne-km)
# ---------------------------------------------------------------------------
GLEC_FACTORS = {
    "sea":  0.011,
    "rail": 0.028,
    "road": 0.096,
    "air":  0.602,
}

# ---------------------------------------------------------------------------
# 5.  Port coordinates + distance helpers
# ---------------------------------------------------------------------------
PORT_COORDINATES = {
    "CNSHA": (31.22,  121.47), "CNQIN": (36.07,  120.38),
    "CNGZU": (22.50,  113.55), "CNNGB": (29.87,  121.55),
    "TWKHH": (22.62,  120.27), "KRPUS": (35.10,  129.04),
    "JPTYO": (35.45,  139.65), "SGSIN": ( 1.26,  103.82),
    "MYPKG": ( 3.14,  101.69), "VNCLI": (15.88,  108.33),
    "VNHPH": (20.84,  106.69), "THBKK": (13.58,  100.90),
    "IDBDJ": (-6.11,  106.88), "BDCGP": (22.33,   91.83),
    "INBOM": (18.93,   72.85), "INNSA": (13.09,   80.29),
    "PKKAR": (24.84,   67.01), "AEDSF": (25.07,   55.14),
    "EGPSD": (29.97,   32.55), "NLRTM": (51.95,    4.14),
    "DEHAM": (53.54,    9.99), "BEANR": (51.22,    4.40),
    "GBFXT": (51.45,    0.70), "GBSOU": (50.90,   -1.40),
    "FRLEH": (49.49,    0.11), "ESALG": (36.14,   -5.45),
    "PTLEI": (38.70,   -9.23), "ITGOA": (44.41,    8.93),
    "GRPIR": (37.95,   23.65), "TRIST": (41.01,   28.96),
    "UAODS": (46.49,   30.74), "RUUSH": (59.91,   30.26),
    "ZADBN": (-29.87,  31.04), "NGAPP": ( 6.45,    3.40),
    "EGALY": (31.19,   29.90), "USLAX": (33.74, -118.27),
    "USNYC": (40.69,  -74.17), "USSAV": (32.08,  -81.10),
    "USHOU": (29.75,  -95.36), "CAVAN": (49.29, -123.11),
    "MXLZC": (22.88, -109.92), "BRSAN": (-23.93, -46.31),
    "ARBA1": (-34.60, -58.37), "CLVAL": (-33.03, -71.63),
    "PEMOL": (-12.07, -77.15), "AUMES": (-33.87,  151.21),
    "AUMER": (-37.82,  144.96), "NZAKL": (-36.84,  174.77),
    "JPOSA": (34.65,   135.46), "PHMNL": (14.59,   120.97),
}

def _haversine_km(lat1, lon1, lat2, lon2):
    R = 6371
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlam/2)**2
    return 2 * R * math.asin(math.sqrt(a))

def get_port_distance(port_a: str, port_b: str) -> float:
    if port_a == port_b:
        return 0.0
    c1 = PORT_COORDINATES.get(port_a)
    c2 = PORT_COORDINATES.get(port_b)
    if not c1 or not c2:
        return 10_000
    return round(_haversine_km(*c1, *c2) * 1.25, 0)

COUNTRY_DEFAULT_PORT = {
    "CN":"CNSHA", "TW":"TWKHH", "KR":"KRPUS", "JP":"JPTYO",
    "SG":"SGSIN", "MY":"MYPKG", "VN":"VNHPH", "TH":"THBKK",
    "ID":"IDBDJ", "BD":"BDCGP", "IN":"INBOM", "PK":"PKKAR",
    "AE":"AEDSF", "EG":"EGPSD", "NL":"NLRTM", "DE":"DEHAM",
    "BE":"BEANR", "GB":"GBFXT", "FR":"FRLEH", "ES":"ESALG",
    "PT":"PTLEI", "IT":"ITGOA", "GR":"GRPIR", "TR":"TRIST",
    "UA":"UAODS", "RU":"RUUSH", "ZA":"ZADBN", "NG":"NGAPP",
    "US":"USNYC", "CA":"CAVAN", "MX":"MXLZC", "BR":"BRSAN",
    "AR":"ARBA1", "CL":"CLVAL", "PE":"PEMOL", "AU":"AUMES",
    "NZ":"NZAKL", "PH":"PHMNL", "KH":"SGSIN", "MM":"SGSIN",
    "LK":"INBOM", "MA":"ESALG", "ET":"INBOM", "GH":"NGAPP",
    "KE":"NGAPP", "SA":"AEDSF", "UZ":"AEDSF", "AZ":"AEDSF",
    "CO":"PEMOL", "CZ":"NLRTM", "AT":"ITGOA", "PL":"DEHAM",
    "RO":"GRPIR", "HU":"ITGOA", "RS":"GRPIR", "SE":"DEHAM",
    "DK":"DEHAM", "NO":"DEHAM", "FI":"DEHAM", "CH":"ITGOA",
    "IL":"EGPSD", "IR":"AEDSF", "IQ":"AEDSF",
    # Nearest listed hub for other sourcing countries (unlisted countries
    # would otherwise fall back to Shanghai in TransportCalculator).
    "IE":"GBSOU", "SK":"DEHAM", "SI":"ITGOA", "HR":"ITGOA",
    "BG":"GRPIR", "LT":"DEHAM", "LV":"DEHAM", "EE":"DEHAM",
    "LU":"BEANR", "CY":"GRPIR", "MT":"ITGOA", "IS":"GBFXT",
    "TN":"ITGOA", "DZ":"ESALG", "JO":"EGPSD", "LB":"EGPSD",
    "QA":"AEDSF", "KW":"AEDSF", "OM":"AEDSF", "BH":"AEDSF",
    "TZ":"ZADBN", "UG":"ZADBN", "MZ":"ZADBN", "CI":"NGAPP",
    "SN":"NGAPP", "CM":"NGAPP", "EC":"PEMOL", "UY":"ARBA1",
    "PY":"ARBA1", "BO":"CLVAL", "GT":"USHOU", "HN":"USHOU",
    "SV":"USHOU", "NI":"USHOU", "CR":"USHOU", "PA":"USHOU",
    "DO":"USSAV", "JM":"USSAV", "NP":"INNSA", "LA":"VNHPH",
    "MN":"CNQIN", "KZ":"AEDSF", "HK":"CNGZU", "BN":"SGSIN",
}

# ---------------------------------------------------------------------------
# 6.  Country manufacturing emission multiplier (IEA-derived, grid-normalised)
#     Now computed from real Ember data; fallback to hardcoded for countries
#     not in Ember.
# ---------------------------------------------------------------------------
def _build_country_multiplier() -> dict:
    """Derive multiplier from real Ember grid intensity, normalised to world avg."""
    world_avg = 450.0  # gCO2/kWh approximate world average
    mult = {}
    for iso2, intensity in EMBER_GRID_INTENSITY.items():
        # Grid-driven component: ratio to world average
        grid_ratio = intensity / world_avg
        # Industrial efficiency adjustment (kept from IEA research)
        eff_adj = _IEA_EFF_ADJUSTMENT.get(iso2, 1.0)
        mult[iso2] = round(grid_ratio * eff_adj, 3)
    return mult

# IEA industrial efficiency adjustments (independent of grid)
# Captures equipment age, process efficiency, regulation
_IEA_EFF_ADJUSTMENT = {
    "CN":1.10, "IN":1.12, "ZA":1.10, "ID":1.08, "PK":1.08,
    "BD":1.06, "VN":1.05, "PH":1.05, "MY":1.05, "TH":1.03,
    "EG":1.05, "NG":1.05, "MA":1.05, "UA":1.03, "KH":1.05,
    "MM":1.05, "TR":1.02, "MX":1.02, "BR":0.96, "KR":1.03,
    "TW":1.05, "JP":0.95, "RU":1.08, "SA":1.05, "AE":1.05,
    "PL":1.05, "CZ":1.03, "RO":1.02, "RS":1.05, "HU":1.00,
    "GR":1.03, "IT":0.95, "ES":0.95, "AU":1.05, "NZ":0.90,
    "DE":0.92, "US":0.96, "CA":0.90, "GB":0.92, "FR":0.90,
    "SE":0.88, "NO":0.88, "DK":0.90, "AT":0.90, "BE":0.92,
    "NL":0.92, "CH":0.88, "FI":0.90, "PT":0.92, "SG":0.95,
}

COUNTRY_EMISSION_MULTIPLIER = _build_country_multiplier()
