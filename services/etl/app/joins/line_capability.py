"""Build line_capability.csv from wo_master and skus.

The table is the optimizer's hard production gate and node-cost fallback. A SKU
can run on a line when its container format is allowed by that line. Historical
observations provide medians; format-compatible but unseen pairs receive a
conservative same-SKU fallback so the optimizer can still consider them.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


ALLOWED_CONTAINER_TYPES: dict[int, set[str]] = {
    14: {"1/2", "1/3"},
    17: {"1/3"},
    19: {"1/2", "1/3", "2/5"},
}

LINE_CAPABILITY_COLS: list[str] = [
    "sku_id",
    "line_id",
    "can_produce",
    "median_speed_uds_per_hour",
    "median_oee",
    "n_workorders_observed",
]

_FALLBACK_PENALTY = 0.90


def build_line_capability(
    wo_master: pd.DataFrame,
    skus: pd.DataFrame,
) -> tuple[pd.DataFrame, list[str]]:
    """Build one row per ``(sku_id, line_id)`` capability pair."""
    warnings: list[str] = []
    work = wo_master.copy()
    sku_work = skus.copy()

    required_wm = {
        "sku_id", "line_id", "wo_kind", "units_produced", "productive_hours", "oee",
    }
    missing_wm = sorted(required_wm - set(work.columns))
    if missing_wm:
        raise KeyError(f"wo_master missing line_capability columns: {missing_wm}")

    required_skus = {"sku_id", "container_type"}
    missing_skus = sorted(required_skus - set(sku_work.columns))
    if missing_skus:
        raise KeyError(f"skus missing line_capability columns: {missing_skus}")

    production = work[work["wo_kind"].astype(str).eq("production")].copy()
    production["line_id"] = pd.to_numeric(production["line_id"], errors="coerce").astype("Int64")
    production["units_produced"] = pd.to_numeric(production["units_produced"], errors="coerce")
    production["productive_hours"] = pd.to_numeric(production["productive_hours"], errors="coerce")
    production["oee"] = pd.to_numeric(production["oee"], errors="coerce")

    valid_speed = (
        production["units_produced"].notna()
        & production["units_produced"].gt(0)
        & production["productive_hours"].notna()
        & production["productive_hours"].gt(0)
    )
    production["speed_uds_per_hour"] = pd.NA
    production.loc[valid_speed, "speed_uds_per_hour"] = (
        production.loc[valid_speed, "units_produced"]
        / production.loc[valid_speed, "productive_hours"]
    )
    production["speed_uds_per_hour"] = pd.to_numeric(
        production["speed_uds_per_hour"], errors="coerce"
    )

    observed = (
        production.groupby(["sku_id", "line_id"], as_index=False)
        .agg(
            n_workorders_observed=("sku_id", "size"),
            median_speed_uds_per_hour=("speed_uds_per_hour", "median"),
            median_oee=("oee", "median"),
        )
    )

    sku_defaults = _sku_defaults(observed)
    line_format_defaults = _line_format_defaults(production, sku_work)
    global_defaults = _global_defaults(production)

    rows: list[dict[str, object]] = []
    for sku in sku_work.sort_values("sku_id").itertuples(index=False):
        sku_id = str(getattr(sku, "sku_id"))
        container_type = getattr(sku, "container_type")
        for line_id in sorted(ALLOWED_CONTAINER_TYPES):
            allowed = _is_allowed(line_id, container_type)
            stats = observed[
                observed["sku_id"].eq(sku_id) & observed["line_id"].eq(line_id)
            ]

            if stats.empty:
                n_observed = 0
                speed = pd.NA
                oee = pd.NA
            else:
                stat = stats.iloc[0]
                n_observed = int(stat["n_workorders_observed"])
                speed = stat["median_speed_uds_per_hour"]
                oee = stat["median_oee"]

            if not allowed and n_observed > 0:
                warnings.append(
                    "capability_history_violates_format: "
                    f"sku_id={sku_id}, line_id={line_id}, container_type={container_type}"
                )

            if allowed and (_missing(speed) or _missing(oee)):
                speed, oee, source = _fallback_values(
                    sku_id=sku_id,
                    line_id=line_id,
                    container_type=container_type,
                    sku_defaults=sku_defaults,
                    line_format_defaults=line_format_defaults,
                    global_defaults=global_defaults,
                )
                warning_name = "capability_format_only" if n_observed == 0 else "capability_metric_fallback"
                warnings.append(
                    f"{warning_name}: sku_id={sku_id}, line_id={line_id}, source={source}"
                )

            rows.append({
                "sku_id": sku_id,
                "line_id": line_id,
                "can_produce": bool(allowed),
                "median_speed_uds_per_hour": round(float(speed)) if allowed and not _missing(speed) else pd.NA,
                "median_oee": round(float(oee), 6) if allowed and not _missing(oee) else pd.NA,
                "n_workorders_observed": n_observed,
            })

    out = pd.DataFrame(rows, columns=LINE_CAPABILITY_COLS)
    out["line_id"] = out["line_id"].astype("int64")
    out["n_workorders_observed"] = out["n_workorders_observed"].astype("int64")
    return out, warnings


def _sku_defaults(observed: pd.DataFrame) -> dict[str, dict[str, object]]:
    defaults: dict[str, dict[str, object]] = {}
    valid = observed.dropna(subset=["median_speed_uds_per_hour", "median_oee"]).copy()
    if valid.empty:
        return defaults

    valid = valid.sort_values(
        ["sku_id", "n_workorders_observed", "median_speed_uds_per_hour"],
        ascending=[True, False, False],
    )
    for row in valid.drop_duplicates("sku_id", keep="first").itertuples(index=False):
        defaults[str(row.sku_id)] = {
            "speed": float(row.median_speed_uds_per_hour) * _FALLBACK_PENALTY,
            "oee": float(row.median_oee) * _FALLBACK_PENALTY,
            "source": f"same_sku_line_{int(row.line_id)}_penalty",
        }
    return defaults


def _line_format_defaults(
    production: pd.DataFrame,
    skus: pd.DataFrame,
) -> dict[tuple[int, str], dict[str, object]]:
    joined = production.merge(
        skus[["sku_id", "container_type"]],
        on="sku_id",
        how="left",
    )
    grouped = (
        joined.dropna(subset=["container_type", "speed_uds_per_hour", "oee"])
        .groupby(["line_id", "container_type"], as_index=False)
        .agg(
            speed=("speed_uds_per_hour", "median"),
            oee=("oee", "median"),
        )
    )

    defaults: dict[tuple[int, str], dict[str, object]] = {}
    for row in grouped.itertuples(index=False):
        defaults[(int(row.line_id), str(row.container_type))] = {
            "speed": float(row.speed) * _FALLBACK_PENALTY,
            "oee": float(row.oee) * _FALLBACK_PENALTY,
            "source": "line_format_penalty",
        }
    return defaults


def _global_defaults(production: pd.DataFrame) -> dict[str, object]:
    valid = production.dropna(subset=["speed_uds_per_hour", "oee"])
    if valid.empty:
        return {"speed": pd.NA, "oee": pd.NA, "source": "missing"}
    return {
        "speed": float(valid["speed_uds_per_hour"].median()) * _FALLBACK_PENALTY,
        "oee": float(valid["oee"].median()) * _FALLBACK_PENALTY,
        "source": "global_penalty",
    }


def _fallback_values(
    sku_id: str,
    line_id: int,
    container_type: object,
    sku_defaults: dict[str, dict[str, object]],
    line_format_defaults: dict[tuple[int, str], dict[str, object]],
    global_defaults: dict[str, object],
) -> tuple[object, object, object]:
    if sku_id in sku_defaults:
        row = sku_defaults[sku_id]
    elif (line_id, str(container_type)) in line_format_defaults:
        row = line_format_defaults[(line_id, str(container_type))]
    else:
        row = global_defaults
    return row["speed"], row["oee"], row["source"]


def _is_allowed(line_id: int, container_type: object) -> bool:
    if _missing(container_type):
        return False
    return str(container_type).strip() in ALLOWED_CONTAINER_TYPES[line_id]


def _missing(value: object) -> bool:
    if pd.isna(value):
        return True
    return str(value).strip().lower() in {"", "nan", "none", "null", "-", "n/a"}


def _cli() -> None:
    from services.etl.app.joins.skus import build_skus
    from services.etl.app.joins.wo_master import build_wo_master
    from services.etl.app.parsers.mantenimiento import parse_mantenimiento
    from services.etl.app.parsers.oee import parse_oee
    from services.etl.app.parsers.tiempo import parse_tiempo
    from services.etl.app.parsers.volumen import parse_volumen

    parser = argparse.ArgumentParser(description="Build line_capability.csv")
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

    print("Building dependencies...")
    wo_master, wo_warnings = build_wo_master(oee_df, tiempo_df, volumen_df, mant_df)
    skus, skus_warnings = build_skus(oee_df)

    print("Building line_capability...")
    capability, warnings = build_line_capability(wo_master, skus)
    out_path = out / "line_capability.csv"
    capability.to_csv(out_path, index=False)

    all_warnings = [*wo_warnings, *skus_warnings, *warnings]
    print(f"Written: {out_path}  ({len(capability)} rows, {len(capability.columns)} cols)")
    if all_warnings:
        print(f"\nWarnings ({len(all_warnings)}):")
        for warning in all_warnings[:50]:
            print(f"  * {warning}")
        if len(all_warnings) > 50:
            print(f"  ... ({len(all_warnings) - 50} more)")


if __name__ == "__main__":
    _cli()
