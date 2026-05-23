# Data

Confidential datasets for the LineWise (Damm × Engineering HUB) challenge.
**Nothing inside `raw/`, `clean/`, or `external/` is committed** — see `.gitignore`.

## Layout

| Folder | What lives here | Produced by |
|---|---|---|
| `raw/` | Original Excel files exactly as shared by Damm. **Never modify in place.** | Hackathon organizers |
| `raw/_briefs/` | The `LineWise Operaciones ES.pdf` and any other reference briefs | Hackathon organizers |
| `clean/` | Tidy CSVs produced by the ETL — `executed_runs`, `changes_actual`, `sku_master`, `sku_line_capability`, `changeover_matrix`, `calendar_constraints`, `incident_log`, `demand`, `weekly_actual_v2026_05` | [`services/etl/`](../services/etl/) |
| `external/` | Anything we end up enriching with (none right now — decision in [`docs/linewise/cobertura_brief.md`](../docs/linewise/cobertura_brief.md) §6) | — |

## Why nothing is committed

Damm data is confidential per the hackathon rules (PDF §6, restated in [`docs/challenge/CHALLENGE.md`](../docs/challenge/CHALLENGE.md)).
The `.gitignore` blocks `*.xlsx`, `*.parquet`, and every file under these folders. If you need
to share a derived sample, anonymize it and put a tiny synthetic version in a fixture folder
under the relevant service's `tests/`.

## Where to look first

- `raw/OEE 14_17_19_ 2025.xlsx` — the spine of the historical dataset (1 row = 1 WO).
- `raw/Tabla CF Prat 2026_14_17_19.xlsx` — theoretical changeover matrix + calendar.
- `raw/Planificado - producciones 14 - 17 - 19.XLSX` — plan for the demo week (18–24 May 2026).

Full inventory and join keys: [`docs/linewise/datos.md`](../docs/linewise/datos.md).
