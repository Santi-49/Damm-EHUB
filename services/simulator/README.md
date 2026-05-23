# `services/simulator/` — Deterministic OEE simulator

> Owner: Person 1 · Contract: [`SimulatorContract`](../../packages/contracts/module/simulator.py) · Status: skeleton

## What this service does, in plain words

Given any production sequence — historical, optimiser-proposed, or hand-crafted — and
the same calendar + incident log, compute **OEE, hours productive, hours lost in
changeovers / cleaning / maintenance / incidents, coverage, and makespan** per line
and globally.

Two properties make it valuable:

1. **Deterministic**: identical inputs → identical outputs. No sampling. Same
   incidents are replayed on `S_real` and `S_opt`, so the comparison is a fair fight.
2. **Historically faithful**: when fed `S_real` (the actual 2025 sequence), the
   reported per-line OEE must reproduce the observed historical OEE within 5%.
   This is the *validation gate* the simulator must pass before being used to
   score `S_opt`.

## Why this is a separate service

The optimiser predicts only changeover times. **It does not predict OEE.** OEE is
*computed* here after the fact. This decoupling has three benefits:

- Bounded ML target (changeover hours) instead of composite KPI prediction.
- No risk of divergence between "predicted OEE used to choose a route" and "reported
  OEE displayed to the user."
- The simulator is reusable across all four architectures (A/B/C/D) and across
  the post-mortem / live demo / what-if modes.

## Contract recap in plain words

> Take a sequence (list of slots with `tren`, `sku`, `fecha_inicio`, `fecha_fin`,
> `uds_planificadas`), the capability table, the calendar, and the incident log.
> For each slot, in chronological order per line: apply changeover before, then
> production, then intersect with any incidents that fall in that `(tren,
> ventana)`, then subtract calendar events. Compute per-slot OEE and aggregate
> per line and globally. Return a `SimulationReport`.

## Incident replay (the fair-fight property)

`incident_log.csv` rows are anchored to `(tren, instante_inicio, duracion_h,
motivo)` — the equipment and the moment, **not the SKU**. A `2025-03-08 10:00`
breakdown on L17 happened independently of which SKU was on the line. If `S_opt`
places another SKU there, it suffers the same downtime. This is physically and
operationally correct.

Exception: incidents *clearly attributable to a SKU* (recurring jams of a specific
format) may be anchored to `(sku, tren)`. Document each exception in the
incident log row.

## Inputs

- `Sequence` from the optimiser (or built from `executed_sequences.csv` for `S_real`).
- `data/clean/sku_line_capability.csv` → `speed_median_uds_h` per `(sku, tren)`.
- `data/clean/calendar_constraints.csv` → cleaning + maintenance windows.
- `data/clean/incident_log.csv` → incidents to replay.

## Output

`SimulationReport` (see `packages/contracts/module/schemas.py`):

- `per_line[LineId] → LineMetrics`: OEE, hours productive / changeover /
  cleaning / maintenance / incidents / low-speed, coverage, makespan.
- Global OEE weighted by hours, total productive / changeover hours, global
  coverage, makespan = `max(per_line.makespan_h)`.
- `uds_no_producidas[sku] → int`: SKUs the optimiser had to drop.

## Definition of done

- [ ] `evaluate_sequence(S_real, …)` reproduces 2025 historical OEE per line
      within 5%.
- [ ] `evaluate_sequence(S_opt, …)` runs in < 100 ms on a one-week horizon so
      the optimiser can use it as a fitness function.
- [ ] `detect_infeasibility(S, calendar)` flags the case where total demand
      can't fit, with hours short per line.

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
