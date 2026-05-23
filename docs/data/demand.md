# `demand.csv` — Window-aggregated demand

**Status:** MVP · **Produced by:** [`services/etl/`](../../services/etl/) (DemandBuilder) ·
**Consumer:** the optimiser (sole input that varies per run) ·
**Granularity:** one row per `(sku_id, window)` pair

The **only** input the optimiser ever consumes for demand. Every source —
historical 2025, JDA plan 2026, what-if from the UI — is re-aggregated to this
shape. Bucket size is governed by [`WindowConfig`](../../packages/contracts/module/schemas.py)
(default 7-day Monday-anchored).

## Schema

| Column | Type | Description |
|---|---|---|
| `window_id` | str (PK part) | Human-readable identifier, e.g. `2025-W18-7d` for ISO week 18 with a 7-day bucket, or `2025-08-04_7d` when anchored to a fixed start. |
| `window_start` | date | First day included in the bucket (inclusive). |
| `window_end` | date | Last day included (inclusive). |
| `sku_id` | str (PK part, FK → `skus.sku_id`) | SKU to produce. The synthetic `LIMPIEZA` SKU is excluded. |
| `units_demanded` | int (>= 0) | Total cans to produce in this window. Sum across the source rows. |
| `source` | str (`historico_2025` / `plan_2026` / `whatif_usuario`) | Provenance of the bucket. |
| `priority` | int (1..5) | Default 3. `5` means the SKU cannot be dropped under disjunction. Was `prioridad`. |

What the optimiser **never sees** here: `line_id`, day, turn, hour. Those are
decisions, not demand.

## Lineage

Three mappers, one shape:

```
wo_master.csv (kind == "production")
   │
   └──► drop LIMPIEZA, bucket on end_day via WindowConfig, sum units_produced
        ──► demand.csv (source == "historico_2025")

Planificado - producciones 14 - 17 - 19.XLSX
   │
   └──► normalise CAJ/UN with skus.units_per_case, bucket on Fecha ini.,
        drop tren/hora_ini/turno
        ──► demand.csv (source == "plan_2026")

UI form
   │
   └──► straight passthrough into DemandBucket
        ──► demand.csv (source == "whatif_usuario")
```

## Cleaning rules applied

* Drop `sku_id == "LIMPIEZA"` and `wo_kind != "production"` from the historical
  source — those are not demand.
* For `plan_2026`: if `unit_of_measure == "CAJ"`, multiply
  `planned_quantity * skus.units_per_case`. Warn on missing
  `units_per_case`.
* Window assignment uses `WindowConfig.anchor`:
  * `"monday"`: ISO-week boundaries. Mid-week WOs fall into the week that
    contains their reference date.
  * `"fixed_start"`: roll forward from `start_date` in `days`-sized chunks.
* Multiple SKUs in the same window → one row per `(sku_id, window)` with
  summed `units_demanded`.

## How to change the window

Change `WindowConfig.days` (and optionally `anchor`) in
`data/clean/optimizer_hyperparams.yaml` or in code. Both the demand bucket
size *and* the optimiser planning horizon track this single knob.

## Used by

* The optimiser, as the only varying input across runs.
