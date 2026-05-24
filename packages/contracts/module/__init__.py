"""LineWise module contracts.

Each functionality of the LineWise solution exposes a Python ``Protocol`` that
the rest of the system depends on. Implementations live in ``services/<name>/``
and are imported by ``services/api/`` (or directly by the UI via REST).

Public surface:

- ``schemas`` — shared dataclasses (DemandBucket, Slot, SkuLineCapability, ...)
- ``etl`` — ``ETLContract`` + ``DemandBuilderContract``
- ``changeover_ml`` — ``ChangeoverModelContract``
- ``optimizer`` — ``GraphOptimizerContract``
- ``simulator`` — ``SimulatorContract``
- ``explainability`` — ``ExplainerContract`` + ``ExplanationPack`` (structured facts for chat)
- ``chat`` — ``ChatContract`` (LLM-powered grounded chat over an ExplanationPack)

See ``docs/architecture/linewise.md`` for the system-level diagram and
``docs/functionalities/overview.md`` for the workspace map.
"""

from . import changeover_ml, chat, etl, explainability, optimizer, schemas, simulator

__all__ = [
    "schemas",
    "etl",
    "changeover_ml",
    "optimizer",
    "simulator",
    "explainability",
    "chat",
]
