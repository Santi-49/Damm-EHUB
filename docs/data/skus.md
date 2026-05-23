# `skus.csv` — SKU catalogue

**Status:** MVP · **Produced by:** [`services/etl/`](../../services/etl/) ·
**Consumers:** ML feature joins, UI lookups, all `(sku_id, …)` consumers ·
**Granularity:** one row per SKU

Deduplicated attributes table. The synthetic `LIMPIEZA` SKU is excluded.

## Schema

| Column | Type | Description |
|---|---|---|
| `sku_id` | str (PK) | SKU identifier. Was `SKU`. |
| `container_type` | str (`1/2` / `1/3` / `2/5`) | Format: 50 cl / 33 cl / 44 cl. Was `Tipo Envase`. **Drives line capability.** |
| `brand` | str | Was `Marca`. |
| `supra_brand` | str | Was `Supramarca`. |
| `family` | str | Was `Familia`. |
| `beer` | str | Beer recipe — drives `flag_brand_change` semantics. Was `Cerveza`. |
| `material_id` | str | Was `ID Material Precio`. |
| `material_label` | str | Was `Mat. Precio`. |
| `container` | str | Was `Envase`. |
| `primary_packaging` | str \| null | Was `Packaging Primario`. |
| `secondary_packaging` | str \| null | Was `Packaging Secundario`. |
| `pallet_type` | str \| null | Was `Tipo Palet`. |
| `units_per_primary_pack` | float \| null | Was `Unidades packaging primario`. |
| `units_per_secondary_pack` | float \| null | Was `Unidades packaging secundario`. |
| `units_per_case` | float \| null | Conversion from `CAJ` to `UN`. Was `Unidad/caja`. |

## Lineage

```
wo_master.csv ──► drop_duplicates(sku_id) ──► skus.csv
```

Picks one canonical row per `sku_id`. Conflicts within a SKU (rare) are
resolved by taking the most-recent WO's attribute set; conflicts must be
surfaced as warnings.

## Cleaning rules applied

* Filter out `sku_id == "LIMPIEZA"`.
* For conflicting attribute values within a `sku_id`, take the value from the
  WO with the latest `end_ts`. Emit a warning per conflicting column.
* Empty / `"-"` / `"N/A"` strings normalised to `null`.

## Used by

* Every downstream consumer that needs SKU attributes for joins or feature engineering.
* The UI drill-down (brand, container, pack — human-readable labels).
