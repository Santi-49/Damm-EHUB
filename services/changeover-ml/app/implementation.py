"""Changeover ML implementation — skeleton.

Implements ``ChangeoverModelContract`` from
``packages.contracts.module.changeover_ml``.

The hackathon team fills this in once ETL milestone M1 lands and
``data/clean/executed_runs.csv`` + ``data/clean/changes_actual.csv`` are
available.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Mapping

from packages.contracts.module.changeover_ml import (
    ChangeoverModelContract,
    ChangeoverPrediction,
    TrainingData,
    TrainingResult,
    WalkForwardSplit,
)
from packages.contracts.module.schemas import LineId


class ChangeoverModel(ChangeoverModelContract):
    """Placeholder LightGBM-backed implementation. Fill in once ETL is ready."""

    async def fit(self, data: TrainingData, split: WalkForwardSplit) -> TrainingResult:
        raise NotImplementedError("ChangeoverModel.fit — implement after ETL M1")

    async def load(self, model_path: Path) -> None:
        raise NotImplementedError("ChangeoverModel.load — implement after ETL M1")

    async def predict(
        self,
        sku_from: str,
        sku_to: str,
        tren: LineId,
        context: Mapping[str, str | float | datetime] | None = None,
    ) -> ChangeoverPrediction:
        raise NotImplementedError("ChangeoverModel.predict — implement after ETL M1")

    async def predict_matrix(
        self,
        skus: tuple[str, ...],
        tren: LineId,
    ) -> dict[tuple[str, str], ChangeoverPrediction]:
        raise NotImplementedError("ChangeoverModel.predict_matrix — implement after ETL M1")
