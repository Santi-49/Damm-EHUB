"""Orchestrator for LineWise: graph building + optimization + serialisation.

Bridges the backend API to the optimizer service and graph_builder.
Translates NetworkX graph objects and OptimizerResult into the Pydantic response
types defined in app.schemas.linewise.
"""

from __future__ import annotations

import sys
import uuid
from datetime import datetime, timedelta
from math import isinf, isnan
from pathlib import Path
from typing import Any

import networkx as nx
import pandas as pd

# Ensure repo root is on sys.path so services.optimizer imports resolve
_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from services.optimizer.app.graph_builder import (
    build_historical_wo_graph,
    build_planning_graph,
)
from services.optimizer.app.implementation import (
    OptimizerResult,
    UrgentDemandResult,
    WhatIfResult,
    optimize_graph,
    replan_graph,
    replan_urgent_demand_graph,
)

from app.schemas.linewise import (
    ChangeoverDriver,
    CompareBundle,
    DeltaMetrics,
    DroppedSku,
    LineMetrics,
    PlanGraphEdge,
    PlanGraphNode,
    PlanOptimizeRequest,
    PlanOptimizeResponse,
    ReplanRecommendation,
    ReplanRequest,
    ReplanScenario,
    Sequence,
    SimulationReport,
    Slot,
    WeekOption,
)

DATA_DIR = _REPO_ROOT / "data" / "clean"
LINE_IDS: tuple[int, ...] = (14, 17, 19)
PLANT_START_HOUR = 6  # shift starts at 06:00 on window_start Monday
_MISSING_EDGE_HOURS = 8.0


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

