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

## Skeleton

```
services/optimizer/
├── README.md
├── app/
│   ├── __init__.py
│   ├── implementation.py    ← TODO: GraphOptimizer(GraphOptimizerContract)
│   ├── graph.py             ← node/edge construction, chunking, calendar expansion
│   ├── vrp_model.py         ← OR-Tools RoutingModel wrapper
│   └── replan.py            ← freeze-window logic
└── tests/
    ├── conftest.py
    └── fixtures/            ← tiny synthetic demand + capability
```
