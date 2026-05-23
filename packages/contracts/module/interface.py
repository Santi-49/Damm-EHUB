"""Back-compat single-import surface.

The original template documented ``packages.contracts.module.interface`` as the
contract location. LineWise grew into five focused protocols, but importers
that still reach for ``interface`` continue to work via these re-exports.

Prefer importing the focused modules directly:

    from packages.contracts.module.optimizer import GraphOptimizerContract
    from packages.contracts.module.simulator import SimulatorContract
"""

from .changeover_ml import (
    ChangeoverModelContract,
    ChangeoverPrediction,
    TrainingData,
    TrainingResult,
    WalkForwardSplit,
)
from .etl import DemandBuilderContract, ETLContract, ETLResult
from .optimizer import GraphOptimizerContract
from .schemas import (
    CalendarConstraint,
    ChangeoverEdge,
    DemandBucket,
    EdgeSource,
    Format,
    Incident,
    LineId,
    LineMetrics,
    OptimizerHyperparams,
    OptimizerInput,
    OptimizerOutput,
    Sequence,
    SimulationReport,
    SKU,
    SkuLineCapability,
    Slot,
    SlotType,
    Source,
)
from .simulator import SimulatorContract

__all__ = [
    # Domain primitives
    "Format",
    "LineId",
    "Source",
    "SlotType",
    "EdgeSource",
    # Dataclasses
    "SKU",
    "DemandBucket",
    "SkuLineCapability",
    "ChangeoverEdge",
    "CalendarConstraint",
    "Incident",
    "Slot",
    "Sequence",
    "OptimizerHyperparams",
    "OptimizerInput",
    "OptimizerOutput",
    "LineMetrics",
    "SimulationReport",
    "TrainingData",
    "TrainingResult",
    "WalkForwardSplit",
    "ChangeoverPrediction",
    "ETLResult",
    # Protocols
    "ETLContract",
    "DemandBuilderContract",
    "ChangeoverModelContract",
    "GraphOptimizerContract",
    "SimulatorContract",
]