class LinewiseOrchestrator:
    """Singleton-style orchestrator — instantiate once at module level."""

    def __init__(self) -> None:
        self._demand: pd.DataFrame | None = None
        self._wo: pd.DataFrame | None = None
        self._capability: pd.DataFrame | None = None
        self._skus: pd.DataFrame | None = None
        self._wo_co: pd.DataFrame | None = None

    # ------------------------------------------------------------------
    # Cached data loaders
    # ------------------------------------------------------------------

    def _get_demand(self) -> pd.DataFrame:
        if self._demand is None:
            self._demand = pd.read_csv(DATA_DIR / "demand.csv")
        return self._demand

    def _get_wo(self) -> pd.DataFrame:
        if self._wo is None:
            self._wo = pd.read_csv(DATA_DIR / "wo_master.csv", parse_dates=["end_day"])
        return self._wo

    def _get_capability(self) -> pd.DataFrame:
        if self._capability is None:
            self._capability = pd.read_csv(DATA_DIR / "line_capability.csv")
        return self._capability

    def _get_skus(self) -> pd.DataFrame:
        if self._skus is None:
            path = DATA_DIR / "skus.csv"
            self._skus = pd.read_csv(path) if path.exists() else pd.DataFrame()
        return self._skus

    def _get_wo_co(self) -> pd.DataFrame:
        if self._wo_co is None:
            self._wo_co = pd.read_csv(
                DATA_DIR / "wo_changeovers.csv", parse_dates=["transition_day"]
            )
        return self._wo_co

    # ------------------------------------------------------------------
    # 1. List comparable weeks
    # ------------------------------------------------------------------

    def list_weeks(self) -> list[WeekOption]:
        demand = self._get_demand()
        wo = self._get_wo()

        # Aggregate demand stats per window
        window_agg = (
            demand.groupby(["window_id", "window_start", "window_end"])
            .agg(sku_count=("sku_id", "nunique"), units=("units_demanded", "sum"))
            .reset_index()
        )

        # Determine source: "demo" when any row is plan_2026
        source_map = (
            demand.groupby("window_id")["source"]
            .apply(lambda s: "demo" if "plan_2026" in s.values else "historical")
            .reset_index()
            .rename(columns={"source": "api_source"})
        )
        window_agg = window_agg.merge(source_map, on="window_id")

        prod_wo = wo[wo["wo_kind"] == "production"].copy()

        results: list[WeekOption] = []
        for _, row in window_agg.iterrows():
            w_start = pd.Timestamp(row["window_start"])
            w_end = pd.Timestamp(row["window_end"])

            mask = (prod_wo["end_day"] >= w_start) & (prod_wo["end_day"] <= w_end)
            wo_w = prod_wo[mask]

            production_rows = int(len(wo_w))
            avg_oee: float | None = None
            downtime_h: float | None = None
            if not wo_w.empty:
                valid = wo_w[wo_w["oee"].notna() & (wo_w["productive_hours"] > 0)]
                if not valid.empty:
                    w = valid["productive_hours"].values
                    avg_oee = float((valid["oee"].values * w).sum() / w.sum())
                downtime_h = float(wo_w["downtime_hours"].sum())

            wid = str(row["window_id"])
            sku_cnt = int(row["sku_count"])
            units = int(row["units"])

            results.append(
                WeekOption(
                    id=wid,
                    label=f"{wid} · {_short_descriptor(sku_cnt, avg_oee)}",
                    range=_format_range(w_start, w_end),
                    week_start=w_start.date().isoformat(),
                    week_end=w_end.date().isoformat(),
                    source=str(row["api_source"]),  # type: ignore[arg-type]
                    reason=_make_reason(sku_cnt, production_rows, avg_oee),
                    production_rows=production_rows,
                    sku_count=sku_cnt,
                    units=units,
                    avg_oee=round(avg_oee, 3) if avg_oee is not None else None,
                    downtime_h=round(downtime_h, 1) if downtime_h is not None else None,
                )
            )

        # Demo weeks first, then historical sorted descending by id
        results.sort(key=lambda w: (w.source != "demo", w.id), reverse=False)
        return results

    # ------------------------------------------------------------------
    # 2. Compare real vs opt
    # ------------------------------------------------------------------

    def compare(self, week_id: str) -> CompareBundle:
        demand = self._get_demand()
        wo = self._get_wo()
        wo_co = self._get_wo_co()
        capability = self._get_capability()

        w_rows = demand[demand["window_id"] == week_id]
        if w_rows.empty:
            raise KeyError(f"week_id {week_id!r} not found in demand.csv")

        w_start = pd.Timestamp(w_rows.iloc[0]["window_start"])
        w_end = pd.Timestamp(w_rows.iloc[0]["window_end"])
        solution_id = str(uuid.uuid4())

        # --- Real sequence ---
        wo_graphs = build_historical_wo_graph(
            week_id, demand_df=demand, wo_df=wo, wo_co_df=wo_co
        )
        real_seq = _wo_graphs_to_sequence(wo_graphs, week_id, w_start, w_end, solution_id)
        real_report = _real_simulation_report(
            real_seq.id, wo_graphs, wo, w_start, w_end, demand, week_id, capability
        )

        # --- Optimised sequence ---
        planning_graph = build_planning_graph(
            week_id, demand_df=demand, capability_df=capability
        )
        opt_result = optimize_graph(planning_graph)
        opt_seq = _opt_result_to_sequence(
            opt_result, planning_graph, week_id, w_start, w_end, solution_id
        )
        opt_report = _opt_simulation_report(
            opt_seq.id, opt_result, planning_graph, demand, week_id, capability
        )

        delta = DeltaMetrics(
            oee_pp=round(opt_report.oee_global - real_report.oee_global, 4),
            h_changes_saved=round(real_report.h_changes - opt_report.h_changes, 2),
            h_productive_gained=round(opt_report.h_productive - real_report.h_productive, 2),
            coverage_delta=round(opt_report.coverage - real_report.coverage, 4),
        )

        week_opt = _week_option_for(week_id, demand, wo, w_start, w_end)

        return CompareBundle(
            week=week_opt,
            solution_id=solution_id,
            real_sequence=real_seq,
            opt_sequence=opt_seq,
            real_simulation=real_report,
            opt_simulation=opt_report,
            delta=delta,
        )

    # ------------------------------------------------------------------
    # 3. Optimize ad-hoc demand
    # ------------------------------------------------------------------

    def optimize(self, request: PlanOptimizeRequest) -> PlanOptimizeResponse:
        from datetime import date

        capability = self._get_capability()
        skus_df = self._get_skus()

        today = date.today()
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)
        window_id = "whatif"
        solution_id = str(uuid.uuid4())
        w_start_ts = pd.Timestamp(week_start)
        w_end_ts = pd.Timestamp(week_end)

        demand_rows = [
            {
                "window_id": window_id,
                "window_start": str(week_start),
                "window_end": str(week_end),
                "sku_id": p.sku_id,
                "units_demanded": p.quantity_units,
                "source": "whatif_usuario",
                "priority": 3,
            }
            for p in request.products
        ]
        demand_df = pd.DataFrame(demand_rows)

        graph = build_planning_graph(
            window_id, demand_df=demand_df, capability_df=capability
        )

        if graph.number_of_nodes() == 0:
            return PlanOptimizeResponse(
                nodes=[],
                edges=[],
                makespan_h=0.0,
                h_saved=0.0,
                coverage_pct=0.0,
                dropped_skus=[p.sku_id for p in request.products],
                sequence=Sequence(
                    id=f"opt-{solution_id[:8]}",
                    week_id=window_id,
                    week_start=str(week_start),
                    week_end=str(week_end),
                    source="opt",
                    slots=[],
                ),
            )

        result = optimize_graph(graph)

        # SKU metadata
        sku_family: dict[str, str] = {}
        sku_hl_factor: dict[str, float] = {}
        if not skus_df.empty:
            if "sku_id" in skus_df.columns and "family" in skus_df.columns:
                sku_family = dict(zip(skus_df["sku_id"], skus_df["family"].fillna("unknown")))

        # HL conversion from historical wo if available
        wo = self._get_wo()
        wo_prod = wo[(wo["wo_kind"] == "production") & (wo["units_produced"] > 0)]
        if not wo_prod.empty:
            hl_conv = (
                wo_prod.groupby("sku_id")
                .apply(
                    lambda g: (g["hectoliters_produced"] / g["units_produced"]).median()
                )
                .to_dict()
            )
            sku_hl_factor = {str(k): float(v) for k, v in hl_conv.items()}

        nodes: list[PlanGraphNode] = []
        for sku in graph.nodes:
            sku_str = str(sku)
            assigned_line = _find_assigned_line(sku_str, result.assignments)
            if assigned_line is None:
                continue
            units = graph.nodes[sku].get("units_demanded", 0)
            factor = sku_hl_factor.get(sku_str, 0.0033)
            volume_hl = units * factor
            nodes.append(
                PlanGraphNode(
                    id=sku_str,
                    label=sku_str,
                    line_id=assigned_line,  # type: ignore[arg-type]
                    family=sku_family.get(sku_str, "unknown"),
                    volume_hl=round(volume_hl, 2),
                )
            )

        edges: list[PlanGraphEdge] = []

        # Baseline: one edge per unique (sku_from, sku_to) pair across all lines
        seen_baseline: set[tuple[str, str]] = set()
        bl_idx = 0
        for u, v, _key, attrs in graph.edges(keys=True, data=True):
            pair = (str(u), str(v))
            if pair not in seen_baseline:
                seen_baseline.add(pair)
                edges.append(
                    PlanGraphEdge(
                        id=f"bl-{bl_idx}",
                        source=str(u),
                        target=str(v),
                        hours=_safe_float(attrs.get("hours", 0.0)),
                        path="baseline",
                    )
                )
                bl_idx += 1

        # Opt path: actual transitions from optimizer routes
        for line_id, route in result.routes.items():
            if not route.feasible or not route.order:
                continue
            for i in range(len(route.order) - 1):
                src, tgt = str(route.order[i]), str(route.order[i + 1])
                edge_data = graph.get_edge_data(src, tgt, key=line_id)
                hours = _safe_float(edge_data.get("hours", 0.0)) if edge_data else 0.0
                edges.append(
                    PlanGraphEdge(
                        id=f"opt-{line_id}-{i}",
                        source=src,
                        target=tgt,
                        hours=hours,
                        path="opt",
                    )
                )

        # h_saved: naive lower-bound (no transitions) vs actual makespan
        total_prod_h = sum(
            _safe_float(
                graph.nodes[n]
                .get("line_data", {})
                .get(_find_assigned_line(str(n), result.assignments) or 14, {})
                .get("predicted_hours", 0.0)
            )
            for n in graph.nodes
        )
        h_saved = max(0.0, total_prod_h / len(LINE_IDS) - result.makespan_hours)

        total_units = sum(p.quantity_units for p in request.products)
        dropped_units = sum(
            graph.nodes[sku].get("units_demanded", 0) for sku in result.dropped
        )
        coverage_pct = (
            max(0.0, 1.0 - dropped_units / total_units) if total_units > 0 else 1.0
        )

        sequence = _opt_result_to_sequence(
            result, graph, window_id, w_start_ts, w_end_ts, solution_id
        )

        return PlanOptimizeResponse(
            nodes=nodes,
            edges=edges,
            makespan_h=round(_safe_float(result.makespan_hours), 2),
            h_saved=round(h_saved, 2),
            coverage_pct=round(coverage_pct, 4),
            dropped_skus=list(result.dropped),
            sequence=sequence,
        )

    # ------------------------------------------------------------------
    # 4. Replan after a line breakdown
    # ------------------------------------------------------------------

    def replan(self, request: ReplanRequest) -> ReplanScenario:
        """Re-plan the remainder of the week after a what-if perturbation."""
        if request.scenario_id == "urgent-demand":
            return self._replan_urgent_demand(request)
        return self._replan_breakdown(request)

    def _replan_breakdown(self, request: ReplanRequest) -> ReplanScenario:
        """Re-plan the remainder of the week after a line breakdown."""
        if request.breakdown_line is None:
            raise ValueError("breakdown_line is required for a breakdown scenario")
        if request.breakdown_day is None:
            raise ValueError("breakdown_day is required")

        maintenance_h = float(request.breakdown_hours or 8.0)
        demand = self._get_demand()
        capability = self._get_capability()

        # Locate the selected planning window. week_id is preferred so the UI can
        # run the same perturbation pattern across different demand windows.
        breakdown_date = pd.Timestamp(request.breakdown_day)
        if request.week_id:
            matching = demand[demand["window_id"] == request.week_id]
            if matching.empty:
                raise KeyError(f"week_id {request.week_id!r} not found in demand.csv")
        else:
            mask = (
                pd.to_datetime(demand["window_start"]) <= breakdown_date
            ) & (
                pd.to_datetime(demand["window_end"]) >= breakdown_date
            )
            matching = demand[mask]
            if matching.empty:
                raise KeyError(
                    f"No planning window found for date {request.breakdown_day!r}"
                )

        row0 = matching.iloc[0]
        week_id = str(row0["window_id"])
        w_start = pd.Timestamp(row0["window_start"])
        w_end = pd.Timestamp(row0["window_end"])
        if not (w_start <= breakdown_date <= w_end):
            raise ValueError(
                f"breakdown_day {request.breakdown_day!r} is outside week_id {week_id!r}"
            )
        solution_id = str(uuid.uuid4())

        graph = build_planning_graph(week_id, demand_df=demand, capability_df=capability)
        if graph.number_of_nodes() == 0:
            raise ValueError(f"No demand nodes found for window {week_id!r}")

        # Breakdown offset: hours from plan start (Monday 06:00) to breakdown day 06:00
        plan_start_dt = datetime(
            w_start.year, w_start.month, w_start.day, PLANT_START_HOUR
        )
        breakdown_dt = datetime(
            breakdown_date.year, breakdown_date.month, breakdown_date.day, PLANT_START_HOUR
        )
        breakdown_offset_h = max(
            0.0, (breakdown_dt - plan_start_dt).total_seconds() / 3600.0
        )

        baseline_result, wif = replan_graph(
            graph,
            breakdown_hours=breakdown_offset_h,
            affected_line=int(request.breakdown_line),
            maintenance_hours=maintenance_h,
        )

        base_seq = _opt_result_to_sequence(
            baseline_result, graph, week_id, w_start, w_end, solution_id
        )
        base_report = _opt_simulation_report(
            base_seq.id, baseline_result, graph, demand, week_id, capability
        )

        replan_seq = _wif_to_sequence(wif, graph, week_id, w_start, solution_id)
        replan_report = _wif_simulation_report(
            wif, graph, demand, week_id, capability, solution_id
        )

        affected_l = int(request.breakdown_line)
        moved_n = len(wif.moved_skus)
        stranded_n = len(wif.stranded_on_affected)
        delta_h = wif.makespan_hours - wif.original_makespan_hours

        constraints: list[str] = []
        if stranded_n:
            constraints.append(
                f"{stranded_n} SKU(s) are format-locked to L{affected_l} "
                f"and will resume after maintenance."
            )
        if moved_n:
            constraints.append(
                f"{moved_n} SKU(s) redistributed across other lines."
            )

        recommendation = ReplanRecommendation(
            headline=(
                f"L{affected_l} offline {maintenance_h:.0f}h — "
                f"makespan {delta_h:+.1f}h vs baseline"
            ),
            why=(
                f"L{affected_l} breaks at hour {breakdown_offset_h:.0f} of the plan "
                f"({request.breakdown_day}). After {maintenance_h:.0f}h maintenance, "
                f"{moved_n} SKU(s) were redistributed to minimise makespan."
                + (
                    f" {stranded_n} SKU(s) are format-locked to L{affected_l} "
                    f"and will wait for the line to come back."
                    if stranded_n
                    else ""
                )
            ),
            constraints=constraints,
        )

        return ReplanScenario(
            id=f"replan-{solution_id[:8]}",
            label=f"L{affected_l} breakdown · {maintenance_h:.0f}h maintenance",
            description=(
                f"L{affected_l} fails at ~{breakdown_offset_h:.0f}h into the week "
                f"({request.breakdown_day}). After {maintenance_h:.0f}h repair the "
                f"plan is re-optimised. New makespan: {wif.makespan_hours:.1f}h "
                f"(baseline {wif.original_makespan_hours:.1f}h)."
            ),
            recommendation=recommendation,
            base_sequence=base_seq,
            sequence=replan_seq,
            report=replan_report,
            base=base_report,
        )

    def _replan_urgent_demand(self, request: ReplanRequest) -> ReplanScenario:
        """Re-plan the remaining week after urgent demand arrives."""
        if not request.introduced_at:
            raise ValueError("introduced_at is required for an urgent-demand scenario")
        if not request.urgent_sku:
            raise ValueError("urgent_sku is required for an urgent-demand scenario")
        if request.urgent_units is None or request.urgent_units <= 0:
            raise ValueError("urgent_units must be positive for an urgent-demand scenario")

        demand = self._get_demand()
        capability = self._get_capability()

        introduced_ts = pd.Timestamp(request.introduced_at)
        introduced_day = pd.Timestamp(introduced_ts.date())
        if request.week_id:
            matching = demand[demand["window_id"] == request.week_id]
            if matching.empty:
                raise KeyError(f"week_id {request.week_id!r} not found in demand.csv")
        else:
            mask = (
                pd.to_datetime(demand["window_start"]) <= introduced_day
            ) & (
                pd.to_datetime(demand["window_end"]) >= introduced_day
            )
            matching = demand[mask]
            if matching.empty:
                raise KeyError(
                    f"No planning window found for introduced_at={request.introduced_at!r}"
                )

        row0 = matching.iloc[0]
        week_id = str(row0["window_id"])
        w_start = pd.Timestamp(row0["window_start"])
        w_end = pd.Timestamp(row0["window_end"])
        if not (w_start <= introduced_day <= w_end):
            raise ValueError(
                f"introduced_at {request.introduced_at!r} is outside week_id {week_id!r}"
            )
        solution_id = str(uuid.uuid4())

        graph = build_planning_graph(week_id, demand_df=demand, capability_df=capability)
        if graph.number_of_nodes() == 0:
            raise ValueError(f"No demand nodes found for window {week_id!r}")

        plan_start_dt = datetime(
            w_start.year, w_start.month, w_start.day, PLANT_START_HOUR
        )
        introduced_dt = _naive_datetime(introduced_ts)
        introduced_offset_h = max(
            0.0, (introduced_dt - plan_start_dt).total_seconds() / 3600.0
        )

        if request.required_by:
            required_dt = _naive_datetime(pd.Timestamp(request.required_by))
        else:
            required_dt = plan_start_dt + timedelta(days=7)
        required_by_h = (required_dt - plan_start_dt).total_seconds() / 3600.0
        if required_by_h < introduced_offset_h:
            raise ValueError("required_by must be at or after introduced_at")

        baseline_result, urgent, augmented_graph = replan_urgent_demand_graph(
            graph,
            urgent_sku=request.urgent_sku,
            urgent_units=int(request.urgent_units),
            introduced_at_hours=introduced_offset_h,
            required_by_hours=required_by_h,
            capability_df=capability,
        )

        base_seq = _opt_result_to_sequence(
            baseline_result, graph, week_id, w_start, w_end, solution_id
        )
        base_report = _opt_simulation_report(
            base_seq.id, baseline_result, graph, demand, week_id, capability
        )

        replan_seq = _urgent_to_sequence(
            urgent, augmented_graph, week_id, w_start, solution_id
        )
        replan_report = _urgent_simulation_report(
            urgent, augmented_graph, demand, week_id, capability, solution_id
        )

        delta_h = urgent.makespan_hours - urgent.original_makespan_hours
        moved_n = len(urgent.moved_skus)
        constraints = [
            (
                f"Frozen prefix kept through hour {introduced_offset_h:.1f}; "
                "only unstarted demand was re-optimised."
            ),
            (
                f"Urgent demand completes at hour {urgent.urgent_end_hours:.1f}, "
                f"before the required deadline at hour {required_by_h:.1f}."
            ),
        ]
        if moved_n:
            constraints.append(f"{moved_n} residual SKU(s) moved across lines.")

        recommendation = ReplanRecommendation(
            headline=(
                f"Assign urgent {request.urgent_sku} to L{urgent.assigned_line} "
                f"inside the required window"
            ),
            why=(
                f"The order arrives at hour {introduced_offset_h:.1f} of the plan "
                f"({request.introduced_at}). V1 reruns the residual problem and "
                f"pins the urgent node first on L{urgent.assigned_line}, finishing "
                f"at hour {urgent.urgent_end_hours:.1f}. Makespan changes "
                f"{delta_h:+.1f}h vs baseline."
            ),
            constraints=constraints,
            assigned_line=urgent.assigned_line,  # type: ignore[arg-type]
        )

        return ReplanScenario(
            id=f"urgent-{solution_id[:8]}",
            label=(
                f"Urgent demand · {request.urgent_units:,} units "
                f"{request.urgent_sku}"
            ),
            description=(
                f"New demand arrives at {request.introduced_at}; required by "
                f"{required_dt.isoformat()}. The replan assigns it to "
                f"L{urgent.assigned_line} from hour {urgent.urgent_start_hours:.1f} "
                f"to {urgent.urgent_end_hours:.1f}."
            ),
            recommendation=recommendation,
            base_sequence=base_seq,
            sequence=replan_seq,
            report=replan_report,
            base=base_report,
        )


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

