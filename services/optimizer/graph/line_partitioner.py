"""Multi-line graph partitioner — two-level algorithm (greedy + exact HK + moves).

The problem
-----------

Given a set of demand SKUs (nodes) and three production lines (L14, L17, L19),
each node :math:`v` has a line-dependent processing time :math:`p_v^{(i)}` and
each ordered pair :math:`(u, v)` has a line-dependent changeover distance
:math:`d^{(i)}(u, v)`. A line cannot run a SKU it does not support, encoded as
:math:`d^{(i)} = \\infty` (the hard ``can_produce`` gate).

For any partition :math:`(S_1, S_2, S_3)` of the SKUs onto the three lines:

.. math::

    T_i = \\sum_{v \\in S_i} p_v^{(i)} + \\mathrm{HeldKarp}(S_i, d^{(i)})

The objective is min-max:

.. math::

    \\min\\ \\max(T_1, T_2, T_3)

with an :math:`\\varepsilon`-weighted :math:`\\sum_i T_i` tie-breaker so the
solver doesn't strand a line idle when the optimum is degenerate.

Why this algorithm
------------------

Two-level decomposition:

* **Level A (partition)** — assign nodes to the three lines. This is the
  combinatorially hard part. We attack it with **local search**: start from a
  feasible greedy assignment, then iterate single-node moves and pair swaps,
  always taking the best-improvement step.
* **Level B (routing)** — for a *fixed* node set on each line, find the
  optimal tour. With ~10-12 nodes per line on the mean LineWise window, this
  is the **exact** Held-Karp regime — :math:`O(n^2 \\cdot 2^n)` DP, sub-ms
  per call. Delegated to :func:`sequence_optimizer.optimize_sequence`, which
  already routes ≤15-node subproblems through Held-Karp.

This separation is the whole point: the *global combinatorial difficulty*
(node allocation) is handled by a cheap, well-instrumented local search; each
candidate partition is then **evaluated exactly** by Held-Karp, so move
acceptance is never wrong about which option is better.

Algorithm steps
---------------

#. **Initial assignment** — constraint-aware Longest Processing Time first.
   SKUs with the fewest feasible lines are placed first (so they don't get
   crowded out); within each constrainedness class, the largest node is
   placed on the least-loaded feasible line. Guarantees a feasible starting
   point in :math:`O(n \\log n)`.

#. **Held-Karp per line** — exact TSP cost for each :math:`S_i`, giving the
   initial :math:`T_i`.

#. **Global evaluation** — compute :math:`\\max T_i + \\varepsilon \\sum T_i`
   and snapshot it as the incumbent.

#. **Improvement loop** — each iteration tries, in order:

   a. **Best single-node move** :math:`v \\in S_A \\to S_B` over every
      :math:`(v, A, B)` with :math:`v` feasible on :math:`B`. Only **two**
      Held-Karp calls per trial — the source and destination lines. If any
      move strictly reduces the objective, apply the best one.

   b. **Best pair swap** :math:`v_A \\leftrightarrow v_B` over every
      cross-line pair with both placements feasible. Same two-HK locality.

   c. **Balance-repair move** — if :math:`\\max T_i - \\min T_i > \\delta`,
      find the node on the bottleneck line whose move to the slack line gives
      the highest *makespan-reduction score*
      :math:`(T_\\max - T_\\max^{\\text{after}}) - (T_\\min^{\\text{after}} - T_\\min)`.
      Applied only when steps a and b both find nothing — it's the
      tie-breaker that prevents idle lines.

   The loop terminates when no improvement is found, or the iteration /
   wall-clock budget runs out.

#. **Snapshot the incumbent** — return the best :math:`(T_i)` seen, not the
   last one (the loop never accepts a worsening move, so these coincide in
   practice; the explicit snapshot is a defensive checkpoint).

Incremental Held-Karp
---------------------

Per the user's design constraint ("recalculate ONLY 2 Held-Karp"), each move
trial recomputes only the two lines it touches. The third line's
:math:`T_i` is reused verbatim. A small ``(line, frozenset(skus)) -> result``
cache further amortises HK calls that recur across iterations (common during
swap evaluation: line A loses node :math:`u` and gains node :math:`v`,
then a sibling trial swaps the same :math:`u` back in).

Decoupling
----------

The partitioner imports nothing from :mod:`generate_test_data` directly.
It takes three callables — ``can_produce(sku, line)``, ``edge_cost(a, b,
line)``, ``node_cost(sku, line)`` — that close over whatever cost model is
plugged in (the synthetic one, the ETL-backed real one, or a future ML edge
predictor). The graph itself is *given* to this module; only Level A is its
responsibility, Level B is delegated, and graph construction lives elsewhere.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Hashable, Literal, Mapping, Sequence, TYPE_CHECKING

from sequence_optimizer import optimize_sequence

if TYPE_CHECKING:
    import networkx as nx

LineId = int  # narrowed to {14, 17, 19} in practice, kept open here
SkuId = Hashable


# ---------------------------------------------------------------------------
# Callable contracts (unchanged — public API)
# ---------------------------------------------------------------------------

CanProduce = Callable[[SkuId, LineId], bool]
"""Hard gate: ``True`` iff ``sku`` can run on ``line``. Mirrors
:attr:`packages.contracts.module.schemas.LineCapability.can_produce`."""

EdgeCost = Callable[[SkuId, SkuId, LineId], float]
"""Changeover hours from ``sku_a`` to ``sku_b`` on ``line``. Per-line so the
real ML predictor drops in unchanged."""

NodeCost = Callable[[SkuId, LineId], float]
"""Production hours of ``sku`` on ``line`` for the relevant demand."""


# ---------------------------------------------------------------------------
# Result dataclass (unchanged — preserves visualize_graph / contract shape)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PartitionResult:
    """Output of :func:`partition_lines`. Mirrors
    :class:`packages.contracts.module.schemas.OptimizerOutput` on every
    headline field; sequence-of-Slots materialisation (timestamps, slot IDs,
    slot types) waits for the calendar layer."""

    sequences: dict[LineId, tuple[SkuId, ...]]
    makespan_per_line_hours: dict[LineId, float]
    makespan_hours: float
    total_hours: float
    production_hours_per_line: dict[LineId, float]
    changeover_hours_per_line: dict[LineId, float]
    dropped: tuple[tuple[SkuId, int], ...]
    solver_log: str | None
    iterations: int
    elapsed_s: float

    @property
    def feasible(self) -> bool:
        return len(self.dropped) == 0


# ---------------------------------------------------------------------------
# Internal search state
# ---------------------------------------------------------------------------

@dataclass
class _LineSnapshot:
    """Immutable-ish snapshot of one line's routing result."""

    sequence: tuple[SkuId, ...]
    production_h: float
    changeover_h: float

    @property
    def T(self) -> float:
        return self.production_h + self.changeover_h


