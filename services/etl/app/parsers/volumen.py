"""Parser for Volumen 14_17_19_ 2025.xlsx.

One row per WO. Provides production volume columns.

Column mapping:
    WOID  → wo_id  (join key)
    UDS   → units_produced
    HL    → hectoliters_produced
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from ._utils import opt_col, read_first_sheet, require_col, to_float, to_int

_COL_MAP: dict[str, list[str]] = {
    "wo_id":                 ["OF", "WOID", "WO"],  # Volumen uses OF (confirmed)
    "units_produced":        ["UDS", "Uds", "Unidades", "Units"],
    "hectoliters_produced":  ["HL", "Hl", "Hectolitros"],
}


def parse_volumen(path: Path) -> pd.DataFrame:
    """Load Volumen xlsx → tidy DataFrame with one row per WO."""
    raw = read_first_sheet(path)

    rename: dict[str, str] = {}
    for target, candidates in _COL_MAP.items():
        src = opt_col(raw, candidates)
        if src is not None:
            rename[src] = target
        elif target == "wo_id":
            require_col(raw, candidates, label="volumen→wo_id")

    df = raw.rename(columns=rename)
    df["wo_id"] = df["wo_id"].astype(str).str.strip()

    if "units_produced" in df.columns:
        df["units_produced"] = to_int(df["units_produced"])
    if "hectoliters_produced" in df.columns:
        df["hectoliters_produced"] = to_float(df["hectoliters_produced"])

    keep = ["wo_id"] + [c for c in _COL_MAP if c != "wo_id" and c in df.columns]
    return df[keep]
