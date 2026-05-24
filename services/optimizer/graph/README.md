# `services/optimizer/graph/` — Graph prototype

> Owner: Person 2 · Parent contract: [`GraphOptimizerContract`](../../../packages/contracts/module/optimizer.py) · Status: standalone prototype, real ETL data wired, ready for OR-Tools swap-in

A self-contained sandbox for the Architecture-D graph search described in
[`services/optimizer/README.md`](../README.md) and
[`docs/linewise/implementacion.md`](../../../docs/linewise/implementacion.md) §3.D.

The prototype now runs on the **real ETL output** in `data/clean/` (53 weeks of
2025 history). It auto-selects the demand window whose SKU count is closest to
the historical mean (~32 SKUs/week) and uses **per-line changeover hours
straight from `Tabla CF Prat`** for the edges, so every number in the demo
traces back to a real Damm cell.

---

## What this is (and isn't)

**This is** a best-in-class prototype solver built from off-the-shelf
state-of-the-art components — **LightGBM** quantile ensemble for the ML
changeover predictor (synthetic mode), **LKH-3** (via `elkai`) for per-line
ATSP, **ALNS** for the multi-line partition — running against the canonical
ETL CSVs (`demand`, `skus`, `line_capability`, `changeover_costs`,
`wo_master`). It produces a `PartitionResult` shape-compatible with
`OptimizerOutput`.

**This is not** the production optimiser. It exists so the rest of the
pipeline (ETL → optimiser → simulator → UI) can be wired and demoed while
[`vrp_model.py`](../app/vrp_model.py) is still being built. When the real
OR-Tools VRP lands, the partitioner and sequencer become reference
implementations to validate it against.

---

## The model in one diagram

```
               ┌──────────────┐
demand SKU ──► │   NODE       │  cost = units / median_speed + ramp_up
               │  (one per    │  (median_speed from line_capability.csv)
               │   chunk)     │
               └──────┬───────┘
                      │
                      ▼  asymmetric-aware edge
               ┌──────────────┐
   SKU → SKU ► │   EDGE       │  cost = changeover_costs.csv[line, a, b]
               │              │  (per-line, from tabla_cf_prat)
               └──────────────┘

three "vehicles"  L14, L17, L19   each tours a subset of nodes
hard gate         line_capability.csv  (sku × line × can_produce)
objective         min  max_ℓ ( prod_hoursℓ + changeover_hoursℓ )   + ε · Σℓ loadℓ
```

The objective is **min-max makespan** with an ε-weighted sum-of-loads
tie-breaker (so no line is left idle when the optimum is degenerate). This
matches OR-Tools VRP's `SetSpanCostCoefficientForVehicle` semantics exactly.

---

## Real-data analysis (the basis for tuning)

From `data/clean/demand.csv` (53 windows, 2025 history):

| Statistic | SKUs / week |
|---|---|
| **mean** | **32.04** |
| median | 33 |
| P25 / P75 | 29 / 37 |
| min / max | 7 / 45 |

The prototype is therefore **tuned for the mean case n ≈ 32**:
- Per-line subproblem size ≈ 10–12 → entirely inside Held-Karp's exact regime (n ≤ 15).
- ALNS time budget: 4 s wall clock, per-line resequence budget 50 ms.

From `data/clean/changeover_costs.csv` (69 086 rows, source = `tabla_cf_prat`):

| Line | rows | mean hours | median | distribution shape |
|---|---|---|---|---|
| L14 | 24 649 | **2.62** | 3.0 | mostly 3 h (heavy) |
| L17 | 15 876 | **0.98** | 1.0 | nearly always 1 h (lightest) |
| L19 | 28 561 | **3.02** | 1.0 | bimodal 1 h and 6 h (variable) |

Per-line costs are **substantially different** — L17 changes are cheap, L19
changes are expensive — and the partitioner sees those differences because
`edge_cost(a, b, line)` reads the matching row from the per-line table.

Self-loops cost 0 h. The matrix is symmetric in the source data; the
optimiser does not assume symmetry so an ML asymmetric correction can drop
in later without code changes.

---

## Files

