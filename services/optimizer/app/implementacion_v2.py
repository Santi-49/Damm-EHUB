"""Optimizer v2: partition search with exact Held-Karp line routing.

This module consumes the ``nx.MultiDiGraph`` produced by
``services.optimizer.app.graph_builder.build_planning_graph``:

* graph node key: ``sku_id``
* node attr ``line_data[line_id]["predicted_hours"]``: production cost on a line
* edge key ``line_id`` plus edge attr ``hours``: changeover cost on that line

The global problem is handled as:

1. greedy feasible initial partition,
2. exact Held-Karp routing per line,
3. local partition improvement by node moves and swaps,
4. optional min-max balance repair when the final gap is too large.

Held-Karp here solves the exact open Hamiltonian path for a fixed line
assignment. Production planning does not need to return to a depot/SKU, so the
route cost is the cheapest sequence through all assigned nodes.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import inf, isfinite
from statistics import fmean
from typing import Iterable

import networkx as nx

LINE_IDS: tuple[int, ...] = (14, 17, 19)
DEFAULT_BALANCE_DELTA_HOURS = 8.0
EPSILON = 1e-9


@dataclass(frozen=True)
class LineRoute:
    """Exact route evaluation for one line and one fixed node set."""

    line_id: int
    nodes: tuple[str, ...]
    order: tuple[str, ...]
    production_hours: float
    changeover_hours: float
    total_hours: float
    feasible: bool
    reason: str | None = None


@dataclass(frozen=True)
class OptimizerV2Result:
    """Result returned by ``optimize_graph``."""

    assignments: dict[int, tuple[str, ...]]
    routes: dict[int, LineRoute]
    makespan_hours: float
    total_hours: float
    gap_hours: float
    dropped: tuple[str, ...]
    feasible: bool
    iterations: int
    accepted_moves: int
    balance_repairs: int
    solver_log: str


@dataclass(frozen=True)
class _PartitionState:
    assignments: dict[int, tuple[str, ...]]
    routes: dict[int, LineRoute]
    makespan_hours: float
    total_hours: float
    gap_hours: float
    feasible: bool


class HeldKarpPartitionOptimizer:
    """Partition nodes across lines and route each line exactly with Held-Karp."""

    def __init__(
        self,
        *,
        line_ids: Iterable[int] = LINE_IDS,
        balance_delta_hours: float = DEFAULT_BALANCE_DELTA_HOURS,
        max_iterations: int = 50,
        max_exact_nodes: int = 20,
        enable_swaps: bool = True,
        max_swap_candidates: int = 60,
        enable_balance_repair: bool = True,
        max_balance_repairs: int = 20,
        tolerance: float = EPSILON,
    ) -> None:
        self.line_ids = tuple(int(line_id) for line_id in line_ids)
        self.balance_delta_hours = float(balance_delta_hours)
        self.max_iterations = int(max_iterations)
        self.max_exact_nodes = int(max_exact_nodes)
        self.enable_swaps = bool(enable_swaps)
        self.max_swap_candidates = int(max_swap_candidates)
        self.enable_balance_repair = bool(enable_balance_repair)
        self.max_balance_repairs = int(max_balance_repairs)
        self.tolerance = float(tolerance)
        self._route_cache: dict[tuple[int, tuple[str, ...]], LineRoute] = {}
        self._approx_cache: dict[tuple[str, int], float] = {}

    def optimize(self, graph: nx.MultiDiGraph) -> OptimizerV2Result:
        """Optimize a ``build_planning_graph`` output graph."""

        self._validate_graph(graph)
        assignments, dropped = self._initial_partition(graph)
        state = self._evaluate_partition(graph, assignments)

        log_lines = [
            "Optimizer v2: greedy partition + exact Held-Karp line routing.",
            f"nodes={graph.number_of_nodes()} dropped_without_line={len(dropped)}",
            f"initial_makespan={state.makespan_hours:.3f}h",
        ]

        accepted_moves = 0
        iterations_done = 0

        for iteration in range(1, self.max_iterations + 1):
            candidate = self._best_local_improvement(graph, state)
            if candidate is None:
                break
            state = candidate
            accepted_moves += 1
            iterations_done = iteration
            log_lines.append(
                f"iter={iteration} makespan={state.makespan_hours:.3f}h "
                f"gap={state.gap_hours:.3f}h"
            )

        balance_repairs = 0
        if self.enable_balance_repair:
            state, balance_repairs = self._apply_balance_repair(graph, state)
            if balance_repairs:
                log_lines.append(
                    f"balance_repairs={balance_repairs} "
                    f"makespan={state.makespan_hours:.3f}h gap={state.gap_hours:.3f}h"
                )

        feasible = state.feasible and not dropped
        if not state.feasible:
            bad = [
                f"L{line}:{route.reason or 'infeasible'}"
                for line, route in state.routes.items()
                if not route.feasible
            ]
            log_lines.append("infeasible_routes=" + ", ".join(bad))

        return OptimizerV2Result(
            assignments=state.assignments,
            routes=state.routes,
            makespan_hours=state.makespan_hours,
            total_hours=state.total_hours,
            gap_hours=state.gap_hours,
            dropped=tuple(sorted(dropped)),
            feasible=feasible,
            iterations=iterations_done,
            accepted_moves=accepted_moves,
            balance_repairs=balance_repairs,
            solver_log="\n".join(log_lines),
        )

    def solve_line_route(
        self,
        graph: nx.MultiDiGraph,
        line_id: int,
        nodes: Iterable[str],
    ) -> LineRoute:
        """Return the exact route for a fixed line/node set."""

        normalized = tuple(sorted(dict.fromkeys(str(node) for node in nodes)))
        key = (int(line_id), normalized)
        cached = self._route_cache.get(key)
        if cached is not None:
            return cached

        route = self._solve_line_route_uncached(graph, int(line_id), normalized)
        self._route_cache[key] = route
        return route

    def _solve_line_route_uncached(
        self,
        graph: nx.MultiDiGraph,
        line_id: int,
        nodes: tuple[str, ...],
    ) -> LineRoute:
        if not nodes:
            return LineRoute(
                line_id=line_id,
                nodes=nodes,
                order=(),
                production_hours=0.0,
                changeover_hours=0.0,
                total_hours=0.0,
                feasible=True,
            )

        missing = [node for node in nodes if not self._node_can_run(graph, node, line_id)]
        if missing:
            return self._infeasible_route(
                line_id,
                nodes,
                f"nodes_not_capable:{','.join(missing)}",
            )

        if len(nodes) > self.max_exact_nodes:
            return self._infeasible_route(
                line_id,
                nodes,
                f"held_karp_node_limit_exceeded:{len(nodes)}>{self.max_exact_nodes}",
            )

        production = sum(self._node_cost(graph, node, line_id) for node in nodes)
        if len(nodes) == 1:
            return LineRoute(
                line_id=line_id,
                nodes=nodes,
                order=nodes,
                production_hours=production,
                changeover_hours=0.0,
                total_hours=production,
                feasible=True,
            )

        distances = self._distance_matrix(graph, line_id, nodes)
        best_changeover, order = self._held_karp_open_path(nodes, distances)
        if not isfinite(best_changeover):
            return self._infeasible_route(
                line_id,
                nodes,
                "no_finite_hamiltonian_path",
            )

        return LineRoute(
            line_id=line_id,
            nodes=nodes,
            order=order,
            production_hours=production,
            changeover_hours=best_changeover,
            total_hours=production + best_changeover,
            feasible=True,
        )

    def _held_karp_open_path(
        self,
        nodes: tuple[str, ...],
        distances: list[list[float]],
    ) -> tuple[float, tuple[str, ...]]:
        """Exact shortest Hamiltonian path with free start and free end."""

        n_nodes = len(nodes)
        full_mask = (1 << n_nodes) - 1
        dp: dict[tuple[int, int], float] = {}
        parent: dict[tuple[int, int], int] = {}

        for end in range(n_nodes):
            dp[(1 << end, end)] = 0.0

        for mask in range(1, full_mask + 1):
            for end in range(n_nodes):
                current = dp.get((mask, end))
                if current is None:
                    continue
                remaining = full_mask ^ mask
                while remaining:
                    bit = remaining & -remaining
                    nxt = bit.bit_length() - 1
                    remaining ^= bit
                    edge_cost = distances[end][nxt]
                    if not isfinite(edge_cost):
                        continue
                    next_mask = mask | bit
                    next_key = (next_mask, nxt)
                    next_cost = current + edge_cost
                    if next_cost + self.tolerance < dp.get(next_key, inf):
                        dp[next_key] = next_cost
                        parent[next_key] = end

        best_end = min(
            range(n_nodes),
            key=lambda end: dp.get((full_mask, end), inf),
        )
        best_cost = dp.get((full_mask, best_end), inf)
        if not isfinite(best_cost):
            return inf, ()

        order_idx: list[int] = []
        mask = full_mask
        end = best_end
        while True:
            order_idx.append(end)
            previous = parent.get((mask, end))
            if previous is None:
                break
            mask ^= 1 << end
            end = previous

        order = tuple(nodes[index] for index in reversed(order_idx))
        return best_cost, order

    def _initial_partition(
        self,
        graph: nx.MultiDiGraph,
    ) -> tuple[dict[int, tuple[str, ...]], list[str]]:
        assignments: dict[int, list[str]] = {line: [] for line in self.line_ids}
        estimated_load = {line: 0.0 for line in self.line_ids}
        dropped: list[str] = []

        nodes = sorted(graph.nodes, key=str)
        for node in nodes:
            candidates = [
                line for line in self.line_ids
                if self._node_can_run(graph, str(node), line)
            ]
            if not candidates:
                dropped.append(str(node))
                continue

            exact_sized_candidates = [
                line for line in candidates
                if len(assignments[line]) < self.max_exact_nodes
            ]
            candidate_pool = exact_sized_candidates or candidates
            best_line = min(
                candidate_pool,
                key=lambda line: (
                    estimated_load[line] + self._approx_line_cost(graph, str(node), line),
                    len(assignments[line]),
                    self._approx_line_cost(graph, str(node), line),
                    line,
                ),
            )
            assignments[best_line].append(str(node))
            estimated_load[best_line] += self._approx_line_cost(graph, str(node), best_line)

        return {line: tuple(nodes_) for line, nodes_ in assignments.items()}, dropped

    def _best_local_improvement(
        self,
        graph: nx.MultiDiGraph,
        state: _PartitionState,
    ) -> _PartitionState | None:
        bottleneck_lines = self._bottleneck_lines(state)
        target_order = sorted(
            self.line_ids,
            key=lambda line: (state.routes[line].total_hours, line),
        )

        for source in bottleneck_lines:
            source_nodes = sorted(
                state.assignments[source],
                key=lambda node: self._node_cost(graph, node, source),
                reverse=True,
            )
            for target in target_order:
                if source == target:
                    continue
                for node in source_nodes:
                    if not self._node_can_run(graph, node, target):
                        continue
                    candidate_assignments = self._move_node(
                        state.assignments,
                        node,
                        source,
                        target,
                    )
                    candidate = self._evaluate_partition(
                        graph,
                        candidate_assignments,
                        base_routes=state.routes,
                        affected_lines={source, target},
                    )
                    if not candidate.feasible:
                        continue
                    if self._is_better(candidate, state):
                        return candidate

        if self.enable_swaps:
            evaluated_swaps = 0
            for idx, line_a in enumerate(self.line_ids):
                for line_b in self.line_ids[idx + 1:]:
                    if line_a not in bottleneck_lines and line_b not in bottleneck_lines:
                        continue

                    nodes_a = sorted(
                        state.assignments[line_a],
                        key=lambda node: self._node_cost(graph, node, line_a),
                        reverse=line_a in bottleneck_lines,
                    )
                    nodes_b = sorted(
                        state.assignments[line_b],
                        key=lambda node: self._node_cost(graph, node, line_b),
                        reverse=line_b in bottleneck_lines,
                    )

                    for node_a in nodes_a:
                        if not self._node_can_run(graph, node_a, line_b):
                            continue
                        for node_b in nodes_b:
                            if not self._node_can_run(graph, node_b, line_a):
                                continue
                            if evaluated_swaps >= self.max_swap_candidates:
                                return None
                            evaluated_swaps += 1
                            candidate_assignments = self._swap_nodes(
                                state.assignments,
                                node_a,
                                line_a,
                                node_b,
                                line_b,
                            )
                            candidate = self._evaluate_partition(
                                graph,
                                candidate_assignments,
                                base_routes=state.routes,
                                affected_lines={line_a, line_b},
                            )
                            if not candidate.feasible:
                                continue
                            if self._is_better(candidate, state):
                                return candidate

        return None

    def _apply_balance_repair(
        self,
        graph: nx.MultiDiGraph,
        state: _PartitionState,
    ) -> tuple[_PartitionState, int]:
        repairs = 0

        while repairs < self.max_balance_repairs:
            if not state.feasible or state.gap_hours <= self.balance_delta_hours + self.tolerance:
                break

            totals = {line: state.routes[line].total_hours for line in self.line_ids}
            long_line = max(totals, key=totals.get)
            short_line = min(totals, key=totals.get)
            best_candidate: _PartitionState | None = None
            best_key: tuple[float, float, float, float] | None = None

            for node in state.assignments[long_line]:
                if not self._node_can_run(graph, node, short_line):
                    continue

                candidate_assignments = self._move_node(
                    state.assignments,
                    node,
                    long_line,
                    short_line,
                )
                candidate = self._evaluate_partition(
                    graph,
                    candidate_assignments,
                    base_routes=state.routes,
                    affected_lines={long_line, short_line},
                )
                if not candidate.feasible:
                    continue
                if candidate.gap_hours + self.tolerance >= state.gap_hours:
                    continue

                old_long = state.routes[long_line].total_hours
                new_long = candidate.routes[long_line].total_hours
                old_short = state.routes[short_line].total_hours
                new_short = candidate.routes[short_line].total_hours
                score = (old_long - new_long) - max(0.0, new_short - old_short)
                key = (
                    candidate.gap_hours,
                    candidate.makespan_hours,
                    -score,
                    candidate.total_hours,
                )
                if best_key is None or key < best_key:
                    best_key = key
                    best_candidate = candidate

            if best_candidate is None:
                break

            state = best_candidate
            repairs += 1

        return state, repairs

    def _evaluate_partition(
        self,
        graph: nx.MultiDiGraph,
        assignments: dict[int, tuple[str, ...]],
        *,
        base_routes: dict[int, LineRoute] | None = None,
        affected_lines: set[int] | None = None,
    ) -> _PartitionState:
        routes: dict[int, LineRoute] = {}
        affected = set(self.line_ids) if affected_lines is None else set(affected_lines)

        for line in self.line_ids:
            if base_routes is not None and line not in affected:
                routes[line] = base_routes[line]
            else:
                routes[line] = self.solve_line_route(graph, line, assignments.get(line, ()))

        totals = [routes[line].total_hours for line in self.line_ids]
        finite_totals = [total for total in totals if isfinite(total)]
        makespan = max(totals) if totals else 0.0
        total_hours = sum(totals) if all(isfinite(total) for total in totals) else inf
        gap = (
            max(finite_totals) - min(finite_totals)
            if finite_totals and len(finite_totals) == len(self.line_ids)
            else inf
        )
        feasible = all(route.feasible for route in routes.values())

        return _PartitionState(
            assignments={line: tuple(assignments.get(line, ())) for line in self.line_ids},
            routes=routes,
            makespan_hours=makespan,
            total_hours=total_hours,
            gap_hours=gap,
            feasible=feasible,
        )

    def _move_node(
        self,
        assignments: dict[int, tuple[str, ...]],
        node: str,
        source: int,
        target: int,
    ) -> dict[int, tuple[str, ...]]:
        moved: dict[int, list[str]] = {
            line: list(assignments.get(line, ())) for line in self.line_ids
        }
        moved[source].remove(node)
        moved[target].append(node)
        return {line: tuple(sorted(nodes)) for line, nodes in moved.items()}

    def _swap_nodes(
        self,
        assignments: dict[int, tuple[str, ...]],
        node_a: str,
        line_a: int,
        node_b: str,
        line_b: int,
    ) -> dict[int, tuple[str, ...]]:
        swapped: dict[int, list[str]] = {
            line: list(assignments.get(line, ())) for line in self.line_ids
        }
        swapped[line_a].remove(node_a)
        swapped[line_b].remove(node_b)
        swapped[line_a].append(node_b)
        swapped[line_b].append(node_a)
        return {line: tuple(sorted(nodes)) for line, nodes in swapped.items()}

    def _distance_matrix(
        self,
        graph: nx.MultiDiGraph,
        line_id: int,
        nodes: tuple[str, ...],
    ) -> list[list[float]]:
        matrix: list[list[float]] = []
        for source in nodes:
            row: list[float] = []
            for target in nodes:
                if source == target:
                    row.append(0.0)
                else:
                    row.append(self._edge_cost(graph, source, target, line_id))
            matrix.append(row)
        return matrix

    def _node_can_run(self, graph: nx.MultiDiGraph, node: str, line_id: int) -> bool:
        if node not in graph:
            return False
        return self._line_data(graph, node, line_id) is not None

    def _node_cost(self, graph: nx.MultiDiGraph, node: str, line_id: int) -> float:
        line_data = self._line_data(graph, node, line_id)
        if line_data is None:
            return inf
        value = line_data.get("predicted_hours", inf)
        try:
            return float(value)
        except (TypeError, ValueError):
            return inf

    def _edge_cost(
        self,
        graph: nx.MultiDiGraph,
        source: str,
        target: str,
        line_id: int,
    ) -> float:
        edge_data = graph.get_edge_data(source, target, key=line_id)
        if edge_data is None:
            edge_data = graph.get_edge_data(source, target, key=str(line_id))
        if edge_data is None:
            return inf
        try:
            return float(edge_data.get("hours", inf))
        except (TypeError, ValueError):
            return inf

    def _line_data(
        self,
        graph: nx.MultiDiGraph,
        node: str,
        line_id: int,
    ) -> dict[str, float] | None:
        raw = graph.nodes[node].get("line_data", {})
        if line_id in raw:
            return raw[line_id]
        str_line = str(line_id)
        if str_line in raw:
            return raw[str_line]
        return None

    def _approx_line_cost(self, graph: nx.MultiDiGraph, node: str, line_id: int) -> float:
        key = (node, line_id)
        cached = self._approx_cache.get(key)
        if cached is not None:
            return cached

        production = self._node_cost(graph, node, line_id)
        if not isfinite(production):
            self._approx_cache[key] = inf
            return inf

        incident_edges: list[float] = []
        for other in graph.nodes:
            other_node = str(other)
            if other_node == node or not self._node_can_run(graph, other_node, line_id):
                continue
            out_cost = self._edge_cost(graph, node, other_node, line_id)
            in_cost = self._edge_cost(graph, other_node, node, line_id)
            if isfinite(out_cost):
                incident_edges.append(out_cost)
            if isfinite(in_cost):
                incident_edges.append(in_cost)

        transition_proxy = fmean(incident_edges) if incident_edges else 0.0
        cost = production + transition_proxy
        self._approx_cache[key] = cost
        return cost

    def _is_better(self, candidate: _PartitionState, incumbent: _PartitionState) -> bool:
        if candidate.makespan_hours + self.tolerance < incumbent.makespan_hours:
            return True
        if abs(candidate.makespan_hours - incumbent.makespan_hours) > self.tolerance:
            return False
        return candidate.total_hours + self.tolerance < incumbent.total_hours

    def _bottleneck_lines(self, state: _PartitionState) -> tuple[int, ...]:
        if not isfinite(state.makespan_hours):
            return tuple(
                line for line in self.line_ids
                if not isfinite(state.routes[line].total_hours)
            ) or self.line_ids
        return tuple(
            line for line in self.line_ids
            if state.routes[line].total_hours + self.tolerance >= state.makespan_hours
        )

    def _infeasible_route(
        self,
        line_id: int,
        nodes: tuple[str, ...],
        reason: str,
    ) -> LineRoute:
        return LineRoute(
            line_id=line_id,
            nodes=nodes,
            order=(),
            production_hours=inf,
            changeover_hours=inf,
            total_hours=inf,
            feasible=False,
            reason=reason,
        )

    def _validate_graph(self, graph: nx.MultiDiGraph) -> None:
        if not isinstance(graph, nx.MultiDiGraph):
            raise TypeError("Optimizer v2 expects the nx.MultiDiGraph from build_planning_graph")
        for node, attrs in graph.nodes(data=True):
            if "line_data" not in attrs:
                raise ValueError(f"graph node {node!r} is missing line_data")


def optimize_graph(
    graph: nx.MultiDiGraph,
    *,
    balance_delta_hours: float = DEFAULT_BALANCE_DELTA_HOURS,
    max_iterations: int = 50,
    max_exact_nodes: int = 20,
    enable_swaps: bool = True,
    max_swap_candidates: int = 60,
    enable_balance_repair: bool = True,
) -> OptimizerV2Result:
    """Convenience function for optimizing a graph_builder planning graph."""

    optimizer = HeldKarpPartitionOptimizer(
        balance_delta_hours=balance_delta_hours,
        max_iterations=max_iterations,
        max_exact_nodes=max_exact_nodes,
        enable_swaps=enable_swaps,
        max_swap_candidates=max_swap_candidates,
        enable_balance_repair=enable_balance_repair,
    )
    return optimizer.optimize(graph)


def optimize_window(window_id: str, **kwargs: object) -> OptimizerV2Result:
    """Build the planning graph for ``window_id`` and run optimizer v2."""

    from services.optimizer.app.graph_builder import build_planning_graph

    graph = build_planning_graph(window_id)
    return optimize_graph(graph, **kwargs)


__all__ = [
    "HeldKarpPartitionOptimizer",
    "LineRoute",
    "OptimizerV2Result",
    "optimize_graph",
    "optimize_window",
]
