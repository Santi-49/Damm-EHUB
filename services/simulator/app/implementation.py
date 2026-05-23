"""Simulator implementation — skeleton."""

from __future__ import annotations

from packages.contracts.module.schemas import (
    Incident,
    LineCalendarEvent,
    LineCapability,
    Sequence,
    SimulationReport,
)
from packages.contracts.module.simulator import SimulatorContract


class Simulator(SimulatorContract):
    """Deterministic OEE simulator. Fill in during M2."""

    async def evaluate_sequence(
        self,
        sequence: Sequence,
        capability: tuple[LineCapability, ...],
        calendar: tuple[LineCalendarEvent, ...],
        incidents: tuple[Incident, ...],
    ) -> SimulationReport:
        raise NotImplementedError("Simulator.evaluate_sequence — implement in M2")

    async def detect_infeasibility(
        self,
        sequence: Sequence,
        calendar: tuple[LineCalendarEvent, ...],
    ) -> bool:
        raise NotImplementedError("Simulator.detect_infeasibility — implement in M2")
