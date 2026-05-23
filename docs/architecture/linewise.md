# LineWise — Architecture (Arch D)

> System-level view of the LineWise solution. See also: [System Overview](overview.md) ·
> [Module Contracts](../contracts.md) · [Functionality map](../functionalities/overview.md) ·
> deep dives in [`docs/linewise/`](../linewise/).

## 1. One-paragraph summary

Weekly demand → graph (nodes = SKU chunks, edges = changeover times) → OR-Tools VRP with
three "vehicles" (lines) and a **makespan** objective → proposed sequence → deterministic
simulator that replays real incidents → side-by-side comparison with `S_real`. ML is
scoped to **predicting edge weights only**; OEE is *computed*, never predicted, at the
reporting layer.

## 2. Why Architecture D

Four options were compared (full breakdown in
[`docs/linewise/implementacion.md`](../linewise/implementacion.md) §3):

| Arch | What it is | Picked because… |
|---|---|---|
| A | Greedy + rules | Simple fail-safe — kept as `S_opt_fallback` |
| B | ILP / CP-SAT | Powerful but hard to story-tell, brittle to model |
| C | Greedy + local search + ML for OEE | Predicts a composite KPI — harder to defend |
| **D** | **m-TSP graph + ML edge weights** | **Best storytelling, cleanest decoupling, mature solver (OR-Tools VRP), bounded ML target** |

## 3. Pipeline

```
                ┌──────────────┐
data/raw/  ──►  │  services/   │  ──►  data/clean/*.csv
*.xlsx          │  etl/        │
                └──────────────┘
                       │
                       ▼
                ┌──────────────────────────────┐
                │  services/optimizer/         │     uses:
                │    1. build graph            │  ◄── sku_line_capability.csv
                │    2. ask ML for edge costs  │  ◄── services/changeover-ml/
                │    3. solve OR-Tools VRP     │  ◄── changeover_matrix.csv (floor)
                │       (3 vehicles, makespan) │  ◄── calendar_constraints.csv
                │    4. emit sequence          │  ◄── demand.csv
                └──────────────────────────────┘
                       │ sequence (list[Slot])
                       ▼
                ┌──────────────────────────────┐
                │  services/simulator/         │     uses:
                │   evaluate_sequence()        │  ◄── sku_line_capability.csv
                │   + incident replay          │  ◄── incident_log.csv
                │   = OEE, h_changes, coverage │  ◄── calendar_constraints.csv
                └──────────────────────────────┘
                       │ metrics
                       ▼
                ┌──────────────────────────────┐
                │  services/api/   →  apps/web │
                │  Gantt · drill-down · what-if│
                └──────────────────────────────┘
```

## 4. Five functionalities, five workspaces

| # | Functionality | Folder | Contract | Owner |
|---|---|---|---|---|
| 1 | **ETL — Data cleaning** | [`services/etl/`](../../services/etl/) | [`ETLContract`](../../packages/contracts/module/etl.py) | Person 1 |
| 2 | **Demand dataset generation** (weekly buckets) | [`services/etl/`](../../services/etl/) (sub-task) | [`DemandBuilderContract`](../../packages/contracts/module/etl.py) | Person 1 |
| 3 | **ML changeover predictor** | [`services/changeover-ml/`](../../services/changeover-ml/) | [`ChangeoverModelContract`](../../packages/contracts/module/changeover_ml.py) | Person 2 |
| 4 | **Graph optimiser (Arch D)** | [`services/optimizer/`](../../services/optimizer/) | [`GraphOptimizerContract`](../../packages/contracts/module/optimizer.py) | Person 2 |
| 5 | **Simulator (deterministic OEE)** | [`services/simulator/`](../../services/simulator/) | [`SimulatorContract`](../../packages/contracts/module/simulator.py) | Person 1 |
| — | **UI (Gantt + drill-down + what-if)** | [`apps/landing/`](../../apps/landing/), [`apps/web/`](../../apps/web/) | OpenAPI types in [`packages/contracts/api/generated/`](../../packages/contracts/api/generated/) | Person 3 |

Each service folder has a `README.md` that re-states the contract in natural language
(input, output, invariants, validation criteria) plus a skeleton `app/` directory.

## 5. The graph optimiser contract — in plain words

**Input:** a complete graph where every node is a SKU chunk that must be produced,
with line-specific node cost (production time = run_time + ramp_up) and line-specific
edge cost (changeover time from SKU A to SKU B on a given line). Each line has
**hard capability constraints** (L14: 1/2 & 1/3 only; L17: 1/3 only; L19: 1/2 & 1/3 & 2/5).

**Output:** a partitioning of the nodes into three subgraphs (one per line) **and** an
ordered path within each subgraph that respects the capability constraints.

**Objective:** minimise the **maximum total time across the three lines** (makespan),
with a small ε-weighted sum-of-times tie-breaker so the solver doesn't leave one line idle.

**Why this is well-formed**:
- The lines' demands are independent only through the makespan term, which is exactly
  the right coupling for a multi-vehicle routing problem.
- Capability is encoded as a hard constraint on which vehicle visits each node.
- Forced events (cleaning Friday 8 h, maintenance Monday-quincennial 8 h) are nodes
  with time-window constraints.
- Insufficient capacity is handled by **disjunctions with penalty** — each demand node
  is optional with penalty `margen[sku] × uds_chunk`, so the solver drops the
  cheapest-margin SKUs first without any branching in the code.

## 6. Two-engine decoupling

```
┌───────────────────┐   sequence    ┌───────────────────┐
│  OPTIMISER        │  ──────────►  │  SIMULATOR        │
│  predicts ONLY    │               │  deterministic    │
│  changeover times │               │  OEE + incidents  │
│  (via ML edges)   │  ◄───────────-│  emits "infeasible"│
└───────────────────┘  capacity     └───────────────────┘
                       feedback
```

The optimiser **never** predicts OEE. The simulator never makes routing decisions.
This means:

1. **Fair comparison** with `S_real` — same simulator, same incidents, same calendar.
2. **Bounded ML target** — changeover_time is observable and validatable; OEE is not.
3. **No risk of divergence** between "predicted OEE" used for routing and "reported OEE"
   used for KPI.

## 7. Implementation milestones

(See [`docs/challenge/CONSTRAINTS.md`](../challenge/CONSTRAINTS.md) for dates and
[`docs/linewise/resumen.md`](../linewise/resumen.md) §6 for the full Gantt.)

| Milestone | Unblocks |
|---|---|
| **M1** ETL CSVs in `data/clean/` | optimiser + UI + ML training |
| **M2** Simulator validated against historical OEE (< 5 % error) | fair comparison KPI |
| **M3** Arch A fallback end-to-end | demo safety net |
| **M4** Arch D (OR-Tools VRP) integrated | primary demo path |
| **M5** What-if (breakdown / urgent demand) wired | re-plan story |
| **M6** Dry-run | confidence for the jury |

## 8. Risks (carried from `docs/linewise/cobertura_brief.md` §10)

| Risk | Severity | Mitigation |
|---|---|---|
| OR-Tools VRP integration slips | medium | Arch A is ready since Saturday evening |
| ML edges underperform | medium | Theoretical matrix is the floor; ML only adjusts where confident |
| Simulator doesn't reproduce historical OEE | medium-high | Person 1 dedicates Sunday morning to validation |
| Confidential data leaks via git | **high** | `.gitignore` rules already in place; verify before every push |
| Demo glitches live | medium | Pre-record a backup video; rehearse end-to-end |
