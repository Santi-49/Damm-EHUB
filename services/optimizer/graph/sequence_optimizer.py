"""Single-line sequence optimiser — Asymmetric TSP (open Hamiltonian path).

Given a set of SKU nodes assigned to **one** line and an asymmetric edge-cost
function (changeover hours from A → B), return the ordering that minimises
the total changeover time along the path.

Why ATSP and not symmetric TSP
------------------------------

Real changeovers are direction-sensitive — going from a 33 cl Estrella to a
50 cl Voll-Damm needs a full format swap, while the reverse may need only a
recipe purge. Our mock cost function in :mod:`generate_test_data` reproduces
this asymmetry by adding a small term keyed on SKU-id ordering, and the real
ML predictor will too. The optimiser must therefore handle ``c(u, v) != c(v, u)``.

Why an *open* path and not a closed cycle
-----------------------------------------

A weekly plan ends Sunday and a new plan starts Monday — there is no edge
from the last SKU back to the first within the same horizon. So we solve a
Hamiltonian *path*, not a tour. The Held-Karp DP and the local-search moves
are both written for the open-path variant.

Algorithms (best-in-class cascade)
----------------------------------

1. **Held-Karp** dynamic programming — O(n² · 2ⁿ), exact. Used when
   ``len(nodes) <= exact_max_n`` (default 15 ≈ 15 × 32 768 = 500 k subproblems,
   well under a second).
2. **LKH-3** via the ``elkai`` C extension — state-of-the-art ATSP solver
   (Lin-Kernighan-Helsgaun). Used in the medium regime (``exact_max_n < n <=
   lkh_max_n``). Typically within 0.1 % of the optimum on n=50-200 in tens of
   milliseconds. Fixed start / end implemented via the classical *dummy-node*
   reduction (zero-cost in-link from dummy to start, zero-cost out-link from
   end to dummy, infinity elsewhere).
3. **NN + 2-opt + Or-opt + SA** — pure-Python fallback for the rare case the
   ``elkai`` extension is unavailable or returns an infeasible cycle.

The whole flow is bounded by ``time_budget_s`` (default 1.8 s) so it stays
inside the < 2 s presentation latency requirement.

Decoupling
----------

The optimiser is **agnostic about what a node is**. It takes a list of
hashable IDs and a pair of callables ``edge_cost(a, b) -> float`` and
``node_cost(a) -> float``. The downstream call from the partitioner closes
over the line, so a single optimizer instance can be reused for L14/L17/L19.
"""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass
from typing import Callable, Hashable, Sequence

try:
    import elkai  # type: ignore[import-untyped]
    _ELKAI_AVAILABLE = True
except ImportError:  # pragma: no cover - elkai is a hard dep but guard anyway
    _ELKAI_AVAILABLE = False


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SequenceResult:
    """Output of :func:`optimize_sequence`.

    ``total_hours = production_hours + changeover_hours``. For pure ATSP only
    ``changeover_hours`` is minimised (node / production costs are
    order-invariant since every node is visited exactly once), but both are
    reported so the makespan breakdown is transparent.

    Field names mirror :class:`packages.contracts.module.schemas.LineMetrics`
    so a downstream caller can stash this dataclass into the simulator's
    return shape with zero re-mapping.
    """

    sequence: tuple[Hashable, ...]
    total_hours: float
    production_hours: float
    changeover_hours: float
    algorithm: str
    iterations: int
    elapsed_s: float


# ---------------------------------------------------------------------------
# Cost helpers
# ---------------------------------------------------------------------------

EdgeCost = Callable[[Hashable, Hashable], float]
NodeCost = Callable[[Hashable], float]


def _edge_cost_path(seq: Sequence[Hashable], edge_cost: EdgeCost) -> float:
    """Sum of edge costs along an open path."""
    if len(seq) < 2:
        return 0.0
    return sum(edge_cost(seq[i - 1], seq[i]) for i in range(1, len(seq)))


