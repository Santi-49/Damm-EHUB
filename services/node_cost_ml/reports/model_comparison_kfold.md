# Node-cost model — 5-fold cross-validation

Stratified by `line_id`. Seed = 42.
`train_median_speed_uds_per_hour` and `baseline_pred_hours` recomputed per fold (no leakage across folds).

## MAE across folds (lower is better)

| Model | mean | std | min | max | lift vs fair |
| --- | ---: | ---: | ---: | ---: | ---: |
| Baseline system | 0.320 | 0.019 | 0.302 | 0.346 | +18.4% |
| CatBoost [speed→hours] | 0.362 | 0.025 | 0.329 | 0.388 | +7.9% |
| Baseline fair | 0.393 | 0.025 | 0.362 | 0.419 | +0.0% |
| MLP torch (sku-embed + residual) | 0.397 | 0.022 | 0.368 | 0.420 | -1.2% |
| LightGBM [speed→hours] | 0.411 | 0.022 | 0.396 | 0.449 | -4.6% |
| Ridge (hours, with units) | 0.419 | 0.029 | 0.381 | 0.448 | -6.8% |
| LightGBM (hours) | 0.543 | 0.160 | 0.401 | 0.746 | -38.2% |
| CatBoost (hours) | 0.552 | 0.078 | 0.483 | 0.661 | -40.6% |

## CatBoost [speed→hours] vs Baseline fair, per fold

| Fold | Baseline fair MAE | CatBoost speed→hours MAE | Δ MAE (h) | Δ % |
| --- | ---: | ---: | ---: | ---: |
| 1 | 0.415 | 0.388 | +0.027 | +6.5% |
| 2 | 0.372 | 0.353 | +0.019 | +5.1% |
| 3 | 0.395 | 0.353 | +0.043 | +10.8% |
| 4 | 0.419 | 0.386 | +0.034 | +8.0% |
| 5 | 0.362 | 0.329 | +0.033 | +9.1% |

**Mean lift across folds:** +0.031 h (+7.9%).
**Folds where CatBoost beats baseline:** 5/5.