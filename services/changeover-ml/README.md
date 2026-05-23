# `services/changeover-ml/` — ML changeover-time predictor

> Owner: Person 2 · Contract: [`ChangeoverModelContract`](../../packages/contracts/module/changeover_ml.py) · Status: skeleton

## What this service does, in plain words

Given two SKUs and a line, **predict in hours how long the changeover will take**.
That number becomes the weight of an edge in the optimiser's graph (Architecture D).

It does **not** predict OEE. OEE is computed by the [`simulator`](../simulator/) after
the optimiser produces a sequence. Keeping the ML scope this narrow gives:

- A single observable, validatable target (changeover hours derived from `PNP` before
  marcha in `executed_runs` ordered by `(tren, fecha_fin)`).
- SHAP attribution that is operationally meaningful: "this transition cost +1.3 h
  because `C.Envase` flipped on a Monday morning."
- A clean handoff to the optimiser — no risk of "predicted OEE" diverging from
  "reported OEE."

## Operating modes (matters because data support is uneven)

Per pair `(sku_from, sku_to, tren)`:

| Historical observations | Returned `source` | What we return |
|---|---|---|
| ≥ 5 | `"ml"` | Pure model prediction |
| 1–4 | `"hibrido"` | Weighted blend of model + theoretical (from `Tabla CF Prat`) |
| 0 | `"teorico"` | Theoretical matrix only |

The optimiser may additionally **clamp** the returned hours to the theoretical floor —
that policy lives in [`services/optimizer/`](../optimizer/), not here.

## Inputs

- `data/clean/executed_runs.csv` ordered by `(tren, fecha_fin)` → derive empirical
  changeover times.
- `data/clean/changes_actual.csv` → categorical features (`C.Brand`, `C.Envase`,
  `C.CAP`, `C.Volum`, `C.Palet`, `C.Primario`, `C.Secundario`, `C.Producto`).
- `data/clean/sku_master.csv` → SKU attributes for the join.
- `data/clean/changeover_matrix.csv` (theoretical) → fallback when the model can't
  predict confidently.

## Validation

- **Walk-forward** split on ISO week (train on weeks < cutoff, validate on weeks ≥
  cutoff). The contract requires reporting MAE / RMSE / R² in `TrainingResult`.
- Sanity floor: the validation MAE should beat the theoretical-matrix-as-prediction
  baseline. If it doesn't, default to theoretical and document the regression.

## Contract recap in plain words

> The optimiser will hand you a list of SKU pairs and a line; you return predicted
> changeover hours per pair, with a confidence score and a source tag so the
> optimiser knows whether to trust you, blend, or fall back. Don't reach into
> the optimiser, don't predict OEE, and don't silently mask predictions with
> theoretical values — emit `source = "hibrido"` so the user can see it.

## Skeleton

```
services/changeover-ml/
├── README.md
├── app/
│   ├── __init__.py
│   ├── implementation.py          ← TODO: ChangeoverModel(ChangeoverModelContract)
│   ├── features.py                ← feature engineering from changes_actual + sku_master
│   └── training.py                ← walk-forward loop, model persistence
└── tests/
    ├── conftest.py
    └── fixtures/                  ← small synthetic dataset
```

## Stack default

- LightGBM or XGBoost regressor (tabular target, fast, SHAP-supported).
- `joblib` for persistence; the optimiser loads the artefact once at startup.

## Definition of done

- [ ] `fit()` produces a model file in `data/clean/models/changeover.joblib` and
      returns a `TrainingResult` with MAE / RMSE / R² and feature importance.
- [ ] `predict_matrix(skus, tren)` returns a complete dict for the optimiser's
      candidate edges.
- [ ] Walk-forward MAE beats the theoretical-matrix baseline (or we document a
      conscious fallback).
- [ ] SHAP values for the top-20 worst historical transitions are exported for the
      UI drill-down.
