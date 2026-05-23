"""Contract for the graph-based optimiser (Architecture D)."""

from __future__ import annotations

from typing import Protocol

from .changeover_ml import ChangeoverModelContract
from .schemas import OptimizerInput, OptimizerOutput, Sequence


class GraphOptimizerContract(Protocol):
    """The Architecture D solver.

    Given a complete graph whose:

    * **Nodes** are SKU chunks. Node cost on a line is
      ``units_chunk / median_speed_uds_per_hour + ramp_up_hours``.
    * **Edges** are line-specific changeover hours supplied by
      :class:`ChangeoverModelContract` (clamped to the theoretical floor in
      ``changeover_costs.csv``).
    * **Capability** is a hard constraint (``line_capability.csv``):
        L14 -> 1/2 (50 cl) and 1/3 (33 cl)
        L17 -> 1/3 (33 cl) only
        L19 -> 1/2, 1/3, 2/5 (44 cl)
    * **Forced events** (Friday cleaning, Monday-biweekly maintenance, injected
      breakdowns) live in ``line_calendar.csv`` and are visits with time windows.

    Find:

    1. A partition of demand nodes across the three lines (subgraphs) that
       respects capability.
    2. The ordered path inside each subgraph.

    Objective: minimise the **maximum total time across the three lines**
    (``makespan``), with an ``epsilon``-weighted sum-of-times tie-breaker so a
    line isn't left idle.

    Infeasibility: every demand node is disjunctive with penalty
    ``margin_per_sku[sku_id] * units_chunk``. The solver drops the
    cheapest-margin SKUs first; ``OptimizerOutput.feasible == False`` and the
    drops show up in ``OptimizerOutput.dropped``.

    Implementations MUST guarantee:

    * Every SKU in ``inputs.demand`` either appears in the returned sequence
      with sufficient ``units_planned`` or appears in ``output.dropped``.
    * Every slot respects ``line_capability``:
      ``can_produce(slot.sku_id, slot.line_id) == True``.
    * Forced calendar events from ``inputs.calendar`` appear in the sequence
      at their declared windows.
    * ``output.makespan_hours == max(output.makespan_per_line_hours.values())``.
    """

    async def optimize(
        self,
        inputs: OptimizerInput,
        ml: ChangeoverModelContract,
    ) -> OptimizerOutput:
        ...

    async def replan(
        self,
        previous: Sequence,
        inputs: OptimizerInput,
        ml: ChangeoverModelContract,
    ) -> OptimizerOutput:
        """Re-plan after a perturbation (breakdown, urgent demand).

        Must respect ``inputs.hyperparams.freeze_days`` — the first N days of
        ``previous`` are fixed. Must use the same objective as
        :meth:`optimize` so dropouts stay consistent.
        """
        ...