orchestrator = LinewiseOrchestrator()


# ---------------------------------------------------------------------------
# Helper: what-if sequence + report builders
# ---------------------------------------------------------------------------

def _wif_to_sequence(
    wif: WhatIfResult,
    graph: nx.MultiDiGraph,
    week_id: str,
    w_start: pd.Timestamp,
    solution_id: str,
) -> Sequence:
    """Build a committed+maintenance+residual Sequence from a WhatIfResult."""
    seq_id = f"replan-{solution_id[:8]}"
    slots: list[Slot] = []
    base_ts = datetime(w_start.year, w_start.month, w_start.day, PLANT_START_HOUR, 0, 0)

    for line in LINE_IDS:
        # --- Committed prefix (same order as baseline plan) ---
        committed = tuple(str(s) for s in wif.committed_per_line.get(line, ()))
        cursor = base_ts
        for i, sku in enumerate(committed):
            nd = graph.nodes.get(sku, {})
            prod_h = _safe_float(
                nd.get("line_data", {}).get(line, {}).get("predicted_hours", 0.0)
            )
            prod_end = cursor + timedelta(hours=prod_h)
            slots.append(
                Slot(
                    id=f"replan-L{line}-c{i}",
                    line=line,  # type: ignore[arg-type]
                    start=cursor.isoformat(),
                    end=prod_end.isoformat(),
                    kind="production",
                    sku=sku,
                    label=sku,
                    units=int(nd.get("units_demanded", 0)),
                )
            )
            cursor = prod_end
            if i < len(committed) - 1:
                next_sku = str(committed[i + 1])
                edge_data = graph.get_edge_data(sku, next_sku, key=line)
                co_h = _safe_float(edge_data.get("hours", 0.0)) if edge_data else 0.0
                if co_h > 0:
                    slots.append(
                        Slot(
                            id=f"replan-L{line}-cco{i}",
                            line=line,  # type: ignore[arg-type]
                            start=cursor.isoformat(),
                            end=(cursor + timedelta(hours=co_h)).isoformat(),
                            kind="changeover",
                            changeover_h=co_h,
                            changeover_source="teorico",
                        )
                    )
                    cursor += timedelta(hours=co_h)

        # --- Maintenance slot (affected line only) ---
        if line == wif.affected_line:
            maint_start = base_ts + timedelta(hours=wif.breakdown_hours)
            maint_end = maint_start + timedelta(hours=wif.maintenance_hours)
            slots.append(
                Slot(
                    id=f"replan-L{line}-maint",
                    line=line,  # type: ignore[arg-type]
                    start=maint_start.isoformat(),
                    end=maint_end.isoformat(),
                    kind="maintenance",
                )
            )

        # --- Residual sequence (anchored to baseline_hours_per_line) ---
        cursor = base_ts + timedelta(hours=wif.baseline_hours_per_line[line])
        new_seq = tuple(str(s) for s in wif.new_sequences.get(line, ()))
        for i, sku in enumerate(new_seq):
            nd = graph.nodes.get(sku, {})
            prod_h = _safe_float(
                nd.get("line_data", {}).get(line, {}).get("predicted_hours", 0.0)
            )
            prod_end = cursor + timedelta(hours=prod_h)
            slots.append(
                Slot(
                    id=f"replan-L{line}-r{i}",
                    line=line,  # type: ignore[arg-type]
                    start=cursor.isoformat(),
                    end=prod_end.isoformat(),
                    kind="production",
                    sku=sku,
                    label=sku,
                    units=int(nd.get("units_demanded", 0)),
                )
            )
            cursor = prod_end
            if i < len(new_seq) - 1:
                next_sku = str(new_seq[i + 1])
                edge_data = graph.get_edge_data(sku, next_sku, key=line)
                co_h = _safe_float(edge_data.get("hours", 0.0)) if edge_data else 0.0
                if co_h > 0:
                    slots.append(
                        Slot(
                            id=f"replan-L{line}-rco{i}",
                            line=line,  # type: ignore[arg-type]
                            start=cursor.isoformat(),
                            end=(cursor + timedelta(hours=co_h)).isoformat(),
                            kind="changeover",
                            changeover_h=co_h,
                            changeover_source="teorico",
                        )
                    )
                    cursor += timedelta(hours=co_h)

    return Sequence(
        id=seq_id,
        week_id=week_id,
        week_start=w_start.date().isoformat(),
        week_end=(w_start + timedelta(days=6)).date().isoformat(),
        source="replan",
        slots=slots,
    )


