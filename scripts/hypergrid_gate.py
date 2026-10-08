"""CI gate over a HYPERGRID results.json. Fails the pipeline on a CORRECTNESS regression only.

Deliberately does NOT gate on speed or cost numbers: those are machine- and assumption-dependent, so a hard threshold
would be either flaky or meaningless. It gates on invariants that must hold on every machine:
  * incremental recomputation is bit-exact against full recomputation in every scenario
  * faults never corrupt completed results; in-flight work never exceeds its bound
  * no privacy violation by the HYPERGRID configuration
  * no unverified output released by the HYPERGRID configuration
"""
import json
import sys

r = json.load(open(sys.argv[1]))
problems = []
for row in r["E3"]:
    if not row["exact_vs_full_recompute"]:
        problems.append(f"E3 inexact: {row['scenario']} ({row['mismatches']} mismatches)")
for row in r["E4"]:
    if row.get("completed_results_identical_to_clean_run") is False:
        problems.append(f"E4 corrupted results: {row['scenario']}")
    if "max_in_flight" in row and row["max_in_flight"] > row["in_flight_bound"]:
        problems.append(f"E4 backpressure bound exceeded: {row['scenario']}")
h = next(x for x in r["E2"] if x["config"].startswith("H_"))
if h["privacy_violations"]:
    problems.append(f"HYPERGRID privacy violations: {h['privacy_violations']}")
if h["unverified_outputs"]:
    problems.append(f"HYPERGRID released unverified outputs: {h['unverified_outputs']}")
if problems:
    print("GATE FAILED\n" + "\n".join(problems)); sys.exit(1)
print("gate passed: exactness, fault safety, privacy and verification invariants hold")
