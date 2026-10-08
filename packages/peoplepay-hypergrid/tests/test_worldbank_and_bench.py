import json

from hypergrid.bench import lpt_makespan, main
from hypergrid.corpus import FIXTURE, load_worldbank
from hypergrid.vintage import VintageStore


def test_world_bank_snapshot_is_real_labelled_historical_and_hash_pinned():
    snap = json.loads(FIXTURE.read_text())
    assert snap["provider"].startswith("World Bank") and "CC BY 4.0" in snap["license"] and "NOT_VINTAGE_AWARE" in snap["data_class"]
    assert set(snap["series"]) == {"WB.IND.CPI", "WB.USA.CPI", "WB.IND.FX"}
    for s in snap["series"].values():
        assert len(s["response_sha256"]) == 64 and "2024" in s["observations"] and s["source_url"].startswith("https://api.worldbank.org/")
    store = VintageStore(); load_worldbank(store)
    o = store.as_of("WB.IND.CPI", 2024, 1e9)
    assert o.origin == "HISTORICAL" and o.value > 100 and o.source_id == "worldbank.org"


def test_lpt_makespan_basics():
    assert lpt_makespan([1, 1, 1, 1], 2) == 2 and lpt_makespan([5], 8) == 5 and lpt_makespan([1] * 10, 1) == 10


def test_bench_smoke_produces_labelled_machine_readable_results_and_exact_incremental(tmp_path):
    r = main(["--decisions", "400", "--sensitivity-decisions", "300", "--workers", "1,2", "--reps", "1", "--draws", "100", "--out", str(tmp_path)])
    for name in ("results.json", "E1.csv", "E2.csv", "E3.csv", "E4.csv", "E5.csv"):
        assert (tmp_path / name).exists()
    assert "NOT_PRESENT" in r["labels"] and "no real LLM call" in r["labels"]["NOT_PRESENT"]
    assert all(row["exact_vs_full_recompute"] for row in r["E3"])
    assert all(row["completed_results_identical_to_clean_run"] for row in r["E4"] if "completed_results_identical_to_clean_run" in row)
    assert {x["config"].split("_")[0] for x in r["E2"]} == {"A", "B", "C", "H"}
    assert all("SIMULATED" in x["kind"] for x in r["E2"])
