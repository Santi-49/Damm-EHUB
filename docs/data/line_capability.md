# `line_capability.csv` — Which SKUs each line can run, and how well

**Status:** MVP · **Produced by:** [`services/etl/`](../../services/etl/) ·
**Consumers:** optimiser (hard gate + node-cost fallback), simulator (speed lookup) ·
**Granularity:** one row per `(sku_id, line_id)` pair (169 SKUs × 3 lines = 507 rows)

A materialised lookup that combines a **hard gate** (`can_produce`) with the
**node-cost baseline** (`median_speed_uds_per_hour`). The optimiser uses both:

* `can_produce == False` removes all edges to/from that node on that line — a
  hard constraint expressing the format restrictions L14 / L17 / L19.
* `median_speed_uds_per_hour` is the fallback for node cost when the ML
  production-time model isn't trained yet (MVP-1 case).

## Schema

| Column | Type | Description |
|---|---|---|
| `sku_id` | str (PK part) | FK → `skus.sku_id`. |
| `line_id` | int (14 / 17 / 19) | Canning line. PK part. |
| `can_produce` | bool | Hard gate. **True** iff the SKU's `container_type` is in the line's allowed set. |
| `median_speed_uds_per_hour` | float \| null | Median of `wo_master.units_produced / wo_master.productive_hours` for observed pairs; conservative fallback for format-compatible unobserved pairs; null when `can_produce == False`. |
| `median_oee` | float \| null | Median `wo_master.oee` for observed pairs; conservative fallback for format-compatible unobserved pairs; null when `can_produce == False`. |
| `n_workorders_observed` | int | Support — number of historical production WOs for this `(sku_id, line_id)`. `0` means the row is format-compatible but fallback-valued. |

## Capability rules (hard)

| Line | Allowed `container_type` |
|---|---|
| L14 | `1/2` (50 cl), `1/3` (33 cl) |
| L17 | `1/3` (33 cl) only |
| L19 | `1/2` (50 cl), `1/3` (33 cl), `2/5` (44 cl) |

A SKU with a `container_type` outside its line's allowed set has
`can_produce = False` regardless of history.

A SKU with `can_produce = True` from format but `n_workorders_observed == 0` is
flagged in `ETLResult.warnings` as `capability_format_only`. The ETL fills
speed/OEE from the same SKU's strongest observed line with a 10 % penalty. If
that is unavailable, it falls back to the same line/container median, then the
global median, also with a 10 % penalty.

## Lineage

```
wo_master.csv  ──┐
                 ├──► groupby(sku_id, line_id) → median speed/oee, count
skus.csv       ──┘                                   │
                                                     ▼
                                              line_capability.csv
                                                     │
                                      apply hard format rule via skus.container_type
```

## Cleaning rules applied

* Skip `wo_kind != "production"` rows from `wo_master` (cleaning / maintenance
  WOs don't carry meaningful speed).
* Use median (not mean) — speed distribution has a long tail of slow WOs
  caused by incidents.
* Round `median_speed_uds_per_hour` to integer cans/hour (the underlying
  measurement precision is way coarser).
* Preserve support separately: fallback-valued rows keep
  `n_workorders_observed == 0`.

## Validation

The ETL validates:

* exactly one row per `(sku_id, line_id)`
* line IDs are only `14`, `17`, `19`
* `can_produce` matches the hard format rule
* all `can_produce == True` rows have non-null positive speed/OEE
* all `can_produce == False` rows have null speed/OEE
* `sku_id` values all exist in `skus.csv`

## Used by

* Optimiser: hard capability gate and node-cost fallback.
* Simulator: `median_speed_uds_per_hour` to convert `units_planned` into
  `productive_hours` for proposed slots.
