"""Contract for the changeover-time ML predictor.

The ML model has **one job**: given two SKUs and a line, predict the changeover
time in hours. It does NOT predict OEE. OEE is computed by the simulator after
the optimiser has chosen a sequence (see ``simulator.py``).

Why this scoping matters:

* The target is observable in history (``PNP`` chunk that precedes marcha plus
  changeover flags from ``Cambios``) → walk-forward validation is straightforward.
* The optimiser uses the prediction as an edge weight in its graph; clamping
  to the theoretical floor (``Tabla CF Prat``) is the implementation's
  responsibility, not the optimiser's.
* The ML target stays tabular (LightGBM / XGBoost work great) and explainable
  (SHAP on a single regression target).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Mapping, Protocol

from .schemas import EdgeSource, LineId


@dataclass(frozen=True)
class TrainingData:
    """Tabular rows derived from history with the empirical changeover time as target."""

    rows_csv: Path                    # one row per observed (sku_from, sku_to, tren, ...)
    feature_columns: tuple[str, ...]
    target_column: str = "changeover_time_h"


@dataclass(frozen=True)
class WalkForwardSplit:
    """Time-based split: train on weeks < ``cutoff``, validate on weeks >= ``cutoff``."""

    cutoff_week: str                  # ISO week, e.g. "2025-W30"


@dataclass(frozen=True)
class TrainingResult:
    model_path: Path
    mae_hours: float
    rmse_hours: float
    r2: float
    n_train: int
    n_val: int
    feature_importance: Mapping[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class ChangeoverPrediction:
    """Single prediction with metadata so the optimiser knows when to trust it."""

    sku_from: str
    sku_to: str
    tren: LineId
    hours: float
    confidence: float                  # 0..1; falls back to theoretical when low
    source: EdgeSource                 # 'ml' | 'hibrido' | 'teorico'


class ChangeoverModelContract(Protocol):
    """Train, persist, and serve changeover-time predictions.

    Operating mode:

    * If the (``sku_from``, ``sku_to``, ``tren``) pair has >= 5 historical
      observations → return the ML prediction (``source = "ml"``).
    * If 1..4 observations → blend ML with theoretical (``source = "hibrido"``).
    * If 0 observations → fall back to ``Tabla CF Prat`` (``source = "teorico"``).

    The optimiser is allowed to clamp the returned ``hours`` to the theoretical
    floor regardless of source — that policy lives in ``services/optimizer/``.
    """

    async def fit(
        self,
        data: TrainingData,
        split: WalkForwardSplit,
    ) -> TrainingResult:
        """Train and persist the model. Idempotent for the same ``data`` + ``split``."""
        ...

    async def load(self, model_path: Path) -> None:
        """Load a previously trained model. Required before any ``predict*`` call."""
        ...

    async def predict(
        self,
        sku_from: str,
        sku_to: str,
        tren: LineId,
        context: Mapping[str, str | float | datetime] | None = None,
    ) -> ChangeoverPrediction:
        """Predict hours for a single transition.

        ``context`` may include ``"day_of_week"``, ``"hour"``, ``"previous_oee"``,
        etc. Implementations are free to ignore unknown keys.
        """
        ...

    async def predict_matrix(
        self,
        skus: tuple[str, ...],
        tren: LineId,
    ) -> dict[tuple[str, str], ChangeoverPrediction]:
        """Bulk variant — populates every (sku_from, sku_to) pair the optimiser needs."""
        ...
