"""Inference for the saved node-cost model.

Public entry point: :func:`predict_node_cost`. Takes a ``wo_master``-shaped
DataFrame (only ``line_id``, ``sku_id`` and ``units_produced`` are required —
extra columns are passed through), joins SKU attributes, attaches the saved
train-median speed lookup, asks CatBoost for the speed prediction, and recovers
hours as ``units / speed``.

Optionally returns per-row SHAP values explaining the speed prediction.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from catboost import CatBoostRegressor, Pool

from services.node_cost_ml.app.fit_final import ARTIFACT_DIR
from services.node_cost_ml.app.preprocessing import DATA_DIR, SKU_ATTR_COLUMNS

REQUIRED_COLS = ("line_id", "sku_id", "units_produced")


@dataclass(frozen=True)
class LoadedModel:
    model: CatBoostRegressor
    pair_lookup: pd.DataFrame
    line_lookup: pd.DataFrame
    global_speed: float
    feature_cols: list[str]
    categorical_feats: list[str]
    cat_idx: list[int]


def load_artefacts(artifact_dir: Path = ARTIFACT_DIR) -> LoadedModel:
    meta = json.loads((artifact_dir / "meta.json").read_text(encoding="utf-8"))
    model = CatBoostRegressor()
    model.load_model(str(artifact_dir / "model.cbm"))
    pair = pd.read_csv(artifact_dir / "speed_lookup_pair.csv")
    line = pd.read_csv(artifact_dir / "speed_lookup_line.csv")
    return LoadedModel(
        model=model,
        pair_lookup=pair,
        line_lookup=line,
        global_speed=float(meta["global_speed_uds_per_hour"]),
        feature_cols=list(meta["feature_cols"]),
        categorical_feats=list(meta["categorical_feats"]),
        cat_idx=list(meta["cat_idx"]),
    )


def _validate(df: pd.DataFrame) -> None:
    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        raise ValueError(
            f"Input DataFrame is missing required columns: {missing}. "
            f"Expected at least {REQUIRED_COLS}."
        )


def _join_sku_attrs(df: pd.DataFrame) -> pd.DataFrame:
    """Join SKU attributes if they aren't already on the input."""
    needed = [c for c in SKU_ATTR_COLUMNS if c not in df.columns]
    if not needed:
        return df
    skus = pd.read_csv(DATA_DIR / "skus.csv")
    keep = ["sku_id", *needed]
    return df.merge(skus[keep], on="sku_id", how="left")


def _attach_speed_feature(df: pd.DataFrame, lm: LoadedModel) -> pd.DataFrame:
    out = df.merge(lm.pair_lookup, on=["sku_id", "line_id"], how="left")
    out = out.merge(
        lm.line_lookup.rename(
            columns={"train_median_speed_uds_per_hour": "_line_speed"}
        ),
        on="line_id",
        how="left",
    )
    out["train_median_speed_uds_per_hour"] = (
        out["train_median_speed_uds_per_hour"]
        .fillna(out["_line_speed"])
        .fillna(lm.global_speed)
    )
    return out.drop(columns=["_line_speed"])


def _build_features(df: pd.DataFrame, lm: LoadedModel) -> pd.DataFrame:
    if "sqrt_units" not in df.columns:
        df = df.assign(sqrt_units=np.sqrt(df["units_produced"]))
    if "log_units" not in df.columns:
        df = df.assign(log_units=np.log1p(df["units_produced"]))
    X = df[lm.feature_cols].copy()
    for c in lm.categorical_feats:
        X[c] = X[c].astype(str).fillna("nan")
    return X


def predict_node_cost(
    inputs: pd.DataFrame,
    *,
    include_shap: bool = False,
    artifact_dir: Path = ARTIFACT_DIR,
    loaded: LoadedModel | None = None,
) -> pd.DataFrame:
    """Predict node cost (productive hours) for each row.

    Parameters
    ----------
    inputs
        A DataFrame in master-WO shape. Must include ``line_id``, ``sku_id`` and
        ``units_produced``. Extra columns are preserved. SKU attributes are
        joined from ``data/clean/skus.csv`` when absent.
    include_shap
        When ``True``, attach one ``shap_<feature>`` column per model input plus
        ``shap_base_value`` (the expected speed across the training set). The
        SHAP values explain the **speed** prediction; recover the contribution
        to hours analytically via ``hours = units / speed``.
    artifact_dir
        Where to find ``model.cbm`` / lookups / ``meta.json``. Defaults to
        ``services/node_cost_ml/artifacts/``.
    loaded
        Optionally pass a pre-loaded :class:`LoadedModel` (avoids re-reading
        artefacts when calling repeatedly in a hot loop).

    Returns
    -------
    The input DataFrame augmented with:
        ``predicted_speed_uds_per_hour``  Estimated effective speed.
        ``predicted_hours``               ``units_produced / predicted_speed`` — the node cost.
        ``train_median_speed_uds_per_hour``  The baseline lookup the model started from.
        ``shap_*`` columns                 (only when ``include_shap=True``).
    """
    _validate(inputs)
    lm = loaded or load_artefacts(artifact_dir)

    work = inputs.copy()
    work = _join_sku_attrs(work)
    work = _attach_speed_feature(work, lm)
    X = _build_features(work, lm)

    pool = Pool(X, cat_features=lm.cat_idx)
    speed_pred = np.clip(lm.model.predict(pool), 1.0, None)

    work["predicted_speed_uds_per_hour"] = speed_pred
    work["predicted_hours"] = work["units_produced"].values / speed_pred

    if include_shap:
        shap = lm.model.get_feature_importance(pool, type="ShapValues")
        # CatBoost returns shape (n, n_features + 1). Last column is the base
        # (expected value across training set).
        for i, feat in enumerate(lm.feature_cols):
            work[f"shap_{feat}"] = shap[:, i]
        work["shap_base_value"] = shap[:, -1]

    return work


def _smoke_test() -> pd.DataFrame:
    """CLI smoke test: predict on a few hand-picked rows from wo_master."""
    wo = pd.read_csv(DATA_DIR / "wo_master.csv")
    sample = (
        wo[wo["wo_kind"] == "production"][["wo_id", "line_id", "sku_id", "units_produced", "productive_hours"]]
        .dropna()
        .sample(8, random_state=0)
        .reset_index(drop=True)
    )
    out = predict_node_cost(sample, include_shap=True)
    cols = [
        "wo_id", "line_id", "sku_id", "units_produced",
        "productive_hours", "predicted_hours",
        "predicted_speed_uds_per_hour", "train_median_speed_uds_per_hour",
    ]
    print(out[cols].to_string(index=False))
    return out


if __name__ == "__main__":
    _smoke_test()
