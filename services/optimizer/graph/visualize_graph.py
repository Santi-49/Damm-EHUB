"""Interactive Plotly dashboard for the partitioned LineWise graph.

Renders the output of :func:`line_partitioner.partition_lines` as a single
**self-contained HTML dashboard** (writes
``data_experiment/line_distribution_map.html``) — light theme, polished
typography, KPI strip, two synchronised panels:

* **Left panel — per-line subgraphs.** Each line (L14, L17, L19) is its own
  cluster, laid out with NetworkX's spring layout on the line's traversed
  path then offset horizontally. Arrow-headed paths show the chosen
  sequence; node size scales with production hours on the assigned line.
* **Right panel — per-line load.** Stacked bar of ``production_hours`` +
  ``changeover_hours``, with the makespan reference line — i.e. the very
  quantity the partitioner minimised.

Tooltips
--------

Hovering any **node** shows: ``sku_id`` · line + position k/n ·
historical work-order ID (from ``wo_master.csv``) · production cost on
the assigned line in hours · container type, brand, family, packaging.

Hovering any **edge** shows: ``L## changeover`` · from → to · hours
(straight from ``changeover_costs.csv``).

The renderer is **decoupled** — it takes the ``PartitionResult`` and a
small set of metadata callables (``edge_cost``, ``node_cost``, optional
``wo_lookup`` / ``sku_meta_lookup``) so it works against real data, the
synthetic prototype, or the future OR-Tools output without changes.
"""

from __future__ import annotations

import html
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Hashable, Mapping

import networkx as nx
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from line_partitioner import PartitionResult

LineId = int
SkuId = Hashable

# ---------------------------------------------------------------------------
# Default styling — calibrated light palette
# ---------------------------------------------------------------------------

# Per-line colours: deeper saturations that read clearly on white and pair
# well with their lighter "fill" siblings used for the bar-chart changeover
# stack. Picked from the Tailwind 600/700 scale for visual cohesion.
DEFAULT_LINE_COLORS: dict[LineId, str] = {
    14: "#2563eb",  # blue-600
    17: "#dc2626",  # red-600
    19: "#059669",  # emerald-600
}
DEFAULT_LINE_COLORS_SOFT: dict[LineId, str] = {
    14: "#dbeafe",  # blue-100
    17: "#fee2e2",  # red-100
    19: "#d1fae5",  # emerald-100
}
# Darker per-line tones used for node outlines: a 2 px ring in the same
# hue as the fill but at Tailwind 900 saturation. This is what makes the
# circles "pop" on a white background — far better contrast than a white
# outline (which disappears) or a generic slate ring (which kills cohesion).
DEFAULT_LINE_COLORS_DARK: dict[LineId, str] = {
    14: "#1e3a8a",  # blue-900
    17: "#7f1d1d",  # red-900
    19: "#064e3b",  # emerald-900
}

DEFAULT_OUTPUT_PATH = (
    Path(__file__).parent / "data_experiment" / "line_distribution_map.html"
)


@dataclass(frozen=True)
class VisualizationStyle:
    """Cosmetic knobs — all in one place so a designer can re-tune without
    touching the rendering code."""

    figure_height: int = 720
    node_size_min: float = 22.0
    node_size_max: float = 60.0
    node_outline_width: float = 2.4
    edge_width: float = 1.8
    cluster_x_gap: float = 3.4
    spring_iterations: int = 140
    spring_k: float = 1.10

    # Light theme tokens (Tailwind-derived slate palette)
    paper_bg: str = "#ffffff"
    plot_bg: str = "#ffffff"
    text_primary: str = "#0f172a"     # slate-900
    text_secondary: str = "#475569"   # slate-600
    text_muted: str = "#94a3b8"       # slate-400
    grid_color: str = "#eef2f7"       # very soft
    panel_border: str = "#e2e8f0"     # slate-200
    panel_bg: str = "#ffffff"
    accent_amber: str = "#d97706"     # makespan reference line

    line_colors: Mapping[LineId, str] = (None)  # type: ignore[assignment]
    line_colors_soft: Mapping[LineId, str] = (None)  # type: ignore[assignment]
    line_colors_dark: Mapping[LineId, str] = (None)  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.line_colors is None:
            object.__setattr__(self, "line_colors", DEFAULT_LINE_COLORS)
        if self.line_colors_soft is None:
            object.__setattr__(self, "line_colors_soft", DEFAULT_LINE_COLORS_SOFT)
        if self.line_colors_dark is None:
            object.__setattr__(self, "line_colors_dark", DEFAULT_LINE_COLORS_DARK)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def visualize_partition(
    result: PartitionResult,
    *,
    edge_cost: Callable[[SkuId, SkuId, LineId], float],
    node_cost: Callable[[SkuId, LineId], float],
    wo_lookup: Callable[[SkuId], str] | None = None,
    sku_meta_lookup: Callable[[SkuId], dict[str, str]] | None = None,
    label_fn: Callable[[SkuId], str] | None = None,
    style: VisualizationStyle | None = None,
    output_path: Path | str = DEFAULT_OUTPUT_PATH,
    title: str = "LineWise — Weekly Production Plan",
    subtitle: str | None = None,
    provenance: str = "data/clean/* · changeover_costs (tabla_cf_prat) · line_capability",
) -> Path:
    """Render the partition to a stand-alone HTML and return the written path.

    Parameters
    ----------
    result
        Output of :func:`line_partitioner.partition_lines`.
    edge_cost, node_cost
        The exact callables used by the partitioner. We re-evaluate them
        here so the displayed numbers match the optimiser's decision basis.
    wo_lookup
        ``SkuId -> work_order_id`` — typically backed by ``wo_master.csv``
        via :func:`real_data_loader.get_last_wo_for_sku`. Tooltip-only.
    sku_meta_lookup
        ``SkuId -> {"container_type": "1/3", "brand": "...", ...}`` — extra
        rows in the node tooltip. Tooltip-only.
    label_fn
        Short on-node label. Defaults to ``str(sku)`` truncated to 10 chars.
    """
    style = style or VisualizationStyle()
    wo_lookup = wo_lookup or (lambda _: "—")
    sku_meta_lookup = sku_meta_lookup or (lambda _: {})
    label_fn = label_fn or (lambda s: _truncate(str(s), 10))
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    graph = _build_graph(result, edge_cost=edge_cost, node_cost=node_cost)
    pos = _line_clustered_layout(result, style=style, seed=42)

    fig, registry = _build_figure(
        graph, pos, result, style,
        wo_lookup=wo_lookup, sku_meta_lookup=sku_meta_lookup, label_fn=label_fn,
    )

    # Embed the Plotly figure in a designed HTML shell — KPI strip on top,
    # provenance footer, system-font typography, soft card chrome.
    fig_div = fig.to_html(
        include_plotlyjs="inline", full_html=False,
        div_id="linewise-graph",
        config={"displaylogo": False, "responsive": True,
                "modeBarButtonsToRemove": ["lasso2d", "select2d"],
                "toImageButtonOptions": {"format": "png", "scale": 2,
                                         "filename": "linewise-plan"}},
    )

    page_html = _render_shell(
        title=title, subtitle=subtitle or _default_subtitle(result),
        kpis=_compute_kpis(result),
        provenance=provenance,
        fig_div=fig_div,
        style=style,
        registry=registry,
    )
    output_path.write_text(page_html, encoding="utf-8")
    return output_path


