"""Graph construction orchestrator for LineWise.

Builds two complementary graph representations for a given planning window:

1. ``build_planning_graph(window_id)``
   Complete SKU-level graph used by the optimiser.
   - One ``nx.DiGraph`` per line (L14 / L17 / L19).
   - Node  = SKU that has demand AND can be produced on that line.
   - Node cost  = ML-predicted productive hours for the weekly demand bucket
                  (units_demanded / predicted_speed, via node_cost_ml).
   - Edge weight = changeover hours from ``changeover_costs.csv``
                   (Tabla CF Prat theoretical floor, per-line directed).

2. ``build_historical_wo_graph(window_id, line_id)``
   Actual path taken on a line during a historical week.
   - Nodes = consecutive same-SKU runs of work orders (WOs collapsed).
   - Node cost  = ML-predicted hours for the observed ``units_produced``.
   - Edges = observed transitions with costs from ``wo_changeovers.csv``.

Visualisation helpers:
   ``visualize_planning_graph(graphs)``   — Matplotlib figure, one subplot per line.
   ``visualize_wo_graph(graph)``          — Timeline-style path for a historical graph.
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
    """Return (window_start, window_end) for a given window_id."""
    row = demand[demand["window_id"] == window_id]
    if row.empty:
        raise ValueError(f"window_id {window_id!r} not found in demand.csv")
    first = row.iloc[0]
    return pd.Timestamp(first["window_start"]), pd.Timestamp(first["window_end"])


# ---------------------------------------------------------------------------
# 1. Planning graph
# ---------------------------------------------------------------------------

def build_planning_graph(
    window_id: str,
    *,
    demand_df: pd.DataFrame | None = None,
    capability_df: pd.DataFrame | None = None,
    changeover_df: pd.DataFrame | None = None,
    ml_model: LoadedModel | None = None,
) -> dict[int, nx.DiGraph]:
    """Build the complete SKU-level planning graph for *window_id*.

    Returns one ``nx.DiGraph`` per line (keys 14, 17, 19).  Node weights and
    edge weights are **line-specific**: the ML speed model predicts a different
    throughput for each (sku, line) pair, and the Tabla CF Prat matrix encodes
    different changeover durations per line.  The VRP optimiser consumes each
    graph independently — one vehicle (line) per graph.

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
    dict[int, nx.DiGraph]
        Keys are line IDs (14, 17, 19).  Each graph contains only SKUs that
        (a) have demand in *window_id* AND (b) are capable on that line
        (``can_produce=True`` in ``line_capability.csv``).  A line with no
        eligible SKUs gets an empty graph.

    Node key
        ``sku_id`` string.

    Node attributes
    ~~~~~~~~~~~~~~~
    ``sku_id``          str     SKU identifier (same as node key)
    ``units_demanded``  int     weekly demand units for this SKU/window
    ``predicted_hours`` float   ML node cost: units_demanded / predicted_speed
                                on *this* line — differs across L14/L17/L19
    ``source``          str     demand origin (historico_2025 / plan_2026 / whatif_usuario)
    ``priority``        int     1–5; 5 = cannot be dropped by the optimiser

    Edge attributes  (directed sku_from → sku_to, self-loops excluded)
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    ``hours``           float   total changeover hours on *this* line —
                                differs across L14/L17/L19
    ``dominant``        str     changeover segment that drives the cost
                                (beer / container / cap_or_label / …)
    ``co_source``       str     origin of the cost estimate
                                (tabla_cf_prat / empirico / ml)
    """
    demand = demand_df if demand_df is not None else _demand()
    capability = capability_df if capability_df is not None else _capability()
    changeovers = changeover_df if changeover_df is not None else _changeover_costs()
    lm = ml_model or load_artefacts()

    wnd = demand[demand["window_id"] == window_id].copy()
    if wnd.empty:
        raise ValueError(f"No demand rows for window_id={window_id!r}")

    graphs: dict[int, nx.DiGraph] = {}

    for line in LINE_IDS:
        cap_line = capability[(capability["line_id"] == line) & capability["can_produce"]]
        capable_skus = set(cap_line["sku_id"])

        nodes_df = wnd[wnd["sku_id"].isin(capable_skus)].copy()

        G = nx.DiGraph(line_id=line, window_id=window_id)

        if nodes_df.empty:
            graphs[line] = G
            continue

        # Predict node cost: rename units_demanded → units_produced for the ML call
        inference_input = pd.DataFrame({
            "line_id": line,
            "sku_id": nodes_df["sku_id"].values,
            "units_produced": nodes_df["units_demanded"].values,
        })
        cost_rows = predict_node_cost(inference_input, loaded=lm)
        nodes_df = nodes_df.copy()
        nodes_df["predicted_hours"] = cost_rows["predicted_hours"].values

        # Add nodes
        for _, row in nodes_df.iterrows():
            G.add_node(
                row["sku_id"],
                sku_id=row["sku_id"],
                units_demanded=int(row["units_demanded"]),
                predicted_hours=float(row["predicted_hours"]),
                source=str(row.get("source", "unknown")),
                priority=int(row.get("priority", 3)),
            )

        # Add edges from the theoretical changeover matrix
        sku_ids = set(G.nodes)
        co_line = changeovers[changeovers["line_id"] == line]
        co_relevant = co_line[
            co_line["sku_from_id"].isin(sku_ids) & co_line["sku_to_id"].isin(sku_ids)
        ]
        for _, row in co_relevant.iterrows():
            src, dst = row["sku_from_id"], row["sku_to_id"]
            if src != dst:
                G.add_edge(
                    src,
                    dst,
                    hours=float(row["total_hours"]),
                    dominant=str(row.get("dominant_component", "")),
                    co_source=str(row.get("source", "tabla_cf_prat")),
                )

        graphs[line] = G

    return graphs


# ---------------------------------------------------------------------------
# 2. Historical WO graph
# ---------------------------------------------------------------------------

def build_historical_wo_graph(
    window_id: str,
    line_id: int,
    *,
    demand_df: pd.DataFrame | None = None,
    wo_df: pd.DataFrame | None = None,
    wo_co_df: pd.DataFrame | None = None,
    ml_model: LoadedModel | None = None,
) -> nx.DiGraph:
    """Build the historical execution graph for *line_id* in *window_id*.

    Encodes the **actual production path taken**, not an optimiser proposal.
    Used for post-mortem analysis and as a baseline to compare against the
    optimiser output.

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
    ``changeover_costs.csv`` (Tabla CF Prat rules, ``source = tabla_cf_prat``).
    The edge lookup key is ``wo_to_id`` — the first WO of the destination run.

    Parameters
    ----------
    window_id:
        Planning-window identifier, e.g. ``"2025-W01-7d"``.  Must exist in
        ``demand.csv`` so the start/end dates can be resolved.
    line_id:
        One of 14, 17, 19.
    demand_df, wo_df, wo_co_df:
        Pre-loaded DataFrames.  Pass them when calling in a loop.
    ml_model:
        Pre-loaded :class:`~services.node_cost_ml.app.inference.LoadedModel`.

    Returns
    -------
    ``nx.DiGraph`` with ``graph`` attributes ``line_id`` and ``window_id``.
    Returns an empty graph when no production WOs fall in the window.

    Node key
        ``"<sku_id>_r<run_idx>"`` — unique even when the same SKU appears
        multiple times on the line in one week.

    Node attributes
    ~~~~~~~~~~~~~~~
    ``sku_id``          str         SKU produced during this run
    ``wo_ids``          list[str]   WO IDs collapsed into this run (≥1)
    ``units_produced``  int         sum of ``units_produced`` across the run's WOs
    ``predicted_hours`` float       ML node cost: ``units_produced / predicted_speed``
                                    on *this* line (``node_cost_ml`` inference)
    ``actual_hours``    float       sum of ``productive_hours`` from ``wo_master``
                                    (machine-running time only; excludes downtime)
    ``run_order``       int         0-based position in the line's execution sequence

    Edge attributes  (directed: run_i → run_{i+1}, path order)
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    ``hours``           float       theoretical changeover hours from
                                    ``wo_changeovers.estimated_changeover_hours``
                                    (sourced from Tabla CF Prat, not observed)
    ``dominant``        str         changeover segment driving the max-rule total,
                                    e.g. ``"secondary_pack"`` or ``"container"``
    ``co_source``       str         ``"tabla_cf_prat"`` for all current rows;
                                    ``"unknown"`` when the transition is absent
                                    from ``wo_changeovers`` (edge still added)
    ``transition_id``   str | None  ``wo_changeovers.transition_id`` (equals
                                    ``wo_to_id`` of the destination WO)
    """
    demand = demand_df if demand_df is not None else _demand()
    wo = wo_df if wo_df is not None else _wo_master()
    wo_co = wo_co_df if wo_co_df is not None else _wo_changeovers()
    lm = ml_model or load_artefacts()

    w_start, w_end = _window_dates(window_id, demand)

    # Filter WOs for this line and window
    line_wo = wo[
        (wo["line_id"] == line_id)
        & (wo["wo_kind"] == "production")
        & (wo["end_day"] >= w_start)
        & (wo["end_day"] <= w_end)
    ].sort_values("line_sequence_order").copy()

    if line_wo.empty:
        return nx.DiGraph(line_id=line_id, window_id=window_id)

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

    # Predict node costs via ML
    inference_input = pd.DataFrame({
        "line_id": line_id,
        "sku_id": runs["sku_id"].values,
        "units_produced": runs["units_produced"].values,
    })
    cost_rows = predict_node_cost(inference_input, loaded=lm)
    runs["predicted_hours"] = cost_rows["predicted_hours"].values

    G = nx.DiGraph(line_id=line_id, window_id=window_id)

    # Add run nodes
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

    # Build edge lookup from wo_changeovers
    # Filter to this line and window
    line_co = wo_co[
        (wo_co["line_id"] == line_id)
        & (wo_co["transition_day"] >= w_start)
        & (wo_co["transition_day"] <= w_end)
    ]
    # Index: wo_to_id → transition row (one transition per WO arrival)
    co_by_wo_to: dict[str, pd.Series] = {
        row["wo_to_id"]: row for _, row in line_co.iterrows()
    }

    # Add edges between consecutive runs
    for i in range(len(node_keys) - 1):
        src_key = node_keys[i]
        dst_key = node_keys[i + 1]
        dst_run = runs.iloc[i + 1]

        # Look up changeover via the first WO of the destination run
        first_wo_of_dst = dst_run["wo_ids"][0] if dst_run["wo_ids"] else None
        co_row = co_by_wo_to.get(first_wo_of_dst)

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
            src_key,
            dst_key,
            hours=hours,
            dominant=dominant,
            co_source=co_source,
            transition_id=tid,
        )

    return G


# ---------------------------------------------------------------------------
# 3. Visualise planning graph
# ---------------------------------------------------------------------------

def visualize_planning_graph(
    graphs: dict[int, nx.DiGraph],
    *,
    figsize: tuple[float, float] = (22, 7),
    max_edge_hours: float | None = None,
) -> plt.Figure:
    """Visualise the planning graphs (one subplot per line).

    Node size ∝ predicted_hours (node cost).
    Edge colour encodes changeover hours (blue = cheap, red = expensive).

    Parameters
    ----------
    graphs:
        Output of :func:`build_planning_graph`.
    figsize:
        Matplotlib figure size in inches.
    max_edge_hours:
        Clip edge colours at this upper bound. Auto-detected if ``None``.

    Returns
    -------
    ``matplotlib.figure.Figure`` — call ``plt.show()`` or ``.savefig()`` on it.
    """
    cmap = plt.colormaps["RdYlGn_r"]

    # Global max for consistent colour scale across lines
    if max_edge_hours is None:
        all_hours = [
            d["hours"]
            for G in graphs.values()
            for _, _, d in G.edges(data=True)
        ]
        max_edge_hours = max(all_hours) if all_hours else 1.0

    norm = mcolors.Normalize(vmin=0, vmax=max_edge_hours)

    fig, axes = plt.subplots(1, 3, figsize=figsize, constrained_layout=True)
    window_id = next(iter(graphs.values())).graph.get("window_id", "")
    fig.suptitle(
        f"Planning graph — {window_id}",
        fontsize=14,
        fontweight="bold",
    )

    for ax, line in zip(axes, LINE_IDS):
        G = graphs.get(line, nx.DiGraph())
        ax.set_title(f"L{line}  ({G.number_of_nodes()} SKUs, {G.number_of_edges()} transitions)")

        if G.number_of_nodes() == 0:
            ax.text(0.5, 0.5, "No capable SKUs", ha="center", va="center", transform=ax.transAxes)
            ax.axis("off")
            continue

        pos = nx.circular_layout(G)

        # Node sizes and labels
        node_hours = [G.nodes[n].get("predicted_hours", 1.0) for n in G.nodes]
        max_h = max(node_hours) if node_hours else 1.0
        node_sizes = [300 + 1500 * (h / max_h) for h in node_hours]
        labels = {n: n[:8] for n in G.nodes}  # truncate long SKU IDs

        # Edge colours
        edges = list(G.edges(data=True))
        edge_colors = [cmap(norm(d.get("hours", 0.0))) for _, _, d in edges]
        edge_widths = [0.5 + 2.0 * (d.get("hours", 0.0) / max_edge_hours) for _, _, d in edges]

        nx.draw_networkx_nodes(G, pos, node_size=node_sizes, node_color="#4C9BE8",
                               alpha=0.85, ax=ax)
        nx.draw_networkx_labels(G, pos, labels=labels, font_size=5, ax=ax)
        nx.draw_networkx_edges(
            G, pos,
            edge_color=edge_colors,
            width=edge_widths,
            arrows=True,
            arrowsize=8,
            connectionstyle="arc3,rad=0.1",
            ax=ax,
        )
        ax.axis("off")

    # Colour bar
    sm = cm.ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=axes, orientation="vertical", fraction=0.02, pad=0.04)
    cbar.set_label("Changeover hours", fontsize=9)

    return fig


# ---------------------------------------------------------------------------
# 4. Visualise historical WO graph (path taken)
# ---------------------------------------------------------------------------

def visualize_wo_graph(
    graph: nx.DiGraph,
    *,
    figsize: tuple[float, float] = (16, 5),
) -> plt.Figure:
    """Visualise the actual production path for one line in one week.

    Nodes are arranged left → right in execution order.
    Node colour encodes predicted vs actual hours ratio (green = match, red = over-predict).
    Edge label shows changeover hours.

    Parameters
    ----------
    graph:
        Output of :func:`build_historical_wo_graph`.

    Returns
    -------
    ``matplotlib.figure.Figure``.
    """
    G = graph
    line_id = G.graph.get("line_id", "?")
    window_id = G.graph.get("window_id", "?")

    fig, ax = plt.subplots(figsize=figsize)
    ax.set_title(
        f"Historical execution path — L{line_id}  {window_id}",
        fontsize=13,
        fontweight="bold",
    )

    if G.number_of_nodes() == 0:
        ax.text(0.5, 0.5, "No production runs in this window",
                ha="center", va="center", transform=ax.transAxes, fontsize=12)
        ax.axis("off")
        return fig

    # Layout: nodes in execution order along x-axis
    ordered_nodes = sorted(G.nodes, key=lambda n: G.nodes[n].get("run_order", 0))
    pos = {node: (i, 0.0) for i, node in enumerate(ordered_nodes)}

    # Node colour: predicted / actual hours ratio (capped)
    def _ratio_color(node: str) -> str:
        pred = G.nodes[node].get("predicted_hours", 0.0)
        actual = G.nodes[node].get("actual_hours", 0.0)
        if actual <= 0:
            return "#AAAAAA"
        ratio = pred / actual
        # Green < 1 (under-predict), Red > 1.5 (large over-predict)
        ratio_clamped = min(ratio, 2.0) / 2.0
        r = int(255 * ratio_clamped)
        g = int(255 * (1 - ratio_clamped))
        return f"#{r:02X}{g:02X}50"

    node_colors = [_ratio_color(n) for n in ordered_nodes]

    # Node sizes ∝ units_produced
    units = [G.nodes[n].get("units_produced", 1) for n in ordered_nodes]
    max_u = max(units) if units else 1
    node_sizes = [600 + 2400 * (u / max_u) for u in units]

    # Labels: SKU id + predicted hours
    labels = {
        n: f"{G.nodes[n]['sku_id']}\n{G.nodes[n].get('predicted_hours', 0):.1f}h"
        for n in ordered_nodes
    }

    nx.draw_networkx_nodes(G, pos, nodelist=ordered_nodes, node_size=node_sizes,
                           node_color=node_colors, alpha=0.9, ax=ax)
    nx.draw_networkx_labels(G, pos, labels=labels, font_size=7, ax=ax)

    # Edges with changeover hour labels
    edge_labels = {
        (u, v): f"{d.get('hours', 0.0):.1f}h\n{d.get('dominant', '')}"
        for u, v, d in G.edges(data=True)
    }
    nx.draw_networkx_edges(G, pos, arrows=True, arrowsize=15,
                           edge_color="#555555", width=2, ax=ax)
    nx.draw_networkx_edge_labels(G, pos, edge_labels=edge_labels,
                                 font_size=6, label_pos=0.3, ax=ax)

    # Legend / info box
    n_nodes = G.number_of_nodes()
    total_co = sum(d.get("hours", 0.0) for _, _, d in G.edges(data=True))
    total_pred = sum(G.nodes[n].get("predicted_hours", 0.0) for n in G.nodes)
    total_actual = sum(G.nodes[n].get("actual_hours", 0.0) for n in G.nodes)
    info = (
        f"Runs: {n_nodes}  |  "
        f"Total changeover: {total_co:.1f}h  |  "
        f"Predicted prod: {total_pred:.1f}h  |  "
        f"Actual prod: {total_actual:.1f}h"
    )
    ax.set_xlabel(info, fontsize=9)
    ax.axis("off")

    # Colour legend for node ratio
    for label, color in [("pred ≈ actual", "#00FF50"), ("pred > actual", "#FF0050")]:
        ax.scatter([], [], c=color, s=80, label=label, alpha=0.85)
    ax.legend(loc="upper right", fontsize=8, framealpha=0.7)

    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# Quick smoke test (run with: python -m services.optimizer.app.graph_builder)
# ---------------------------------------------------------------------------

def _smoke_test() -> None:
    print("Loading demand to pick a valid window_id …")
    demand = _demand()
    window_id = demand["window_id"].iloc[0]
    print(f"  using window_id: {window_id}")

    print("\nBuilding planning graph ...")
    graphs = build_planning_graph(window_id, demand_df=demand)
    for line, G in graphs.items():
        print(f"  L{line}: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")

    print("\nVisualising planning graph ...")
    fig = visualize_planning_graph(graphs)
    fig.savefig("planning_graph.png", dpi=120, bbox_inches="tight")
    print("  saved: planning_graph.png")

    print("\nBuilding historical WO graph for L14 ...")
    wo_graph = build_historical_wo_graph(window_id, line_id=14, demand_df=demand)
    print(f"  L14 runs: {wo_graph.number_of_nodes()}, transitions: {wo_graph.number_of_edges()}")

    print("\nVisualising WO graph ...")
    fig2 = visualize_wo_graph(wo_graph)
    fig2.savefig("wo_path_graph.png", dpi=120, bbox_inches="tight")
    print("  saved: wo_path_graph.png")


if __name__ == "__main__":
    _smoke_test()
