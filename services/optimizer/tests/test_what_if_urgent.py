from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_GRAPH_DIR = _REPO_ROOT / "services" / "optimizer" / "graph"
if str(_GRAPH_DIR) not in sys.path:
    sys.path.insert(0, str(_GRAPH_DIR))

from line_partitioner import PartitionResult  # noqa: E402
from what_if import what_if_urgent_demand  # noqa: E402


LINE_IDS = (14, 17)
URGENT_NODE = "U__urgent_1000"


def _baseline() -> PartitionResult:
    return PartitionResult(
        sequences={14: ("A", "B"), 17: ("C",)},
        makespan_per_line_hours={14: 7.0, 17: 2.0},
        makespan_hours=7.0,
        total_hours=9.0,
        production_hours_per_line={14: 6.0, 17: 2.0},
        changeover_hours_per_line={14: 1.0, 17: 0.0},
        dropped=(),
        solver_log="",
        iterations=0,
        elapsed_s=0.0,
    )


def _can_produce(sku: str, line: int) -> bool:
    return line in {
        "A": {14},
        "B": {14},
        "C": {17},
        URGENT_NODE: {14},
    }.get(sku, set())


def _node_cost(sku: str, line: int) -> float:
    del line
    return {
        "A": 2.0,
        "B": 4.0,
        "C": 2.0,
        URGENT_NODE: 1.0,
    }[sku]


def _edge_cost(a: str, b: str, line: int) -> float:
    del line
    return {
        ("A", "B"): 1.0,
        ("A", URGENT_NODE): 1.0,
        (URGENT_NODE, "B"): 0.5,
    }.get((a, b), 0.25)


def test_urgent_demand_is_forced_inside_required_window() -> None:
    result = what_if_urgent_demand(
        _baseline(),
        introduced_at_hours=2.0,
        required_by_hours=4.5,
        urgent_sku="U",
        urgent_node=URGENT_NODE,
        urgent_units=1_000,
        sku_ids=("A", "B", "C"),
        line_ids=LINE_IDS,
        can_produce=_can_produce,
        edge_cost=_edge_cost,
        node_cost=_node_cost,
        units_by_sku={"A": 10, "B": 10, "C": 10, URGENT_NODE: 1_000},
        time_budget_s=0.2,
        sequence_budget_s=0.01,
        move_strategy="first_improvement",
    )

    assert result.assigned_line == 14
    assert result.committed_per_line[14] == ("A",)
    assert result.new_sequences[14][0] == URGENT_NODE
    assert result.urgent_start_hours == 3.0
    assert result.urgent_end_hours == 4.0
    assert result.urgent_end_hours <= result.required_by_hours
    assert result.due_window_met


def test_urgent_demand_rejects_impossible_deadline() -> None:
    with pytest.raises(ValueError, match="cannot fit in the required time window"):
        what_if_urgent_demand(
            _baseline(),
            introduced_at_hours=2.0,
            required_by_hours=3.5,
            urgent_sku="U",
            urgent_node=URGENT_NODE,
            urgent_units=1_000,
            sku_ids=("A", "B", "C"),
            line_ids=LINE_IDS,
            can_produce=_can_produce,
            edge_cost=_edge_cost,
            node_cost=_node_cost,
            time_budget_s=0.2,
            sequence_budget_s=0.01,
            move_strategy="first_improvement",
        )