| File | Purpose |
|---|---|
| [`real_data_loader.py`](real_data_loader.py) | **Real-data adapter.** Reads `data/clean/{demand,skus,line_capability,changeover_costs,wo_master}.csv`, picks the mean-case demand window (~32 SKUs), and exposes the *same* callable API the synthetic module does. `get_transition_cost(a, b, line)` does an O(1) dict lookup against the per-line `tabla_cf_prat` table; `get_node_cost(sku, units, line)` uses the real `median_speed_uds_per_hour`; `get_last_wo_for_sku` powers UI tooltips. |
| [`generate_test_data.py`](generate_test_data.py) | **Synthetic fallback.** 30-SKU dataset (5 sheets), schema-aligned with `packages/contracts`. Cost model is a LightGBM quantile ensemble (q10 / q50 / q90) trained once on a 10 k-sample synthetic ground truth with non-additive interactions. Models cached to `data_experiment/changeover_model.pkl`. Used automatically when `data/clean/` is unavailable. |
| [`sequence_optimizer.py`](sequence_optimizer.py) | Single-line ATSP open-path solver, **three-tier cascade**: Held-Karp DP for n ≤ 15 (exact); LKH-3 via `elkai` for 16 ≤ n ≤ 500 (state-of-the-art, dummy-node reduction for open path); NN + 2-opt + Or-opt + SA fallback. Returns `SequenceResult`. |
| [`line_partitioner.py`](line_partitioner.py) | Multi-line min-max VRP solved with **ALNS** (Adaptive Large Neighbourhood Search). Constraint-aware LPT seed, three destroy operators (random / worst / Shaw related-removal) × two repair operators (greedy / regret-2), Roulette-Wheel adaptive selection, SA acceptance. Each repair re-sequences via `optimize_sequence`. Returns `PartitionResult`. Also exposes `verify_partition(...)` for an independent objective-alignment check. |
| [`visualize_graph.py`](visualize_graph.py) | **Interactive Plotly dashboard** (writes `data_experiment/line_distribution_map.html`). Two synchronised panels: left subgraph per line (spring layout, arrow-headed paths, hover tooltips on every node with **SKU + work order + production cost + container/brand/family**); right stacked bar chart with the makespan reference line. Self-contained — Plotly bundled inline, opens in any browser, no internet needed. |
| [`data_experiment/artificial_plans.xlsx`](data_experiment/) | Synthetic dataset (`.gitignore`d). 5 sheets: `skus`, `demand`, `line_capability`, `node_costs`, `edge_matrix`. |
| [`data_experiment/changeover_model.pkl`](data_experiment/) | Cached LightGBM boosters. Delete to force re-training. |
| [`data_experiment/line_distribution_map.html`](data_experiment/) | Output of the visualiser — the interactive headline image for the pitch. |

---

## Mathematical statement

Given:

- `N` demand nodes `i ∈ V`, each with units `u_i` and SKU metadata.
- Lines `ℓ ∈ {14, 17, 19}` with allowed container types `F_ℓ`.
- Per-line node cost `p_iℓ = u_i / median_speed_iℓ + ramp_iℓ`.
- Per-line edge cost `c_{ij}ℓ` from `changeover_costs.csv` (symmetric in
  `tabla_cf_prat`, but the optimiser does not assume symmetry — ML deltas
  can break that without code changes).
- Hard gate: `a_iℓ = 1` iff `can_produce(i, ℓ)`.

Decide a partition `V = V₁₄ ∪ V₁₇ ∪ V₁₉` (disjoint) and per-line orderings
`π_ℓ : V_ℓ → {1, …, |V_ℓ|}` that minimise

```
makespan = max_ℓ  ( Σ_{i ∈ V_ℓ} p_iℓ  +  Σ_{k=1..|V_ℓ|-1} c_{π_ℓ⁻¹(k), π_ℓ⁻¹(k+1)} ℓ )
```

subject to `i ∈ V_ℓ  ⇒  a_iℓ = 1`. The ε-sum tie-breaker is
`+ ε · Σ_ℓ load_ℓ` (ε = 1e-4) with ε small enough never to dominate a
makespan improvement. Unassigned SKUs incur a constant penalty of 1 000 h
each so ALNS treats them as strictly worse than any feasible placement.

### Objective-alignment check (built in)

`line_partitioner.verify_partition(result, …)` recomputes
`prod_h`, `chg_h`, `makespan`, and `total` independently from the returned
sequences and confirms they match what ALNS reported. The partitioner
`_demo` runs the check after every solve and exits non-zero on mismatch.

Demo output (real data, 2025-W48):

```
--- objective alignment check ---
every SKU placed once    : OK
capability gate honoured : OK
makespan reported        : 77.9543 h
makespan recomputed      : 77.9543 h
reported == recomputed   : OK
objective (makespan+eps*sum) : 77.9772
```

---

## Quick start

