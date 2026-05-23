# `services/etl/` — Data cleaning & demand dataset generation

> Owner: Person 1 · Contracts: [`ETLContract`](../../packages/contracts/module/etl.py),
> [`DemandBuilderContract`](../../packages/contracts/module/etl.py) ·
> Status: skeleton

This is the **initial bottleneck** of the LineWise pipeline. Until clean datasets land
in `data/clean/`, neither the optimiser nor the ML model nor the UI can do useful work.
**Milestone M1 (Sat 13:00)** is "ETL CSVs ready" — that's this service.

## Two responsibilities in one workspace

### 1. Raw-Excel → tidy CSV (`ETLContract.build_clean_datasets`)

Read everything in `data/raw/*.xlsx`, join on the keys documented in
[`docs/linewise/datos.md`](../../docs/linewise/datos.md) §2, and emit these CSVs in
`data/clean/`:

| Output CSV | Built from | Used by |
|---|---|---|
| `executed_runs.csv` | join `OEE` + `Tiempo` + `Volumen` + `Mantenimiento` on `OF == WOID` | optimiser (capability + speed), simulator, ML training |
| `changes_actual.csv` | `Cambios 14_17_19_ 2025.xlsx` keyed by `OF` | ML training (changeover flags) |
| `sku_master.csv` | `OEE` deduped per `SKU` | every downstream consumer |
| `sku_line_capability.csv` | aggregations of `executed_runs` per `(sku, tren)` | optimiser, ML matrix gating |
| `changeover_matrix.csv` | parse `Tabla CF Prat` hoja `LATA_BARRIL` + empirical aggregations | optimiser floor, ML target source |
| `calendar_constraints.csv` | parse `Tabla CF Prat` hoja `Tiempos adicionales` + runtime injections | optimiser forced events, simulator |
| `incident_log.csv` | derive from `Mantenimiento` + `Tiempo` (PNP / IDLE / saturación / falta producto) | simulator replay |
| `weekly_actual_v2026_05.csv` | `Produccion_L14,17,19_18-22.xlsx` | demo comparison vs `S_opt` |

**Discard explicitly**:
- `data - 2026-05-18T181640.542.xlsx` — duplicate of OEE 2025 (verified row-by-row).
- `Diario Hl_Planif.xlsx` — pivoted, inconsistent units (HL vs CAJ/UN), missing SKUs.

Both must be reported in `ETLResult.discarded_files`.

### 2. Demand dataset generation (`DemandBuilderContract.build_demand`)

The optimiser only ever consumes one schema (see
[`docs/linewise/reto.md`](../../docs/linewise/reto.md) §6.1): a list of
`DemandBucket(window_id, window_start, window_end, sku, uds_demanded, source, prioridad)`.

Three sources, one shape:

| Source | How to build it |
|---|---|
| `historico_2025` | From `executed_runs.csv` — drop `SKU == "LIMPIEZA"`, derive ISO week from `fecha_fin`, sum `uds` per `(sku, semana)`. |
| `plan_2026` | From `Planificado - producciones 14 - 17 - 19.XLSX` — normalise `Cntd plan` (CAJ → UN via `unidad_por_caja`), derive week from `fecha_ini`, sum per `(sku, semana)`. **Drop** `tren`, `hora_ini`, `definicion_de_turno` — those are JDA's solution, not the demand. |
| `whatif_usuario` | Direct `DemandBucket` from the UI's what-if form. |

Output goes both as Python objects (for in-process callers) and as `demand.csv` (for
debugging / replay).

## Contract recap in plain words

> Read every raw Excel under `data/raw/`. Produce eight tidy CSVs under
> `data/clean/`. Never modify the raw files. Surface data-quality warnings
> (OEE > 1, `H. Tot.` outliers, `Calidad ≠ 1`, ambiguous `Frecuencia Total` in
> `Cambios`, …) — don't silently clip. Then, on demand, aggregate any planning
> source to weekly `DemandBucket`s with `tren / día / turno` deliberately dropped.

## Data-quality decisions to honour

From [`docs/linewise/datos.md`](../../docs/linewise/datos.md) §5:

- Treat `OEE > 1` and `Ineficiencia < 0` as legitimate — report P50/P95, do not cap.
- `Calidad ≡ 1` ⇒ optimise A × P only.
- Derive `velocidad_efectiva(sku, línea) = median(UDS / Tiempo Máquina en Marcha)`.
- Derive `fecha_inicio = fecha_fin − H. Tot.` with overlap correction.
- `PRT…-M` rows: cleaning iff `SKU == "LIMPIEZA"`, else normal production.

## Skeleton

```
services/etl/
├── README.md              ← this file
├── app/
│   ├── __init__.py
│   ├── implementation.py  ← TODO: implements ETLContract + DemandBuilderContract
│   ├── parsers/           ← one parser per raw file family
│   └── joins/             ← join logic, deduplication, sanity checks
└── tests/
    ├── conftest.py
    └── fixtures/          ← tiny synthetic XLSX for CI
```

## Validation criteria (definition of done)

- [ ] All eight CSVs land in `data/clean/` and pass `pandera`-style schema checks.
- [ ] `ETLResult.warnings` surfaces at least the documented data-quality flags.
- [ ] Discarded files appear in `ETLResult.discarded_files`.
- [ ] `build_demand("historico_2025")` returns a non-empty tuple and round-trips
      through `to_csv` / re-read without loss.
- [ ] The simulator (downstream) is able to reproduce historical OEE within 5%
      using `executed_runs.csv` + `incident_log.csv`.

## Local commands

```bash
# Run ETL end-to-end from data/raw/ to data/clean/
python -m services.etl.app.implementation --raw data/raw --out data/clean

# Build weekly demand from history
python -m services.etl.app.implementation demand --source historico_2025 --out data/clean/demand.csv
```
