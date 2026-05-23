# Solution Vision — LineWise

## Core Concept

Model weekly production planning as a **graph pathfinding problem**: nodes are SKU chunks
(production work to be done), edges are changeover times between SKUs on a given line.
Three "travelling salesmen" — one per line — visit every node exactly once between them.
The optimiser minimises the **maximum total time across the three lines** (makespan), so
the slowest line finishes as early as possible. ML predicts the cost of each edge; a
deterministic simulator validates the final sequence by computing OEE with the same
incidents that actually happened.

This is **Architecture D** of the four we considered — full comparison in
[`docs/linewise/implementacion.md`](../linewise/implementacion.md) §3.

## Philosophy & Selling Point

> **"We find the shortest path that covers all your weekly demand."**

That one sentence wins the storytelling battle vs ILP, greedy, or local-search framings.
Three properties make it defensible:

1. **ML target is well-bounded** — predicting *changeover time* between two SKUs is a
   single, observable, easily validatable quantity. Not a composite KPI.
2. **Clean decoupling** — ML for edges, OR-Tools for routing, simulator for OEE.
   Each component has one job and is independently testable.
3. **Drop-out is native** — when capacity is short (breakdown, urgent demand), OR-Tools
   VRP supports *disjunctions with penalty*: each demand node is optional and the solver
   picks which to skip according to `margin × uds`. The same objective handles both the
   feasible and infeasible regimes — no separate emergency branch.

## Target Users

- **Primary user:** Damm planners on the El Prat canning floor.
- **Main pain point:** today's plan (Blue Yonder / JDA) ignores realised changeover
  costs and produces sequences that operators silently override. The result: avoidable
  setup time, lower OEE, and no traceable explanation when the plan diverges.
- **How this solves it:** LineWise replays the same incidents on top of a graph-optimal
  proposal so the planner can see *exactly* which transitions could have been avoided,
  and a "what-if" button lets them inject urgent demand or a breakdown and see the
  re-planned week in seconds.

## Key Features — MVP

1. **ETL → clean datasets** ready for the optimiser (`executed_runs`, `sku_master`,
   `sku_line_capability`, `changeover_matrix`, `calendar_constraints`, `incident_log`,
   `demand` at weekly granularity).
2. **Graph optimiser** (Arch D, OR-Tools VRP) that distributes SKUs across L14/L17/L19
   respecting format constraints, finds the cheapest path per line, and minimises makespan.
3. **ML changeover predictor** that estimates edge weights from history, with theoretical
   matrix as floor for rare pairs.
4. **Deterministic simulator** that takes a proposed sequence and computes OEE while
   replaying real incidents — so `S_opt` vs `S_real` is a fair fight.
5. **Interactive UI** — Gantt per line, drill-down `week → day → transition`, drag to
   move slots, "inject breakdown / urgent demand" button.

## Full Vision

Beyond MVP, the same pipeline supports:

- **Post-mortem mode** on any historical window: re-aggregate executed WOs to weekly
  demand, re-plan, compare ΔOEE / Δh_cambios per day.
- **Live replan** on the demo week (18–24 May 2026): inject the real breakdowns of that
  week and watch the proposal degrade gracefully via disjunction dropouts.
- **Coverage-aware mode**: report both OEE *and* coverage so the optimiser cannot
  "win" by simply producing less.
- **Margin-aware drop** (`margen[sku]`): when capacity is short, sacrifice the
  lowest-margin SKUs first; surface what was dropped to the planner.

## Main User Journey

1. Planner opens LineWise on Monday morning, sees the week's demand bucket per SKU.
2. Clicks **Optimise** → the graph optimiser returns a proposal in <5 s.
3. Reviews the Gantt: makespan per line, total changeover hours, coverage at 100%.
4. Drills into the worst transition of the week: the UI shows which `C.*` flags
   (Brand / Envase / Packaging…) drove the cost and what historical context applies.
5. On Wednesday a breakdown hits L14 → planner injects the event → LineWise re-plans
   the rest of the week, respecting freeze days, and shows the diff side by side.
6. If demand no longer fits, the dropped SKUs (lowest margin first) are highlighted with
   their `€ lost` and a suggestion to roll them to the next week.

## Demo Script (~8 minutes)

1. **Frame** (30 s): "Three lines, hundreds of SKUs, every changeover costs OEE.
   We optimise the weekly path."
2. **Show the demo week** (90 s): planned vs actual for 18–22 May 2026.
3. **Run LineWise** (60 s): proposal, makespan, hours saved vs `S_real`.
4. **Drill into the worst transition** (90 s): SHAP-style attribution on the edge,
   explain the avoidable change.
5. **Inject a breakdown** (90 s): re-plan in seconds, show drop-out behaviour.
6. **Inject urgent demand** (60 s): same re-plan flow, opposite direction.
7. **Close** (60 s): headline metric — productive hours saved vs the real week,
   tangible and OEE-compatible.

Full storytelling text lives in [`docs/linewise/implementacion.md`](../linewise/implementacion.md) §5.
