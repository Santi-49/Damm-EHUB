"""Demand builders for services/etl.

The implemented MVP mapper turns historical production in ``wo_master.csv``
into source-agnostic demand buckets. The optimiser consumes these buckets and
decides line/day/sequence later.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from packages.contracts.module.schemas import DemandBucket, WindowConfig


DEMAND_COLS: list[str] = [
    "window_id",
    "window_start",
    "window_end",
    "sku_id",
    "units_demanded",
    "source",
    "priority",
]


def build_historical_demand(
    wo_master: pd.DataFrame,
    window: WindowConfig | None = None,
) -> tuple[pd.DataFrame, list[str]]:
    """Aggregate production WOs into demand buckets."""
    window = window or WindowConfig()
    warnings: list[str] = []

    work = wo_master.copy()
    required = {"wo_id", "sku_id", "end_day", "units_produced", "wo_kind"}
    missing = sorted(required - set(work.columns))
    if missing:
        raise KeyError(f"wo_master missing demand columns: {missing}")

    work["end_day"] = pd.to_datetime(work["end_day"], errors="coerce").dt.date
    work["units_produced"] = pd.to_numeric(work["units_produced"], errors="coerce")

    invalid_day = work["end_day"].isna()
    if invalid_day.any():
        warnings.append(f"demand_invalid_end_day: {int(invalid_day.sum())} rows dropped")

    production = work["wo_kind"].astype(str).eq("production")
    not_limpieza = work["sku_id"].astype(str).str.upper().ne("LIMPIEZA")
    valid_units = work["units_produced"].notna() & work["units_produced"].gt(0)

    invalid_units = production & not_limpieza & ~valid_units
    if invalid_units.any():
        warnings.append(f"demand_invalid_units: {int(invalid_units.sum())} production rows dropped")

    work = work[production & not_limpieza & valid_units & ~invalid_day].copy()
    if work.empty:
        return pd.DataFrame(columns=DEMAND_COLS), warnings

    window_info = work["end_day"].apply(lambda value: _window_for_day(value, window))
    work["window_id"] = window_info.apply(lambda item: item[0])
    work["window_start"] = window_info.apply(lambda item: item[1])
    work["window_end"] = window_info.apply(lambda item: item[2])

    demand = (
        work.groupby(["window_id", "window_start", "window_end", "sku_id"], as_index=False)
        .agg(units_demanded=("units_produced", "sum"))
        .sort_values(["window_start", "sku_id"])
        .reset_index(drop=True)
    )
    demand["units_demanded"] = demand["units_demanded"].round().astype("int64")
    demand["source"] = "historico_2025"
    demand["priority"] = 3

    return demand[DEMAND_COLS], warnings


def dataframe_to_buckets(demand: pd.DataFrame) -> tuple[DemandBucket, ...]:
    """Convert a demand DataFrame into contract dataclasses."""
    buckets: list[DemandBucket] = []
    for row in demand[DEMAND_COLS].itertuples(index=False):
        buckets.append(DemandBucket(
            window_id=str(row.window_id),
            window_start=_to_date(row.window_start),
            window_end=_to_date(row.window_end),
            sku_id=str(row.sku_id),
            units_demanded=int(row.units_demanded),
            source=row.source,
            priority=int(row.priority),
        ))
    return tuple(buckets)


def buckets_to_dataframe(demand: tuple[DemandBucket, ...]) -> pd.DataFrame:
    """Convert demand dataclasses into a CSV-ready DataFrame."""
    rows = [asdict(bucket) for bucket in demand]
    df = pd.DataFrame(rows, columns=DEMAND_COLS)
    if not df.empty:
        df["window_start"] = pd.to_datetime(df["window_start"]).dt.strftime("%Y-%m-%d")
        df["window_end"] = pd.to_datetime(df["window_end"]).dt.strftime("%Y-%m-%d")
    return df


def _window_for_day(value: date, window: WindowConfig) -> tuple[str, date, date]:
    if window.anchor == "monday":
        start = _monday_window_start(value, window.days)
    else:
        assert window.start_date is not None
        start = _fixed_window_start(value, window.start_date, window.days)

    end = start + timedelta(days=window.days - 1)
    return _window_id(start, window), start, end


def _monday_window_start(value: date, days: int) -> date:
    week_start = value - timedelta(days=value.weekday())
    if days == 7:
        return week_start

    epoch = date(1970, 1, 5)  # Monday.
    bucket_idx = (week_start - epoch).days // days
    return epoch + timedelta(days=bucket_idx * days)


def _fixed_window_start(value: date, start_date: date, days: int) -> date:
    bucket_idx = (value - start_date).days // days
    return start_date + timedelta(days=bucket_idx * days)


def _window_id(start: date, window: WindowConfig) -> str:
    if window.anchor == "monday" and window.days == 7:
        iso = start.isocalendar()
        return f"{iso.year}-W{iso.week:02d}-7d"
    return f"{start.isoformat()}_{window.days}d"


def _to_date(value: object) -> date:
    if isinstance(value, date):
        return value
    return pd.to_datetime(value).date()


def _cli() -> None:
    parser = argparse.ArgumentParser(description="Build demand.csv from wo_master.csv")
    parser.add_argument("--clean", default="data/clean", type=Path)
    parser.add_argument("--out", default=None, type=Path)
    parser.add_argument("--days", default=7, type=int)
    args = parser.parse_args()

    clean_dir: Path = args.clean
    out_path = args.out or (clean_dir / "demand.csv")

    wo_master = pd.read_csv(clean_dir / "wo_master.csv")
    demand, warnings = build_historical_demand(wo_master, WindowConfig(days=args.days))
    demand.to_csv(out_path, index=False)

    print(f"Written: {out_path}  ({len(demand)} rows, {len(demand.columns)} cols)")
    if warnings:
        print(f"\nWarnings ({len(warnings)}):")
        for warning in warnings:
            print(f"  * {warning}")


if __name__ == "__main__":
    _cli()
