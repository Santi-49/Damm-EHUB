import networkx as nx

from services.optimizer.app.implementacion_v2 import (
    HeldKarpPartitionOptimizer,
    optimize_graph,
)


def test_held_karp_returns_exact_open_path() -> None:
    graph = nx.MultiDiGraph(window_id="synthetic")
    for node in ("A", "B", "C"):
        graph.add_node(node, line_data={14: {"predicted_hours": 1.0}})

    for source, target, hours in (
        ("A", "B", 1.0),
        ("B", "C", 1.0),
        ("A", "C", 10.0),
        ("C", "B", 10.0),
        ("B", "A", 10.0),
        ("C", "A", 10.0),
    ):
        graph.add_edge(source, target, key=14, line_id=14, hours=hours)

    optimizer = HeldKarpPartitionOptimizer(line_ids=(14,), max_exact_nodes=10)
    route = optimizer.solve_line_route(graph, 14, ("A", "B", "C"))

    assert route.feasible
    assert route.order == ("A", "B", "C")
    assert route.changeover_hours == 2.0
    assert route.total_hours == 5.0


def test_optimizer_respects_line_data_capability() -> None:
    graph = nx.MultiDiGraph(window_id="synthetic")
    graph.add_node("A", line_data={14: {"predicted_hours": 1.0}})
    graph.add_node("B", line_data={17: {"predicted_hours": 1.0}})
    graph.add_node("C", line_data={14: {"predicted_hours": 2.0}, 17: {"predicted_hours": 2.0}})

    graph.add_edge("A", "C", key=14, line_id=14, hours=1.0)
    graph.add_edge("C", "A", key=14, line_id=14, hours=1.0)
    graph.add_edge("B", "C", key=17, line_id=17, hours=1.0)
    graph.add_edge("C", "B", key=17, line_id=17, hours=1.0)

    result = optimize_graph(
        graph,
        max_exact_nodes=10,
        enable_swaps=True,
        enable_balance_repair=False,
    )

    assert result.feasible
    assert result.dropped == ()
    assert "A" in result.assignments[14]
    assert "B" in result.assignments[17]
    assert all("B" not in route.nodes for line, route in result.routes.items() if line != 17)

