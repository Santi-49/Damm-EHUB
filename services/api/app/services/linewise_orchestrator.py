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
    optimize_graph,
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
    Sequence,
    SimulationReport,
    Slot,
    WeekOption,
)

DATA_DIR = _REPO_ROOT / "data" / "clean"
LINE_IDS: tuple[int, ...] = (14, 17, 19)
PLANT_START_HOUR = 6  # shift starts at 06:00 on window_start Monday


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

        return PlanOptimizeResponse(
            nodes=nodes,
            edges=edges,
            makespan_h=round(_safe_float(result.makespan_hours), 2),
            h_saved=round(h_saved, 2),
            coverage_pct=round(coverage_pct, 4),
            dropped_skus=list(result.dropped),
        )


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

orchestrator = LinewiseOrchestrator()


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
        source=source_val,  # type: ignore[arg-type]
        reason=_make_reason(sku_count, production_rows, avg_oee),
        production_rows=production_rows,
        sku_count=sku_count,
        units=units,
        avg_oee=round(avg_oee, 3) if avg_oee is not None else None,
        downtime_h=round(downtime_h, 1) if downtime_h is not None else None,
    )
