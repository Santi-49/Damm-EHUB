"""Parser for OEE 14_17_19_ 2025.xlsx.

Returns a DataFrame with one row per work order (WO). Columns map to
the wo_master schema plus any extra SKU-attribute columns that survive
the drop list (used later for skus.csv).

Column mapping (Spanish → English):
    OF                              → wo_id
    TREN                            → line_id
    SKU                             → sku_id
    Fecha Fin                       → end_ts
    H. Tot.                         → total_hours
    OEE                             → oee
    Disponibilidad                  → availability
    Rendimiento                     → performance
    Calidad                         → quality
    Ineficiencia                    → inefficiency
    Cambios                         → had_changeover  (SI/NO)

Dropped (constant or irrelevant per cleaning_rules §9):
    CENTRO, Columna Blanca, Cantidad registros, ID Tipo artículo,
    Tipo artículo, Retornable, ID Retornable, Palet
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from ._utils import opt_col, read_first_sheet, require_col, to_bool_si_no, to_float, to_int

# Columns dropped because they are constant or add no signal for wo_master / skus
_DROP_COLS = frozenset([
    "CENTRO", "Columna Blanca", "Cantidad registros",
    "ID Tipo artículo", "Tipo artículo",
    "Retornable", "ID Retornable",
    "Palet",
])

# Candidates for each target column (first match wins, case-insensitive)
_COL_MAP: dict[str, list[str]] = {
    "wo_id":          ["OF", "O.F.", "WO", "WOID"],
    "line_id":        ["TREN", "Línea", "Linea", "Line"],
    "sku_id":         ["SKU", "Sku"],
    "end_ts":         ["Fecha Fin", "Fecha fin", "FechaFin"],
    # NOTE: H. Tot. / total_hours lives in Tiempo, NOT in OEE.
    "oee":            ["OEE"],
    "availability":   ["Disponibilidad"],
    "performance":    ["Rendimiento"],
    # NOTE: Calidad is in Tiempo (always 1.0) and dropped by cleaning_rules §9.
    "inefficiency":   ["Ineficiencia"],
    "had_changeover": ["Cambios"],
    # SKU metadata columns — kept here for skus.csv derivation
    "brand":                   ["Marca"],
    "brand_family":            ["Supramarca"],
    "container_type_raw":      ["Tipo Envase"],
    "units_per_case":          ["Unidad/caja"],
    "primary_packaging":       ["Packaging Primario"],
    "secondary_packaging":     ["Packaging Secundario"],
    "pallet_type":             ["Tipo Palet"],
    "beer_code":               ["Cerveza"],
    "family_code":             ["Familia"],
    "material_id":             ["ID Material Precio", "Codigo Material"],
    "material_label":          ["Mat. Precio", "Material Precio", "Mat.Precio"],
    "container":               ["Envase"],
    "units_per_primary_pack":  ["Unidades packaging primario", "Uds. Packaging Primario",
                                "Uds packaging primario"],
    "units_per_secondary_pack": ["Unidades packaging secundario", "Uds. Packaging Secundario",
                                 "Uds packaging secundario"],
}


def parse_oee(path: Path) -> pd.DataFrame:
    """Load OEE xlsx → tidy DataFrame with one row per WO."""
    raw = read_first_sheet(path)

    # Build rename dict — only for columns that are actually present
    rename: dict[str, str] = {}
    for target, candidates in _COL_MAP.items():
        src = opt_col(raw, candidates)
        if src is not None:
            rename[src] = target
        else:
            # Mandatory columns raise; optional ones we handle downstream
            if target in ("wo_id", "line_id", "sku_id", "end_ts"):
                require_col(raw, candidates, label=f"oee→{target}")  # raises

    df = raw.rename(columns=rename)

    # Drop constant columns (match case-insensitively)
    drop_actual = [c for c in df.columns if c in _DROP_COLS]
    df = df.drop(columns=drop_actual, errors="ignore")

    # Type casts
    df["line_id"] = to_int(df["line_id"], dtype="Int16")
    df["wo_id"] = df["wo_id"].astype(str).str.strip()
    df["sku_id"] = df["sku_id"].astype(str).str.strip()
    df["end_ts"] = pd.to_datetime(df["end_ts"], errors="coerce")

    for col in ("oee", "availability", "performance", "inefficiency"):
        if col in df.columns:
            df[col] = to_float(df[col])

    if "had_changeover" in df.columns:
        df["had_changeover"] = to_bool_si_no(df["had_changeover"])

    if "units_per_case" in df.columns:
        df["units_per_case"] = to_float(df["units_per_case"])

    # Drop Excel grand-total footer row: line_id is NaN and wo_id is "Total"
    # (This accounts for the infamous 21065h outlier in the raw stats.)
    df = df[df["line_id"].notna()].reset_index(drop=True)

    return df