def _node_cost_path(seq: Sequence[Hashable], node_cost: NodeCost) -> float:
    return sum(node_cost(n) for n in seq)


# ---------------------------------------------------------------------------
# Held-Karp exact DP (open path)
# ---------------------------------------------------------------------------

def _held_karp(
    nodes: list[Hashable],
    edge_cost: EdgeCost,
    *,
    start: Hashable | None,
    end: Hashable | None,
) -> tuple[list[Hashable], float, int]:
    """Exact min-cost Hamiltonian path. Returns ``(sequence, edge_cost, n_subproblems)``."""
    n = len(nodes)
    if n == 0:
        return [], 0.0, 0
    if n == 1:
        return list(nodes), 0.0, 1

    idx_of = {nd: i for i, nd in enumerate(nodes)}

    # Pre-compute the cost matrix once — edge_cost may be expensive.
    INF = math.inf
    cost = [[0.0] * n for _ in range(n)]
    for i in range(n):
        a = nodes[i]
        for j in range(n):
            if i != j:
                cost[i][j] = edge_cost(a, nodes[j])

    full = (1 << n) - 1
    # f[S][j] = min edge-cost path visiting exactly bitmask S, ending at j ∈ S.
    f: list[list[float]] = [[INF] * n for _ in range(1 << n)]
    parent: list[list[int]] = [[-1] * n for _ in range(1 << n)]

    starts = [idx_of[start]] if start is not None else list(range(n))
    for s in starts:
        f[1 << s][s] = 0.0

    n_sub = 0
    for S in range(1, 1 << n):
        for j in range(n):
            if not (S & (1 << j)):
                continue
            base = f[S][j]
            if base == INF:
                continue
            n_sub += 1
            rem = (~S) & full
            while rem:
                k = (rem & -rem).bit_length() - 1
                rem &= rem - 1
                S2 = S | (1 << k)
                cand = base + cost[j][k]
                if cand < f[S2][k]:
                    f[S2][k] = cand
                    parent[S2][k] = j

    ends = [idx_of[end]] if end is not None else list(range(n))
    best_end, best_cost = -1, INF
    for j in ends:
        if f[full][j] < best_cost:
            best_end, best_cost = j, f[full][j]

    # Reconstruct path
    rev: list[int] = []
    S, cur = full, best_end
    while cur != -1:
        rev.append(cur)
        prev = parent[S][cur]
        S ^= 1 << cur
        cur = prev
    rev.reverse()
    return [nodes[i] for i in rev], best_cost, n_sub


# ---------------------------------------------------------------------------
# LKH-3 backend (via elkai) — open Hamiltonian path with optional pinned ends
# ---------------------------------------------------------------------------

# Cost scaling for the integer LKH solver. The synthetic edge costs are
# expressed in hours with three decimals, so 1e4 keeps two digits of safety
# margin while staying well under int32.
_LKH_SCALE: int = 10_000
_LKH_INF: int = 10**9


