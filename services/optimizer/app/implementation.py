"""Production optimiser entrypoint for the LineWise pipeline.

The API should import this module instead of binding itself to one experiment
module.  The current production engine is the original graph/v1 partitioner in
``services/optimizer/graph/line_partitioner.py`` because the all-week benchmark
showed it is at least as strong as ``implementacion_v2`` on the adjusted
simulation comparison.

The public ``optimize_graph`` function intentionally returns the small route
shape the API already consumed from v2: ``assignments``, ``routes``,
``makespan_hours``, ``dropped`` and ``solver_log``.
"""

from __future__ import annotations

import sys
from dataclasses import asdict, dataclass
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Any, Iterable

import networkx as nx
import pandas as pd

from packages.contracts.module.changeover_ml import ChangeoverModelContract
from packages.contracts.module.optimizer import GraphOptimizerContract
from packages.contracts.module.schemas import (
    OptimizerInput,
    OptimizerOutput,
    Sequence,
    Slot,
)
from services.optimizer.app.graph_builder import LINE_IDS, build_planning_graph

_REPO_ROOT = Path(__file__).resolve().parents[3]
_GRAPH_DIR = _REPO_ROOT / "services" / "optimizer" / "graph"
if str(_GRAPH_DIR) not in sys.path:
    sys.path.insert(0, str(_GRAPH_DIR))

from line_partitioner import PartitionResult, partition_from_graph  # noqa: E402


DEFAULT_TIME_BUDGET_S = 4.0
DEFAULT_MOVE_STRATEGY = "first_improvement"
DEFAULT_BALANCE_DELTA_H = 0.5
DEFAULT_EPS = 1e-3
DEFAULT_MAX_ITERATIONS = 500
DEFAULT_MAX_NO_IMPROVE = 20
DEFAULT_SEQUENCE_BUDGET_S = 0.05
DEFAULT_SEED = 42
PLANT_START_HOUR = 6


@dataclass(frozen=True)
class LineRoute:
    """One line's ordered route and cost decomposition."""

    line_id: int
    nodes: tuple[str, ...]
    order: tuple[str, ...]
    production_hours: float
    changeover_hours: float
    total_hours: float
    feasible: bool
    reason: str | None = None


@dataclass(frozen=True)
class OptimizerResult:
    """Stable optimizer result consumed by the API orchestrator."""

    assignments: dict[int, tuple[str, ...]]
    routes: dict[int, LineRoute]
    makespan_hours: float
    total_hours: float
    gap_hours: float
    dropped: tuple[str, ...]
    dropped_units: dict[str, int]
    feasible: bool
    iterations: int
    accepted_moves: int
    balance_repairs: int
    elapsed_s: float
    solver_log: str


def optimize_graph(
    graph: nx.MultiDiGraph,
    *,
    line_ids: Iterable[int] = LINE_IDS,
    time_budget_s: float = DEFAULT_TIME_BUDGET_S,
    sequence_budget_s: float = DEFAULT_SEQUENCE_BUDGET_S,
    move_strategy: str = DEFAULT_MOVE_STRATEGY,
    delta_balance_h: float = DEFAULT_BALANCE_DELTA_H,
    eps: float = DEFAULT_EPS,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    max_no_improve: int = DEFAULT_MAX_NO_IMPROVE,
    seed: int = DEFAULT_SEED,
    # Compatibility with old v2 call sites. They are deliberately ignored by
    # v1, but accepting them keeps external callers from breaking during the
    # engine swap.
    max_exact_nodes: int | None = None,
    balance_delta_hours: float | None = None,
    enable_swaps: bool | None = None,
    max_swap_candidates: int | None = None,
    enable_balance_repair: bool | None = None,
) -> OptimizerResult:
    """Optimize a ``graph_builder`` planning graph with the v1 partitioner."""

    del max_exact_nodes, enable_swaps, max_swap_candidates, enable_balance_repair
    if balance_delta_hours is not None:
        delta_balance_h = balance_delta_hours

    if not isinstance(graph, nx.MultiDiGraph):
        raise TypeError("optimize_graph expects the nx.MultiDiGraph from build_planning_graph")

    line_ids_t = tuple(int(line) for line in line_ids)
    partition = partition_from_graph(
        graph,
        line_ids=line_ids_t,
        seed=seed,
        time_budget_s=time_budget_s,
        sequence_budget_s=sequence_budget_s,
        move_strategy=move_strategy,
        delta_balance_h=delta_balance_h,
        eps=eps,
        max_iterations=max_iterations,
        max_no_improve=max_no_improve,
    )
    return _adapt_partition_result(partition, line_ids_t)


def optimize_window(window_id: str, **kwargs: Any) -> OptimizerResult:
    """Build the planning graph for ``window_id`` and run the production engine."""

    graph = build_planning_graph(window_id)
    return optimize_graph(graph, **kwargs)


class GraphOptimizer(GraphOptimizerContract):
    """Contract-facing wrapper around the production v1 graph optimizer."""

    async def optimize(
        self,
        inputs: OptimizerInput,
        ml: ChangeoverModelContract,
    ) -> OptimizerOutput:
        del ml
        if not inputs.demand:
            raise ValueError("OptimizerInput.demand must not be empty")

        demand_df = _demand_to_frame(inputs)
        capability_df = _capability_to_frame(inputs)
        changeover_df = _changeovers_to_frame(inputs)
        window_id = inputs.demand[0].window_id

        graph = build_planning_graph(
            window_id,
            demand_df=demand_df,
            capability_df=capability_df,
            changeover_df=changeover_df,
        )
        result = optimize_graph(graph)
        sequence = _result_to_contract_sequence(
            result,
            graph,
            window_start=inputs.demand[0].window_start,
            window_end=inputs.demand[0].window_end,
        )

        return OptimizerOutput(
            sequence=sequence,
            makespan_per_line_hours={
                line: route.total_hours for line, route in result.routes.items()
            },
            makespan_hours=result.makespan_hours,
            dropped=tuple((sku, result.dropped_units.get(sku, 0)) for sku in result.dropped),
            feasible=result.feasible,
            solver_log=result.solver_log,
        )

    async def replan(
        self,
        previous: Sequence,
        inputs: OptimizerInput,
        ml: ChangeoverModelContract,
    ) -> OptimizerOutput:
        del previous, inputs, ml
        raise NotImplementedError("GraphOptimizer.replan freeze-window support is not wired yet")


