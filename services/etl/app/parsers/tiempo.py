"""Parser for Tiempo 14_17_19_ 2025.xlsx.

One row per WO (2278 rows; 4 more than OEE — left-join drops the extras).

KEY FINDING from exploratory run:
  * H. Tot. lives HERE, not in OEE.
  * Par. tot  is the primary downtime column (Tiempo Maquina en paro is an alias).
  * Calidad is always 1.0 -> dropped per cleaning_rules 9.
  * Many columns duplicate what OEE already has (TREN, SKU, Marca, etc.) ->
    excluded from the final keep list so the join sees a clean frame.

Column mapping:
    WOID                                    -> wo_id  (join key)
    H. Tot.                                 -> total_hours   (from Tiempo!)
    Par. tot                                -> downtime_hours
    Tiempo Maquina en Marcha               -> productive_hours
    PNP                                     -> unplanned_stop_hours
    IDLE                                    -> idle_hours
    Tiempo Baja Velocidad                  -> low_speed_hours
    Limpieza                               -> cleaning_hours
    Tiempo de CIP                          -> cip_hours
    Tiempo de esterilizacion               -> sterilization_hours
    Tiempo Paro por Saturacion a la Salida -> downstream_block_hours
    Tiempo Paro por Falta Producto         -> upstream_starve_hours
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from ._utils import opt_col, read_first_sheet, require_col, to_float

_COL_MAP: dict[str, list[str]] = {
    "wo_id":                    ["WOID", "OF", "WO"],
    "total_hours":              ["H. Tot.", "H.Tot.", "H. Total", "Horas Total"],
    "productive_hours":         ["Tiempo Máquina en Marcha",
                                 "Tiempo Maquina en Marcha",
                                 "T. Marcha"],
    "downtime_hours":           ["Par. tot",
                                 "Tiempo Máquina en paro",
                                 "Tiempo Maquina en paro",
                                 "T. Paro"],
    "unplanned_stop_hours":     ["PNP"],
    "idle_hours":               ["IDLE", "Idle"],
    "low_speed_hours":          ["Tiempo Baja Velocidad", "T. Baja Velocidad"],
    "cleaning_hours":           ["Limpieza"],
    "cip_hours":                ["Tiempo de CIP", "T. CIP", "CIP"],
    "sterilization_hours":      ["Tiempo de esterilización",
                                 "Tiempo de esterilizacion",
                                 "Esterilización"],
    "downstream_block_hours":   ["Tiempo Paro por Saturación a la Salida",
                                 "Tiempo Paro por Saturacion a la Salida"],
    "upstream_starve_hours":    ["Tiempo Paro por Falta Producto",
                                 "Falta Producto"],
}

_TIME_COLS = [c for c in _COL_MAP if c != "wo_id"]


def parse_tiempo(path: Path) -> pd.DataFrame:
    """Load Tiempo xlsx -> tidy DataFrame with one row per WO."""
    raw = read_first_sheet(path)

    rename: dict[str, str] = {}
    for target, candidates in _COL_MAP.items():
        src = opt_col(raw, candidates)
        if src is not None:
            rename[src] = target
        elif target in ("wo_id", "total_hours"):
            require_col(raw, candidates, label=f"tiempo->{target}")  # must exist

    df = raw.rename(columns=rename)
    df["wo_id"] = df["wo_id"].astype(str).str.strip()

    for col in _TIME_COLS:
        if col in df.columns:
            df[col] = to_float(df[col])

    # Return only wo_id + time columns (exclude redundant OEE/SKU/Marca cols)
    keep = ["wo_id"] + [c for c in _TIME_COLS if c in df.columns]
    return df[keep]