def _wif_simulation_report(
    wif: WhatIfResult,
    graph: nx.MultiDiGraph,
    demand: pd.DataFrame,
    week_id: str,
    capability: pd.DataFrame,
    solution_id: str,
) -> SimulationReport:
    """Build a SimulationReport from a WhatIfResult."""
    seq_id = f"replan-{solution_id[:8]}"
    week_demand = demand[demand["window_id"] == week_id]
    total_demanded = int(week_demand["units_demanded"].sum())

    cap_oee: dict[int, float] = {}
    for line in LINE_IDS:
        cap_line = capability[(capability["line_id"] == line) & capability["can_produce"]]
        cap_oee[line] = (
            float(cap_line["median_oee"].median()) if not cap_line.empty else 0.5
        )
    global_oee = float(
        capability[capability["can_produce"]]["median_oee"].median()
        if not capability.empty
        else 0.5
    )

    all_covered: set[str] = set()
    for line in LINE_IDS:
        for sku in wif.committed_per_line.get(line, ()):
            all_covered.add(str(sku))
        for sku in wif.new_sequences.get(line, ()):
            all_covered.add(str(sku))

    covered_units = 0
    dropped_sku_list: list[DroppedSku] = []
    for _, row in week_demand.iterrows():
        sku = str(row["sku_id"])
        units_dem = int(row["units_demanded"])
        if sku not in all_covered:
            dropped_sku_list.append(
                DroppedSku(
                    sku=sku,
                    units_demanded=units_dem,
                    units_dropped=units_dem,
                    margin_lost=0.0,
                    reason="breakdown_capacity",
                )
            )
        else:
            covered_units += units_dem

    coverage = covered_units / total_demanded if total_demanded > 0 else 1.0

    line_metrics_list: list[LineMetrics] = []
    total_prod_h = 0.0
    total_co_h = 0.0
    for line in LINE_IDS:
        h_prod = _safe_float(wif.residual_production_hours_per_line.get(line, 0.0))
        h_co = _safe_float(wif.residual_changeover_hours_per_line.get(line, 0.0))
        h_maint = wif.maintenance_hours if line == wif.affected_line else 0.0
        line_metrics_list.append(
            LineMetrics(
                line=line,  # type: ignore[arg-type]
                oee=round(cap_oee.get(line, global_oee), 4),
                h_productive=round(h_prod, 2),
                h_changeover=round(h_co, 2),
                h_cleaning=8.0,
                h_maintenance=round(h_maint, 2),
                h_idle=0.0,
                coverage=round(coverage, 4),
            )
        )
        total_prod_h += h_prod
        total_co_h += h_co

    return SimulationReport(
        sequence_id=seq_id,
        oee_global=round(global_oee, 4),
        oee_per_line=line_metrics_list,
        h_changes=round(total_co_h, 2),
        h_productive=round(total_prod_h, 2),
        coverage=round(coverage, 4),
        makespan_h=round(_safe_float(wif.makespan_hours), 2),
        dropped_skus=dropped_sku_list,
    )


