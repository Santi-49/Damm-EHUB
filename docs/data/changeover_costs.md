# `changeover_costs.csv` — Fused changeover hours per `(line_id, sku_from_id, sku_to_id)`

**Status:** MVP · **Produced by:** [`services/etl/`](../../services/etl/) ·
**Consumers:** optimiser (edge weights), changeover ML (theoretical floor) ·
**Granularity:** one row per `(line_id, sku_from_id, sku_to_id)` triple that exists in history or in the theoretical matrix

The single source the optimiser reads for edge weights. Combines theoretical
values from `Tabla CF Prat` with empirical observations, segmented by which
component drove the cost so it sums to the total.

## Schema

| Column | Type | Description |
|---|---|---|
| `line_id` | int (PK part, 14/17/19) | Line on which the transition takes place. |
| `sku_from_id` | str (PK part) | Predecessor SKU. |
| `sku_to_id` | str (PK part) | Successor SKU. |
| `total_hours` | float | Total changeover hours. `sum(segment_*_hours) == total_hours`. |
| `segment_brand_hours` | float | Time attributable to a brand change. |
| `segment_container_hours` | float | Time attributable to a container/format change. |
| `segment_cap_hours` | float | Time attributable to a cap change. |
| `segment_primary_pack_hours` | float | Time attributable to a primary packaging change. |
| `segment_secondary_pack_hours` | float | Time attributable to a secondary packaging change. |
| `segment_pallet_hours` | float | Time attributable to a pallet-type change. |
| `segment_product_hours` | float | Time attributable to a product (recipe) change. |
| `segment_volume_hours` | float | Time attributable to a volume change. |
| `segment_startup_hours` | float | Constant arranque time per line. |
| `segment_shutdown_hours` | float | Constant final time per line. |
| `n_observations` | int | Number of historical transitions of this triple. |
| `source` | str (`teorico` / `empirico` / `hibrido`) | How the row was produced (see below). |

## Source-tag semantics

| `source` | Meaning |
|---|---|
| `teorico` | Pure theoretical value parsed from `Tabla CF Prat`. Used when `n_observations < 5`. |
| `empirico` | Pure empirical aggregation from history. Used when `n_observations >= 5` and theoretical is unavailable. |
| `hibrido` | Empirical anchored to the theoretical floor: `total_hours = max(theoretical_total, empirical_median)`. Used when both are present and `n_observations >= 5`. |

## Lineage

```
Tabla CF Prat 2026_14_17_19.xlsx (sheet "LATA_BARRIL")
   │   parse human duration strings, expand the partial format-pair matrix
   │   to all SKU pairs by joining via skus.container_type, brand, packaging
   └──► theoretical rows (source = "teorico")

wo_master.csv + wo_changeovers.csv
   │   for each (sku_prev_id → sku_curr_id) transition on the same line,
   │   take wo_changeovers.empirical_changeover_hours (validated against
   │   wo_master.unplanned_stop_hours), segment by the flag_* columns
   └──► empirical rows (source = "empirico")

         ┌──────────► fusion: keep max(theoretical, empirical_median)
         │                    when both exist and n_observations >= 5
         ▼
   changeover_costs.csv
```

## Cleaning rules applied

* Parse strings like `"3 h"`, `"30 min"`, `"1 h 15 min"` to decimal hours.
* The theoretical matrix is keyed by `container_type` pairs, not SKU pairs.
  Expand to all SKU pairs by joining through `skus.container_type` and adding
  segment contributions for brand / packaging changes per the CF sheet.
* The sum-equals-total invariant is enforced post-fusion: if rounding pushes
  the segment sum away from `total_hours`, the residual is added to
  `segment_startup_hours` (the noisiest line item).
* For pairs with 0 historical observations and 0 theoretical entry (genuinely
  unseen), apply a conservative `total_hours = max_observed_changeover_on_line`
  and tag `source = "teorico"` with `n_observations = 0`. Warn.

## Used by

* **Optimiser** — `total_hours` is the edge weight in the m-TSP graph for
  MVP-1 (no ML). Once the ML model is active, `changeover_costs` provides the
  **floor**: the optimizer clamps `max(theoretical_total, ml_prediction)` so
  the ML can never predict below the physical minimum.
* **Changeover ML inference** — fallback for `(line_id, sku_from_id, sku_to_id)`
  triples the model has never seen in `wo_changeovers.csv`.

> **NOT a training input.** The changeover ML model trains exclusively on
> real observations in `wo_changeovers.csv`. Theoretical values from this table
> must never be mixed into the training set.
