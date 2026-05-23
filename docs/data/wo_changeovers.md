# `wo_changeovers.csv` — Per-WO changeover-flag observations (raw)

**Status:** MVP · **Produced by:** [`services/etl/`](../../services/etl/) ·
**Consumers:** [`edge_cost_train.csv`](./edge_cost_train.md) builder, UI drill-down ·
**Granularity:** one row per WO that *followed* a changeover (137 WOs without a row correspond to the first WO on a line or to cleaning/maintenance)

The cleaned version of `Cambios 14_17_19_ 2025.xlsx`. Tracks which components
changed when a WO began.

## Schema

| Column | Type | Description |
|---|---|---|
| `wo_id` | str (PK, FK → `wo_master.wo_id`) | The WO at the *destination* of the changeover. Was `OF`. |
| `n_components_changed` | int | How many components flipped. Was `Nº de Cambios`. |
| `empirical_changeover_hours` | float | Hours observed for this changeover (ambiguous source — see [`cleaning_rules.md`](./cleaning_rules.md) §4). Was `Frecuencia Total`. |
| `principal_change_type` | str | Driving component. Was `C. PRINCIPAL`. Values: `Contenido`, `Marca`, `Pack. Primario`, `Pack. Secundario`, `Palet`, `Referencia`, `Tapa/Tapón`, `Volumen Envase`. |
| `flag_brand_change` | bool | Was `C. Brand`. |
| `flag_cap_change` | bool | Was `C. CAP`. |
| `flag_container_change` | bool | Was `C. Envase`. |
| `flag_pallet_change` | bool | Was `C. Palet`. |
| `flag_primary_pack_change` | bool | Was `C. Primario`. |
| `flag_secondary_pack_change` | bool | Was `C. Secundario`. |
| `flag_product_change` | bool | Was `C. Producto`. |
| `flag_volume_change` | bool | Was `C. Volum`. |

## Lineage

```
Cambios 14_17_19_ 2025.xlsx ──► drop constant cols ──► wo_changeovers.csv
                                   join to wo_master on wo_id for line_id and sku_id
```

`Cambios` does not carry `TREN` — joining to `wo_master` is the only way to
know which line the changeover happened on.

## Cleaning rules applied

* Cast `0`/`1` to boolean for all `flag_*` columns.
* `empirical_changeover_hours` ambiguity: the column is labelled
  `Frecuencia Total` but its magnitude (mean 1.65 h, max 17.5 h) is consistent
  with hours. The ETL emits a warning and validates correlation with
  `unplanned_stop_hours` from `wo_master`. If correlation is weak, downstream
  consumers must fall back to the theoretical matrix.
* Drop `CENTRO`, `Columna Blanca`, redundant SKU attribute columns (these
  come from the join to `skus`).

## Used by

* [`edge_cost_train.csv`](./edge_cost_train.md) — feature columns for the ML
  model are the `flag_*` indicators plus the SKU attributes joined in.
* UI drill-down — for the "what changed at this transition" view.