def _urgent_to_sequence(
    urgent: UrgentDemandResult,
    graph: nx.MultiDiGraph,
    week_id: str,
    w_start: pd.Timestamp,
    solution_id: str,
) -> Sequence:
    """Build a frozen-prefix + urgent-first residual sequence."""
    seq_id = f"urgent-{solution_id[:8]}"
    slots: list[Slot] = []
    base_ts = datetime(w_start.year, w_start.month, w_start.day, PLANT_START_HOUR, 0, 0)

    for line in LINE_IDS:
        committed = tuple(str(s) for s in urgent.committed_per_line.get(line, ()))
        cursor = base_ts
        for i, sku in enumerate(committed):
            prod_h = _node_predicted_hours(graph, sku, line)
            prod_end = cursor + timedelta(hours=prod_h)
            slots.append(
                Slot(
                    id=f"urgent-L{line}-c{i}",
                    line=line,  # type: ignore[arg-type]
                    start=cursor.isoformat(),
                    end=prod_end.isoformat(),
                    kind="production",
                    sku=_display_sku(graph, sku),
                    label=_display_sku(graph, sku),
                    units=_node_units(graph, sku),
                )
            )
            cursor = prod_end
            if i < len(committed) - 1:
                next_sku = committed[i + 1]
                co_h = _edge_hours(graph, sku, next_sku, line)
                if co_h > 0:
                    slots.append(
                        Slot(
                            id=f"urgent-L{line}-cco{i}",
                            line=line,  # type: ignore[arg-type]
                            start=cursor.isoformat(),
                            end=(cursor + timedelta(hours=co_h)).isoformat(),
                            kind="changeover",
                            sku=_display_sku(graph, sku),
                            label=f"→ {_display_sku(graph, next_sku)}",
                            changeover_h=co_h,
                            changeover_source="teorico",
                        )
                    )
                    cursor += timedelta(hours=co_h)

        cursor = base_ts + timedelta(hours=urgent.baseline_hours_per_line[line])
        new_seq = tuple(str(s) for s in urgent.new_sequences.get(line, ()))
        for i, sku in enumerate(new_seq):
            if line == urgent.assigned_line and sku == str(urgent.urgent_node) and i == 0:
                setup_h = urgent.pre_urgent_changeover_hours_per_line.get(line, 0.0)
                if setup_h > 0:
                    slots.append(
                        Slot(
                            id=f"urgent-L{line}-setup",
                            line=line,  # type: ignore[arg-type]
                            start=cursor.isoformat(),
                            end=(cursor + timedelta(hours=setup_h)).isoformat(),
                            kind="changeover",
                            sku=_display_sku(graph, sku),
                            label=f"→ {_display_sku(graph, sku)}",
                            changeover_h=setup_h,
                            changeover_source="teorico",
                        )
                    )
                    cursor += timedelta(hours=setup_h)

            prod_h = _node_predicted_hours(graph, sku, line)
            prod_end = cursor + timedelta(hours=prod_h)
            label = _display_sku(graph, sku)
            if graph.has_node(sku) and graph.nodes[sku].get("is_urgent"):
                label = f"{label} (urgent)"
            slots.append(
                Slot(
                    id=f"urgent-L{line}-r{i}",
                    line=line,  # type: ignore[arg-type]
                    start=cursor.isoformat(),
                    end=prod_end.isoformat(),
                    kind="production",
                    sku=_display_sku(graph, sku),
                    label=label,
                    units=_node_units(graph, sku),
                    is_urgent=bool(graph.has_node(sku) and graph.nodes[sku].get("is_urgent")),
                )
            )
            cursor = prod_end

            if i < len(new_seq) - 1:
                next_sku = new_seq[i + 1]
                co_h = _edge_hours(graph, sku, next_sku, line)
                if co_h > 0:
                    slots.append(
                        Slot(
                            id=f"urgent-L{line}-rco{i}",
                            line=line,  # type: ignore[arg-type]
                            start=cursor.isoformat(),
                            end=(cursor + timedelta(hours=co_h)).isoformat(),
                            kind="changeover",
                            sku=_display_sku(graph, sku),
                            label=f"→ {_display_sku(graph, next_sku)}",
                            changeover_h=co_h,
                            changeover_source="teorico",
                        )
                    )
                    cursor += timedelta(hours=co_h)

    return Sequence(
        id=seq_id,
        week_id=week_id,
        week_start=w_start.date().isoformat(),
        week_end=(w_start + timedelta(days=6)).date().isoformat(),
        source="replan",
        slots=slots,
    )