def _adapt_partition_result(
    result: PartitionResult,
    line_ids: tuple[int, ...],
) -> OptimizerResult:
    assignments: dict[int, tuple[str, ...]] = {}
    routes: dict[int, LineRoute] = {}
    totals: list[float] = []

    for line in line_ids:
        sequence = tuple(str(sku) for sku in result.sequences.get(line, ()))
        production_h = float(result.production_hours_per_line.get(line, 0.0))
        changeover_h = float(result.changeover_hours_per_line.get(line, 0.0))
        total_h = float(result.makespan_per_line_hours.get(line, production_h + changeover_h))

        assignments[line] = sequence
        routes[line] = LineRoute(
            line_id=line,
            nodes=sequence,
            order=sequence,
            production_hours=production_h,
            changeover_hours=changeover_h,
            total_hours=total_h,
            feasible=True,
        )
        totals.append(total_h)

    dropped_units = {str(sku): int(units) for sku, units in result.dropped}
    dropped = tuple(dropped_units)
    solver_log = result.solver_log or ""

    accepted_counts = _parse_log_step_counts(solver_log)

    return OptimizerResult(
        assignments=assignments,
        routes=routes,
        makespan_hours=float(result.makespan_hours),
        total_hours=float(result.total_hours),
        gap_hours=(max(totals) - min(totals)) if totals else 0.0,
        dropped=dropped,
        dropped_units=dropped_units,
        feasible=result.feasible,
        iterations=int(result.iterations),
        accepted_moves=sum(accepted_counts.values()),
        balance_repairs=accepted_counts.get("balance", 0),
        elapsed_s=float(result.elapsed_s),
        solver_log=solver_log,
    )


def _result_to_contract_sequence(
    result: OptimizerResult,
    graph: nx.MultiDiGraph,
    *,
    window_start: Any,
    window_end: Any,
) -> Sequence:
    slots: list[Slot] = []
    base_dt = datetime.combine(pd.Timestamp(window_start).date(), time(PLANT_START_HOUR))

    for line in LINE_IDS:
        route = result.routes.get(line)
        if route is None or not route.order:
            continue

        cursor = base_dt
        for index, sku in enumerate(route.order):
            node = graph.nodes[sku]
            prod_h = float(node.get("line_data", {}).get(line, {}).get("predicted_hours", 0.0))
            prod_end = cursor + timedelta(hours=prod_h)
            slots.append(
                Slot(
                    slot_id=f"opt-L{line}-n{index}",
                    line_id=line,  # type: ignore[arg-type]
                    sku_id=sku,
                    start_ts=cursor,
                    end_ts=prod_end,
                    units_planned=int(node.get("units_demanded", 0)),
                    slot_type="produccion",
                )
            )
            cursor = prod_end

            if index < len(route.order) - 1:
                next_sku = route.order[index + 1]
                edge_data = graph.get_edge_data(sku, next_sku, key=line)
                co_h = float(edge_data.get("hours", 0.0)) if edge_data else 0.0
                if co_h > 0:
                    slots.append(
                        Slot(
                            slot_id=f"opt-L{line}-co{index}",
                            line_id=line,  # type: ignore[arg-type]
                            sku_id=next_sku,
                            start_ts=cursor,
                            end_ts=cursor + timedelta(hours=co_h),
                            units_planned=0,
                            slot_type="cambio",
                            sku_prev_id=sku,
                            changeover_hours=co_h,
                        )
                    )
                    cursor += timedelta(hours=co_h)

    return Sequence(
        slots=tuple(slots),
        window_start=pd.Timestamp(window_start).date(),
        window_end=pd.Timestamp(window_end).date(),
    )


def _demand_to_frame(inputs: OptimizerInput) -> pd.DataFrame:
    return pd.DataFrame(asdict(row) for row in inputs.demand)


def _capability_to_frame(inputs: OptimizerInput) -> pd.DataFrame:
    return pd.DataFrame(asdict(row) for row in inputs.capability)


def _changeovers_to_frame(inputs: OptimizerInput) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for edge in inputs.changeovers:
        dominant = ""
        if edge.segments:
            dominant = max(edge.segments.items(), key=lambda item: item[1])[0]
        rows.append(
            {
                "line_id": edge.line_id,
                "sku_from_id": edge.sku_from_id,
                "sku_to_id": edge.sku_to_id,
                "total_hours": edge.total_hours,
                "dominant_component": dominant,
                "source": edge.source,
            }
        )
    return pd.DataFrame(rows)


def _parse_log_step_counts(solver_log: str) -> dict[str, int]:
    marker = "moves accepted    :"
    if marker not in solver_log:
        return {}
    try:
        line = next(row for row in solver_log.splitlines() if marker in row)
        return {
            part.split("=")[0]: int(part.split("=")[1])
            for part in line.split()
            if "=" in part
        }
    except (StopIteration, IndexError, ValueError):
        return {}


__all__ = [
    "GraphOptimizer",
    "LineRoute",
    "OptimizerResult",
    "optimize_graph",
    "optimize_window",
]
