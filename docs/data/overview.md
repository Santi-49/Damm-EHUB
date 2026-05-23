# Data Products — Catalogue

> Where every clean CSV the LineWise pipeline depends on is documented:
> schema, lineage, cleaning rules, and consumer. Companion to
> [`docs/architecture/linewise.md`](../architecture/linewise.md) and
> [`docs/linewise/datos.md`](../linewise/datos.md) (the original raw inventory).

## Convention

All column names and dataset names are **English snake_case**. Each per-product
doc carries a `Raw → clean` table mapping the original Damm Spanish columns to
the canonical names so the lineage is one click away.

## The nine data products

```
                                                  ┌─────────────────────┐
   data/raw/*.xlsx                                │   ETL                 │
        │                                         │   (services/etl/)     │
        └──────────────────────────────────────►  └──────────┬────────────┘
                                                             │
                ┌────────────────────────────────────────────┼──────────────────────────────────┐
                ▼                                            ▼                                  ▼
       wo_master.csv (spine)                     skus.csv          wo_changeovers.csv (transitions)
                │                                    │                        │
                ├──────► line_capability.csv         │                        │ ← ML training input
                │                                    │                        │   (empirical only)
                ├──────► node_cost_train.csv  ◄──────┤                        │
                │                                    │                        │
                ├──────► demand.csv  (window-aggregated)                       │
                │                                                              │
                └──────► incidents.csv  (simulator, M2)                        │
                                                                               │
   data/raw/Tabla CF Prat 2026_14_17_19.xlsx  ────► line_calendar.csv          │
                                              ────► changeover_costs.csv ◄──── │
                                                    (optimizer floor only,      │
                                                     NOT training data)  ←──────┘
```

| # | Product | Role | Consumers | Status |
|---|---|---|---|---|
| 1 | [`wo_master`](./wo_master.md) | Master cleaned work-order table — the spine | Everyone | **MVP** |
| 2 | [`skus`](./skus.md) | SKU catalogue (deduped attributes) | Everyone | **MVP** |
| 3 | [`wo_changeovers`](./wo_changeovers.md) | Transition master table (`sku_from → sku_to`) with empirical times + features | Changeover-ML (training), UI drill-down | **MVP** |
| 4 | [`demand`](./demand.md) | Window-aggregated demand — single input to the optimiser | Optimiser | **MVP** |
| 5 | [`line_capability`](./line_capability.md) | Hard `(sku, line) → can_produce + median speed/OEE` | Optimiser (hard gate + node cost fallback), simulator | **MVP** |
| 6 | [`line_calendar`](./line_calendar.md) | Forced events per line (cleaning, maintenance, injected breakdowns) | Optimiser, simulator | **MVP** |
| 7 | [`changeover_costs`](./changeover_costs.md) | Theoretical changeover matrix — optimizer floor for unseen pairs | Optimiser (edge weights floor / fallback) | **MVP** |
| 8 | [`node_cost_train`](./node_cost_train.md) | Training table for production-time / speed model | (optional ML) | post-MVP |
| 9 | [`incidents`](./incidents.md) | Deterministic-replay incident log | Simulator only | M2 (deferred) |

**MVP-1 of the optimiser** needs products 1–7. `node_cost_train` (8) is
post-MVP — until then the optimiser uses
`line_capability.median_speed_uds_per_hour` for node cost.

**Changeover ML** trains directly on `wo_changeovers.csv` (product 3) —
empirical transitions only. `changeover_costs.csv` is the optimizer's floor
for pairs the ML has never seen; it is never a training input.

## Time window

Demand aggregation and the optimiser's planning horizon share a single knob:
[`WindowConfig`](../../packages/contracts/module/schemas.py) with
``days=7, anchor="monday"`` by default. Change it once and both
`demand.csv` and one optimisation run move in lockstep.

## Naming

* Columns: English snake_case. Hours in column names always end in `_hours`.
* Units: counts of cans use `units_*` (was `UDS`), hectoliters `hectoliters_*` (was `HL`).
* Identifiers: always `_id` suffix (`sku_id`, `line_id`, `wo_id`).
* Booleans: `had_*`, `is_*`, `can_*`, or `flag_*` for explicit boolean change indicators.
* Timestamps: `_ts` suffix (`start_ts`, `end_ts`).

## Where the cleaning rules live

See [`cleaning_rules.md`](./cleaning_rules.md) for the full data-cleaning
recipe (derivations, outlier handling, ambiguous columns, discarded files).
That document is the secondary reference — the per-product docs in this folder
are the primary reference for consumers.
