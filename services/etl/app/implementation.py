"""ETL implementation — skeleton.

Implements ``ETLContract`` and ``DemandBuilderContract``. Filled in during M1
(Sat morning). Structure once real:

* ``parsers/``     — one per raw-file family
* ``joins/``       — combine into the eight clean CSVs
* ``demand.py``    — the three :meth:`DemandBuilderContract.build_demand` source mappers
"""

from __future__ import annotations

from pathlib import Path

from packages.contracts.module.etl import (
    DemandBuilderContract,
    ETLContract,
    ETLResult,
)
from packages.contracts.module.schemas import DemandBucket, Source, WindowConfig


class ETL(ETLContract, DemandBuilderContract):
    """Placeholder. Fill in during M1."""

    async def build_clean_datasets(self, raw_dir: Path, out_dir: Path) -> ETLResult:
        raise NotImplementedError("ETL.build_clean_datasets — implement in M1")

    async def build_demand(
        self,
        source: Source,
        clean_dir: Path,
        window: WindowConfig | None = None,
        whatif_extra: tuple[DemandBucket, ...] | None = None,
    ) -> tuple[DemandBucket, ...]:
        raise NotImplementedError("ETL.build_demand — implement in M1")

    async def to_csv(
        self,
        demand: tuple[DemandBucket, ...],
        out_path: Path,
    ) -> Path:
        raise NotImplementedError("ETL.to_csv — implement in M1")
