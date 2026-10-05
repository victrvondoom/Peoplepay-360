"""
transport.py
------------
Transport-emission helpers shared by scoring and the /rescore-transport
endpoint.

GLEC factors come from `ml.reference_data` (kgCO2e per tonne-km), so the
formula here matches `TransportCalculator.compute` exactly:

    tCO2e = factor_kg_per_tkm × weight_tonnes × distance_km / 1000
"""

from __future__ import annotations

from . import ml_bridge  # noqa: F401  (side-effect: configures sys.path for ml.*)

TRANSPORT_MODES = ("sea", "air", "rail", "road")


def _glec_factors() -> dict[str, float]:
    from ml.reference_data import GLEC_FACTORS  # type: ignore

    return GLEC_FACTORS


def transport_tco2e(distance_km: float, weight_kg: float, mode: str) -> float:
    """Shipment tCO2e for one mode. Unknown modes fall back to sea."""
    factors = _glec_factors()
    factor = factors.get((mode or "sea").lower(), factors["sea"])
    weight_tonnes = max(float(weight_kg), 0.0) / 1000.0
    return round(factor * weight_tonnes * max(float(distance_km), 0.0) / 1000.0, 4)


def transport_tco2e_by_mode(distance_km: float, weight_kg: float) -> dict[str, float]:
    """Shipment tCO2e for every supported mode, keyed by mode."""
    return {
        mode: transport_tco2e(distance_km, weight_kg, mode)
        for mode in TRANSPORT_MODES
    }


def rescore_transport(manufacturers: list[dict], new_mode: str) -> list[dict]:
    """
    Recalculate transport emissions for all manufacturers with a new mode.

    Expects each manufacturer dict to carry `transport.distance_km` and
    `transport.weight_kg` (populated during the original /search call).

    Returns the same list with `transport` and `scores` fields updated in place.
    """
    mode = (new_mode or "sea").lower()
    factors = _glec_factors()
    factor = factors.get(mode, factors["sea"])

    for m in manufacturers:
        transport = m.setdefault("transport", {})
        scores = m.setdefault("scores", {})

        distance_km = float(transport.get("distance_km", 8000))
        weight_kg = float(transport.get("weight_kg", 500))

        new_transport_tco2e = transport_tco2e(distance_km, weight_kg, mode)
        transport["transport_tco2e"] = new_transport_tco2e
        transport["mode"] = mode
        transport["glec_factor"] = factor

        scores["transport_tco2e"] = new_transport_tco2e
        mfg = float(scores.get("manufacturing_tco2e", 0.0))
        scores["total_tco2e"] = round(mfg + new_transport_tco2e, 2)

    return manufacturers
