"""
inference.py
------------
GreenChain ML inference module — loaded once at FastAPI startup.

Provides:
  EmissionsModel        — XGBoost quantile regression wrapper
  TransportCalculator   — pure-formula GLEC transport emissions
  ScoreAssembler        — combines all 5 dimensions into composite score

Usage:
    from ml.inference import EmissionsModel, TransportCalculator, ScoreAssembler

    model = EmissionsModel.load()

    # Predict manufacturing emissions
    result = model.predict(
        country_iso="CN",
        naics4="3152",        # Cut & Sew Apparel
        revenue_usd_m=25.0,
        year=2023
    )
    # result = {"q10": 312.4, "q50": 841.7, "q90": 2240.1}   (tCO2e/$1M * revenue)

    # Transport
    transport = TransportCalculator.compute(
        origin_country="CN",
        destination_country="US",
        weight_tonnes=5.0,
        mode="sea"
    )
    # transport = {"tco2e": 7.2, "distance_km": 11812, "glec_factor": 0.011}
"""

import json
import math
import os
import sys
from typing import cast

import joblib  # type: ignore[import-untyped]  # Upstream provides no type marker.
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from ml.reference_data import (  # noqa: E402  (needs the sys.path entry above)
    EMBER_GRID_INTENSITY, COUNTRY_EMISSION_MULTIPLIER, ND_GAIN_RISK,
    GLEC_FACTORS, COUNTRY_DEFAULT_PORT, get_port_distance, NAICS_DETAIL,
    get_grid_intensity,
)

MODEL_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "models")


