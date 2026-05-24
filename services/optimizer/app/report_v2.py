"""Generate an all-weeks benchmark report for optimizer v2.

Run from the repository root:

    python -m services.optimizer.app.report_v2

Outputs:

* ``services/optimizer/reports/optimizer_v2_report.md``
* ``services/optimizer/reports/optimizer_v2_weekly_comparison.csv``
* ``services/optimizer/reports/optimizer_v2_line_comparison.csv``
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Iterable

import networkx as nx
import pandas as pd

from services.node_cost_ml.app.inference import load_artefacts
from services.optimizer.app.graph_builder import (
    DATA_DIR,
    LINE_IDS,
    REPORTS_DIR,
    build_historical_wo_graph,
    build_planning_graph,
)
from services.optimizer.app.implementacion_v2 import OptimizerV2Result, optimize_graph


@dataclass(frozen=True)
class ReportConfig:
    max_iterations: int = 2
    max_exact_nodes: int = 15
    enable_swaps: bool = True
    max_swap_candidates: int = 20
    enable_balance_repair: bool = True
    balance_delta_hours: float = 8.0


@dataclass(frozen=True)
class ValidationResult:
    is_valid: bool
    missing_nodes: tuple[str, ...]
    duplicate_nodes: tuple[str, ...]
    extra_nodes: tuple[str, ...]
    capability_errors: tuple[str, ...]


def generate_report(
    *,
    data_dir: Path = DATA_DIR,
    reports_dir: Path = REPORTS_DIR,
    windows: Iterable[str] | None = None,
    config: ReportConfig = ReportConfig(),
) -> tuple[Path, Path, Path]:
    """Run optimizer v2 for every requested week and write report artefacts."""

    reports_dir.mkdir(parents=True, exist_ok=True)
    clean = _load_clean_data(data_dir)
    ml_model = load_artefacts()

    all_windows = tuple(clean["demand"]["window_id"].drop_duplicates())
    selected_windows = tuple(windows) if windows is not None else all_windows

    weekly_rows: list[dict[str, object]] = []
    line_rows: list[dict[str, object]] = []

    started_at = perf_counter()
    for index, window_id in enumerate(selected_windows, start=1):
        week_start = perf_counter()
        graph = build_planning_graph(
            window_id,
            demand_df=clean["demand"],
            capability_df=clean["capability"],
            changeover_df=clean["changeovers"],
            ml_model=ml_model,
        )
        result = optimize_graph(
            graph,
            balance_delta_hours=config.balance_delta_hours,
            max_iterations=config.max_iterations,
            max_exact_nodes=config.max_exact_nodes,
            enable_swaps=config.enable_swaps,
            max_swap_candidates=config.max_swap_candidates,
            enable_balance_repair=config.enable_balance_repair,
        )
        validation = validate_optimizer_result(graph, result)
        real_graphs = build_historical_wo_graph(
            window_id,
            demand_df=clean["demand"],
            wo_df=clean["wo"],
            wo_co_df=clean["wo_changeovers"],
            ml_model=ml_model,
        )
        window_wo = _window_work_orders(clean["wo"], clean["demand"], window_id)
        real_by_line = {
            line: _historical_line_totals(real_graphs.get(line, nx.DiGraph()), window_wo, line)
            for line in LINE_IDS
        }
        opt_by_line = {
            line: _optimizer_line_totals(result, line)
            for line in LINE_IDS
        }

        real_makespan = max(row["total_hours"] for row in real_by_line.values())
        real_total = sum(row["total_hours"] for row in real_by_line.values())
        real_productive = sum(row["productive_hours"] for row in real_by_line.values())
        real_changeover = sum(row["changeover_hours"] for row in real_by_line.values())
        real_production_wall_makespan = max(
            row["production_wall_hours"] for row in real_by_line.values()
        )
        real_full_wall_makespan = max(
            row["all_wo_wall_hours"] for row in real_by_line.values()
        )
        real_production_wall_plus_changeover_makespan = max(
            row["production_wall_plus_changeover_hours"] for row in real_by_line.values()
        )
        real_full_wall_plus_changeover_makespan = max(
            row["all_wo_wall_plus_changeover_hours"] for row in real_by_line.values()
        )
        real_production_wall_total = sum(
            row["production_wall_hours"] for row in real_by_line.values()
        )
        real_full_wall_total = sum(row["all_wo_wall_hours"] for row in real_by_line.values())
        real_inefficiency_total = sum(
            row["production_inefficiency_hours"] for row in real_by_line.values()
        )
        real_downtime_total = sum(row["downtime_hours"] for row in real_by_line.values())
        real_low_speed_total = sum(row["low_speed_hours"] for row in real_by_line.values())
        real_in_run_cleaning_total = sum(
            row["in_run_cleaning_hours"] for row in real_by_line.values()
        )
        real_cleaning_wo_total = sum(
            row["cleaning_wo_hours"] for row in real_by_line.values()
        )
        real_maintenance_rerun_total = sum(
            row["maintenance_rerun_hours"] for row in real_by_line.values()
        )
        opt_total = sum(row["total_hours"] for row in opt_by_line.values())
        opt_productive = sum(row["productive_hours"] for row in opt_by_line.values())
        opt_changeover = sum(row["changeover_hours"] for row in opt_by_line.values())

        elapsed = perf_counter() - week_start
        weekly_rows.append({
            "window_id": window_id,
            "node_count": graph.number_of_nodes(),
            "edge_count": graph.number_of_edges(),
            "valid_solution": validation.is_valid,
            "missing_node_count": len(validation.missing_nodes),
            "duplicate_node_count": len(validation.duplicate_nodes),
            "extra_node_count": len(validation.extra_nodes),
            "capability_error_count": len(validation.capability_errors),
            "dropped_count": len(result.dropped),
            "v2_feasible": result.feasible,
            "v2_makespan_hours": result.makespan_hours,
            "v2_total_hours": opt_total,
            "v2_productive_hours": opt_productive,
            "v2_changeover_hours": opt_changeover,
            "v2_gap_hours": result.gap_hours,
            "v2_accepted_moves": result.accepted_moves,
            "v2_balance_repairs": result.balance_repairs,
            "real_makespan_hours": real_makespan,
            "real_total_hours": real_total,
            "real_productive_hours": real_productive,
            "real_changeover_hours": real_changeover,
            "real_production_wall_makespan_hours": real_production_wall_makespan,
            "real_full_wall_makespan_hours": real_full_wall_makespan,
            "real_production_wall_plus_changeover_makespan_hours": (
                real_production_wall_plus_changeover_makespan
            ),
            "real_full_wall_plus_changeover_makespan_hours": (
                real_full_wall_plus_changeover_makespan
            ),
            "real_production_wall_total_hours": real_production_wall_total,
            "real_full_wall_total_hours": real_full_wall_total,
            "real_production_inefficiency_hours": real_inefficiency_total,
            "real_downtime_hours": real_downtime_total,
            "real_low_speed_hours": real_low_speed_total,
            "real_in_run_cleaning_hours": real_in_run_cleaning_total,
            "real_cleaning_wo_hours": real_cleaning_wo_total,
            "real_maintenance_rerun_hours": real_maintenance_rerun_total,
            "makespan_saved_hours": real_makespan - result.makespan_hours,
            "wall_makespan_saved_hours": real_full_wall_makespan - result.makespan_hours,
            "total_saved_hours": real_total - opt_total,
            "wall_total_saved_hours": real_full_wall_total - opt_total,
            "changeover_saved_hours": real_changeover - opt_changeover,
            "elapsed_seconds": elapsed,
            "missing_nodes": ",".join(validation.missing_nodes),
            "duplicate_nodes": ",".join(validation.duplicate_nodes),
            "extra_nodes": ",".join(validation.extra_nodes),
            "capability_errors": ",".join(validation.capability_errors),
        })

        for line in LINE_IDS:
            opt_line = opt_by_line[line]
            real_line = real_by_line[line]
            line_rows.append({
                "window_id": window_id,
                "line_id": line,
                "valid_solution": validation.is_valid,
                "v2_node_count": opt_line["node_count"],
                "real_run_count": real_line["node_count"],
                "v2_total_hours": opt_line["total_hours"],
                "v2_productive_hours": opt_line["productive_hours"],
                "v2_changeover_hours": opt_line["changeover_hours"],
                "real_total_hours": real_line["total_hours"],
                "real_productive_hours": real_line["productive_hours"],
                "real_changeover_hours": real_line["changeover_hours"],
                "real_production_wall_hours": real_line["production_wall_hours"],
                "real_all_wo_wall_hours": real_line["all_wo_wall_hours"],
                "real_production_wall_plus_changeover_hours": (
                    real_line["production_wall_plus_changeover_hours"]
                ),
                "real_all_wo_wall_plus_changeover_hours": (
                    real_line["all_wo_wall_plus_changeover_hours"]
                ),
                "real_production_inefficiency_hours": (
                    real_line["production_inefficiency_hours"]
                ),
                "real_downtime_hours": real_line["downtime_hours"],
                "real_low_speed_hours": real_line["low_speed_hours"],
                "real_in_run_cleaning_hours": real_line["in_run_cleaning_hours"],
                "real_cleaning_wo_hours": real_line["cleaning_wo_hours"],
                "real_maintenance_rerun_hours": real_line["maintenance_rerun_hours"],
                "line_saved_hours": real_line["total_hours"] - opt_line["total_hours"],
                "wall_line_saved_hours": (
                    real_line["all_wo_wall_hours"] - opt_line["total_hours"]
                ),
            })

        print(
            f"[{index}/{len(selected_windows)}] {window_id}: "
            f"valid={validation.is_valid} "
            f"v2={result.makespan_hours:.2f}h real={real_makespan:.2f}h "
            f"elapsed={elapsed:.1f}s"
        )

    weekly = pd.DataFrame(weekly_rows)
    lines = pd.DataFrame(line_rows)

    weekly_path = reports_dir / "optimizer_v2_weekly_comparison.csv"
    line_path = reports_dir / "optimizer_v2_line_comparison.csv"
    report_path = reports_dir / "optimizer_v2_report.md"

    weekly.to_csv(weekly_path, index=False)
    lines.to_csv(line_path, index=False)
    report_path.write_text(
        _render_markdown_report(
            weekly,
            lines,
            config=config,
            generated_at=datetime.now().isoformat(timespec="seconds"),
            elapsed_seconds=perf_counter() - started_at,
        ),
        encoding="utf-8",
    )
    return report_path, weekly_path, line_path


def validate_optimizer_result(
    graph: nx.MultiDiGraph,
    result: OptimizerV2Result,
) -> ValidationResult:
    """Validate that every planning node is visited exactly once."""

    graph_nodes = {str(node) for node in graph.nodes}
    visited = [
        str(node)
        for line in LINE_IDS
        for node in result.routes.get(line).order
    ]
    counts = Counter(visited)

    missing = tuple(sorted(graph_nodes - set(visited)))
    duplicates = tuple(sorted(node for node, count in counts.items() if count > 1))
    extra = tuple(sorted(set(visited) - graph_nodes))
    capability_errors = []
    for line in LINE_IDS:
        route = result.routes.get(line)
        if route is None:
            continue
        for node in route.order:
            if line not in graph.nodes[node].get("line_data", {}):
                capability_errors.append(f"L{line}:{node}")

    is_valid = (
        result.feasible
        and not result.dropped
        and not missing
        and not duplicates
        and not extra
        and not capability_errors
    )

    return ValidationResult(
        is_valid=is_valid,
        missing_nodes=missing,
        duplicate_nodes=duplicates,
        extra_nodes=extra,
        capability_errors=tuple(sorted(capability_errors)),
    )


def _load_clean_data(data_dir: Path) -> dict[str, pd.DataFrame]:
    return {
        "demand": pd.read_csv(data_dir / "demand.csv"),
        "capability": pd.read_csv(data_dir / "line_capability.csv"),
        "changeovers": pd.read_csv(data_dir / "changeover_costs.csv"),
        "wo": pd.read_csv(data_dir / "wo_master.csv", parse_dates=["end_day"]),
        "wo_changeovers": pd.read_csv(
            data_dir / "wo_changeovers.csv",
            parse_dates=["transition_day"],
        ),
    }


def _window_work_orders(
    wo: pd.DataFrame,
    demand: pd.DataFrame,
    window_id: str,
) -> pd.DataFrame:
    window_rows = demand[demand["window_id"] == window_id]
    if window_rows.empty:
        return wo.iloc[0:0]
    first = window_rows.iloc[0]
    start = pd.Timestamp(first["window_start"])
    end = pd.Timestamp(first["window_end"])
    return wo[(wo["end_day"] >= start) & (wo["end_day"] <= end)].copy()


def _optimizer_line_totals(result: OptimizerV2Result, line_id: int) -> dict[str, float]:
    route = result.routes[line_id]
    return {
        "node_count": float(len(route.order)),
        "productive_hours": route.production_hours,
        "changeover_hours": route.changeover_hours,
        "total_hours": route.total_hours,
    }


def _historical_line_totals(
    graph: nx.DiGraph,
    window_wo: pd.DataFrame,
    line_id: int,
) -> dict[str, float]:
    productive = sum(float(attrs.get("actual_hours", 0.0)) for _, attrs in graph.nodes(data=True))
    changeover = sum(float(attrs.get("hours", 0.0)) for _, _, attrs in graph.edges(data=True))
    line_wo = window_wo[window_wo["line_id"] == line_id]
    production_wo = line_wo[line_wo["wo_kind"] == "production"]
    cleaning_wo = line_wo[line_wo["wo_kind"] == "cleaning"]
    maintenance_rerun_wo = line_wo[
        line_wo["wo_kind"].isin(["maintenance_or_rerun", "maintenance"])
    ]

    production_wall = float(production_wo["total_hours"].fillna(0.0).sum())
    all_wo_wall = float(line_wo["total_hours"].fillna(0.0).sum())
    production_inefficiency = float(
        (production_wo["total_hours"].fillna(0.0) - production_wo["productive_hours"].fillna(0.0))
        .clip(lower=0.0)
        .sum()
    )

    return {
        "node_count": float(graph.number_of_nodes()),
        "productive_hours": productive,
        "changeover_hours": changeover,
        "total_hours": productive + changeover,
        "production_wall_hours": production_wall,
        "all_wo_wall_hours": all_wo_wall,
        "production_wall_plus_changeover_hours": production_wall + changeover,
        "all_wo_wall_plus_changeover_hours": all_wo_wall + changeover,
        "production_inefficiency_hours": production_inefficiency,
        "downtime_hours": float(production_wo["downtime_hours"].fillna(0.0).sum()),
        "low_speed_hours": float(production_wo["low_speed_hours"].fillna(0.0).sum()),
        "in_run_cleaning_hours": float(production_wo["cleaning_hours"].fillna(0.0).sum()),
        "cleaning_wo_hours": float(cleaning_wo["total_hours"].fillna(0.0).sum()),
        "maintenance_rerun_hours": float(
            maintenance_rerun_wo["total_hours"].fillna(0.0).sum()
        ),
    }


def _render_markdown_report(
    weekly: pd.DataFrame,
    lines: pd.DataFrame,
    *,
    config: ReportConfig,
    generated_at: str,
    elapsed_seconds: float,
) -> str:
    valid = weekly[weekly["valid_solution"]]
    invalid = weekly[~weekly["valid_solution"]]

    line_summary = (
        lines.groupby("line_id")
        .agg(
            mean_v2_total_hours=("v2_total_hours", "mean"),
            max_v2_total_hours=("v2_total_hours", "max"),
            mean_real_total_hours=("real_total_hours", "mean"),
            max_real_total_hours=("real_total_hours", "max"),
            mean_real_all_wo_wall_hours=("real_all_wo_wall_hours", "mean"),
            max_real_all_wo_wall_hours=("real_all_wo_wall_hours", "max"),
            mean_line_saved_hours=("line_saved_hours", "mean"),
            mean_wall_line_saved_hours=("wall_line_saved_hours", "mean"),
        )
        .reset_index()
    )

    top_savings = weekly.sort_values("makespan_saved_hours", ascending=False).head(10)
    regressions = weekly.sort_values("makespan_saved_hours", ascending=True).head(10)

    md = [
        "# Optimizer v2 weekly benchmark",
        "",
        f"Generated at: `{generated_at}`",
        "",
        "## Configuration",
        "",
        f"- `max_iterations`: {config.max_iterations}",
        f"- `max_exact_nodes`: {config.max_exact_nodes}",
        f"- `enable_swaps`: {config.enable_swaps}",
        f"- `max_swap_candidates`: {config.max_swap_candidates}",
        f"- `enable_balance_repair`: {config.enable_balance_repair}",
        f"- `balance_delta_hours`: {config.balance_delta_hours}",
        f"- Runtime: {elapsed_seconds:.1f} s",
        "",
        "## Coverage validation",
        "",
        f"- Weeks evaluated: {len(weekly)}",
        f"- Valid v2 solutions: {int(weekly['valid_solution'].sum())}/{len(weekly)}",
        f"- Invalid v2 solutions: {len(invalid)}",
        f"- Mean nodes per week: {weekly['node_count'].mean():.1f}",
        "",
        "A solution is valid only when every planning-graph node is visited exactly once, no node appears on an incompatible line, and no SKU is dropped.",
        "",
        "## Global time summary",
        "",
        f"- Mean v2 makespan: {weekly['v2_makespan_hours'].mean():.2f} h",
        f"- Mean real makespan: {weekly['real_makespan_hours'].mean():.2f} h",
        f"- Mean makespan saved: {weekly['makespan_saved_hours'].mean():.2f} h",
        f"- Mean v2 total line-hours: {weekly['v2_total_hours'].mean():.2f} h",
        f"- Mean real total line-hours: {weekly['real_total_hours'].mean():.2f} h",
        f"- Mean total line-hours saved: {weekly['total_saved_hours'].mean():.2f} h",
        f"- Mean changeover hours saved: {weekly['changeover_saved_hours'].mean():.2f} h",
        "",
        "## Historical wall-clock sensitivity",
        "",
        "`real_makespan_hours` above is the route-comparison metric: production running time plus estimated changeovers. The rows below add historical inefficiency layers from `wo_master.total_hours`.",
        "",
        f"- Mean real production wall-clock makespan: {weekly['real_production_wall_makespan_hours'].mean():.2f} h",
        f"- Mean real full wall-clock makespan: {weekly['real_full_wall_makespan_hours'].mean():.2f} h",
        f"- Mean real production wall-clock + changeover makespan: {weekly['real_production_wall_plus_changeover_makespan_hours'].mean():.2f} h",
        f"- Mean real full wall-clock + changeover makespan: {weekly['real_full_wall_plus_changeover_makespan_hours'].mean():.2f} h",
        f"- Mean wall-clock makespan saved vs v2: {weekly['wall_makespan_saved_hours'].mean():.2f} h",
        f"- Mean production inefficiency hours per week: {weekly['real_production_inefficiency_hours'].mean():.2f} h",
        f"- Mean cleaning WO hours per week: {weekly['real_cleaning_wo_hours'].mean():.2f} h",
        f"- Mean maintenance/rerun WO hours per week: {weekly['real_maintenance_rerun_hours'].mean():.2f} h",
        "",
        "## Production-line totals",
        "",
        _to_markdown(line_summary, floatfmt=".2f"),
        "",
        "## Top makespan savings",
        "",
        _to_markdown(
            top_savings[[
                "window_id",
                "valid_solution",
                "v2_makespan_hours",
                "real_makespan_hours",
                "makespan_saved_hours",
                "total_saved_hours",
            ]],
            floatfmt=".2f",
        ),
        "",
        "## Worst makespan deltas",
        "",
        _to_markdown(
            regressions[[
                "window_id",
                "valid_solution",
                "v2_makespan_hours",
                "real_makespan_hours",
                "makespan_saved_hours",
                "total_saved_hours",
            ]],
            floatfmt=".2f",
        ),
    ]

    if not invalid.empty:
        md.extend([
            "",
            "## Invalid weeks",
            "",
            _to_markdown(
                invalid[[
                    "window_id",
                    "missing_node_count",
                    "duplicate_node_count",
                    "extra_node_count",
                    "capability_error_count",
                    "dropped_count",
                    "v2_feasible",
                ]],
                floatfmt=".2f",
            ),
        ])

    return "\n".join(md) + "\n"


def _to_markdown(df: pd.DataFrame, *, floatfmt: str) -> str:
    try:
        return df.to_markdown(index=False, floatfmt=floatfmt)
    except ImportError:
        return df.to_string(index=False)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate optimizer v2 all-weeks report")
    parser.add_argument("--window", action="append", dest="windows", help="Window id to include")
    parser.add_argument("--max-iterations", type=int, default=ReportConfig.max_iterations)
    parser.add_argument("--max-exact-nodes", type=int, default=ReportConfig.max_exact_nodes)
    parser.add_argument("--no-swaps", action="store_true")
    parser.add_argument("--max-swap-candidates", type=int, default=ReportConfig.max_swap_candidates)
    parser.add_argument("--no-balance-repair", action="store_true")
    parser.add_argument("--balance-delta-hours", type=float, default=ReportConfig.balance_delta_hours)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    config = ReportConfig(
        max_iterations=args.max_iterations,
        max_exact_nodes=args.max_exact_nodes,
        enable_swaps=not args.no_swaps,
        max_swap_candidates=args.max_swap_candidates,
        enable_balance_repair=not args.no_balance_repair,
        balance_delta_hours=args.balance_delta_hours,
    )
    report_path, weekly_path, line_path = generate_report(
        windows=args.windows,
        config=config,
    )
    print(f"Markdown report: {report_path}")
    print(f"Weekly CSV: {weekly_path}")
    print(f"Line CSV: {line_path}")


if __name__ == "__main__":
    main()
