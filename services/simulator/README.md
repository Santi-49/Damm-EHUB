# `services/simulator/` — Deterministic OEE simulator

> Owner: Person 1 · Contract: [`SimulatorContract`](../../packages/contracts/module/simulator.py) · Status: skeleton

## What this service does, in plain words

Given any production sequence — historical, optimiser-proposed, or
hand-crafted — and the same calendar + incident log, compute **OEE, hours
productive, hours lost in changeovers / cleaning / maintenance / incidents,
coverage, and makespan** per line and globally.

Two properties make it valuable:

1. **Deterministic**: identical inputs → identical outputs. No sampling.
   Same incidents replay on `S_real` and `S_opt`, so the comparison is a
   fair fight.
2. **Historically faithful**: when fed `S_real` (the actual 2025 sequence),
   the reported per-line OEE must reproduce observed historical OEE within
   5 %. This is the validation gate before the simulator is trusted to
   score `S_opt`.

## Why a separate service

The optimiser predicts only changeover times. **It does not predict OEE.**
OEE is computed here, after the fact. This decoupling has three benefits:

- Bounded ML target (changeover hours) instead of composite KPI prediction.
- No risk of divergence between "predicted OEE used to choose a route" and
  "reported OEE displayed to the user."
- Reusable across all four architectures (A/B/C/D) and across post-mortem /
  live demo / what-if modes.

## Contract recap in plain words

> Take a `Sequence` (slots with `line_id`, `sku_id`, `start_ts`, `end_ts`,
> `units_planned`), the [`line_capability`](../../docs/data/line_capability.md)
> table, the [`line_calendar`](../../docs/data/line_calendar.md), and the
> [`incidents`](../../docs/data/incidents.md) log. For each slot, in
> chronological order per line: apply the changeover before, then production,
> then intersect with incidents in that `(line_id, window)`, then subtract
> calendar events. Compute per-slot OEE and aggregate per line and globally.
> Return a `SimulationReport`.

## Incident replay (the fair-fight property)

`incidents.csv` rows are anchored to `(line_id, start_ts)` — the equipment
and moment, **not the SKU**. A breakdown on L17 at 10:00 happened
independently of which SKU was on the line. If `S_opt` places another SKU
there, it suffers the same downtime. Physically and operationally correct.

Exception: incidents *clearly attributable to a SKU* (recurring jams of a
specific format) may be anchored to `(sku_id, line_id)`. Document each
exception in the row.

## Inputs

- `Sequence` from the optimiser (or built from history for `S_real`).
- [`line_capability.csv`](../../docs/data/line_capability.md) — `median_speed_uds_per_hour` per `(sku_id, line_id)`.
- [`line_calendar.csv`](../../docs/data/line_calendar.md) — cleaning + maintenance windows.
- [`incidents.csv`](../../docs/data/incidents.md) — incidents to replay.

## Output

`SimulationReport` (see [`schemas.py`](../../packages/contracts/module/schemas.py)):

- `per_line[LineId] → LineMetrics`: OEE, productive / changeover /
  cleaning / maintenance / incident / low-speed hours, coverage, makespan.
- Global OEE weighted by hours, total productive / changeover hours, global
  coverage, makespan = `max(per_line.makespan_hours)`.
- `unproduced_units[sku_id] → int`: SKUs the optimiser had to drop.

## Definition of done

- [ ] `evaluate_sequence(S_real, …)` reproduces 2025 historical OEE per line within 5 %.
- [ ] `evaluate_sequence(S_opt, …)` runs in < 100 ms on a one-week horizon so the optimiser can use it as a fitness function.
- [ ] `detect_infeasibility(S, calendar)` flags the case where total demand can't fit, with hours short per line.

## Skeleton

```
services/simulator/
├── README.md
├── app/
│   ├── __init__.py
│   ├── implementation.py    ← TODO: Simulator(SimulatorContract)
│   ├── replay.py            ← incident replay logic
│   └── aggregations.py      ← per-line / global metric rollups
└── tests/
    ├── conftest.py
    └── fixtures/            ← tiny synthetic sequence + incident log
```