def _urgent_simulation_report(
    urgent: UrgentDemandResult,
    graph: nx.MultiDiGraph,
    demand: pd.DataFrame,
    week_id: str,
    capability: pd.DataFrame,
    solution_id: str,
) -> SimulationReport:
    seq_id = f"urgent-{solution_id[:8]}"
    week_demand = demand[demand["window_id"] == week_id]
    total_demanded = int(week_demand["units_demanded"].sum()) + urgent.urgent_units

    cap_oee: dict[int, float] = {}
    for line in LINE_IDS:
        cap_line = capability[(capability["line_id"] == line) & capability["can_produce"]]
        cap_oee[line] = (
            float(cap_line["median_oee"].median()) if not cap_line.empty else 0.5
        )
    global_oee = float(
        capability[capability["can_produce"]]["median_oee"].median()
        if not capability.empty
        else 0.5
    )

    covered_nodes: set[str] = set()
    for line in LINE_IDS:
        covered_nodes.update(str(s) for s in urgent.committed_per_line.get(line, ()))
        covered_nodes.update(str(s) for s in urgent.new_sequences.get(line, ()))

    covered_units = urgent.urgent_units if str(urgent.urgent_node) in covered_nodes else 0
    dropped_sku_list: list[DroppedSku] = []
    for _, row in week_demand.iterrows():
        sku = str(row["sku_id"])
        units_dem = int(row["units_demanded"])
        if sku not in covered_nodes:
            dropped_sku_list.append(
                DroppedSku(
                    sku=sku,
                    units_demanded=units_dem,
                    units_dropped=units_dem,
                    margin_lost=0.0,
                    reason="urgent_replan_capacity",
                )
            )
        else:
            covered_units += units_dem

    if str(urgent.urgent_node) not in covered_nodes:
        dropped_sku_list.append(
            DroppedSku(
                sku=str(urgent.urgent_sku),
                units_demanded=urgent.urgent_units,
                units_dropped=urgent.urgent_units,
                margin_lost=0.0,
                reason="urgent_deadline",
            )
        )

    coverage = covered_units / total_demanded if total_demanded > 0 else 1.0
    line_metrics_list: list[LineMetrics] = []
    total_prod_h = 0.0
    total_co_h = 0.0
    for line in LINE_IDS:
        h_prod = _safe_float(urgent.residual_production_hours_per_line.get(line, 0.0))
        h_co = _safe_float(urgent.residual_changeover_hours_per_line.get(line, 0.0))
        line_metrics_list.append(
            LineMetrics(
                line=line,  # type: ignore[arg-type]
                oee=round(cap_oee.get(line, global_oee), 4),
                h_productive=round(h_prod, 2),
                h_changeover=round(h_co, 2),
                h_cleaning=8.0,
                h_maintenance=0.0,
                h_idle=0.0,
                coverage=round(coverage, 4),
            )
        )
        total_prod_h += h_prod
        total_co_h += h_co

    return SimulationReport(
        sequence_id=seq_id,
        oee_global=round(global_oee, 4),
        oee_per_line=line_metrics_list,
        h_changes=round(total_co_h, 2),
        h_productive=round(total_prod_h, 2),
        coverage=round(coverage, 4),
        makespan_h=round(_safe_float(urgent.makespan_hours), 2),
        dropped_skus=dropped_sku_list,
    )


# ---------------------------------------------------------------------------
# Helper: sequence builders
# ---------------------------------------------------------------------------

def _wo_graphs_to_sequence(
    wo_graphs: dict[int, nx.DiGraph],
    week_id: str,
    w_start: pd.Timestamp,
    w_end: pd.Timestamp,
    solution_id: str,
) -> Sequence:
    seq_id = f"real-{solution_id[:8]}"
    slots: list[Slot] = []
    base_ts = datetime(w_start.year, w_start.month, w_start.day, PLANT_START_HOUR, 0, 0)

    for line in LINE_IDS:
        G = wo_graphs.get(line, nx.DiGraph())
        if G.number_of_nodes() == 0:
            continue

        cursor = base_ts
        ordered = sorted(G.nodes, key=lambda nd: G.nodes[nd].get("run_order", 0))

        for i, node_key in enumerate(ordered):
            nd = G.nodes[node_key]
            prod_h = _safe_float(nd.get("actual_hours") or nd.get("predicted_hours", 0.0))

            prod_start = cursor
            prod_end = cursor + timedelta(hours=prod_h)
            slots.append(
                Slot(
                    id=f"real-L{line}-r{i}",
                    line=line,  # type: ignore[arg-type]
                    start=prod_start.isoformat(),
                    end=prod_end.isoformat(),
                    kind="production",
                    sku=str(nd.get("sku_id", "")),
                    label=str(nd.get("sku_id", "")),
                    units=int(nd.get("units_produced", 0)),
                )
            )
            cursor = prod_end

            # Changeover to next run
            if i < len(ordered) - 1:
                next_key = ordered[i + 1]
                if G.has_edge(node_key, next_key):
                    ed = G.edges[node_key, next_key]
                    co_h = _safe_float(ed.get("hours", 0.0))
                    if co_h > 0:
                        drivers = _build_drivers(ed, co_h)
                        slots.append(
                            Slot(
                                id=f"real-L{line}-co{i}",
                                line=line,  # type: ignore[arg-type]
                                start=cursor.isoformat(),
                                end=(cursor + timedelta(hours=co_h)).isoformat(),
                                kind="changeover",
                                changeover_h=co_h,
                                changeover_source=_map_co_source(
                                    str(ed.get("co_source", "tabla_cf_prat"))
                                ),
                                changeover_drivers=drivers or None,
                            )
                        )
                        cursor += timedelta(hours=co_h)

    return Sequence(
        id=seq_id,
        week_id=week_id,
        week_start=w_start.date().isoformat(),
        week_end=w_end.date().isoformat(),
        source="real",
        slots=slots,
    )


