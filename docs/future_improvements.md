# Future Improvements

Items intentionally deferred from the current hackathon MVP. Each entry:
**Motivation**, **What changes**, **Touch points**. Append as new items surface.

---

## 1. Calendar / temporal features for the node-cost model

**Motivation.** Ramp-up and steady-state speed plausibly drift with day-of-week,
hours-since-last-cleaning, week-of-year (seasonal product mix), and shift
boundaries. The current MVP node-cost model only sees
`(sku, line, units, sku_attrs)` — none of the temporal context that historically
correlates with effective speed.

**What changes.** Add to the training feature pipeline:

- `day_of_week`, `is_weekend`, `week_of_year`, `month` derived from
  `wo_master.end_day`.
- `hours_since_last_cleaning` from [line_calendar.csv](../data/clean/line_calendar.csv).
- `cumulative_run_hours_today` — line warmth proxy (sum of `productive_hours`
  for earlier WOs on the same line/day).
- Optional: plant holiday and one-off calendar flags.

**Touch points.**

- ETL aggregation step in [services/etl/](../services/etl/) must preserve
  `end_day` (and ideally start/end of the bounding WOs) for each aggregated
  consecutive-same-SKU run.
- Training pipeline in [services/changeover_ml/](../services/changeover_ml/).
- Update the feature list in [docs/data/node_cost_train.md](data/node_cost_train.md).

---

## 2. Margin-aware demand discard in the graph optimiser

**Motivation.** When the week is infeasible (breakdown, urgent demand,
capacity-short), today's MVP drops demand uniformly via the OR-Tools VRP
disjunction mechanism. In practice low-margin SKUs should yield first so
revenue is preserved. The current setup uses a flat penalty per droppable
node, which makes the dropout decision economically blind.

**What changes.** Set the disjunction penalty per droppable node to
`margin_eur_per_unit × units_chunk` instead of a flat constant. The same
objective then handles both the feasible and infeasible regimes — no emergency
branch. The storytelling line "we sacrifice the cheapest beer first" lands
naturally in the demo. See Architecture D in
[docs/linewise/implementacion.md](linewise/implementacion.md) §3.D and §3 of
[docs/challenge/VISION.md](challenge/VISION.md).

**Touch points.**

- New input: `margin_eur_per_unit` per SKU. Source: ask Damm or estimate from
  public retail price × known yield.
- Extend `GraphOptimizerContract` in
  [packages/contracts/module/interface.py](../packages/contracts/module/interface.py)
  with an optional margin map.
- Wire the penalty into the OR-Tools `AddDisjunction` calls.
- UI: surface "€ lost from dropped SKUs" in the post-replan summary.

---

## 3. Predictive maintenance during changeovers

**Motivation.** Beyond optimising the weekly sequence, the historical dataset
(`Mantenimiento`, `Tiempo` PNP/IDLE breakdowns, `incident_log`) carries the
signal to anticipate **when a machine is about to fail**. Unplanned breakdowns
are the single largest OEE killer in the demo week and the operational scenario
the planner cares about most. Today the simulator only *replays* incidents —
it does not *anticipate* them.

**What changes.** Train a per-line (and ideally per-component) failure-risk
model that outputs, for each upcoming time window, a probability of unplanned
downtime. When `P(failure) ≥ τ` (calibrated threshold per line), the optimiser
treats the next **scheduled changeover** as an inspection / preventive-repair
slot: the changeover edge cost is inflated by an estimated inspection time,
but the expected breakdown cost downstream drops out of the makespan. The
trade-off — small certain cost now vs. large probable cost later — becomes
explicit in the objective.

This pairs naturally with Architecture D: the changeover is already a
discrete, well-bounded "edge" in the graph, so we only extend the existing
edge-cost computation with one extra term `E[downtime_avoided] − inspection_time`.

**Touch points.**

- New model in [services/changeover_ml/](../services/changeover_ml/) (or a
  sibling `services/failure_ml/`) trained on
  [data/clean/](../data/clean/) — cumulative run hours, recent incident
  density, hours since last maintenance, vibration/temperature proxies if
  any survive the ETL.
- Walk-forward validation discipline mirroring the changeover predictor; report
  precision/recall at the chosen threshold so planners can tune τ.
- Extend `SimulatorContract` to expose the realised vs. predicted incidents per
  WO, so we can show "this preventive stop avoided an N-hour breakdown".
- Optimiser: extend the edge-cost function with a `preventive_inspection`
  flag and an expected-cost term. Disjunctions remain unchanged.
- UI: badge changeovers chosen for inspection (e.g. wrench icon) and surface
  the model's confidence + expected downtime avoided in the drill-down.
- Demo storytelling: "we don't just replan around incidents — we schedule the
  intervention before the incident happens, using the changeover slot we were
  going to pay for anyway."
