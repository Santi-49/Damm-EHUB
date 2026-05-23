# `line_calendar.csv` — Forced events per line

**Status:** MVP · **Produced by:** [`services/etl/`](../../services/etl/) ·
**Consumers:** optimiser (forced nodes with time windows), simulator (subtract from productive hours) ·
**Granularity:** one row per recurring rule OR one row per one-off event

The plant has mandatory non-productive events that the optimiser must respect:
**Friday 8-hour cleaning** and **Monday biweekly 8-hour maintenance** on every
line, plus any one-off breakdown or maintenance that the user injects via the
UI what-if flow.

## Schema

| Column | Type | Description |
|---|---|---|
| `event_id` | str (PK) | Stable identifier. Recurring rules use slugs (`cleaning_friday_l14`); one-off events use `breakdown_<line>_<yyyymmddTHHMM>`. |
| `line_id` | int (14 / 17 / 19) | Line affected. |
| `event_type` | str (`cleaning` / `maintenance` / `breakdown`) | What kind of event. |
| `duration_hours` | float | How long the event blocks production. Cleaning and maintenance default to 8.0; breakdowns carry the injected value. |
| `recurrence` | str \| null | For recurring events: e.g. `weekly:friday`, `biweekly:monday`. **Null for one-off events.** |
| `start_ts` | timestamp \| null | For one-off events: when it starts. **Null for recurring events.** |

Exactly one of `recurrence` / `start_ts` is set per row.

## Lineage

```
Tabla CF Prat 2026_14_17_19.xlsx (sheet "Tiempos adicionales")
   │
   └──► parse cleaning + maintenance frequencies and durations per line
        ──► recurring rows in line_calendar.csv

UI what-if form
   │
   └──► append one-off rows when user injects a breakdown / urgent maintenance
        ──► one-off rows in line_calendar.csv (in-memory at runtime)
```

The ETL emits the **recurring** rows. The optimiser/UI append **one-off** rows
at runtime in the in-memory `OptimizerInput.calendar` tuple. The CSV is only
the persistent recurring baseline.

## Cleaning rules applied

* Parse human-readable duration strings from the CF sheet (`"8 h"`, `"30 min"`,
  `"1 h 15 min"`) into decimal hours.
* Normalise the frequency text to the slugs above. Anything matching
  `"semanal"` + `"viernes"` → `weekly:friday`; `"quincenal"` + `"lunes"` →
  `biweekly:monday`. Unrecognised patterns are surfaced in
  `ETLResult.warnings`.
* Only emit rows that actually constrain production — pure-information rows
  in the CF sheet (e.g. arranque / final times) live in
  `changeover_costs.csv` as part of the changeover hour breakdown.

## Used by

* **Optimiser** — turns each row into a forced visit on the VRP route with a
  time window. Recurring rules are expanded to concrete events covering the
  planning window before being handed to the solver.
* **Simulator** — subtracts the event's `duration_hours` from `total_hours` and
  attributes it to `cleaning_hours` / `maintenance_hours`.
