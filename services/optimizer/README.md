# `services/optimizer/` — Graph optimiser (Architecture D)

> Owner: Person 2 · Contract: [`GraphOptimizerContract`](../../packages/contracts/module/optimizer.py) · Status: skeleton

This is the heart of LineWise. It implements the graph-search algorithm described in
[`docs/linewise/implementacion.md`](../../docs/linewise/implementacion.md) §3.D.

## What this service does, in plain words

You have a **complete graph** where:

- Each **node** represents a SKU chunk that has to be produced. Node cost on a
  given line = production time `(uds_chunk / speed_median + ramp_up)`.
- Each **edge** represents a possible transition between two SKUs on a line. Edge
  cost = changeover time (provided by [`services/changeover-ml/`](../changeover-ml/),
  clamped to the theoretical floor from `Tabla CF Prat`).
- **Both node and edge costs vary by line** — the same SKU runs at a different
  speed on L14 than on L17, and the same `A → B` transition takes longer on one
  line than another.

**Hard capability constraints** (a SKU cannot be planned on a line whose format it
doesn't support):

| Line | Allowed formats |
|---|---|
| **L14** | 1/2 (50 cl), 1/3 (33 cl) |
| **L17** | 1/3 (33 cl) only |
| **L19** | 1/2 (50 cl), 1/3 (33 cl), 2/5 (44 cl) |

Find:

1. The **distribution** of nodes across the three lines (a partition into three
   subgraphs) that respects capability.
2. The **path inside each subgraph** that visits its nodes in the cheapest order.

**Objective: minimise the maximum total time across the three lines (makespan).** With
a tiny `ε`-weighted sum-of-times tie-breaker so the solver doesn't strand a line idle.

## Why a multi-vehicle VRP fits this exactly

Three "vehicles" = three lines. Each vehicle has a temporal capacity = available hours
in the planning horizon. Forced events (Friday cleaning, Monday-biweekly maintenance,
injected breakdowns) are nodes with time windows. The makespan objective is native to
OR-Tools' `RoutingModel`.

When capacity is insufficient, every demand node becomes **disjunctive**: it is
optional, with a penalty = `margen[sku] × uds_chunk`. The solver drops the
cheapest-margin SKUs first, no branching code required.

## Contract recap in plain words

> Given the demand, capability map, ML edge predictions, and calendar, return a
> sequence of slots assigned to lines such that (a) every node respects the
> capability constraints, (b) every forced calendar event is honoured, and
> (c) the makespan across L14/L17/L19 is minimised. If the load doesn't fit,
> emit the dropped SKUs (lowest margin first) and flag `feasible = False`.

## Inputs

- `data/clean/demand.csv` → list of `DemandBucket`. The optimiser may further
  chunk large buckets into ≤ `chunk_max_productive_h` (default 8 h) sub-nodes.
- `data/clean/sku_line_capability.csv` → `(sku, tren) → can_produce, speed_median, oee_median`.
- `data/clean/changeover_matrix.csv` → theoretical floor.
- ML model from [`services/changeover-ml/`](../changeover-ml/) → live edge weights.
- `data/clean/calendar_constraints.csv` → forced events with windows.
- `data/clean/optimizer_hyperparams.yaml` → `horizon_days`, `freeze_days`,
  `lambda_changeover`, `mu_demanda_no_cubierta`, `nu_beneficio`, `margen_per_sku`.

## Output

`OptimizerOutput` carrying a `Sequence` plus per-line makespan, global makespan,
dropped SKUs, and the solver log. The simulator consumes the `Sequence` to compute
OEE-style metrics — the optimiser itself never reports OEE.

## Replan

`replan(previous, inputs, ml)` is what the UI calls when the user injects a
breakdown or urgent demand. It respects `freeze_days`: the first N days of
`previous` are taken as fixed.

## Stack

- **OR-Tools** (`ortools.constraint_solver.pywrapcp`) — proven VRP with disjunctions,
  time windows, makespan via `SetSpanCostCoefficientForVehicle`.
- Plain Python orchestration; no GPU, no async I/O bottleneck.

## Definition of done

- [ ] `optimize(inputs, ml)` returns a valid `OptimizerOutput` on the demo week
      in < 5 s on a laptop.
- [ ] Every slot respects `sku_line_capability`.
- [ ] Forced calendar events appear in the output at their declared windows.
- [ ] When demand exceeds capacity, `feasible = False` and `dropped` lists the
      lowest-margin SKUs.
- [ ] `replan` preserves slots inside the freeze window byte-for-byte.

## Skeleton

```
services/optimizer/
├── README.md
├── app/
│   ├── __init__.py
│   ├── implementation.py    ← TODO: GraphOptimizer(GraphOptimizerContract)
│   ├── graph.py             ← node/edge construction, chunking
│   ├── vrp_model.py         ← OR-Tools RoutingModel wrapper
│   └── replan.py            ← freeze-window logic
└── tests/
    ├── conftest.py
    └── fixtures/            ← tiny synthetic demand + capability
```
