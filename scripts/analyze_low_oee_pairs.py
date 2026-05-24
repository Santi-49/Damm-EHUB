from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd

DATA_DIR = Path("/Users/nicolasvilloria/Desktop/DATOS/Damm-EHUB/data")
OUT_DIR = DATA_DIR / "analysis_out"

OEE_FILE = DATA_DIR / "OEE 14_17_19_ 2025.xlsx"
CAMBIOS_FILE = DATA_DIR / "Cambios 14_17_19_ 2025.xlsx"
TIEMPO_FILE = DATA_DIR / "Tiempo 14_17_19_ 2025.xlsx"
MANT_FILE = DATA_DIR / "Mantenimiento 14_17_19_ 2025.xlsx"

SHEET_NAME = "Export"
PAIR_LEVEL = "SKU"  # Use "Familia" to group by product family instead
MIN_PAIR_COUNT = 5


def _standardize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip().replace("\n", " ") for c in df.columns]
    return df


def _read_sheet(path: Path, sheet: str = SHEET_NAME) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name=sheet)
    df = _standardize_columns(df)
    df = df.dropna(how="all").dropna(axis=1, how="all")
    return df


def _coerce_numeric(df: pd.DataFrame, cols: Iterable[str]) -> pd.DataFrame:
    for col in cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def _coerce_date(df: pd.DataFrame, col: str) -> pd.DataFrame:
    if col in df.columns:
        df[col] = pd.to_datetime(df[col], errors="coerce")
    return df


