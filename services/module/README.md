# `services/module/` — legacy placeholder

> The template shipped with a single `services/module/` "challenge module" pattern.
> LineWise's challenge logic is large enough that we split it into **five sibling
> services**. This folder is kept as a pointer so the original [Module Contracts](../../docs/contracts.md)
> documentation still resolves; new code goes in the siblings below.

| What you want to touch | Where it lives |
|---|---|
| Raw Excel → clean CSV, weekly demand dataset | [`services/etl/`](../etl/) |
| ML predictor of changeover times | [`services/changeover_ml/`](../changeover_ml/) |
| Graph optimiser (Arch D, OR-Tools VRP) | [`services/optimizer/`](../optimizer/) |
| Deterministic OEE simulator | [`services/simulator/`](../simulator/) |
| FastAPI gateway that orchestrates the four above | [`services/api/`](../api/) |

System map: [`docs/architecture/linewise.md`](../../docs/architecture/linewise.md).
Functionality table: [`docs/functionalities/overview.md`](../../docs/functionalities/overview.md).
Contracts: [`packages/contracts/module/`](../../packages/contracts/module/).
