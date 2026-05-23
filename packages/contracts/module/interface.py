"""Back-compat single-import surface.

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
    SKU,
    ChangeoverEdge,
    ChangeoverSegment,
    DemandBucket,
    EdgeSource,
    Format,
    Incident,
    LineCalendarEvent,
    LineCapability,
    LineId,
    LineMetrics,
    OptimizerHyperparams,
    OptimizerInput,
    OptimizerOutput,
    Sequence,
    SimulationReport,
    Slot,
    SlotType,
    Source,
    WindowConfig,
)
from .simulator import SimulatorContract

__all__ = [
    # Domain primitives
    "ChangeoverSegment",
    "EdgeSource",
    "Format",
    "LineId",
    "SlotType",
    "Source",
    "WindowConfig",
    # Dataclasses
    "SKU",
    "ChangeoverEdge",
    "ChangeoverPrediction",
    "DemandBucket",
    "ETLResult",
    "Incident",
    "LineCalendarEvent",
    "LineCapability",
    "LineMetrics",
    "OptimizerHyperparams",
    "OptimizerInput",
    "OptimizerOutput",
    "Sequence",
    "SimulationReport",
    "Slot",
    "TrainingData",
    "TrainingResult",
    "WalkForwardSplit",
    # Protocols
    "ChangeoverModelContract",
    "DemandBuilderContract",
    "ETLContract",
    "GraphOptimizerContract",
    "SimulatorContract",
]