# ---------------------------------------------------------------------------
# KPI strip + HTML shell
# ---------------------------------------------------------------------------

def _compute_kpis(result: PartitionResult) -> list[tuple[str, str, str]]:
    """Return the list of (label, value, hint) tuples shown above the figure."""
    n_skus = sum(len(s) for s in result.sequences.values())
    spread = (
        result.makespan_hours - min(result.makespan_per_line_hours.values())
        if result.makespan_per_line_hours else 0.0
    )
    pct = (spread / result.makespan_hours * 100.0) if result.makespan_hours else 0.0
    return [
        ("Makespan", f"{result.makespan_hours:.1f} h",
         "max(production + changeover) across lines · the objective"),
        ("Spread",   f"{spread:.1f} h",
         f"max − min line load · {pct:.1f}% imbalance · lower is better"),
        ("Total work", f"{result.total_hours:.1f} h",
         "sum of all line loads · used as ε-tie-breaker"),
        ("SKUs placed", f"{n_skus}",
         f"dropped: {len(result.dropped)} · feasible: {result.feasible}"),
        ("Solve time", f"{result.elapsed_s:.2f} s",
         f"ALNS iterations: {result.iterations}"),
    ]


def _default_subtitle(result: PartitionResult) -> str:
    per_line = " · ".join(
        f"L{l}: {len(result.sequences.get(l, ()))} SKUs · {result.makespan_per_line_hours.get(l, 0):.1f} h"
        for l in sorted(result.sequences.keys())
    )
    return per_line