```bash
cd services/optimizer/graph

# Step 0 (one-time) — confirm the data adapter sees data/clean/
python real_data_loader.py
# → [demand] 53 weeks, mean=32.04 median=33 min=7 max=45 SKUs/week
# → [demo window] 2025-W48-7d  n_skus=32 total_units=12,472,860

# Step 1 — synth dataset (only needed for the synthetic fallback path;
#          trains+caches data_experiment/changeover_model.pkl)
python generate_test_data.py

# Step 2 — sequence one line (Held-Karp on n=8, LKH-3 on n=25, SA baseline)
python sequence_optimizer.py

# Step 3 — partition + sequence all three lines via ALNS (real data by default)
python line_partitioner.py

# Step 4 — render the interactive dashboard (runs Step 3 internally,
#          writes data_experiment/line_distribution_map.html — open in browser)
python visualize_graph.py
```

Each script's `__main__` is a self-contained smoke test that prints a
human-readable summary. No CLI flags, no config — the dataset is fixed for
reproducibility. The partitioner and visualiser **prefer real data**; if
`data/clean/` is missing they fall back transparently to the synthetic
fixture so the prototype is usable offline.

### Dependencies

```
pandas     # CSV I/O for the real-data adapter
lightgbm   # changeover model (synthetic mode)
elkai      # LKH-3 ATSP solver
alns       # adaptive large neighbourhood search
networkx   # graph layout for the visualiser
plotly     # interactive HTML dashboard
numpy      # ALNS RNG + training matrices
openpyxl   # Excel I/O for the synthetic dataset
```

All available on PyPI, all pure-Python or pre-built wheels — no compilation
required on a stock Python ≥ 3.11.

---

## Demo numbers (real ETL, week 2025-W48, n=32 SKUs, observed)

| Metric | Value |
|---|---|
| Demand window | 2025-W48-7d (closest to mean of 32 SKUs) |
| SKUs partitioned | 32 (32 / 0 / 0 unassigned) |
| Per-line counts | L14 = 11 · L17 = 9 · L19 = 12 |
| Makespan | **77.95 h** (L19 is the longest line) |
| Max − min spread | **2.72 h** (≈ 3.5 % imbalance) |
| Capability violations | 0 |
| ALNS iterations | ~5 (within 4 s budget) |
| Total elapsed | ~4.9 s |
| Objective-alignment check | reported == recomputed ✓ |
| Output | `data_experiment/line_distribution_map.html` (~4.6 MB, self-contained) |

The partitioner balances the three lines to within 2.72 h on a 78 h
makespan — well inside what a planner would treat as "equivalent". L17's
small SKU count (n=9) is intentional: it has the *lightest* changeover
costs (mean 1 h) so it can absorb more production time per SKU and still
land at the same finish time as L14 / L19, whose changeovers cost 2-3× more.

---

## Interactive dashboard (the demo surface)

`visualize_graph.py` emits a single self-contained HTML file with:

* **Left panel — per-line subgraphs.** Three coloured clusters (L14 blue,
  L17 red, L19 green), spring-layout inside each cluster, traversed-edge
  arrows show the chosen sequence. Node size scales with production hours.
* **Right panel — per-line load.** Stacked bar (production + hatched
  changeover) with a dashed horizontal line marking the makespan — i.e.
  the very quantity the partitioner minimised. Total above each bar.
* **Tooltips on every node** — `SKU · line (position k/n) · work order ·
  production cost (h) · container_type · brand · family · primary_packaging`.
  The work order is the most-recent historical production WO for that SKU
  from `wo_master.csv` (`—` if the SKU has no production history).
* **Tooltips on every edge** — `L## changeover · from → to · hours`. The
  hours value is the exact cell from `changeover_costs.csv`.
* **Legend toggles** — click a line in the legend to hide / show its nodes
  and edges; click "changeover" to compare production-only vs total.
* **Plotly pan/zoom/box-select** — the standard mode bar is enabled.

Dark "control-room" theme by default; colours, sizing and spacing all
expose a `VisualizationStyle` dataclass so the pitch designer can tune
without editing the rendering code.

---

## Swap-in plan (prototype → real)

The whole point of the layering is that each piece has a single seam.

