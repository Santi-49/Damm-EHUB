"""Contracts for the ETL functionality.

Split into two protocols so the demand-builder can be tested without re-running
the (slow) Excel parsing on every iteration:

* ``ETLContract``           — raw ``data/raw/*.xlsx`` → tidy ``data/clean/*.csv``
* ``DemandBuilderContract`` — tidy CSVs → ``demand.csv`` for the optimiser

Implementations live in ``services/etl/``. See its ``README.md`` for the prose
restatement of these contracts.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from .schemas import DemandBucket, Source


@dataclass(frozen=True)
class ETLResult:
    """Summary of an ETL run."""

    clean_dir: Path
    rows_per_table: dict[str, int]               # e.g. {"executed_runs": 2274, "sku_master": 170}
    discarded_files: tuple[str, ...]             # files we intentionally skipped
    warnings: tuple[str, ...]                    # surfaced data-quality issues


class ETLContract(Protocol):
    """Turn raw Excel exports into the canonical clean CSV set.

    Output files produced in ``out_dir`` (see ``docs/linewise/datos.md`` §3):

    * ``executed_runs.csv``            joined OEE + Tiempo + Volumen + Mantenimiento
    * ``changes_actual.csv``           per-WO changeover flags
    * ``sku_master.csv``               deduped SKU attributes
    * ``sku_line_capability.csv``      ``can_produce``, ``speed_median_uds_h``, ``oee_median``
    * ``changeover_matrix.csv``        theoretical + empirical edges (hybrid where supported)
    * ``calendar_constraints.csv``     cleaning + maintenance rules per line
    * ``incident_log.csv``             deterministic-replay incidents anchored to ``(tren, instante)``
    * ``weekly_actual_v2026_05.csv``   ground truth for the demo week

    Invariants:

    * The implementation MUST NOT modify files under ``raw_dir``.
    * Discarded inputs (``data - 2026-05-18….xlsx``, ``Diario Hl_Planif.xlsx``)
      must be reported in ``ETLResult.discarded_files``.
    * Data-quality warnings (OEE > 1, ``H. Tot.`` outliers, ``Calidad`` != 1, ...)
      must be surfaced in ``ETLResult.warnings`` — do NOT silently clip values.
    """

    async def build_clean_datasets(self, raw_dir: Path, out_dir: Path) -> ETLResult:
        ...


class DemandBuilderContract(Protocol):
    """Re-aggregate any planning source to weekly demand buckets.

    The optimiser only consumes ``demand.csv``; this contract is the only place
    that knows where demand comes from (historical 2025, JDA plan 2026, what-if
    form, …).

    For ``source = "historico_2025"``:
        Read ``executed_runs.csv``. Drop ``SKU = LIMPIEZA``. Derive ``window_id``
        (ISO week) from ``fecha_fin``. Sum ``uds`` per ``(sku, window)``.

    For ``source = "plan_2026"``:
        Read ``Planificado - producciones 14 - 17 - 19.XLSX``. Normalise
        ``Cntd plan`` (CAJ via ``unidad_por_caja``, UN as-is). Derive
        ``window_id`` from ``fecha_ini``. Sum per ``(sku, window)``.
        **Drop** ``tren``, ``hora_ini``, ``definicion_de_turno`` — those are
        the planner's *solution*, not the demand.

    For ``source = "whatif_usuario"``:
        Accept a list of ``DemandBucket`` directly from the UI.

    Output: a list of ``DemandBucket`` ready to feed the optimiser.
    """

    async def build_demand(
        self,
        source: Source,
        clean_dir: Path,
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