_HKKey = tuple[LineId, frozenset]


class _Search:
    """Encapsulates the partition search state + HK cache.

    The state is the current per-line snapshot. Moves return a *trial* dict
    of new snapshots without mutating the search; only :meth:`apply` commits.
    """

    __slots__ = (
        "line_ids", "can_produce", "edge_cost", "node_cost",
        "sequence_budget_s", "seed", "eps",
        "lines", "unassigned",
        "_hk_cache", "_hk_calls", "_hk_hits",
    )

    def __init__(
        self,
        line_ids: tuple[LineId, ...],
        can_produce: CanProduce,
        edge_cost: EdgeCost,
        node_cost: NodeCost,
        *,
        sequence_budget_s: float,
        seed: int,
        eps: float,
    ) -> None:
        self.line_ids = line_ids
        self.can_produce = can_produce
        self.edge_cost = edge_cost
        self.node_cost = node_cost
        self.sequence_budget_s = sequence_budget_s
        self.seed = seed
        self.eps = eps
        self.lines: dict[LineId, _LineSnapshot] = {}
        self.unassigned: list[SkuId] = []
        self._hk_cache: dict[_HKKey, _LineSnapshot] = {}
        self._hk_calls = 0
        self._hk_hits = 0

    # -- exact per-line routing --------------------------------------------

    def hk(self, line: LineId, skus: Sequence[SkuId]) -> _LineSnapshot:
        """Held-Karp on ``line`` for the given SKU set, cached.

        The cache key is ``(line, frozenset(skus))`` — order-independent
        because HK returns the optimal order regardless of input order.
        Empty sets short-circuit to the zero snapshot.
        """
        self._hk_calls += 1
        if not skus:
            return _LineSnapshot(sequence=(), production_h=0.0, changeover_h=0.0)
        key: _HKKey = (line, frozenset(skus))
        hit = self._hk_cache.get(key)
        if hit is not None:
            self._hk_hits += 1
            return hit

        def ec(a: SkuId, b: SkuId) -> float:
            return self.edge_cost(a, b, line)

        def nc(s: SkuId) -> float:
            return self.node_cost(s, line)

        r = optimize_sequence(
            list(skus), ec, nc,
            time_budget_s=self.sequence_budget_s, seed=self.seed,
        )
        snap = _LineSnapshot(
            sequence=r.sequence,
            production_h=r.production_hours,
            changeover_h=r.changeover_hours,
        )
        self._hk_cache[key] = snap
        return snap

    # -- objective ----------------------------------------------------------

    def objective(self, lines: Mapping[LineId, _LineSnapshot] | None = None) -> float:
        snaps = lines if lines is not None else self.lines
        loads = [snaps[l].T for l in self.line_ids]
        return max(loads) + self.eps * sum(loads)

    def makespan(self, lines: Mapping[LineId, _LineSnapshot] | None = None) -> float:
        snaps = lines if lines is not None else self.lines
        return max(snaps[l].T for l in self.line_ids)

    # -- trial-state builder ------------------------------------------------

    def _trial_after_move(
        self, from_line: LineId, sku: SkuId, to_line: LineId,
    ) -> dict[LineId, _LineSnapshot] | None:
        """Return a *new* per-line snapshot dict after moving ``sku``.

        ``None`` if the move is infeasible (capability gate). The two
        affected lines run HK; every other line is reused by reference."""
        if from_line == to_line:
            return None
        if not self.can_produce(sku, to_line):
            return None
        if sku not in self.lines[from_line].sequence:
            return None
        new_from_set = [s for s in self.lines[from_line].sequence if s != sku]
        new_to_set = list(self.lines[to_line].sequence) + [sku]
        new_from = self.hk(from_line, new_from_set)
        new_to = self.hk(to_line, new_to_set)
        return {
            **self.lines,
            from_line: new_from,
            to_line: new_to,
        }

    def _trial_after_swap(
        self, line_a: LineId, sku_a: SkuId, line_b: LineId, sku_b: SkuId,
    ) -> dict[LineId, _LineSnapshot] | None:
        """Return a *new* per-line snapshot dict after swapping two SKUs.

        ``None`` if the swap is infeasible."""
        if line_a == line_b:
            return None
        if not self.can_produce(sku_a, line_b):
            return None
        if not self.can_produce(sku_b, line_a):
            return None
        if sku_a not in self.lines[line_a].sequence:
            return None
        if sku_b not in self.lines[line_b].sequence:
            return None
        new_a_set = [s for s in self.lines[line_a].sequence if s != sku_a] + [sku_b]
        new_b_set = [s for s in self.lines[line_b].sequence if s != sku_b] + [sku_a]
        new_a = self.hk(line_a, new_a_set)
        new_b = self.hk(line_b, new_b_set)
        return {
            **self.lines,
            line_a: new_a,
            line_b: new_b,
        }

    def apply(self, new_lines: Mapping[LineId, _LineSnapshot]) -> None:
        self.lines = dict(new_lines)

    # -- move ordering ------------------------------------------------------

    def _lines_by_load_desc(self) -> tuple[LineId, ...]:
        """Lines ranked by current load, heaviest first. Moves *from* heavy
        lines are by far the most likely to reduce makespan, so scanning
        them first lets first-improvement converge much faster and lets
        best-improvement prune harder via the ``best_delta`` watermark."""
        return tuple(sorted(self.line_ids, key=lambda l: -self.lines[l].T))

    def _skus_by_node_cost_desc(self, line: LineId) -> tuple[SkuId, ...]:
        """SKUs on ``line`` ranked by their own production cost on this line,
        heaviest first. Moving the biggest contributor off the bottleneck
        line shrinks T_max the most per attempt."""
        seq = self.lines[line].sequence
        return tuple(sorted(seq, key=lambda s: -self.node_cost(s, line)))

    # -- move search --------------------------------------------------------

    def best_single_move(
        self, *, strategy: str = "best_improvement",
        deadline: float | None = None,
    ) -> tuple[float, dict[LineId, _LineSnapshot]] | None:
        """Return ``(delta, new_lines)`` for an improving move.

        ``strategy="best_improvement"`` scans every feasible move and returns
        the one with the largest ``delta``. ``strategy="first_improvement"``
        returns the first move whose ``delta > 0`` under the load-aware scan
        order (bottleneck line first, biggest SKU first). The latter is
        roughly an order of magnitude faster per iteration; both eventually
        converge, but to potentially different local optima.

        ``deadline`` (``perf_counter()`` timestamp) interrupts the scan when
        exceeded; the best move *found so far* is returned (or ``None`` if
        nothing improved yet). This is how ``time_budget_s`` enforces a hard
        cap on best-improvement scans that would otherwise blow past it on
        large windows (e.g. n=45 with HK ~60 ms × ~270 trials = ~16 s)."""
        current_obj = self.objective()
        best_delta = 1e-9
        best_state: dict[LineId, _LineSnapshot] | None = None
        from_lines = self._lines_by_load_desc()
        for from_l in from_lines:
            for sku in self._skus_by_node_cost_desc(from_l):
                if deadline is not None and time.perf_counter() >= deadline:
                    return (best_delta, best_state) if best_state else None
                for to_l in reversed(from_lines):
                    if to_l == from_l:
                        continue
                    trial = self._trial_after_move(from_l, sku, to_l)
                    if trial is None:
                        continue
                    delta = current_obj - self.objective(trial)
                    if delta > best_delta:
                        best_delta = delta
                        best_state = trial
                        if strategy == "first_improvement":
                            return best_delta, best_state
        if best_state is None:
            return None
        return best_delta, best_state

    def best_swap(
        self, *, strategy: str = "best_improvement",
        deadline: float | None = None,
    ) -> tuple[float, dict[LineId, _LineSnapshot]] | None:
        """Return ``(delta, new_lines)`` for an improving swap.

        Same ``strategy`` and ``deadline`` semantics as
        :meth:`best_single_move`. Swaps are evaluated heavy-pair first (the
        two lines with the largest |ΔT|), and within each pair the biggest
        SKUs first."""
        current_obj = self.objective()
        best_delta = 1e-9
        best_state: dict[LineId, _LineSnapshot] | None = None
        ranked = self._lines_by_load_desc()
        for i, line_a in enumerate(ranked):
            for line_b in ranked[i + 1:]:
                for sku_a in self._skus_by_node_cost_desc(line_a):
                    if deadline is not None and time.perf_counter() >= deadline:
                        return (best_delta, best_state) if best_state else None
                    if not self.can_produce(sku_a, line_b):
                        continue
                    for sku_b in self._skus_by_node_cost_desc(line_b):
                        if not self.can_produce(sku_b, line_a):
                            continue
                        trial = self._trial_after_swap(line_a, sku_a, line_b, sku_b)
                        if trial is None:
                            continue
                        delta = current_obj - self.objective(trial)
                        if delta > best_delta:
                            best_delta = delta
                            best_state = trial
                            if strategy == "first_improvement":
                                return best_delta, best_state
        if best_state is None:
            return None
        return best_delta, best_state

    def best_balance_move(
        self, delta_balance_h: float,
    ) -> tuple[float, dict[LineId, _LineSnapshot]] | None:
        """Balance repair: if ``max T_i − min T_i > delta_balance_h``, find
        the best node on the bottleneck line to ship to the slack line.

        Score = ``(T_max − T_max_after) − (T_min_after − T_min)``. Positive
        means the makespan reduces by more than the slack line grows.

        Accepts the move iff the global objective strictly improves (we never
        let the balance repair worsen the overall solution — that would
        defeat the search).
        """
        loads = {l: self.lines[l].T for l in self.line_ids}
        l_max = max(loads, key=loads.get)
        l_min = min(loads, key=loads.get)
        if loads[l_max] - loads[l_min] <= delta_balance_h:
            return None
        current_obj = self.objective()
        best_score = -float("inf")
        best_state: dict[LineId, _LineSnapshot] | None = None
        best_delta = 0.0
        for sku in list(self.lines[l_max].sequence):
            if not self.can_produce(sku, l_min):
                continue
            trial = self._trial_after_move(l_max, sku, l_min)
            if trial is None:
                continue
            t_max_after = trial[l_max].T
            t_min_after = trial[l_min].T
            score = (loads[l_max] - t_max_after) - (t_min_after - loads[l_min])
            new_obj = self.objective(trial)
            delta = current_obj - new_obj
            # Pick the highest score that also strictly improves the objective.
            if score > best_score and delta > 1e-9:
                best_score = score
                best_state = trial
                best_delta = delta
        if best_state is None:
            return None
        return best_delta, best_state

    # -- diagnostics --------------------------------------------------------

    @property
    def cache_hit_rate(self) -> float:
        return self._hk_hits / self._hk_calls if self._hk_calls else 0.0


