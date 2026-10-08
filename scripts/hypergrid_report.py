"""Render results/SUMMARY.md from results.json. Every number is read from the data; nothing is typed by hand."""
import json
import sys
from pathlib import Path

src = Path(sys.argv[1])
r = json.loads(src.read_text())
env, wl = r["environment"], r["workload"]
L = []
w = L.append
w("# HYPERGRID benchmark summary (generated)\n")
w(f"Generated from `{src.name}` · git `{env['git_sha'][:10]}` · {env['platform']} · {env['cpu_count']} CPUs · Python {env['python']} · NumPy {env['numpy']} · run {env['run_at_utc']}\n")
w("## What is and is not real\n")
for k, v in r["labels"].items():
    w(f"- **{k}**: {v}")
w(f"\nWorkload: {wl['decisions']:,} synthetic procurement decisions; hard share {wl['hard_share']:.1%}; local-only share {wl['local_only_share']:.1%}; "
  f"{wl['measured_compute_ms_per_decision_1worker']:.3f} ms/decision numerics on one worker (measured).\n")

w("## E1 Worker scaling (MEASURED, real multiprocessing, CPU-bound Monte Carlo)\n")
w("| workers | median s | throughput /s | speedup | efficiency | note |\n|---|---|---|---|---|---|")
for x in r["E1"]:
    w(f"| {x['workers']} | {x['median_s']} | {x['throughput_per_s']:,} | {x['speedup_vs_1']}× | {x['efficiency']:.0%} | {'oversubscribed (> CPU count)' if x['oversubscribed'] else ''} |")

w("\n## E2 Four configurations, matched workload (counts MEASURED; prices, latency, accuracy SIMULATED)\n")
w("| config | model calls | input tok | output tok | total $ | $/verified-correct | correct | accepted wrong | privacy viol. | task p95 s | task p99 s | makespan s (virtual) |\n|---|---|---|---|---|---|---|---|---|---|---|---|")
for x in r["E2"]:
    w(f"| {x['config']} | {x['model_calls']:,} | {x['input_tokens']:,} | {x['output_tokens']:,} | {x['total_cost_usd']:.2f} | {x['cost_per_verified_correct_usd']:.2e} | {x['correct']:,} | {x['accepted_wrong']:,} | {x['privacy_violations']} | {x['task_latency_p95_s']} | {x['task_latency_p99_s']} | {x['makespan_virtual_s']:,} |")
A = next(x for x in r["E2"] if x["config"].startswith("A_"))
H = next(x for x in r["E2"] if x["config"].startswith("H_"))
w(f"\nH vs A: cost per verified-correct {A['cost_per_verified_correct_usd'] / H['cost_per_verified_correct_usd']:.1f}× lower, "
  f"correct share {H['correct'] / H['tasks']:.1%} vs {A['correct'] / A['tasks']:.1%}, task p95 latency {H['task_latency_p95_s']}s vs {A['task_latency_p95_s']}s. "
  "**Quality and tail latency are reported next to cost on purpose.**\n")
w("### Ablation\n")
w("| config | model calls | input tok | total $ | $/verified-correct | correct | makespan s |\n|---|---|---|---|---|---|---|")
for x in r["E2_ablation"]:
    w(f"| {x['config']} | {x['model_calls']:,} | {x['input_tokens']:,} | {x['total_cost_usd']:.2f} | {x['cost_per_verified_correct_usd']:.2e} | {x['correct']:,} | {x['makespan_virtual_s']:,} |")

w("\n## E3 Incremental vs full recomputation (numerics MEASURED; model $ SIMULATED)\n")
w("| scenario | data | affected by dependency index | recomputed | recommendation changed | incremental s (1 worker) | incremental s (grid) | full s (1 worker) | full s (grid) | speedup vs full-1 | exact vs full |\n|---|---|---|---|---|---|---|---|---|---|---|")
for x in r["E3"]:
    w(f"| {x['scenario']} | {x['data_class']} | {x['candidates_by_dependency_index']:,} | {x['recomputed']:,} | {x['summary_changed']:,} | {x['incremental_compute_s']} | {x['incremental_parallel_s']} | {x['full_recompute_sequential_s']} | {x['full_recompute_parallel_s']} | {x['speedup_vs_full_sequential']}× | {x['exact_vs_full_recompute']} |")
w("\nModel calls after a revision: incremental / full re-explain with warm cache / full re-explain with cold cache\n")
w("| scenario | incremental | full (warm cache) | full (cold cache) |\n|---|---|---|---|")
for x in r["E3"]:
    w(f"| {x['scenario'][:60]} | {x['model_calls_incremental_warm_cache']:,} | {x['model_calls_full_reexplain_warm_cache']:,} | {x['model_calls_full_reexplain_cold_cache']:,} |")

w("\n## E4 Fault tolerance (MEASURED)\n")
w("| scenario | chunks | completed | retries | dead-lettered | decisions missing | completed results == clean run | max in flight / bound |\n|---|---|---|---|---|---|---|---|")
for x in r["E4"]:
    w(f"| {x['scenario']} | {x['chunks']} | {x['completed']} | {x.get('retries', '')} | {x.get('dead_lettered_chunks', '')} | {x['decisions_missing']} | {x.get('completed_results_identical_to_clean_run', '')} | {x.get('max_in_flight', '')}/{x.get('in_flight_bound', '')} |")

w("\n## E5 Sensitivity to the simulated assumptions\n")
w("| assumption varied | hard share | H÷B cost/verified | H÷C cost/verified | H correct | C correct |\n|---|---|---|---|---|---|")
for x in r["E5"]:
    w(f"| {x['assumption']} | {x['hard_share']:.1%} | {x['H_vs_B_cost_ratio']} | {x['H_vs_C_cost_ratio']} | {x['H_correct_share']:.1%} | {x['C_correct_share']:.1%} |")
Path(src.parent / "SUMMARY.md").write_text("\n".join(L) + "\n")
print("wrote", src.parent / "SUMMARY.md")
