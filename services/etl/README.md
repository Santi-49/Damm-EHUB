# `services/etl/` — Data cleaning & demand dataset generation

> Owner: Person 1 · Contracts: [`ETLContract`](../../packages/contracts/module/etl.py),
> [`DemandBuilderContract`](../../packages/contracts/module/etl.py) ·
> Status: skeleton

This is the **initial bottleneck** of the LineWise pipeline. Until clean
datasets land in `data/clean/`, neither the optimiser nor the ML model nor the
UI can do useful work. **Milestone M1 (Sat 13:00)** is "clean data ready" —
that's this service.

## Two responsibilities in one workspace

### 1. Raw-Excel → tidy CSV (`ETLContract.build_clean_datasets`)

Read everything in `data/raw/*.xlsx` and emit the canonical data products
documented in [`docs/data/overview.md`](../../docs/data/overview.md):

| Output CSV | Doc | Status | Notes |
|---|---|---|---|
| `wo_master.csv` | [wo_master.md](../../docs/data/wo_master.md) | **MVP** | |
| `skus.csv` | [skus.md](../../docs/data/skus.md) | **MVP** | |
| `wo_changeovers.csv` | [wo_changeovers.md](../../docs/data/wo_changeovers.md) | **MVP** | Transition master: `sku_from → sku_to`, empirical `changeover_hours`, features. ML training source. |
| `line_capability.csv` | [line_capability.md](../../docs/data/line_capability.md) | **MVP** | |
| `line_calendar.csv` | [line_calendar.md](../../docs/data/line_calendar.md) | **MVP** | |
| `changeover_costs.csv` | [changeover_costs.md](../../docs/data/changeover_costs.md) | **MVP** | Theoretical floor — optimizer only, NOT training data. |
| `node_cost_train.csv` | [node_cost_train.md](../../docs/data/node_cost_train.md) | post-MVP | |
| `incidents.csv` | [incidents.md](../../docs/data/incidents.md) | M2 (simulator) | |

**Discard explicitly**:
- `data - 2026-05-18T181640.542.xlsx` — duplicate of `OEE 14_17_19_ 2025.xlsx`.
- `Diario Hl_Planif.xlsx` — pivoted, inconsistent.

Both must be reported in `ETLResult.discarded_files`.

Full cleaning recipe (joins, derivations, outlier handling, ambiguity
resolution): [`docs/data/cleaning_rules.md`](../../docs/data/cleaning_rules.md).

### 2. Demand dataset generation (`DemandBuilderContract.build_demand`)

The optimiser only ever consumes one schema (see
[`docs/data/demand.md`](../../docs/data/demand.md)): a tuple of
`DemandBucket(window_id, window_start, window_end, sku_id, units_demanded, source, priority)`.

Bucket size is governed by [`WindowConfig`](../../packages/contracts/module/schemas.py).
**Defaults to 7 days, Monday-anchored** — change it once and both the demand
dataset *and* the optimiser planning horizon move in lockstep.

Three sources, one shape (`historico_2025`, `plan_2026`, `whatif_usuario`).
See [`docs/data/demand.md`](../../docs/data/demand.md) for the mapping per source.

## Contract recap in plain words

> Read every raw Excel under `data/raw/`. Produce the nine cleaned products
> documented in `docs/data/`. Never modify the raw files. Surface data-quality
> warnings — don't silently clip. Then, on demand, aggregate any planning
> source to time-windowed `DemandBucket`s with `line_id / day / turn`
> deliberately dropped; window size comes from `WindowConfig`.

## Skeleton

```
services/etl/
├── README.md              ← this file
├── app/
│   ├── __init__.py
│   ├── implementation.py  ← TODO: ETL(ETLContract, DemandBuilderContract)
│   ├── parsers/           ← one parser per raw-file family
│   ├── joins/             ← join logic, deduplication, sanity checks
│   └── demand.py          ← the three build_demand source mappers
└── tests/
    ├── conftest.py
    └── fixtures/          ← tiny synthetic XLSX for CI
```

## Definition of done

- [ ] All seven MVP CSVs land in `data/clean/` and pass schema checks (`wo_master`, `skus`, `wo_changeovers`, `line_capability`, `line_calendar`, `changeover_costs`, `demand`).
- [ ] `ETLResult.warnings` surfaces every documented data-quality flag (catalogue in [`cleaning_rules.md`](../../docs/data/cleaning_rules.md) §11).
- [ ] Discarded files appear in `ETLResult.discarded_files`.
- [ ] `build_demand("historico_2025", clean_dir, window=WindowConfig(days=7))` returns a non-empty tuple and round-trips through `to_csv`.
- [ ] Switching `WindowConfig.days` from 7 to 14 doubles the row volume (sanity).
- [ ] The simulator (downstream) reproduces historical OEE within 5 % using `wo_master.csv` + `incidents.csv`.

## Local commands

```bash
# Run ETL end-to-end from data/raw/ to data/clean/
python -m services.etl.app.implementation --raw data/raw --out data/clean

# Build weekly demand from history
python -m services.etl.app.implementation demand \
    --source historico_2025 --window-days 7 --out data/clean/demand.csv
```
