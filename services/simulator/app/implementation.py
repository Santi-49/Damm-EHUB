"""Simulator implementation — skeleton.

Implements ``SimulatorContract`` from
``packages.contracts.module.simulator``. Fill in during M2 (Sat afternoon)
right after ETL lands the cleaned datasets.
"""

from __future__ import annotations

from packages.contracts.module.schemas import (
    CalendarConstraint,
    Incident,
    Sequence,
    SimulationReport,
    SkuLineCapability,
)
from packages.contracts.module.simulator import SimulatorContract


class Simulator(SimulatorContract):
    """Deterministic OEE simulator. Fill in during M2."""

    async def evaluate_sequence(
        self,
        sequence: Sequence,
        capability: tuple[SkuLineCapability, ...],
        calendar: tuple[CalendarConstraint, ...],
        incidents: tuple[Incident, ...],
    ) -> SimulationReport:
        raise NotImplementedError("Simulator.evaluate_sequence — implement in M2")

    async def detect_infeasibility(
        self,
        sequence: Sequence,
        calendar: tuple[CalendarConstraint, ...],
    ) -> bool:
        raise NotImplementedError("Simulator.detect_infeasibility — implement in M2")