def _opt_result_to_sequence(
    result: OptimizerResult,
    graph: nx.MultiDiGraph,
    week_id: str,
    w_start: pd.Timestamp,
    w_end: pd.Timestamp,
    solution_id: str,
) -> Sequence:
    seq_id = f"opt-{solution_id[:8]}"
    slots: list[Slot] = []
    base_ts = datetime(w_start.year, w_start.month, w_start.day, PLANT_START_HOUR, 0, 0)

    for line in LINE_IDS:
        route = result.routes.get(line)
        if route is None or not route.feasible or not route.order:
            continue

        cursor = base_ts
        order = route.order

        for i, sku in enumerate(order):
            sku_str = str(sku)
            nd = graph.nodes.get(sku_str, {})
            line_data = nd.get("line_data", {}).get(line, {})
            prod_h = _safe_float(line_data.get("predicted_hours", 0.0))

            prod_end = cursor + timedelta(hours=prod_h)
            slots.append(
                Slot(
                    id=f"opt-L{line}-n{i}",
                    line=line,  # type: ignore[arg-type]
                    start=cursor.isoformat(),
                    end=prod_end.isoformat(),
                    kind="production",
                    sku=sku_str,
                    label=sku_str,
                    units=int(nd.get("units_demanded", 0)),
                )
            )
            cursor = prod_end

            if i < len(order) - 1:
                next_sku = str(order[i + 1])
                edge_data = graph.get_edge_data(sku_str, next_sku, key=line)
                co_h = _safe_float(edge_data.get("hours", 0.0)) if edge_data else 0.0
                if co_h > 0:
                    drivers = _build_drivers(edge_data or {}, co_h)
                    slots.append(
                        Slot(
                            id=f"opt-L{line}-co{i}",
                            line=line,  # type: ignore[arg-type]
                            start=cursor.isoformat(),
                            end=(cursor + timedelta(hours=co_h)).isoformat(),
                            kind="changeover",
                            changeover_h=co_h,
                            changeover_source="teorico",
                            changeover_drivers=drivers or None,
                        )
                    )
                    cursor += timedelta(hours=co_h)

    return Sequence(
        id=seq_id,
        week_id=week_id,
        week_start=w_start.date().isoformat(),
        week_end=w_end.date().isoformat(),
        source="opt",
        slots=slots,
    )


# ---------------------------------------------------------------------------
# Helper: simulation reports
# ---------------------------------------------------------------------------

def _real_simulation_report(
    seq_id: str,
    wo_graphs: dict[int, nx.DiGraph],
    wo: pd.DataFrame,
    w_start: pd.Timestamp,
    w_end: pd.Timestamp,
    demand: pd.DataFrame,
    week_id: str,
    capability: pd.DataFrame,
) -> SimulationReport:
    prod_wo = wo[
        (wo["wo_kind"] == "production")
        & (wo["end_day"] >= w_start)
        & (wo["end_day"] <= w_end)
    ]
    cleaning_wo = wo[
        (wo["wo_kind"] == "cleaning")
        & (wo["end_day"] >= w_start)
        & (wo["end_day"] <= w_end)
    ]
    maint_wo = wo[
        (wo["wo_kind"] == "maintenance")
        & (wo["end_day"] >= w_start)
        & (wo["end_day"] <= w_end)
    ]

    line_metrics_list: list[LineMetrics] = []
    total_prod_h = 0.0
    total_co_h = 0.0
    oee_num = 0.0
    oee_den = 0.0

    for line in LINE_IDS:
        G = wo_graphs.get(line, nx.DiGraph())
        line_prod = prod_wo[prod_wo["line_id"] == line]

        h_prod = float(line_prod["productive_hours"].sum())
        h_idle = float(line_prod["idle_hours"].sum())
        h_clean = float(cleaning_wo[cleaning_wo["line_id"] == line]["total_hours"].sum())
        h_maint = float(maint_wo[maint_wo["line_id"] == line]["total_hours"].sum())

        h_co = sum(
            _safe_float(G.edges[u, v].get("hours", 0.0)) for u, v in G.edges()
        )

        valid = line_prod[line_prod["oee"].notna() & (line_prod["productive_hours"] > 0)]
        if not valid.empty:
            wts = valid["productive_hours"].values
            oee_line = float((valid["oee"].values * wts).sum() / wts.sum())
        else:
            oee_line = 0.0

        line_metrics_list.append(
            LineMetrics(
                line=line,  # type: ignore[arg-type]
                oee=round(oee_line, 4),
                h_productive=round(h_prod, 2),
                h_changeover=round(h_co, 2),
                h_cleaning=round(h_clean, 2),
                h_maintenance=round(h_maint, 2),
                h_idle=round(h_idle, 2),
                coverage=1.0,
            )
        )
        total_prod_h += h_prod
        total_co_h += h_co
        if h_prod > 0:
            oee_num += oee_line * h_prod
            oee_den += h_prod

    global_oee = oee_num / oee_den if oee_den > 0 else 0.0

    # Makespan = max total time across lines (prod + changeover)
    line_totals = [
        sum(_safe_float(G.edges[u, v].get("hours", 0.0)) for u, v in G.edges())
        + float(prod_wo[prod_wo["line_id"] == line]["productive_hours"].sum())
        for line, G in wo_graphs.items()
    ]
    makespan = max(line_totals) if line_totals else 0.0

    return SimulationReport(
        sequence_id=seq_id,
        oee_global=round(global_oee, 4),
        oee_per_line=line_metrics_list,
        h_changes=round(total_co_h, 2),
        h_productive=round(total_prod_h, 2),
        coverage=1.0,
        makespan_h=round(makespan, 2),
        dropped_skus=[],
    )


def _opt_simulation_report(
    seq_id: str,
    result: OptimizerResult,
    graph: nx.MultiDiGraph,
    demand: pd.DataFrame,
    week_id: str,
    capability: pd.DataFrame,
) -> SimulationReport:
    week_demand = demand[demand["window_id"] == week_id]
    total_demanded = int(week_demand["units_demanded"].sum())

    # Median OEE per line from capability
    cap_oee: dict[int, float] = {}
    for line in LINE_IDS:
        cap_line = capability[(capability["line_id"] == line) & capability["can_produce"]]
        cap_oee[line] = (
            float(cap_line["median_oee"].median()) if not cap_line.empty else 0.5
        )
    global_oee_cap = float(
        capability[capability["can_produce"]]["median_oee"].median()
        if not capability.empty
        else 0.5
    )

    dropped_sku_list: list[DroppedSku] = []
    for sku_id in result.dropped:
        sku_demand = week_demand[week_demand["sku_id"] == sku_id]
        units_dem = int(sku_demand["units_demanded"].sum()) if not sku_demand.empty else 0
        dropped_sku_list.append(
            DroppedSku(
                sku=str(sku_id),
                units_demanded=units_dem,
                units_dropped=units_dem,
                margin_lost=0.0,
                reason="capacity_constraint",
            )
        )

    dropped_units = sum(d.units_dropped for d in dropped_sku_list)
    coverage = (
        max(0.0, 1.0 - dropped_units / total_demanded) if total_demanded > 0 else 1.0
    )

    line_metrics_list: list[LineMetrics] = []
    total_prod_h = 0.0
    total_co_h = 0.0

    for line in LINE_IDS:
        route = result.routes.get(line)
        h_prod = _safe_float(route.production_hours) if (route and route.feasible) else 0.0
        h_co = (
            _safe_float(route.changeover_hours)
            if (route and route.feasible and route.changeover_hours is not None)
            else 0.0
        )
        oee_line = cap_oee.get(line, global_oee_cap)

        line_metrics_list.append(
            LineMetrics(
                line=line,  # type: ignore[arg-type]
                oee=round(oee_line, 4),
                h_productive=round(h_prod, 2),
                h_changeover=round(h_co, 2),
                h_cleaning=8.0,
                h_maintenance=0.0,
                h_idle=0.0,
                coverage=round(coverage, 4),
            )
        )
        total_prod_h += h_prod
        total_co_h += h_co

    return SimulationReport(
        sequence_id=seq_id,
        oee_global=round(global_oee_cap, 4),
        oee_per_line=line_metrics_list,
        h_changes=round(total_co_h, 2),
        h_productive=round(total_prod_h, 2),
        coverage=round(coverage, 4),
        makespan_h=round(_safe_float(result.makespan_hours), 2),
        dropped_skus=dropped_sku_list,
    )


