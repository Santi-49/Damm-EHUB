# `node_cost_train.csv` — Training table for production-time / speed model

**Status:** post-MVP (optimiser MVP-1 uses `line_capability.median_speed_uds_per_hour` directly) ·
**Produced by:** [`services/etl/`](../../services/etl/) ·
**Consumers:** an optional production-time ML model ·
**Granularity:** one row per `wo_master` row classified as `wo_kind == "production"`

Training table for a regressor that predicts **production time per unit** (or
equivalently effective speed) given the SKU, the line, and contextual features.

> The optimiser doesn't strictly need this — `line_capability.csv` already
> carries `median_speed_uds_per_hour` per `(sku_id, line_id)`. Add this dataset
> when you want to capture context effects ("Monday-morning slowdown",
> "back-to-back same SKU runs ramp up faster", etc.).

## Schema

| Column | Type | Description |
|---|---|---|
| `wo_id` | str (PK, FK → `wo_master.wo_id`) | Reference WO. |
| `sku_id` | str | Joined from `wo_master`. |
| `line_id` | int (14/17/19) | Joined from `wo_master`. |
| `start_ts` | timestamp | Joined from `wo_master`. |
| `end_ts` | timestamp | Joined from `wo_master`. |
| **Features** ↓ | | |
| `container_type` | str | From `skus`. |
| `brand` | str | From `skus`. |
| `family` | str | From `skus`. |
| `beer` | str | From `skus`. |
| `material_id` | str | From `skus`. |
| `primary_packaging` | str | From `skus`. |
| `secondary_packaging` | str | From `skus`. |
| `pallet_type` | str | From `skus`. |
| `units_per_case` | float | From `skus`. |
| `day_of_week` | int (0..6) | Derived from `start_ts`. |
| `hour_of_day` | int (0..23) | Derived from `start_ts`. |
| `is_weekend` | bool | Derived. |
| `same_sku_as_prev` | bool | Whether the previous WO on this line had the same SKU. |
| `hours_since_last_cleaning` | float | Derived from `line_calendar`. |
| `cumulative_run_hours_today` | float | Sum of `productive_hours` for previous WOs on this line on the same date. |
| **Targets** ↓ | | |
| `units_produced` | int | From `wo_master`. |
| `productive_hours` | float | From `wo_master`. |
| `effective_speed_uds_per_hour` | float | `units_produced / productive_hours`. Primary regression target. |
| `oee` | float | From `wo_master` — secondary target if a separate OEE model is trained. |

## Lineage

```
wo_master.csv ─┐
                ├──► join on sku_id and on (line_id, start_ts)
skus.csv      ─┤              ↑
                │              compute day_of_week, hour_of_day,
                │              same_sku_as_prev, cumulative_run_hours_today,
                │              hours_since_last_cleaning
                ▼
        node_cost_train.csv
```

## Cleaning rules applied

* Filter `wo_kind == "production"` only.
* Filter out WOs with `productive_hours < 0.5` — too short to be a credible
  training signal (typically aborted runs).
* Drop WOs with `oee > 1.2` from training (those are upstream measurement
  artefacts) but keep them in `wo_master`.

## Modelling notes

* Default target: `effective_speed_uds_per_hour`. Production time for a
  proposed slot then becomes `units_planned / predicted_speed + ramp_up`.
* Walk-forward validation using `WindowConfig.days`-sized windows.
* Compare against the `line_capability.median_speed_uds_per_hour` baseline.
  Only deploy if the model beats the baseline on validation MAE.

## Used by

* (Optional) a production-time predictor. Until that exists, the optimiser
  uses `line_capability.median_speed_uds_per_hour` as the node-cost lookup.
