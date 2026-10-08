# HYPERGRID benchmark summary (generated)

Generated from `results.json` · git `28e3da93fe` · Linux-6.18.44-fc-v80-x86_64-with-glibc2.39 · 4 CPUs · Python 3.13.16 · NumPy 2.5.3 · run 2026-10-08T03:13:37Z

## What is and is not real

- **HISTORICAL**: World Bank annual series (3), retrieved snapshot
- **SYNTHETIC**: all requirements/suppliers/prices and 197 category series
- **INJECTED**: revisions applied to real series are injected experiments, not observed provider revisions
- **SIMULATED**: model prices/latency/accuracy are assumptions, not provider measurements
- **NOT_PRESENT**: no DELAYED or LIVE market data; no real LLM call

Workload: 20,000 synthetic procurement decisions; hard share 43.6%; local-only share 5.0%; 0.799 ms/decision numerics on one worker (measured).

## E1 Worker scaling (MEASURED, real multiprocessing, CPU-bound Monte Carlo)

| workers | median s | throughput /s | speedup | efficiency | note |
|---|---|---|---|---|---|
| 1 | 15.989 | 1,250.8 | 1.0× | 100% |  |
| 2 | 8.135 | 2,458.5 | 1.97× | 98% |  |
| 4 | 4.365 | 4,582.1 | 3.66× | 92% |  |
| 8 | 4.449 | 4,495.4 | 3.59× | 45% | oversubscribed (> CPU count) |

## E2 Four configurations, matched workload (counts MEASURED; prices, latency, accuracy SIMULATED)

| config | model calls | input tok | output tok | total $ | $/verified-correct | correct | accepted wrong | privacy viol. | task p95 s | task p99 s | makespan s (virtual) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A_sequential_single_model | 20,000 | 7,177,208 | 1,800,000 | 48.53 | 2.49e-03 | 19,499 | 501 | 990 | 2.301 | 2.301 | 46,015.99 |
| B_parallel_single_model | 20,000 | 7,177,208 | 1,800,000 | 48.53 | 2.49e-03 | 19,499 | 501 | 990 | 2.301 | 2.301 | 5,752.0 |
| C_static_routing | 20,000 | 7,177,208 | 1,800,000 | 24.54 | 1.41e-03 | 17,453 | 2,547 | 0 | 2.301 | 3.501 | 4,269.2 |
| H_hypergrid | 10,154 | 682,337 | 913,860 | 1.90 | 1.03e-04 | 18,504 | 1,496 | 0 | 6.701 | 6.701 | 3,376.06 |

H vs A: cost per verified-correct 24.2× lower, correct share 92.5% vs 97.5%, task p95 latency 6.701s vs 2.301s. **Quality and tail latency are reported next to cost on purpose.**

### Ablation

| config | model calls | input tok | total $ | $/verified-correct | correct | makespan s |
|---|---|---|---|---|---|---|
| H_minus_det_first | 18,738 | 1,258,760 | 2.12 | 1.15e-04 | 18,358 | 6,989.93 |
| H_minus_cache | 14,136 | 949,945 | 2.66 | 1.44e-04 | 18,545 | 4,680.92 |
| H_minus_validate_escalate | 6,313 | 424,181 | 0.14 | 9.00e-06 | 14,797 | 2,766.93 |
| H_minus_compact_prompt | 10,154 | 3,711,396 | 3.03 | 1.64e-04 | 18,504 | 3,376.06 |
| B_plus_det_first | 8,726 | 3,192,884 | 21.36 | 1.09e-03 | 19,551 | 2,511.34 |
| B_plus_cache | 14,457 | 5,176,861 | 35.05 | 1.79e-03 | 19,528 | 4,160.36 |
| B_plus_compact_prompt | 20,000 | 1,343,405 | 31.03 | 1.59e-03 | 19,499 | 5,752.0 |
| B_plus_adaptive_validate | 26,050 | 9,389,881 | 4.77 | 2.60e-04 | 18,384 | 9,687.72 |

## E3 Incremental vs full recomputation (numerics MEASURED; model $ SIMULATED)

