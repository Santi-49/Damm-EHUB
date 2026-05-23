"""Contract for the graph-based optimiser (Architecture D).

In plain words
--------------

Given a *complete graph* whose:

* **Nodes** are SKU chunks to be produced. Each node carries a per-line
  production time (``run_time + ramp_up``) computed from
  ``sku_line_capability.csv``.
* **Edges** are changeover times between SKUs, **line-specific** (the same
  pair has a different cost on each line) and **provided by the ML predictor**
  (``ChangeoverModelContract``), with the ``Tabla CF Prat`` matrix as the
  theoretical floor.
* **Line capability** is a hard constraint:

      L14 -> only 1/2 (50 cl) and 1/3 (33 cl) cans
      L17 -> only 1/3 (33 cl) cans
      L19 -> 1/2 (50 cl), 1/3 (33 cl) and 2/5 (44 cl) cans

  Nodes that cannot run on a line have no edges to/from that line.
* **Forced events** (Friday cleaning 8 h, Monday-biweekly maintenance 8 h, any
  injected breakdown) are forced visits with time windows.

The optimiser must return:

1. A partitioning of the demand nodes into three subgraphs (one per line),
   respecting capability.
2. An ordered path inside each subgraph (which SKU runs first, second, …).

Objective: **minimise the maximum total time across the three lines**
(``makespan``), with an ``epsilon``-weighted sum-of-times tie-breaker so the
solver doesn't leave a line idle.

Infeasibility
-------------

If demand exceeds capacity (e.g. after a breakdown), every demand node becomes
*disjunctive*: visiting it is optional with penalty ``margen[sku] * uds_chunk``.
The solver drops the lowest-margin SKUs first without any code branch.
``OptimizerOutput.feasible`` is then ``False`` and ``dropped`` lists what was
left out.
"""

from __future__ import annotations

from typing import Protocol

from .changeover_ml import ChangeoverModelContract
from .schemas import OptimizerInput, OptimizerOutput, Sequence


class GraphOptimizerContract(Protocol):
    """The Architecture D solver.

    The implementation owns the OR-Tools VRP model, but the contract is
    deliberately solver-agnostic so a future ILP / heuristic implementation
    can plug in unchanged.

    Invariants the implementation MUST guarantee:

    * Every SKU in ``inputs.demand`` either appears in the returned sequence
      (sum of ``uds_planificadas`` >= ``uds_demanded``) or appears in
      ``output.dropped``.
    * Every slot in the returned sequence respects ``sku_line_capability``:
      ``can_produce(slot.sku, slot.tren)`` must be ``True``.
    * Forced calendar events from ``inputs.calendar`` are present in the
      sequence at their declared windows.
    * ``output.makespan_h`` equals ``max(output.makespan_per_line_h.values())``.
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
        """Re-plan in flight after a perturbation (breakdown, urgent demand).

        Implementations must:
        * Respect ``inputs.hyperparams.freeze_days`` — the first N days of
          ``previous`` are taken as fixed.
        * Use the same objective as ``optimize`` so dropouts remain consistent.
        """
        ...