# ============================================================
#  1. Emissions Model
# ============================================================
class EmissionsModel:
    """
    Wraps 3 XGBoost quantile models (q10, q50, q90).
    Call .predict() to get tCO2e estimates for a supplier config.
    """

    def __init__(self, models: dict, feature_cols: list):
        self.models        = models       # {0.10: xgb, 0.50: xgb, 0.90: xgb}
        self.feature_cols  = feature_cols
        self._country_set  = set()
        self._naics2_set   = set()
        self._naics_index  = self._build_naics_prefix_index()  # fast NAICS lookup
        # Infer known categories from feature column names
        for col in feature_cols:
            if col.startswith("ctry_"):
                self._country_set.add(col[5:])
            elif col.startswith("nac_"):
                self._naics2_set.add(col[4:])

    @classmethod
    def load(cls, model_dir: str = MODEL_DIR) -> "EmissionsModel":
        import xgboost as xgb

        models = {}
        for q_int in [10, 50, 90]:
            native_path = os.path.join(model_dir, f"xgb_q{q_int:02d}.ubj")
            if os.path.exists(native_path):
                # XGBoost's own format: portable across versions, and loading it
                # avoids the "serialized model" warning pickles trigger.
                model = xgb.XGBRegressor()
                model.load_model(native_path)
            else:
                # Fallback for checkouts without .ubj files. joblib unpickles,
                # so only point model_dir at the repo's own vendored models.
                model = joblib.load(os.path.join(model_dir, f"xgb_q{q_int:02d}.joblib"))
            models[q_int / 100] = model
        with open(os.path.join(model_dir, "feature_columns.json")) as f:
            feature_cols = json.load(f)
        print(f"[EmissionsModel] Loaded 3 quantile models ({len(feature_cols)} features)")
        return cls(models, feature_cols)

    @staticmethod
    def _build_naics_prefix_index() -> dict:
        """
        Pre-build prefix index for fast NAICS lookups (built once at import).

        A full code maps to its own USEEIO intensity; a partial code (e.g. "33"
        or "3344") maps to the median intensity of every code sharing that
        prefix, so a vague industry hint gets a representative value rather
        than whichever code happens to be listed first.
        """
        values_by_prefix: dict[str, list[float]] = {}
        for code, (_n2, _title, val) in NAICS_DETAIL.items():
            for length in [6, 5, 4, 3, 2]:
                if len(code) >= length:
                    values_by_prefix.setdefault(code[:length], []).append(float(val))
        return {
            prefix: (prefix[:2], float(np.median(values)))
            for prefix, values in values_by_prefix.items()
        }

    @staticmethod
    def _lookup_naics(naics_str: str, prefix_index: dict) -> tuple:
        """
        Returns (naics2, useeio_intensity) for any NAICS code length.
        Tries exact match then progressively shorter prefixes.
        """
        s = str(naics_str).strip()
        for length in [len(s), 5, 4, 3, 2]:
            hit = prefix_index.get(s[:length])
            if hit:
                return hit
        return ("33", 500_000.0)  # fallback: generic manufacturing

    def _build_row(self, country_iso: str, naics4: str, revenue_usd_m: float,
                   year: int, grid_override: float | None = None) -> pd.DataFrame:
        naics_str = str(naics4).strip()
        naics2, useeio_val = self._lookup_naics(naics_str, self._naics_index)

        grid      = grid_override if grid_override is not None else EMBER_GRID_INTENSITY.get(country_iso, 450)
        ctry_mult = COUNTRY_EMISSION_MULTIPLIER.get(country_iso, 1.0)

        log_useeio = math.log(max(useeio_val, 1_000))
        log_grid   = math.log(max(grid, 5))

        row: dict[str, float] = {col: 0 for col in self.feature_cols}
        row["log_revenue"]     = math.log10(max(revenue_usd_m, 0.1))
        row["log_grid"]        = log_grid
        row["year_offset"]     = year - 2018
        row["ctry_mult"]       = ctry_mult
        row["log_useeio_base"] = log_useeio

        # Interaction features
        if "useeio_x_grid" in row:
            row["useeio_x_grid"] = log_useeio * log_grid
        if "useeio_x_ctry" in row:
            row["useeio_x_ctry"] = log_useeio * ctry_mult

        if f"ctry_{country_iso}" in row:
            row[f"ctry_{country_iso}"] = 1
        if f"nac_{naics2}" in row:
            row[f"nac_{naics2}"]       = 1
        return cast(pd.DataFrame, pd.DataFrame([row])[self.feature_cols])

    def predict(self, country_iso: str, naics4: str,
                revenue_usd_m: float, year: int = 2023,
                region: str | None = None, renewable_pct: float = 0.0) -> dict:
        """
        Returns estimated manufacturing tCO2e for the given supplier config.

        Args:
            country_iso:   e.g. "CN", "US", "IN"
            naics4:        NAICS code, any length e.g. "315220", "3152", "31"
            revenue_usd_m: Annual revenue in $M
            year:          Reporting year (default 2023)
            region:        Sub-national region for finer grid accuracy.
                           e.g. "GD" or "CN-GD" for Guangdong, "CA" for California
                           Supported: CN provinces, US states, IN states, DE states
            renewable_pct: 0.0–1.0. Fraction of energy from renewables/RECs.
                           e.g. 0.8 means factory runs on 80% clean energy.
        """
        grid = get_grid_intensity(country_iso, region, renewable_pct)
        X    = self._build_row(country_iso, naics4, revenue_usd_m, year,
                               grid_override=grid)
        predictions = []
        for model in self.models.values():
            log_pred  = model.predict(X)[0]
            intensity = float(np.exp(log_pred))
            predictions.append(round(intensity * revenue_usd_m, 1))

        # Monotone rearrangement: the vendored quantile models return their
        # bands in inverted order (the q10 model predicts the highest value),
        # so sort to guarantee q10 <= q50 <= q90. The median is unaffected.
        q10, q50, q90 = sorted(predictions)

        return {
            "q10_tco2e":                q10,
            "q50_tco2e":                q50,
            "q90_tco2e":                q90,
            "intensity_tco2e_per_usdm": round(q50 / max(revenue_usd_m, 0.1), 2),
            "country_iso":              country_iso,
            "region":                   region,
            "grid_gco2_kwh":            grid,
            "renewable_pct":            renewable_pct,
            "naics4":                   naics4,
            "revenue_usd_m":            revenue_usd_m,
        }


# ============================================================
#  2. Transport Calculator  (pure formula, no ML)
# ============================================================
class TransportCalculator:

    @staticmethod
    def compute(origin_country: str, destination_country: str,
                weight_tonnes: float, mode: str = "sea") -> dict:
        """
        tCO2e = GLEC_factor × weight_tonnes × distance_km / 1000
        (GLEC factor is per tonne-km, distance in km, factor in kgCO2/tonne-km
         → divide by 1000 to convert kg → tonnes)
        """
        mode = mode.lower()
        if mode not in GLEC_FACTORS:
            raise ValueError(f"Unknown mode '{mode}'. Choose from {list(GLEC_FACTORS)}")

        factor     = GLEC_FACTORS[mode]           # kgCO2 / tonne-km
        origin_port = COUNTRY_DEFAULT_PORT.get(origin_country, "CNSHA")
        dest_port   = COUNTRY_DEFAULT_PORT.get(destination_country, "USNYC")
        distance_km = get_port_distance(origin_port, dest_port)

        tco2e = factor * weight_tonnes * distance_km / 1000   # kg → tonne

        return {
            "tco2e":          round(tco2e, 2),
            "distance_km":    int(distance_km),
            "glec_factor":    factor,
            "mode":           mode,
            "origin_port":    origin_port,
            "dest_port":      dest_port,
            "weight_tonnes":  weight_tonnes,
        }

    @staticmethod
    def compare_all_modes(origin_country: str, destination_country: str,
                          weight_tonnes: float) -> dict:
        """Return transport tCO2e for all 4 modes side by side."""
        return {
            mode: TransportCalculator.compute(
                origin_country, destination_country, weight_tonnes, mode
            )["tco2e"]
            for mode in GLEC_FACTORS
        }