# ---------------------------------------------------------------------------
# Front-end JS — draggable nodes with live edge / arrow updates
# ---------------------------------------------------------------------------
# This script attaches to the Plotly figure once it's rendered. It uses the
# registry block (#linewise-registry, JSON) to find which trace + point a
# given SKU lives at, plus which edge segments and arrow annotations need
# to follow the dragged node. Coordinate conversion goes through Plotly's
# axis ``p2d`` (pixel-to-data) so it works regardless of zoom / resize.
# A double-click restores the original layout via Plotly.react.
_DRAG_JS = r"""
(function () {
  const REGISTRY = JSON.parse(document.getElementById("linewise-registry").textContent);
  const PLOT_ID = "linewise-graph";

  function whenReady(cb) {
    const gd = document.getElementById(PLOT_ID);
    if (gd && gd._fullLayout && gd._fullLayout.xaxis) { cb(gd); return; }
    setTimeout(() => whenReady(cb), 60);
  }

  whenReady(function (gd) {
    // Snapshot the original positions so double-click can restore them.
    const original = { nodes: {}, edges: {}, mids: {}, anns: {} };
    for (const sku in REGISTRY.nodes) {
      const n = REGISTRY.nodes[sku];
      original.nodes[sku] = { x: gd.data[n.trace].x[n.idx], y: gd.data[n.trace].y[n.idx] };
    }
    REGISTRY.edges.forEach((e, i) => {
      const et = gd.data[e.edge_trace], mt = gd.data[e.mid_trace];
      original.edges[i] = {
        ex: [et.x[e.seg * 3], et.x[e.seg * 3 + 1]],
        ey: [et.y[e.seg * 3], et.y[e.seg * 3 + 1]],
      };
      original.mids[i] = { x: mt.x[e.mid_idx], y: mt.y[e.mid_idx] };
      const a = gd.layout.annotations[e.ann];
      original.anns[i] = { x: a.x, y: a.y, ax: a.ax, ay: a.ay };
    });

    let hovered = null;   // {sku, trace, idx} — set by plotly_hover
    let drag = null;      // {sku, trace, idx} — set on mousedown

    gd.on("plotly_hover", (e) => {
      if (drag) return;
      const pt = e.points[0];
      const tr = gd.data[pt.curveNumber];
      if (!tr || !tr.customdata) { hovered = null; return; }
      hovered = {
        sku: tr.customdata[pt.pointNumber],
        trace: pt.curveNumber, idx: pt.pointNumber,
      };
      gd.style.cursor = "grab";
    });
    gd.on("plotly_unhover", () => {
      if (!drag) { hovered = null; gd.style.cursor = ""; }
    });

    function dataCoords(ev) {
      const bb = gd.getBoundingClientRect();
      const xa = gd._fullLayout.xaxis, ya = gd._fullLayout.yaxis;
      const xpx = ev.clientX - bb.left - xa._offset;
      const ypx = ev.clientY - bb.top  - ya._offset;
      return { x: xa.p2d(xpx), y: ya.p2d(ypx) };
    }

    // Capture-phase mousedown so we intercept BEFORE Plotly's zoom select.
    gd.addEventListener("mousedown", (ev) => {
      if (!hovered) return;
      ev.preventDefault();
      ev.stopPropagation();
      drag = Object.assign({}, hovered);
      gd.style.cursor = "grabbing";
    }, true);

    document.addEventListener("mousemove", (ev) => {
      if (!drag) return;
      const { x, y } = dataCoords(ev);
      moveNode(drag.sku, x, y);
    });

    document.addEventListener("mouseup", () => {
      if (!drag) return;
      drag = null;
      gd.style.cursor = "";
    });

    // Double-click anywhere in the network subplot → restore the spring layout.
    gd.addEventListener("dblclick", (ev) => {
      // Only reset when the click is over the network subplot (col=1).
      const bb = gd.getBoundingClientRect();
      const xa = gd._fullLayout.xaxis;
      const inNetwork =
        ev.clientX >= bb.left + xa._offset &&
        ev.clientX <= bb.left + xa._offset + xa._length;
      if (!inNetwork) return;
      ev.preventDefault();
      ev.stopPropagation();
      restoreOriginalLayout();
    }, true);

    function moveNode(sku, x, y) {
      const info = REGISTRY.nodes[sku];
      if (!info) return;
      const tr = gd.data[info.trace];
      const newX = tr.x.slice(); newX[info.idx] = x;
      const newY = tr.y.slice(); newY[info.idx] = y;
      Plotly.restyle(gd, { x: [newX], y: [newY] }, [info.trace]);

      // Group edge-trace updates so we restyle each trace once per frame.
      const edgeBuf = {}, midBuf = {}, annPatch = {};
      for (const e of REGISTRY.edges) {
        if (e.u !== sku && e.v !== sku) continue;
        const et = gd.data[e.edge_trace], mt = gd.data[e.mid_trace];
        if (!edgeBuf[e.edge_trace]) {
          edgeBuf[e.edge_trace] = { x: et.x.slice(), y: et.y.slice() };
        }
        if (!midBuf[e.mid_trace]) {
          midBuf[e.mid_trace] = { x: mt.x.slice(), y: mt.y.slice() };
        }
        const ex = edgeBuf[e.edge_trace].x, ey = edgeBuf[e.edge_trace].y;
        const base = e.seg * 3;
        if (e.u === sku) { ex[base]     = x; ey[base]     = y; }
        if (e.v === sku) { ex[base + 1] = x; ey[base + 1] = y; }
        midBuf[e.mid_trace].x[e.mid_idx] = (ex[base] + ex[base + 1]) / 2;
        midBuf[e.mid_trace].y[e.mid_idx] = (ey[base] + ey[base + 1]) / 2;
        if (e.u === sku) {
          annPatch["annotations[" + e.ann + "].ax"] = x;
          annPatch["annotations[" + e.ann + "].ay"] = y;
        }
        if (e.v === sku) {
          annPatch["annotations[" + e.ann + "].x"] = x;
          annPatch["annotations[" + e.ann + "].y"] = y;
        }
      }
      for (const t in edgeBuf) {
        Plotly.restyle(gd, { x: [edgeBuf[t].x], y: [edgeBuf[t].y] }, [+t]);
      }
      for (const t in midBuf) {
        Plotly.restyle(gd, { x: [midBuf[t].x], y: [midBuf[t].y] }, [+t]);
      }
      if (Object.keys(annPatch).length) Plotly.relayout(gd, annPatch);
    }

    function restoreOriginalLayout() {
      // Group restyle updates per trace for one Plotly call per trace.
      const perTrace = {};
      function ensure(t) {
        if (!perTrace[t]) perTrace[t] = { x: gd.data[t].x.slice(), y: gd.data[t].y.slice() };
      }
      for (const sku in REGISTRY.nodes) {
        const n = REGISTRY.nodes[sku];
        ensure(n.trace);
        perTrace[n.trace].x[n.idx] = original.nodes[sku].x;
        perTrace[n.trace].y[n.idx] = original.nodes[sku].y;
      }
      REGISTRY.edges.forEach((e, i) => {
        ensure(e.edge_trace);
        const base = e.seg * 3;
        perTrace[e.edge_trace].x[base]     = original.edges[i].ex[0];
        perTrace[e.edge_trace].x[base + 1] = original.edges[i].ex[1];
        perTrace[e.edge_trace].y[base]     = original.edges[i].ey[0];
        perTrace[e.edge_trace].y[base + 1] = original.edges[i].ey[1];
        ensure(e.mid_trace);
        perTrace[e.mid_trace].x[e.mid_idx] = original.mids[i].x;
        perTrace[e.mid_trace].y[e.mid_idx] = original.mids[i].y;
      });
      for (const t in perTrace) {
        Plotly.restyle(gd, { x: [perTrace[t].x], y: [perTrace[t].y] }, [+t]);
      }
      const annPatch = {};
      REGISTRY.edges.forEach((e, i) => {
        annPatch["annotations[" + e.ann + "].x"]  = original.anns[i].x;
        annPatch["annotations[" + e.ann + "].y"]  = original.anns[i].y;
        annPatch["annotations[" + e.ann + "].ax"] = original.anns[i].ax;
        annPatch["annotations[" + e.ann + "].ay"] = original.anns[i].ay;
      });
      Plotly.relayout(gd, annPatch);
    }
  });
})();
"""


