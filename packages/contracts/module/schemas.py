"""Shared dataclasses used across every LineWise contract.

These types are the on-the-wire schema between ETL, ML, optimizer, simulator
and UI. Keep them framework-agnostic (plain ``dataclass``, no Pydantic) so the
optimizer and simulator can be tested without spinning up FastAPI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Literal

# ---------------------------------------------------------------------------
# Domain primitives
# ---------------------------------------------------------------------------

LineId = Literal[14, 17, 19]
"""Damm canning lines in scope: L14, L17, L19."""

Format = Literal["1/2", "1/3", "2/5"]
"""Can formats: 50cl (1/2), 33cl (1/3), 44cl (2/5).

Line capability (hard):
    L14 -> {"1/2", "1/3"}
    L17 -> {"1/3"}
    L19 -> {"1/2", "1/3", "2/5"}
"""

Source = Literal["historico_2025", "plan_2026", "whatif_usuario"]
SlotType = Literal["produccion", "limpieza", "mantenimiento", "cambio"]
EdgeSource = Literal["teorico", "empirico", "hibrido", "ml"]


# ---------------------------------------------------------------------------
# SKU catalogue
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SKU:
    """Static attributes of a SKU (rows are deduped from ``executed_runs``)."""

    sku_id: str
    format: Format
    marca: str
    familia: str
    cerveza: str
    tipo_envase: str
    mat_precio: str
    packaging_primario: str | None
    packaging_secundario: str | None
    uds_por_caja: float | None


# ---------------------------------------------------------------------------
# Demand
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DemandBucket:
    """One row of ``demand.csv``: how many units of one SKU to produce in one ISO week.

    The optimiser decides *which line*, *which day* and *which turn* — these
    fields are deliberately absent from the schema.
    """

    window_id: str            # e.g. "2025-W18"
    window_start: date        # inclusive Monday
    window_end: date          # inclusive Sunday
    sku: str
    uds_demanded: int         # >= 0
    source: Source = "historico_2025"
    prioridad: int = 3        # 1-5; 5 = cannot be dropped


# ---------------------------------------------------------------------------
# Line capability and changeovers
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SkuLineCapability:
    """Whether a SKU can run on a line, and how fast it runs there on average."""

    sku: str
    tren: LineId
    can_produce: bool                # hard gate (format compatibility + history)
    speed_median_uds_h: float        # median over historical WOs
    oee_median: float                # median OEE on this (sku, line) pair
    n_wos_historico: int             # support — used to decide ML vs fallback


@dataclass(frozen=True)
class ChangeoverEdge:
    """Cost in hours of going from ``sku_from`` to ``sku_to`` on line ``tren``."""

    tren: LineId
    sku_from: str
    sku_to: str
    hours: float
    source: EdgeSource


# ---------------------------------------------------------------------------
# Calendar and incidents
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CalendarConstraint:
    """Forced event in a line's calendar (cleaning, maintenance, injected breakdown)."""

    tren: LineId
    regla_temporal: str                                       # e.g. "friday_weekly", "monday_biweekly"
    evento: Literal["limpieza", "mantenimiento", "averia"]
    duracion_h: float
    frecuencia: str                                           # human-readable
    fecha_ini: datetime | None = None                         # for one-off events (averías)


@dataclass(frozen=True)
class Incident:
    """Historical incident anchored to (line, instant). Used for deterministic replay."""

    tren: LineId
    instante_inicio: datetime
    duracion_h: float
    motivo: Literal["averia", "mantenimiento_no_planificado", "saturacion", "falta_producto", "otro"]
    of_origen: str | None = None                              # WO that surfaced the incident


# ---------------------------------------------------------------------------
# Sequence (optimiser output)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Slot:
    """One row of ``sequence.csv`` — the optimiser's atomic output."""

    slot_id: str
    tren: LineId
    sku: str
    fecha_inicio: datetime
    fecha_fin: datetime
    uds_planificadas: int
    tipo: SlotType
    sku_prev: str | None = None
    coste_cambio_h: float | None = None
    oee_esperado: float | None = None


@dataclass(frozen=True)
class Sequence:
    """A full proposed schedule: ordered slots grouped logically by line."""

    slots: tuple[Slot, ...]
    horizon_start: date
    horizon_end: date

    def for_line(self, tren: LineId) -> tuple[Slot, ...]:
        return tuple(s for s in self.slots if s.tren == tren)


# ---------------------------------------------------------------------------
# Hyperparameters
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class OptimizerHyperparams:
    """Tunables loaded from ``data/clean/optimizer_hyperparams.yaml``."""

    horizon_days: int = 7
    freeze_days: int = 0
    lambda_changeover: float = 1.0
    mu_demanda_no_cubierta: float = 1.0
    nu_beneficio: float = 1.0
    chunk_max_productive_h: float = 8.0
    margen_per_sku: dict[str, float] = field(default_factory=dict)        # default 1.0 if absent


# ---------------------------------------------------------------------------
# Simulator output
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LineMetrics:
    tren: LineId
    horas_totales: float
    horas_productivas: float
    horas_cambio: float
    horas_limpieza: float
    horas_mantenimiento: float
    horas_incidentes: float
    horas_baja_velocidad: float
    oee_semana: float
    coverage_pct: float
    makespan_h: float                                          # time when last slot ends


@dataclass(frozen=True)
class SimulationReport:
    """Output of ``Simulator.evaluate_sequence``."""

    per_line: dict[LineId, LineMetrics]
    oee_ponderado_global: float
    horas_productivas_total: float
    horas_cambio_total: float
    coverage_pct_global: float
    makespan_h_global: float
    uds_no_producidas: dict[str, int]                          # sku -> uds dropped


# ---------------------------------------------------------------------------
# Optimizer input/output bundles
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class OptimizerInput:
    demand: tuple[DemandBucket, ...]
    capability: tuple[SkuLineCapability, ...]
    changeovers: tuple[ChangeoverEdge, ...]
    calendar: tuple[CalendarConstraint, ...]
    hyperparams: OptimizerHyperparams


@dataclass(frozen=True)
class OptimizerOutput:
    sequence: Sequence
    makespan_per_line_h: dict[LineId, float]
    makespan_h: float                                          # max over lines
    dropped: tuple[tuple[str, int], ...]                       # (sku, uds_not_produced)
    feasible: bool                                             # False -> dropouts happened
    solver_log: str | None = None
