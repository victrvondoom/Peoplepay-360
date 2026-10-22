"""Known-answer and input-validation tests for the procurement numerics.

Every expected value below is derived analytically from the model's definition, not copied from program output:
a series with constant growth g has zero volatility, so each supplier cost is exactly ``quantity * base * exp(w*g)``.
"""
import math

import pytest

from hypergrid.procurement import Requirement, Supplier, compute_decision
from hypergrid.validation import InsufficientData, InvalidInput
from hypergrid.vintage import Observation, VintageStore

FIRST, NOW = 2014, 2024


def world(**series):
    """Snapshot with one series per keyword; ``None`` entries are missing periods (11 periods: 2014..2024)."""
    store = VintageStore()
    for name, values in series.items():
        for i, v in enumerate(values):
            if v is not None:
                store.append(Observation(name.replace("_", "."), FIRST + i, v, known_at=1.0))
    return store.snapshot(10.0)


def growth_series(g_rate, start=100.0, n=11):
    return [start * (1.0 + g_rate) ** i for i in range(n)]


def two_suppliers(weight=1.0, qty=7, base_a=12.5, base_b=13.0, series="X"):
    return Requirement("R", qty, (Supplier("A", base_a, "INR", ((series, weight),)),
                                  Supplier("B", base_b, "INR", ((series, weight),))), period_now=NOW)


# ------------------------------------------------------------------ closed-form answers
def test_constant_growth_gives_the_closed_form_cost_margin_and_zero_uncertainty():
    g = math.log(1.05)
    res = compute_decision(two_suppliers(weight=0.8), world(X=growth_series(0.05)), draws=64)
    exp_a, exp_b = 7 * 12.5 * math.exp(0.8 * g), 7 * 13.0 * math.exp(0.8 * g)
    assert res.mean_cost[0] == pytest.approx(exp_a, rel=1e-9) and res.mean_cost[1] == pytest.approx(exp_b, rel=1e-9)
    assert res.winner == 0 and res.margin == pytest.approx((exp_b - exp_a) / exp_a, rel=1e-9)
    assert res.p_not_best == 0.0 and res.complete and res.quality_flags == ()


def test_lognormal_mean_matches_exp_wg_plus_half_w2_sigma2():
    # One-period log-returns alternate 0.02 / 0.06: mean 0.04, sample std (n-1) = sqrt(10 * 0.02^2 / 9).
    levels, x = [100.0], 100.0
    for i in range(10):
        x *= math.exp(0.02 if i % 2 == 0 else 0.06)
        levels.append(x)
    g, sigma, w = 0.04, math.sqrt(10 * 0.02 ** 2 / 9), 0.9
    res = compute_decision(two_suppliers(weight=w), world(X=levels), draws=200_000)
    assert res.mean_cost[0] == pytest.approx(7 * 12.5 * math.exp(w * g + 0.5 * w * w * sigma * sigma), rel=5e-4)


def test_usd_supplier_is_converted_at_the_latest_fx_rate_plus_fx_drift():
    gfx = math.log(1.01)
    fx = growth_series(0.01, start=80.0)
    req = Requirement("R", 3, (Supplier("U", 2.0, "USD", (("X", 0.0),)), Supplier("L", 400.0, "INR", (("X", 0.0),))), period_now=NOW)
    res = compute_decision(req, world(X=growth_series(0.02), WB_IND_FX=fx), draws=64)
    assert res.mean_cost[0] == pytest.approx(3 * 2.0 * fx[-1] * math.exp(gfx), rel=1e-9)
    assert res.mean_cost[1] == pytest.approx(3 * 400.0, rel=1e-9) and res.winner == 0


def test_a_usd_price_is_never_converted_at_an_assumed_rate():
    req = Requirement("R", 3, (Supplier("U", 2.0, "USD", (("X", 1.0),)),), period_now=NOW)
    with pytest.raises(InsufficientData):
        compute_decision(req, world(X=growth_series(0.02)), draws=64)          # no FX observations at all