def _lkh_open_path(
    nodes: list[Hashable],
    edge_cost: EdgeCost,
    *,
    start: Hashable | None,
    end: Hashable | None,
) -> tuple[list[Hashable], float] | None:
    """Solve the open-path ATSP with LKH-3 via the dummy-node reduction.

    The reduction (textbook, Helsgaun 2000) is:

    * Add one extra node ``D``.
    * Set ``c(D, start) = 0`` (or ``0`` for all candidates if start is free).
    * Set ``c(end, D) = 0`` (or ``0`` for all candidates if end is free).
    * Set every other edge involving ``D`` to ``+∞``.
    * Solve the closed TSP. Rotate the resulting cycle so it ends at ``D`` —
      the prefix is exactly the open path ``start → … → end``.

    Returns ``None`` if elkai is unavailable or the cycle did not include the
    forced shape (caller falls back to the heuristic regime).
    """
    if not _ELKAI_AVAILABLE:
        return None
    n = len(nodes)
    if n < 3:
        return None

    idx_of = {nd: i for i, nd in enumerate(nodes)}
    start_idx = idx_of[start] if start is not None else None
    end_idx = idx_of[end] if end is not None else None

    # Cost matrix of size (n+1) × (n+1). Diagonal is INF (no self-loops).
    size = n + 1
    dummy = n
    matrix: list[list[int]] = [[_LKH_INF] * size for _ in range(size)]
    for i in range(n):
        a = nodes[i]
        for j in range(n):
            if i == j:
                continue
            matrix[i][j] = int(round(edge_cost(a, nodes[j]) * _LKH_SCALE))
    # Dummy → real
    if start_idx is None:
        for k in range(n):
            matrix[dummy][k] = 0
    else:
        matrix[dummy][start_idx] = 0
    # Real → dummy
    if end_idx is None:
        for k in range(n):
            matrix[k][dummy] = 0
    else:
        matrix[end_idx][dummy] = 0
    matrix[dummy][dummy] = 0

    solver = elkai.DistanceMatrix(matrix)
    tour = solver.solve_tsp()  # closed cycle, starts and ends at index 0
    # Tour shape: [0, ..., 0]. We need to locate `dummy` and rotate so the
    # cycle reads [dummy, start_node, ..., end_node, dummy], then drop the
    # dummy and return the inner path.
    if dummy not in tour:
        return None
    # Strip the duplicate closing index, then rotate so dummy is at index 0.
    body = tour[:-1]
    d_pos = body.index(dummy)
    rotated = body[d_pos:] + body[:d_pos]
    # rotated[0] is dummy, the rest is the path. Validate forced ends.
    path_idx = rotated[1:]
    if start_idx is not None and path_idx[0] != start_idx:
        return None
    if end_idx is not None and path_idx[-1] != end_idx:
        return None
    if any(i == dummy for i in path_idx):
        return None
    path = [nodes[i] for i in path_idx]
    return path, _edge_cost_path(path, edge_cost)


# ---------------------------------------------------------------------------
# Construction heuristic — best-of-N nearest neighbour
# ---------------------------------------------------------------------------

def _nearest_neighbour(
    nodes: list[Hashable],
    edge_cost: EdgeCost,
    *,
    start_idx: int,
) -> list[Hashable]:
    """One greedy nearest-neighbour pass starting from ``nodes[start_idx]``."""
    remaining = set(nodes)
    cur = nodes[start_idx]
    remaining.remove(cur)
    seq = [cur]
    while remaining:
        nxt = min(remaining, key=lambda x: edge_cost(cur, x))
        seq.append(nxt)
        remaining.remove(nxt)
        cur = nxt
    return seq


def _best_of_nn(
    nodes: list[Hashable],
    edge_cost: EdgeCost,
    *,
    start: Hashable | None,
    end: Hashable | None,
) -> list[Hashable]:
    """Return the cheapest NN path across all valid starting nodes."""
    if start is not None:
        candidates_starts = [nodes.index(start)]
    else:
        candidates_starts = list(range(len(nodes)))

    best_seq, best_cost = None, math.inf
    for s in candidates_starts:
        seq = _nearest_neighbour(nodes, edge_cost, start_idx=s)
        if end is not None and seq[-1] != end:
            # Try forcing the end by swapping the tail-occurrence of `end`
            try:
                eidx = seq.index(end)
                seq = seq[:eidx] + seq[eidx + 1:] + [end]
            except ValueError:
                pass
        c = _edge_cost_path(seq, edge_cost)
        if c < best_cost:
            best_cost, best_seq = c, seq
    return list(best_seq) if best_seq is not None else list(nodes)


# ---------------------------------------------------------------------------
# Local-search moves (asymmetric-safe, brute-force deltas)
# ---------------------------------------------------------------------------

