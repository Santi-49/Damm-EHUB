"""Contract for the deterministic simulator.

The simulator takes any sequence (real or proposed) and computes OEE-style
metrics. It is the **only** component that owns the OEE number reported to the
user — the optimiser never predicts OEE.

Three properties define correctness:

1. **Determinism**: same inputs → same outputs, every time. No sampling.
2. **Historical reproducibility**: when fed ``S_real`` (the historical
   sequence), the per-line OEE must reproduce the historically observed OEE
   within 5%.
3. **Replay fairness**: incidents in ``incident_log.csv`` are anchored to
   ``(tren, instante)`` and applied identically regardless of whether the
   slot belongs to ``S_real`` or ``S_opt`` — so the comparison is a fair fight.
"""

from __future__ import annotations

from typing import Protocol

from .schemas import (
    CalendarConstraint,
    Incident,
    Sequence,
    SimulationReport,
    SkuLineCapability,
)


class SimulatorContract(Protocol):
    """Score a proposed schedule.

    Inputs:

    * ``sequence``  — the schedule to evaluate (from the optimiser or from history).
    * ``capability`` — to look up ``speed_median_uds_h`` per ``(sku, tren)``.
    * ``calendar`` — to honour forced cleaning + maintenance.
    * ``incidents`` — list of ``Incident``, replayed deterministically.

    Output: ``SimulationReport`` with per-line and global metrics, including:

    * ``oee_semana`` per line and ``oee_ponderado_global``
    * Hours decomposed into productive / changeover / cleaning / maintenance /
      incidents / low-speed
    * ``coverage_pct`` — share of demanded units that ended up in the schedule
    * ``makespan_h`` per line and globally
    * ``uds_no_producidas`` — SKUs that were dropped (sourced from the optimiser
      output; the simulator does not decide what to drop)
    """

    async def evaluate_sequence(
        self,
        sequence: Sequence,
        capability: tuple[SkuLineCapability, ...],
        calendar: tuple[CalendarConstraint, ...],
        incidents: tuple[Incident, ...],
    ) -> SimulationReport:
        ...

    async def detect_infeasibility(
        self,
        sequence: Sequence,
        calendar: tuple[CalendarConstraint, ...],
    ) -> bool:
        """Return ``True`` when the proposed sequence cannot fit in the calendar.

        Used by the optimiser/UI to decide when to re-invoke optimisation with
        disjunctions enabled. The simulator never *decides* what to drop.
        """
        ...
