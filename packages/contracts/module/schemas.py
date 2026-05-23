"""Shared dataclasses used across every LineWise contract.

These are the on-the-wire types between ETL, ML, optimiser, simulator and UI.
They are deliberately framework-agnostic (plain ``dataclass``, no Pydantic)
so the optimiser and simulator can be unit-tested without spinning up FastAPI.

Column / field names follow English snake_case. The mapping back to the
original Damm Spanish columns lives in each data-product README under
``docs/data/`` so the lineage is one click away.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Literal, Mapping

# ---------------------------------------------------------------------------
# Domain primitives
# ---------------------------------------------------------------------------

LineId = Literal[14, 17, 19]
"""Damm canning lines in scope. Was ``TREN`` in the source files."""

Format = Literal["1/2", "1/3", "2/5"]
"""Can formats: 50 cl (1/2), 33 cl (1/3), 44 cl (2/5).

Line capability (hard constraint, enforced in ``line_capability.csv``):
    L14 -> {"1/2", "1/3"}
    L17 -> {"1/3"}
    L19 -> {"1/2", "1/3", "2/5"}
"""

Source = Literal["historico_2025", "plan_2026", "whatif_usuario"]
SlotType = Literal["produccion", "limpieza", "mantenimiento", "cambio"]
EdgeSource = Literal["teorico", "empirico", "hibrido", "ml"]

# Changeover segments. Mapped from the ``C.*`` boolean flags in
# ``Cambios 14_17_19_ 2025.xlsx``. ``segments[name] = hours`` means "this many
# hours of the total changeover came from this kind of change".
ChangeoverSegment = Literal[
    "brand",          # C. Brand
    "container",      # C. Envase
    "cap",            # C. CAP
    "primary_pack",   # C. Primario
    "secondary_pack", # C. Secundario
    "pallet",         # C. Palet
    "product",        # C. Producto
    "volume",         # C. Volum
    "startup",        # arranque (constant per line)
    "shutdown",       # final (constant per line)
]


# ---------------------------------------------------------------------------
# Time window
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class WindowConfig:
    """Time-window for demand aggregation and optimiser planning horizon.

    Defaults to 7-day Monday-anchored windows — matches Damm's weekly planning
    rhythm. The optimiser plans **one window at a time**, so this also fixes
    the horizon for a single ``optimize()`` call. For longer horizons, the
    caller chains multiple optimisations.

    * ``days``        — bucket size in days (>= 1). Default 7.
    * ``anchor``      — how to align bucket boundaries to the calendar.
                        ``"monday"`` aligns to ISO week, ``"fixed_start"``
                        starts from ``start_date``.
    * ``start_date``  — only used when ``anchor == "fixed_start"``.
    """

    days: int = 7
    anchor: Literal["monday", "fixed_start"] = "monday"
    start_date: date | None = None

    def __post_init__(self) -> None:
        if self.days < 1:
            raise ValueError(f"WindowConfig.days must be >= 1, got {self.days}")
        if self.anchor == "fixed_start" and self.start_date is None:
            raise ValueError("WindowConfig.anchor='fixed_start' requires start_date")


# ---------------------------------------------------------------------------
# SKU catalogue (skus.csv)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SKU:
    """One row of ``skus.csv``. Deduped from ``wo_master.csv``."""

    sku_id: str                              # was SKU
    container_type: Format                   # was Tipo Envase
    brand: str                               # was Marca
    family: str                              # was Familia
    supra_brand: str                         # was Supramarca
    beer: str                                # was Cerveza
    material_id: str                         # was ID Material Precio
    material_label: str                      # was Mat. Precio
    container: str                           # was Envase
    primary_packaging: str | None            # was Packaging Primario
    secondary_packaging: str | None          # was Packaging Secundario
    pallet_type: str | None                  # was Tipo Palet
    units_per_case: float | None             # was Unidad/caja


# ---------------------------------------------------------------------------
# Demand (demand.csv)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DemandBucket:
    """One row of ``demand.csv``: units of one SKU to produce in one window.

    The optimiser decides ``line_id``, day and turn — these are absent here on
    purpose. Window size is governed by :class:`WindowConfig`.
    """

    window_id: str                           # e.g. "2025-W18-7d"
    window_start: date                       # inclusive
    window_end: date                         # inclusive
    sku_id: str
    units_demanded: int                      # >= 0; was uds_demanded
    source: Source = "historico_2025"
    priority: int = 3                        # 1..5; 5 means cannot be dropped


# ---------------------------------------------------------------------------
# Line capability (line_capability.csv)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LineCapability:
    """One row of ``line_capability.csv``: whether ``sku_id`` runs on ``line_id``,
    and how fast / well on average. Materialised because (a) it's a hard
    optimiser gate and (b) the optimiser uses ``median_speed`` as the node-cost
    fallback when ML node-cost is not yet available.
    """

    sku_id: str
    line_id: LineId
    can_produce: bool                        # hard gate; respects format constraint
    median_speed_uds_per_hour: float         # from wo_master.units_produced / productive_hours
    median_oee: float                        # from wo_master.oee
    n_workorders_observed: int               # support; informs ML vs fallback decision


# ---------------------------------------------------------------------------
# Changeovers (changeover_costs.csv and edge_cost_train.csv)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ChangeoverEdge:
    """Cost in hours of going from ``sku_from_id`` to ``sku_to_id`` on ``line_id``.

    Fused theoretical (from ``Tabla CF Prat``) + empirical / ML. ``segments``
    breaks the total down by which kind of change drives the cost. The
    invariant ``sum(segments.values()) == total_hours`` is enforced by the
    ETL / ML producers — consumers may assume it.
    """

    line_id: LineId
    sku_from_id: str
    sku_to_id: str
    total_hours: float
    segments: Mapping[ChangeoverSegment, float]
    source: EdgeSource


# ---------------------------------------------------------------------------
# Calendar (line_calendar.csv)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LineCalendarEvent:
    """One row of ``line_calendar.csv``: a forced event in a line's calendar.

    Two flavours:
    * **Recurring** rules (cleaning Friday 8 h, maintenance Monday biweekly 8 h)
      → ``recurrence`` set, ``start_ts`` is ``None``.
    * **One-off** events (injected breakdown, ad-hoc maintenance) →
      ``start_ts`` set, ``recurrence`` ignored.
    """

    line_id: LineId
    event_type: Literal["cleaning", "maintenance", "breakdown"]
    duration_hours: float
    recurrence: str | None = None            # e.g. "weekly:friday", "biweekly:monday"
    start_ts: datetime | None = None         # for one-off events


# ---------------------------------------------------------------------------
# Incidents (incidents.csv — used by simulator, not optimiser)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Incident:
    """Historical incident anchored to ``(line_id, start_ts)`` for fair replay."""

    line_id: LineId
    start_ts: datetime
    duration_hours: float
    cause: Literal[
        "breakdown",
        "unplanned_maintenance",
        "downstream_block",
        "upstream_starve",
        "other",
    ]
    source_wo_id: str | None = None          # the WO that surfaced the incident


# ---------------------------------------------------------------------------
# Sequence (optimiser output)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Slot:
    """One row of ``sequence.csv`` — the optimiser's atomic output."""

    slot_id: str
    line_id: LineId
    sku_id: str
    start_ts: datetime
    end_ts: datetime
    units_planned: int
    slot_type: SlotType
    sku_prev_id: str | None = None
    changeover_hours: float | None = None
    expected_oee: float | None = None