# ---------------------------------------------------------------------------
# Initial assignment — constraint-aware LPT
# ---------------------------------------------------------------------------

def _initial_assignment(
    sku_ids: Sequence[SkuId],
    line_ids: Sequence[LineId],
    can_produce: CanProduce,
    node_cost: NodeCost,
) -> tuple[dict[LineId, list[SkuId]], list[SkuId]]:
    """Constraint-aware Longest Processing Time first.

    Sort by (n_feasible_lines ASC, max_node_cost DESC) so:

    * The most-constrained SKUs (one feasible line) get placed first — they
      have no choice and would otherwise be crowded out.
    * Within each constrainedness class, the largest SKUs go down first so
      the small ones can fill the remaining gaps. This is the classic LPT
      bound for makespan scheduling.

    Each SKU lands on the feasible line that minimises *load after
    insertion* (load = sum of node costs so far). Changeovers are added at
    the routing step — this is the production-only greedy that supplies HK
    with a balanced starting set.
    """
    feasible_by_sku: dict[SkuId, list[LineId]] = {
        s: [l for l in line_ids if can_produce(s, l)] for s in sku_ids
    }

    def sort_key(s: SkuId) -> tuple[int, float]:
        feas = feasible_by_sku[s]
        max_prod = -max((node_cost(s, l) for l in feas), default=0.0)
        return (len(feas), max_prod)

    ordered = sorted(sku_ids, key=sort_key)
    assignments: dict[LineId, list[SkuId]] = {l: [] for l in line_ids}
    loads: dict[LineId, float] = {l: 0.0 for l in line_ids}
    unassigned: list[SkuId] = []

    for s in ordered:
        feas = feasible_by_sku[s]
        if not feas:
            unassigned.append(s)
            continue
        best = min(feas, key=lambda l: loads[l] + node_cost(s, l))
        assignments[best].append(s)
        loads[best] += node_cost(s, best)

    return assignments, unassigned


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def partition_lines(
    sku_ids: Sequence[SkuId],
    line_ids: Sequence[LineId],
    can_produce: CanProduce,
    edge_cost: EdgeCost,
    node_cost: NodeCost,
    *,
    units_by_sku: Mapping[SkuId, int] | None = None,
    seed: int = 42,
    time_budget_s: float = 5.0,
    sequence_budget_s: float = 0.05,
    eps: float = 1e-3,
    delta_balance_h: float = 0.5,
    max_iterations: int = 500,
    max_no_improve: int = 50,
    move_strategy: str = "best_improvement",
) -> PartitionResult:
    """Partition ``sku_ids`` across ``line_ids`` to minimise the makespan.

    Two-level algorithm: constraint-aware LPT initial assignment, then exact
    Held-Karp per line on every trial, with best-improvement single-node
    moves, best-improvement swaps, and a balance-repair step when the load
    spread exceeds ``delta_balance_h``.

    Parameters tunable by the grid-search step
    ------------------------------------------

    ``time_budget_s``
        Hard wall-clock cap on the improvement loop. Initial assignment +
        first HK round is *not* counted — they always run.
    ``sequence_budget_s``
        Per-call budget passed to :func:`optimize_sequence`. With ~10-12
        nodes per line, Held-Karp finishes in sub-millisecond regardless,
        so 0.05 s is comfortable headroom.
    ``eps``
        Tie-breaker coefficient on :math:`\\sum T_i`. Small enough that
        makespan dominates, large enough to disambiguate between solutions
        with equal makespan. Default ``1e-3`` — picked by the grid search
        (``grid_search.py``) as the Pareto-knee value: same makespan as
        ``1e-4``, slightly stronger total-time tie-breaker so balance-repair
        gets cleaner signal.
    ``delta_balance_h``
        Load-spread threshold that triggers the balance-repair move when
        single moves and swaps both stall. Default ``0.5`` — picked by the
        grid search as the Pareto-knee value: lower threshold means
        balance-repair triggers more aggressively when the search hits a
        local plateau, costing one extra HK pair per iteration but cleaning
        up small load imbalances the move search misses.
    ``max_iterations`` / ``max_no_improve``
        Hard caps so the loop always terminates even if local minima
        oscillate (in practice convergence is reached in <50 iters on the
        mean LineWise window).
    ``move_strategy``
        ``"best_improvement"`` (default) — scan all candidates per iteration
        and accept the move with the largest ``delta``. Highest per-iteration
        quality, slowest. ``"first_improvement"`` — accept the first move
        whose ``delta > 0`` under the load-aware scan order (bottleneck line
        first, biggest SKU first). ~5-10× faster per iteration on the mean
        LineWise window; reaches similar solutions in a few more iterations.
    ``units_by_sku``
        Optional ``{sku_id: units_demanded}`` lookup. Forwarded into
        :attr:`PartitionResult.dropped` so the contract semantics match
        :attr:`OptimizerOutput.dropped` (``(sku_id, units_not_produced)``).
    """
    t0 = time.perf_counter()
    line_ids_t = tuple(line_ids)

    # ---- Step 1: constraint-aware LPT initial assignment -----------------
    assignments, unassigned = _initial_assignment(
        sku_ids, line_ids_t, can_produce, node_cost,
    )

    # ---- Step 2: exact Held-Karp per line --------------------------------
    search = _Search(
        line_ids=line_ids_t,
        can_produce=can_produce,
        edge_cost=edge_cost,
        node_cost=node_cost,
        sequence_budget_s=sequence_budget_s,
        seed=seed,
        eps=eps,
    )
    search.unassigned = list(unassigned)
    search.lines = {l: search.hk(l, assignments[l]) for l in line_ids_t}
    initial_obj = search.objective()
    initial_makespan = search.makespan()

    # ---- Step 3: snapshot the incumbent ---------------------------------
    best_lines = dict(search.lines)
    best_obj = initial_obj

    # ---- Step 4: improvement loop ---------------------------------------
    iterations = 0
    no_improve = 0
    trace: list[tuple[str, float, float]] = []  # (action, objective, makespan)
    trace.append(("init", initial_obj, initial_makespan))

    deadline = t0 + time_budget_s
    while iterations < max_iterations and no_improve < max_no_improve:
        if time.perf_counter() >= deadline:
            trace.append(("timeout", search.objective(), search.makespan()))
            break
        iterations += 1

        # 4a) single-node move (best- or first-improvement per strategy)
        move = search.best_single_move(strategy=move_strategy, deadline=deadline)
        if move is not None:
            _, new_lines = move
            search.apply(new_lines)
            if search.objective() < best_obj - 1e-9:
                best_obj = search.objective()
                best_lines = dict(search.lines)
                no_improve = 0
                trace.append(("move", best_obj, search.makespan()))
            else:
                no_improve += 1
            continue

        # 4b) pair swap (same strategy)
        swap = search.best_swap(strategy=move_strategy, deadline=deadline)
        if swap is not None:
            _, new_lines = swap
            search.apply(new_lines)
            if search.objective() < best_obj - 1e-9:
                best_obj = search.objective()
                best_lines = dict(search.lines)
                no_improve = 0
                trace.append(("swap", best_obj, search.makespan()))
            else:
                no_improve += 1
            continue

        # 4c) balance-repair move (only if load is unbalanced)
        repair = search.best_balance_move(delta_balance_h)
        if repair is not None:
            _, new_lines = repair
            search.apply(new_lines)
            if search.objective() < best_obj - 1e-9:
                best_obj = search.objective()
                best_lines = dict(search.lines)
                no_improve = 0
                trace.append(("balance", best_obj, search.makespan()))
            else:
                no_improve += 1
            continue

        # 4d) no improvement found anywhere — converged.
        trace.append(("converged", best_obj, search.makespan(best_lines)))
        break

    # ---- Step 5: package the incumbent into PartitionResult --------------
    elapsed = time.perf_counter() - t0
    makespan_per_line = {l: best_lines[l].T for l in line_ids_t}
    units_lookup = dict(units_by_sku) if units_by_sku is not None else {}
    dropped = tuple(
        (sku, int(units_lookup.get(sku, 0))) for sku in search.unassigned
    )

    # Solver log mirrors OptimizerOutput.solver_log shape.
    final_makespan = max(makespan_per_line.values())
    delta_h = initial_makespan - final_makespan
    pct = (delta_h / initial_makespan * 100.0) if initial_makespan else 0.0
    move_steps = sum(1 for a, _, _ in trace if a == "move")
    swap_steps = sum(1 for a, _, _ in trace if a == "swap")
    bal_steps = sum(1 for a, _, _ in trace if a == "balance")
    log = (
        f"Two-Level (Greedy + HK + Best-Improvement) | "
        f"{iterations} iterations | {elapsed:.2f}s\n"
        f"  initial makespan  : {initial_makespan:7.2f} h   (objective {initial_obj:.4f})\n"
        f"  final   makespan  : {final_makespan:7.2f} h   (objective {best_obj:.4f})\n"
        f"  improvement       : {delta_h:7.2f} h  ({pct:+.1f}%)\n"
        f"  moves accepted    : single={move_steps}  swap={swap_steps}  balance={bal_steps}\n"
        f"  HK calls / cached : {search._hk_calls} / {search._hk_hits} "
        f"({search.cache_hit_rate * 100:.1f}% hit rate)\n"
        f"  init heuristic    : constraint-aware LPT\n"
        f"  routing per line  : Held-Karp via sequence_optimizer (exact, n<=15)\n"
        f"  delta_balance     : {delta_balance_h:.2f} h\n"
        f"  move strategy     : {move_strategy}\n"
        f"  eps tie-breaker   : {eps:g}"
    )

    return PartitionResult(
        sequences={l: best_lines[l].sequence for l in line_ids_t},
        makespan_per_line_hours=makespan_per_line,
        makespan_hours=final_makespan,
        total_hours=sum(makespan_per_line.values()),
        production_hours_per_line={l: best_lines[l].production_h for l in line_ids_t},
        changeover_hours_per_line={l: best_lines[l].changeover_h for l in line_ids_t},
        dropped=dropped,
        solver_log=log,
        iterations=iterations,
        elapsed_s=elapsed,
    )


