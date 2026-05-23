# Node-cost model — selection process and findings

> Companion to [`model_comparison.md`](model_comparison.md) (single split) and
> [`model_comparison_kfold.md`](model_comparison_kfold.md) (5-fold CV).
> This document is the narrative: how we got from the brief to the deployed
> artefact, what we measured, and why we picked what we picked.

## 1. Problem framing

The graph optimiser ([`services/optimizer/`](../../optimizer/)) — Architecture
D in [`docs/linewise/implementacion.md`](../../../docs/linewise/implementacion.md) —
treats production planning as pathfinding. **Nodes** are SKU chunks; **edges**
are SKU-to-SKU changeovers. The optimiser needs a cost per node:

> "How many productive hours will it take to produce *U* units of SKU *S* on
> line *L*, ignoring the transition that precedes it?"

`productive_hours` is the right target (not `total_hours`): inefficiencies
within a run (downtime, idle, low speed, in-run cleaning) are simulated
separately by [`services/simulator/`](../../simulator/) via deterministic
incident replay. If the node cost included those, they would be double-counted.

The MVP optimiser uses a simple per-`(sku, line)` median-speed lookup from
[`line_capability.csv`](../../../docs/data/line_capability.md). This document
records the experiment that asked: **can we beat that with ML?**

## 2. Data and preprocessing

Single training source: [`data/clean/wo_master.csv`](../../../data/clean/wo_master.csv),
joined with [`skus.csv`](../../../data/clean/skus.csv) for SKU attributes and
[`line_capability.csv`](../../../data/clean/line_capability.csv) for the system
baseline. ETL details in [`docs/data/wo_master.md`](../../../docs/data/wo_master.md).

Preprocessing in [`preprocessing.py`](../app/preprocessing.py):

1. Keep only `wo_kind == "production"`.
2. Drop `productive_hours < 0.5` (aborted runs).
3. Drop `oee > 1.2` (upstream measurement artefacts).
4. **Aggregate consecutive same-SKU WOs on the same line** into a single row.
   The optimiser models one `(sku, line)` chunk as one node, so the training
   granularity must match — otherwise ramp-up is repeated artificially. Sum
   `units_produced`, sum `productive_hours`, keep first row's SKU attributes.
5. Join SKU attributes and the `line_capability.median_speed_uds_per_hour`
   reference.

Result: **1,766 aggregated `(sku, line)` runs** (L14: 325 · L17: 747 · L19: 694).
Median productive hours per run is ~5 h on L17/L19 and ~9 h on L14.

## 3. Target parameterization journey

| Iteration | Target | Rationale | Outcome |
|---|---|---|---|
| Initial proposal | `effective_speed_uds_per_hour` | Scale-free; hours recovered by division | Set aside per user input |
| After feedback | `total_hours` | "Sum of node costs + edge costs = total time window" | Considered |
| Corrected | `productive_hours` | The MVP doesn't model in-run inefficiencies — those belong to the simulator's incident replay, not to the node-cost model | Used for all models |
| Final experiment | back to speed (with hours recovered) | Speed target eliminates the multiplicative `units × (1/speed)` interaction that tree models struggle to learn; analytical division at inference recovers hours | **Winner** |

The final winning architecture is therefore: model predicts **speed**, post-process
divides units by predicted speed to get **hours**. Same target the user originally
heard about; we arrived back at it because the experiment proved the
parameterization mattered more than the algorithm.

## 4. Features

14 inputs, mostly categorical:

| # | Feature | Type | Source |
|---|---|---|---|
| 1 | `line_id` | categorical | wo_master |
| 2 | `sku_id` | categorical | wo_master |
| 3 | `container_type` | categorical | skus (1/2, 1/3, 2/5) |
| 4 | `brand` / `family` / `beer` | categorical | skus |
| 5 | `primary_packaging` / `secondary_packaging` / `pallet_type` / `units_per_case` | categorical | skus |
| 6 | `units_produced` | numeric | wo_master (aggregated) |
| 7 | `sqrt_units` / `log_units` | numeric | derived (ramp-up shape) |
| 8 | `train_median_speed_uds_per_hour` | numeric | train-only median over `(sku, line)` → `line` → global |

We **explicitly deferred** temporal features (`day_of_week`,
`hours_since_last_cleaning`, `cumulative_run_hours_today`) to
[`docs/future_improvements.md`](../../../docs/future_improvements.md) — they
need ETL work to preserve `end_day` through the aggregation step.