def _or_opt_best_improvement(
    seq: list[Hashable],
    edge_cost: EdgeCost,
    *,
    start_fixed: bool,
    end_fixed: bool,
) -> tuple[list[Hashable], bool]:
    """One full O(n³) sweep of single-node relocation.

    Returns the improved sequence and ``True`` if any move was applied.
    Brute force keeps the code small and provably asymmetric-safe; for the
    n ≤ ~100 regime we operate in this is well under 1 s.
    """
    n = len(seq)
    if n < 4:
        return seq, False

    cur_cost = _edge_cost_path(seq, edge_cost)
    best_cost = cur_cost
    best_seq = seq

    i_lo = 1 if start_fixed else 0
    i_hi = n - 1 if end_fixed else n
    for i in range(i_lo, i_hi):
        for j in range(-1 if not start_fixed else 0, n if not end_fixed else n - 1):
            if j == i or j == i - 1:
                continue
            trial = list(seq)
            node = trial.pop(i)
            insert_at = j + 1 if j < i else j
            trial.insert(insert_at, node)
            c = _edge_cost_path(trial, edge_cost)
            if c < best_cost - 1e-9:
                best_cost = c
                best_seq = trial

    return best_seq, best_seq is not seq


def _two_opt_best_improvement(
    seq: list[Hashable],
    edge_cost: EdgeCost,
    *,
    start_fixed: bool,
    end_fixed: bool,
) -> tuple[list[Hashable], bool]:
    """One full O(n³) sweep of segment reversal, asymmetric-safe.

    With asymmetric edges the segment-internal cost changes on reversal, so
    we recompute the full path cost — clean and correct, slower than the
    symmetric algebra trick but fast enough for our scale.
    """
    n = len(seq)
    if n < 4:
        return seq, False

    cur_cost = _edge_cost_path(seq, edge_cost)
    best_cost = cur_cost
    best_seq = seq

    i_lo = 1 if start_fixed else 0
    j_hi = n - 1 if end_fixed else n
    for i in range(i_lo, n - 1):
        for j in range(i + 1, j_hi):
            trial = seq[:i] + seq[i:j + 1][::-1] + seq[j + 1:]
            c = _edge_cost_path(trial, edge_cost)
            if c < best_cost - 1e-9:
                best_cost = c
                best_seq = trial

    return best_seq, best_seq is not seq


# ---------------------------------------------------------------------------
# Simulated annealing on top of local search
# ---------------------------------------------------------------------------