# ---------------------------------------------------------------------------
# Tiny helpers
# ---------------------------------------------------------------------------

def _naive_datetime(value: pd.Timestamp) -> datetime:
    ts = pd.Timestamp(value)
    if ts.tzinfo is not None:
        ts = ts.tz_convert(None)
    return ts.to_pydatetime()


def _display_sku(graph: nx.MultiDiGraph, node: str) -> str:
    if graph.has_node(node):
        attrs = graph.nodes[node]
        return str(attrs.get("display_sku", attrs.get("urgent_base_sku", node)))
    return str(node)


def _node_units(graph: nx.MultiDiGraph, node: str) -> int:
    if graph.has_node(node):
        return int(graph.nodes[node].get("units_demanded", 0) or 0)
    return 0


def _node_predicted_hours(graph: nx.MultiDiGraph, node: str, line: int) -> float:
    if not graph.has_node(node):
        return 0.0
    line_data = graph.nodes[node].get("line_data", {})
    return _safe_float(line_data.get(line, {}).get("predicted_hours", 0.0))


def _edge_base_sku(graph: nx.MultiDiGraph, node: str) -> str:
    if graph.has_node(node):
        return str(graph.nodes[node].get("urgent_base_sku", node))
    return str(node)


def _edge_hours(graph: nx.MultiDiGraph, source: str, target: str, line: int) -> float:
    if source == target:
        return 0.0
    base_source = _edge_base_sku(graph, source)
    base_target = _edge_base_sku(graph, target)
    if base_source == base_target:
        return 0.0

    for src, dst in ((source, target), (base_source, base_target)):
        if not (graph.has_node(src) and graph.has_node(dst)):
            continue
        edge_data = graph.get_edge_data(src, dst, key=line)
        if edge_data is not None:
            return _safe_float(edge_data.get("hours", _MISSING_EDGE_HOURS))
    return _MISSING_EDGE_HOURS


def _safe_float(v: Any, fallback: float = 0.0) -> float:
    try:
        f = float(v)
        return fallback if (isinf(f) or isnan(f)) else f
    except (TypeError, ValueError):
        return fallback


def _find_assigned_line(sku: str, assignments: dict[int, tuple[str, ...]]) -> int | None:
    for line, nodes in assignments.items():
        if sku in nodes:
            return line
    return None


def _map_co_source(raw: str) -> str:
    mapping = {
        "tabla_cf_prat": "teorico",
        "teorico": "teorico",
        "empirico": "hibrido",
        "hibrido": "hibrido",
        "ml": "ml",
    }
    return mapping.get(raw.lower(), "teorico")


def _build_drivers(edge_attrs: dict, co_h: float) -> list[ChangeoverDriver]:
    dominant = str(edge_attrs.get("dominant", ""))
    if not dominant:
        return []
    return [ChangeoverDriver(feature=dominant, impact_h=co_h)]


def _format_range(start: pd.Timestamp, end: pd.Timestamp) -> str:
    months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
    m_s = months[start.month - 1]
    if start.month == end.month and start.year == end.year:
        return f"{start.day}–{end.day} {m_s} {start.year}"
    m_e = months[end.month - 1]
    return f"{start.day} {m_s}–{end.day} {m_e} {end.year}"


def _short_descriptor(sku_count: int, avg_oee: float | None) -> str:
    if sku_count >= 40:
        return "high SKU variety"
    if sku_count >= 20:
        return "medium SKU mix"
    return "focused production"


def _make_reason(sku_count: int, production_rows: int, avg_oee: float | None) -> str:
    parts: list[str] = []
    if production_rows > 0:
        parts.append(f"{production_rows} production WOs across {sku_count} SKUs.")
    if avg_oee is not None:
        if avg_oee < 0.5:
            parts.append("Low OEE — reveals sequencing inefficiencies.")
        elif avg_oee > 0.7:
            parts.append("Strong OEE baseline — good for benchmark comparison.")
        else:
            parts.append("Good stress test for sequencing complexity.")
    return " ".join(parts) if parts else f"{sku_count} SKUs in scope."


def _week_option_for(
    week_id: str,
    demand: pd.DataFrame,
    wo: pd.DataFrame,
    w_start: pd.Timestamp,
    w_end: pd.Timestamp,
) -> WeekOption:
    wnd = demand[demand["window_id"] == week_id]
    sku_count = int(wnd["sku_id"].nunique())
    units = int(wnd["units_demanded"].sum())
    source_val = "demo" if "plan_2026" in wnd["source"].values else "historical"

    prod_wo = wo[
        (wo["wo_kind"] == "production")
        & (wo["end_day"] >= w_start)
        & (wo["end_day"] <= w_end)
    ]
    production_rows = int(len(prod_wo))
    valid = prod_wo[prod_wo["oee"].notna() & (prod_wo["productive_hours"] > 0)]
    avg_oee: float | None = None
    if not valid.empty:
        wts = valid["productive_hours"].values
        avg_oee = float((valid["oee"].values * wts).sum() / wts.sum())
    downtime_h = float(prod_wo["downtime_hours"].sum()) if not prod_wo.empty else None

    return WeekOption(
        id=week_id,
        label=f"{week_id} · {_short_descriptor(sku_count, avg_oee)}",
        range=_format_range(w_start, w_end),
        week_start=w_start.date().isoformat(),
        week_end=w_end.date().isoformat(),
        source=source_val,  # type: ignore[arg-type]
        reason=_make_reason(sku_count, production_rows, avg_oee),
        production_rows=production_rows,
        sku_count=sku_count,
        units=units,
        avg_oee=round(avg_oee, 3) if avg_oee is not None else None,
        downtime_h=round(downtime_h, 1) if downtime_h is not None else None,
    )
