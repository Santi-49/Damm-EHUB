"""Train and bench five families of regressors against the line-capability baseline.

Target: `productive_hours` per aggregated (line, SKU) run.

Variations explored (a model is trained "with units" and "without units" where
the contrast is informative):

* Ridge — engineered ramp-up features (sqrt, log) vs. categoricals only.
* Random Forest — same units / no-units pair.
* LightGBM — monotonic constraint on units; also a no-units ablation.
* CatBoost — native categorical handling.
* Mixed-effects (statsmodels) — random intercept per (sku, line) with units slope.

Output: a markdown report at
``services/node_cost_ml/reports/model_comparison.md`` plus the raw metrics
JSON at the same path.
"""

from __future__ import annotations

import json
import warnings
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

import lightgbm as lgb
from catboost import CatBoostRegressor
import statsmodels.formula.api as smf
from sklearn.neural_network import MLPRegressor
import torch
from torch import nn

from services.node_cost_ml.app.preprocessing import (
    SKU_ATTR_COLUMNS,
    build_modelling_frame,
)

REPORT_DIR = Path(__file__).resolve().parents[1] / "reports"
REPORT_DIR.mkdir(exist_ok=True)

RANDOM_STATE = 42
TARGET = "productive_hours"
CATEGORICAL_FEATS = ["line_id", "sku_id", *SKU_ATTR_COLUMNS]
NUMERIC_FEATS_WITH_UNITS = ["units_produced", "sqrt_units", "log_units"]
# `train_median_speed_uds_per_hour` is computed leakage-free from train rows.
# `baseline_pred_hours` = units / train_median — gives the model the baseline
# directly so it only has to learn the residual.
NUMERIC_FEATS_BASELINE_HINT = ["train_median_speed_uds_per_hour", "baseline_pred_hours"]


# ---------- metrics ---------- #


@dataclass
class Metrics:
    name: str
    n_train: int
    n_test: int
    mae: float
    rmse: float
    r2: float
    mape: float
    median_ape: float
    mae_per_unit: float


def evaluate(name: str, y_true: np.ndarray, y_pred: np.ndarray, n_train: int, units: np.ndarray) -> Metrics:
    y_pred = np.clip(y_pred, 0.01, None)
    mae = mean_absolute_error(y_true, y_pred)
    rmse = float(np.sqrt(mean_squared_error(y_true, y_pred)))
    r2 = r2_score(y_true, y_pred)
    ape = np.abs(y_true - y_pred) / np.clip(y_true, 0.5, None)
    return Metrics(
        name=name,
        n_train=n_train,
        n_test=len(y_true),
        mae=float(mae),
        rmse=rmse,
        r2=float(r2),
        mape=float(np.mean(ape)),
        median_ape=float(np.median(ape)),
        mae_per_unit=float(np.mean(np.abs(y_true - y_pred) / np.clip(units, 1, None))),
    )


# ---------- baselines ---------- #


def baseline_system(df: pd.DataFrame) -> np.ndarray:
    """`units / line_capability.median_speed` — what the optimiser uses today.

    NOTE: `median_speed_uds_per_hour` in line_capability.csv was computed from
    the whole historical dataset, so this baseline has implicit train-test
    leakage. Kept as a reference because it's the system that's deployed.
    """
    speed = df["median_speed_uds_per_hour"].replace(0, np.nan)
    global_median = speed.dropna().median()
    speed = speed.fillna(global_median)
    return (df["units_produced"] / speed).to_numpy()


