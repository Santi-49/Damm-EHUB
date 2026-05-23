# Functionality Map

> Where each piece of LineWise lives, who owns it, and which contract it satisfies.
> Companion to [`docs/architecture/linewise.md`](../architecture/linewise.md).

## TL;DR

Five functionalities, five workspaces, five contracts. The UI lives in the existing
`apps/` workspaces.

```
data/raw/  ─►  [1] services/etl/         ─►  data/clean/*.csv
                       │                          │
                       │ DemandBuilderContract    │
                       ▼                          ▼
              data/clean/demand.csv         [3] services/changeover-ml/
                       │                          │ ChangeoverModelContract
                       │                          │
                       └─────►  [4] services/optimizer/  ──► Sequence
                                       │
                                       ▼
                              [5] services/simulator/  ──► SimulationReport
                                       │
                                       ▼
                                services/api/  ──►  apps/web/, apps/landing/
```

## The five workspaces

| # | Functionality | Folder | Contract | Owner | Milestone |
|---|---|---|---|---|---|
| 1 | **Data cleaning (ETL)** — raw Excel → clean CSV | [`services/etl/`](../../services/etl/) | [`ETLContract`](../../packages/contracts/module/etl.py) | Person 1 | M1 (Sat 13:00) |
| 2 | **Demand dataset** — weekly buckets `(sku, semana, uds)` | same folder as #1 | [`DemandBuilderContract`](../../packages/contracts/module/etl.py) | Person 1 | M1 (Sat 13:00) |
| 3 | **ML changeover predictor** — predicts edge weights | [`services/changeover-ml/`](../../services/changeover-ml/) | [`ChangeoverModelContract`](../../packages/contracts/module/changeover_ml.py) | Person 2 | Sun morning |
| 4 | **Graph optimiser (Arch D)** — m-TSP / VRP on 3 lines | [`services/optimizer/`](../../services/optimizer/) | [`GraphOptimizerContract`](../../packages/contracts/module/optimizer.py) | Person 2 | M4 (Sun 14:00) |
| 5 | **Simulator** — deterministic OEE + incident replay | [`services/simulator/`](../../services/simulator/) | [`SimulatorContract`](../../packages/contracts/module/simulator.py) | Person 1 | M2 (Sat 19:00) |
| — | **UI** (Gantt, drill-down, what-if) | [`apps/web/`](../../apps/web/), [`apps/landing/`](../../apps/landing/) | OpenAPI types from [`packages/contracts/api/generated/`](../../packages/contracts/api/generated/) | Person 3 | rolling |

## Contract import paths

```python
# All shared dataclasses
from packages.contracts.module.schemas import (
    DemandBucket, SkuLineCapability, ChangeoverEdge,
    CalendarConstraint, Incident, Slot, Sequence,
    OptimizerInput, OptimizerOutput, SimulationReport,
    OptimizerHyperparams,
)

# Each functionality's Protocol
from packages.contracts.module.etl           import ETLContract, DemandBuilderContract
from packages.contracts.module.changeover_ml import ChangeoverModelContract
from packages.contracts.module.optimizer     import GraphOptimizerContract
from packages.contracts.module.simulator     import SimulatorContract
```

A single-import backward-compatible shim still lives at
`packages.contracts.module.interface`.

## What each contract guarantees (the natural-language restatement)

### 1. ETL — `ETLContract`

> Read every raw Excel under `data/raw/`. Produce the eight tidy CSVs under
> `data/clean/` documented in [`docs/linewise/datos.md`](../linewise/datos.md) §3.
> Never modify the raw files. Surface data-quality warnings (OEE > 1,
> `H. Tot.` outliers, ambiguous `Frecuencia Total`, …) — do not silently clip.

### 2. Demand dataset — `DemandBuilderContract`

> Aggregate any planning source (historical 2025, JDA plan 2026, what-if form) to
> weekly `DemandBucket(window_id, window_start, window_end, sku, uds_demanded,
> source, prioridad)`. The optimiser never sees `tren / día / turno` — those
> are decisions, not demand.

### 3. ML changeover — `ChangeoverModelContract`

> Given two SKUs and a line, predict the changeover time in hours, with a
> confidence and a source tag (`ml` / `hibrido` / `teorico`). The optimiser uses
> the result as an edge weight in its graph. Never predict OEE.

### 4. Graph optimiser — `GraphOptimizerContract`

> Given a complete graph where each node is a SKU chunk with line-specific
> production time, and each edge is a line-specific changeover time, return:
> (a) the **distribution of nodes across the three lines** (subgraphs) respecting
> the hard capability constraints
> (L14 → 1/2 & 1/3; L17 → 1/3 only; L19 → 1/2, 1/3, 2/5),
> and (b) the **ordered path inside each subgraph**, minimising the **maximum
> total time across the three lines** (makespan). When demand exceeds capacity,
> drop the lowest-margin SKUs via OR-Tools disjunction penalties; expose them in
> `OptimizerOutput.dropped` with `feasible = False`.

### 5. Simulator — `SimulatorContract`

> Take any `Sequence`, the calendar, and the incident log. Replay incidents
> deterministically against `(tren, instante)` so `S_real` and `S_opt` are
> measured under the same conditions. Return a `SimulationReport` with per-line
> and global OEE, hour decomposition, coverage and makespan.

## Definition of "ready to integrate"

Each service is considered ready when its README's *Definition of done* checklist
is satisfied **and** an end-to-end pipeline run (ETL → ML → Optimizer → Simulator)
produces a `SimulationReport` for the demo week without errors.