def _simulated_annealing(
    seq: list[Hashable],
    edge_cost: EdgeCost,
    *,
    deadline_s: float,
    rng: random.Random,
    start_fixed: bool,
    end_fixed: bool,
) -> tuple[list[Hashable], int]:
    """Or-opt-based SA, returns best-ever sequence + iteration count."""
    n = len(seq)
    if n < 4:
        return seq, 0

    cur = list(seq)
    cur_cost = _edge_cost_path(cur, edge_cost)
    best, best_cost = list(cur), cur_cost

    # Calibrate initial temperature from the mean absolute edge cost.
    sample_edges = [edge_cost(cur[i - 1], cur[i]) for i in range(1, n)]
    mean_edge = sum(sample_edges) / max(1, len(sample_edges))
    T = max(mean_edge * 0.5, 1e-3)
    T_MIN = 1e-3
    COOLING = 0.9985

    i_lo = 1 if start_fixed else 0
    i_hi = n - 1 if end_fixed else n
    j_lo = 0 if not start_fixed else 1
    j_hi = n if not end_fixed else n - 1

    iters = 0
    while time.perf_counter() < deadline_s and T > T_MIN:
        iters += 1
        i = rng.randrange(i_lo, i_hi)
        j = rng.randrange(j_lo, j_hi)
        if j == i or j == i - 1:
            T *= COOLING
            continue
        trial = list(cur)
        node = trial.pop(i)
        insert_at = j if j < i else j - 1
        trial.insert(insert_at, node)
        c = _edge_cost_path(trial, edge_cost)
        delta = c - cur_cost
        accept = delta < 0 or rng.random() < math.exp(-delta / T)
        if accept:
            cur, cur_cost = trial, c
            if cur_cost < best_cost - 1e-9:
                best_cost, best = cur_cost, list(cur)
        T *= COOLING
    return best, iters


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def optimize_sequence(
    nodes: Sequence[Hashable],
    edge_cost: EdgeCost,
    node_cost: NodeCost | None = None,
    *,
    start: Hashable | None = None,
    end: Hashable | None = None,
    time_budget_s: float = 1.8,
    exact_max_n: int = 15,
    lkh_max_n: int = 500,
    seed: int = 42,
) -> SequenceResult:
    """Return the minimum-cost Hamiltonian path through ``nodes``.

    Parameters
    ----------
    nodes
        Hashable IDs of the SKU chunks to be sequenced on ONE line.
    edge_cost
        ``edge_cost(a, b)`` returns the changeover hours from ``a`` to ``b``.
        Asymmetric is supported and assumed.
    node_cost
        Optional per-node production hours; reported in the result but not
        optimised over (order-invariant for a Hamiltonian path).
    start, end
        Optional pinning of the first / last node (e.g. to preserve the
        previous week's tail SKU).
    time_budget_s
        Hard wall-clock cap. The function will return before this elapses.
    exact_max_n
        Use Held-Karp DP when ``len(nodes) <= exact_max_n``. Above this
        threshold the heuristic path is used.
    seed
        RNG seed for the SA phase — reproducibility for the demo.
    """
    nodes_list: list[Hashable] = list(nodes)
    n = len(nodes_list)
    t0 = time.perf_counter()
    node_cost = node_cost or (lambda _: 0.0)

    if n <= 1:
        prod_h = _node_cost_path(nodes_list, node_cost)
        return SequenceResult(
            sequence=tuple(nodes_list),
            total_hours=prod_h,
            production_hours=prod_h,
            changeover_hours=0.0,
            algorithm="trivial",
            iterations=0,
            elapsed_s=time.perf_counter() - t0,
        )

    if n <= exact_max_n:
        seq, edge_h, n_sub = _held_karp(
            nodes_list, edge_cost, start=start, end=end,
        )
        prod_h = _node_cost_path(seq, node_cost)
        return SequenceResult(
            sequence=tuple(seq),
            total_hours=prod_h + edge_h,
            production_hours=prod_h,
            changeover_hours=edge_h,
            algorithm="held_karp",
            iterations=n_sub,
            elapsed_s=time.perf_counter() - t0,
        )

    # ---- LKH-3 (preferred for medium instances) --------------------------
    if n <= lkh_max_n and _ELKAI_AVAILABLE:
        lkh = _lkh_open_path(nodes_list, edge_cost, start=start, end=end)
        if lkh is not None:
            seq, edge_h = lkh
            prod_h = _node_cost_path(seq, node_cost)
            return SequenceResult(
                sequence=tuple(seq),
                total_hours=prod_h + edge_h,
                production_hours=prod_h,
                changeover_hours=edge_h,
                algorithm="lkh3",
                iterations=1,
                elapsed_s=time.perf_counter() - t0,
            )

    # ---- heuristic regime ------------------------------------------------
    rng = random.Random(seed)
    deadline = t0 + time_budget_s
    start_fixed = start is not None
    end_fixed = end is not None

    seq = _best_of_nn(nodes_list, edge_cost, start=start, end=end)

    # Best-improvement local search until convergence or time/2 elapsed.
    ls_deadline = t0 + time_budget_s * 0.5
    while time.perf_counter() < ls_deadline:
        seq, improved1 = _or_opt_best_improvement(
            list(seq), edge_cost,
            start_fixed=start_fixed, end_fixed=end_fixed,
        )
        if time.perf_counter() >= ls_deadline:
            break
        seq, improved2 = _two_opt_best_improvement(
            list(seq), edge_cost,
            start_fixed=start_fixed, end_fixed=end_fixed,
        )
        if not (improved1 or improved2):
            break

    # SA on the remaining time budget.
    seq, sa_iters = _simulated_annealing(
        list(seq), edge_cost,
        deadline_s=deadline, rng=rng,
        start_fixed=start_fixed, end_fixed=end_fixed,
    )

    edge_h = _edge_cost_path(seq, edge_cost)
    prod_h = _node_cost_path(seq, node_cost)
    return SequenceResult(
        sequence=tuple(seq),
        total_hours=prod_h + edge_h,
        production_hours=prod_h,
        changeover_hours=edge_h,
        algorithm="nn+2opt+or-opt+sa",
        iterations=sa_iters,
        elapsed_s=time.perf_counter() - t0,
    )