def _render_shell(
    *, title: str, subtitle: str,
    kpis: list[tuple[str, str, str]], provenance: str,
    fig_div: str, style: VisualizationStyle, registry: dict,
) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    kpi_html = "\n".join(
        f'''
        <div class="kpi">
          <div class="kpi-label">{html.escape(label)}</div>
          <div class="kpi-value">{html.escape(value)}</div>
          <div class="kpi-hint">{html.escape(hint)}</div>
        </div>'''
        for label, value, hint in kpis
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>
  :root {{
    --text-primary: {style.text_primary};
    --text-secondary: {style.text_secondary};
    --text-muted: {style.text_muted};
    --panel-border: {style.panel_border};
    --panel-bg: {style.panel_bg};
    --page-bg: #f8fafc;
    --accent: {style.accent_amber};
    --l14: {style.line_colors[14]};
    --l17: {style.line_colors[17]};
    --l19: {style.line_colors[19]};
  }}
  * {{ box-sizing: border-box; }}
  html, body {{ margin: 0; padding: 0; background: var(--page-bg);
    color: var(--text-primary);
    font-family: "Inter", ui-sans-serif, system-ui, -apple-system,
                 "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    font-feature-settings: "cv11", "ss01", "tnum";
    -webkit-font-smoothing: antialiased; }}
  .page {{ max-width: 1480px; margin: 0 auto; padding: 28px 32px 48px; }}
  header {{ display: flex; align-items: baseline; justify-content: space-between;
    gap: 16px; flex-wrap: wrap; margin-bottom: 18px; }}
  .title-block h1 {{ font-size: 22px; font-weight: 700; letter-spacing: -0.01em;
    margin: 0 0 4px; }}
  .title-block .subtitle {{ font-size: 13px; color: var(--text-secondary);
    font-weight: 500; }}
  .badge {{ display: inline-flex; align-items: center; gap: 6px;
    padding: 4px 10px; border-radius: 999px; background: #eff6ff; color: #1d4ed8;
    font-size: 12px; font-weight: 600; border: 1px solid #dbeafe; }}
  .badge::before {{ content: ""; width: 6px; height: 6px; border-radius: 50%;
    background: #1d4ed8; }}
  .kpi-strip {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px;
    margin: 4px 0 22px; }}
  .kpi {{ background: var(--panel-bg); border: 1px solid var(--panel-border);
    border-radius: 12px; padding: 14px 16px;
    box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04); }}
  .kpi-label {{ font-size: 11px; font-weight: 600; text-transform: uppercase;
    letter-spacing: 0.05em; color: var(--text-muted); }}
  .kpi-value {{ font-size: 26px; font-weight: 700; color: var(--text-primary);
    margin: 2px 0; font-variant-numeric: tabular-nums; }}
  .kpi-hint {{ font-size: 12px; color: var(--text-secondary); line-height: 1.35; }}
  .card {{ background: var(--panel-bg); border: 1px solid var(--panel-border);
    border-radius: 16px; padding: 8px 8px 14px;
    box-shadow: 0 1px 3px rgba(15, 23, 42, 0.05); }}
  footer {{ margin-top: 18px; display: flex; justify-content: space-between;
    align-items: center; gap: 12px; flex-wrap: wrap;
    color: var(--text-muted); font-size: 12px; }}
  footer .line-chips {{ display: flex; gap: 10px; }}
  .chip {{ display: inline-flex; align-items: center; gap: 6px;
    padding: 3px 9px; border-radius: 999px; background: #f1f5f9;
    border: 1px solid var(--panel-border); font-weight: 500;
    color: var(--text-secondary); }}
  .chip .dot {{ width: 8px; height: 8px; border-radius: 50%; }}
  .chip.l14 .dot {{ background: var(--l14); }}
  .chip.l17 .dot {{ background: var(--l17); }}
  .chip.l19 .dot {{ background: var(--l19); }}
  @media (max-width: 1024px) {{
    .kpi-strip {{ grid-template-columns: repeat(2, 1fr); }}
  }}
</style>
</head>
<body>
<div class="page">
  <header>
    <div class="title-block">
      <h1>{html.escape(title)}</h1>
      <div class="subtitle">{html.escape(subtitle)}</div>
    </div>
    <span class="badge">Architecture D · ALNS + LKH-3</span>
  </header>

  <section class="kpi-strip">{kpi_html}
  </section>

  <section class="card">
    {fig_div}
  </section>

  <footer>
    <div class="line-chips">
      <span class="chip l14"><span class="dot"></span>L14 — 50 cl / 33 cl</span>
      <span class="chip l17"><span class="dot"></span>L17 — 33 cl only</span>
      <span class="chip l19"><span class="dot"></span>L19 — 50 cl / 33 cl / 44 cl</span>
      <span class="chip" style="background:#fef3c7;color:#92400e;border-color:#fde68a">
        <span class="dot" style="background:#d97706"></span>drag nodes to reposition · double-click to reset
      </span>
    </div>
    <div>{html.escape(provenance)} · generated {html.escape(now)}</div>
  </footer>
</div>

<script id="linewise-registry" type="application/json">
{json.dumps(registry)}
</script>
<script>
{_DRAG_JS}
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Plotly figure construction
# ---------------------------------------------------------------------------

def _build_figure(
    graph: nx.DiGraph,
    pos: dict[SkuId, tuple[float, float]],
    result: PartitionResult,
    style: VisualizationStyle,
    *,
    wo_lookup: Callable[[SkuId], str],
    sku_meta_lookup: Callable[[SkuId], dict[str, str]],
    label_fn: Callable[[SkuId], str],
) -> tuple[go.Figure, dict]:
    fig = make_subplots(
        rows=1, cols=2,
        column_widths=[0.74, 0.26],
        specs=[[{"type": "scatter"}, {"type": "xy"}]],
        horizontal_spacing=0.06,
        subplot_titles=(
            "<span style='font-weight:600'>Traversed paths per line</span>"
            "<br><span style='color:#64748b;font-size:11px'>"
            "node size ∝ production hours · arrows = chosen sequence</span>",
            "<span style='font-weight:600'>Per-line load</span>"
            "<br><span style='color:#64748b;font-size:11px'>"
            "objective: minimise the tallest bar</span>",
        ),
    )

    registry = _add_network_traces(
        fig, graph, pos, result, style,
        wo_lookup=wo_lookup, sku_meta_lookup=sku_meta_lookup, label_fn=label_fn,
    )
    _add_load_bar_traces(fig, result, style)

    fig.update_layout(
        height=style.figure_height,
        showlegend=True,
        legend={
            "orientation": "h", "y": -0.04, "x": 0.5, "xanchor": "center",
            "bgcolor": "rgba(0,0,0,0)",
            "font": {"color": style.text_secondary, "size": 12},
            "itemsizing": "constant",
        },
        paper_bgcolor=style.paper_bg,
        plot_bgcolor=style.plot_bg,
        font={"color": style.text_primary,
              "family": 'Inter, ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif'},
        hoverlabel={"bgcolor": "white", "bordercolor": style.panel_border,
                    "font": {"size": 12, "color": style.text_primary,
                             "family": "Inter, ui-sans-serif, system-ui, sans-serif"}},
        margin={"l": 16, "r": 16, "t": 64, "b": 80},
    )
    # Subplot title sizing
    for ann in fig.layout.annotations or ():
        if hasattr(ann, "font"):
            ann.font.size = 13
            ann.font.color = style.text_primary

    # Axes off on the network panel; explicit range with padding so user
    # drags never trigger an auto-rescale of the whole subplot.
    if pos:
        all_x = [p[0] for p in pos.values()]
        all_y = [p[1] for p in pos.values()]
        x_pad = max(0.6, 0.18 * (max(all_x) - min(all_x)))
        y_pad = max(0.6, 0.22 * (max(all_y) - min(all_y)))
        fig.update_xaxes(
            visible=False, autorange=False,
            range=[min(all_x) - x_pad, max(all_x) + x_pad],
            row=1, col=1,
        )
        fig.update_yaxes(
            visible=False, autorange=False,
            range=[min(all_y) - y_pad, max(all_y) + y_pad],
            row=1, col=1,
        )
    else:
        fig.update_xaxes(visible=False, row=1, col=1)
        fig.update_yaxes(visible=False, row=1, col=1)
    fig.update_xaxes(
        showgrid=False, zeroline=False, ticks="outside",
        ticklen=4, tickcolor=style.panel_border,
        color=style.text_secondary,
        row=1, col=2,
    )
    fig.update_yaxes(
        showgrid=True, gridcolor=style.grid_color, gridwidth=1, zeroline=False,
        title="hours", color=style.text_secondary,
        title_font={"size": 12, "color": style.text_secondary},
        row=1, col=2,
    )
    return fig, registry


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------

def _build_graph(
    result: PartitionResult,
    *,
    edge_cost: Callable[[SkuId, SkuId, LineId], float],
    node_cost: Callable[[SkuId, LineId], float],
) -> nx.DiGraph:
    """Build a directed graph containing only the *traversed* edges."""
    graph: nx.DiGraph = nx.DiGraph()
    for line_id, seq in result.sequences.items():
        for order_idx, sku in enumerate(seq):
            graph.add_node(
                sku,
                line_id=line_id,
                position=order_idx + 1,
                production_hours=float(node_cost(sku, line_id)),
            )
        for a, b in zip(seq, seq[1:]):
            graph.add_edge(
                a, b, line_id=line_id, weight=float(edge_cost(a, b, line_id))
            )
    return graph


def _line_clustered_layout(
    result: PartitionResult, *, style: VisualizationStyle, seed: int,
) -> dict[SkuId, tuple[float, float]]:
    """Place each line's nodes in its own horizontal cluster."""
    pos: dict[SkuId, tuple[float, float]] = {}
    line_ids = sorted(result.sequences.keys())
    for idx, line_id in enumerate(line_ids):
        seq = result.sequences[line_id]
        if not seq:
            continue
        sub: nx.DiGraph = nx.DiGraph()
        sub.add_nodes_from(seq)
        sub.add_edges_from(zip(seq, seq[1:]))
        local = nx.spring_layout(
            sub, seed=seed, k=style.spring_k, iterations=style.spring_iterations,
        )
        x_offset = (idx - (len(line_ids) - 1) / 2.0) * style.cluster_x_gap
        for sku, (x, y) in local.items():
            pos[sku] = (x + x_offset, y)
    return pos


# ---------------------------------------------------------------------------
# Network panel
# ---------------------------------------------------------------------------

def _add_network_traces(
    fig: go.Figure,
    graph: nx.DiGraph,
    pos: dict[SkuId, tuple[float, float]],
    result: PartitionResult,
    style: VisualizationStyle,
    *,
    wo_lookup: Callable[[SkuId], str],
    sku_meta_lookup: Callable[[SkuId], dict[str, str]],
    label_fn: Callable[[SkuId], str],
) -> dict:
    """Add network traces + arrow annotations and return a *registry* the
    front-end JS uses to drag nodes around.

    Registry shape (all indices into ``fig.data`` / ``fig.layout.annotations``):

    .. code-block:: json

        {
          "nodes": {"<sku>": {"trace": 7, "idx": 3}},
          "edges": [
            {"u": "...", "v": "...", "line": 14,
             "edge_trace": 0, "seg": 4,
             "mid_trace": 1, "mid_idx": 4,
             "ann": 17}
          ]
        }
    """
    registry: dict = {"nodes": {}, "edges": []}
    edge_meta_per_line: dict[int, dict] = {}

    # ---- Edges (one line trace + one invisible midpoint trace per line)
    for line_id, color in style.line_colors.items():
        edges = [(u, v, d) for u, v, d in graph.edges(data=True)
                 if d.get("line_id") == line_id]
        if not edges:
            continue
        xs: list[float | None] = []
        ys: list[float | None] = []
        for u, v, _ in edges:
            xs += [pos[u][0], pos[v][0], None]
            ys += [pos[u][1], pos[v][1], None]
        fig.add_trace(
            go.Scatter(
                x=xs, y=ys, mode="lines",
                line={"color": color, "width": style.edge_width},
                opacity=0.6, hoverinfo="skip", showlegend=False,
                name=f"L{line_id} edges",
            ),
            row=1, col=1,
        )
        edge_trace_idx = len(fig.data) - 1

        mx, my, htext = [], [], []
        for u, v, d in edges:
            mx.append((pos[u][0] + pos[v][0]) / 2.0)
            my.append((pos[u][1] + pos[v][1]) / 2.0)
            htext.append(
                f"<b style='color:{color}'>L{line_id} changeover</b><br>"
                f"<b>from</b> &nbsp; {html.escape(str(u))}<br>"
                f"<b>to</b> &nbsp;&nbsp;&nbsp; {html.escape(str(v))}<br>"
                f"<b>hours</b> &nbsp; {d['weight']:.2f} h"
            )
        fig.add_trace(
            go.Scatter(
                x=mx, y=my, mode="markers",
                marker={"size": 10, "color": color, "opacity": 0.0,
                        "line": {"width": 0}},
                hovertext=htext, hoverinfo="text", showlegend=False,
                name=f"L{line_id} edge labels",
            ),
            row=1, col=1,
        )
        mid_trace_idx = len(fig.data) - 1

        # Arrowheads — one annotation per edge. Track each new annotation's
        # index right after the add so the registry stays consistent.
        arrow_ix: list[int] = []
        for u, v, _ in edges:
            _add_arrow_annotation(fig, pos[u], pos[v], color)
            arrow_ix.append(len(fig.layout.annotations) - 1)

        edge_meta_per_line[line_id] = {
            "edge_trace": edge_trace_idx,
            "mid_trace": mid_trace_idx,
            "edges": [(str(u), str(v), arrow_ix[k])
                      for k, (u, v, _) in enumerate(edges)],
        }

    # ---- Nodes (one trace per line, dark-ring outline for contrast)
    prod_values = [d["production_hours"] for _, d in graph.nodes(data=True)]
    if prod_values:
        lo, hi = min(prod_values), max(prod_values)
        span = max(hi - lo, 1e-6)
    else:
        lo, span = 0.0, 1.0

    def _size(p: float) -> float:
        t = (p - lo) / span
        return style.node_size_min + t * (style.node_size_max - style.node_size_min)

    for line_id, color in style.line_colors.items():
        nodes = [n for n, d in graph.nodes(data=True) if d.get("line_id") == line_id]
        if not nodes:
            continue
        n_skus = len(nodes)
        load = result.makespan_per_line_hours.get(line_id, 0.0)
        outline = style.line_colors_dark.get(line_id, "#0f172a")
        xs = [pos[n][0] for n in nodes]
        ys = [pos[n][1] for n in nodes]
        sizes = [_size(graph.nodes[n]["production_hours"]) for n in nodes]
        labels = [label_fn(n) for n in nodes]
        sku_ids = [str(n) for n in nodes]
        hovers: list[str] = []
        for n in nodes:
            d = graph.nodes[n]
            meta = sku_meta_lookup(n) or {}
            extra = "".join(
                f"<br><span style='color:#64748b'>{html.escape(str(k))}</span>"
                f" &nbsp; {html.escape(str(v))}"
                for k, v in meta.items() if v not in (None, "")
            )
            hovers.append(
                f"<b style='color:{outline};font-size:13px'>{html.escape(str(n))}</b>"
                f"<br><span style='color:#64748b'>line</span> &nbsp; "
                f"<b>L{line_id}</b> · position {d['position']}/{n_skus}"
                f"<br><span style='color:#64748b'>work order</span> &nbsp; "
                f"{html.escape(str(wo_lookup(n)))}"
                f"<br><span style='color:#64748b'>production cost</span> &nbsp; "
                f"<b>{d['production_hours']:.2f} h</b>"
                f"{extra}"
                f"<br><span style='color:#94a3b8;font-size:10px'>"
                f"&nbsp;drag to reposition</span>"
            )
        fig.add_trace(
            go.Scatter(
                x=xs, y=ys, mode="markers+text",
                marker={
                    "size": sizes, "color": color, "opacity": 0.96,
                    "line": {"color": outline, "width": style.node_outline_width},
                },
                text=labels, textposition="middle center",
                textfont={"size": 9, "color": "white", "family": "Inter"},
                hovertext=hovers, hoverinfo="text",
                customdata=sku_ids,  # JS uses this to identify dragged nodes
                name=f"L{line_id} · {n_skus} SKUs · {load:.1f} h",
                legendgroup=f"L{line_id}",
            ),
            row=1, col=1,
        )
        node_trace_idx = len(fig.data) - 1
        for i, sku in enumerate(sku_ids):
            registry["nodes"][sku] = {"trace": node_trace_idx, "idx": i}

    # ---- Flatten the per-line edge metadata into the registry ----------
    for line_id, meta in edge_meta_per_line.items():
        for k, (u, v, ann_idx) in enumerate(meta["edges"]):
            registry["edges"].append({
                "u": u, "v": v, "line": int(line_id),
                "edge_trace": meta["edge_trace"], "seg": k,
                "mid_trace": meta["mid_trace"], "mid_idx": k,
                "ann": ann_idx,
            })
    return registry


def _add_arrow_annotation(
    fig: go.Figure,
    src: tuple[float, float],
    dst: tuple[float, float],
    color: str,
) -> None:
    fig.add_annotation(
        x=dst[0], y=dst[1],
        ax=src[0], ay=src[1],
        xref="x1", yref="y1", axref="x1", ayref="y1",
        showarrow=True, arrowhead=2, arrowsize=1.1, arrowwidth=1.2,
        arrowcolor=color, opacity=0.75, standoff=12,
    )


# ---------------------------------------------------------------------------
# Bar chart panel
# ---------------------------------------------------------------------------

def _add_load_bar_traces(
    fig: go.Figure,
    result: PartitionResult,
    style: VisualizationStyle,
) -> None:
    line_ids = sorted(result.sequences.keys())
    labels = [f"L{i}" for i in line_ids]
    prod = [result.production_hours_per_line.get(i, 0.0) for i in line_ids]
    chg = [result.changeover_hours_per_line.get(i, 0.0) for i in line_ids]
    colors = [style.line_colors.get(i, "#94a3b8") for i in line_ids]
    softs = [style.line_colors_soft.get(i, "#e2e8f0") for i in line_ids]

    # Production — solid colour, refined corner radius (Plotly fakes via marker_line).
    fig.add_trace(
        go.Bar(
            x=labels, y=prod, marker={"color": colors, "line": {"width": 0}},
            opacity=0.95, name="production",
            hovertemplate=(
                "<b>%{x} production</b><br>"
                "<span style='color:#64748b'>hours</span> "
                "<b>%{y:.2f}</b><extra></extra>"
            ),
        ),
        row=1, col=2,
    )
    # Changeover — same hue, softer fill, hatched in line colour for clarity.
    fig.add_trace(
        go.Bar(
            x=labels, y=chg,
            marker={
                "color": softs, "line": {"color": colors, "width": 1.2},
                "pattern": {"shape": "/", "fgcolor": colors,
                            "bgcolor": softs, "size": 6, "solidity": 0.35},
            },
            name="changeover",
            hovertemplate=(
                "<b>%{x} changeover</b><br>"
                "<span style='color:#64748b'>hours</span> "
                "<b>%{y:.2f}</b><extra></extra>"
            ),
        ),
        row=1, col=2,
    )
    fig.update_layout(barmode="stack", bargap=0.36)

    makespan = result.makespan_hours
    # Add headroom so the totals + the makespan corner-card never collide.
    max_total = max((p + c for p, c in zip(prod, chg)), default=1.0)
    headroom = max(makespan, max_total) * 1.28
    fig.update_yaxes(range=[0, headroom], row=1, col=2)

    # Dashed makespan reference — no inline label (we draw a clean corner
    # card instead, below).
    fig.add_hline(
        y=makespan,
        line={"color": style.accent_amber, "dash": "dash", "width": 1.4},
        row=1, col=2,
    )
    # Per-bar totals — sit just above each bar; safely below the corner card.
    for x, p, c in zip(labels, prod, chg):
        fig.add_annotation(
            x=x, y=p + c, text=f"<b>{p + c:.1f} h</b>",
            showarrow=False, yshift=12,
            font={"color": style.text_primary, "size": 12},
            xref="x2", yref="y2",
        )
    # Makespan callout — pinned to the top-right corner of the bar subplot
    # via domain refs so it always sits above the tallest bar regardless of
    # the data range.
    fig.add_annotation(
        xref="x2 domain", yref="y2 domain",
        x=0.98, y=0.98, xanchor="right", yanchor="top",
        text=(
            f"<span style='color:{style.accent_amber};font-size:14px'>━━</span>"
            f"&nbsp;&nbsp;<b>makespan</b> · {makespan:.1f} h"
        ),
        showarrow=False,
        bgcolor="rgba(255,255,255,0.96)",
        bordercolor=style.panel_border, borderwidth=1, borderpad=6,
        font={"color": style.accent_amber, "size": 11,
              "family": "Inter, ui-sans-serif, sans-serif"},
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _truncate(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 1] + "…"


# ---------------------------------------------------------------------------
# Demo — end-to-end against the real ETL output (synthetic fallback)
# ---------------------------------------------------------------------------

def _demo() -> None:
    from line_partitioner import partition_lines

    try:
        from real_data_loader import (
            LINE_IDS, can_produce,
            get_last_wo_for_sku,
            get_node_cost as _node_cost_real,
            get_transition_cost as _edge_cost_real,
            load_window_dataset,
        )
        ds = load_window_dataset()
        sku_ids = list(ds.sku_ids)
        units_by_sku = dict(ds.units_by_sku)

        def edge_cost(a, b, line):
            return _edge_cost_real(a, b, line)

        def node_cost(sku, line):
            return _node_cost_real(sku, ds.units_by_sku[sku], line)

        def sku_meta_lookup(sku):
            s = ds.sku_by_id.get(sku)
            if s is None:
                return {}
            return {
                "container": s.container_type,
                "brand": s.brand,
                "family": s.family,
                "pack": s.primary_packaging,
            }

        wo_lookup = get_last_wo_for_sku
        title_window = ds.window_id
        source = "real ETL"
    except (FileNotFoundError, ImportError, KeyError):
        from generate_test_data import (
            DEFAULT_OUT_PATH, LINE_CONTAINER_TYPES, LINE_IDS,
            build_sku_catalog, get_node_cost as _syn_node_cost,
            get_transition_cost as _syn_edge_cost, read_sheet,
        )
        catalog = build_sku_catalog()
        sku_by_id = {s.sku_id: s for s in catalog}
        demand_rows = read_sheet(DEFAULT_OUT_PATH, "demand")
        units_by_sku = {r["sku_id"]: int(r["units_demanded"]) for r in demand_rows}

        def can_produce(sku, line):  # type: ignore[no-redef]
            return sku_by_id[sku].container_type in LINE_CONTAINER_TYPES[line]

        def edge_cost(a, b, line):
            return _syn_edge_cost(sku_by_id[a], sku_by_id[b], line)

        def node_cost(sku, line):
            return _syn_node_cost(sku_by_id[sku], units_by_sku[sku], line)

        def wo_lookup(sku):
            return "—"

        def sku_meta_lookup(sku):
            s = sku_by_id.get(sku)
            return {} if s is None else {
                "container": s.container_type, "brand": s.brand,
                "family": s.family, "pack": s.primary_packaging,
            }

        sku_ids = [s.sku_id for s in catalog]
        title_window = "synthetic"
        source = "synthetic"

    print(f"Partitioning {len(sku_ids)} SKUs across L{list(LINE_IDS)} ({source})...")
    result = partition_lines(
        sku_ids, list(LINE_IDS), can_produce, edge_cost, node_cost,
        units_by_sku=units_by_sku, time_budget_s=4.0, sequence_budget_s=0.05,
    )

    html_out = visualize_partition(
        result,
        edge_cost=edge_cost, node_cost=node_cost,
        wo_lookup=wo_lookup, sku_meta_lookup=sku_meta_lookup,
        title=f"LineWise — Weekly Production Plan · {title_window}",
    )
    print(f"[OK] wrote {html_out}")


if __name__ == "__main__":
    _demo()
