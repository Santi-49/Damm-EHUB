"""Contract for the deterministic simulator.

Takes any ``Sequence`` (real or proposed) and computes OEE-style metrics.
It is the only component that emits OEE — the optimiser never predicts it.

Three properties define correctness:

1. **Determinism** — same inputs ⇒ same outputs. No sampling.
2. **Historical fidelity** — fed ``S_real``, the per-line OEE must reproduce
   historical observations within 5%.
3. **Replay fairness** — incidents are anchored to ``(line_id, start_ts)`` and
   applied identically to ``S_real`` and ``S_opt``.
"""

from __future__ import annotations

from typing import Protocol

from .schemas import (
    Incident,
    LineCalendarEvent,
    LineCapability,
    Sequence,
    SimulationReport,
)


class SimulatorContract(Protocol):
    """Score a proposed schedule.

    Inputs:

    * ``sequence``   — schedule to evaluate.
    * ``capability`` — ``line_capability.csv`` for ``median_speed_uds_per_hour`` lookups.
    * ``calendar``   — ``line_calendar.csv`` for forced cleaning + maintenance.
    * ``incidents``  — ``incidents.csv`` rows to replay deterministically.

    Output: a :class:`SimulationReport` with per-line and global metrics
    (OEE, hour decomposition, coverage, makespan, unproduced units).
    """

    async def evaluate_sequence(
        self,
        sequence: Sequence,
        capability: tuple[LineCapability, ...],
        calendar: tuple[LineCalendarEvent, ...],
        incidents: tuple[Incident, ...],
    ) -> SimulationReport:
        ...

    async def detect_infeasibility(
        self,
        sequence: Sequence,
        calendar: tuple[LineCalendarEvent, ...],
    ) -> bool:
        """Return ``True`` when the sequence cannot fit in the calendar.

        Used by the optimiser/UI to decide when to re-invoke optimisation with
        disjunctions enabled. The simulator never *decides* what to drop.
        """
        ...
