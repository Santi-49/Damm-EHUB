"""5-fold cross-validation of the top contenders.

Re-runs the most informative models from train.py across 5 folds (stratified by
`line_id`) so we can see whether the single-split lift of `CatBoost [speed→hours]`
over the fair baseline is robust or seed-luck on one 354-row test.

Critically, the train-only baseline features (`train_median_speed_uds_per_hour`
and `baseline_pred_hours`) are recomputed **inside each fold** to keep the CV
leakage-free.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

# Windows console defaults to cp1252; the model names contain a unicode arrow.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass

import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedKFold

from services.node_cost_ml.app.preprocessing import build_modelling_frame
from services.node_cost_ml.app.train import (
    RANDOM_STATE,
    TARGET,
    add_train_only_features,
    baseline_fair,
    baseline_system,
    build_ridge,
    evaluate,
    train_catboost,
    train_catboost_speed_target,
    train_lgb_speed_target,
    train_lightgbm,
    train_mlp_residual,
)

REPORT_DIR = Path(__file__).resolve().parents[1] / "reports"
N_SPLITS = 5


@dataclass
class FoldResult:
    fold: int
    model: str
    mae: float
    rmse: float
    median_ape: float


def run_fold(fold: int, train_raw: pd.DataFrame, test_raw: pd.DataFrame) -> list[FoldResult]:
    train, test = add_train_only_features(train_raw, test_raw)
    y_test = test[TARGET].values
    units_test = test["units_produced"].values
    n_train = len(train)
    results: list[FoldResult] = []

    def record(name: str, pred: np.ndarray) -> None:
        m = evaluate(name, y_test, pred, n_train, units_test)
        results.append(FoldResult(fold=fold, model=name, mae=m.mae, rmse=m.rmse, median_ape=m.median_ape))

    # Baselines
    record("Baseline system", baseline_system(test))
    record("Baseline fair", baseline_fair(train_raw, test_raw))

    # Ridge (hours target, with units)
    ridge = build_ridge(with_units=True)
    ridge.fit(train, train[TARGET].values)
    record("Ridge (hours, with units)", ridge.predict(test))

    # LightGBM hours target (best of the lgb hours variants — free)
    lgb_pred, _ = train_lightgbm(train, test, with_units=True, monotone_on_units=False)
    record("LightGBM (hours)", lgb_pred)

    # LightGBM speed → hours
    record("LightGBM [speed→hours]", train_lgb_speed_target(train, test))

    # CatBoost hours target
    cat_pred, _ = train_catboost(train, test)
    record("CatBoost (hours)", cat_pred)

    # CatBoost speed → hours (the candidate winner)
    record("CatBoost [speed→hours]", train_catboost_speed_target(train, test))

    # PyTorch tiny MLP residual head
    record("MLP torch (sku-embed + residual)", train_mlp_residual(train, test))

    return results


def main() -> None:
    df = build_modelling_frame()
    print(f"Modelling frame: {len(df)} rows. Running {N_SPLITS}-fold CV (stratified by line_id).")

    skf = StratifiedKFold(n_splits=N_SPLITS, shuffle=True, random_state=RANDOM_STATE)
    all_rows: list[FoldResult] = []
    for fold, (tr_idx, te_idx) in enumerate(skf.split(df, df["line_id"]), start=1):
        train_raw = df.iloc[tr_idx].reset_index(drop=True)
        test_raw = df.iloc[te_idx].reset_index(drop=True)
        print(f"\n--- Fold {fold}/{N_SPLITS} (n_train={len(train_raw)}, n_test={len(test_raw)}) ---")
        fold_results = run_fold(fold, train_raw, test_raw)
        for r in fold_results:
            print(f"  [{r.model:45s}] MAE={r.mae:.3f}  RMSE={r.rmse:.3f}  medAPE={r.median_ape*100:.1f}%")
        all_rows.extend(fold_results)

    write_report(all_rows)


def write_report(rows: list[FoldResult]) -> None:
    df = pd.DataFrame([r.__dict__ for r in rows])
    (REPORT_DIR / "model_comparison_kfold.json").write_text(
        json.dumps(df.to_dict(orient="records"), indent=2), encoding="utf-8"
    )

    agg = (
        df.groupby("model")["mae"]
        .agg(["mean", "std", "min", "max"])
        .sort_values("mean")
        .reset_index()
    )
    baseline_fair_mean = float(agg.loc[agg["model"] == "Baseline fair", "mean"].iloc[0])
    agg["lift_vs_fair_pct"] = (baseline_fair_mean - agg["mean"]) / baseline_fair_mean * 100

    lines = [
        "# Node-cost model — 5-fold cross-validation",
        "",
        f"Stratified by `line_id`. Seed = {RANDOM_STATE}.",
        "`train_median_speed_uds_per_hour` and `baseline_pred_hours` recomputed per fold (no leakage across folds).",
        "",
        "## MAE across folds (lower is better)",
        "",
        "| Model | mean | std | min | max | lift vs fair |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for _, row in agg.iterrows():
        lines.append(
            f"| {row['model']} | {row['mean']:.3f} | {row['std']:.3f} | "
            f"{row['min']:.3f} | {row['max']:.3f} | {row['lift_vs_fair_pct']:+.1f}% |"
        )

    # Paired fold-by-fold lift of CatBoost-speed vs fair baseline.
    pivot = df.pivot_table(index="fold", columns="model", values="mae")
    if "CatBoost [speed→hours]" in pivot.columns and "Baseline fair" in pivot.columns:
        per_fold = (pivot["Baseline fair"] - pivot["CatBoost [speed→hours]"])
        lines += [
            "",
            "## CatBoost [speed→hours] vs Baseline fair, per fold",
            "",
            "| Fold | Baseline fair MAE | CatBoost speed→hours MAE | Δ MAE (h) | Δ % |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
        for fold, val in per_fold.items():
            base = pivot.loc[fold, "Baseline fair"]
            cat = pivot.loc[fold, "CatBoost [speed→hours]"]
            lines.append(f"| {fold} | {base:.3f} | {cat:.3f} | {val:+.3f} | {val/base*100:+.1f}% |")
        lines += [
            "",
            f"**Mean lift across folds:** {per_fold.mean():+.3f} h ({per_fold.mean()/pivot['Baseline fair'].mean()*100:+.1f}%).",
            f"**Folds where CatBoost beats baseline:** {(per_fold > 0).sum()}/{len(per_fold)}.",
        ]

    (REPORT_DIR / "model_comparison_kfold.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"\nReport written to {REPORT_DIR / 'model_comparison_kfold.md'}")


if __name__ == "__main__":
    main()