## 5. Baselines

Two baselines because the optimiser's existing fallback contains an implicit
leakage:

* **Baseline system.** `units_produced / line_capability.median_speed_uds_per_hour`.
  `line_capability.csv` was built from the *whole* historical dataset, so any
  holdout row contributed to its own per-pair median. Kept for reference as
  the system that's deployed today.
* **Baseline fair.** Same formula, but the median is recomputed from train
  rows only at each split. **This is the honest bar to beat.**

## 6. Models surveyed

11 model variants on a single 80/20 holdout (stratified by `line_id`), then
the top eight on 5-fold CV (also stratified by `line_id`). All numbers below
are 5-fold CV mean MAE (lower is better); per-fold raw numbers are in
[`model_comparison_kfold.json`](model_comparison_kfold.json).

| Model | mean MAE (h) | std | vs fair baseline |
|---|---:|---:|---:|
| Baseline system *(leakage)* | 0.320 | 0.019 | +18.4% |
| **CatBoost [speed→hours]** ← selected | **0.362** | **0.025** | **+7.9%** |
| Baseline fair | 0.393 | 0.025 | — |
| MLP torch (sku-embed + residual head) | 0.397 | 0.022 | −1.2% |
| LightGBM [speed→hours] | 0.411 | 0.022 | −4.6% |
| Ridge (hours target, with units) | 0.419 | 0.029 | −6.8% |
| LightGBM (hours target) | 0.543 | 0.160 | −38.2% |
| CatBoost (hours target) | 0.552 | 0.078 | −40.6% |

Additional variants run on single split (full list in
[`model_comparison.md`](model_comparison.md)): Random Forest (hours and speed),
Ridge no-units, Mixed-effects (random intercept per SKU), MLP sklearn,
LightGBM with monotonic constraint, LightGBM speed-target. None beat the
selected model.

## 7. Findings

### 7.1 The first round: nothing beat the baseline

With every model trained to predict `productive_hours` directly, the
leakage-free baseline (MAE = 0.403 on single split, 0.393 on CV) was the
ceiling. Best ML (CatBoost hours-target) at 0.517 single-split, 0.552 CV —
materially worse. Conclusion at that point: ship the baseline.

### 7.2 The parameterization experiment

The "predict speed, divide by units to get hours" parameterization changed the
result by a large margin for tree models:

| Model | hours target MAE (CV) | speed→hours MAE (CV) | Δ |
|---|---:|---:|---:|
| CatBoost | 0.552 | **0.362** | **−34%** |
| LightGBM | 0.543 | 0.411 | −24% |
| Random Forest | 0.539 *(single split)* | 0.456 *(single split)* | −15% |
| Ridge | 0.419 | 0.486 | +16% (worse) |

Why: when the target is hours, the tree has to discover the `units × (1/speed)`
relationship via splits — wasteful on ~1.4k rows. When the target is speed,
the model only has to learn the rate per `(sku, line)` and its perturbations
by attributes; the analytical `units / speed` does the multiplication at
inference for free. Ridge moves the other way: it can express the
multiplicative interaction through its `baseline_pred_hours` feature
(`= units / median_speed`), and stripping that feature in the speed target
costs it.

### 7.3 The lift is robust under CV

CatBoost [speed→hours] beat the fair baseline in **5/5 folds**, with per-fold
lift bounded between +5.1% and +10.8%, mean +7.9%, standard deviation of the
lift across folds ~2 pp. Not a single-split artefact.

### 7.4 What the model is doing

Feature importance (PredictionValuesChange) on the final fitted model:

| Feature | Importance |
|---|---:|
| `train_median_speed_uds_per_hour` | 68.8% |
| `line_id` | 8.8% |
| `container_type` | 6.7% |
| `pallet_type` | 2.2% |
| `secondary_packaging` | 2.1% |
| `beer` | 2.0% |
| `primary_packaging` | 1.7% |
| `units_per_case` | 1.7% |
| `sqrt_units` + `log_units` + `units_produced` | 4.1% combined |
| `family` | 1.0% |
| `brand` | 0.8% |
| `sku_id` | 0.0% |

Read it as: ~69% of the signal is "look up the median speed of this pair", the
remaining ~30% is small corrections by line, container type, and packaging
attributes. **`sku_id` carries zero extra signal** once the train-median speed
is in the model — the lookup already encodes everything SKU-specific. The
model is essentially a smoothed/refined baseline, which is exactly the right
intuition for an explainable production tool.

