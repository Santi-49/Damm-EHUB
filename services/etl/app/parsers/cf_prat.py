"""Parser for Tabla CF Prat 2026_14_17_19.xlsx.

The workbook is human-formatted, so this parser extracts only the structured
pieces needed by the ETL:

* ``LATA_BARRIL``: line-specific format / packaging change matrix.
* ``Tiempos adicionales``: line-specific additional event durations.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class CFPratTables:
    """Structured tables parsed from the CF workbook."""

    matrix: pd.DataFrame
    additional_times: pd.DataFrame


def parse_cf_prat(path: Path) -> CFPratTables:
    """Load CF workbook into normalized matrix and additional-time tables."""
    matrix_raw = pd.read_excel(path, sheet_name="LATA_BARRIL", header=None)
    additional_raw = pd.read_excel(path, sheet_name="Tiempos adicionales", header=None)

    return CFPratTables(
        matrix=_parse_lata_barril(matrix_raw),
        additional_times=_parse_additional_times(additional_raw),
    )


def parse_duration_hours(value: object) -> float | None:
    """Parse strings like ``30 min`` / ``1,5 h`` / ``1 h 15 min``."""
    if pd.isna(value):
        return None

    text = str(value).strip().lower().replace(",", ".")
    if not text:
        return None

    hours = 0.0
    hour_match = re.search(r"(\d+(?:\.\d+)?)\s*h", text)
    minute_match = re.search(r"(\d+(?:\.\d+)?)\s*min", text)

    if hour_match:
        hours += float(hour_match.group(1))
    if minute_match:
        hours += float(minute_match.group(1)) / 60.0
    if hours == 0.0 and re.fullmatch(r"\d+(?:\.\d+)?", text):
        hours = float(text)

    return hours if hours > 0.0 else None


def _parse_lata_barril(raw: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []

    for header_idx, first_cell in raw.iloc[:, 0].items():
        line_id = _line_id(first_cell)
        if line_id is None:
            continue

        headers = _matrix_headers(raw.iloc[header_idx])
        row_idx = header_idx + 1
        while row_idx < len(raw) and pd.notna(raw.iat[row_idx, 0]):
            from_label = str(raw.iat[row_idx, 0]).strip()
            for col_idx, to_label in headers:
                hours = parse_duration_hours(raw.iat[row_idx, col_idx])
                if hours is None:
                    continue
                rows.append({
                    "line_id": line_id,
                    "from_label": from_label,
                    "to_label": to_label,
                    "hours": hours,
                })
            row_idx += 1

    return pd.DataFrame(rows, columns=["line_id", "from_label", "to_label", "hours"])


def _matrix_headers(row: pd.Series) -> list[tuple[int, str]]:
    headers: list[tuple[int, str]] = []
    for col_idx in range(1, len(row)):
        value = row.iloc[col_idx]
        if pd.isna(value):
            continue
        text = str(value).strip()
        if text and not text.upper().startswith("TREN"):
            headers.append((col_idx, text))
    return headers


def _parse_additional_times(raw: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    current_line: int | None = None

    for _, row in raw.iterrows():
        line_id = _line_id(row.iloc[0])
        if line_id is not None:
            current_line = line_id

        if current_line is None or len(row) < 3:
            continue

        event = row.iloc[1]
        hours = parse_duration_hours(row.iloc[2])
        if not isinstance(event, str) or hours is None:
            continue

        event = event.strip()
        if not event:
            continue

        rows.append({
            "line_id": current_line,
            "event": event,
            "hours": hours,
        })

    return pd.DataFrame(rows, columns=["line_id", "event", "hours"])


def _line_id(value: object) -> int | None:
    if not isinstance(value, str):
        return None
    match = re.search(r"TREN\s*(\d+)", value.strip(), flags=re.IGNORECASE)
    return int(match.group(1)) if match else None
