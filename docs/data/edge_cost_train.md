# `edge_cost_train.csv` — Training table for the changeover-time model

**Status:** post-MVP (optimiser MVP-1 uses `changeover_costs.csv` directly) ·
**Produced by:** [`services/etl/`](../../services/etl/) ·
**Consumers:** [`services/changeover_ml/`](../../services/changeover_ml/) ·
**Granularity:** one row per observed transition `(sku_from_id → sku_to_id)` on the same line

Training table for the changeover-time predictor. Target carries both a
**total** and the **segmented decomposition**, with the
`sum(segments) == total` invariant. SHAP on each segment is far more useful
than SHAP on the total alone.

## Schema

| Column | Type | Description |
|---|---|---|
| `transition_id` | str (PK) | `wo_to_id` (the changeover ends with the start of that WO). |
| `line_id` | int (14/17/19) | Line of the transition. |
| `sku_from_id` | str (FK → `skus.sku_id`) | Predecessor SKU. |
| `sku_to_id` | str (FK → `skus.sku_id`) | Successor SKU. |
| `wo_from_id` | str (FK → `wo_master.wo_id`) | Predecessor WO. |
| `wo_to_id` | str (FK → `wo_master.wo_id`) | Successor WO. |
| `transition_ts` | timestamp | Effectively `wo_to_master.start_ts`. |
| **Features — SKU pair attributes** ↓ | | (joined from `skus`) |
| `from_container_type`, `to_container_type` | str | |
| `from_brand`, `to_brand` | str | |
| `from_beer`, `to_beer` | str | |
| `from_primary_packaging`, `to_primary_packaging` | str | |
| `from_secondary_packaging`, `to_secondary_packaging` | str | |
| `from_pallet_type`, `to_pallet_type` | str | |
| **Features — change flags** ↓ | | (from `wo_changeovers`) |
| `flag_brand_change` | bool | |
| `flag_container_change` | bool | |
| `flag_cap_change` | bool | |
| `flag_primary_pack_change` | bool | |
| `flag_secondary_pack_change` | bool | |
| `flag_pallet_change` | bool | |
| `flag_product_change` | bool | |
| `flag_volume_change` | bool | |
| `principal_change_type` | str | Driving component label. |
| `n_components_changed` | int | How many flags fired. |
| **Features — context** ↓ | | |
| `day_of_week` | int (0..6) | Derived from `transition_ts`. |
| `hour_of_day` | int (0..23) | Derived. |
| `hours_since_line_started` | float | Time since the first WO of the day on this line. |
| **Targets** ↓ | | |
| `total_changeover_hours` | float | Total. Derived from `wo_changeovers.empirical_changeover_hours` validated against the leading chunk of `wo_to_master.unplanned_stop_hours`. |
| `segment_brand_hours` | float | See below for how segments are imputed. |
| `segment_container_hours` | float | |
| `segment_cap_hours` | float | |
| `segment_primary_pack_hours` | float | |
| `segment_secondary_pack_hours` | float | |
| `segment_pallet_hours` | float | |
| `segment_product_hours` | float | |
| `segment_volume_hours` | float | |
| `segment_startup_hours` | float | Constant per line from CF sheet. |
| `segment_shutdown_hours` | float | Constant per line from CF sheet. |
| `segment_sum_error` | float | `total_changeover_hours - sum(segment_*_hours)`. Should be ~ 0.0; rows where \|error\| > 0.1 h are flagged via `is_segment_sum_inconsistent`. |
| `is_segment_sum_inconsistent` | bool | Quality gate — ML training should weight these rows lower or exclude them. |

## How segment hours are imputed

The raw data only gives **total** empirical changeover time and **flags**
indicating which components changed. To split the total into segments:

1. Look up theoretical contribution per segment from `changeover_costs.csv`
   for the same `(line_id, sku_from_id, sku_to_id)` triple.
2. Normalise the theoretical segment contributions so they sum to the
   empirical `total_changeover_hours`:
   `segment_x_hours = theoretical_segment_x_hours * (empirical_total / theoretical_total)`.
3. `segment_startup_hours` and `segment_shutdown_hours` are line-level
   constants from the CF sheet, **not** scaled.
4. Compute the residual `segment_sum_error = total - sum(segments)`. Should be
   ~ 0; rounding artefacts are absorbed into `segment_startup_hours`.

If theoretical data is missing for the triple, fall back to **flag-weighted
attribution**: assign the total proportionally across the `flag_*` columns
that are `True`, using global mean ratios per flag. Mark
`is_segment_sum_inconsistent = True` so the ML training can downweight those
rows.

## Lineage

```
wo_master.csv (sequential by line)
   │
   └──► derive (sku_from, sku_to, transition_ts, empirical_total) per pair
        │
wo_changeovers.csv ──► join on wo_to_id → adds flags + principal_change_type
skus.csv          ──► join twice (from / to) for attribute features
changeover_costs.csv (theoretical) ──► impute segments
   │
   └──► edge_cost_train.csv
```

## Cleaning rules applied

* Drop transitions where the time gap between consecutive WOs is >= 24 h on
  the same line — likely covers maintenance/cleaning, not a real changeover.
* Drop transitions where `wo_to_master.wo_kind != "production"`.
* Cap `total_changeover_hours` at the line's observed P99 (e.g., 12 h).
  Above that almost certainly indicates an unrecorded breakdown overlapping
  the changeover.

## Modelling notes

* Use a **multi-target** regressor (one head per segment) or two models (one
  for total, one for each segment normalised to share = 1). Both options must
  enforce the sum-equals-total invariant at inference time.
* Walk-forward validation by `WindowConfig.days`-sized windows.

## Used by

* [`services/changeover_ml/`](../../services/changeover_ml/) — training input.