# ---------------------------------------------------------------------------
# Verification — sanity-check the returned partition against the objective
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class VerificationReport:
    """Independent recomputation of the objective from the sequences."""

    sku_count_ok: bool
    capability_ok: bool
    makespan_recomputed_h: float
    total_recomputed_h: float
    spread_h: float
    objective_value: float          # makespan + eps · total
    matches_reported: bool
    notes: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return self.sku_count_ok and self.capability_ok and self.matches_reported


def verify_partition(
    result: PartitionResult,
    sku_ids: Sequence[SkuId],
    can_produce: CanProduce,
    edge_cost: EdgeCost,
    node_cost: NodeCost,
    *,
    eps: float = 1e-4,
    tolerance_h: float = 1e-3,
) -> VerificationReport:
    """Recompute the objective from the returned sequences and confirm it
    matches what :func:`partition_lines` reported.

    Checks:

    1. Every input SKU appears in exactly one line's sequence (or in
       ``dropped``) — no duplicates, no losses.
    2. Every placed SKU passes the ``can_produce`` gate.
    3. ``production_h = Σ node_cost(s, line)`` on each line.
    4. ``changeover_h = Σ edge_cost(seq[i-1], seq[i], line)`` on each line.
    5. ``makespan = max_ℓ (production_h + changeover_h)``.
    6. The recomputed makespan matches ``result.makespan_hours`` to
       ``tolerance_h``.
    """
    notes: list[str] = []
    sku_set = set(sku_ids)

    # 1) every input SKU placed exactly once (or dropped).
    placed = [s for seq in result.sequences.values() for s in seq]
    placed_set = set(placed)
    dropped_set = {sku for sku, _units in result.dropped}
    duplicates = len(placed) - len(placed_set)
    missing = sku_set - placed_set - dropped_set
    extras = placed_set - sku_set
    sku_count_ok = (
        duplicates == 0 and not missing and not extras
        and not (placed_set & dropped_set)
    )
    if duplicates:
        notes.append(f"{duplicates} duplicated SKUs across lines")
    if missing:
        notes.append(f"{len(missing)} SKUs disappeared: {sorted(missing)[:3]}…")
    if extras:
        notes.append(f"{len(extras)} unknown SKUs in output: {sorted(extras)[:3]}…")

    # 2) capability gate.
    capability_ok = True
    for line, seq in result.sequences.items():
        for s in seq:
            if not can_produce(s, line):
                capability_ok = False
                notes.append(f"capability violation: {s} on L{line}")
                break

    # 3-5) recompute loads from the sequences.
    makespan = 0.0
    total = 0.0
    for line, seq in result.sequences.items():
        prod = sum(node_cost(s, line) for s in seq)
        chg = sum(edge_cost(seq[i - 1], seq[i], line) for i in range(1, len(seq)))
        load = prod + chg
        total += load
        if load > makespan:
            makespan = load
    spread = makespan - min(
        result.makespan_per_line_hours.values(), default=makespan,
    ) if result.makespan_per_line_hours else 0.0

    # 6) reported vs recomputed.
    diff = abs(makespan - result.makespan_hours)
    matches_reported = diff <= tolerance_h
    if not matches_reported:
        notes.append(
            f"makespan mismatch: reported={result.makespan_hours:.4f}h, "
            f"recomputed={makespan:.4f}h, |Δ|={diff:.4f}h"
        )

    return VerificationReport(
        sku_count_ok=sku_count_ok,
        capability_ok=capability_ok,
        makespan_recomputed_h=round(makespan, 4),
        total_recomputed_h=round(total, 4),
        spread_h=round(spread, 4),
        objective_value=round(makespan + eps * total, 4),
        matches_reported=matches_reported,
        notes=tuple(notes),
    )


