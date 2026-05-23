# Node-cost model comparison

Target: `productive_hours` per aggregated `(line, sku)` run.
Dataset: 1766 rows after aggregation. Train/test split = 80/20, stratified by `line_id`, seed=42. n_train=1412, n_test=354.

## Results (sorted by MAE — lower is better)

| Rank | Model | MAE (h) | RMSE (h) | R² | MAPE | Median APE |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 1 | Baseline system (units / line_capability) | 0.337 | 0.732 | 0.996 | 6.3% | 4.5% |
| 2 | CatBoost [speed→hours] | 0.353 | 0.695 | 0.996 | 7.1% | 5.2% |
| 3 | Baseline fair (units / train-median) | 0.403 | 0.811 | 0.995 | 7.7% | 6.0% |
| 4 | MLP torch (sku-embed + residual) | 0.404 | 0.814 | 0.995 | 7.9% | 6.0% |
| 5 | Ridge (no units) | 0.422 | 0.832 | 0.995 | 9.9% | 7.4% |
| 6 | Ridge (with units) | 0.424 | 0.837 | 0.995 | 9.5% | 6.7% |
| 7 | LightGBM [speed→hours] | 0.446 | 0.904 | 0.994 | 8.4% | 7.0% |
| 8 | Random Forest [speed→hours] | 0.456 | 0.859 | 0.994 | 8.8% | 6.6% |
| 9 | MLP sklearn (with units) | 0.468 | 1.197 | 0.989 | 9.6% | 7.1% |
| 10 | Mixed-effects (random intercept per sku@line) | 0.486 | 0.917 | 0.993 | 12.7% | 9.5% |
| 11 | Ridge [speed→hours] | 0.486 | 1.440 | 0.984 | 7.9% | 6.0% |
| 12 | MLP sklearn (no units) | 0.502 | 0.928 | 0.993 | 14.2% | 8.2% |
| 13 | Random Forest (no units) | 0.536 | 2.287 | 0.959 | 8.5% | 6.5% |
| 14 | Random Forest (with units) | 0.542 | 2.279 | 0.959 | 8.5% | 6.5% |
| 15 | CatBoost (with units) | 0.628 | 2.612 | 0.947 | 8.6% | 6.7% |
| 16 | LightGBM (with units, mono) | 0.691 | 3.443 | 0.908 | 10.3% | 7.7% |
| 17 | LightGBM (with units, free) | 0.693 | 3.454 | 0.907 | 10.4% | 7.8% |
| 18 | LightGBM (no units) | 0.709 | 3.468 | 0.906 | 11.2% | 8.4% |

## Headline

- Best ML model: **CatBoost [speed→hours]** at MAE = 0.353 h.
- Fair baseline (no leakage) MAE = 0.403 h → best ML lifts by **+12.5%**.
- System baseline (line_capability.csv, slight leakage) MAE = 0.337 h → best ML lifts by **-4.6%**.

## Notes

- Predictions clipped at 0.01 h to avoid pathological MAPE blow-ups.
- `Baseline system` reads `median_speed` straight from `line_capability.csv` — that file is built from the whole historical dataset, so it has implicit
  train-test leakage and is shown only as a deployable reference.
- `Baseline fair` recomputes `median_speed` from train rows only. That's the
  honest target to beat at deploy time.
- The mixed-effects model uses random intercept per `sku_id` and falls back to
  the fixed-effects prediction for unseen SKUs.