# ------------------------------------------------------------------ time-series gaps
@pytest.mark.parametrize("missing", [1, 5, 9])
def test_a_missing_period_is_not_bridged_into_a_fake_return(missing):
    g = math.log(1.05)
    values = growth_series(0.05)
    values[missing] = None
    res = compute_decision(two_suppliers(), world(X=values), draws=64)
    # The old code treated the two-period return across the gap as one period: ~0.5% error and non-zero volatility.
    assert res.mean_cost[0] == pytest.approx(7 * 12.5 * math.exp(g), rel=1e-9)
    assert res.p_not_best == 0.0
    assert res.complete is False and res.hard                                  # the gap is still reported


def test_too_little_adjacent_history_is_reported_not_extrapolated():
    values = [None] * 11
    values[0], values[2], values[4] = 100.0, 105.0, 110.0                      # no two adjacent periods at all
    res = compute_decision(two_suppliers(), world(X=values), draws=64)
    assert res.complete is False and res.mean_cost[0] == pytest.approx(7 * 12.5, rel=1e-9)   # zero drift, flagged incomplete


# ------------------------------------------------------------------ input validation
@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_observations_are_refused_at_the_boundary(bad):
    with pytest.raises(InvalidInput):
        Observation("X", 2020, bad, known_at=1.0)
    with pytest.raises(InvalidInput):
        Observation("X", 2020, 1.0, known_at=bad)


@pytest.mark.parametrize("bad", [0.0, -5.0])
def test_non_positive_levels_are_flagged_and_excluded_never_logged(bad):
    values = growth_series(0.02)
    values[4] = bad
    res = compute_decision(two_suppliers(), world(X=values), draws=64)
    assert "X:invalid_value" in res.quality_flags and res.complete is False and res.hard
    assert all(math.isfinite(c) for c in res.mean_cost) and all(math.isfinite(c) for c in res.p90_cost)
    res.summary()                                                              # used to raise "cannot convert float NaN to integer"


@pytest.mark.parametrize("kwargs", [
    dict(quantity=0), dict(quantity=-5), dict(quantity=True), dict(quantity=2.5), dict(suppliers=()),
    dict(period_now=3), dict(period_now=True)])
def test_requirements_with_impossible_facts_are_refused(kwargs):
    base = dict(id="R", quantity=1, suppliers=(Supplier("A", 1.0, "INR", ()),), period_now=NOW)
    with pytest.raises(InvalidInput):
        Requirement(**{**base, **kwargs})


def test_duplicate_supplier_ids_are_refused():
    with pytest.raises(InvalidInput):
        Requirement("R", 1, (Supplier("A", 1.0, "INR", ()), Supplier("A", 2.0, "INR", ())), period_now=NOW)


@pytest.mark.parametrize("kwargs", [
    dict(base_price=float("nan")), dict(base_price=0.0), dict(base_price=-1.0), dict(base_price=float("inf")),
    dict(currency="EUR"), dict(currency=""), dict(exposure=(("X", float("nan")),)), dict(exposure=(("", 1.0),)),
    dict(exposure=("X",))])
def test_suppliers_with_impossible_facts_are_refused(kwargs):
    base = dict(id="A", base_price=1.0, currency="INR", exposure=(("X", 1.0),))
    with pytest.raises(InvalidInput):
        Supplier(**{**base, **kwargs})


@pytest.mark.parametrize("draws", [0, -1, True, 1.5])
def test_monte_carlo_draw_count_is_validated(draws):
    with pytest.raises(InvalidInput):
        compute_decision(two_suppliers(), world(X=growth_series(0.05)), draws=draws)


def test_an_exponent_that_overflows_is_an_error_not_an_infinite_cost():
    req = Requirement("R", 1, (Supplier("A", 1.0, "INR", (("X", 1e6),)),), period_now=NOW)
    levels = [100.0, 150.0, 90.0, 160.0, 80.0, 170.0, 70.0, 180.0, 60.0, 190.0, 50.0]      # large volatility
    with pytest.raises(InvalidInput):
        compute_decision(req, world(X=levels), draws=64)
