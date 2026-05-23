# `wo_changeovers.csv` — Transition master table (`sku_from → sku_to`)

**Status:** MVP · **Produced by:** [`services/etl/`](../../services/etl/) ·
**Consumers:** [`services/changeover_ml/`](../../services/changeover_ml/) (training), UI drill-down ·
**Granularity:** one row per observed `sku_from → sku_to` transition on the same line

The canonical transition table. Each row is the gap between two consecutive
production WOs on the same line: WO[i] ends → WO[i+1] begins. Row order in
`wo_master` (sorted by `line_id, start_ts`) defines the transitions —
`sku_from_id` = WO[i].sku_id, `sku_to_id` = WO[i+1].sku_id.

**This is the sole training input for the changeover ML model.**
Only real observations are included — no theoretical values from `changeover_costs.csv`.

## Schema

| Column | Type | Description |
|---|---|---|
| `transition_id` | str (PK) | Equals `wo_to_id` — the WO that began after the changeover. |
| `line_id` | int (14/17/19) | Line on which the transition occurred. |
| `sku_from_id` | str (FK → `skus.sku_id`) | SKU of WO[i] — the predecessor run. |
| `sku_to_id` | str (FK → `skus.sku_id`) | SKU of WO[i+1] — the successor run. |
| `wo_from_id` | str (FK → `wo_master.wo_id`) | Predecessor WO. |
| `wo_to_id` | str (FK → `wo_master.wo_id`) | Successor WO. |
| `transition_ts` | timestamp | `wo_to.start_ts` — when the changeover ended and production resumed. |
| `changeover_hours` | float | **Primary target.** `wo_to.start_ts − wo_from.end_ts`. Pure gap from timestamps. |
| `cambios_hours` | float \| null | Cross-validation only. `Frecuencia Total` from `Cambios` xlsx — ambiguous magnitude, see note. |
| **Features — SKU attributes** ↓ | | Joined from `skus` for each side. |
| `from_container_type` | str | Container format of the predecessor SKU. |
| `to_container_type` | str | Container format of the successor SKU. |
| `from_brand` | str | |
| `to_brand` | str | |
| `from_beer` | str | |
| `to_beer` | str | |
| `from_primary_packaging` | str | |
| `to_primary_packaging` | str | |
| `from_secondary_packaging` | str | |
| `to_secondary_packaging` | str | |
| `from_pallet_type` | str | |
| `to_pallet_type` | str | |
| **Features — change flags** ↓ | | From `Cambios 14_17_19_ 2025.xlsx`. |
| `flag_brand_change` | bool | Was `C. Brand`. |
| `flag_container_change` | bool | Was `C. Envase`. |
| `flag_cap_change` | bool | Was `C. CAP`. |
| `flag_primary_pack_change` | bool | Was `C. Primario`. |
| `flag_secondary_pack_change` | bool | Was `C. Secundario`. |
| `flag_pallet_change` | bool | Was `C. Palet`. |
| `flag_product_change` | bool | Was `C. Producto`. |
| `flag_volume_change` | bool | Was `C. Volum`. |
| `n_components_changed` | int | Was `Nº de Cambios`. |
| `principal_change_type` | str | Was `C. PRINCIPAL`. Driving component label. |
| **Features — context** ↓ | | Derived from `transition_ts`. |
| `day_of_week` | int (0..6) | 0 = Monday. |
| `hour_of_day` | int (0..23) | Hour at which the changeover began. |

## Target note — `changeover_hours` vs `cambios_hours`

`changeover_hours` is authoritative: it comes directly from the gap between
consecutive WO timestamps in `wo_master` — no interpretation required.

`cambios_hours` (`Frecuencia Total` from the Cambios sheet) is kept for
cross-validation only. Its magnitude is hours-compatible (mean ≈ 1.65 h,
max ≈ 17.5 h) but the column label is ambiguous. The ETL emits a warning if the
two columns diverge by more than 0.5 h on more than 5 % of rows.

The ML model trains on `changeover_hours`. `cambios_hours` is never used as a target.

## Lineage

```
wo_master.csv  (sorted by line_id, start_ts)
   │
   └── for each consecutive pair (WO[i], WO[i+1]) on the same line:
       │   sku_from_id  = WO[i].sku_id
       │   sku_to_id    = WO[i+1].sku_id
       │   changeover_hours = WO[i+1].start_ts - WO[i].end_ts
       │
skus.csv  ──► join twice (sku_from_id and sku_to_id) for attribute columns
       │
Cambios 14_17_19_ 2025.xlsx  ──► join on wo_to_id for flag_* and cambios_hours
       │
       ▼
   wo_changeovers.csv
```

## Cleaning rules applied

* Keep only transitions where both WOs have `wo_kind == "production"`.
* Drop rows where `changeover_hours < 0` (clock drift / data error) or
  `changeover_hours > 24` (likely a hidden maintenance event, not a changeover).
* Cast `0`/`1` to boolean for all `flag_*` columns.
* Drop `CENTRO`, `Columna Blanca`, and any duplicate SKU attribute columns already
  covered by the join from `skus`.

## Used by

* **[`services/changeover_ml/`](../../services/changeover_ml/)** — training input.
  The model predicts `changeover_hours` (and optionally a segmented breakdown)
  from the feature columns above.
* **UI drill-down** — "what changed at this transition" view uses the `flag_*`
  columns and `principal_change_type`.
