"""Contracts for the ETL functionality.

Two protocols so the demand-builder can iterate without re-parsing the Excel
files every time:

* ``ETLContract``           — raw ``data/raw/*.xlsx`` → tidy CSVs in ``data/clean/``
* ``DemandBuilderContract`` — clean tables → ``demand.csv`` for the optimiser

Implementations live in ``services/etl/``. The list of CSVs and their schemas
is the catalogue under ``docs/data/``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .schemas import DemandBucket, Source, WindowConfig


@dataclass(frozen=True)
class ETLResult:
    """Summary of an ETL run."""

    clean_dir: Path
    rows_per_table: dict[str, int]           # e.g. {"wo_master": 2274, "skus": 170}
    discarded_files: tuple[str, ...]         # files we intentionally skipped
    warnings: tuple[str, ...]                # surfaced data-quality issues


class ETLContract(Protocol):
    """Turn raw Excel exports into the canonical clean CSV set.

    Output files produced in ``out_dir`` (full schemas in ``docs/data/``):

    * ``wo_master.csv``           Master cleaned work-order table (one row per WO)
    * ``skus.csv``                SKU catalogue (one row per SKU)
    * ``wo_changeovers.csv``      Historical ``sku_from -> sku_to`` transitions
                                  derived from consecutive production WOs on the same
                                  line, with change flags and estimated CF cost joined
                                  from ``changeover_costs.csv``.
    * ``demand.csv``              Window-aggregated historical demand from
                                  ``wo_master.csv`` (default source: ``historico_2025``).
    * ``line_capability.csv``     Materialised ``(sku_id, line_id) -> can_produce + median/fallback speed/OEE``
    * ``line_calendar.csv``       Forced events per line (cleaning + maintenance)
    * ``changeover_costs.csv``    SKU-to-SKU theoretical transition matrix expanded from
                                  ``Tabla CF Prat``.
    * ``node_cost_train.csv``     [post-MVP] Training table for production-time / speed model
    * ``incidents.csv``           [M2, simulator] Replay log with explicit or estimated
                                  incident timestamps.

    Invariants:

    * The implementation MUST NOT modify files under ``raw_dir``.
    * Discarded inputs (``data - 2026-05-18….xlsx``, ``Diario Hl_Planif.xlsx``)
      must be reported in ``ETLResult.discarded_files``.
    * Data-quality warnings (OEE > 1, ``total_hours`` outliers, diagnostic
      ``Frecuencia Total``, ...) must be surfaced in
      ``ETLResult.warnings`` — do NOT silently clip values.
    * ``wo_changeovers.csv`` must not invent timestamp-gap changeover targets.
      Estimated duration comes from ``changeover_costs.csv``.
    """

    async def build_clean_datasets(self, raw_dir: Path, out_dir: Path) -> ETLResult:
        ...


class DemandBuilderContract(Protocol):
    """Re-aggregate any planning source to time-windowed demand buckets.

    The optimiser only consumes ``demand.csv``; this contract is the only place
    that knows where demand comes from (historical 2025, JDA plan 2026, what-if
    form, …). The bucket size is governed by :class:`WindowConfig` — default
    7-day Monday-anchored windows.

    For ``source = "historico_2025"``:
        Read ``wo_master.csv``. Drop ``sku_id == "LIMPIEZA"``. Drop ``PRT…-M``
        maintenance WOs. Assign each WO to a window via ``window.anchor`` on
        ``end_day``. Sum ``units_produced`` per ``(sku_id, window)``.

    For ``source = "plan_2026"``:
        Read ``Planificado - producciones 14 - 17 - 19.XLSX``. Normalise
        ``planned_quantity`` (CAJ -> UN via ``units_per_case``, UN as-is).
        Window-bucket on ``start_ts``. Sum per ``(sku_id, window)``. **Drop**
        ``line_id``, ``start_hour``, ``shift_definition`` — those are JDA's
        *solution*, not the demand.

    For ``source = "whatif_usuario"``:
        Accept a tuple of ``DemandBucket`` directly from the UI.
    """

    async def build_demand(
        self,
        source: Source,
        clean_dir: Path,
        window: WindowConfig | None = None,             # default WindowConfig(days=7)
        whatif_extra: tuple[DemandBucket, ...] | None = None,
    ) -> tuple[DemandBucket, ...]:
        ...

    async def to_csv(
        self,
        demand: tuple[DemandBucket, ...],
        out_path: Path,
    ) -> Path:
        """Persist a ``DemandBucket`` tuple to ``demand.csv``."""
        ...