# ---------------------------------------------------------------------------
# Graph adapter — consume the canonical planning graph from graph_builder
# ---------------------------------------------------------------------------

# Fallback edge cost when (a, b, line) is missing from the MultiDiGraph.
# Should be rare — graph_builder.build_planning_graph emits an edge for every
# (sku_from, sku_to, line) triple present in ``changeover_costs.csv`` whose
# endpoints are both capable on ``line``. Kept as a finite penalty so a stray
# lookup during local-search trials never crashes the partitioner.
_MISSING_EDGE_HOURS: float = 8.0


def partition_from_graph(
    graph: "nx.MultiDiGraph",
    *,
    line_ids: Sequence[LineId] | None = None,
    **kwargs: Any,
) -> PartitionResult:
    """Run the two-level partitioner on a planning graph from ``graph_builder``.

    Adapter over :func:`partition_lines` that turns the canonical graph object
    produced by
    :func:`services.optimizer.app.graph_builder.build_planning_graph` into the
    three callables the search needs:

    * ``can_produce(sku, line) = line in graph.nodes[sku]["line_data"]``
      — matches the hard ``line_capability.csv`` gate that ``graph_builder``
      applies before adding ``line_data`` entries.
    * ``node_cost(sku, line) = graph.nodes[sku]["line_data"][line]["predicted_hours"]``
      — already precomputed by the CatBoost ``node_cost_ml`` inference inside
      ``graph_builder``; we never re-call the model here.
    * ``edge_cost(a, b, line) = graph[a][b][line]["hours"]``
      — the per-line theoretical changeover from ``changeover_costs.csv``
      (sourced from Tabla CF Prat). Missing triples fall back to
      :data:`_MISSING_EDGE_HOURS` so the search arithmetic stays finite even
      if a swap trial probes a pair the matrix doesn't enumerate.

    Parameters
    ----------
    graph
        :class:`networkx.MultiDiGraph` returned by
        :func:`build_planning_graph`. Node attribute ``units_demanded`` is
        forwarded as ``units_by_sku`` so ``PartitionResult.dropped`` carries
        the contract-shaped ``(sku_id, units_not_produced)`` tuples.
    line_ids
        Optional override; by default the function uses whatever line IDs
        appear in any node's ``line_data`` (in sorted order). For LineWise
        this is always ``(14, 17, 19)``.
    kwargs
        Forwarded verbatim to :func:`partition_lines` (``time_budget_s``,
        ``move_strategy``, ``delta_balance_h``, ``eps``, …).

    Returns
    -------
    :class:`PartitionResult` — exact same shape as the synthetic-path call,
    so :func:`verify_partition` and the visualiser consume it identically.
    """
    sku_ids = list(graph.nodes)
    units_by_sku = {
        s: int(graph.nodes[s].get("units_demanded", 0)) for s in sku_ids
    }

    if line_ids is None:
        collected: set[LineId] = set()
        for s in sku_ids:
            collected.update(graph.nodes[s].get("line_data", {}).keys())
        line_ids = tuple(sorted(collected))

    def can_produce(sku: SkuId, line: LineId) -> bool:
        return line in graph.nodes[sku].get("line_data", {})

    def node_cost(sku: SkuId, line: LineId) -> float:
        ld = graph.nodes[sku].get("line_data", {}).get(line)
        if ld is None:
            # Should never be reached because the partitioner gates on
            # can_produce first; a finite value keeps arithmetic safe if it is.
            return _MISSING_EDGE_HOURS
        return float(ld["predicted_hours"])

    def edge_cost(a: SkuId, b: SkuId, line: LineId) -> float:
        if a == b:
            return 0.0
        d = graph.get_edge_data(a, b, key=line)
        if d is None:
            return _MISSING_EDGE_HOURS
        return float(d["hours"])

    return partition_lines(
        sku_ids,
        line_ids,
        can_produce,
        edge_cost,
        node_cost,
        units_by_sku=units_by_sku,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Demo — run when invoked directly
# ---------------------------------------------------------------------------

def _demo() -> None:
    """Wire the partitioner to the **real** ``data/clean`` CSVs and print a
    report. Falls back to the synthetic dataset if the real data is missing."""
    try:
        from real_data_loader import (
            LINE_IDS,
            can_produce,
            get_node_cost as _real_node_cost,
            get_transition_cost as _real_edge_cost,
            load_window_dataset,
        )
        ds = load_window_dataset()
        sku_ids = list(ds.sku_ids)
        units_by_sku = dict(ds.units_by_sku)

        def edge_cost(a_id: str, b_id: str, line_id: int) -> float:
            return _real_edge_cost(a_id, b_id, line_id)

        def node_cost(sku_id: str, line_id: int) -> float:
            return _real_node_cost(sku_id, ds.units_by_sku[sku_id], line_id)

        print(f"[partitioner demo] real window={ds.window_id}  n_skus={len(sku_ids)}")
    except (FileNotFoundError, ImportError):
        from generate_test_data import (
            DEFAULT_OUT_PATH, LINE_CONTAINER_TYPES, LINE_IDS,
            build_sku_catalog, get_node_cost as _syn_node_cost,
            get_transition_cost as _syn_edge_cost, read_sheet,
        )
        catalog = build_sku_catalog()
        sku_by_id = {s.sku_id: s for s in catalog}
        demand_rows = read_sheet(DEFAULT_OUT_PATH, "demand")
        units_by_sku = {r["sku_id"]: int(r["units_demanded"]) for r in demand_rows}

        def can_produce(sku_id: str, line_id: int) -> bool:  # type: ignore[no-redef]
            return sku_by_id[sku_id].container_type in LINE_CONTAINER_TYPES[line_id]

        def edge_cost(a_id: str, b_id: str, line_id: int) -> float:
            return _syn_edge_cost(sku_by_id[a_id], sku_by_id[b_id], line_id)

        def node_cost(sku_id: str, line_id: int) -> float:
            return _syn_node_cost(sku_by_id[sku_id], units_by_sku[sku_id], line_id)

        sku_ids = [s.sku_id for s in catalog]
        print(f"[partitioner demo] SYNTHETIC fallback  n_skus={len(sku_ids)}")

    result = partition_lines(
        sku_ids, list(LINE_IDS), can_produce, edge_cost, node_cost,
        units_by_sku=units_by_sku,
        time_budget_s=4.0,
        sequence_budget_s=0.05,
        # Pareto-knee hyperparameters from grid_search.py
        delta_balance_h=0.5,
        eps=1e-3,
        move_strategy="best_improvement",
        max_iterations=500,
        max_no_improve=50,
    )

    print(f"\n=== Partition result ({len(sku_ids)} SKUs across {len(LINE_IDS)} lines) ===")
    for line_id in LINE_IDS:
        seq = result.sequences[line_id]
        prod = result.production_hours_per_line[line_id]
        chg = result.changeover_hours_per_line[line_id]
        load = result.makespan_per_line_hours[line_id]
        head = " -> ".join(str(s) for s in seq[:4])
        tail = str(seq[-1]) if seq else "(empty)"
        print(
            f"  L{line_id}: n={len(seq):2d}  "
            f"prod={prod:6.2f}h  chg={chg:5.2f}h  load={load:6.2f}h  "
            f"seq={head}{' -> ... -> ' + tail if len(seq) > 4 else ''}"
        )

    spread = result.makespan_hours - min(result.makespan_per_line_hours.values())
    print(f"\n  makespan          = {result.makespan_hours:7.2f} h  (max over lines)")
    print(f"  total work        = {result.total_hours:7.2f} h  (sum)")
    print(f"  spread (max-min)  = {spread:7.2f} h  (lower is better balance)")
    print(f"  dropped SKUs      = {len(result.dropped)}  feasible = {result.feasible}")
    print(f"  iterations        = {result.iterations}")
    print(f"  elapsed           = {result.elapsed_s*1000:6.0f} ms")

    # Objective alignment check.
    report = verify_partition(
        result, sku_ids, can_produce, edge_cost, node_cost, eps=1e-4,
    )
    print(
        "\n  --- objective alignment check ---"
        f"\n  every SKU placed once    : {'OK' if report.sku_count_ok else 'FAIL'}"
        f"\n  capability gate honoured : {'OK' if report.capability_ok else 'FAIL'}"
        f"\n  makespan reported        : {result.makespan_hours:7.4f} h"
        f"\n  makespan recomputed      : {report.makespan_recomputed_h:7.4f} h"
        f"\n  reported == recomputed   : {'OK' if report.matches_reported else 'FAIL'}"
        f"\n  objective (makespan+eps*sum) : {report.objective_value:.4f}"
    )
    if report.notes:
        print("  notes:")
        for n in report.notes:
            print(f"   - {n}")
    print("\n  --- solver log ---")
    for line in (result.solver_log or "").splitlines():
        print(f"  {line}")
    if not report.ok:
        raise SystemExit(2)


if __name__ == "__main__":
    _demo()
