# `services/optimizer/` — Graph optimiser (Architecture D)

> Owner: Person 2 · Contract: [`GraphOptimizerContract`](../../packages/contracts/module/optimizer.py) · Status: skeleton

This is the heart of LineWise. It implements the graph-search algorithm
described in [`docs/linewise/implementacion.md`](../../docs/linewise/implementacion.md) §3.D.

## What this service does, in plain words

You have a **complete graph** where:

- Each **node** represents a SKU chunk to be produced. Node cost on a given
  line is `units_chunk / median_speed_uds_per_hour + ramp_up_hours` —
  the speed lookup lives in [`line_capability.csv`](../../docs/data/line_capability.md).
- Each **edge** represents a possible transition between two SKUs on a line.
  Edge cost = changeover hours (provided by
  [`services/changeover_ml/`](../changeover_ml/), clamped to the theoretical
  floor in [`changeover_costs.csv`](../../docs/data/changeover_costs.md)).
- **Both node and edge costs vary by line** — the same SKU runs at a different
  speed on L14 than on L17, and the same A → B transition takes longer on one
  line than another.

**Hard capability constraints** (encoded in [`line_capability.csv`](../../docs/data/line_capability.md)):

| Line | Allowed `container_type` |
|---|---|
| **L14** | `1/2` (50 cl), `1/3` (33 cl) |
| **L17** | `1/3` (33 cl) only |
| **L19** | `1/2` (50 cl), `1/3` (33 cl), `2/5` (44 cl) |

Find:

1. The **distribution** of nodes across the three lines (a partition into
   three subgraphs) that respects capability.
2. The **ordered path inside each subgraph**.

**Objective: minimise the maximum total time across the three lines
(makespan)**, with a tiny ε-weighted sum-of-times tie-breaker so the solver
doesn't strand a line idle.

## Planning window

One `optimize()` call plans **one window**. Window size = `WindowConfig.days`
(default 7). Long horizons = chained calls. The same `WindowConfig` controls
the demand bucket size in [`demand.csv`](../../docs/data/demand.md) — change
one, both move.

## Inputs

- [`demand.csv`](../../docs/data/demand.md) — bucketed demand. The optimiser
  may further chunk large buckets into `<= chunk_max_productive_hours` (default 8 h) sub-nodes.
- [`line_capability.csv`](../../docs/data/line_capability.md) — hard capability gate + node-cost fallback.
- [`changeover_costs.csv`](../../docs/data/changeover_costs.md) — theoretical floor.
- ML model from [`services/changeover_ml/`](../changeover_ml/) — live edge weights.
- [`line_calendar.csv`](../../docs/data/line_calendar.md) — forced events with windows.
- `optimizer_hyperparams.yaml` — `WindowConfig`, `freeze_days`, `lambda_changeover`,
  `mu_unmet_demand`, `nu_margin`, `chunk_max_productive_hours`, `margin_per_sku`.

## Output

`OptimizerOutput` carrying a `Sequence`, per-line and global makespan, dropped
SKUs and the solver log. The simulator consumes the `Sequence` to compute
OEE-style metrics — the optimiser itself never reports OEE.

## Infeasibility

Every demand node is **disjunctive**: visiting is optional with penalty
`margin_per_sku[sku_id] * units_chunk`. The solver drops the lowest-margin
SKUs first. `feasible = False` then, and `dropped` lists what was left out.

## Replan

`replan(previous, inputs, ml)` is what the UI calls when the user injects a
breakdown or urgent demand. It respects `freeze_days`: the first N days of
`previous` are taken as fixed.

## Stack

- **OR-Tools** (`ortools.constraint_solver.pywrapcp`) — proven VRP with
  disjunctions, time windows, makespan via `SetSpanCostCoefficientForVehicle`.

## Definition of done

- [ ] `optimize(inputs, ml)` returns a valid `OptimizerOutput` for the demo
      week in < 5 s on a laptop.
- [ ] Every slot respects `line_capability.can_produce`.
- [ ] Forced calendar events appear in the output at their declared windows.
- [ ] When demand exceeds capacity, `feasible = False` and `dropped` lists the
      lowest-margin SKUs.
- [ ] `replan` preserves slots inside the freeze window byte-for-byte.
- [ ] Switching `WindowConfig.days` from 7 to 14 keeps `optimize` working
      without code changes.

## Graph construction — `graph_builder.py`

`services/optimizer/app/graph_builder.py` is the **graph orchestration layer**
that sits between the raw CSVs and the OR-Tools solver.  It exposes four
public functions:

### `build_planning_graph(window_id, ...)` → `nx.MultiDiGraph`

Builds the complete SKU-level planning graph the optimiser routes through.
Returns a **single** `nx.MultiDiGraph` covering all three lines — node costs
and edge costs are both **line-specific**, encoded as follows:

| Graph element | Storage | Source |
|---|---|---|
| Node (`sku_id`) | `G.nodes[sku]["line_data"][line_id]["predicted_hours"]` = `units_demanded / predicted_speed` on that line. Only lines where `can_produce = True` are present. | `node_cost_ml` CatBoost model |
| Edge (`sku_from → sku_to`) keyed by `line_id` | `G[sku_from][sku_to][line_id]["hours"]` = theoretical changeover time on that line. One edge per `(sku_from, sku_to, line_id)` triple. | `changeover_costs.csv` (Tabla CF Prat) |