# ============================================================
#  3. Score Assembler — combines 5 dimensions into composite
# ============================================================
DEFAULT_WEIGHTS = {
    "manufacturing": 0.40,
    "transport":     0.25,
    "grid_carbon":   0.20,
    "certifications":0.10,
    "climate_risk":  0.05,
}

# Canonical certification keys -> fractional change to manufacturing tCO2e.
# Within the CDP and SBTi families only the strongest credential counts.
CERT_ADJUSTMENTS = {
    "iso14001":      -0.05,
    "cdp_a":         -0.10,
    "cdp_b":         -0.06,
    "cdp_c":         -0.03,
    "sbt_achieved":  -0.10,
    "sbt_committed": -0.08,
    "bcorp":         -0.04,
}
NO_DISCLOSURE_PENALTY = 0.15   # applied when a supplier discloses nothing at all

_CERT_FAMILY = {
    "cdp_a": "cdp", "cdp_b": "cdp", "cdp_c": "cdp",
    "sbt_achieved": "sbt", "sbt_committed": "sbt",
}

# Compact spellings (lowercase, alphanumerics only) -> canonical key.
_CERT_ALIASES = {
    "iso14001": "iso14001",
    "cdpa": "cdp_a", "cdpaminus": "cdp_a", "cdpleadership": "cdp_a",
    "cdpb": "cdp_b", "cdpbminus": "cdp_b",
    "cdpc": "cdp_c", "cdpcminus": "cdp_c",
    "sbtachieved": "sbt_achieved", "sbtiachieved": "sbt_achieved",
    "sbtvalidated": "sbt_achieved", "sbtivalidated": "sbt_achieved",
    "sbtapproved": "sbt_achieved", "sbtiapproved": "sbt_achieved",
    "sciencebasedtargetsachieved": "sbt_achieved",
    "sciencebasedtargetsvalidated": "sbt_achieved",
    "sbt": "sbt_committed", "sbti": "sbt_committed",
    "sbtcommitted": "sbt_committed", "sbticommitted": "sbt_committed",
    "sciencebasedtarget": "sbt_committed",
    "sciencebasedtargets": "sbt_committed",
    "sciencebasedtargetsinitiative": "sbt_committed",
    "sciencebasedtargetscommitted": "sbt_committed",
    "bcorp": "bcorp", "bcorporation": "bcorp",
    "certifiedbcorp": "bcorp", "certifiedbcorporation": "bcorp",
}


def normalise_certification(raw: str) -> str | None:
    """
    Map a free-form certification label to a canonical key, or None if unknown.

    e.g. "ISO 14001:2015" -> "iso14001", "CDP A-" -> "cdp_a",
         "science_based_targets" -> "sbt_committed", "B Corp" -> "bcorp".
    """
    compact = "".join(ch for ch in str(raw or "").lower() if ch.isalnum())
    if not compact:
        return None
    if compact.startswith("iso14001"):
        return "iso14001"
    return _CERT_ALIASES.get(compact)


def certification_adjustment(certifications: list[str]) -> float:
    """
    Multiplicative adjustment to manufacturing tCO2e (lower = better).

    No disclosure at all -> 1 + NO_DISCLOSURE_PENALTY. Unrecognised labels
    count as disclosure but carry no reduction.
    """
    labels = [c for c in (certifications or []) if str(c or "").strip()]
    if not labels:
        return round(1.0 + NO_DISCLOSURE_PENALTY, 4)

    best_by_family: dict[str, float] = {}
    for label in labels:
        key = normalise_certification(label)
        if key is None:
            continue
        family = _CERT_FAMILY.get(key, key)
        best_by_family[family] = min(best_by_family.get(family, 0.0), CERT_ADJUSTMENTS[key])
    return round(1.0 + sum(best_by_family.values()), 4)