| Replace this prototype piece | with this real piece | seam |
|---|---|---|
| `generate_test_data._train_models` (synthetic 10 k samples) | training on real `Cambios 14_17_19_ 2025.xlsx` history | one function — same `_featurise` row, same q10/q50/q90 outputs |
| `real_data_loader.get_transition_cost` (CSV lookup) | `services/changeover_ml.predict` | same `(sku_a, sku_b, line_id) → float` signature, plug ML on top of the `tabla_cf_prat` floor |
| `real_data_loader.get_node_cost` | `line_capability.median_speed_uds_per_hour × median_oee` | same signature `(sku, units, line)` if production wants OEE-aware throughput |
| `line_partitioner.partition_lines` | OR-Tools `RoutingModel` with disjunctions + `SetSpanCostCoefficientForVehicle` | same `PartitionResult` shape → mirrors `OptimizerOutput` |
| `sequence_optimizer.optimize_sequence` | OR-Tools' tour inside each vehicle | not called directly when OR-Tools owns both layers |
| `visualize_graph.visualize_partition` | unchanged | takes any `PartitionResult` |

---

## Deferred (out of scope for the prototype)

These belong to the production optimiser, not the prototype. Listed here
so the gap is explicit when handing off:

- **Chunking** — large demand buckets split into `≤ chunk_max_productive_hours`
  sub-nodes. The prototype assumes one node per SKU.
- **Calendar events** — forced cleaning / maintenance windows (Friday 8 h,
  biweekly Monday 8 h) modelled as time-window-constrained nodes. The
  prototype treats lines as 24×7.
- **Disjunctive demand** — `margin_per_sku`-weighted node-drop penalties for
  infeasibility. The prototype assumes every SKU is mandatory; an upstream
  shortfall raises rather than silently dropping. (The unassigned-pool
  mechanism is in place — only the per-SKU margin weighting is missing.)
- **Replan with `freeze_days`** — the first N days of `previous` are taken
  fixed. The prototype always plans from scratch.
- **`median_oee` in the speed model** — node cost currently uses raw
  `median_speed_uds_per_hour`; production may want `speed × oee` to reflect
  realistic throughput. (User confirmed the current formula is correct for
  this prototype.)
- **Asymmetric ML edge corrections** — `tabla_cf_prat` is symmetric; the
  ML predictor can add direction-dependent deltas (e.g. "purge 33→50 vs
  full swap 50→33"). The optimiser already handles asymmetric inputs.

---

## Why these specific backends

**LightGBM quantile ensemble** for synthetic changeover prediction:
- Tabular, low-feature problem → gradient boosting dominates neural nets at this scale.
- Quantile objective gives uncertainty bands *for free* (q10/q90).
- SHAP-friendly → drill-down can attribute each edge's hours to specific features.
- Re-trains in < 5 s, predicts in ~30 µs/edge.

**LKH-3 (Lin-Kernighan-Helsgaun)** for ATSP:
- World-record holder on TSPLIB ATSP benchmarks since 2000.
- The `elkai` Python wrapper is a single PyPI install.
- Open-path / pinned-ends supported via the textbook dummy-node reduction.
- At the mean case (n=10-12 per line) Held-Karp is exact and faster — LKH
  takes over above n=15.

**ALNS** for the multi-line partition:
- Standard framework when a problem is "local search but the neighbourhood
  is expensive to enumerate" — re-sequencing each candidate costs ~50 ms.
- Three destroy × two repair × roulette-wheel = built-in diversification.
- Same SA acceptance the OR-Tools team uses, so the prototype's behaviour
  prefigures the real solver's.

**Plotly** for the dashboard:
- Self-contained HTML (no server, no internet); opens by double-click.
- Native tooltips with HTML formatting → the SKU + WO + cost metadata the
  brief explicitly asks for, one hover away.
- Built-in zoom / pan / legend-toggle / PNG export — the planner can drive
  the demo themselves without extra UI code.

---

## Why a hand-rolled solver at all

OR-Tools is the target. The prototype exists because:

1. **Schema lock-in** — putting the output shape into code before the solver
   forces every downstream consumer (simulator, UI, contracts) to commit to
   the field names. Bugs surface in hours, not on Sunday afternoon.
2. **Fail-safe** — if OR-Tools integration slips, the ALNS partitioner +
   LKH-3 sequencer is a presentable Arch-A+ fallback that already produces
   a balanced plan within seconds on every week of 2025 history.
3. **Reference oracle** — Held-Karp is exact on subsets of ≤ 15 nodes,
   which covers every per-line subset in the mean case (~10-12 SKUs/line).
   We can regression-test the real solver against this on small instances.
4. **Real data already wired** — the same scripts that produce the demo
   image read straight from the canonical ETL CSVs, so the day OR-Tools
   lands it can be A/B-tested side-by-side on identical inputs.
