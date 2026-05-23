"""Parser for Mantenimiento 14_17_19_ 2025.xlsx.

KEY FINDINGS from exploratory run:
  * Join key is OF (not WOID like Tiempo).
  * Already ONE row per WO (2276 rows, 0 duplicates on OF).
    Do NOT aggregate -- the groupby count approach would overwrite the real
    Llamadas value with 1 for every WO.
  * 50.5% null: only WOs with maintenance calls have values. Null = no calls.
  * Nro LLamadas is the actual call count (float in Excel, cast to Int64).

Column mapping:
    OF               -> wo_id  (join key)
    Nro LLamadas     -> maintenance_calls
    Tiempo en Espera -> maintenance_wait_hours
    Tiempo Intervencion -> maintenance_intervention_hours
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from ._utils import opt_col, read_first_sheet, require_col, to_float, to_int

_COL_MAP: dict[str, list[str]] = {
    "wo_id":                           ["OF", "WOID", "WO"],
    "maintenance_calls":               ["Nº LLamadas", "N LLamadas", "Nº Llamadas",
                                        "N Llamadas", "Llamadas"],
    "maintenance_wait_hours":          ["Tiempo en Espera", "T. Espera", "Espera"],
    "maintenance_intervention_hours":  ["Tiempo Intervención", "Tiempo Intervencion",
                                        "T. Intervención", "T. Intervencion",
                                        "Intervención", "Intervencion"],
}

_MANT_COLS = [c for c in _COL_MAP if c != "wo_id"]


def parse_mantenimiento(path: Path) -> pd.DataFrame:
    """Load Mantenimiento xlsx -> one row per wo_id (already aggregated in source)."""
    raw = read_first_sheet(path)

    rename: dict[str, str] = {}
    for target, candidates in _COL_MAP.items():
        src = opt_col(raw, candidates)
        if src is not None:
            rename[src] = target
        elif target == "wo_id":
            require_col(raw, candidates, label="mantenimiento->wo_id")

    df = raw.rename(columns=rename)
    df["wo_id"] = df["wo_id"].astype(str).str.strip()

    if "maintenance_calls" in df.columns:
        df["maintenance_calls"] = to_int(df["maintenance_calls"])
    if "maintenance_wait_hours" in df.columns:
        df["maintenance_wait_hours"] = to_float(df["maintenance_wait_hours"])
    if "maintenance_intervention_hours" in df.columns:
        df["maintenance_intervention_hours"] = to_float(df["maintenance_intervention_hours"])

    keep = ["wo_id"] + [c for c in _MANT_COLS if c in df.columns]
    return df[keep]