Node attributes shared across all three lines: `units_demanded`, `source`,
`priority`.  Only SKUs that have demand in `window_id` **and** are capable on
at least one line appear as nodes.  Self-loops are excluded.

```python
from services.optimizer.app.graph_builder import build_planning_graph, visualize_planning_graph

G = build_planning_graph("2025-W01-7d")
# Per-line node cost on L14:
#   G.nodes["ED13LP12"]["line_data"][14]["predicted_hours"]  → float
# Per-line changeover cost A→B on L14 (MultiDiGraph edge keyed by line):
#   G["ED13LP12"]["ED13LTW"][14]["hours"]                    → float
# Capability gate is implicit — a line is in line_data iff can_produce = True.

fig = visualize_planning_graph(G)
fig.savefig("planning_graph.png", dpi=120, bbox_inches="tight")
```

This is the graph object the partitioner consumes via
`graph/line_partitioner.partition_from_graph(G, ...)` — see *Partitioner
algorithm* below.

### Partitioner algorithm — `graph/line_partitioner.py`

`graph/line_partitioner.py` implements the **two-level partition + routing**
algorithm that turns the planning graph into a per-line sequence:

1. **Level A — partition.** Constraint-aware LPT initial assignment (most
   constrained SKUs placed first, then largest node cost first onto the
   least-loaded feasible line), then a best-improvement local search over
   three move families:

   a. Single-node moves `v ∈ S_A → S_B` (every feasible `(v, A, B)`).
   b. Pair swaps `v_A ↔ v_B` across lines, both placements feasible.
   c. Balance-repair: if `max T_i − min T_i > δ`, move the highest-score
      node from the bottleneck line to the slack line — only applied when
      single moves and swaps both stall.

2. **Level B — routing.** For each candidate partition, the per-line sequence
   is the **exact** Held-Karp DP via
   `graph/sequence_optimizer.optimize_sequence` (≤ 15 nodes per line in
   practice, sub-ms per call). Every move trial recomputes **only the two
   lines it touches**; the third line's `T_i` is reused. Results are cached
   by `(line, frozenset(skus))` so identical sub-problems hit the cache
   instead of re-running Held-Karp.

Objective: `min  max_i T_i + ε · Σ_i T_i`. The makespan dominates; the ε
tie-breaker prevents leaving a line idle when the optimum is degenerate.

Entry points:

```python
from services.optimizer.app.graph_builder import build_planning_graph
from line_partitioner import partition_from_graph, verify_partition

G = build_planning_graph("2025-W13-7d")
result = partition_from_graph(G, time_budget_s=4.0)
# result.makespan_hours, result.sequences[14], result.dropped, …
```

`partition_from_graph` is the thin adapter that closes
`can_produce / node_cost / edge_cost` over `G` and calls `partition_lines`
(the callable-API form used by the synthetic test path).

### Evaluation — `graph/evaluate_windows.py`

Runs the partitioner end-to-end on **every** `window_id` present in
`data/clean/demand.csv` (53 windows for the 2025 history) and reports
`mean / median / stdev / P25 / P75 / min / max` of the makespan along with
per-line load, spread, drop count, and wall-clock time.

```bash
python services/optimizer/graph/evaluate_windows.py --budget 4.0
```

Writes one row per window to `data_experiment/evaluation_all_windows.csv` for
post-hoc analysis. This is the canonical *aggregate quality* metric for the
partitioner — used to compare hyperparameter choices and to spot windows
where capacity is tight (high drop count) or load is unbalanced (large
spread).

### `build_historical_wo_graph(window_id, line_id, ...)` → `nx.DiGraph`

Encodes the **actual production path taken** on a line in a historical week,
for post-mortem comparison against the optimiser's proposal.

- Filters `wo_master.csv` to `wo_kind == "production"` WOs whose `end_day`
  falls in the window.
- Collapses consecutive same-SKU WOs into a single *run* node (matches the
  node-cost model's training granularity).
- Adds ML-predicted node costs (`node_cost_ml`) alongside the actual
  `productive_hours` for direct comparison.
- Fills edges from `wo_changeovers.csv` — costs are **theoretical** (from
  Tabla CF Prat), not observed durations (no timestamps exist in the raw exports).

```python
from services.optimizer.app.graph_builder import build_historical_wo_graph, visualize_wo_graph

G = build_historical_wo_graph("2025-W01-7d", line_id=14)
# G.nodes["ED13LP12_r0"]["predicted_hours"]  → float
# G.nodes["ED13LP12_r0"]["actual_hours"]     → float

fig = visualize_wo_graph(G)
fig.savefig("wo_path_graph.png", dpi=120, bbox_inches="tight")
```

### `visualize_planning_graph(graphs)` and `visualize_wo_graph(graph)`

Return `matplotlib.figure.Figure` objects — call `.savefig()` or `plt.show()`
on them.  The planning graph uses a circular layout with node size ∝ hours and
edge colour ∝ changeover cost.  The WO path uses a left-to-right timeline
where node colour encodes `predicted / actual` ratio.

---

## Skeleton

```
services/optimizer/
├── README.md
├── app/
│   ├── __init__.py
│   ├── implementation.py    ← TODO: GraphOptimizer(GraphOptimizerContract)
│   ├── graph_builder.py     ← graph construction + visualisation (done)
│   ├── vrp_model.py         ← OR-Tools RoutingModel wrapper
│   └── replan.py            ← freeze-window logic
└── tests/
    ├── conftest.py
    └── fixtures/            ← tiny synthetic demand + capability
```
