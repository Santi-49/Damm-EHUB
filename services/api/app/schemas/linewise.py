"""Pydantic schemas for the /linewise/* endpoints.

Field names follow the LINEWISE_API_CONTRACT.md spec exactly.
Percentages are fractions in [0, 1]. Line IDs are int literals 14/17/19.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Shared primitives
# ---------------------------------------------------------------------------

LineId = Literal[14, 17, 19]
SlotKind = Literal["production", "changeover", "cleaning", "maintenance"]
ChangeoverSourceApi = Literal["ml", "hibrido", "teorico"]


class ChangeoverDriver(BaseModel):
    feature: str
    impact_h: float


# ---------------------------------------------------------------------------
# Weeks
# ---------------------------------------------------------------------------

class WeekOption(BaseModel):
    id: str
    label: str
    range: str
    source: Literal["demo", "historical"]
    reason: str
    production_rows: Optional[int] = None
    sku_count: Optional[int] = None
    units: Optional[int] = None
    avg_oee: Optional[float] = None
    downtime_h: Optional[float] = None


# ---------------------------------------------------------------------------
# Sequence / Slots
# ---------------------------------------------------------------------------

class Slot(BaseModel):
    id: str
    line: LineId
    start: str
    end: str
    kind: SlotKind
    sku: Optional[str] = None
    label: Optional[str] = None
    units: Optional[int] = None
    oee_expected: Optional[float] = None
    oee_actual: Optional[float] = None
    changeover_h: Optional[float] = None
    changeover_source: Optional[ChangeoverSourceApi] = None
    changeover_drivers: Optional[list[ChangeoverDriver]] = None


class Sequence(BaseModel):
    id: str
    week_id: str
    week_start: str
    week_end: str
    source: Literal["opt", "real", "replan"]
    slots: list[Slot]


# ---------------------------------------------------------------------------
# Simulation reports
# ---------------------------------------------------------------------------

class LineMetrics(BaseModel):
    line: LineId
    oee: float
    h_productive: float
    h_changeover: float
    h_cleaning: float
    h_maintenance: float
    h_idle: float
    coverage: float


class DroppedSku(BaseModel):
    sku: str
    units_demanded: int
    units_dropped: int
    margin_lost: float
    reason: str


class SimulationReport(BaseModel):
    sequence_id: str
    oee_global: float
    oee_per_line: list[LineMetrics]
    h_changes: float
    h_productive: float
    coverage: float
    makespan_h: float
    dropped_skus: list[DroppedSku]


# ---------------------------------------------------------------------------
# Delta
# ---------------------------------------------------------------------------

class DeltaMetrics(BaseModel):
    oee_pp: float
    h_changes_saved: float
    h_productive_gained: float
    coverage_delta: float


# ---------------------------------------------------------------------------
# Compare bundle (endpoint 2)
# ---------------------------------------------------------------------------

class CompareBundle(BaseModel):
    week: WeekOption
    solution_id: str
    real_sequence: Sequence
    opt_sequence: Sequence
    real_simulation: SimulationReport
    opt_simulation: SimulationReport
    delta: DeltaMetrics


# ---------------------------------------------------------------------------
# Optimize plan (endpoint 3)
# ---------------------------------------------------------------------------

class ProductDemand(BaseModel):
    sku_id: str
    quantity_units: int


class PlanOptimizeRequest(BaseModel):
    products: list[ProductDemand]


class PlanGraphNode(BaseModel):
    id: str
    label: str
    line_id: LineId
    family: str
    volume_hl: float


class PlanGraphEdge(BaseModel):
    id: str
    source: str
    target: str
    hours: float
    path: Literal["opt", "baseline"]


class PlanOptimizeResponse(BaseModel):
    nodes: list[PlanGraphNode]
    edges: list[PlanGraphEdge]
    makespan_h: float
    h_saved: float
    coverage_pct: float
    dropped_skus: list[str]
    sequence: Sequence