@dataclass(frozen=True)
class Sequence:
    """Full proposed schedule for one planning window."""

    slots: tuple[Slot, ...]
    window_start: date
    window_end: date

    def for_line(self, line_id: LineId) -> tuple[Slot, ...]:
        return tuple(s for s in self.slots if s.line_id == line_id)


# ---------------------------------------------------------------------------
# Hyperparameters
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class OptimizerHyperparams:
    """Tunables loaded from ``data/clean/optimizer_hyperparams.yaml``.

    ``aggregation_window.days`` is the single time-window knob — it controls
    both demand-bucket size *and* the planning horizon for one ``optimize()``
    call. There is no separate ``horizon_days`` parameter.
    """

    aggregation_window: WindowConfig = field(default_factory=WindowConfig)
    freeze_days: int = 0
    lambda_changeover: float = 1.0
    mu_unmet_demand: float = 1.0
    nu_margin: float = 1.0
    chunk_max_productive_hours: float = 8.0
    margin_per_sku: Mapping[str, float] = field(default_factory=dict)    # default 1.0 if absent


# ---------------------------------------------------------------------------
# Simulator output
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LineMetrics:
    line_id: LineId
    total_hours: float
    productive_hours: float
    changeover_hours: float
    cleaning_hours: float
    maintenance_hours: float
    incident_hours: float
    low_speed_hours: float
    oee_window: float
    coverage_pct: float
    makespan_hours: float                    # time when last slot ends


@dataclass(frozen=True)
class SimulationReport:
    """Output of :meth:`SimulatorContract.evaluate_sequence`."""

    per_line: dict[LineId, LineMetrics]
    oee_weighted_global: float
    productive_hours_total: float
    changeover_hours_total: float
    coverage_pct_global: float
    makespan_hours_global: float
    unproduced_units: dict[str, int]         # sku_id -> units dropped


# ---------------------------------------------------------------------------
# Optimizer I/O bundles
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class OptimizerInput:
    demand: tuple[DemandBucket, ...]
    capability: tuple[LineCapability, ...]
    changeovers: tuple[ChangeoverEdge, ...]
    calendar: tuple[LineCalendarEvent, ...]
    hyperparams: OptimizerHyperparams


@dataclass(frozen=True)
class OptimizerOutput:
    sequence: Sequence
    makespan_per_line_hours: dict[LineId, float]
    makespan_hours: float                    # max over lines
    dropped: tuple[tuple[str, int], ...]     # (sku_id, units_not_produced)
    feasible: bool                           # False -> dropouts happened
    solver_log: str | None = None