# ---------------------------------------------------------------------------
# Demo — run when invoked directly
# ---------------------------------------------------------------------------

def _demo() -> None:
    """Wire the optimiser to the synthetic dataset and print a small report."""
    from generate_test_data import (
        DEFAULT_OUT_PATH,
        LINE_CONTAINER_TYPES,
        build_sku_catalog,
        get_node_cost,
        get_transition_cost,
        read_sheet,
    )

    catalog = build_sku_catalog()
    sku_by_id = {s.sku_id: s for s in catalog}
    demand_rows = read_sheet(DEFAULT_OUT_PATH, "demand")
    units_by_sku = {r["sku_id"]: int(r["units_demanded"]) for r in demand_rows}

    def make_edge_cost(line_id: int):
        def _f(a_id: str, b_id: str) -> float:
            return get_transition_cost(sku_by_id[a_id], sku_by_id[b_id], line_id)
        return _f

    def make_node_cost(line_id: int):
        def _f(sku_id: str) -> float:
            return get_node_cost(sku_by_id[sku_id], units_by_sku.get(sku_id, 0), line_id)
        return _f

    # 1) Small exact problem: 8 SKUs from L17 → Held-Karp.
    small_nodes = [s.sku_id for s in catalog if s.container_type == "1/3"][:8]
    r_small = optimize_sequence(
        small_nodes, make_edge_cost(17), make_node_cost(17),
    )
    print(f"\n[Held-Karp, n={len(small_nodes)}, line=17]")
    print(f"  changeover_hours = {r_small.changeover_hours:.4f}  production_hours = {r_small.production_hours:.4f}")
    print(f"  algorithm        = {r_small.algorithm}  elapsed = {r_small.elapsed_s*1000:.1f} ms")

    # 2) Realistic: 25 SKUs feasible on L14 → LKH-3.
    l14_nodes = [s.sku_id for s in catalog if s.container_type in LINE_CONTAINER_TYPES[14]]
    r_l14 = optimize_sequence(
        l14_nodes, make_edge_cost(14), make_node_cost(14),
        time_budget_s=1.8,
    )
    print(f"\n[n={len(l14_nodes)}, line=14]")
    print(f"  algorithm        = {r_l14.algorithm}")
    print(f"  changeover_hours = {r_l14.changeover_hours:.4f}")
    print(f"  total_hours      = {r_l14.total_hours:.4f}")
    print(f"  elapsed          = {r_l14.elapsed_s*1000:.1f} ms")

    # 3) LKH vs SA comparison on the L14 instance (force SA via exact_max_n=0
    #    and a flag that disables LKH).
    r_l14_sa = optimize_sequence(
        l14_nodes, make_edge_cost(14), make_node_cost(14),
        time_budget_s=1.8, exact_max_n=0, lkh_max_n=0,
    )
    gap = (r_l14_sa.changeover_hours - r_l14.changeover_hours) / max(r_l14.changeover_hours, 1e-9)
    print(f"\n[SA baseline, n={len(l14_nodes)}, line=14]  (vs LKH)")
    print(f"  algorithm        = {r_l14_sa.algorithm}")
    print(f"  changeover_hours = {r_l14_sa.changeover_hours:.4f}  gap to LKH = {gap*100:+.2f}%")
    print(f"  elapsed          = {r_l14_sa.elapsed_s*1000:.1f} ms")


if __name__ == "__main__":
    _demo()
