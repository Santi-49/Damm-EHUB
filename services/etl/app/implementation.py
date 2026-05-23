"""ETL implementation — implements ETLContract + DemandBuilderContract.

Status: wo_master pipeline complete (M1).  Other products are stubs.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from packages.contracts.module.etl import (
    DemandBuilderContract,
    ETLContract,
    ETLResult,
)
from packages.contracts.module.schemas import DemandBucket, Source, WindowConfig

from .joins.skus import build_skus
from .joins.wo_master import build_wo_master
from .parsers.mantenimiento import parse_mantenimiento
from .parsers.oee import parse_oee
from .parsers.tiempo import parse_tiempo
from .parsers.volumen import parse_volumen

# Files we intentionally skip (per ETLContract docstring)
DISCARDED_FILES = (
    "data - 2026-05-18T181640.542.xlsx",
    "Diario Hl_Planif.xlsx",
)


class ETL:
    """Implements ETLContract and DemandBuilderContract."""

    async def build_clean_datasets(self, raw_dir: Path, out_dir: Path) -> ETLResult:
        return await asyncio.to_thread(_build_sync, raw_dir, out_dir)

    async def build_demand(
        self,
        source: Source,
        clean_dir: Path,
        window: WindowConfig | None = None,
        whatif_extra: tuple[DemandBucket, ...] | None = None,
    ) -> tuple[DemandBucket, ...]:
        raise NotImplementedError("build_demand — implement after M1")

    async def to_csv(
        self,
        demand: tuple[DemandBucket, ...],
        out_path: Path,
    ) -> Path:
        raise NotImplementedError("to_csv — implement after M1")


# ── Synchronous implementation (called via asyncio.to_thread) ────────────────

def _build_sync(raw_dir: Path, out_dir: Path) -> ETLResult:
    out_dir.mkdir(parents=True, exist_ok=True)
    rows_per_table: dict[str, int] = {}
    all_warnings: list[str] = []

    # ── wo_master ────────────────────────────────────────────────────────────
    oee_df = parse_oee(raw_dir / "OEE 14_17_19_ 2025.xlsx")
    tiempo_df = parse_tiempo(raw_dir / "Tiempo 14_17_19_ 2025.xlsx")
    volumen_df = parse_volumen(raw_dir / "Volumen 14_17_19_ 2025.xlsx")
    mant_df = parse_mantenimiento(raw_dir / "Mantenimiento 14_17_19_ 2025.xlsx")

    wo_master, wo_warnings = build_wo_master(oee_df, tiempo_df, volumen_df, mant_df)
    wo_master.to_csv(out_dir / "wo_master.csv", index=False)
    rows_per_table["wo_master"] = len(wo_master)
    all_warnings.extend(wo_warnings)

    # ── skus ──────────────────────────────────────────────────────────────────
    skus, skus_warnings = build_skus(oee_df)
    skus.to_csv(out_dir / "skus.csv", index=False)
    rows_per_table["skus"] = len(skus)
    all_warnings.extend(skus_warnings)

    # ── stubs for remaining MVP products ─────────────────────────────────────
    for product in (
        "wo_changeovers", "line_capability",
        "line_calendar", "changeover_costs",
    ):
        all_warnings.append(f"not_implemented: {product}.csv not yet produced")

    return ETLResult(
        clean_dir=out_dir,
        rows_per_table=rows_per_table,
        discarded_files=DISCARDED_FILES,
        warnings=tuple(all_warnings),
    )
