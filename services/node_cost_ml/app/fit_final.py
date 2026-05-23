"""Train the selected model on the full dataset and persist artefacts.

Selected model: **CatBoost predicting effective speed** (`units / productive_hours`),
with hours recovered analytically at inference (`hours = units / speed`).
Selection rationale and full benchmark in
`services/node_cost_ml/reports/model_selection.md`.

Artefacts (all under ``services/node_cost_ml/artifacts/``):

* ``model.cbm`` — the trained CatBoost regressor (speed target).
* ``speed_lookup_pair.csv`` — train-median speed per ``(sku_id, line_id)``.
* ``speed_lookup_line.csv`` — train-median speed per ``line_id`` (fallback).
* ``meta.json`` — feature columns, cat indices, global-median speed, train rows used.

The persisted artefacts are everything ``inference.predict_node_cost`` needs.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from catboost import CatBoostRegressor

from services.node_cost_ml.app.preprocessing import (
    SKU_ATTR_COLUMNS,
    build_modelling_frame,
)

ARTIFACT_DIR = Path(__file__).resolve().parents[1] / "artifacts"
RANDOM_STATE = 42

CATEGORICAL_FEATS = ["line_id", "sku_id", *SKU_ATTR_COLUMNS]
NUMERIC_FEATS = [
    "units_produced",
    "sqrt_units",
    "log_units",
    "train_median_speed_uds_per_hour",
]
FEATURE_COLS = list(CATEGORICAL_FEATS) + NUMERIC_FEATS


@dataclass
class FitArtefacts:
    model_path: Path
    pair_lookup_path: Path
    line_lookup_path: Path
    meta_path: Path
    n_train: int
    n_iterations: int


def build_speed_lookups(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, float]:
    """Per-row median speed lookups: (sku, line) → line → global.

    Speeds are `units_produced / productive_hours`. Built from the FULL training
    frame here because there is no holdout at deploy time.
    """
    speed = df["units_produced"] / df["productive_hours"]
    pair = (
        df.assign(_s=speed)
        .groupby(["sku_id", "line_id"])["_s"]
        .median()
        .reset_index()
        .rename(columns={"_s": "train_median_speed_uds_per_hour"})
    )
    line = (
        df.assign(_s=speed)
        .groupby("line_id")["_s"]
        .median()
        .reset_index()
        .rename(columns={"_s": "train_median_speed_uds_per_hour"})
    )
    global_speed = float(speed.median())
    return pair, line, global_speed


def attach_speed_feature(
    df: pd.DataFrame,
    pair: pd.DataFrame,
    line: pd.DataFrame,
    global_speed: float,
) -> pd.DataFrame:
    out = df.merge(pair, on=["sku_id", "line_id"], how="left", suffixes=("", "_pair"))
    out = out.merge(line, on="line_id", how="left", suffixes=("", "_line"))
    # The pair lookup is the primary value. When missing, fall back to line, then global.
    out["train_median_speed_uds_per_hour"] = (
        out["train_median_speed_uds_per_hour"]
        .fillna(out["train_median_speed_uds_per_hour_line"])
        .fillna(global_speed)
    )
    return out.drop(columns=[c for c in out.columns if c.endswith("_line")])


def fit_final_model(output_dir: Path = ARTIFACT_DIR) -> FitArtefacts:
    output_dir.mkdir(parents=True, exist_ok=True)
    df = build_modelling_frame()
    print(f"Modelling frame: {len(df)} rows")

    pair, line, global_speed = build_speed_lookups(df)
    df = attach_speed_feature(df, pair, line, global_speed)

    X = df[FEATURE_COLS].copy()
    for c in CATEGORICAL_FEATS:
        X[c] = X[c].astype(str).fillna("nan")
    cat_idx = [FEATURE_COLS.index(c) for c in CATEGORICAL_FEATS]
    y = (df["units_produced"] / df["productive_hours"]).values

    # 123 boosting rounds was the early-stop optimum in CV.
    # Use a small buffer here since there's no validation set.
    model = CatBoostRegressor(
        iterations=300,
        learning_rate=0.05,
        depth=6,
        loss_function="MAE",
        cat_features=cat_idx,
        random_seed=RANDOM_STATE,
        verbose=0,
    )
    model.fit(X, y)

    model_path = output_dir / "model.cbm"
    pair_path = output_dir / "speed_lookup_pair.csv"
    line_path = output_dir / "speed_lookup_line.csv"
    meta_path = output_dir / "meta.json"

    model.save_model(str(model_path))
    pair.to_csv(pair_path, index=False)
    line.to_csv(line_path, index=False)
    meta = {
        "feature_cols": FEATURE_COLS,
        "categorical_feats": CATEGORICAL_FEATS,
        "numeric_feats": NUMERIC_FEATS,
        "cat_idx": cat_idx,
        "global_speed_uds_per_hour": global_speed,
        "n_train": int(len(df)),
        "n_iterations": int(model.tree_count_),
        "target": "effective_speed_uds_per_hour",
        "inference_recovery": "predicted_hours = units_produced / predicted_speed",
        "random_state": RANDOM_STATE,
    }
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    print(f"Saved model       -> {model_path}")
    print(f"Saved pair lookup -> {pair_path} ({len(pair)} rows)")
    print(f"Saved line lookup -> {line_path} ({len(line)} rows)")
    print(f"Saved meta        -> {meta_path}")
    return FitArtefacts(
        model_path=model_path,
        pair_lookup_path=pair_path,
        line_lookup_path=line_path,
        meta_path=meta_path,
        n_train=len(df),
        n_iterations=int(model.tree_count_),
    )


if __name__ == "__main__":
    fit_final_model()