class ScoreAssembler:
    """
    Combines all 5 environmental dimensions into a composite 0-100 score.
    Lower = better (less environmental impact).

    Score is normalised within the candidate set so ranking is relative.
    """

    @staticmethod
    def grid_score(country_iso: str) -> float:
        """Normalised grid carbon score: 0=cleanest, 100=dirtiest."""
        intensity = EMBER_GRID_INTENSITY.get(country_iso, 450)
        # Scale 0-100: 0 gCO2/kWh → 0, 900 gCO2/kWh → 100
        return round(min(intensity / 900 * 100, 100), 1)

    @staticmethod
    def climate_risk_score(country_iso: str) -> float:
        """ND-GAIN physical climate risk: 0=low risk, 100=high risk."""
        return ND_GAIN_RISK.get(country_iso, 50.0)

    @staticmethod
    def cert_adjustment(certifications: list[str]) -> float:
        """Multiplicative adjustment to manufacturing tCO2e from certifications."""
        return certification_adjustment(certifications)

    @staticmethod
    def normalise_to_100(values: list[float]) -> list[float]:
        """Min-max normalise a list to 0-100. Lower input = lower output."""
        mn, mx = min(values), max(values)
        if mx == mn:
            return [50.0] * len(values)
        return [round((v - mn) / (mx - mn) * 100, 1) for v in values]

    @classmethod
    def score_candidates(
        cls,
        candidates: list[dict],
        weights: dict | None = None
    ) -> list[dict]:
        """
        candidates: list of dicts, each must have:
          - name               : str
          - country_iso        : str
          - mfg_tco2e          : float  (from EmissionsModel.predict q50)
          - transport_tco2e    : float  (from TransportCalculator.compute)
          - certifications     : list[str]   e.g. ["iso14001", "sbt"]

        Returns: sorted list of candidates (ascending score = better first).
        """
        if not candidates:
            raise ValueError("candidates list is empty")
        required = {"name", "country_iso", "mfg_tco2e", "transport_tco2e"}
        for i, c in enumerate(candidates):
            missing = required - set(c.keys())
            if missing:
                raise ValueError(f"Candidate[{i}] missing required fields: {missing}")
            if c["mfg_tco2e"] < 0:
                raise ValueError(f"Candidate '{c['name']}': mfg_tco2e must be >= 0")
            if c["transport_tco2e"] < 0:
                raise ValueError(f"Candidate '{c['name']}': transport_tco2e must be >= 0")
            # Ensure certifications key always exists
            c.setdefault("certifications", [])

        weights = weights or DEFAULT_WEIGHTS
        # Normalise weights
        total_w = sum(weights.values())
        w = {k: v / total_w for k, v in weights.items()}

        # Apply cert adjustment to manufacturing
        for c in candidates:
            adj = cls.cert_adjustment(c.get("certifications", []))
            c["mfg_tco2e_adj"] = c["mfg_tco2e"] * adj
            c["cert_adj"]      = adj
            c["grid_raw"]      = EMBER_GRID_INTENSITY.get(c["country_iso"], 450)
            c["risk_raw"]      = ND_GAIN_RISK.get(c["country_iso"], 50.0)

        # Normalise each dimension across candidates
        mfg_norm    = cls.normalise_to_100([c["mfg_tco2e_adj"]  for c in candidates])
        trans_norm  = cls.normalise_to_100([c["transport_tco2e"] for c in candidates])
        grid_norm   = cls.normalise_to_100([c["grid_raw"]        for c in candidates])
        cert_norm   = cls.normalise_to_100([c["cert_adj"]        for c in candidates])
        risk_norm   = cls.normalise_to_100([c["risk_raw"]        for c in candidates])

        scored = []
        for i, c in enumerate(candidates):
            composite = (
                w["manufacturing"]  * mfg_norm[i]   +
                w["transport"]      * trans_norm[i]  +
                w["grid_carbon"]    * grid_norm[i]   +
                w["certifications"] * cert_norm[i]   +
                w["climate_risk"]   * risk_norm[i]
            )
            scored.append({
                **c,
                "score":           round(composite, 1),
                "mfg_norm":        mfg_norm[i],
                "transport_norm":  trans_norm[i],
                "grid_norm":       grid_norm[i],
                "cert_norm":       cert_norm[i],
                "risk_norm":       risk_norm[i],
                "total_tco2e":     round(c["mfg_tco2e_adj"] + c["transport_tco2e"], 1),
                "grid_gco2_kwh":   c["grid_raw"],
                "climate_risk_score": c["risk_raw"],
            })

        scored.sort(key=lambda x: x["score"])
        for rank, s in enumerate(scored, 1):
            s["rank"] = rank
        return scored
