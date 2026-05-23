# `incidents.csv` — Deterministic replay log

**Status:** M2 (deferred — not optimiser MVP) ·
**Produced by:** [`services/etl/`](../../services/etl/) ·
**Consumers:** [`services/simulator/`](../../services/simulator/) ·
**Granularity:** one row per replayable incident anchored to a line and an
estimated or externally supplied timestamp

Used only by the simulator. Lets us compare `S_real` and `S_opt` under the
**same** unplanned downtime so neither side wins by luck.

## Schema

| Column | Type | Description |
|---|---|---|
| `incident_id` | str (PK) | Stable identifier `incident_<line>_<yyyymmddTHHMMSS>`. |
| `line_id` | int (14/17/19) | Line affected. |
| `start_ts` | timestamp | When the incident began. Historical exports do not provide this directly; M2 must derive an explicitly estimated timestamp or use an external event source. |
| `duration_hours` | float | How long it disrupted production. |
| `cause` | str | One of `breakdown` / `unplanned_maintenance` / `downstream_block` / `upstream_starve` / `other`. |
| `source_wo_id` | str \| null | The WO that surfaced the incident, when traceable. |

## Lineage

```
wo_master.csv  ──► extract rows where:
                       maintenance_calls > 0           → cause = "unplanned_maintenance"
                       downstream_block_hours > 0.5    → cause = "downstream_block"
                       upstream_starve_hours > 0.5     → cause = "upstream_starve"
                       unplanned_stop_hours > 1.0      → cause = "breakdown" (if not already)
                   one or more rows per WO, with estimated/external start_ts
                                 │
                                 ▼
                          incidents.csv
```

## Anchoring philosophy

Incidents should be anchored to `(line_id, start_ts)` — the equipment and
moment, **not** the SKU. Because the current historical files have only
`end_day`, M2 must make any timestamp estimation explicit and keep it out of
the canonical `wo_master` facts.

Exceptions (SKU-attributable jams typical of a specific format) are allowed
and documented per-row in `source_wo_id` notes.

## Cleaning rules applied

* Merge overlapping events of the same cause within the same WO.
* Drop very small events (`duration_hours < 0.25`).
* Beware double-counting: `maintenance_wait_hours + maintenance_intervention_hours`
  overlap with `unplanned_stop_hours` and `downtime_hours` in `wo_master`. The
  ETL audits a sample of WOs and emits a warning if the overlap looks
  inconsistent — see [`cleaning_rules.md`](./cleaning_rules.md) §6.

## Used by

* **Simulator** — replayed deterministically when evaluating any `Sequence`.