| scenario | data | affected by dependency index | recomputed | recommendation changed | incremental s (1 worker) | incremental s (grid) | full s (1 worker) | full s (grid) | speedup vs full-1 | exact vs full |
|---|---|---|---|---|---|---|---|---|---|---|
| S1 late revision: one synthetic series, latest period +2% | SYNTHETIC | 82 | 82 | 80 | 0.0701 | 0.0903 | 17.578 | 4.757 | 250.7× | True |
| S2 revision of REAL World Bank India CPI 2024, +1.5% (value INJECTED, series real) | HISTORICAL+INJECTED | 11,830 | 11,830 | 4,917 | 9.8549 | 2.7907 | 17.578 | 4.757 | 1.8× | True |
| S3 no-op republish: same value, later vintage | SYNTHETIC | 131 | 0 | 0 | 0.0004 | None | 17.578 | 4.757 | 41366.9× | True |
| S4 old-period revision (2016) of one synthetic series, +3% | SYNTHETIC | 123 | 123 | 4 | 0.1139 | 0.1218 | 17.578 | 4.757 | 154.3× | True |
| S5 bulk: five synthetic series revised +1% | SYNTHETIC | 603 | 603 | 430 | 0.5748 | 0.2642 | 17.578 | 4.757 | 30.6× | True |
| S6 tiny revision (+0.01%) of the most widely used synthetic series | SYNTHETIC | 158 | 158 | 0 | 0.1357 | 0.1279 | 17.578 | 4.757 | 129.6× | True |
| S7 revision of REAL World Bank India FX 2024, +2% (INJECTED) | HISTORICAL+INJECTED | 11,625 | 11,625 | 10,101 | 10.8121 | 3.1953 | 17.578 | 4.757 | 1.6× | True |

Model calls after a revision: incremental / full re-explain with warm cache / full re-explain with cold cache

| scenario | incremental | full (warm cache) | full (cold cache) |
|---|---|---|---|
| S1 late revision: one synthetic series, latest period +2% | 34 | 34 | 10,154 |
| S2 revision of REAL World Bank India CPI 2024, +1.5% (value  | 2,433 | 5,502 | 10,162 |
| S3 no-op republish: same value, later vintage | 0 | 0 | 10,162 |
| S4 old-period revision (2016) of one synthetic series, +3% | 2 | 47 | 10,162 |
| S5 bulk: five synthetic series revised +1% | 198 | 271 | 10,162 |
| S6 tiny revision (+0.01%) of the most widely used synthetic  | 0 | 45 | 10,162 |
| S7 revision of REAL World Bank India FX 2024, +2% (INJECTED) | 5,041 | 5,056 | 10,078 |

## E4 Fault tolerance (MEASURED)

| scenario | chunks | completed | retries | dead-lettered | decisions missing | completed results == clean run | max in flight / bound |
|---|---|---|---|---|---|---|---|
| transient faults on ~20% of chunks, retry budget 2 | 50 | 50 | 15 | 0 | 0 | True | 8/8 |
| persistent faults on ~10% of chunks (5 attempts), retry budget 2 | 50 | 47 | 6 | 3 | 300 | True | 8/8 |
| cancelled before submission | 50 | 0 |  |  | 5000 |  | / |

## E5 Sensitivity to the simulated assumptions

| assumption varied | hard share | H÷B cost/verified | H÷C cost/verified | H correct | C correct |
|---|---|---|---|---|---|
| repeat_rate=0.0 | 42.9% | 0.054 | 0.096 | 93.1% | 87.8% |
| repeat_rate=0.15 | 45.0% | 0.047 | 0.084 | 92.3% | 87.7% |
| repeat_rate=0.3 | 44.2% | 0.041 | 0.072 | 92.1% | 87.5% |
| repeat_rate=0.6 | 43.0% | 0.021 | 0.036 | 94.3% | 86.9% |
| price_spread=±10% | 44.2% | 0.041 | 0.072 | 92.1% | 87.5% |
| price_spread=±25% | 20.4% | 0.019 | 0.034 | 96.6% | 93.4% |
| small_model_accuracy_on_hard=0.3 | 44.2% | 0.059 | 0.096 | 91.2% | 82.6% |
| small_model_accuracy_on_hard=0.55 | 44.2% | 0.041 | 0.072 | 92.1% | 87.5% |
| small_model_accuracy_on_hard=0.8 | 44.2% | 0.022 | 0.042 | 93.4% | 92.7% |
| silent_error_share=0.0 | 44.2% | 0.057 | 0.1 | 100.0% | 87.5% |
| silent_error_share=0.2 | 44.2% | 0.041 | 0.072 | 92.1% | 87.5% |
| silent_error_share=0.5 | 44.2% | 0.021 | 0.036 | 83.7% | 87.5% |
| NO price gap: small model priced like the large one | 44.2% | 0.1 | 0.094 | 94.1% | 87.5% |
| NO price gap at all: every model priced like the large one | 44.2% | 0.21 | 0.189 | 99.1% | 87.5% |
| validator blind: every model error is silent (share=1.0) | 44.2% | 0.004 | 0.006 | 73.8% | 87.5% |
| large_model_price_x0.25 (price gap shrinks) | 44.2% | 0.063 | 0.097 | 92.1% | 87.5% |
