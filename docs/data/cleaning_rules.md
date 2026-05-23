# Cleaning Rules (secondary reference)

> Consolidated data-cleaning recipe behind every product in
> [`docs/data/overview.md`](./overview.md). Per-product docs are the primary
> consumer reference.

## 0. Files Discarded Entirely

| File | Reason |
|---|---|
| `data - 2026-05-18T181640.542.xlsx` | Verified duplicate of `OEE 14_17_19_ 2025.xlsx`. |
| `Diario Hl_Planif.xlsx` | Pivoted planning export with inconsistent units and brittle layout. |

Both must appear in `ETLResult.discarded_files`.

## 1. Joins

| Join | On | Result |
|---|---|---|
| `OEE` + `Tiempo` + `Volumen` + `Mantenimiento` | `OF == WOID` | `wo_master.csv` |
| `wo_master` production rows | `end_day` bucket + `sku_id` | `demand.csv` |
| OEE SKU attributes | `drop_duplicates(sku_id)` | `skus.csv` |
| `wo_master` + `skus` | `(sku_id, line_id)` medians + format rules | `line_capability.csv` |
| `Tabla CF Prat` + `skus` | SKU attributes and line/container rules | `changeover_costs.csv` |
| `wo_master` + `skus` + `Cambios` + `changeover_costs` | consecutive production WOs, `wo_to_id`, `(line, sku_from, sku_to)` | `wo_changeovers.csv` |

## 2. Date and Sequence Policy

Historical `Fecha Fin` values are date-only. Excel cells have `mm-dd-yy`
format and no hidden time-of-day. Therefore:

1. `wo_master.end_day` is the normalized `Fecha Fin` date.
2. `wo_master.source_row_order` preserves raw OEE row order.
3. `wo_master.line_sequence_order` sorts by `(line_id, end_day, source_row_order, wo_id)`.
4. `wo_changeovers` uses consecutive production rows by `line_sequence_order`.
5. Do not derive canonical `start_ts` or timestamp-gap `changeover_hours`.

If a Gantt needs approximate times later, add explicitly named estimated fields
outside the canonical historical products.

## 3. Changeover Time Policy

Mentor guidance: `Cambios.Frecuencia Total` is not important for the target.
`Mantenimiento` is also not changeover time; it is WO-level maintenance burden.

Therefore:

* `changeover_costs.total_hours` is the authoritative transition estimate.
* It is derived from `Tabla CF Prat`, expanded to SKU-to-SKU transitions.
* `wo_changeovers.estimated_changeover_hours` is a join from `changeover_costs`.
* `Cambios` contributes flags/features only.
* `Cambios.Frecuencia Total` is retained as `cambios_frequency_total` for
  diagnostics and should not be used as an authoritative target.

## 4. Max-Component Changeover Rule

When multiple components change in one SKU-to-SKU transition, total time is the
maximum component duration, not the sum:

```
total_hours = max(segment_*_hours)
```

The component set is:

| Segment | Source |
|---|---|
| `segment_container_hours` | `LATA_BARRIL` format pair |
| `segment_beer_hours` | `Tiempos adicionales` / `Cambio cerveza` |
| `segment_cap_or_label_hours` | `Tiempos adicionales` / `Cambio lata` when beer does not change |
| `segment_primary_pack_hours` | `LATA_BARRIL` / `Cambio Packaging` |
| `segment_secondary_pack_hours` | `LATA_BARRIL` / `Cambio a Bandeja` |
| `segment_pallet_hours` | `LATA_BARRIL` / `Cambio Paletizado` |

`Cambio cerveza` suppresses the cap/label/lata segment because the CF note says
those changes are included when beer changes.

## 5. `wo_kind` Classification

| Condition | `wo_kind` |
|---|---|
| `wo_id` starts with `PRT` and `sku_id == "LIMPIEZA"` | `cleaning` |
| `wo_id` starts with `PRT` and other SKU | `maintenance_or_rerun` |
| otherwise | `production` |

Only `production` rows feed historical transition products.

## 6. Maintenance Interpretation

`Mantenimiento` has a row for every WO, but non-null maintenance calls/times are
sparse and also appear on WOs where `OEE.Cambios == NO`. Treat these columns as
maintenance/incident context:

* `maintenance_calls`
* `maintenance_wait_hours`
* `maintenance_intervention_hours`

Do not use them as changeover durations.

## 7. Outliers We Preserve

* `oee > 1.0` — performance can exceed 1 because theoretical speed is
  conservative.
* `inefficiency < 0` — over-production / corrections.
* `total_hours` extremes — preserved and warned, not clipped.

Downstream training tables should filter or robustly handle these, but the
master table keeps raw truth.

## 8. Unit Normalisation

`Planificado - producciones…` mixes CAJ and UN. The demand builder converts:

```
if unit_of_measure == "CAJ":
    units = planned_quantity * skus.units_per_case
else:
    units = planned_quantity
```

Missing `units_per_case` is a warning and the row is dropped.

## 9. CF-Table String Parsing

| String | Hours |
|---|---|
| `"30 min"` | 0.5 |
| `"1 h"` | 1.0 |
| `"1 h 15 min"` | 1.25 |
| `"1,5 h"` | 1.5 |
| `"3 h"` | 3.0 |
| `"8 h"` | 8.0 |

Unparseable strings are surfaced in `ETLResult.warnings`.

## 10. Constants We Drop

| File | Constant columns dropped |
|---|---|
| `OEE` | `CENTRO`, `Columna Blanca`, `Cantidad registros`, `ID Tipo artículo`, `Tipo artículo`, `Retornable`, `ID Retornable`, `Palet` |
| `Tiempo` | `MAQUINA`, `Calidad`, `Tiempo Operativo Neto`, `Tiempo Operativo Neto2` |
| `Cambios` | `CENTRO`, `Columna Blanca`, duplicated SKU attribute columns |

## 11. Warnings Catalogue

Expected warning names include:

* `total_hours_outlier`
* `oee_above_one`
* `inefficiency_negative`
* `maintenance_double_count`
* `demand_invalid_end_day`
* `demand_invalid_units`
* `skus_attribute_conflict`
* `capability_format_only`
* `capability_metric_fallback`
* `capability_history_violates_format`
* `changeover_costs_missing_container_type`
* `changeover_costs_missing_format_pair`
* `changeover_costs_missing_component`
* `changeover_costs_missing_additional_time`
* `wo_changeovers_missing_changeover_cost`
* `wo_changeovers_missing_cambios`
* `cambios_duplicate_wo_id`
* `cambios_flag_non_binary`
* `units_per_case_missing`
* `cf_string_unparseable`
