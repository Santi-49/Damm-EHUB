# Hackathon Template — Claude Guide

@docs/challenge/CHALLENGE.md
@docs/challenge/VISION.md
@docs/challenge/CONSTRAINTS.md
@docs/challenge/RESEARCH.md
@docs/contracts.md

---

## How Documentation Works

```
docs/
  challenge/           ← imported above — read before every session
    CHALLENGE.md       ← problem statement, rules, data, judging criteria
    VISION.md          ← solution concept, philosophy, key features, demo script
    CONSTRAINTS.md     ← scope, team, timeline, external services, design language
  architecture/        ← system design, service map, request flow
  backend/             ← API reference, auth, RBAC, database schema
  contracts.md         ← module contract system (imported above)
  index.md             ← docs entry point
```

---

## How to Work in This Repo

### Contract-First Development

Before any feature that crosses a service boundary:

1. Read `docs/contracts.md` (imported above)
2. Define the Python Protocol in `packages/contracts/module/interface.py`
3. Update OpenAPI types in `packages/contracts/api/`
4. Run `make generate-types` → TypeScript types land in `packages/contracts/api/`
5. Implement in `services/module/app/implementation.py`
6. Build the frontend against the generated types — never hand-write API types

This is the pattern that allows frontend and backend to work in parallel.
Break it only if you are prototyping something that will never cross a service boundary.

### Backend Is Pre-Built

Auth (JWT + Redis whitelist), RBAC (OPA), user CRUD, token refresh, logout — all done.
Full reference at `docs/backend/`. To extend:
- Challenge logic → `services/module/`
- New authorization rules → `infra/opa/policies/` (one Rego entry per resource)
- New routes → `services/api/app/routes/` (auth middleware is automatic)

### Monorepo Layout

```
apps/landing/     Astro → Cloudflare Pages
apps/web/         Vite + React + TypeScript
apps/mobile/      Expo (React Native)
services/api/     FastAPI — extend, don't rewrite
services/module/  Challenge logic — implement here
packages/contracts/api/     OpenAPI + TypeScript types
packages/contracts/module/  Python Protocol
infra/            OPA, Postgres, Redis config
```

### Commands

```bash
make dev                       # start all services
make migrate                   # run migrations
make test                      # pytest, no Docker
make generate-types            # OpenAPI → TypeScript
make makemigration MSG="..."   # new Alembic migration
```

---

## MCP Servers

Five servers are available via `.mcp.json`. Prefer them over shell commands.

| Server | Use when |
|--------|----------|
| `postgres` | Query/inspect the DB — schema, data, slow queries, post-migration checks |
| `fetch` | Hit a URL or read external API docs |
| `markitdown` | Convert a local file (`file://`) or URL to markdown (handles PDF, DOCX, HTML) |
| `playwright` | Test UI in a real browser, take screenshots, scrape rendered pages |
| `docker` | Run a command inside a running Compose service |

**docker caveat:** always pass `service` explicitly — the default (`laravel_app_dev`) is wrong for this project. Valid names are in `docker-compose.yml` (e.g. `api`, `module`, `postgres`, `redis`).

---

## Skills — Load Contextually

Skills are in `.skills/` grouped by domain. Load only what the current task needs.
Do not import all skills at once — each group can be large.

### Working on `apps/landing/` or `apps/web/` — Animation

Read these when adding GSAP animation:

| Task | File |
|------|------|
| Any GSAP animation | `.skills/animation/gsap-core/SKILL.md` |
| GSAP in React | `.skills/animation/gsap-react/SKILL.md` |
| Scroll animations, pinning, scrub | `.skills/animation/gsap-scrolltrigger/SKILL.md` |
| Sequenced / timeline animations | `.skills/animation/gsap-timeline/SKILL.md` |

### Working on 3D (any app)

Always read `.skills/3d/3d-web-experience/SKILL.md` first — it covers stack selection
(Spline vs R3F vs vanilla Three.js) before you commit to an approach.

| Task | File |
|------|------|
| Stack decision | `.skills/3d/3d-web-experience/SKILL.md` ← read first |
| Scene / camera / renderer | `.skills/3d/threejs-fundamentals/SKILL.md` |
| Animating 3D objects | `.skills/3d/threejs-animation/SKILL.md` |
| Geometry | `.skills/3d/threejs-geometry/SKILL.md` |
| Interactions (click, hover, raycast) | `.skills/3d/threejs-interaction/SKILL.md` |
| Lighting and shadows | `.skills/3d/threejs-lighting/SKILL.md` |
| Loading GLB / GLTF | `.skills/3d/threejs-loaders/SKILL.md` |
| PBR materials | `.skills/3d/threejs-materials/SKILL.md` |
| Post-processing (bloom, etc.) | `.skills/3d/threejs-postprocessing/SKILL.md` |
| Custom GLSL shaders | `.skills/3d/threejs-shaders/SKILL.md` |
| Textures and UV | `.skills/3d/threejs-textures/SKILL.md` |

For 3D on mobile specifically: read `.skills/mobile/use-dom/SKILL.md` — this is the
bridge that lets Three.js / R3F run inside Expo via DOM components without full native builds.
Also check `.skills/mobile/building-native-ui/references/webgpu-three.md`.

### Working on `apps/mobile/`

