# Constraints & Team Context — LineWise

## Apps in Scope

- [x] `apps/landing/` — Landing page (Astro → Cloudflare Pages) — pitch surface
- [x] `apps/web/` — Web app (Vite + React + TS) — **primary demo surface** (Gantt + drill-down + what-if)
- [ ] `apps/damm-mobile/` — Expo — stretch goal, not required for the demo

## 3D / Immersive Elements

- **Needed:** no
- **Where:** —
- **Approach:** plain Plotly / D3 timelines inside the web app. The brief asks for an
  interactive Gantt with drag-and-drop, not a 3D experience.

## Performance Requirements

- **Re-plan latency:** < 5 s for a single weekly horizon (Arch D / OR-Tools VRP target).
- **Simulator throughput:** < 100 ms per `evaluate_sequence` call so the optimiser can
  use it inside its loop if needed.
- **UI:** the Gantt must remain interactive (drag + recompute) without a full page reload.

## Line Capability Constraints (hard)

| Line | Allowed formats | Source |
|---|---|---|
| L14 | 1/2 (50 cl), 1/3 (33 cl) | brief + historical observation |
| L17 | 1/3 (33 cl) only | brief + historical observation |
| L19 | 1/2 (50 cl), 1/3 (33 cl), 2/5 (44 cl) | brief + historical observation |

A SKU is **forbidden** on a line whose format it doesn't match — encoded as
`can_produce = False` in `sku_line_capability.csv` and as an absent edge in the optimiser
graph.

## Calendar Constraints (hard)

- Weekly **cleaning**: 8 h every Friday, all three lines.
- Quincennial **maintenance**: 8 h every other Monday, all three lines.
- Encoded as forced nodes / time-window constraints in the optimiser. Detail in
  [`docs/linewise/datos.md`](../linewise/datos.md) §1.5 and the parsed `calendar_constraints.csv`.

## Device & Platform Targets

- Demo runs on a laptop (Chrome / Firefox / Edge, 1440×900+).
- Mobile is not in scope for the demo; the existing `apps/damm-mobile/` is parked.

## Accessibility Requirements

- Keep the Gantt keyboard-navigable for drill-down (Tab / Enter on slot → opens detail).
- Use semantic color tokens (success / warning / danger) for OEE bins, never colour-only.

## External Services

| Service | Purpose | Tier / Cost |
|---|---|---|
| Cloudflare Pages | Hosting landing + web | Free tier |
| Postgres (local) | Optional persistence for what-if history | Docker compose dev |
| Redis (local) | Existing JWT whitelist | Docker compose dev |
| OPA (local) | Existing RBAC | Docker compose dev |
| (none) | No paid AI APIs in the MVP | — |

All ML training and inference is in-process (LightGBM / XGBoost via Python). No outbound
calls during the demo so the network isn't a failure mode.

## Design Language

- **Style direction:** clean operational dashboard, **content-first** density, **dark
  mode** as default to align with control-room interfaces.
- **Primary colors:** Damm dark green + cream accent + functional traffic-light
  scale for OEE bins. Final palette via the ui-ux-pro-max skill once a designer iterates.
- **Fonts:** Inter / IBM Plex Sans for UI; tabular numerals for KPI tiles and Gantt
  time labels.
- **Assets / inspiration:** real plant-floor schedulers (Aveva, Siemens Opcenter) for
  structure; modern SaaS dashboards (Linear, Vercel) for chrome.

## Team

(Three-person split per [`docs/linewise/resumen.md`](../linewise/resumen.md) §6.)

| Name | Role | Owns |
|---|---|---|
| Person 1 | Data & Simulator | ETL → clean CSVs, deterministic simulator, `incident_log` + replay, validation that simulator reproduces historical OEE within 5% |
| Person 2 | Optimiser & ML | Graph construction, theoretical edges from CF table, ML changeover model + walk-forward validation, OR-Tools VRP with makespan + ε·sum objective, replan with disjunctions |
| Person 3 | UI, analysis & demo | Streamlit / React app, Gantt per line, drill-down `week → day → transition`, descriptive inefficiency detection (works without optimiser), what-if + storytelling |

Re-allocate freely — these are the natural seams, not contractual roles.

## Timeline (~2 days hackathon)

(Detailed Gantt in [`docs/linewise/resumen.md`](../linewise/resumen.md) §6.)

| Milestone | When |
|---|---|
| Hackathon starts | Sat 09:00 |
| **M1**: ETL CSVs ready (unblocks optimiser + UI) | Sat 13:00 |
| **M2**: Simulator validated against historical OEE | Sat 19:00 |
| **M3**: Arch A fallback functional end-to-end | Sat 22:00 |
| **M4**: Arch D (OR-Tools VRP) integrated | Sun 14:00 |
| **M5**: What-if button wired to replan endpoint | Sun 16:00 |
| **M6**: Dry-run of full 8-minute demo | Sun 18:00 |
| Demo / submission | Sun evening |

## Fail-safe Policy

If Arch D doesn't integrate in time → present with Arch A (greedy + rules), which is
running since Saturday evening. If neither optimiser works → present the descriptive
inefficiency detection alone (still satisfies Objective 1 of the brief).
