# `wo_changeovers.csv` — Historical transition table (`sku_from -> sku_to`)

**Status:** MVP · **Produced by:** [`services/etl/`](../../services/etl/) ·
**Consumers:** UI drill-down, diagnostics, future feature engineering ·
**Granularity:** one row per observed consecutive production transition on the same line

This table describes what historically happened between consecutive production
WOs. It is **not** an observed duration table: the historical exports do not
contain actual start/end timestamps. The estimated duration joined here comes
from [`changeover_costs.csv`](./changeover_costs.md), which expands `Tabla CF
Prat` rules to SKU-to-SKU costs.

## Schema

| Column | Type | Description |
|---|---|---|
| `transition_id` | str (PK) | Equals `wo_to_id`, the destination WO after the transition. |
| `line_id` | int (14/17/19) | Line on which the transition occurred. |
| `transition_sequence_order` | int | Destination WO's `line_sequence_order`. |
| `transition_day` | date | Destination WO's `end_day`. Date-only, not a timestamp. |
| `day_of_week` | int (0..6) | Derived from `transition_day`; 0 = Monday. |
| `sku_from_id` | str (FK -> `skus.sku_id`) | Predecessor SKU. |
| `sku_to_id` | str (FK -> `skus.sku_id`) | Successor SKU. |
| `wo_from_id` | str (FK -> `wo_master.wo_id`) | Predecessor WO. |
| `wo_to_id` | str (FK -> `wo_master.wo_id`) | Successor WO. |
| `wo_to_had_changeover` | bool | `wo_master.had_changeover` on the destination WO. |
| `estimated_changeover_hours` | float | Joined from `changeover_costs.total_hours`. This is theoretical CF time, not observed timestamp gap. |
| `changeover_cost_source` | str | Source tag from `changeover_costs`; currently `tabla_cf_prat`. |
| `dominant_component` | str | Segment(s) that determine the max-rule total, from `changeover_costs`. |
| `cambios_frequency_total` | float \| null | Raw `Cambios.Frecuencia Total`, retained only as a diagnostic because mentors said it is not important for the target. |
| `from_container_type`, `to_container_type` | str | SKU formats. |
| `from_brand`, `to_brand` | str | SKU brands. |
| `from_beer`, `to_beer` | str | Beer/recipe IDs. |
| `from_primary_packaging`, `to_primary_packaging` | str \| null | Packaging attributes. |
| `from_secondary_packaging`, `to_secondary_packaging` | str \| null | Packaging attributes. |
| `from_pallet_type`, `to_pallet_type` | str \| null | Pallet attributes. |
| `flag_brand_change` | bool | Was `C. Brand` in `Cambios`. |
| `flag_container_change` | bool | Was `C. Envase`. |
| `flag_cap_change` | bool | Was `C. CAP`. |
| `flag_primary_pack_change` | bool | Was `C. Primario`. |
| `flag_secondary_pack_change` | bool | Was `C. Secundario`. |
| `flag_pallet_change` | bool | Was `C. Palet`. |
| `flag_product_change` | bool | Was `C. Producto`. |
| `flag_volume_change` | bool | Was `C. Volum`. |
| `n_components_changed` | int | Was `Nº de Cambios`. |
| `principal_change_type` | str \| null | Was `C. PRINCIPAL`. |

## Lineage

```
wo_master.csv
  │ sort production WOs by (line_id, line_sequence_order)
  └─► consecutive pairs become historical transitions

skus.csv
  └─► join twice for from/to attributes

changeover_costs.csv
  └─► join on (line_id, sku_from_id, sku_to_id)
      estimated_changeover_hours = total_hours

Cambios 14_17_19_ 2025.xlsx
  └─► join on wo_to_id for flags and diagnostic Frecuencia Total
```

## Cleaning Rules Applied

* Keep only transitions where both WOs have `wo_kind == "production"`.
* Sequence by `line_sequence_order`, not by inferred timestamps.
* Do not compute `changeover_hours` from timestamp gaps.
* Aggregate duplicate `Cambios.OF` rows by destination WO:
  * flags use logical OR / positive-as-true
  * `n_components_changed` uses max
  * `principal_change_type` keeps distinct labels
  * `cambios_frequency_total` sums non-null duplicate values
* Every row must find exactly one matching `(line_id, sku_from_id, sku_to_id)`
  in `changeover_costs.csv`.

## Used By

* UI drill-down: explains what changed historically and what the theoretical
  changeover time would be.
* Future diagnostics: compare historical OEE/downtime around expensive
  theoretical transitions.
* Future ML features, if a true observed duration source is provided later.
