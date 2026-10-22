"""Nothing in a HYPERGRID result may depend on process state.

Fingerprints, dependency keys and seeds must be identical in the parent, in a worker, in a restarted process and on
another platform; otherwise incremental invalidation silently compares apples with oranges.
"""
import multiprocessing as mp
import os
import subprocess
import sys
from pathlib import Path

import pytest

import hypergrid
from hypergrid import grid
from hypergrid.corpus import T0, build_world
from hypergrid.grid import run_grid
from hypergrid.procurement import compute_decision
from hypergrid.vintage import Observation, TrackingReader, VintageStore

#: The child processes must import the same code as this process, wherever it was loaded from.
SRC = str(Path(hypergrid.__file__).resolve().parents[1])

#: Known answer. blake2b(digest_size=8) over struct.pack(">d", 10.0) + b"ok", read big-endian. If this changes,
#: every persisted dependency fingerprint is invalidated: change it only deliberately.
GOLDEN_FINGERPRINT = 11249773524895109774


def _child_fingerprint(hash_seed: str) -> str:
    code = ("import sys; sys.path.insert(0, %r);"
            "from hypergrid.vintage import Observation;"
            "print(Observation('S', 1, 10.0, 1.0).fingerprint())") % SRC
    out = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True,
                         env={**os.environ, "PYTHONHASHSEED": hash_seed}, check=True)
    return out.stdout.strip()


def test_world_bank_fixture_ships_inside_the_package():
    """It used to be located relative to the repository layout, so an installed copy could not find it."""
    from hypergrid import corpus
    pkg = Path(hypergrid.__file__).resolve().parent
    assert corpus.FIXTURE.is_file() and pkg in corpus.FIXTURE.parents
    manifest = pkg.parents[1] / "pyproject.toml"            # present in a source checkout only
    if manifest.is_file():
        assert "data/*.json" in manifest.read_text(encoding="utf-8")


def test_fingerprint_is_identical_across_processes_with_different_hash_seeds():
    seen = {_child_fingerprint(s) for s in ("1", "2", "random")}
    assert seen == {str(GOLDEN_FINGERPRINT)}


def test_fingerprint_matches_the_golden_value_and_distinguishes_value_and_quality():
    ok = Observation("S", 1, 10.0, 1.0)
    assert ok.fingerprint() == GOLDEN_FINGERPRINT
    assert Observation("S", 1, 10.0, 99.0, source_id="elsewhere").fingerprint() == GOLDEN_FINGERPRINT    # not when/where learned
    assert Observation("S", 1, 10.0, 1.0, quality="stale").fingerprint() != GOLDEN_FINGERPRINT
    assert Observation("S", 1, 10.000000000000002, 1.0).fingerprint() != GOLDEN_FINGERPRINT            # one ulp matters
    assert Observation("S", 1, -0.0, 1.0).fingerprint() == Observation("S", 1, 0.0, 1.0).fingerprint()   # -0.0 == 0.0
    assert Observation("S", 1, 0.0, 1.0).fingerprint() != 0                                              # 0 means "absent"


def test_dependency_keys_do_not_depend_on_what_a_process_has_seen_before():
    a, b = VintageStore(), VintageStore()
    for name in ("A", "B", "C"):
        a.append(Observation(name, 1, 1.0, 1.0))
    for name in ("C", "B", "A"):                          # same series, opposite arrival order
        b.append(Observation(name, 1, 1.0, 1.0))
    fresh = VintageStore()                                # never saw any of them
    for name in ("A", "B", "C", "never-stored"):
        assert a.key(name, 7) == b.key(name, 7) == fresh.key(name, 7) == (name, 7)


def test_a_key_issued_by_one_process_never_names_a_different_series_in_another():
    parent = VintageStore()
    parent.append(Observation("A", 1, 1.0, 1.0))
    worker_key = VintageStore().key("X", 1)               # a worker meets a series the parent has not interned yet
    parent.append(Observation("Y", 1, 2.0, 2.0))
    assert parent.key_parts(worker_key) == ("X", 1)       # used to decode as ("Y", 1): the keys were intern-table indexes


@pytest.mark.parametrize("method", ["spawn"])
def test_grid_under_spawn_returns_the_same_results_and_dependencies_as_the_parent(monkeypatch, method):
    """``spawn`` is what Windows uses. Workers share nothing with the parent, so equality here proves the results,
    fingerprints and dependency keys carry no process-local state."""
    store, reqs, _ = build_world(40, n_synthetic=12)
    monkeypatch.setattr(grid, "_mp_context", lambda: mp.get_context(method))
    rep = run_grid(store, reqs, list(range(40)), T0 + 1, workers=2, draws=100, chunk=10, track=True)
    assert rep.completed == rep.chunks == 4 and not rep.dead_lettered
    snap = store.snapshot(T0 + 1)
    for i in range(40):
        rd = TrackingReader(snap)
        expected = compute_decision(reqs[i], rd, 100)
        res, seen = rep.results[i]
        assert res == expected
        assert seen == rd.seen                            # same keys, same fingerprints, computed in another process