## 8. Selection rationale

CatBoost [speed→hours] is the deploy candidate because:

1. **It beats the fair baseline consistently** (+7.9% MAE, 5/5 folds, low
   variance across folds).
2. **Predictions are explainable.** Two-thirds of each prediction comes from a
   transparent lookup; the remainder is a small CatBoost correction with
   per-feature SHAP values available at inference for the UI drill-down.
3. **Inference is cheap.** A small `.cbm` (123 boosting rounds at depth 6) plus
   two CSV lookups. No GPU. Easy to ship into the optimiser's hot loop.
4. **Native categorical handling.** CatBoost handles the 170-cardinality
   `sku_id` plus the SKU attribute fields without hand-rolled encoding.
5. **Speed-target is interpretable.** The model predicts the rate of the line
   on this SKU; the planner sees the same quantity they reason about.

## 9. Limitations and follow-ups

* **No temporal context.** Day-of-week, time-since-last-cleaning, week-of-year
  are not in the model. They probably exist as signal and need ETL work to
  surface — see [`docs/future_improvements.md`](../../../docs/future_improvements.md) §1.
* **Cold-start regimes untested.** All CV folds contain test rows whose
  `(sku, line)` pair was seen in training. The deployed model degrades
  gracefully (lookup falls back to line median, then global) but we haven't
  measured how badly. A held-out-pair evaluation would tell us.
* **System baseline still 13% better than ML.** With leakage. We don't have a
  way to safely consume `line_capability.csv` at planning time without
  introducing the same leakage in the model. The honest comparison is against
  the fair baseline, which is what we've beaten.
* **Walk-forward CV not run.** Folds are random. If production drift exists,
  random CV under-estimates real degradation. Worth doing if temporal features
  ever land.

## 10. Artefacts produced

All under [`services/node_cost_ml/`](..):

| File | What it is |
|---|---|
| [`app/preprocessing.py`](../app/preprocessing.py) | Loads + aggregates + joins; emits the modelling frame |
| [`app/train.py`](../app/train.py) | Bench harness (11 model variants on a single 80/20 split) |
| [`app/kfold.py`](../app/kfold.py) | 5-fold CV harness for the top 8 |
| [`app/fit_final.py`](../app/fit_final.py) | Trains the selected model on the **full** dataset and writes artefacts |
| [`app/inference.py`](../app/inference.py) | `predict_node_cost(df, include_shap=False)` |
| [`artifacts/model.cbm`](../artifacts/model.cbm) | The CatBoost regressor (speed target) |
| [`artifacts/speed_lookup_pair.csv`](../artifacts/speed_lookup_pair.csv) | Median speed per `(sku, line)` over the full data |
| [`artifacts/speed_lookup_line.csv`](../artifacts/speed_lookup_line.csv) | Median speed per `line_id` (fallback) |
| [`artifacts/meta.json`](../artifacts/meta.json) | Feature schema + global-median speed + provenance |
| [`reports/model_comparison.md`](model_comparison.md) | Single-split benchmark (11 variants) |
| [`reports/model_comparison_kfold.md`](model_comparison_kfold.md) | 5-fold CV (top 8) |
| [`reports/model_selection.md`](model_selection.md) | This document |

## 11. How to use

Train from scratch (re-fits on whatever is currently in `data/clean/`):

```bash
python -m services.node_cost_ml.app.fit_final
```

Predict for a batch of nodes — pass a DataFrame in `wo_master` shape (only
`line_id`, `sku_id`, `units_produced` are strictly required; SKU attributes
are joined automatically when absent):

```python
import pandas as pd
from services.node_cost_ml.app.inference import predict_node_cost

nodes = pd.DataFrame({
    "line_id": [17, 14, 19],
    "sku_id":  ["FD13LTNN", "3BNEBL23", "XI12LT"],
    "units_produced": [200_000, 500_000, 80_000],
})

out = predict_node_cost(nodes, include_shap=False)
# columns added: predicted_speed_uds_per_hour, predicted_hours,
#                train_median_speed_uds_per_hour
```

With SHAP attribution for the drill-down UI (one `shap_<feature>` column per
input plus `shap_base_value`, all in *speed* units; SHAP values are additive
to `predicted_speed_uds_per_hour`):

```python
out = predict_node_cost(nodes, include_shap=True)
```
