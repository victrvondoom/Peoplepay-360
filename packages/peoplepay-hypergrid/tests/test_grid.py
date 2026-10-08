import threading

from hypergrid.corpus import T0, build_world
from hypergrid.grid import FaultPlan, run_grid


def small(n=400):
    store, reqs, _ = build_world(n, n_synthetic=30)
    return store, reqs, list(range(n))


def test_parallel_results_equal_sequential_results():
    store, reqs, idx = small()
    one = run_grid(store, reqs, idx, T0 + 1, workers=1, draws=200, chunk=50)
    four = run_grid(store, reqs, idx, T0 + 1, workers=4, draws=200, chunk=50)
    assert len(four.results) == len(idx) and all(one.results[i][0] == four.results[i][0] for i in idx)


def test_in_flight_work_is_bounded_by_admission_control():
    store, reqs, idx = small()
    r = run_grid(store, reqs, idx, T0 + 1, workers=2, draws=100, chunk=20, max_in_flight=3)
    assert r.chunks == 20 and r.max_in_flight <= 3


def test_transient_faults_are_retried_within_budget_and_results_are_identical():
    store, reqs, idx = small()
    clean = run_grid(store, reqs, idx, T0 + 1, workers=2, draws=100, chunk=20)
    faulty = run_grid(store, reqs, idx, T0 + 1, workers=2, draws=100, chunk=20, faults=FaultPlan(0.5, 1, 1), retry_budget=2)
    assert faulty.retries > 0 and not faulty.dead_lettered and all(faulty.results[i][0] == clean.results[i][0] for i in idx)


def test_persistent_faults_go_to_the_dead_letter_queue_without_blocking_other_chunks():
    store, reqs, idx = small()
    r = run_grid(store, reqs, idx, T0 + 1, workers=2, draws=100, chunk=20, faults=FaultPlan(0.3, 99, 2), retry_budget=1)
    assert r.dead_lettered and r.completed == r.chunks - len(r.dead_lettered)
    assert len(r.results) == (r.chunks - len(r.dead_lettered)) * 20


def test_cancellation_prevents_new_work():
    store, reqs, idx = small()
    ev = threading.Event(); ev.set()
    r = run_grid(store, reqs, idx, T0 + 1, workers=2, draws=100, chunk=20, cancel=ev)
    assert r.cancelled and not r.results
