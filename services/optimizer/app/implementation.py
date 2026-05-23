"""Graph optimiser implementation — skeleton.

Implements ``GraphOptimizerContract`` from
``packages.contracts.module.optimizer``. The hackathon team wires this up
during milestone M4 (Sunday morning) once ETL + ML are ready.

Until then this file documents the intended structure for OR-Tools VRP so
downstream callers can ``from services.optimizer.app.implementation import
GraphOptimizer`` without ImportError.
"""

from __future__ import annotations

from packages.contracts.module.changeover_ml import ChangeoverModelContract
from packages.contracts.module.optimizer import GraphOptimizerContract
from packages.contracts.module.schemas import (
    OptimizerInput,
    OptimizerOutput,
    Sequence,
)


class GraphOptimizer(GraphOptimizerContract):
    """OR-Tools VRP-backed optimiser. Fill in during M4."""

    async def optimize(
        self,
        inputs: OptimizerInput,
        ml: ChangeoverModelContract,
    ) -> OptimizerOutput:
        raise NotImplementedError("GraphOptimizer.optimize — implement in M4")

    async def replan(
        self,
        previous: Sequence,
        inputs: OptimizerInput,
        ml: ChangeoverModelContract,
    ) -> OptimizerOutput:
        raise NotImplementedError("GraphOptimizer.replan — implement in M5")
