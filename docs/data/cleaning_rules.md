# Cleaning Rules (secondary reference)

> Consolidated data-cleaning recipe behind every product in
> [`docs/data/overview.md`](./overview.md). Primary references for consumers
> are the per-product docs; this file is the where-questions-go-when-something-is-weird page.

## 0. Files discarded entirely

| File | Reason |
|---|---|
| `data - 2026-05-18T181640.542.xlsx` | Verified row-by-row duplicate of `OEE 14_17_19_ 2025.xlsx`. |
| `Diario Hl_Planif.xlsx` | Pivoted, inconsistent units (HL vs CAJ/UN), SKUs missing or extra vs `Planificado…`. Format makes it brittle. |

Both must appear in `ETLResult.discarded_files`.

## 1. Joins

| Join | On | Result |
|---|---|---|
| `OEE` + `Tiempo` + `Volumen` + `Mantenimiento` | `OF == WOID` (1:1) | `wo_master.csv` |
| `Cambios` ↪ `wo_master` | `OF == wo_id` (~96 % match; 137 unmatched rows are LIMPIEZA / `PRT…-M`) | `wo_changeovers.csv` |
| `skus` | `drop_duplicates(sku_id)` from `wo_master` | `skus.csv` |

## 2. `start_ts` derivation

Only `end_ts` (`Fecha Fin`) is recorded. Steps:

1. Sort `wo_master` by `(line_id, end_ts)`.
2. Candidate `start_ts = end_ts - total_hours`.
3. If `candidate < prev.end_ts` on the same line, clamp `start_ts = prev.end_ts`.
4. Emit a warning when the clamp adjustment exceeds 10 minutes — indicates
   either an overlap or an outlier `total_hours`.

## 3. Outliers we preserve (do **not** clip)

* `oee > 1.0` — observed up to 1.57. Performance can exceed 1 because the
  theoretical speed is conservatively set. Report P50 / P95 downstream.
* `inefficiency < 0` — over-production / corrections. Keep.
* `total_hours` extremes — max observed 21 065 h ≈ 877 days. Keep the value
  but flag it in `ETLResult.warnings`. The outlier should never end up in
  training tables (see §4 of the per-product docs for filters).

## 4. `Cambios.Frecuencia Total` ambiguity

Magnitude (mean 1.65 h, max 17.5 h) is plausibly hours. Steps:

1. Treat as `empirical_changeover_hours` in `wo_changeovers.csv`.
2. Validate by computing Spearman correlation against the leading
   `unplanned_stop_hours` chunk of the same WO.
3. If `|ρ| < 0.3`, fall back to the theoretical matrix for that
   `(line_id, sku_from, sku_to)` and tag downstream rows
   `is_segment_sum_inconsistent = True`.

## 5. `wo_kind` classification

| Condition | `wo_kind` |
|---|---|
| `wo_id` starts with `PRT` and `sku_id == "LIMPIEZA"` | `cleaning` |
| `wo_id` starts with `PRT` (other SKUs) | `maintenance_or_rerun` |
| Otherwise | `production` |

Only `production` rows feed `node_cost_train`, `edge_cost_train`,
`line_capability`, and the historical `demand` mapper.

## 6. Maintenance double-counting

`Mantenimiento.Tiempo en Espera + Tiempo Intervención` overlaps with
`Tiempo.PNP` and `Tiempo Máquina en paro`. Don't sum naively.

1. For each WO with maintenance calls, audit the sum:
   `maintenance_wait_hours + maintenance_intervention_hours`
   vs `unplanned_stop_hours + idle_hours`.
2. If the difference exceeds 0.5 h, surface a `wo_id` warning. The ETL still
   writes the row, but `incidents.csv` deduplicates by taking the
   `(start_ts, duration_hours)` from the longer source.

## 7. Unit normalisation

`Planificado - producciones…` mixes CAJ (cases) and UN (units). The demand
builder converts:

```
if unit_of_measure == "CAJ":
    units = planned_quantity * skus.units_per_case
else:                                   # UN
    units = planned_quantity
```

Missing `units_per_case` is a warning, not an error — the row is dropped and
listed.

## 8. CF-table string parsing

`Tabla CF Prat` durations are strings:

| String | Hours |
|---|---|
| `"30 min"` | 0.5 |
| `"1 h"` | 1.0 |
| `"1 h 15 min"` | 1.25 |
| `"3 h"` | 3.0 |
| `"8 h"` | 8.0 |
| empty cell | NaN — interpret as "not applicable" for that transition |

Unparseable strings are surfaced in `ETLResult.warnings`.

## 9. Constants we drop

These columns add no signal and are dropped on load:

| File | Constant columns dropped |
|---|---|
| `OEE` | `CENTRO` (always `"PRAT"`), `Columna Blanca`, `Cantidad registros`, `ID Tipo artículo`, `Tipo artículo`, `Retornable`, `ID Retornable`, `Palet` |
| `Tiempo` | `MAQUINA` (always `"LLENAD"`), `Calidad` (always `1`), `Tiempo Operativo Neto`, `Tiempo Operativo Neto2` |
| `Cambios` | `CENTRO`, `Columna Blanca`, duplicated SKU attribute columns (resolved via `skus` join) |

## 10. Renaming policy

* Spanish → English snake_case (full mapping in each per-product doc).
* Hours columns end in `_hours`.
* Counts of cans use `units_*`; volumes use `hectoliters_*`.
* IDs end in `_id`.
* Timestamps end in `_ts`.

## 11. Warnings catalogue

These names appear in `ETLResult.warnings` so consumers know what to expect:

* `start_ts_clamp_large` — `start_ts` adjustment > 10 minutes.
* `total_hours_outlier` — `total_hours` outside `[0.5, 240]`.
* `oee_above_one` — `oee > 1`.
* `inefficiency_negative` — `inefficiency < 0`.
* `cambios_frecuencia_weak_correlation` — `|ρ| < 0.3` for the PNP correlation check.
* `units_per_case_missing` — couldn't normalise a `plan_2026` CAJ row.
* `cf_string_unparseable` — couldn't parse a duration string in `Tabla CF Prat`.
* `maintenance_double_count` — overlap audit failed on a WO.
* `skus_attribute_conflict` — same `sku_id` carries conflicting attribute values across WOs.
* `capability_format_only` — SKU is format-compatible with a line but never ran there historically.
