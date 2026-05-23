"""Parser for Cambios 14_17_19_ 2025.xlsx.

One source row describes change components for the destination WO. Some WOs
appear more than once in the raw workbook; aggregation happens in the
wo_changeovers join so warnings can be emitted with full context.

Column mapping:
    OF               -> wo_id
    Frecuencia Total -> cambios_hours  (diagnostic only; not target)
    Nro de Cambios   -> n_components_changed
    C. PRINCIPAL     -> principal_change_type
    C. Brand         -> flag_brand_change
    C. CAP           -> flag_cap_change
    C. Envase        -> flag_container_change
    C. Palet         -> flag_pallet_change
    C. Primario      -> flag_primary_pack_change
    C. Producto      -> flag_product_change
    C. Secundario    -> flag_secondary_pack_change
    C. Volum         -> flag_volume_change
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from ._utils import opt_col, read_first_sheet, require_col, to_float, to_int

_COL_MAP: dict[str, list[str]] = {
    "wo_id": ["OF", "WOID", "WO"],
    "cambios_end_ts": ["Fecha Fin", "Fecha fin", "FechaFin"],
    "cambios_sku_id": ["SKU", "Sku"],
    "n_components_changed": ["Nº de Cambios", "N de Cambios", "No de Cambios"],
    "cambios_hours": ["Frecuencia Total"],
    "principal_change_type": ["C. PRINCIPAL", "C.PRINCIPAL"],
    "flag_brand_change": ["C. Brand", "C.Brand"],
    "flag_cap_change": ["C. CAP", "C.CAP"],
    "flag_container_change": ["C. Envase", "C.Envase"],
    "flag_pallet_change": ["C. Palet", "C.Palet"],
    "flag_primary_pack_change": ["C. Primario", "C.Primario"],
    "flag_product_change": ["C. Producto", "C.Producto"],
    "flag_secondary_pack_change": ["C. Secundario", "C.Secundario"],
    "flag_volume_change": ["C. Volum", "C.Volum"],
}

FLAG_COLS: list[str] = [
    "flag_brand_change",
    "flag_container_change",
    "flag_cap_change",
    "flag_primary_pack_change",
    "flag_secondary_pack_change",
    "flag_pallet_change",
    "flag_product_change",
    "flag_volume_change",
]

_OPTIONAL_NUMERIC_COLS = ["cambios_hours", "n_components_changed", *FLAG_COLS]
_EMPTY_CHANGE_TYPES = frozenset(["", "-", "-2", "nan", "none", "null"])


def parse_cambios(path: Path) -> pd.DataFrame:
    """Load Cambios xlsx -> normalized source rows keyed by wo_id."""
    raw = read_first_sheet(path)

    rename: dict[str, str] = {}
    for target, candidates in _COL_MAP.items():
        src = opt_col(raw, candidates)
        if src is not None:
            rename[src] = target
        elif target == "wo_id":
            require_col(raw, candidates, label="cambios->wo_id")

    df = raw.rename(columns=rename)

    # Drop footer / total rows that do not refer to a work order.
    df = df[df["wo_id"].notna()].copy()
    df["wo_id"] = df["wo_id"].astype(str).str.strip()
    df = df[df["wo_id"].str.lower().ne("nan")].reset_index(drop=True)

    if "cambios_end_ts" in df.columns:
        df["cambios_end_ts"] = pd.to_datetime(df["cambios_end_ts"], errors="coerce")
    if "cambios_sku_id" in df.columns:
        df["cambios_sku_id"] = df["cambios_sku_id"].astype(str).str.strip()

    for col in _OPTIONAL_NUMERIC_COLS:
        if col not in df.columns:
            continue
        if col == "n_components_changed":
            df[col] = to_int(df[col])
        else:
            df[col] = to_float(df[col])

    if "principal_change_type" in df.columns:
        principal = df["principal_change_type"].astype(str).str.strip()
        df["principal_change_type"] = principal.where(
            ~principal.str.lower().isin(_EMPTY_CHANGE_TYPES),
            other=pd.NA,
        )

    keep = [
        "wo_id",
        "cambios_end_ts",
        "cambios_sku_id",
        "cambios_hours",
        "n_components_changed",
        "principal_change_type",
        *FLAG_COLS,
    ]
    return df[[c for c in keep if c in df.columns]]
