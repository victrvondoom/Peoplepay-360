import random

import pytest

from hypergrid.corpus import LAST_PERIOD, T0, build_world
from hypergrid.incremental import IncrementalEngine
from hypergrid.procurement import compute_decision
from hypergrid.vintage import Observation, TrackingReader, VintageStore


def obs(series="S", period=2020, value=10.0, t=1.0, **kw):
    return Observation(series, period, value, known_at=t, **kw)


# ------------------------------------------------------------- vintage store
def test_as_of_returns_the_vintage_known_at_that_time():
    s = VintageStore()
    s.append(obs(value=10, t=1)); s.append(obs(value=11, t=5))
    assert s.as_of("S", 2020, 0.5) is None
    assert s.as_of("S", 2020, 1).value == 10 and s.as_of("S", 2020, 4.9).value == 10
    assert s.as_of("S", 2020, 5).value == 11 and len(s.vintages("S", 2020)) == 2    # nothing overwritten


def test_revision_must_be_later_in_knowledge_time():
    s = VintageStore(); s.append(obs(t=3))
    with pytest.raises(ValueError):
        s.append(obs(value=99, t=3))
    with pytest.raises(ValueError):
        s.append(obs(value=99, t=2))


def test_snapshot_is_isolated_from_later_revisions():
    s = VintageStore(); s.append(obs(value=10, t=1))
    snap = s.snapshot(2.0)
    s.append(obs(value=12, t=3))
    assert snap.read("S", 2020).value == 10                    # a batch pinned to t=2 never sees the t=3 revision
    assert s.snapshot(3.0).read("S", 2020).value == 12


def test_fingerprint_ignores_republication_time_but_not_value_or_quality():
    a, b = obs(value=10, t=1), obs(value=10, t=9)
    assert a.fingerprint() == b.fingerprint()
    assert a.fingerprint() != obs(value=10.5, t=1).fingerprint()
    assert a.fingerprint() != obs(value=10, t=1, quality="stale").fingerprint()


def test_tracking_reader_records_exactly_what_was_read():
    s = VintageStore(); s.extend([obs(period=p) for p in (2019, 2020)])
    rd = TrackingReader(s.snapshot(2.0))
    rd.read("S", 2020); rd.read("S", 2018)                      # present and absent
    keys = {s.key_parts(k): fp for k, fp in rd.seen.items()}
    assert set(keys) == {("S", 2020), ("S", 2018)} and keys[("S", 2018)] == 0


# ------------------------------------------------------------- numerics
def test_numerics_are_deterministic_and_independent_of_the_requirement_id():
    store, reqs, _ = build_world(60, n_synthetic=20, repeat_rate=0.0)
    snap = store.snapshot(T0 + 1)
    r = reqs[5]
    twin = type(r)("OTHER-ID", r.quantity, r.suppliers, r.fx_series, r.data_class, r.period_now)
    assert compute_decision(r, snap) == compute_decision(r, snap) == compute_decision(twin, snap)


def test_stale_observation_marks_the_decision_hard():
    store, reqs, syn = build_world(400, n_synthetic=60, repeat_rate=0.0)
    store.append(Observation(syn[0], LAST_PERIOD, 1000.0, known_at=T0 + 2, quality="stale", origin="SYNTHETIC"))
    users = [r for r in reqs if syn[0] in r.series_used()]
    assert users
    assert all(compute_decision(r, store.snapshot(T0 + 3)).hard for r in users)
    assert not any(f"{syn[0]}:stale" in compute_decision(r, store.snapshot(T0 + 1)).quality_flags for r in users)


# ------------------------------------------------------------- incremental engine
def world(n=300, k=40):
    store, reqs, syn = build_world(n, n_synthetic=k, repeat_rate=0.1)
    eng = IncrementalEngine(store, reqs, draws=200)
    eng.full_run(T0 + 0.5)
    return store, reqs, syn, eng


def revise(store, series, period, factor, t):
    o = store.as_of(series, period, t - 1e-6)
    store.append(Observation(series, period, o.value * factor, known_at=t, root_id=o.root_id, quality=o.quality, origin=o.origin))
    return (series, period)


