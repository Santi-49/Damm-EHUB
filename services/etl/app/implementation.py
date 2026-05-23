"""ETL implementation — implements ETLContract + DemandBuilderContract.

Status: wo_master, skus, changeover_costs and wo_changeovers complete.
Other products are stubs.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pandas as pd

from packages.contracts.module.etl import ETLResult
from packages.contracts.module.schemas import DemandBucket, Source, WindowConfig

from .demand import build_historical_demand, buckets_to_dataframe, dataframe_to_buckets
from .joins.changeover_costs import build_changeover_costs
from .joins.skus import build_skus
from .joins.wo_changeovers import build_wo_changeovers
from .joins.wo_master import build_wo_master
from .parsers.cambios import parse_cambios
from .parsers.cf_prat import parse_cf_prat
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
        if source == "whatif_usuario":
            return whatif_extra or tuple()
        if source != "historico_2025":
            raise NotImplementedError("build_demand source not implemented: plan_2026")

        return await asyncio.to_thread(_build_historical_demand_sync, clean_dir, window)

    async def to_csv(
        self,
        demand: tuple[DemandBucket, ...],
        out_path: Path,
    ) -> Path:
        return await asyncio.to_thread(_demand_to_csv_sync, demand, out_path)


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

    # ── demand ───────────────────────────────────────────────────────────────
    demand, demand_warnings = build_historical_demand(wo_master, WindowConfig())
    demand.to_csv(out_dir / "demand.csv", index=False)
    rows_per_table["demand"] = len(demand)
    all_warnings.extend(demand_warnings)

    # ── skus ──────────────────────────────────────────────────────────────────
    skus, skus_warnings = build_skus(oee_df)
    skus.to_csv(out_dir / "skus.csv", index=False)
    rows_per_table["skus"] = len(skus)
    all_warnings.extend(skus_warnings)

    # ── changeover_costs ─────────────────────────────────────────────────────
    cf_tables = parse_cf_prat(raw_dir / "Tabla CF Prat 2026_14_17_19.xlsx")
    changeover_costs, cost_warnings = build_changeover_costs(skus, cf_tables)
    changeover_costs.to_csv(out_dir / "changeover_costs.csv", index=False)
    rows_per_table["changeover_costs"] = len(changeover_costs)
    all_warnings.extend(cost_warnings)

    # ── wo_changeovers ───────────────────────────────────────────────────────
    cambios_df = parse_cambios(raw_dir / "Cambios 14_17_19_ 2025.xlsx")
    wo_changeovers, changeover_warnings = build_wo_changeovers(
        wo_master, skus, cambios_df, changeover_costs
    )
    wo_changeovers.to_csv(out_dir / "wo_changeovers.csv", index=False)
    rows_per_table["wo_changeovers"] = len(wo_changeovers)
    all_warnings.extend(changeover_warnings)

    # ── stubs for remaining MVP products ─────────────────────────────────────
    for product in (
        "line_capability", "line_calendar",
    ):
        all_warnings.append(f"not_implemented: {product}.csv not yet produced")

    return ETLResult(
        clean_dir=out_dir,
        rows_per_table=rows_per_table,
        discarded_files=DISCARDED_FILES,
        warnings=tuple(all_warnings),
    )


def _build_historical_demand_sync(
    clean_dir: Path,
    window: WindowConfig | None,
) -> tuple[DemandBucket, ...]:
    wo_master = pd.read_csv(clean_dir / "wo_master.csv")
    demand, _warnings = build_historical_demand(wo_master, window or WindowConfig())
    return dataframe_to_buckets(demand)


def _demand_to_csv_sync(
    demand: tuple[DemandBucket, ...],
    out_path: Path,
) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    buckets_to_dataframe(demand).to_csv(out_path, index=False)
    return out_path
