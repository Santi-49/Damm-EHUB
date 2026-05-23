# Company & Challenge Research

> **Iterative document** — update this before major design decisions, not just once.
> Each entry should include the date it was added so stale findings are easy to spot.

---

## The Company / Organizer

- **Name:** S.A. Damm (Estrella Damm)
- **Industry:** Brewing / consumer packaged goods
- **Size / stage:** Established multinational, multiple breweries; this challenge focuses
  on the **canning plant in El Prat de Llobregat (Barcelona)**
- **Mission statement:** TBD — confirm from public source before pitch
- **Core product(s):** Estrella Damm, Voll-Damm, Free Damm, Daura, Inedit, Turia, etc.
- **Website / relevant links:** https://www.damm.com/

### Their Existing Approach to This Problem

- Production planning is currently driven by **Blue Yonder / JDA** (visible as
  `Cntd JDA` column in `Planificado - producciones…`).
- Planners then **override the JDA plan** based on operational judgment — visible in
  the discrepancy between `Planificado` and the actual `Produccion_L14,17,19_18-22`
  for the demo week.
- No public-facing tool for changeover impact analysis was found — this is exactly the
  gap LineWise targets.

### Tech Stack & Preferences

- Tooling visible from the data exports: **Excel** for delivery, **JDA / Blue Yonder**
  for upstream planning. No explicit preference imposed for the hackathon.
- Brief explicitly allows Streamlit, generative AI, AutoML, no-code — so the team has
  free choice on the stack.

### Public Statements About This Challenge

- From the brief: framing is *learn from what really happened* → *detect inefficiencies,
  simulate alternatives, recommend line + sequence*. The vocabulary is operational
  (OEE, changeover, line, SKU) rather than research-y, so the audience expects an
  industry-ready demo.

### Values & Culture Signals

- Heavy emphasis on **operational realism** (the brief is named "LineWise Operaciones").
- Explicit interest in **explainability** (judging criterion + drill-down requirement)
  suggests the planners themselves are the intended end users.
- The instruction to *not commit data* signals a security-conscious culture — handle
  the dataset with care during the demo.

---

## The Problem Space

### Existing Solutions in the Market

| Solution | Approach | Gap |
|---|---|---|
| Blue Yonder / JDA | Heuristic-driven MRP+APS, weekly horizon | Doesn't learn from realised changeover times; output is overridden in practice |
| Aveva Plant Performance | OEE dashboards, downtime breakdown | Reports *what happened*, doesn't propose alternative sequences |
| Siemens Opcenter Scheduler | Constraint-based scheduler, drag-and-drop Gantt | Strong UX, but no native ML on changeover prediction; expensive licensing |
| Bespoke spreadsheets | Manual reorder by operators | What Damm partially relies on today |

### Relevant Research or Industry Context

- **Changeover modelling**: well-studied in the SMED (Single-Minute Exchange of Die)
  literature — most academic work is rules-based; ML approaches are newer and a good
  storytelling angle.
- **m-TSP / VRP with makespan objective**: standard problem in OR; OR-Tools provides
  a battle-tested RoutingModel with disjunctions. No novel algorithm needed.
- **OEE = A × P × Q** is the universal canning industry metric — using it as the headline
  KPI makes the demo immediately legible to plant managers.

### Past Hackathon Winners (if available)

- No public record found of prior LineWise hackathon submissions.

---

## Recommendations

> Update this section whenever a meaningful new finding changes the strategic picture.

### Framing That Resonates With This Company

- **"Shortest path that covers all your demand"** — concrete, visual, non-jargon.
- **"Same incidents, same calendar — fair fight"** — the deterministic-replay framing
  pre-empts the "you only won by luck" objection.
- **"Same objective decides whether you drop SKUs"** — emphasises a single coherent
  optimiser rather than two pipelines (normal vs emergency).

### Technical Choices That Align

- OR-Tools VRP (open-source, Python-friendly, well-known in OR circles).
- LightGBM / XGBoost for the changeover model (industry-standard for tabular ML, fast,
  SHAP-able for explanation).
- Streamlit / React for the demo surface — the brief endorses Streamlit explicitly.

### What to Emphasize in the Demo

- The **headline metric: productive hours saved vs the real week**. Tangible, OEE-compatible.
- The **drill-down to a specific transition** with `C.Brand` / `C.Envase` flags and SHAP
  attribution — that's the moment a planner says "yes, I would have caught that too,
  but the tool found it in 3 seconds."
- The **breakdown injection** — proves the system handles the operationally interesting
  edge case (a planner's daily reality).

### What to Avoid

- Don't pitch the optimiser as a replacement for JDA — it's an *enrichment layer*.
- Don't show OEE numbers above 1 without a P50/P95 caveat (visible in raw data).
- Don't hide the assumptions — surface them in the demo notes; the brief explicitly
  asks for documented supposition.

---

## Research Log

> Append entries here as new information surfaces. Format: `YYYY-MM-DD — finding — source`.

- **2026-05-23 — Initial research compiled from brief + thought_process docs.** Sources:
  `data/raw/_briefs/LineWise Operaciones ES.pdf`, `docs/linewise/{datos,reto,implementacion,cobertura_brief,resumen}.md`.
- **2026-05-23 — Decision: no external data sources.** Brief allows them but
  `docs/linewise/cobertura_brief.md` §6 documents we focus on the historical dataset.
  Revisit only if a major gap emerges.
- **2026-05-23 — Architecture choice locked: D (m-TSP graph + ML edges).** Rationale in
  `docs/linewise/implementacion.md` §3 and §3.D. Arch A retained as fail-safe.