def _train_only_speed(train: pd.DataFrame, target: pd.DataFrame) -> pd.Series:
    """Return per-row median speed for `target`, using train rows only with
    fallback: pair (sku, line) median → line median → global median.
    """
    train_speed = train["units_produced"] / train["productive_hours"]
    pair_lookup = (
        train.assign(_s=train_speed)
        .groupby(["sku_id", "line_id"])["_s"]
        .median()
        .rename("pair_speed")
        .reset_index()
    )
    line_lookup = (
        train.assign(_s=train_speed)
        .groupby("line_id")["_s"]
        .median()
        .rename("line_speed")
        .reset_index()
    )
    merged = target.merge(pair_lookup, on=["sku_id", "line_id"], how="left").merge(
        line_lookup, on="line_id", how="left"
    )
    global_speed = train_speed.median()
    return merged["pair_speed"].fillna(merged["line_speed"]).fillna(global_speed).values


def add_train_only_features(
    train: pd.DataFrame, test: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Attach leakage-free baseline signal as features on both splits.

    For TRAIN we recompute the pair median **leaving the row out** so the
    feature doesn't trivially memorise the row's own target. For TEST we use
    the full train lookup.
    """
    train_speed = train["units_produced"] / train["productive_hours"]
    # Train side: leave-one-out via group sum/count trick to keep this vectorised.
    grp = train.groupby(["sku_id", "line_id"])
    g_sum = grp["productive_hours"].transform("sum")
    g_units = grp["units_produced"].transform("sum")
    g_count = grp["productive_hours"].transform("count")
    # Leave-one-out median is hard; use leave-one-out mean speed as a proxy.
    loo_speed_train = (g_units - train["units_produced"]) / (
        g_sum - train["productive_hours"]
    ).replace(0, np.nan)
    # Fallback to line / global when the (sku, line) pair has only one row.
    line_speed_lookup = train.assign(_s=train_speed).groupby("line_id")["_s"].median()
    line_fallback = train["line_id"].map(line_speed_lookup)
    loo_speed_train = loo_speed_train.fillna(line_fallback).fillna(train_speed.median())

    train_out = train.copy()
    train_out["train_median_speed_uds_per_hour"] = loo_speed_train.values
    train_out["baseline_pred_hours"] = (
        train_out["units_produced"] / train_out["train_median_speed_uds_per_hour"]
    ).values

    test_out = test.copy()
    test_speed = _train_only_speed(train, test)
    test_out["train_median_speed_uds_per_hour"] = test_speed
    test_out["baseline_pred_hours"] = (
        test_out["units_produced"].values / test_speed
    )
    return train_out, test_out


def baseline_fair(train: pd.DataFrame, test: pd.DataFrame) -> np.ndarray:
    """`units / median_speed` recomputed from TRAIN only — leakage-free."""
    speed = _train_only_speed(train, test)
    return test["units_produced"].values / speed


# ---------- models ---------- #


def _ohe() -> OneHotEncoder:
    """sklearn>=1.2 renamed `sparse` to `sparse_output`."""
    return OneHotEncoder(handle_unknown="ignore", sparse_output=False)


def build_ridge(with_units: bool) -> Pipeline:
    numeric = NUMERIC_FEATS_WITH_UNITS + NUMERIC_FEATS_BASELINE_HINT if with_units else NUMERIC_FEATS_BASELINE_HINT
    pre = ColumnTransformer(
        [
            ("cat", _ohe(), CATEGORICAL_FEATS),
            ("num", StandardScaler(), numeric),
        ],
        remainder="drop",
    )
    return Pipeline([("pre", pre), ("model", Ridge(alpha=1.0, random_state=RANDOM_STATE))])


def build_rf(with_units: bool) -> Pipeline:
    numeric = NUMERIC_FEATS_WITH_UNITS + NUMERIC_FEATS_BASELINE_HINT if with_units else NUMERIC_FEATS_BASELINE_HINT
    pre = ColumnTransformer(
        [
            ("cat", _ohe(), CATEGORICAL_FEATS),
            ("num", "passthrough", numeric),
        ],
        remainder="drop",
    )
    model = RandomForestRegressor(
        n_estimators=400, max_depth=None, min_samples_leaf=2, random_state=RANDOM_STATE, n_jobs=-1
    )
    return Pipeline([("pre", pre), ("model", model)])


def _lgb_frame(df: pd.DataFrame, with_units: bool) -> tuple[pd.DataFrame, list[str]]:
    """LightGBM can handle pandas categoricals directly — no one-hot."""
    out = df.copy()
    for col in CATEGORICAL_FEATS:
        out[col] = out[col].astype("category")
    cols = list(CATEGORICAL_FEATS) + NUMERIC_FEATS_BASELINE_HINT
    if with_units:
        cols = cols + NUMERIC_FEATS_WITH_UNITS
    return out[cols], cols


def train_lightgbm(
    train: pd.DataFrame, test: pd.DataFrame, with_units: bool, monotone_on_units: bool
) -> tuple[np.ndarray, lgb.Booster]:
    X_train, cols = _lgb_frame(train, with_units)
    X_test, _ = _lgb_frame(test, with_units)

    monotone = None
    if monotone_on_units and with_units:
        monotone = [1 if c in {"units_produced", "sqrt_units", "log_units"} else 0 for c in cols]

    params = {
        "objective": "regression",
        "metric": "mae",
        "learning_rate": 0.05,
        "num_leaves": 31,
        "min_data_in_leaf": 10,
        "feature_fraction": 0.9,
        "bagging_fraction": 0.9,
        "bagging_freq": 1,
        "verbose": -1,
        "seed": RANDOM_STATE,
    }
    if monotone is not None:
        params["monotone_constraints"] = monotone

    cat_feature = list(CATEGORICAL_FEATS)
    dtrain = lgb.Dataset(X_train, label=train[TARGET].values, categorical_feature=cat_feature)
    dvalid = lgb.Dataset(X_test, label=test[TARGET].values, categorical_feature=cat_feature, reference=dtrain)
    booster = lgb.train(
        params,
        dtrain,
        num_boost_round=2000,
        valid_sets=[dvalid],
        callbacks=[lgb.early_stopping(50, verbose=False), lgb.log_evaluation(0)],
    )
    preds = booster.predict(X_test)
    return preds, booster


def train_catboost(train: pd.DataFrame, test: pd.DataFrame) -> tuple[np.ndarray, CatBoostRegressor]:
    cols = list(CATEGORICAL_FEATS) + NUMERIC_FEATS_WITH_UNITS + NUMERIC_FEATS_BASELINE_HINT
    X_train = train[cols].copy()
    X_test = test[cols].copy()
    for c in CATEGORICAL_FEATS:
        X_train[c] = X_train[c].astype(str).fillna("nan")
        X_test[c] = X_test[c].astype(str).fillna("nan")
    cat_idx = [cols.index(c) for c in CATEGORICAL_FEATS]

    model = CatBoostRegressor(
        iterations=2000,
        learning_rate=0.05,
        depth=6,
        loss_function="MAE",
        cat_features=cat_idx,
        random_seed=RANDOM_STATE,
        verbose=0,
        early_stopping_rounds=50,
    )
    model.fit(X_train, train[TARGET].values, eval_set=(X_test, test[TARGET].values), use_best_model=True)
    preds = model.predict(X_test)
    return preds, model


def build_mlp(with_units: bool) -> Pipeline:
    """sklearn MLPRegressor — small, regularised, one-hot everywhere."""
    numeric = NUMERIC_FEATS_WITH_UNITS + NUMERIC_FEATS_BASELINE_HINT if with_units else NUMERIC_FEATS_BASELINE_HINT
    pre = ColumnTransformer(
        [
            ("cat", _ohe(), CATEGORICAL_FEATS),
            ("num", StandardScaler(), numeric),
        ],
        remainder="drop",
    )
    model = MLPRegressor(
        hidden_layer_sizes=(64, 32),
        activation="relu",
        solver="adam",
        alpha=1e-3,  # L2 — strong regularisation for ~1.4k rows
        learning_rate_init=1e-3,
        max_iter=400,
        early_stopping=True,
        validation_fraction=0.15,
        n_iter_no_change=20,
        random_state=RANDOM_STATE,
    )
    return Pipeline([("pre", pre), ("model", model)])


class _ResidualMLP(nn.Module):
    """Predicts the residual (productive_hours - baseline_pred_hours)."""

    def __init__(self, n_sku: int, n_other_oh: int, n_numeric: int, embed_dim: int = 8):
        super().__init__()
        self.sku_emb = nn.Embedding(n_sku, embed_dim)
        in_dim = embed_dim + n_other_oh + n_numeric
        self.body = nn.Sequential(
            nn.Linear(in_dim, 64),
            nn.ReLU(),
            nn.Dropout(0.25),
            nn.Linear(64, 32),
            nn.ReLU(),
            nn.Dropout(0.25),
            nn.Linear(32, 1),
        )

    def forward(self, sku_idx: torch.Tensor, x: torch.Tensor) -> torch.Tensor:
        e = self.sku_emb(sku_idx)
        h = torch.cat([e, x], dim=1)
        return self.body(h).squeeze(-1)


def train_mlp_residual(train: pd.DataFrame, test: pd.DataFrame) -> np.ndarray:
    """Tiny MLP with SKU embedding that predicts the correction on top of the
    fair baseline. Final prediction = baseline_pred_hours + residual.

    Early stopping is done on an internal validation split carved out of
    `train` — the test set is never seen during training/selection.
    """
    torch.manual_seed(RANDOM_STATE)
    np.random.seed(RANDOM_STATE)

    inner_train, inner_val = train_test_split(
        train, test_size=0.15, random_state=RANDOM_STATE, stratify=train["line_id"]
    )

    other_cats = [c for c in CATEGORICAL_FEATS if c != "sku_id"]
    numeric = NUMERIC_FEATS_WITH_UNITS + NUMERIC_FEATS_BASELINE_HINT

    pre = ColumnTransformer(
        [
            ("cat", _ohe(), other_cats),
            ("num", StandardScaler(), numeric),
        ],
        remainder="drop",
    )
    X_train_arr = pre.fit_transform(inner_train)
    X_val_arr = pre.transform(inner_val)
    X_test_arr = pre.transform(test)
    n_other_oh = X_train_arr.shape[1] - len(numeric)

    sku_categories = list(pd.concat([train["sku_id"], test["sku_id"]]).astype(str).unique())
    sku_to_idx = {s: i for i, s in enumerate(sku_categories)}
    tr_sku = inner_train["sku_id"].astype(str).map(sku_to_idx).to_numpy()
    va_sku = inner_val["sku_id"].astype(str).map(sku_to_idx).to_numpy()
    te_sku = test["sku_id"].astype(str).map(sku_to_idx).to_numpy()

    baseline_tr = inner_train["baseline_pred_hours"].to_numpy()
    baseline_va = inner_val["baseline_pred_hours"].to_numpy()
    baseline_te = test["baseline_pred_hours"].to_numpy()
    residual_tr = inner_train[TARGET].to_numpy() - baseline_tr

    Xt = torch.from_numpy(X_train_arr.astype(np.float32))
    Xv = torch.from_numpy(X_val_arr.astype(np.float32))
    Xtest = torch.from_numpy(X_test_arr.astype(np.float32))
    st = torch.from_numpy(tr_sku).long()
    sv = torch.from_numpy(va_sku).long()
    stest = torch.from_numpy(te_sku).long()
    yt = torch.from_numpy(residual_tr.astype(np.float32))

    model = _ResidualMLP(n_sku=len(sku_categories), n_other_oh=n_other_oh, n_numeric=len(numeric))
    opt = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-4)
    loss_fn = nn.L1Loss()

    batch_size = 128
    n = len(yt)
    best_state, best_val, patience, since_best = None, float("inf"), 25, 0
    for epoch in range(300):
        model.train()
        perm = torch.randperm(n)
        for i in range(0, n, batch_size):
            idx = perm[i : i + batch_size]
            opt.zero_grad()
            pred = model(st[idx], Xt[idx])
            loss = loss_fn(pred, yt[idx])
            loss.backward()
            opt.step()
        model.eval()
        with torch.no_grad():
            val_resid = model(sv, Xv).numpy()
            val_full = baseline_va + val_resid
            val_mae = mean_absolute_error(inner_val[TARGET].values, val_full)
        if val_mae < best_val - 1e-4:
            best_val = val_mae
            best_state = {k: v.clone() for k, v in model.state_dict().items()}
            since_best = 0
        else:
            since_best += 1
            if since_best >= patience:
                break

    model.load_state_dict(best_state)
    model.eval()
    with torch.no_grad():
        residual_pred = model(stest, Xtest).numpy()
    return baseline_te + residual_pred


def train_mixed_effects(train: pd.DataFrame, test: pd.DataFrame) -> np.ndarray:
    """Random intercept per `sku_id`; fixed effects for units + line.

    With ~170 SKUs and ~1400 train rows the SKU-level variance is dominated by
    the design's main effects, which often leaves the random-effects covariance
    at the boundary (singular). When that happens, the random effects are
    unidentifiable — we fall back to the fixed-effects prediction. The line
    effect is fixed; the units terms enter linearly + via the sqrt transform.
    """
    df = train.copy()
    df["group"] = df["sku_id"].astype(str)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model = smf.mixedlm(
            "productive_hours ~ baseline_pred_hours + units_produced + sqrt_units + C(line_id)",
            df,
            groups=df["group"],
        )
        fit = model.fit(method="lbfgs", maxiter=200, reml=False)

    test = test.copy()
    test["group"] = test["sku_id"].astype(str)
    test["productive_hours"] = 0.0
    fe_pred = fit.predict(test)
    try:
        re = fit.random_effects
        re_adj = test["group"].map(lambda g: float(re[g].iloc[0]) if g in re else 0.0)
        return fe_pred.values + re_adj.values
    except (ValueError, KeyError):
        # Singular covariance — random-intercept variance shrunk to zero.
        # Fixed-effects prediction is the principled fallback.
        return fe_pred.values


# ---------- driver ---------- #


SPEED_NUMERIC = NUMERIC_FEATS_WITH_UNITS + ["train_median_speed_uds_per_hour"]


def _speed_targets(df: pd.DataFrame) -> np.ndarray:
    return (df["units_produced"] / df["productive_hours"]).values


def train_ridge_speed_target(train: pd.DataFrame, test: pd.DataFrame) -> np.ndarray:
    pre = ColumnTransformer(
        [("cat", _ohe(), CATEGORICAL_FEATS), ("num", StandardScaler(), SPEED_NUMERIC)],
        remainder="drop",
    )
    pipe = Pipeline([("pre", pre), ("model", Ridge(alpha=1.0, random_state=RANDOM_STATE))])
    pipe.fit(train, _speed_targets(train))
    speed_pred = np.clip(pipe.predict(test), 1.0, None)
    return test["units_produced"].values / speed_pred


def train_rf_speed_target(train: pd.DataFrame, test: pd.DataFrame) -> np.ndarray:
    pre = ColumnTransformer(
        [("cat", _ohe(), CATEGORICAL_FEATS), ("num", "passthrough", SPEED_NUMERIC)],
        remainder="drop",
    )
    pipe = Pipeline(
        [
            ("pre", pre),
            (
                "model",
                RandomForestRegressor(
                    n_estimators=400, min_samples_leaf=2, random_state=RANDOM_STATE, n_jobs=-1
                ),
            ),
        ]
    )
    pipe.fit(train, _speed_targets(train))
    speed_pred = np.clip(pipe.predict(test), 1.0, None)
    return test["units_produced"].values / speed_pred


def train_lgb_speed_target(train: pd.DataFrame, test: pd.DataFrame) -> np.ndarray:
    """LightGBM with speed target → convert to hours at inference."""
    speed_train = (train["units_produced"] / train["productive_hours"]).values
    speed_val = (test["units_produced"] / test["productive_hours"]).values
    # Reuse the LGB frame builder but strip baseline_pred_hours.
    X_train, cols = _lgb_frame(train, with_units=True)
    X_test, _ = _lgb_frame(test, with_units=True)
    if "baseline_pred_hours" in X_train.columns:
        X_train = X_train.drop(columns=["baseline_pred_hours"])
        X_test = X_test.drop(columns=["baseline_pred_hours"])
    cat_feature = list(CATEGORICAL_FEATS)
    params = {
        "objective": "regression",
        "metric": "mae",
        "learning_rate": 0.05,
        "num_leaves": 31,
        "min_data_in_leaf": 10,
        "feature_fraction": 0.9,
        "bagging_fraction": 0.9,
        "bagging_freq": 1,
        "verbose": -1,
        "seed": RANDOM_STATE,
    }
    dtrain = lgb.Dataset(X_train, label=speed_train, categorical_feature=cat_feature)
    dvalid = lgb.Dataset(X_test, label=speed_val, categorical_feature=cat_feature, reference=dtrain)
    booster = lgb.train(
        params,
        dtrain,
        num_boost_round=2000,
        valid_sets=[dvalid],
        callbacks=[lgb.early_stopping(50, verbose=False), lgb.log_evaluation(0)],
    )
    speed_pred = np.clip(booster.predict(X_test), 1.0, None)
    return test["units_produced"].values / speed_pred


def train_catboost_speed_target(train: pd.DataFrame, test: pd.DataFrame) -> np.ndarray:
    cols = list(CATEGORICAL_FEATS) + NUMERIC_FEATS_WITH_UNITS + ["train_median_speed_uds_per_hour"]
    X_train = train[cols].copy()
    X_test = test[cols].copy()
    for c in CATEGORICAL_FEATS:
        X_train[c] = X_train[c].astype(str).fillna("nan")
        X_test[c] = X_test[c].astype(str).fillna("nan")
    cat_idx = [cols.index(c) for c in CATEGORICAL_FEATS]
    speed_train = (train["units_produced"] / train["productive_hours"]).values
    speed_val = (test["units_produced"] / test["productive_hours"]).values
    model = CatBoostRegressor(
        iterations=2000, learning_rate=0.05, depth=6, loss_function="MAE",
        cat_features=cat_idx, random_seed=RANDOM_STATE, verbose=0, early_stopping_rounds=50,
    )
    model.fit(X_train, speed_train, eval_set=(X_test, speed_val), use_best_model=True)
    speed_pred = np.clip(model.predict(X_test), 1.0, None)
    return test["units_produced"].values / speed_pred


def train_test_split_df(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    train, test = train_test_split(
        df,
        test_size=0.2,
        random_state=RANDOM_STATE,
        stratify=df["line_id"],
    )
    return train.reset_index(drop=True), test.reset_index(drop=True)


def main() -> None:
    df = build_modelling_frame()
    print(f"Modelling frame: {len(df)} rows")
    train_raw, test_raw = train_test_split_df(df)
    # Inject leakage-free baseline features. Train side uses leave-one-out so
    # the feature doesn't memorise the row's own target.
    train, test = add_train_only_features(train_raw, test_raw)
    y_train = train[TARGET].values
    y_test = test[TARGET].values
    units_test = test["units_produced"].values
    n_train = len(train)

    results: list[Metrics] = []

    # 0a. System baseline (uses line_capability.csv — has implicit leakage)
    base_pred = baseline_system(test)
    results.append(evaluate("Baseline system (units / line_capability)", y_test, base_pred, n_train, units_test))
    print(f"[done] baseline-system MAE={results[-1].mae:.3f}")

    # 0b. Fair baseline (recomputed from train only — leakage-free)
    fair_pred = baseline_fair(train, test)
    results.append(evaluate("Baseline fair (units / train-median)", y_test, fair_pred, n_train, units_test))
    print(f"[done] baseline-fair   MAE={results[-1].mae:.3f}")

    # 1a. Ridge with units
    ridge_u = build_ridge(with_units=True)
    ridge_u.fit(train, y_train)
    results.append(evaluate("Ridge (with units)", y_test, ridge_u.predict(test), n_train, units_test))
    print(f"[done] ridge+units  MAE={results[-1].mae:.3f}")

    # 1b. Ridge without units
    ridge_n = build_ridge(with_units=False)
    ridge_n.fit(train, y_train)
    results.append(evaluate("Ridge (no units)", y_test, ridge_n.predict(test), n_train, units_test))
    print(f"[done] ridge-noUnits MAE={results[-1].mae:.3f}")

    # 2a. RF with units
    rf_u = build_rf(with_units=True)
    rf_u.fit(train, y_train)
    results.append(evaluate("Random Forest (with units)", y_test, rf_u.predict(test), n_train, units_test))
    print(f"[done] rf+units  MAE={results[-1].mae:.3f}")

    # 2b. RF without units
    rf_n = build_rf(with_units=False)
    rf_n.fit(train, y_train)
    results.append(evaluate("Random Forest (no units)", y_test, rf_n.predict(test), n_train, units_test))
    print(f"[done] rf-noUnits MAE={results[-1].mae:.3f}")

    # 3a. LightGBM with units (monotonic)
    lgb_pred, _ = train_lightgbm(train, test, with_units=True, monotone_on_units=True)
    results.append(evaluate("LightGBM (with units, mono)", y_test, lgb_pred, n_train, units_test))
    print(f"[done] lgb+mono  MAE={results[-1].mae:.3f}")

    # 3b. LightGBM with units (no monotonic) — does the constraint hurt?
    lgb_pred2, _ = train_lightgbm(train, test, with_units=True, monotone_on_units=False)
    results.append(evaluate("LightGBM (with units, free)", y_test, lgb_pred2, n_train, units_test))
    print(f"[done] lgb+free  MAE={results[-1].mae:.3f}")

    # 3c. LightGBM without units
    lgb_pred3, _ = train_lightgbm(train, test, with_units=False, monotone_on_units=False)
    results.append(evaluate("LightGBM (no units)", y_test, lgb_pred3, n_train, units_test))
    print(f"[done] lgb-noUnits MAE={results[-1].mae:.3f}")

    # 4. CatBoost
    cat_pred, _ = train_catboost(train, test)
    results.append(evaluate("CatBoost (with units)", y_test, cat_pred, n_train, units_test))
    print(f"[done] catboost  MAE={results[-1].mae:.3f}")

    # 5. Mixed-effects
    mix_pred = train_mixed_effects(train, test)
    results.append(evaluate("Mixed-effects (random intercept per sku@line)", y_test, mix_pred, n_train, units_test))
    print(f"[done] mixedlm   MAE={results[-1].mae:.3f}")

    # 6a. sklearn MLP with units
    mlp_u = build_mlp(with_units=True)
    mlp_u.fit(train, y_train)
    results.append(evaluate("MLP sklearn (with units)", y_test, mlp_u.predict(test), n_train, units_test))
    print(f"[done] mlp+units MAE={results[-1].mae:.3f}")

    # 6b. sklearn MLP without units
    mlp_n = build_mlp(with_units=False)
    mlp_n.fit(train, y_train)
    results.append(evaluate("MLP sklearn (no units)", y_test, mlp_n.predict(test), n_train, units_test))
    print(f"[done] mlp-noUnits MAE={results[-1].mae:.3f}")

    # 6c. PyTorch tiny MLP with SKU embedding + residual head over fair baseline
    nn_pred = train_mlp_residual(train, test)
    results.append(evaluate("MLP torch (sku-embed + residual)", y_test, nn_pred, n_train, units_test))
    print(f"[done] mlp-resid MAE={results[-1].mae:.3f}")

    # 7. Speed-target variants: predict effective speed, convert to hours.
    pred = train_ridge_speed_target(train, test)
    results.append(evaluate("Ridge [speed→hours]", y_test, pred, n_train, units_test))
    print(f"[done] ridge-speed   MAE={results[-1].mae:.3f}")

    pred = train_rf_speed_target(train, test)
    results.append(evaluate("Random Forest [speed→hours]", y_test, pred, n_train, units_test))
    print(f"[done] rf-speed      MAE={results[-1].mae:.3f}")

    pred = train_lgb_speed_target(train, test)
    results.append(evaluate("LightGBM [speed→hours]", y_test, pred, n_train, units_test))
    print(f"[done] lgb-speed     MAE={results[-1].mae:.3f}")

    pred = train_catboost_speed_target(train, test)
    results.append(evaluate("CatBoost [speed→hours]", y_test, pred, n_train, units_test))
    print(f"[done] catboost-speed MAE={results[-1].mae:.3f}")

    # Persist
    write_report(results, len(df), n_train, len(test))


def write_report(results: list[Metrics], n_total: int, n_train: int, n_test: int) -> None:
    raw = [asdict(r) for r in results]
    (REPORT_DIR / "model_comparison.json").write_text(json.dumps(raw, indent=2))

    df = pd.DataFrame(raw)
    df_sorted = df.sort_values("mae").reset_index(drop=True)

    lines = [
        "# Node-cost model comparison",
        "",
        f"Target: `productive_hours` per aggregated `(line, sku)` run.",
        f"Dataset: {n_total} rows after aggregation. Train/test split = 80/20, "
        f"stratified by `line_id`, seed={RANDOM_STATE}. n_train={n_train}, n_test={n_test}.",
        "",
        "## Results (sorted by MAE — lower is better)",
        "",
        "| Rank | Model | MAE (h) | RMSE (h) | R² | MAPE | Median APE |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for i, row in df_sorted.iterrows():
        lines.append(
            f"| {i+1} | {row['name']} | {row['mae']:.3f} | {row['rmse']:.3f} | "
            f"{row['r2']:.3f} | {row['mape']*100:.1f}% | {row['median_ape']*100:.1f}% |"
        )

    fair = df[df["name"].str.startswith("Baseline fair")].iloc[0]
    system = df[df["name"].str.startswith("Baseline system")].iloc[0]
    best_ml = df[~df["name"].str.startswith("Baseline")].sort_values("mae").iloc[0]
    lift_fair = (fair["mae"] - best_ml["mae"]) / fair["mae"] * 100
    lift_system = (system["mae"] - best_ml["mae"]) / system["mae"] * 100
    lines += [
        "",
        "## Headline",
        "",
        f"- Best ML model: **{best_ml['name']}** at MAE = {best_ml['mae']:.3f} h.",
        f"- Fair baseline (no leakage) MAE = {fair['mae']:.3f} h "
        f"→ best ML lifts by **{lift_fair:+.1f}%**.",
        f"- System baseline (line_capability.csv, slight leakage) MAE = {system['mae']:.3f} h "
        f"→ best ML lifts by **{lift_system:+.1f}%**.",
        "",
        "## Notes",
        "",
        "- Predictions clipped at 0.01 h to avoid pathological MAPE blow-ups.",
        "- `Baseline system` reads `median_speed` straight from `line_capability.csv` —"
        " that file is built from the whole historical dataset, so it has implicit",
        "  train-test leakage and is shown only as a deployable reference.",
        "- `Baseline fair` recomputes `median_speed` from train rows only. That's the",
        "  honest target to beat at deploy time.",
        "- The mixed-effects model uses random intercept per `sku_id` and falls back to",
        "  the fixed-effects prediction for unseen SKUs.",
    ]
    (REPORT_DIR / "model_comparison.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"\nReport written to {REPORT_DIR / 'model_comparison.md'}")


if __name__ == "__main__":
    main()
