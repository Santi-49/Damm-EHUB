"""ETL implementation — skeleton.

Implements ``ETLContract`` and ``DemandBuilderContract`` from
``packages.contracts.module.etl``.

This file is a placeholder. The hackathon team fills it in during M1 (Sat
morning). The structure should be:

* ``parsers/`` — one parser per raw-file family (OEE/Tiempo/Volumen/Mant., Cambios, CF table, Planificado, Producción real)
* ``joins/`` — combine parsed dataframes into the eight clean CSVs
* ``demand_builder.py`` — the three ``build_demand`` source mappers

Until then importing this module just exposes the contract-shaped stubs so
the rest of the system can ``from services.etl.app.implementation import ETL``
without ImportError.
"""

from __future__ import annotations

from pathlib import Path

from packages.contracts.module.etl import (
    DemandBuilderContract,
    ETLContract,
    ETLResult,
)
from packages.contracts.module.schemas import DemandBucket, Source


class ETL(ETLContract, DemandBuilderContract):
    """Placeholder implementation. Fill in during M1."""

    async def build_clean_datasets(self, raw_dir: Path, out_dir: Path) -> ETLResult:
        raise NotImplementedError("ETL.build_clean_datasets — implement in M1")

    async def build_demand(
        self,
        source: Source,
        clean_dir: Path,
        whatif_extra: tuple[DemandBucket, ...] | None = None,
    ) -> tuple[DemandBucket, ...]:
        raise NotImplementedError("ETL.build_demand — implement in M1")

    async def to_csv(
        self,
        demand: tuple[DemandBucket, ...],
        out_path: Path,
    ) -> Path:
        raise NotImplementedError("ETL.to_csv — implement in M1")