| Task | File |
|------|------|
| Navigation, tabs, native UI | `.skills/mobile/building-native-ui/SKILL.md` |
| Data fetching, caching, offline | `.skills/mobile/native-data-fetching/SKILL.md` |
| Three.js / web libs in Expo | `.skills/mobile/use-dom/SKILL.md` |
| expo-gl, native modules, custom builds | `.skills/mobile/expo-dev-client/SKILL.md` |

### Design decisions (any app)

Read `.skills/design/ui-ux-pro-max/SKILL.md` when making visual decisions.
To search the design database:

```bash
python .skills/design/ui-ux-pro-max/scripts/search.py "<query>" --design-system
python .skills/design/ui-ux-pro-max/scripts/search.py "<query>" --domain color
python .skills/design/ui-ux-pro-max/scripts/search.py "<query>" --domain typography
```

---

## Challenge Context

**Challenge:** LineWise Operaciones — Damm × Engineering HUB. Optimise the weekly
production sequence on the three Damm canning lines (L14, L17, L19) at El Prat.

**Core concept (Architecture D):** model planning as **graph pathfinding** — nodes are
SKU chunks (node cost = production time per line), edges are line-specific changeover
times predicted by ML with the theoretical `Tabla CF Prat` matrix as floor.
Three "vehicles" (lines) tour the nodes; OR-Tools VRP minimises **makespan** with
disjunction penalties to handle infeasibility. OEE is never predicted — it is
*computed* post-hoc by a deterministic simulator that replays real incidents.

**Selling point:** *"We find the shortest path that covers all your weekly demand."*
ML target is bounded (changeover hours, observable), comparison with `S_real` is fair
(same incidents replayed), and capacity shortfalls drop the lowest-margin SKUs via
the same objective — no emergency branch.

**Hard capability constraints**:
- L14 → 1/2 (50 cl) and 1/3 (33 cl)
- L17 → 1/3 (33 cl) only
- L19 → 1/2, 1/3, 2/5 (44 cl)

**MVP features**:
1. ETL → 8 clean CSVs in `data/clean/`
2. Weekly demand dataset (`sku, semana, uds`) from history + JDA plan + what-if
3. ML changeover predictor with walk-forward validation
4. OR-Tools VRP optimiser (Arch D) with makespan objective + disjunctions
5. Deterministic simulator with incident replay
6. Web UI: Gantt per line, drill-down `week → day → transition`, what-if button

**Scope — apps**: `apps/landing/` (pitch), `apps/web/` (demo surface).
`apps/damm-mobile/` parked.

**Five workspaces, five contracts** (full map in [`docs/functionalities/overview.md`](docs/functionalities/overview.md)):

| Functionality | Folder | Contract |
|---|---|---|
| Data cleaning (ETL) | [`services/etl/`](services/etl/) | `ETLContract` |
| Demand dataset gen | [`services/etl/`](services/etl/) | `DemandBuilderContract` |
| ML changeover predictor | [`services/changeover_ml/`](services/changeover_ml/) | `ChangeoverModelContract` |
| Graph optimiser (Arch D) | [`services/optimizer/`](services/optimizer/) | `GraphOptimizerContract` |
| Simulator (deterministic OEE) | [`services/simulator/`](services/simulator/) | `SimulatorContract` |
| UI (Gantt, drill-down, what-if) | [`apps/landing/`](apps/landing/), [`apps/web/`](apps/web/) | OpenAPI types |

**Data products:** nine clean CSVs catalogued in [`docs/data/overview.md`](docs/data/overview.md) —
`wo_master`, `skus`, `wo_changeovers`, `demand`, `line_capability`, `line_calendar`,
`changeover_costs`, `node_cost_train`, `edge_cost_train` (+ `incidents` for the simulator).
Cleaning rules in [`docs/data/cleaning_rules.md`](docs/data/cleaning_rules.md).

**Time-window knob:** `WindowConfig(days=7, anchor="monday")` drives both demand
aggregation *and* the optimiser planning horizon. Change it once, both move.

**Team (3 people, ~2 days)**:
- Person 1 — Data & Simulator (ETL + simulator + `incident_log` replay + historical OEE validation)
- Person 2 — Optimiser & ML (graph construction + ML edges + OR-Tools VRP + replan with disjunctions)
- Person 3 — UI, analysis & demo (Streamlit/React Gantt + drill-down + what-if + storytelling)

**Key constraints**:
- Data is **confidential** — never commit anything under `data/`. `.gitignore` is set.
- Demo must be end-to-end (interactive Gantt, not a static mock).
- Re-plan latency target < 5 s on the demo week.
- Arch A (greedy + rules) is kept as a fail-safe should OR-Tools integration slip.

**Demo deadline:** TBD by the organiser. Milestones: M1 (Sat 13:00) ETL → M2 (Sat 19:00)
simulator validated → M3 (Sat 22:00) Arch A fallback → M4 (Sun 14:00) Arch D
integrated → M5 (Sun 16:00) what-if wired → M6 (Sun 18:00) dry-run.

**Deep dives** (kept verbatim from the thought-process phase):
- [`docs/linewise/datos.md`](docs/linewise/datos.md) — raw Excel inventory + joins + clean schema
- [`docs/linewise/reto.md`](docs/linewise/reto.md) — problem framing, objective function, post-mortem methodology
- [`docs/linewise/implementacion.md`](docs/linewise/implementacion.md) — Arch D vs alternatives, full justification
- [`docs/linewise/resumen.md`](docs/linewise/resumen.md) — visual overview, Gantt, sync points
- [`docs/linewise/cobertura_brief.md`](docs/linewise/cobertura_brief.md) — brief-by-brief coverage check