def _merge_by_best_key(left: pd.DataFrame, right: pd.DataFrame) -> pd.DataFrame:
    # Prefer OF if available; otherwise use SKU+Fecha Fin+TREN.
    if "OF" in left.columns and "OF" in right.columns:
        return left.merge(right, on="OF", how="left", suffixes=("", "_y"))
    keys = [k for k in ["SKU", "Fecha Fin", "TREN"] if k in left.columns and k in right.columns]
    if not keys:
        raise ValueError("No compatible join keys found between dataframes")
    return left.merge(right, on=keys, how="left", suffixes=("", "_y"))


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    oee = _read_sheet(OEE_FILE)
    oee = _coerce_date(oee, "Fecha Fin")
    oee = _coerce_numeric(oee, ["OEE", "Disponibilidad", "Rendimiento", "Ineficiencia", "Cambios"])

    # Sort to build transitions within each line.
    sort_cols = [c for c in ["TREN", "Fecha Fin", "OF"] if c in oee.columns]
    oee = oee.sort_values(sort_cols).reset_index(drop=True)

    if PAIR_LEVEL not in oee.columns:
        raise ValueError(f"PAIR_LEVEL '{PAIR_LEVEL}' not found in OEE data")

    oee["from_key"] = oee.groupby("TREN")[PAIR_LEVEL].shift(1)
    oee["to_key"] = oee[PAIR_LEVEL]
    pairs = oee.dropna(subset=["from_key", "to_key", "OEE"]).copy()

    baseline_oee = pairs["OEE"].mean()

    pair_summary = (
        pairs.groupby(["from_key", "to_key"], as_index=False)
        .agg(mean_oee=("OEE", "mean"), count=("OEE", "size"))
        .assign(penalty=lambda d: d["mean_oee"] - baseline_oee)
        .sort_values(["mean_oee", "count"], ascending=[True, False])
    )

    pair_summary.to_csv(OUT_DIR / "pairs_summary.csv", index=False)

    worst_pairs = pair_summary[pair_summary["count"] >= MIN_PAIR_COUNT].head(50)
    worst_pairs.to_csv(OUT_DIR / "pairs_worst.csv", index=False)

    heatmap = pair_summary.pivot(index="from_key", columns="to_key", values="mean_oee")
    heatmap.to_csv(OUT_DIR / "pairs_heatmap.csv")

    sankey = pair_summary[["from_key", "to_key", "count", "mean_oee"]]
    sankey.to_csv(OUT_DIR / "pairs_sankey.csv", index=False)

    # Root-cause breakdown from time-loss data.
    tiempo = _read_sheet(TIEMPO_FILE)
    tiempo = _coerce_date(tiempo, "Fecha Fin")
    tiempo = _coerce_numeric(
        tiempo,
        [
            "Par. tot",
            "% Parada",
            "PNP",
            "Limpieza",
            "IDLE",
            "Tiempo Paro por Saturación a la Salida",
            "Tiempo de CIP",
            "Tiempo Máquina en paro",
            "Tiempo Paro por Falta Producto",
            "Tiempo Baja Velocidad",
            "Tiempo Máquina en Marcha",
            "Tiempo de esterilización",
            "Tiempo Operativo Neto",
            "Tiempo Operativo Neto2",
        ],
    )

    pairs_with_time = _merge_by_best_key(pairs, tiempo)

    time_cols = [
        c
        for c in [
            "Par. tot",
            "% Parada",
            "PNP",
            "Limpieza",
            "IDLE",
            "Tiempo Paro por Saturación a la Salida",
            "Tiempo de CIP",
            "Tiempo Máquina en paro",
            "Tiempo Paro por Falta Producto",
            "Tiempo Baja Velocidad",
            "Tiempo de esterilización",
        ]
        if c in pairs_with_time.columns
    ]

    pairs_with_time = _coerce_numeric(pairs_with_time, time_cols)
    time_cols_numeric = (
        pairs_with_time[time_cols].select_dtypes(include="number").columns.tolist()
    )

    pair_causes = (
        pairs_with_time.groupby(["from_key", "to_key"], as_index=False)[time_cols_numeric]
        .mean(numeric_only=True)
        .merge(pair_summary, on=["from_key", "to_key"], how="left")
    )
    pair_causes.to_csv(OUT_DIR / "pairs_time_loss_causes.csv", index=False)

    # Change-type impact from Cambios.
    cambios = _read_sheet(CAMBIOS_FILE)
    cambios = _coerce_date(cambios, "Fecha Fin")

    change_cols = [c for c in cambios.columns if c.startswith("C.")]
    pairs_with_changes = _merge_by_best_key(pairs, cambios)

    if change_cols:
        pairs_with_changes = _coerce_numeric(pairs_with_changes, change_cols)
        change_cols_numeric = (
            pairs_with_changes[change_cols].select_dtypes(include="number").columns.tolist()
        )
        if change_cols_numeric:
            change_impact = (
                pairs_with_changes.groupby(["from_key", "to_key"], as_index=False)[
                    change_cols_numeric
                ]
                .mean(numeric_only=True)
                .merge(pair_summary, on=["from_key", "to_key"], how="left")
            )
            change_impact.to_csv(OUT_DIR / "pairs_change_type_impact.csv", index=False)

    # Maintenance context.
    mant = _read_sheet(MANT_FILE)
    mant = _coerce_date(mant, "Fecha Fin")
    mant = _coerce_numeric(
        mant,
        [
            "Nº LLamadas",
            "Tiempo en Espera",
            "Tiempo Intervención",
            "Tiempo Total",
            "Tiempo Total en Marcha",
            "Tiempo Total en Paro",
        ],
    )

    pairs_with_mant = _merge_by_best_key(pairs, mant)
    mant_cols = [
        c
        for c in [
            "Nº LLamadas",
            "Tiempo en Espera",
            "Tiempo Intervención",
            "Tiempo Total",
            "Tiempo Total en Paro",
        ]
        if c in pairs_with_mant.columns
    ]

    if mant_cols:
        pairs_with_mant = _coerce_numeric(pairs_with_mant, mant_cols)
        mant_cols_numeric = (
            pairs_with_mant[mant_cols].select_dtypes(include="number").columns.tolist()
        )
        if mant_cols_numeric:
            mant_impact = (
                pairs_with_mant.groupby(["from_key", "to_key"], as_index=False)[
                    mant_cols_numeric
                ]
                .mean(numeric_only=True)
                .merge(pair_summary, on=["from_key", "to_key"], how="left")
            )
            mant_impact.to_csv(OUT_DIR / "pairs_maintenance_impact.csv", index=False)

    print("Analysis complete. Outputs written to:", OUT_DIR)


if __name__ == "__main__":
    main()
