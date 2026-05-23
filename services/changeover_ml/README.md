# `services/changeover_ml/` — ML changeover-time predictor

> Owner: Person 2 · Contract: [`ChangeoverModelContract`](../../packages/contracts/module/changeover_ml.py) · Status: skeleton

## What this service does, in plain words

Given two SKUs and a line, **predict the changeover time in hours, split into
segments** (brand / container / cap / packaging / pallet / product / volume /
startup / shutdown) **that sum to the total**. That number becomes the weight
of an edge in the optimiser's graph (Architecture D).

It does **not** predict OEE — OEE is computed by the
[`simulator`](../simulator/) after the optimiser has chosen a sequence.
Keeping the ML scope this narrow gives:

- A single observable, validatable target (the empirical changeover hours from
  [`docs/data/edge_cost_train.md`](../../docs/data/edge_cost_train.md)).
- SHAP attribution that lands on each segment — operationally meaningful.
- Clean handoff to the optimiser, no risk of "predicted OEE" diverging from
  "reported OEE."

## Operating modes (data support is uneven)

Per `(sku_from_id, sku_to_id, line_id)` triple:

| Historical observations | Returned `source` | Behaviour |
|---|---|---|
| ≥ 5 | `"ml"` | Pure model prediction |
| 1–4 | `"hibrido"` | Weighted blend of model + theoretical |
| 0 | `"teorico"` | Theoretical floor from `changeover_costs.csv` |

The optimiser may additionally **clamp** the returned hours to the theoretical
floor — that policy lives in [`services/optimizer/`](../optimizer/), not here.

## Inputs

- [`edge_cost_train.csv`](../../docs/data/edge_cost_train.md) — primary training table.
- [`changeover_costs.csv`](../../docs/data/changeover_costs.md) — theoretical floor and the source of segment shares for low-support triples.
- [`skus.csv`](../../docs/data/skus.md) — SKU attribute features.
- [`wo_changeovers.csv`](../../docs/data/wo_changeovers.md) — flag features used during training.

## Validation

- **Walk-forward** by `WindowConfig.days`-sized windows
  (`cutoff_window_id` parameter of `WalkForwardSplit`).
- Sanity floor: the validation MAE must beat using the theoretical matrix as
  the prediction. If it doesn't, default to theoretical and log the regression.
- Sum-equals-total: at inference, `sum(segments.values()) ≈ total_hours`
  (within numerical tolerance).

## Contract recap in plain words

> The optimiser hands you a list of SKU pairs and a line. You return predicted
> total changeover hours **and** a segmented breakdown per pair, with a
> confidence and a source tag so the optimiser knows whether to trust you,
> blend, or fall back. Don't reach into the optimiser, don't predict OEE, and
> don't silently mask predictions with theoretical values — emit
> `source = "hibrido"` so the user can see it.

## Skeleton

```
services/changeover_ml/
├── README.md
├── app/
│   ├── __init__.py
│   ├── implementation.py    ← TODO: ChangeoverModel(ChangeoverModelContract)
│   ├── features.py          ← feature engineering join logic
│   └── training.py          ← walk-forward loop, model persistence
└── tests/
    ├── conftest.py
    └── fixtures/            ← small synthetic dataset
```

## Stack default

- LightGBM (or XGBoost) regressor — tabular target, fast, SHAP-supported.
- Multi-output head (one per segment) trained with a softmax-like
  normalisation so the segments sum to the total, *plus* a separate head for
  the total to provide a sanity-check signal.
- `joblib` for persistence; the optimiser loads the artefact once at startup.

## Definition of done

- [ ] `fit()` produces `data/clean/models/changeover.joblib` and returns a `TrainingResult` with total + per-segment MAE.
- [ ] `predict_matrix(sku_ids, line_id)` returns a complete dict for the optimiser's candidate edges.
- [ ] Walk-forward total MAE beats the theoretical-matrix baseline (or we document a conscious fallback).
- [ ] `sum(segments.values())` equals `total_hours` within 0.05 h tolerance for every prediction.
- [ ] SHAP values for the top-20 worst historical transitions exported for the UI drill-down.
