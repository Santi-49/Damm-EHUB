"""Shared helpers for raw Excel parsers."""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd


def require_col(df: pd.DataFrame, candidates: list[str], label: str = "") -> str:
    """Return the first matching column name (case- and space-insensitive).

    Raises KeyError with a descriptive message if none match.
    """
    norm_map = {_norm(c): c for c in df.columns}
    for c in candidates:
        if _norm(c) in norm_map:
            return norm_map[_norm(c)]
    prefix = f"[{label}] " if label else ""
    raise KeyError(
        f"{prefix}None of {candidates!r} found in columns: {list(df.columns)}"
    )


def opt_col(df: pd.DataFrame, candidates: list[str]) -> str | None:
    """Like require_col but returns None if not found."""
    norm_map = {_norm(c): c for c in df.columns}
    for c in candidates:
        if _norm(c) in norm_map:
            return norm_map[_norm(c)]
    return None


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).lower().strip()


def read_first_sheet(path: Path, **kwargs) -> pd.DataFrame:
    """Read the first sheet of an Excel file."""
    return pd.read_excel(path, sheet_name=0, **kwargs)


def to_float(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").astype(float)


def to_int(series: pd.Series, dtype: str = "Int64") -> pd.Series:
    return pd.to_numeric(series, errors="coerce").astype(dtype)


def to_bool_si_no(series: pd.Series) -> pd.Series:
    """Convert SI/NO (Spanish) strings to bool. Unknown → NA."""
    mapping = {"si": True, "sí": True, "s": True, "yes": True,
               "no": False, "n": False}
    return (
        series.astype(str)
        .str.lower()
        .str.strip()
        .map(mapping)
        .astype("boolean")
    )
