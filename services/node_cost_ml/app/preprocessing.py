"""Preprocessing for the node-cost model.

Loads `wo_master`, joins `skus`, aggregates consecutive same-SKU work orders on
each line into a single "run" (the granularity at which the optimiser queries
node cost), and emits a clean modelling frame.

Target is `productive_hours` — pure machine-running time of the run, ramp-up
included implicitly via the per-run speed signal. Within-run inefficiencies
(downtime, idle, low-speed, cleaning, maintenance) are handled by the
simulator via incident replay, not by this model.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "clean"

SKU_ATTR_COLUMNS = (
    "container_type",
    "brand",
    "family",
    "beer",
    "primary_packaging",
    "secondary_packaging",
    "pallet_type",
    "units_per_case",
)


def load_raw() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    wo = pd.read_csv(DATA_DIR / "wo_master.csv")
    skus = pd.read_csv(DATA_DIR / "skus.csv")
    cap = pd.read_csv(DATA_DIR / "line_capability.csv")
    return wo, skus, cap


def filter_production(wo: pd.DataFrame) -> pd.DataFrame:
    """Apply the gates documented in `docs/data/node_cost_train.md`."""
    out = wo[wo["wo_kind"] == "production"].copy()
    out = out[out["productive_hours"] >= 0.5]
    out = out[(out["oee"].isna()) | (out["oee"] <= 1.2)]
    return out


def aggregate_consecutive_same_sku(wo: pd.DataFrame) -> pd.DataFrame:
    """Collapse consecutive same-SKU WOs on each line into a single row.

    The optimiser treats one (sku, line) chunk as one node — training rows must
    match that granularity, otherwise ramp-up is artificially repeated.
    """
    df = wo.sort_values(["line_id", "line_sequence_order"]).copy()
    sku_changed = (df.groupby("line_id")["sku_id"].shift() != df["sku_id"]).astype(int)
    df["run_id"] = sku_changed.groupby(df["line_id"]).cumsum()
    grouped = df.groupby(["line_id", "run_id"], as_index=False).agg(
        sku_id=("sku_id", "first"),
        units_produced=("units_produced", "sum"),
        total_hours=("total_hours", "sum"),
        productive_hours=("productive_hours", "sum"),
        n_wos_in_run=("wo_id", "count"),
    )
    return grouped


def join_features(
    runs: pd.DataFrame, skus: pd.DataFrame, cap: pd.DataFrame
) -> pd.DataFrame:
    runs = runs.merge(
        skus[["sku_id", *SKU_ATTR_COLUMNS]], on="sku_id", how="left"
    )
    runs = runs.merge(
        cap[["sku_id", "line_id", "median_speed_uds_per_hour"]],
        on=["sku_id", "line_id"],
        how="left",
    )
    return runs


def build_modelling_frame() -> pd.DataFrame:
    wo, skus, cap = load_raw()
    prod = filter_production(wo)
    runs = aggregate_consecutive_same_sku(prod)
    runs = join_features(runs, skus, cap)
    runs = runs[runs["productive_hours"] >= 0.5].copy()
    runs = runs[runs["units_produced"] > 0].copy()
    runs["sqrt_units"] = np.sqrt(runs["units_produced"])
    runs["log_units"] = np.log1p(runs["units_produced"])
    return runs.reset_index(drop=True)


if __name__ == "__main__":
    df = build_modelling_frame()
    print(f"Rows after aggregation: {len(df)}")
    print(df[["line_id", "sku_id", "units_produced", "total_hours", "n_wos_in_run"]].head())
    print("\nPer-line summary:")
    print(df.groupby("line_id")[["units_produced", "total_hours", "n_wos_in_run"]].describe().T)
