# `wo_master.csv` — Master work-order table

**Status:** MVP · **Produced by:** [`services/etl/`](../../services/etl/) ·
**Consumers:** every downstream service (spine of the pipeline) ·
**Granularity:** one row per completed work order (WO) in 2025

The cleaned, joined version of `OEE 14_17_19_ 2025.xlsx` +
`Tiempo 14_17_19_ 2025.xlsx` + `Volumen 14_17_19_ 2025.xlsx` +
`Mantenimiento 14_17_19_ 2025.xlsx`.

The historical exports contain **date-only** `Fecha Fin` values. They do not
contain actual WO start/end timestamps. Sequence-sensitive products therefore
use `source_row_order` and `line_sequence_order`, not inferred timestamps.

## Schema

| Column | Type | Description |
|---|---|---|
| `wo_id` | str (PK) | Unique work-order identifier. Was `OF` / `WOID`. WOs starting with `PRT…-M` are cleanings or manual re-runs. |
| `line_id` | int (14 / 17 / 19) | Canning line. Was `TREN`. |
| `sku_id` | str (FK -> `skus.sku_id`) | SKU produced. Was `SKU`. The synthetic value `LIMPIEZA` marks cleaning pseudo-WOs. |
| `end_day` | date | Date-only value from `Fecha Fin`. No time-of-day exists in the historical source. |
| `source_row_order` | int | Original row order in the OEE export. Used to break ties inside the same line/day. |
| `line_sequence_order` | int | Derived order within each line after sorting by `(line_id, end_day, source_row_order, wo_id)`. |
| `total_hours` | float | Wall-clock duration of the WO. Was `H. Tot.`. |
| `productive_hours` | float | Time the machine was actually running. Was `Tiempo Máquina en Marcha`. |
| `downtime_hours` | float | Time the machine was stopped. Was `Tiempo Máquina en paro` / `Par. tot`. |
| `unplanned_stop_hours` | float | Was `PNP`. WO-level downtime context, not a pure changeover target. |
| `idle_hours` | float | Was `IDLE`. |
| `low_speed_hours` | float | Was `Tiempo Baja Velocidad`. |
| `cleaning_hours` | float | Cleaning time inside this WO. Was `Limpieza` in `Tiempo`. |
| `cip_hours` | float | Clean-in-place duration. Was `Tiempo de CIP`. |
| `sterilization_hours` | float | Was `Tiempo de esterilización`. |
| `downstream_block_hours` | float | Halt because downstream could not receive cans. Was `Tiempo Paro por Saturación a la Salida`. |
| `upstream_starve_hours` | float | Halt because upstream was not delivering. Was `Tiempo Paro por Falta Producto`. |
| `maintenance_calls` | int | Number of maintenance calls during the WO. Was `Nº LLamadas`. |
| `maintenance_wait_hours` | float | Time waiting for a technician. Was `Tiempo en Espera`. |
| `maintenance_intervention_hours` | float | Time the technician was working. Was `Tiempo Intervención`. |
| `oee` | float | Overall Equipment Effectiveness for this WO. Was `OEE`. Can exceed 1.0 for some WOs. |
| `availability` | float | Was `Disponibilidad`. |
| `performance` | float | Was `Rendimiento`. |
| `inefficiency` | float | Was `Ineficiencia`. Can be negative for over-production / corrections. |
| `units_produced` | int | Cans produced. Was `UDS`. |
| `hectoliters_produced` | float | Volume produced. Was `HL`. |
| `had_changeover` | bool | Whether the OEE export marked the WO as following a changeover. Was `Cambios` (`SI` / `NO`). |
| `wo_kind` | str | Derived: `production` / `cleaning` / `maintenance_or_rerun`. |

## Lineage

```
OEE 14_17_19_ 2025.xlsx           ──┐
Tiempo 14_17_19_ 2025.xlsx        ──┼─► join on wo_id ──► wo_master.csv
Volumen 14_17_19_ 2025.xlsx       ──┤
Mantenimiento 14_17_19_ 2025.xlsx ──┘
```

* Join key: `OF == WOID`.
* `data - 2026-05-18….xlsx` is a duplicate of `OEE` and is dropped.

## Cleaning Rules Applied

* `Fecha Fin` is normalized to `end_day`; time-of-day is not invented.
* `source_row_order` is preserved from the OEE export.
* `line_sequence_order` is derived per line from `(end_day, source_row_order, wo_id)`.
* `wo_kind` classification:
  * `PRT…-M` + `sku_id == "LIMPIEZA"` -> `cleaning`
  * `PRT…-M` + other `sku_id` -> `maintenance_or_rerun`
  * else -> `production`
* Outliers such as tiny/huge `total_hours`, `oee > 1`, and negative
  `inefficiency` are preserved and surfaced as warnings.
* Maintenance time is kept as WO-level incident context. It is not interpreted
  as changeover time.

## Used By

* [`skus.csv`](./skus.md) — deduped SKU rows
* [`wo_changeovers.csv`](./wo_changeovers.md) — historical consecutive production transitions
* [`line_capability.csv`](./line_capability.md) — `(sku, line)` median speed / OEE
* [`node_cost_train.csv`](./node_cost_train.md) — per-WO production-time training set
* [`demand.csv`](./demand.md) — historical-source aggregation
* [`incidents.csv`](./incidents.md) — future incident/context extraction
