"""Build skus.csv from the parsed OEE DataFrame.

Lineage:
    parse_oee() → build_skus() → skus.csv

One row per sku_id. For conflicting attribute values within a sku_id,
the row with the latest source date wins. Conflicts are emitted as warnings.

Column renaming (oee internal → skus.csv):
    container_type_raw → container_type
    brand_family       → supra_brand
    beer_code          → beer
    family_code        → family
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

# SKU attribute columns as named in the oee DataFrame (post-rename by parse_oee)
_SKU_ATTR_COLS: list[str] = [
    "brand", "brand_family", "container_type_raw",
    "primary_packaging", "secondary_packaging", "pallet_type",
    "beer_code", "family_code",
    "material_id", "material_label", "container",
    "units_per_case", "units_per_primary_pack", "units_per_secondary_pack",
]

# oee internal name → skus.csv canonical name
_RENAME: dict[str, str] = {
    "container_type_raw": "container_type",
    "brand_family":       "supra_brand",
    "beer_code":          "beer",
    "family_code":        "family",
}

# Final column order for skus.csv (only columns that are present)
SKUS_COLS: list[str] = [
    "sku_id",
    "container_type",
    "brand",
    "supra_brand",
    "family",
    "beer",
    "material_id",
    "material_label",
    "container",
    "primary_packaging",
    "secondary_packaging",
    "pallet_type",
    "units_per_primary_pack",
    "units_per_secondary_pack",
    "units_per_case",
]

# Values normalised to null (empty / placeholder strings in Excel exports)
_EMPTY = frozenset(["", "-", "N/A", "n/a", "NA", "na", "NULL", "null", "#N/A"])

# SKU IDs that are synthetic / non-product and must be excluded
_EXCLUDE_SKU_IDS = frozenset(["LIMPIEZA"])

_CONTAINER_TYPE_MAP = {
    "LATA 1/2 SR.": "1/2",
    "LATA 1/3 SR.": "1/3",
    "LATA 2/5": "2/5",
}


def build_skus(oee: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Derive skus.csv from the parsed OEE DataFrame.

    Returns (skus_df, warnings).
    """
    warnings: list[str] = []

    # Work only with sku_id, end_ts, and whatever SKU attr cols are present
    attr_present = [c for c in _SKU_ATTR_COLS if c in oee.columns]
    work = oee[["sku_id", "end_ts"] + attr_present].copy()

    # Exclude synthetic SKUs
    excluded = work["sku_id"].isin(_EXCLUDE_SKU_IDS)
    if excluded.any():
        n = excluded.sum()
        warnings.append(f"skus_excluded_synthetic: {n} rows for sku_ids {list(_EXCLUDE_SKU_IDS)} dropped")
    work = work[~excluded].reset_index(drop=True)

    # Sort descending by date-only end_ts so drop_duplicates keeps the most recent row.
    work = work.sort_values("end_ts", ascending=False)

    # Detect attribute conflicts within each sku_id before deduplication
    for col in attr_present:
        n_unique = (
            work.dropna(subset=[col])
            .groupby("sku_id", sort=False)[col]
            .nunique()
        )
        conflicted = n_unique[n_unique > 1].index.tolist()
        for sku in conflicted:
            vals = (
                work.loc[work["sku_id"] == sku, col]
                .dropna().unique().tolist()
            )
            warnings.append(
                f"sku_attribute_conflict: sku_id={sku}, col={col}, "
                f"values={vals[:5]}"
            )

    # One row per sku_id — most-recent WO's attributes win
    skus = work.drop_duplicates(subset=["sku_id"], keep="first").drop(columns=["end_ts"])

    # Rename to canonical skus.csv names
    skus = skus.rename(columns=_RENAME)

    # Normalise empty / placeholder strings → pd.NA
    for col in skus.select_dtypes(include="object").columns:
        skus[col] = skus[col].where(~skus[col].isin(_EMPTY), other=pd.NA)

    if "container_type" in skus.columns:
        skus["container_type"] = skus["container_type"].replace(_CONTAINER_TYPE_MAP)

    # Select and order final columns
    present = [c for c in SKUS_COLS if c in skus.columns]
    skus = skus[present].reset_index(drop=True)

    return skus, warnings


# ── CLI entry point ───────────────────────────────────────────────────────────

def _cli() -> None:
    from services.etl.app.parsers.oee import parse_oee

    parser = argparse.ArgumentParser(description="Build skus.csv")
    parser.add_argument("--raw", default="data/raw", type=Path)
    parser.add_argument("--out", default="data/clean", type=Path)
    args = parser.parse_args()

    raw: Path = args.raw
    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)

    print("Loading OEE…")
    oee_df = parse_oee(raw / "OEE 14_17_19_ 2025.xlsx")

    print("Building skus…")
    skus, warnings = build_skus(oee_df)

    out_path = out / "skus.csv"
    skus.to_csv(out_path, index=False)
    print(f"Written: {out_path}  ({len(skus)} rows, {len(skus.columns)} cols)")
    print(f"Columns: {list(skus.columns)}")

    if warnings:
        print(f"\nWarnings ({len(warnings)}):")
        for w in warnings[:20]:
            print(f"  * {w}")
        if len(warnings) > 20:
            print(f"  ... ({len(warnings) - 20} more)")


if __name__ == "__main__":
    _cli()
