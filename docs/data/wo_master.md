# `wo_master.csv` — Master work-order table

**Status:** MVP · **Produced by:** [`services/etl/`](../../services/etl/) ·
**Consumers:** every downstream service (spine of the pipeline) ·
**Granularity:** one row per completed work order (WO) in 2025

The cleaned, joined version of `OEE 14_17_19_ 2025.xlsx` +
`Tiempo 14_17_19_ 2025.xlsx` + `Volumen 14_17_19_ 2025.xlsx` +
`Mantenimiento 14_17_19_ 2025.xlsx`. Every other data product is derived from
this one.

## Schema

| Column | Type | Description |
|---|---|---|
| `wo_id` | str (PK) | Unique work-order identifier. Was `OF` / `WOID`. WOs starting with `PRT…-M` are cleanings or manual re-runs. |
| `line_id` | int (14 / 17 / 19) | Canning line. Was `TREN`. |
| `sku_id` | str (FK → `skus.sku_id`) | SKU produced. Was `SKU`. The synthetic value `LIMPIEZA` marks cleaning pseudo-WOs. |
| `start_ts` | timestamp | Derived: `end_ts - total_hours`, then capped at the previous WO's `end_ts` to avoid overlap. |
| `end_ts` | timestamp | Was `Fecha Fin`. The only timestamp directly recorded. |
| `total_hours` | float | Wall-clock duration of the WO. Was `H. Tot.`. |
| `productive_hours` | float | Time the machine was actually running. Was `Tiempo Máquina en Marcha`. |
| `downtime_hours` | float | Time the machine was stopped. Was `Tiempo Máquina en paro` (alias `Par. tot`). |
| `unplanned_stop_hours` | float | Was `PNP`. The chunk just before marcha is the source for empirical changeover time. |
| `idle_hours` | float | Was `IDLE`. |
| `low_speed_hours` | float | Was `Tiempo Baja Velocidad`. |
| `cleaning_hours` | float | Cleaning time inside this WO (not the standalone Friday cleaning). Was `Limpieza` (in Tiempo). |
| `cip_hours` | float | Clean-in-place duration. Was `Tiempo de CIP`. |
| `sterilization_hours` | float | Was `Tiempo de esterilización`. |
| `downstream_block_hours` | float | Production halted because downstream couldn't take the cans (palletiser, etc.). Was `Tiempo Paro por Saturación a la Salida`. |
| `upstream_starve_hours` | float | Production halted because upstream wasn't delivering (beer, cans). Was `Tiempo Paro por Falta Producto`. |
| `maintenance_calls` | int | Number of maintenance calls during the WO. Was `Nº LLamadas`. |
| `maintenance_wait_hours` | float | Time waiting for a technician. Was `Tiempo en Espera`. |
| `maintenance_intervention_hours` | float | Time the technician was working. Was `Tiempo Intervención`. |
| `oee` | float | Overall Equipment Effectiveness for this WO. Was `OEE`. **Can exceed 1.0** for some WOs (see [`cleaning_rules.md`](./cleaning_rules.md) §3). |
| `availability` | float | Was `Disponibilidad`. |
| `performance` | float | Was `Rendimiento`. |
| `quality` | float | Was `Calidad`. Equals 1.0 across the 2025 dataset. |
| `inefficiency` | float | Was `Ineficiencia`. Can be negative for over-production / corrections. |
| `units_produced` | int | Cans produced. Was `UDS`. |
| `hectoliters_produced` | float | Volume produced. Was `HL`. |
| `had_changeover` | bool | Whether this WO followed a changeover. Was `Cambios` (`SI` / `NO`). |
| `wo_kind` | str | Derived: `production` (normal) / `cleaning` (`sku_id == "LIMPIEZA"`) / `maintenance_or_rerun` (`PRT…-M` + non-LIMPIEZA SKU). |

## Lineage

```
OEE 14_17_19_ 2025.xlsx        ──┐
Tiempo 14_17_19_ 2025.xlsx     ──┼─►  join on wo_id  ──►  wo_master.csv
Volumen 14_17_19_ 2025.xlsx    ──┤
Mantenimiento 14_17_19_ 2025.xlsx ┘
```

* Join key: `OF == WOID` (1:1 match for 2 274 WOs).
* `data - 2026-05-18….xlsx` is a duplicate of `OEE` (verified) and is dropped.

## Cleaning rules applied

Detail in [`cleaning_rules.md`](./cleaning_rules.md). Highlights:

* **`start_ts` derivation** — `end_ts - total_hours`, then clamped so it doesn't precede the previous WO's `end_ts` on the same line.
* **Outlier `total_hours`** (max observed 21 065 h ≈ 877 days) flagged but **not** clipped — listed in `ETLResult.warnings`.
* **`oee > 1` / `inefficiency < 0`** preserved. Report P50/P95 downstream rather than capping.
* **`wo_kind` classification**:
  * `PRT…-M` + `sku_id == "LIMPIEZA"` → `cleaning`
  * `PRT…-M` + other `sku_id` → `maintenance_or_rerun`
  * else → `production`
* `MAQUINA` (always `"LLENAD"`), `CENTRO` (always `"PRAT"`), and other constant columns are dropped.
* `Tiempo Operativo Neto` and `Tiempo Operativo Neto2` are dropped — ambiguous definitions, use `productive_hours` instead.

## Used by

* [`skus.csv`](./skus.md) — deduped SKU rows
* [`line_capability.csv`](./line_capability.md) — `(sku, line)` median speed / OEE
* [`node_cost_train.csv`](./node_cost_train.md) — per-WO production-time training set
* [`edge_cost_train.csv`](./edge_cost_train.md) — joined with `wo_changeovers` to build per-transition rows
* [`demand.csv`](./demand.md) — historical-source aggregation
* [`incidents.csv`](./incidents.md) — derive incident windows from maintenance + saturation + starvation columns