def test_incremental_equals_full_recompute_under_random_revision_sequences():
    store, reqs, syn, eng = world()
    rnd, t = random.Random(11), T0 + 1
    for _ in range(12):
        batch = [revise(store, rnd.choice(syn + ["WB.IND.CPI", "WB.USA.CPI", "WB.IND.FX"]), rnd.choice(range(2014, 2025)),
                        rnd.choice([0.97, 1.0, 1.0001, 1.02, 1.1]), t + i * 0.01) for i in range(rnd.randint(1, 4))
                 if True]
        # one revision per (series, period) per batch
        batch = list(dict.fromkeys(batch))
        eng.apply_revisions(batch, t + 0.5)
        ok, bad = eng.verify_against_full()
        assert ok, f"mismatch on {bad[:5]}"
        t += 1


def test_unread_key_invalidates_nothing_and_noop_republish_recomputes_nothing():
    store, reqs, syn, eng = world()
    store.append(Observation("SYN.UNUSED", 2020, 1.0, known_at=T0 + 1))
    assert eng.apply_revisions([("SYN.UNUSED", 2020)], T0 + 1).candidates == 0
    used = next(s for s in syn if eng.rev.get(store.key(s, LAST_PERIOD)))
    rep = eng.apply_revisions([revise(store, used, LAST_PERIOD, 1.0, T0 + 2)], T0 + 2)
    assert rep.candidates > 0 and rep.recomputed == 0           # same value => fingerprint equal => no work
    assert eng.verify_against_full()[0]


def test_recompute_set_is_small_for_a_rarely_used_series():
    store, reqs, syn, eng = world(n=600, k=120)
    rare = min(syn, key=lambda s: len(eng.rev.get(store.key(s, LAST_PERIOD), [1] * 9)) or 9)
    rep = eng.apply_revisions([revise(store, rare, LAST_PERIOD, 1.05, T0 + 1)], T0 + 1)
    assert rep.recomputed <= len(reqs) * 0.1 and eng.verify_against_full()[0]


def test_early_cutoff_tiny_revision_recomputes_but_does_not_change_recommendation_summaries():
    store, reqs, syn, eng = world(n=500, k=30)
    busiest = max(syn, key=lambda s: len(eng.rev.get(store.key(s, LAST_PERIOD), ())))
    rep = eng.apply_revisions([revise(store, busiest, LAST_PERIOD, 1.00001, T0 + 1)], T0 + 1)
    assert rep.recomputed > 0 and rep.summary_changed < rep.recomputed       # downstream (explanation) work is cut off


def test_a_cache_invalidation_defect_is_caught_by_the_exactness_check():
    """Mutation test: break invalidation on purpose (ignore the revised key's reverse index) and prove the gate fails."""
    store, reqs, syn, eng = world()
    used = next(s for s in syn if len(eng.rev.get(store.key(s, LAST_PERIOD), ())) > 2)
    eng.rev[store.key(used, LAST_PERIOD)] = []                  # the injected defect
    eng.apply_revisions([revise(store, used, LAST_PERIOD, 1.25, T0 + 1)], T0 + 1)
    ok, bad = eng.verify_against_full()
    assert not ok and len(bad) > 2


def test_results_are_consistent_with_a_single_knowledge_time():
    store, reqs, syn, eng = world()
    pre = list(eng.results)
    used = next(s for s in syn if eng.rev.get(store.key(s, LAST_PERIOD)))
    revise(store, used, LAST_PERIOD, 1.3, T0 + 5)               # arrives LATER than the snapshot the batch is pinned to
    assert eng.verify_against_full(T0 + 0.5)[0] and eng.results == pre


def test_parallel_incremental_equals_sequential_incremental_and_full():
    store, reqs, syn, eng = world(n=400, k=20)
    used = next(s for s in syn if len(eng.rev.get(store.key(s, LAST_PERIOD), ())) > 5)
    rep = eng.apply_revisions([revise(store, used, LAST_PERIOD, 1.2, T0 + 1)], T0 + 1, workers=2, parallel_threshold=1)
    assert rep.recomputed > 5 and eng.verify_against_full()[0]
