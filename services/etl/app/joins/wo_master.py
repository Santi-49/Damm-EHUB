"""Build wo_master.csv from the four parsed source DataFrames.

Steps (per cleaning_rules.md):
  1. Left-join OEE ← Tiempo ← Volumen ← Mantenimiento on wo_id
  2. Preserve date-only end_day and raw/source sequence ordering
  3. Classify wo_kind (production / cleaning / maintenance_or_rerun)
  4. Emit warnings for outliers (see catalogue in cleaning_rules §11)
  5. Select the final wo_master column set and write to out_path

Can also be run as a CLI:
    python -m services.etl.app.joins.wo_master --raw data/raw --out data/clean
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

# ── Final column order for wo_master.csv ────────────────────────────────────

WO_MASTER_COLS = [
    "wo_id", "line_id", "sku_id",
    "end_day", "source_row_order", "line_sequence_order", "total_hours",
    "productive_hours", "downtime_hours",
    "unplanned_stop_hours", "idle_hours", "low_speed_hours",
    "cleaning_hours", "cip_hours", "sterilization_hours",
    "downstream_block_hours", "upstream_starve_hours",
    "maintenance_calls", "maintenance_wait_hours", "maintenance_intervention_hours",
    "oee", "availability", "performance", "quality", "inefficiency",
    "units_produced", "hectoliters_produced",
    "had_changeover", "wo_kind",
]


# ── Public entry point ───────────────────────────────────────────────────────

def build_wo_master(
    oee: pd.DataFrame,
    tiempo: pd.DataFrame,
    volumen: pd.DataFrame,
    mantenimiento: pd.DataFrame,
) -> tuple[pd.DataFrame, list[str]]:
    """Join four source DataFrames → (wo_master DataFrame, warnings list).

    The returned DataFrame has exactly the columns in WO_MASTER_COLS that
    are present after the join (missing optional columns are silently omitted
    so the function degrades gracefully when a source file is absent).
    """
    warnings: list[str] = []

    # ── 1. Join ──────────────────────────────────────────────────────────────
    df = (
        oee
        .merge(tiempo, on="wo_id", how="left")
        .merge(volumen, on="wo_id", how="left")
        .merge(mantenimiento, on="wo_id", how="left")
    )

    n_oee = len(oee)
    n_joined = len(df)
    if n_joined != n_oee:
        # Left join should preserve all OEE rows; duplicates mean source had dupes
        warnings.append(
            f"join_row_count_mismatch: OEE={n_oee} rows, joined={n_joined} rows "
            f"(check for duplicate wo_id in Tiempo/Volumen/Mantenimiento)"
        )

    # ── 2. Date-only timing + sequence ordering ─────────────────────────────
    if "source_row_order" not in df.columns:
        df["source_row_order"] = range(len(df))
        warnings.append("wo_master_source_row_order_missing: rebuilt from joined row order")

    df["end_day"] = pd.to_datetime(df["end_ts"], errors="coerce").dt.strftime("%Y-%m-%d")
    df = df.sort_values(["line_id", "end_day", "source_row_order", "wo_id"]).reset_index(drop=True)
    df["line_sequence_order"] = df.groupby("line_id", sort=False).cumcount() + 1

    # ── 3. wo_kind classification ────────────────────────────────────────────
    df["wo_kind"] = _classify_wo_kind(df)

    # ── 4. Outlier / quality warnings ────────────────────────────────────────
    _emit_outlier_warnings(df, warnings)

    # ── 5. Select final columns ───────────────────────────────────────────────
    present = [c for c in WO_MASTER_COLS if c in df.columns]
    return df[present].reset_index(drop=True), warnings


# ── Helpers ──────────────────────────────────────────────────────────────────

def _classify_wo_kind(df: pd.DataFrame) -> pd.Series:
    """Vectorised wo_kind: production / cleaning / maintenance_or_rerun."""
    wo_id = df["wo_id"].astype(str)
    sku_id = df["sku_id"].astype(str).str.upper()

    is_prt = wo_id.str.upper().str.startswith("PRT")
    is_limpieza = sku_id == "LIMPIEZA"

    return pd.Series(
        pd.Categorical(
            ["cleaning" if (p and l)
             else "maintenance_or_rerun" if p
             else "production"
             for p, l in zip(is_prt, is_limpieza)],
            categories=["production", "cleaning", "maintenance_or_rerun"],
        ),
        index=df.index,
    )


def _emit_outlier_warnings(df: pd.DataFrame, warnings: list[str]) -> None:
    # total_hours outside [0.5, 240]
    mask = (df["total_hours"] < 0.5) | (df["total_hours"] > 240)
    for _, row in df[mask].iterrows():
        warnings.append(
            f"total_hours_outlier: wo_id={row['wo_id']}, "
            f"total_hours={row['total_hours']:.3f}"
        )

    # oee > 1
    if "oee" in df.columns:
        above = df["oee"] > 1.0
        if above.any():
            warnings.append(
                f"oee_above_one: {above.sum()} WOs, "
                f"max={df['oee'].max():.4f}"
            )

    # inefficiency < 0
    if "inefficiency" in df.columns:
        neg = df["inefficiency"] < 0
        if neg.any():
            warnings.append(
                f"inefficiency_negative: {neg.sum()} WOs, "
                f"min={df['inefficiency'].min():.4f}"
            )

    # maintenance double-count check (cleaning_rules §6)
    if all(c in df.columns for c in (
        "maintenance_calls", "maintenance_wait_hours",
        "maintenance_intervention_hours", "unplanned_stop_hours", "idle_hours",
    )):
        has_maint = df["maintenance_calls"].fillna(0) > 0
        maint_total = (
            df["maintenance_wait_hours"].fillna(0)
            + df["maintenance_intervention_hours"].fillna(0)
        )
        pnp_idle = (
            df["unplanned_stop_hours"].fillna(0)
            + df["idle_hours"].fillna(0)
        )
        double_count = has_maint & ((maint_total - pnp_idle).abs() > 0.5)
        for _, row in df[double_count].iterrows():
            warnings.append(
                f"maintenance_double_count: wo_id={row['wo_id']}"
            )


# ── CLI entry point ───────────────────────────────────────────────────────────

def _cli() -> None:
    """Build wo_master.csv from raw files and write to out_dir."""
    from services.etl.app.parsers.oee import parse_oee
    from services.etl.app.parsers.mantenimiento import parse_mantenimiento
    from services.etl.app.parsers.tiempo import parse_tiempo
    from services.etl.app.parsers.volumen import parse_volumen

    parser = argparse.ArgumentParser(description="Build wo_master.csv")
    parser.add_argument("--raw", default="data/raw", type=Path)
    parser.add_argument("--out", default="data/clean", type=Path)
    args = parser.parse_args()

    raw: Path = args.raw
    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)

    print("Loading source files…")
    oee_df = parse_oee(raw / "OEE 14_17_19_ 2025.xlsx")
    tiempo_df = parse_tiempo(raw / "Tiempo 14_17_19_ 2025.xlsx")
    volumen_df = parse_volumen(raw / "Volumen 14_17_19_ 2025.xlsx")
    mant_df = parse_mantenimiento(raw / "Mantenimiento 14_17_19_ 2025.xlsx")

    print("Building wo_master…")
    wo_master, warnings = build_wo_master(oee_df, tiempo_df, volumen_df, mant_df)

    out_path = out / "wo_master.csv"
    wo_master.to_csv(out_path, index=False)
    print(f"Written: {out_path}  ({len(wo_master)} rows, {len(wo_master.columns)} cols)")

    if warnings:
        print(f"\nWarnings ({len(warnings)}):")
        for w in warnings:
            print(f"  • {w}")


if __name__ == "__main__":
    _cli()
