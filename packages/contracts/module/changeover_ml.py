"""Contract for the changeover-time ML predictor.

The model has **one job**: given two SKUs and a line, predict the changeover
time in hours, split into segments (brand change, container change, …) that
sum to the total. It does NOT predict OEE — that is computed by the
simulator post-hoc.

Why the segmented output matters:

* Each segment has an interpretable cause the planner recognises.
* The sum-equals-total invariant ``sum(segments.values()) == total_hours`` is
  a built-in sanity check — if a model violates it, training data is leaking.
* SHAP attribution on each segment is far more actionable than on the total.

Why the scope stays narrow:

* The target is observable in history: ``empirical_changeover_h`` (the ``PNP``
  chunk that precedes marcha, validated against the ``C.*`` flags from
  ``Cambios``) → walk-forward validation is straightforward.
* No leakage risk into the OEE path — the optimiser uses these predictions as
  edge weights, and the simulator separately computes OEE.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Mapping, Protocol

from .schemas import ChangeoverSegment, EdgeSource, LineId


@dataclass(frozen=True)
class TrainingData:
    """Reference to the tabular training set produced by ETL.

    Each row of ``edge_cost_train.csv`` is one observed transition with both
    ``total_changeover_hours`` and per-``ChangeoverSegment`` columns.
    """

    rows_csv: Path
    feature_columns: tuple[str, ...]
    target_total_column: str = "total_changeover_hours"
    target_segment_columns: tuple[str, ...] = (
        "segment_brand_hours",
        "segment_container_hours",
        "segment_cap_hours",
        "segment_primary_pack_hours",
        "segment_secondary_pack_hours",
        "segment_pallet_hours",
        "segment_product_hours",
        "segment_volume_hours",
        "segment_startup_hours",
        "segment_shutdown_hours",
    )


@dataclass(frozen=True)
class WalkForwardSplit:
    """Time-based split. Train on windows < ``cutoff``, validate on windows >= cutoff."""

    cutoff_window_id: str                    # e.g. "2025-W30-7d"


@dataclass(frozen=True)
class TrainingResult:
    model_path: Path
    mae_hours_total: float
    rmse_hours_total: float
    r2_total: float
    mae_hours_per_segment: Mapping[ChangeoverSegment, float]
    n_train: int
    n_val: int
    feature_importance: Mapping[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class ChangeoverPrediction:
    """One prediction with the segmented breakdown.

    Invariant: ``round(sum(segments.values()), 6) == round(total_hours, 6)``.
    """

    sku_from_id: str
    sku_to_id: str
    line_id: LineId
    total_hours: float
    segments: Mapping[ChangeoverSegment, float]
    confidence: float                        # 0..1; falls back to theoretical when low
    source: EdgeSource                       # 'ml' | 'hibrido' | 'teorico'


class ChangeoverModelContract(Protocol):
    """Train, persist, and serve changeover-time predictions.

    Operating mode (per ``(sku_from, sku_to, line_id)`` triple):

    * >= 5 historical observations → ML prediction (``source = "ml"``).
    * 1..4 observations            → blend with theoretical (``source = "hibrido"``).
    * 0 observations               → fall back to ``Tabla CF Prat`` (``source = "teorico"``).

    The optimiser may additionally clamp the returned hours to the theoretical
    floor — that policy lives in ``services/optimizer/``.
    """

    async def fit(
        self,
        data: TrainingData,
        split: WalkForwardSplit,
    ) -> TrainingResult:
        ...

    async def load(self, model_path: Path) -> None:
        ...

    async def predict(
        self,
        sku_from_id: str,
        sku_to_id: str,
        line_id: LineId,
        context: Mapping[str, str | float | datetime] | None = None,
    ) -> ChangeoverPrediction:
        ...

    async def predict_matrix(
        self,
        sku_ids: tuple[str, ...],
        line_id: LineId,
    ) -> dict[tuple[str, str], ChangeoverPrediction]:
        """Bulk variant for the optimiser's graph construction."""
        ...
