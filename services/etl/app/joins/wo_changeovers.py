"""Build wo_changeovers.csv from wo_master, skus, Cambios and costs.

Lineage:
    wo_master production WOs -> consecutive line-local transitions
    skus.csv                 -> from/to SKU attributes
    Cambios xlsx             -> change flags / diagnostic frequency
    changeover_costs.csv     -> theoretical estimated transition time

This table is historical transition context. The authoritative transition time
used by the optimiser lives in changeover_costs.csv and is joined here as
``estimated_changeover_hours`` for analysis and UI drill-down.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from services.etl.app.parsers.cambios import FLAG_COLS

SKU_ATTR_COLS: list[str] = [
    "container_type",
    "brand",
    "beer",
    "primary_packaging",
    "secondary_packaging",
    "pallet_type",
]

WO_CHANGEOVER_COLS: list[str] = [
    "transition_id",
    "line_id",
    "transition_sequence_order",
    "transition_day",
    "day_of_week",
    "sku_from_id",
    "sku_to_id",
    "wo_from_id",
    "wo_to_id",
    "wo_to_had_changeover",
    "estimated_changeover_hours",
    "changeover_cost_source",
    "dominant_component",
    "cambios_frequency_total",
    "from_container_type",
    "to_container_type",
    "from_brand",
    "to_brand",
    "from_beer",
    "to_beer",
    "from_primary_packaging",
    "to_primary_packaging",
    "from_secondary_packaging",
    "to_secondary_packaging",
    "from_pallet_type",
    "to_pallet_type",
    "flag_brand_change",
    "flag_container_change",
    "flag_cap_change",
    "flag_primary_pack_change",
    "flag_secondary_pack_change",
    "flag_pallet_change",
    "flag_product_change",
    "flag_volume_change",
    "n_components_changed",
    "principal_change_type",
]

_FLAG_ORDER = FLAG_COLS


def build_wo_changeovers(
    wo_master: pd.DataFrame,
    skus: pd.DataFrame,
    cambios: pd.DataFrame,
    changeover_costs: pd.DataFrame,
) -> tuple[pd.DataFrame, list[str]]:
    """Build historical production transitions with estimated CF cost joined."""
    warnings: list[str] = []

    transitions = _production_transitions(wo_master)
    transitions = _join_changeover_costs(transitions, changeover_costs, warnings)
    transitions = _join_sku_attrs(transitions, skus, warnings)

    cambios_agg, cambios_warnings = _aggregate_cambios(cambios)
    warnings.extend(cambios_warnings)

    transitions = transitions.merge(
        cambios_agg,
        left_on="wo_to_id",
        right_on="wo_id",
        how="left",
        indicator=True,
    )

    missing_cambios = transitions["_merge"].eq("left_only")
    for row in transitions.loc[missing_cambios, ["transition_id", "wo_to_id"]].itertuples(index=False):
        warnings.append(
            f"wo_changeovers_missing_cambios: transition_id={row.transition_id}, "
            f"wo_to_id={row.wo_to_id}"
        )

    transitions = transitions.drop(columns=["wo_id", "_merge"])
    for col in _FLAG_ORDER:
        if col not in transitions.columns:
            transitions[col] = False
        transitions[col] = transitions[col].fillna(False).astype(bool)

    if "n_components_changed" not in transitions.columns:
        transitions["n_components_changed"] = 0
    transitions["n_components_changed"] = (
        pd.to_numeric(transitions["n_components_changed"], errors="coerce")
        .fillna(0)
        .astype("int64")
    )

    transitions["transition_day"] = pd.to_datetime(transitions["transition_day"], errors="coerce")
    transitions["day_of_week"] = transitions["transition_day"].dt.dayofweek.astype("Int64")
    transitions["transition_day"] = transitions["transition_day"].dt.strftime("%Y-%m-%d")

    return transitions[WO_CHANGEOVER_COLS].reset_index(drop=True), warnings


def _production_transitions(wo_master: pd.DataFrame) -> pd.DataFrame:
    work = wo_master.copy()
    if "line_sequence_order" not in work.columns:
        sort_cols = ["line_id", "end_day", "source_row_order", "wo_id"]
        work = work.sort_values([c for c in sort_cols if c in work.columns]).reset_index(drop=True)
        work["line_sequence_order"] = work.groupby("line_id", sort=False).cumcount() + 1

    production = (
        work[work["wo_kind"].astype(str).eq("production")]
        .sort_values(["line_id", "line_sequence_order", "wo_id"])
        .reset_index(drop=True)
    )

    previous = production.groupby("line_id", sort=False)[[
        "wo_id",
        "sku_id",
        "line_sequence_order",
    ]].shift(1)

    transitions = pd.DataFrame({
        "transition_id": production["wo_id"],
        "line_id": production["line_id"].astype("int64"),
        "transition_sequence_order": production["line_sequence_order"].astype("int64"),
        "transition_day": production["end_day"],
        "sku_from_id": previous["sku_id"],
        "sku_to_id": production["sku_id"],
        "wo_from_id": previous["wo_id"],
        "wo_to_id": production["wo_id"],
        "wo_to_had_changeover": production["had_changeover"].fillna(False).astype(bool),
    })
    transitions = transitions[transitions["wo_from_id"].notna()].copy()
    return transitions.reset_index(drop=True)


def _join_changeover_costs(
    transitions: pd.DataFrame,
    changeover_costs: pd.DataFrame,
    warnings: list[str],
) -> pd.DataFrame:
    cost_cols = [
        "line_id",
        "sku_from_id",
        "sku_to_id",
        "total_hours",
        "source",
        "dominant_component",
    ]
    costs = changeover_costs[[c for c in cost_cols if c in changeover_costs.columns]].copy()
    costs = costs.rename(columns={
        "total_hours": "estimated_changeover_hours",
        "source": "changeover_cost_source",
    })

    out = transitions.merge(
        costs,
        on=["line_id", "sku_from_id", "sku_to_id"],
        how="left",
        indicator=True,
    )

    missing = out["_merge"].eq("left_only")
    for row in out.loc[missing, ["transition_id", "line_id", "sku_from_id", "sku_to_id"]].itertuples(index=False):
        warnings.append(
            "wo_changeovers_missing_changeover_cost: "
            f"transition_id={row.transition_id}, line_id={row.line_id}, "
            f"sku_from_id={row.sku_from_id}, sku_to_id={row.sku_to_id}"
        )

    out = out.drop(columns=["_merge"])
    return out


def _join_sku_attrs(
    transitions: pd.DataFrame,
    skus: pd.DataFrame,
    warnings: list[str],
) -> pd.DataFrame:
    sku_attrs = skus[["sku_id"] + [c for c in SKU_ATTR_COLS if c in skus.columns]].copy()

    from_attrs = sku_attrs.rename(
        columns={"sku_id": "sku_from_id", **{c: f"from_{c}" for c in SKU_ATTR_COLS}}
    )
    to_attrs = sku_attrs.rename(
        columns={"sku_id": "sku_to_id", **{c: f"to_{c}" for c in SKU_ATTR_COLS}}
    )

    out = transitions.merge(from_attrs, on="sku_from_id", how="left")
    out = out.merge(to_attrs, on="sku_to_id", how="left")

    required_attr_cols = ["from_container_type", "to_container_type"]
    missing = out[required_attr_cols].isna().any(axis=1)
    for row in out.loc[missing, ["transition_id", "sku_from_id", "sku_to_id"]].itertuples(index=False):
        warnings.append(
            f"wo_changeovers_missing_sku_attrs: transition_id={row.transition_id}, "
            f"sku_from_id={row.sku_from_id}, sku_to_id={row.sku_to_id}"
        )

    return out


def _aggregate_cambios(cambios: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    warnings: list[str] = []
    work = cambios.copy()

    duplicate_counts = work["wo_id"].value_counts()
    duplicate_keys = duplicate_counts[duplicate_counts > 1]
    if not duplicate_keys.empty:
        warnings.append(
            "cambios_duplicate_wo_id: "
            f"{len(duplicate_keys)} wo_ids, {int((duplicate_keys - 1).sum())} extra rows aggregated"
        )

    for col in _FLAG_ORDER:
        if col not in work.columns:
            work[col] = pd.NA
        raw = pd.to_numeric(work[col], errors="coerce")
        non_binary = raw.notna() & ~raw.isin([0.0, 1.0])
        if non_binary.any():
            warnings.append(
                f"cambios_flag_non_binary: col={col}, rows={int(non_binary.sum())}; "
                "treated_positive_as_true"
            )
        work[col] = raw.gt(0)

    if "cambios_hours" in work.columns:
        work["cambios_frequency_total"] = pd.to_numeric(work["cambios_hours"], errors="coerce")
    else:
        work["cambios_frequency_total"] = pd.NA

    if "n_components_changed" in work.columns:
        work["n_components_changed"] = pd.to_numeric(work["n_components_changed"], errors="coerce")
    else:
        work["n_components_changed"] = pd.NA

    if "principal_change_type" not in work.columns:
        work["principal_change_type"] = pd.NA

    agg_spec = {
        "cambios_frequency_total": ("cambios_frequency_total", lambda s: s.sum(min_count=1)),
        "n_components_changed": ("n_components_changed", "max"),
        "principal_change_type": ("principal_change_type", _join_principal_types),
    }
    for col in _FLAG_ORDER:
        agg_spec[col] = (col, "max")

    aggregated = work.groupby("wo_id", as_index=False).agg(**agg_spec)
    return aggregated, warnings


def _join_principal_types(series: pd.Series) -> object:
    values: list[str] = []
    for value in series.dropna().astype(str).str.strip():
        if not value or value.lower() in {"nan", "none", "null"}:
            continue
        if value not in values:
            values.append(value)
    if not values:
        return pd.NA
    return "; ".join(values)


def _cli() -> None:
    from services.etl.app.joins.changeover_costs import build_changeover_costs
    from services.etl.app.joins.skus import build_skus
    from services.etl.app.joins.wo_master import build_wo_master
    from services.etl.app.parsers.cambios import parse_cambios
    from services.etl.app.parsers.cf_prat import parse_cf_prat
    from services.etl.app.parsers.mantenimiento import parse_mantenimiento
    from services.etl.app.parsers.oee import parse_oee
    from services.etl.app.parsers.tiempo import parse_tiempo
    from services.etl.app.parsers.volumen import parse_volumen

    parser = argparse.ArgumentParser(description="Build wo_changeovers.csv")
    parser.add_argument("--raw", default="data/raw", type=Path)
    parser.add_argument("--out", default="data/clean", type=Path)
    args = parser.parse_args()

    raw: Path = args.raw
    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)

    print("Loading source files...")
    oee_df = parse_oee(raw / "OEE 14_17_19_ 2025.xlsx")
    tiempo_df = parse_tiempo(raw / "Tiempo 14_17_19_ 2025.xlsx")
    volumen_df = parse_volumen(raw / "Volumen 14_17_19_ 2025.xlsx")
    mant_df = parse_mantenimiento(raw / "Mantenimiento 14_17_19_ 2025.xlsx")
    cambios_df = parse_cambios(raw / "Cambios 14_17_19_ 2025.xlsx")
    cf_tables = parse_cf_prat(raw / "Tabla CF Prat 2026_14_17_19.xlsx")

    print("Building dependencies...")
    wo_master, wo_warnings = build_wo_master(oee_df, tiempo_df, volumen_df, mant_df)
    skus, skus_warnings = build_skus(oee_df)
    changeover_costs, cost_warnings = build_changeover_costs(skus, cf_tables)

    print("Building wo_changeovers...")
    wo_changeovers, warnings = build_wo_changeovers(
        wo_master, skus, cambios_df, changeover_costs
    )

    out_path = out / "wo_changeovers.csv"
    wo_changeovers.to_csv(out_path, index=False)
    all_warnings = [*wo_warnings, *skus_warnings, *cost_warnings, *warnings]

    print(f"Written: {out_path}  ({len(wo_changeovers)} rows, {len(wo_changeovers.columns)} cols)")
    if all_warnings:
        print(f"\nWarnings ({len(all_warnings)}):")
        for warning in all_warnings[:50]:
            print(f"  * {warning}")
        if len(all_warnings) > 50:
            print(f"  ... ({len(all_warnings) - 50} more)")


if __name__ == "__main__":
    _cli()
