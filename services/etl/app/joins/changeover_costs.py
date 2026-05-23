"""Build changeover_costs.csv from SKU attributes and Tabla CF Prat.

The CF workbook provides theoretical durations by line, container format and
change component. It does not contain direct SKU IDs, so this join expands the
rules to every allowed ``(line_id, sku_from_id, sku_to_id)`` pair.

Important business rule: when several components change in the same transition,
the total duration is the maximum component duration, not the sum. The work can
be prepared in parallel and the slowest component dominates.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from services.etl.app.parsers.cf_prat import CFPratTables, parse_cf_prat


ALLOWED_CONTAINER_TYPES: dict[int, set[str]] = {
    14: {"1/2", "1/3"},
    17: {"1/3"},
    19: {"1/2", "1/3", "2/5"},
}

SEGMENT_COLS: list[str] = [
    "segment_container_hours",
    "segment_beer_hours",
    "segment_cap_or_label_hours",
    "segment_primary_pack_hours",
    "segment_secondary_pack_hours",
    "segment_pallet_hours",
]

CHANGEOVER_COST_COLS: list[str] = [
    "line_id",
    "sku_from_id",
    "sku_to_id",
    "from_container_type",
    "to_container_type",
    "total_hours",
    *SEGMENT_COLS,
    "dominant_component",
    "source",
]


def build_changeover_costs(
    skus: pd.DataFrame,
    cf_tables: CFPratTables,
) -> tuple[pd.DataFrame, list[str]]:
    """Expand CF theoretical rules to all allowed SKU-to-SKU transitions."""
    warnings: list[str] = []
    warning_keys: set[str] = set()

    sku_work = skus.copy()
    required = [
        "sku_id",
        "container_type",
        "beer",
        "material_id",
        "material_label",
        "container",
        "primary_packaging",
        "secondary_packaging",
        "pallet_type",
    ]
    for col in required:
        if col not in sku_work.columns:
            sku_work[col] = pd.NA

    missing_container = sku_work["container_type"].isna()
    if missing_container.any():
        warnings.append(
            f"changeover_costs_missing_container_type: {int(missing_container.sum())} skus excluded"
        )
    sku_work = sku_work[~missing_container].copy()

    matrix = _matrix_lookup(cf_tables.matrix)
    additional = _additional_lookup(cf_tables.additional_times)

    rows: list[dict[str, object]] = []
    for line_id, allowed_formats in ALLOWED_CONTAINER_TYPES.items():
        line_skus = (
            sku_work[sku_work["container_type"].isin(allowed_formats)]
            .sort_values("sku_id")
            .reset_index(drop=True)
        )
        if line_skus.empty:
            _warn_once(warnings, warning_keys, f"changeover_costs_no_skus_for_line: line_id={line_id}")
            continue

        for from_row in line_skus.itertuples(index=False):
            for to_row in line_skus.itertuples(index=False):
                rows.append(_build_pair_row(
                    line_id=line_id,
                    from_row=from_row,
                    to_row=to_row,
                    matrix=matrix,
                    additional=additional,
                    warnings=warnings,
                    warning_keys=warning_keys,
                ))

    out = pd.DataFrame(rows, columns=CHANGEOVER_COST_COLS)
    if not out.empty:
        out["line_id"] = out["line_id"].astype("int64")
        for col in ["total_hours", *SEGMENT_COLS]:
            out[col] = pd.to_numeric(out[col], errors="coerce").round(6)

    return out, warnings


def _build_pair_row(
    line_id: int,
    from_row: object,
    to_row: object,
    matrix: dict[tuple[int, str, str], float],
    additional: dict[tuple[int, str], float],
    warnings: list[str],
    warning_keys: set[str],
) -> dict[str, object]:
    from_sku = getattr(from_row, "sku_id")
    to_sku = getattr(to_row, "sku_id")
    from_format = getattr(from_row, "container_type")
    to_format = getattr(to_row, "container_type")

    segments = {
        "segment_container_hours": _format_duration(
            line_id, from_format, to_format, matrix, warnings, warning_keys
        ),
        "segment_beer_hours": _additional_duration(
            line_id,
            "Cambio cerveza",
            _changed(getattr(from_row, "beer"), getattr(to_row, "beer")),
            additional,
            warnings,
            warning_keys,
        ),
        "segment_cap_or_label_hours": _additional_duration(
            line_id,
            "Cambio lata",
            _needs_cap_or_label_change(from_row, to_row),
            additional,
            warnings,
            warning_keys,
        ),
        "segment_primary_pack_hours": _component_duration(
            line_id,
            from_format,
            to_format,
            "Cambio Packaging",
            _changed(getattr(from_row, "primary_packaging"), getattr(to_row, "primary_packaging")),
            matrix,
            warnings,
            warning_keys,
        ),
        "segment_secondary_pack_hours": _component_duration(
            line_id,
            from_format,
            to_format,
            "Cambio a Bandeja",
            _changed(getattr(from_row, "secondary_packaging"), getattr(to_row, "secondary_packaging")),
            matrix,
            warnings,
            warning_keys,
        ),
        "segment_pallet_hours": _component_duration(
            line_id,
            from_format,
            to_format,
            "Cambio Paletizado",
            _changed(getattr(from_row, "pallet_type"), getattr(to_row, "pallet_type")),
            matrix,
            warnings,
            warning_keys,
        ),
    }
    total = max(segments.values()) if segments else 0.0

    return {
        "line_id": line_id,
        "sku_from_id": from_sku,
        "sku_to_id": to_sku,
        "from_container_type": from_format,
        "to_container_type": to_format,
        "total_hours": total,
        **segments,
        "dominant_component": _dominant_component(segments, total),
        "source": "tabla_cf_prat",
    }


def _matrix_lookup(matrix: pd.DataFrame) -> dict[tuple[int, str, str], float]:
    lookup: dict[tuple[int, str, str], float] = {}
    for row in matrix.itertuples(index=False):
        lookup[(int(row.line_id), str(row.from_label), str(row.to_label))] = float(row.hours)
    return lookup


def _additional_lookup(additional: pd.DataFrame) -> dict[tuple[int, str], float]:
    lookup: dict[tuple[int, str], float] = {}
    for row in additional.itertuples(index=False):
        lookup[(int(row.line_id), str(row.event).strip().lower())] = float(row.hours)
    return lookup


def _format_duration(
    line_id: int,
    from_format: object,
    to_format: object,
    matrix: dict[tuple[int, str, str], float],
    warnings: list[str],
    warning_keys: set[str],
) -> float:
    if _same(from_format, to_format):
        return 0.0

    key = (line_id, str(from_format), str(to_format))
    if key in matrix:
        return matrix[key]

    _warn_once(
        warnings,
        warning_keys,
        "changeover_costs_missing_format_pair: "
        f"line_id={line_id}, from={from_format}, to={to_format}",
    )
    return _line_matrix_max(line_id, matrix)


def _component_duration(
    line_id: int,
    from_format: object,
    to_format: object,
    component_label: str,
    needed: bool,
    matrix: dict[tuple[int, str, str], float],
    warnings: list[str],
    warning_keys: set[str],
) -> float:
    if not needed:
        return 0.0

    candidates = [
        (line_id, str(from_format), component_label),
        (line_id, component_label, str(from_format)),
        (line_id, str(to_format), component_label),
        (line_id, component_label, str(to_format)),
    ]
    values = [matrix[key] for key in candidates if key in matrix]
    if values:
        return max(values)

    _warn_once(
        warnings,
        warning_keys,
        "changeover_costs_missing_component: "
        f"line_id={line_id}, component={component_label}",
    )
    return 0.0


def _additional_duration(
    line_id: int,
    event: str,
    needed: bool,
    additional: dict[tuple[int, str], float],
    warnings: list[str],
    warning_keys: set[str],
) -> float:
    if not needed:
        return 0.0

    key = (line_id, event.lower())
    if key in additional:
        return additional[key]

    _warn_once(
        warnings,
        warning_keys,
        f"changeover_costs_missing_additional_time: line_id={line_id}, event={event}",
    )
    return 0.0


def _needs_cap_or_label_change(from_row: object, to_row: object) -> bool:
    """Etiqueta/tapon/lata time applies only when not already covered by beer."""
    if _changed(getattr(from_row, "beer"), getattr(to_row, "beer")):
        return False

    return any(
        _changed(getattr(from_row, attr), getattr(to_row, attr))
        for attr in ("material_id", "material_label", "container", "container_type")
    )


def _dominant_component(segments: dict[str, float], total: float) -> str:
    if total <= 0:
        return "none"
    dominant = [
        name.removeprefix("segment_").removesuffix("_hours")
        for name, value in segments.items()
        if abs(value - total) < 1e-9
    ]
    return ";".join(dominant)


def _changed(left: object, right: object) -> bool:
    if _is_missing(left) or _is_missing(right):
        return False
    return str(left).strip() != str(right).strip()


def _same(left: object, right: object) -> bool:
    if _is_missing(left) or _is_missing(right):
        return False
    return str(left).strip() == str(right).strip()


def _is_missing(value: object) -> bool:
    if pd.isna(value):
        return True
    return str(value).strip().lower() in {"", "nan", "none", "null", "-", "n/a"}


def _line_matrix_max(line_id: int, matrix: dict[tuple[int, str, str], float]) -> float:
    values = [value for (line, _, _), value in matrix.items() if line == line_id]
    return max(values) if values else 0.0


def _warn_once(warnings: list[str], warning_keys: set[str], message: str) -> None:
    if message in warning_keys:
        return
    warning_keys.add(message)
    warnings.append(message)


def _cli() -> None:
    from services.etl.app.joins.skus import build_skus
    from services.etl.app.parsers.oee import parse_oee

    parser = argparse.ArgumentParser(description="Build changeover_costs.csv")
    parser.add_argument("--raw", default="data/raw", type=Path)
    parser.add_argument("--out", default="data/clean", type=Path)
    args = parser.parse_args()

    raw: Path = args.raw
    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)

    print("Loading OEE and CF Prat...")
    oee_df = parse_oee(raw / "OEE 14_17_19_ 2025.xlsx")
    skus, skus_warnings = build_skus(oee_df)
    cf_tables = parse_cf_prat(raw / "Tabla CF Prat 2026_14_17_19.xlsx")

    print("Building changeover_costs...")
    costs, warnings = build_changeover_costs(skus, cf_tables)

    out_path = out / "changeover_costs.csv"
    costs.to_csv(out_path, index=False)

    all_warnings = [*skus_warnings, *warnings]
    print(f"Written: {out_path}  ({len(costs)} rows, {len(costs.columns)} cols)")
    if all_warnings:
        print(f"\nWarnings ({len(all_warnings)}):")
        for warning in all_warnings[:50]:
            print(f"  * {warning}")
        if len(all_warnings) > 50:
            print(f"  ... ({len(all_warnings) - 50} more)")


if __name__ == "__main__":
    _cli()
