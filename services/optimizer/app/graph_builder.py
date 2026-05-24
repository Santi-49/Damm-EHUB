"""Graph construction orchestrator for LineWise.

Builds two complementary graph representations for a given planning window:

1. ``build_planning_graph(window_id)``
   Complete SKU-level graph used by the optimiser — **single** ``nx.MultiDiGraph``
   covering all three lines.
   - Node  = SKU that has demand in the window AND is capable on at least one line.
   - Node attribute ``line_data`` carries per-line ML node costs; only lines where
     ``can_produce=True`` are present.
   - Edge  = one directed edge per valid (sku_from, sku_to, line_id) triple.
     Line ID is the MultiDiGraph edge key so costs are accessed as
     ``G[sku_from][sku_to][line_id]``.

2. ``build_historical_wo_graph(window_id)``
   Actual paths taken on all three lines during a historical week — returns
   ``dict[int, nx.DiGraph]`` (keys 14/17/19).  Each graph is a **strict linear
   path**: only the run-nodes visited and only the sequential transition edges.
   No isolated nodes, no unused edges.

Visualisation helpers:
   ``visualize_planning_graph(graph)``   — 3-subplot figure, one line-view per subplot.
   ``visualize_wo_graph(graphs)``        — 3-subplot timeline of the historical paths.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import matplotlib.pyplot as plt
import matplotlib.cm as cm
import matplotlib.colors as mcolors
import networkx as nx
import numpy as np
import pandas as pd

from services.node_cost_ml.app.inference import LoadedModel, load_artefacts, predict_node_cost

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "clean"
LINE_IDS: tuple[int, ...] = (14, 17, 19)

LineId = Literal[14, 17, 19]


# ---------------------------------------------------------------------------
# Internal data loaders
# ---------------------------------------------------------------------------

def _demand() -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / "demand.csv")


def _capability() -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / "line_capability.csv")


def _changeover_costs() -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / "changeover_costs.csv")


def _wo_master() -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / "wo_master.csv", parse_dates=["end_day"])


def _wo_changeovers() -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / "wo_changeovers.csv", parse_dates=["transition_day"])


def _window_dates(window_id: str, demand: pd.DataFrame) -> tuple[pd.Timestamp, pd.Timestamp]:
    row = demand[demand["window_id"] == window_id]
    if row.empty:
        raise ValueError(f"window_id {window_id!r} not found in demand.csv")
    first = row.iloc[0]
    return pd.Timestamp(first["window_start"]), pd.Timestamp(first["window_end"])


# ---------------------------------------------------------------------------
# Internal: line-filtered DiGraph view (for visualisation)
# ---------------------------------------------------------------------------

def _line_view(G: nx.MultiDiGraph, line: int) -> nx.DiGraph:
    """Return a plain DiGraph containing only the nodes and edges for *line*."""
    view: nx.DiGraph = nx.DiGraph()
    for node, attrs in G.nodes(data=True):
        if line in attrs.get("line_data", {}):
            view.add_node(
                node,
                predicted_hours=attrs["line_data"][line]["predicted_hours"],
                units_demanded=attrs.get("units_demanded", 0),
            )
    for u, v, key, attrs in G.edges(keys=True, data=True):
        if key == line and view.has_node(u) and view.has_node(v):
            view.add_edge(u, v, **attrs)
    return view


# ---------------------------------------------------------------------------
# 1. Planning graph — single MultiDiGraph across all three lines
# ---------------------------------------------------------------------------

def build_planning_graph(
    window_id: str,
    *,
    demand_df: pd.DataFrame | None = None,
    capability_df: pd.DataFrame | None = None,
    changeover_df: pd.DataFrame | None = None,
    ml_model: LoadedModel | None = None,
) -> nx.MultiDiGraph:
    """Build the complete SKU-level planning graph for *window_id*.

    Returns a **single** ``nx.MultiDiGraph`` covering all three lines.
    Both node costs and edge costs are line-specific: the ML speed model
    predicts a different throughput for each (sku, line) pair, and the
    Tabla CF Prat matrix encodes different changeover durations per line.

    The VRP optimiser queries per-line costs directly from the unified graph
    instead of switching between three separate graph objects.

    Parameters
    ----------
    window_id:
        Planning-window identifier, e.g. ``"2025-W01-7d"``.  Must exist in
        ``demand.csv``.
    demand_df, capability_df, changeover_df:
        Pre-loaded DataFrames.  Pass them when calling in a loop to avoid
        re-reading CSVs on every iteration.
    ml_model:
        Pre-loaded :class:`~services.node_cost_ml.app.inference.LoadedModel`.
        Avoids re-reading CatBoost artefacts on every call.

    Returns
    -------
    ``nx.MultiDiGraph`` with ``graph`` attribute ``window_id``.

    A SKU appears as a node only if it has demand in *window_id* **and** is
    capable (``can_produce=True``) on at least one line.  Self-loop edges
    (same SKU → same SKU) are excluded.

    Node key
        ``sku_id`` string.

    Node attributes
    ~~~~~~~~~~~~~~~
    ``units_demanded``  int     weekly demand for this SKU in the window
                                (same across lines — from demand.csv)
    ``source``          str     demand origin
                                (historico_2025 / plan_2026 / whatif_usuario)
    ``priority``        int     1–5; 5 = cannot be dropped by the optimiser
    ``line_data``       dict    per-line node costs, keyed by line_id.
                                Only lines where ``can_produce=True`` are present.
                                ``line_data[14]["predicted_hours"]`` — ML node cost
                                on L14 (units_demanded / predicted_speed_L14).
                                ``line_data[17]["predicted_hours"]`` — same for L17.
                                ``line_data[19]["predicted_hours"]`` — same for L19.

    Edge key
        ``line_id`` (int).  Access via ``G[sku_from][sku_to][line_id]``.

    Edge attributes  (directed sku_from → sku_to, one edge per line)
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    ``line_id``         int     line this transition belongs to (14 / 17 / 19)
    ``hours``           float   total changeover hours on this line —
                                differs across L14/L17/L19
    ``dominant``        str     changeover segment that drives the cost
                                (beer / container / cap_or_label / …)
    ``co_source``       str     origin of the estimate
                                (tabla_cf_prat / empirico / ml)
    """
    demand = demand_df if demand_df is not None else _demand()
    capability = capability_df if capability_df is not None else _capability()
    changeovers = changeover_df if changeover_df is not None else _changeover_costs()
    lm = ml_model or load_artefacts()

    wnd = demand[demand["window_id"] == window_id].copy()
    if wnd.empty:
        raise ValueError(f"No demand rows for window_id={window_id!r}")

    G: nx.MultiDiGraph = nx.MultiDiGraph(window_id=window_id)

    # --- nodes: predict per-line costs, merge into line_data ---
    for line in LINE_IDS:
        cap_line = capability[(capability["line_id"] == line) & capability["can_produce"]]
        capable_skus = set(cap_line["sku_id"])
        nodes_df = wnd[wnd["sku_id"].isin(capable_skus)].copy()
        if nodes_df.empty:
            continue

        inference_input = pd.DataFrame({
            "line_id": line,
            "sku_id": nodes_df["sku_id"].values,
            "units_produced": nodes_df["units_demanded"].values,
        })
        cost_rows = predict_node_cost(inference_input, loaded=lm)
        nodes_df = nodes_df.copy()
        nodes_df["predicted_hours"] = cost_rows["predicted_hours"].values

        for _, row in nodes_df.iterrows():
            sku = row["sku_id"]
            if G.has_node(sku):
                # Node already added by a previous line — just extend line_data
                G.nodes[sku]["line_data"][line] = {
                    "predicted_hours": float(row["predicted_hours"]),
                }
            else:
                G.add_node(
                    sku,
                    units_demanded=int(row["units_demanded"]),
                    source=str(row.get("source", "unknown")),
                    priority=int(row.get("priority", 3)),
                    line_data={
                        line: {"predicted_hours": float(row["predicted_hours"])},
                    },
                )

    # --- edges: one per (sku_from, sku_to, line_id), keyed by line_id ---
    all_skus = set(G.nodes)
    for line in LINE_IDS:
        co_line = changeovers[changeovers["line_id"] == line]
        co_relevant = co_line[
            co_line["sku_from_id"].isin(all_skus) & co_line["sku_to_id"].isin(all_skus)
        ]
        for _, row in co_relevant.iterrows():
            src, dst = row["sku_from_id"], row["sku_to_id"]
            if src == dst:
                continue
            # Only add edge if both endpoints are actually capable on this line
            if (
                line in G.nodes[src].get("line_data", {})
                and line in G.nodes[dst].get("line_data", {})
            ):
                G.add_edge(
                    src,
                    dst,
                    key=line,
                    line_id=line,
                    hours=float(row["total_hours"]),
                    dominant=str(row.get("dominant_component", "")),
                    co_source=str(row.get("source", "tabla_cf_prat")),
                )

    return G


# ---------------------------------------------------------------------------
# 2. Historical WO graphs — one linear path per line
# ---------------------------------------------------------------------------

def _build_line_path(
    line_id: int,
    w_start: pd.Timestamp,
    w_end: pd.Timestamp,
    window_id: str,
    wo: pd.DataFrame,
    wo_co: pd.DataFrame,
    lm: LoadedModel,
) -> nx.DiGraph:
    """Build the linear execution path for one line.  Internal helper."""
    line_wo = wo[
        (wo["line_id"] == line_id)
        & (wo["wo_kind"] == "production")
        & (wo["end_day"] >= w_start)
        & (wo["end_day"] <= w_end)
    ].sort_values("line_sequence_order").copy()

    G = nx.DiGraph(line_id=line_id, window_id=window_id)
    if line_wo.empty:
        return G

    # Collapse consecutive same-SKU WOs into runs
    sku_changed = (line_wo["sku_id"].shift() != line_wo["sku_id"]).astype(int)
    line_wo["_run_idx"] = sku_changed.cumsum()

    runs = (
        line_wo.groupby("_run_idx", sort=True)
        .agg(
            sku_id=("sku_id", "first"),
            wo_ids=("wo_id", list),
            units_produced=("units_produced", "sum"),
            actual_hours=("productive_hours", "sum"),
            run_start_order=("line_sequence_order", "min"),
        )
        .reset_index()
    )

    # Predict node costs
    cost_rows = predict_node_cost(
        pd.DataFrame({
            "line_id": line_id,
            "sku_id": runs["sku_id"].values,
            "units_produced": runs["units_produced"].values,
        }),
        loaded=lm,
    )
    runs["predicted_hours"] = cost_rows["predicted_hours"].values

    # Add run nodes (all are on the path — no isolated nodes possible)
    node_keys: list[str] = []
    for i, row in runs.iterrows():
        key = f"{row['sku_id']}_r{int(row['_run_idx'])}"
        node_keys.append(key)
        G.add_node(
            key,
            sku_id=row["sku_id"],
            wo_ids=row["wo_ids"],
            units_produced=int(row["units_produced"]),
            predicted_hours=float(row["predicted_hours"]),
            actual_hours=float(row["actual_hours"]),
            run_order=int(i),
        )

    # Build changeover lookup: wo_to_id → row
    line_co = wo_co[
        (wo_co["line_id"] == line_id)
        & (wo_co["transition_day"] >= w_start)
        & (wo_co["transition_day"] <= w_end)
    ]
    co_by_wo_to: dict[str, pd.Series] = {
        row["wo_to_id"]: row for _, row in line_co.iterrows()
    }

    # Add only the sequential path edges
    for i in range(len(node_keys) - 1):
        dst_run = runs.iloc[i + 1]
        first_wo = dst_run["wo_ids"][0] if dst_run["wo_ids"] else None
        co_row = co_by_wo_to.get(first_wo)

        if co_row is not None:
            hours = float(co_row.get("estimated_changeover_hours", 0.0) or 0.0)
            dominant = str(co_row.get("dominant_component", ""))
            co_source = str(co_row.get("changeover_cost_source", "tabla_cf_prat"))
            tid = str(co_row.get("transition_id", ""))
        else:
            hours = 0.0
            dominant = ""
            co_source = "unknown"
            tid = None

        G.add_edge(
            node_keys[i],
            node_keys[i + 1],
            hours=hours,
            dominant=dominant,
            co_source=co_source,
            transition_id=tid,
        )

    return G


def build_historical_wo_graph(
    window_id: str,
    *,
    demand_df: pd.DataFrame | None = None,
    wo_df: pd.DataFrame | None = None,
    wo_co_df: pd.DataFrame | None = None,
    ml_model: LoadedModel | None = None,
) -> dict[int, nx.DiGraph]:
    """Build the historical execution graphs for all three lines in *window_id*.

    Returns one ``nx.DiGraph`` per line (keys 14, 17, 19).  Each graph is a
    **strict linear path** — only the run-nodes that were actually visited and
    only the sequential transition edges between them.  There are no isolated
    nodes and no edges that were not part of the executed sequence.

    **Run collapsing** — consecutive WOs of the same SKU on the same line are
    merged into a single *run* node.  This matches the granularity at which
    the node-cost ML model was trained: one run = one (sku, line) chunk.  The
    merge is order-safe because ``wo_master`` is sorted by
    ``line_sequence_order`` (a deterministic position derived from
    ``end_day, source_row_order, wo_id`` — there are no timestamps in the
    historical exports).

    **Window filtering** — WOs are included when ``end_day`` falls within
    [``window_start``, ``window_end``] as declared in ``demand.csv`` for the
    given *window_id*.  Only ``wo_kind == "production"`` rows are considered;
    cleanings and maintenance WOs are excluded.

    **Edge costs** — come from ``wo_changeovers.csv``.  These are **not**
    observed changeover durations (the historical Damm exports contain no
    start/end timestamps); they are the theoretical estimates joined from
    ``changeover_costs.csv`` (Tabla CF Prat rules).  The lookup key is
    ``wo_to_id`` — the first WO of the destination run.  When no matching row
    is found in ``wo_changeovers``, the edge is still added with
    ``co_source="unknown"`` and ``hours=0.0``.

    Parameters
    ----------
    window_id:
        Planning-window identifier, e.g. ``"2025-W01-7d"``.  Must exist in
        ``demand.csv`` so start/end dates can be resolved.
    demand_df, wo_df, wo_co_df:
        Pre-loaded DataFrames.  Pass them when calling in a loop.
    ml_model:
        Pre-loaded :class:`~services.node_cost_ml.app.inference.LoadedModel`.

    Returns
    -------
    ``dict[int, nx.DiGraph]`` — keys are 14, 17, 19.
    Lines with no production WOs in the window return an empty graph.

    Node key
        ``"<sku_id>_r<run_idx>"`` — unique even when the same SKU recurs
        on the line within one week.

    Node attributes
    ~~~~~~~~~~~~~~~
    ``sku_id``          str         SKU produced during this run
    ``wo_ids``          list[str]   WO IDs collapsed into this run (≥1)
    ``units_produced``  int         sum of ``units_produced`` across the run's WOs
    ``predicted_hours`` float       ML node cost: ``units_produced / predicted_speed``
                                    on this line (``node_cost_ml`` inference)
    ``actual_hours``    float       sum of ``productive_hours`` from ``wo_master``
                                    (machine-running time only; excludes downtime)
    ``run_order``       int         0-based position in the execution sequence

    Edge attributes  (directed run_i → run_{i+1}, strictly sequential)
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    ``hours``           float       theoretical changeover hours from
                                    ``wo_changeovers.estimated_changeover_hours``
                                    (sourced from Tabla CF Prat, not observed)
    ``dominant``        str         changeover segment driving the max-rule total,
                                    e.g. ``"secondary_pack"`` or ``"container"``
    ``co_source``       str         ``"tabla_cf_prat"`` for all current rows;
                                    ``"unknown"`` when the transition is absent
                                    from ``wo_changeovers``
    ``transition_id``   str | None  ``wo_changeovers.transition_id`` (equals
                                    ``wo_to_id`` of the destination WO)
    """
    demand = demand_df if demand_df is not None else _demand()
    wo = wo_df if wo_df is not None else _wo_master()
    wo_co = wo_co_df if wo_co_df is not None else _wo_changeovers()
    lm = ml_model or load_artefacts()

    w_start, w_end = _window_dates(window_id, demand)

    return {
        line: _build_line_path(line, w_start, w_end, window_id, wo, wo_co, lm)
        for line in LINE_IDS
    }


# ---------------------------------------------------------------------------
# 3. Visualise planning graph (single MultiDiGraph, three line-view subplots)
# ---------------------------------------------------------------------------

def visualize_planning_graph(
    graph: nx.MultiDiGraph,
    *,
    figsize: tuple[float, float] = (22, 7),
    max_edge_hours: float | None = None,
) -> plt.Figure:
    """Visualise the planning graph as three line-view subplots.

    Each subplot shows the nodes and edges that are active on that specific
    line (filtered from the unified MultiDiGraph).  Node size is proportional
    to the ML-predicted hours for that line.  Edge colour encodes changeover
    hours (green = cheap, red = expensive) on a shared scale.

    Parameters
    ----------
    graph:
        Output of :func:`build_planning_graph`.
    figsize:
        Matplotlib figure size in inches.
    max_edge_hours:
        Upper bound for the colour scale.  Auto-detected if ``None``.

    Returns
    -------
    ``matplotlib.figure.Figure`` — call ``plt.show()`` or ``.savefig()`` on it.
    """
    cmap = plt.colormaps["RdYlGn_r"]

    if max_edge_hours is None:
        all_hours = [d["hours"] for _, _, _, d in graph.edges(keys=True, data=True)]
        max_edge_hours = max(all_hours) if all_hours else 1.0

    norm = mcolors.Normalize(vmin=0, vmax=max_edge_hours)
    window_id = graph.graph.get("window_id", "")

    fig, axes = plt.subplots(1, 3, figsize=figsize, constrained_layout=True)
    fig.suptitle(f"Planning graph — {window_id}", fontsize=14, fontweight="bold")

    for ax, line in zip(axes, LINE_IDS):
        G = _line_view(graph, line)
        n, e = G.number_of_nodes(), G.number_of_edges()
        ax.set_title(f"L{line}  ({n} SKUs, {e} transitions)")

        if n == 0:
            ax.text(0.5, 0.5, "No capable SKUs", ha="center", va="center",
                    transform=ax.transAxes)
            ax.axis("off")
            continue

        pos = nx.circular_layout(G)

        node_hours = [G.nodes[nd].get("predicted_hours", 1.0) for nd in G.nodes]
        max_h = max(node_hours) if node_hours else 1.0
        node_sizes = [300 + 1500 * (h / max_h) for h in node_hours]
        labels = {nd: nd[:8] for nd in G.nodes}

        edges = list(G.edges(data=True))
        edge_colors = [cmap(norm(d.get("hours", 0.0))) for _, _, d in edges]
        edge_widths = [0.5 + 2.0 * (d.get("hours", 0.0) / max_edge_hours) for _, _, d in edges]

        nx.draw_networkx_nodes(G, pos, node_size=node_sizes, node_color="#4C9BE8",
                               alpha=0.85, ax=ax)
        nx.draw_networkx_labels(G, pos, labels=labels, font_size=5, ax=ax)
        nx.draw_networkx_edges(G, pos, edge_color=edge_colors, width=edge_widths,
                               arrows=True, arrowsize=8,
                               connectionstyle="arc3,rad=0.1", ax=ax)
        ax.axis("off")

    sm = cm.ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=axes, orientation="vertical", fraction=0.02, pad=0.04)
    cbar.set_label("Changeover hours", fontsize=9)

    return fig


# ---------------------------------------------------------------------------
# 4. Visualise historical WO graphs (dict of linear paths, three subplots)
# ---------------------------------------------------------------------------

def visualize_wo_graph(
    graphs: dict[int, nx.DiGraph],
    *,
    figsize: tuple[float, float] = (22, 6),
) -> plt.Figure:
    """Visualise the historical execution paths for all three lines.

    Each subplot shows the linear run-sequence for one line.  Nodes are laid
    out left-to-right in execution order.  Node colour encodes the
    predicted/actual hours ratio (green = ML matches reality, red = large
    over-prediction).  Edge labels show changeover hours and the dominant
    component.

    Parameters
    ----------
    graphs:
        Output of :func:`build_historical_wo_graph`.

    Returns
    -------
    ``matplotlib.figure.Figure``.
    """
    window_id = next(
        (G.graph.get("window_id", "") for G in graphs.values()), ""
    )

    fig, axes = plt.subplots(1, 3, figsize=figsize, constrained_layout=True)
    fig.suptitle(f"Historical execution paths — {window_id}", fontsize=14, fontweight="bold")

    for ax, line in zip(axes, LINE_IDS):
        G = graphs.get(line, nx.DiGraph())
        n = G.number_of_nodes()
        ax.set_title(f"L{line}  ({n} runs)")

        if n == 0:
            ax.text(0.5, 0.5, "No production runs", ha="center", va="center",
                    transform=ax.transAxes)
            ax.axis("off")
            continue

        ordered = sorted(G.nodes, key=lambda nd: G.nodes[nd].get("run_order", 0))
        pos = {nd: (i, 0.0) for i, nd in enumerate(ordered)}

        def _ratio_color(nd: str) -> str:
            pred = G.nodes[nd].get("predicted_hours", 0.0)
            actual = G.nodes[nd].get("actual_hours", 0.0)
            if actual <= 0:
                return "#AAAAAA"
            ratio_clamped = min(pred / actual, 2.0) / 2.0
            r = int(255 * ratio_clamped)
            g_ch = int(255 * (1 - ratio_clamped))
            return f"#{r:02X}{g_ch:02X}50"

        node_colors = [_ratio_color(nd) for nd in ordered]
        units = [G.nodes[nd].get("units_produced", 1) for nd in ordered]
        max_u = max(units) if units else 1
        node_sizes = [500 + 2000 * (u / max_u) for u in units]
        labels = {
            nd: f"{G.nodes[nd]['sku_id']}\n{G.nodes[nd].get('predicted_hours', 0):.1f}h"
            for nd in ordered
        }

        nx.draw_networkx_nodes(G, pos, nodelist=ordered, node_size=node_sizes,
                               node_color=node_colors, alpha=0.9, ax=ax)
        nx.draw_networkx_labels(G, pos, labels=labels, font_size=6, ax=ax)
        nx.draw_networkx_edges(G, pos, arrows=True, arrowsize=12,
                               edge_color="#555555", width=2, ax=ax)

        edge_labels = {
            (u, v): f"{d.get('hours', 0.0):.1f}h\n{d.get('dominant', '')}"
            for u, v, d in G.edges(data=True)
        }
        nx.draw_networkx_edge_labels(G, pos, edge_labels=edge_labels,
                                     font_size=5, label_pos=0.3, ax=ax)

        total_co = sum(d.get("hours", 0.0) for _, _, d in G.edges(data=True))
        total_pred = sum(G.nodes[nd].get("predicted_hours", 0.0) for nd in G.nodes)
        total_actual = sum(G.nodes[nd].get("actual_hours", 0.0) for nd in G.nodes)
        ax.set_xlabel(
            f"CO: {total_co:.1f}h  |  pred: {total_pred:.1f}h  |  actual: {total_actual:.1f}h",
            fontsize=7,
        )
        ax.axis("off")

    return fig


# ---------------------------------------------------------------------------
# Quick smoke test (run with: python -m services.optimizer.app.graph_builder)
# ---------------------------------------------------------------------------

def _smoke_test() -> None:
    demand = _demand()
    window_id = demand["window_id"].iloc[0]
    print(f"window_id: {window_id}")

    print("\nbuild_planning_graph ...")
    G = build_planning_graph(window_id, demand_df=demand)
    print(f"  nodes: {G.number_of_nodes()}")
    print(f"  edges (total across all lines): {G.number_of_edges()}")
    for line in LINE_IDS:
        view = _line_view(G, line)
        print(f"  L{line}: {view.number_of_nodes()} nodes, {view.number_of_edges()} edges")

    # Show per-line node cost difference for the first shared SKU
    shared = [
        n for n in G.nodes
        if len(G.nodes[n].get("line_data", {})) > 1
    ]
    if shared:
        sku = shared[0]
        print(f"\n  Node cost for {sku}:")
        for ln, ld in G.nodes[sku]["line_data"].items():
            print(f"    L{ln}: {ld['predicted_hours']:.2f}h")

    fig = visualize_planning_graph(G)
    fig.savefig("planning_graph.png", dpi=120, bbox_inches="tight")
    print("\n  saved: planning_graph.png")

    print("\nbuild_historical_wo_graph ...")
    wo_graphs = build_historical_wo_graph(window_id, demand_df=demand)
    for line, path in wo_graphs.items():
        print(f"  L{line}: {path.number_of_nodes()} runs, {path.number_of_edges()} transitions")

    fig2 = visualize_wo_graph(wo_graphs)
    fig2.savefig("wo_path_graph.png", dpi=120, bbox_inches="tight")
    print("\n  saved: wo_path_graph.png")


if __name__ == "__main__":
    _smoke_test()
