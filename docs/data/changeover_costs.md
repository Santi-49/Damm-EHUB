# `changeover_costs.csv` — SKU-to-SKU theoretical transition times

**Status:** MVP · **Produced by:** [`services/etl/`](../../services/etl/) ·
**Consumers:** optimiser edge weights, `wo_changeovers.csv` estimated-time join ·
**Granularity:** one row per allowed `(line_id, sku_from_id, sku_to_id)` transition

This is the canonical SKU-to-SKU transition-time data product. It expands the
predefined `Tabla CF Prat 2026_14_17_19.xlsx` rules through `skus.csv`.

`Tabla CF Prat` does not list SKU IDs directly. It gives theoretical durations
by line, container format, packaging operation and additional change events.
The ETL derives SKU-pair costs by comparing SKU attributes.

## Schema

| Column | Type | Description |
|---|---|---|
| `line_id` | int (PK part, 14/17/19) | Line on which the transition takes place. |
| `sku_from_id` | str (PK part) | Predecessor SKU. |
| `sku_to_id` | str (PK part) | Successor SKU. |
| `from_container_type` | str | Predecessor format (`1/2`, `1/3`, `2/5`). |
| `to_container_type` | str | Successor format. |
| `total_hours` | float | Estimated transition time. Equals the maximum segment duration on the row. |
| `segment_container_hours` | float | Format/container change time from `LATA_BARRIL`. |
| `segment_beer_hours` | float | `Cambio cerveza` time from `Tiempos adicionales`. |
| `segment_cap_or_label_hours` | float | `Cambio lata` / etiqueta / tapon time when beer does not change. |
| `segment_primary_pack_hours` | float | `Cambio Packaging` duration. |
| `segment_secondary_pack_hours` | float | `Cambio a Bandeja` duration. |
| `segment_pallet_hours` | float | `Cambio Paletizado` duration. |
| `dominant_component` | str | Segment(s) equal to `total_hours`; semicolon-separated on ties. |
| `source` | str | Currently always `tabla_cf_prat`. |

## Max-Component Rule

If multiple components need changing, the total cost is the **maximum** of the
component times, not the sum:

```
total_hours = max(
  segment_container_hours,
  segment_beer_hours,
  segment_cap_or_label_hours,
  segment_primary_pack_hours,
  segment_secondary_pack_hours,
  segment_pallet_hours,
)
```

This encodes the operational assumption that parallel preparation is possible
and the slowest required component dominates the transition.

## Lineage

```
Tabla CF Prat 2026_14_17_19.xlsx
  ├─ sheet LATA_BARRIL
  │    format pairs: 1/3 <-> 1/2 <-> 2/5
  │    component rows: Cambio Packaging, Cambio a Bandeja, Cambio Paletizado
  └─ sheet Tiempos adicionales
       Cambio cerveza, Cambio lata, CIP, esterilizacion, limpieza, mantenimiento

skus.csv
  └─ compare from/to SKU attributes
       container_type, beer, material/container, primary/secondary packaging, pallet

expanded to all allowed line/SKU pairs
  └─► changeover_costs.csv
```

## Coverage Rules

Allowed line/container pairs:

| Line | Allowed `container_type` |
|---|---|
| L14 | `1/2`, `1/3` |
| L17 | `1/3` |
| L19 | `1/2`, `1/3`, `2/5` |

The ETL includes same-SKU rows with `total_hours = 0.0` so historical repeated
SKU transitions can still join cleanly.

## Cleaning Rules Applied

* Parse strings like `"3 h"`, `"30 min"`, `"1 h 15 min"`, and `"1,5 h"` to
  decimal hours.
* `Cambio cerveza` suppresses `Cambio lata` / etiqueta / tapon because the CF
  note says those changes are included when beer changes.
* Missing component durations produce warnings. Current raw coverage validates
  with no missing historical cost joins.
* Validate that `total_hours == max(segment_*_hours)` for every row.

## Used By

* Optimiser: `total_hours` is the edge weight in the SKU routing graph.
* [`wo_changeovers.csv`](./wo_changeovers.md): joins the theoretical estimated
  time onto historical transitions for explanation and diagnostics.
