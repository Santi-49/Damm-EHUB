#!/usr/bin/env python3
"""Explore the four raw Excel files that feed wo_master.csv.

Run before writing any parser — this tells you the real column names,
sheet layout, null rates, and value distributions.

Usage:
    python services/etl/scripts/explore_wo_master_sources.py            # uses data/raw
    python services/etl/scripts/explore_wo_master_sources.py data/raw
    python services/etl/scripts/explore_wo_master_sources.py data/raw --file OEE
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

RAW_FILES = {
    "OEE": "OEE 14_17_19_ 2025.xlsx",
    "Tiempo": "Tiempo 14_17_19_ 2025.xlsx",
    "Volumen": "Volumen 14_17_19_ 2025.xlsx",
    "Mantenimiento": "Mantenimiento 14_17_19_ 2025.xlsx",
}

# Columns we expect — used to flag mismatches
EXPECTED = {
    "OEE": ["OF", "TREN", "SKU", "Fecha Fin", "H. Tot.", "OEE",
             "Disponibilidad", "Rendimiento", "Calidad", "Ineficiencia", "Cambios"],
    "Tiempo": ["WOID", "Tiempo Máquina en Marcha", "PNP", "IDLE",
                "Tiempo Baja Velocidad", "Limpieza", "Tiempo de CIP",
                "Tiempo de esterilización",
                "Tiempo Paro por Saturación a la Salida",
                "Tiempo Paro por Falta Producto"],
    "Volumen": ["WOID", "UDS", "HL"],
    "Mantenimiento": ["WOID", "Nº LLamadas", "Tiempo en Espera", "Tiempo Intervención"],
}


def _sep(width: int = 72) -> None:
    print("-" * width)


def _header(title: str) -> None:
    print(f"\n{'=' * 72}")
    print(f"  {title}")
    print(f"{'=' * 72}")


def _explore_sheet(df: pd.DataFrame, sheet: str, expected: list[str]) -> None:
    print(f"\n  Sheet: {sheet!r}   shape={df.shape}")
    _sep()

    # Column inventory
    print(f"  {'Column':<52} {'dtype':<14} {'null%':>6}  sample")
    _sep()
    actual_norm = {c.lower().strip() for c in df.columns}
    for col in df.columns:
        null_pct = df[col].isna().mean() * 100
        dtype = str(df[col].dtype)
        try:
            sample = repr(df[col].dropna().iloc[0])[:40]
        except IndexError:
            sample = "ALL NULL"
        flag = ""  # mark expected columns
        if col in expected:
            flag = " [OK]"
        elif col.lower().strip() in {e.lower().strip() for e in expected}:
            flag = " [~]"  # case/space match
        print(f"  {col + flag:<52} {dtype:<14} {null_pct:>5.1f}%  {sample}")

    # Missing expected columns
    missing = [e for e in expected if e.lower().strip() not in actual_norm]
    if missing:
        print(f"\n  [MISSING] Expected but NOT found: {missing}")

    # First 3 rows (transposed for readability)
    print(f"\n  First 3 rows (transposed):")
    _sep()
    try:
        print(df.head(3).T.to_string(max_colwidth=35))
    except Exception as exc:
        print(f"  (could not transpose: {exc})")

    # Numeric summary
    num_cols = df.select_dtypes("number").columns.tolist()
    if num_cols:
        print(f"\n  Numeric describe ({len(num_cols)} cols):")
        _sep()
        desc = df[num_cols].describe().round(3)
        print(desc.to_string())

    # Categorical value counts (first 6 object cols)
    obj_cols = df.select_dtypes(include=["object", "category"]).columns.tolist()
    for col in obj_cols[:6]:
        vc = df[col].value_counts(dropna=False).head(12)
        print(f"\n  Value counts — {col!r}:")
        print(vc.to_string())

    # Duplicate check on likely join key
    for key_col in ["OF", "WOID"]:
        if key_col in df.columns:
            dupes = df[key_col].duplicated().sum()
            nulls = df[key_col].isna().sum()
            print(f"\n  Join key {key_col!r}: {len(df)} rows, {dupes} duplicates, {nulls} nulls")

    # Date column range
    date_cols = df.select_dtypes(include=["datetime", "datetimetz"]).columns.tolist()
    for col in date_cols:
        print(f"\n  Date range — {col!r}: {df[col].min()} → {df[col].max()}")


def explore_file(name: str, path: Path) -> None:
    _header(f"{name}  ·  {path.name}")
    print(f"  Size: {path.stat().st_size / 1024:.1f} KB")

    xl = pd.ExcelFile(path)
    print(f"  Sheets ({len(xl.sheet_names)}): {xl.sheet_names}")

    expected = EXPECTED.get(name, [])
    for sheet in xl.sheet_names:
        df = xl.parse(sheet)
        _explore_sheet(df, sheet, expected)


def main() -> None:
    args = sys.argv[1:]
    raw_dir = Path(args[0]) if args and not args[0].startswith("--") else Path("data/raw")

    filter_name = None
    if "--file" in args:
        idx = args.index("--file")
        filter_name = args[idx + 1] if idx + 1 < len(args) else None

    print(f"Raw directory: {raw_dir.resolve()}")

    for name, filename in RAW_FILES.items():
        if filter_name and filter_name.upper() not in name.upper():
            continue
        path = raw_dir / filename
        if not path.exists():
            print(f"\nMISSING: {path}")
            continue
        explore_file(name, path)

    print(f"\n{'=' * 72}")
    print("  Done.")
    print(f"{'=' * 72}\n")


if __name__ == "__main__":
    main()
