"""What-if scenario: a line breaks down mid-week and needs maintenance.

Scenario
--------

While the optimised weekly plan is executing on the three Damm lines, a
machine on line ``L`` fails at wall-clock time ``T_b`` (hours into the
plan). The line is dead for ``maintenance_hours``; afterwards it resumes
but cannot pick up where it left off (the SKU in flight when the machine
broke must be redone). We want to know: **what is the best plan from
this moment forward?**

Approach
--------

The graph is unchanged. We reuse :func:`line_partitioner.partition_lines`
without modification, and feed it a *residual* problem:

1. **Snapshot at ``T_b``.** Walk each line's original sequence and
   accumulate ``prod + changeover`` cumulatively.

   * On a **non-affected** line, a SKU is *committed* if it has already
     started by ``T_b`` — it continues to completion uninterrupted.
   * On the **affected** line, a SKU is *committed* only if it finished
     strictly before ``T_b``. Anything in-flight when the machine fails
     is aborted and goes back into the residual pool.

2. **Per-line baseline** (idle / locked-in hours the new plan starts with):

   * Non-affected line: end-time of its last committed SKU.
   * Affected line: ``T_b + maintenance_hours`` (line is dead until the
     breakdown moment plus the repair). After maintenance the affected
     line restarts on whatever the new plan assigns it.

3. **Phantom baseline nodes.** For each line we add one synthetic node
   to the residual SKU pool whose ``node_cost`` equals that line's
   baseline, that can only be placed on its own line, and whose edge
   cost to/from anything is zero. This makes
   :func:`line_partitioner.partition_lines` see the baseline as a
   per-line load tax — SKUs naturally migrate off the overloaded
   (broken) line until the makespan rebalances. Because the phantom's
   edges are zero, the per-line ATSP (Held-Karp) is unaffected: it
   reduces to the same problem on the real residual SKUs. After the
   solve we strip the phantoms back out for display.

4. **Hard capability is honoured by the existing gate.** SKUs that can
   only run on the broken line (e.g. 2/5 cans, which only L19 supports)
   stay there because no other line passes ``can_produce``. They wait
   for the line to come back up — exactly what the brief asks for.

Output
------

:class:`WhatIfResult` carries the committed sequence per line
(unchanged from the original plan), the redistributed residual demand
per line, the new makespan, the SKUs that moved across lines, and the
SKUs that were stranded on the broken line because no other line could
take them.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Hashable, Mapping, Sequence

from line_partitioner import (
    CanProduce,
    EdgeCost,
    LineId,
    NodeCost,
    PartitionResult,
    SkuId,
    partition_lines,
)


# ---------------------------------------------------------------------------
# Phantom sentinel — represents the per-line baseline (committed +
# maintenance) as a node the partitioner can balance against.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _BaselinePhantom:
    """Sentinel SKU id that carries a line's pre-existing load.

    Frozen + hashable so it slots into the partitioner's dict / frozenset
    machinery without changes. ``__repr__`` is informative because the
    partitioner's solver log echoes node IDs."""

    line_id: int

    def __repr__(self) -> str:
        return f"<MAINT_BASELINE_L{self.line_id}>"


@dataclass(frozen=True)
class _UrgentPrefixPhantom:
    """Sentinel that locks an urgent order at the start of one line's suffix."""

    line_id: int
    urgent_node: SkuId

    def __repr__(self) -> str:
        return f"<URGENT_PREFIX_L{self.line_id}>"


def _is_phantom(sku: Any) -> bool:
    return isinstance(sku, (_BaselinePhantom, _UrgentPrefixPhantom))


def _is_urgent_prefix(sku: Any) -> bool:
    return isinstance(sku, _UrgentPrefixPhantom)


_FORCED_PREFIX_PENALTY_HOURS = 1_000_000.0


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class WhatIfResult:
    """Output of :func:`what_if_breakdown`.

    The result is *temporally split* in two parts:

    * ``committed_per_line`` — the SKUs already done (or, on non-affected
      lines, already in flight) by the breakdown moment. These are
      reported verbatim from the original plan.
    * ``new_sequences`` — the re-optimised order on the residual SKU set
      that runs **after** the breakdown moment, with the affected line
      sitting idle for ``maintenance_hours`` before resuming.

    Headline numbers:

    * ``baseline_hours_per_line[ℓ]`` — committed runtime on ``ℓ`` (plus
      maintenance overhead on the affected line).
    * ``residual_hours_per_line[ℓ]`` — prod + changeover for the new
      sequence on ``ℓ``.
    * ``total_hours_per_line[ℓ]`` — sum of the two, i.e. when line ``ℓ``
      actually finishes its week.
    * ``makespan_hours`` — ``max_ℓ total_hours_per_line[ℓ]``, the
      apples-to-apples comparison vs the original plan's makespan.
    """

    week_id: str
    breakdown_hours: float
    affected_line: int
    maintenance_hours: float

    committed_per_line: dict[int, tuple[SkuId, ...]]
    redistributed_per_line: dict[int, tuple[SkuId, ...]]
    new_sequences: dict[int, tuple[SkuId, ...]]

    baseline_hours_per_line: dict[int, float]
    residual_production_hours_per_line: dict[int, float]
    residual_changeover_hours_per_line: dict[int, float]
    residual_hours_per_line: dict[int, float]
    total_hours_per_line: dict[int, float]

    makespan_hours: float
    original_makespan_hours: float

    moved_skus: tuple[tuple[SkuId, int, int], ...]
    stranded_on_affected: tuple[SkuId, ...]

    underlying_result: PartitionResult
    iterations: int
    elapsed_s: float
    solver_log: str | None = None


@dataclass(frozen=True)
class UrgentDemandResult:
    """Output of :func:`what_if_urgent_demand`.

    ``committed_per_line`` is the frozen prefix at the moment the order
    arrives. ``new_sequences`` is the re-optimised suffix. The urgent demand
    is represented by ``urgent_node`` in ``new_sequences[assigned_line]`` and
    is always first in that suffix, so it starts after the frozen prefix and
    any required setup changeover.
    """

    week_id: str
    introduced_at_hours: float
    required_by_hours: float
    urgent_sku: SkuId
    urgent_node: SkuId
    urgent_units: int

    assigned_line: int
    urgent_start_hours: float
    urgent_end_hours: float
    due_window_met: bool

    committed_per_line: dict[int, tuple[SkuId, ...]]
    redistributed_per_line: dict[int, tuple[SkuId, ...]]
    new_sequences: dict[int, tuple[SkuId, ...]]

    baseline_hours_per_line: dict[int, float]
    pre_urgent_changeover_hours_per_line: dict[int, float]
    residual_production_hours_per_line: dict[int, float]
    residual_changeover_hours_per_line: dict[int, float]
    residual_hours_per_line: dict[int, float]
    total_hours_per_line: dict[int, float]

    makespan_hours: float
    original_makespan_hours: float

    moved_skus: tuple[tuple[SkuId, int, int], ...]

    underlying_result: PartitionResult
    iterations: int
    elapsed_s: float
    solver_log: str | None = None


# ---------------------------------------------------------------------------
# Snapshot of the original plan at the breakdown moment
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _LineSnapshot:
    committed: tuple[SkuId, ...]
    residual: tuple[SkuId, ...]
    baseline_h: float  # end-time of last committed SKU (or 0.0 if none)


def _snapshot_at_breakdown(
    sequences: Mapping[int, Sequence[SkuId]],
    breakdown_hours: float,
    affected_line: int,
    edge_cost: EdgeCost,
    node_cost: NodeCost,
) -> dict[int, _LineSnapshot]:
    """Split each line's sequence into (committed, residual) at ``T_b``.

    Non-affected line rule: a SKU is committed if it has *started* by
    ``T_b`` (so the line will run it to completion without interruption).

    Affected line rule: a SKU is committed only if it has *finished*
    strictly before ``T_b`` — anything in flight is aborted.
    """
    out: dict[int, _LineSnapshot] = {}
    for line, seq in sequences.items():
        seq = tuple(seq)
        committed: list[SkuId] = []
        residual: list[SkuId] = []
        baseline = 0.0
        t_cursor = 0.0  # time at which the upcoming SKU starts
        for i, sku in enumerate(seq):
            if i > 0:
                t_cursor += float(edge_cost(seq[i - 1], sku, line))
            nc = float(node_cost(sku, line))
            t_end = t_cursor + nc
            if line == affected_line:
                if t_end <= breakdown_hours:
                    committed.append(sku)
                    baseline = t_end
                else:
                    residual.append(sku)
            else:
                if t_cursor < breakdown_hours:
                    committed.append(sku)
                    baseline = t_end
                else:
                    residual.append(sku)
            t_cursor = t_end
        out[line] = _LineSnapshot(
            committed=tuple(committed),
            residual=tuple(residual),
            baseline_h=round(baseline, 4),
        )
    return out


def _snapshot_at_time(
    sequences: Mapping[int, Sequence[SkuId]],
    at_hours: float,
    edge_cost: EdgeCost,
    node_cost: NodeCost,
) -> dict[int, _LineSnapshot]:
    """Split each line into frozen prefix and re-plannable suffix.

    A SKU is frozen if it has already started before ``at_hours``. This is
    the freeze-window rule used for urgent demand: operators do not interrupt
    work already in progress, but anything not started returns to the residual
    pool.
    """
    out: dict[int, _LineSnapshot] = {}
    for line, seq in sequences.items():
        seq = tuple(seq)
        committed: list[SkuId] = []
        residual: list[SkuId] = []
        baseline = 0.0
        t_cursor = 0.0
        for i, sku in enumerate(seq):
            if i > 0:
                t_cursor += float(edge_cost(seq[i - 1], sku, line))
            nc = float(node_cost(sku, line))
            t_end = t_cursor + nc
            if t_cursor < at_hours:
                committed.append(sku)
                baseline = t_end
            else:
                residual.append(sku)
            t_cursor = t_end
        out[line] = _LineSnapshot(
            committed=tuple(committed),
            residual=tuple(residual),
            baseline_h=round(baseline, 4),
        )
    return out


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def what_if_breakdown(
    original_result: PartitionResult,
    *,
    breakdown_hours: float,
    affected_line: int,
    maintenance_hours: float,
    sku_ids: Sequence[SkuId],
    line_ids: Sequence[int],
    can_produce: CanProduce,
    edge_cost: EdgeCost,
    node_cost: NodeCost,
    units_by_sku: Mapping[SkuId, int] | None = None,
    week_id: str | None = None,
    **partition_kwargs: Any,
) -> WhatIfResult:
    """Re-plan the remainder of the week after a line breaks down.

    Parameters
    ----------
    original_result
        The baseline :class:`PartitionResult` for the week (typically the
        output of :func:`line_partitioner.partition_lines` on the same
        inputs).
    breakdown_hours
        Wall-clock time, in hours since the start of the plan, at which
        the breakdown happens. Must be ≥ 0; if it lands past every line's
        finish, the call is a no-op (returns the original plan).
    affected_line
        Line ID where the machine has failed (one of ``line_ids``).
    maintenance_hours
        Duration of the repair. The affected line is unavailable for
        ``[breakdown_hours, breakdown_hours + maintenance_hours]``.
    sku_ids, line_ids, can_produce, edge_cost, node_cost, units_by_sku
        Same callables / IDs that produced ``original_result``. The
        contract matches :func:`line_partitioner.partition_lines`.
    week_id
        Optional label echoed back in the result.
    partition_kwargs
        Forwarded verbatim to :func:`line_partitioner.partition_lines`
        for the re-plan call (``time_budget_s``, ``move_strategy``, …).

    Returns
    -------
    :class:`WhatIfResult` — committed prefix per line + re-optimised
    suffix per line, with adjusted timings.
    """
    t0 = time.perf_counter()
    line_ids_t = tuple(line_ids)
    if affected_line not in line_ids_t:
        raise ValueError(
            f"affected_line={affected_line!r} is not in line_ids={line_ids_t!r}"
        )
    if breakdown_hours < 0:
        raise ValueError(f"breakdown_hours must be ≥ 0, got {breakdown_hours}")
    if maintenance_hours < 0:
        raise ValueError(f"maintenance_hours must be ≥ 0, got {maintenance_hours}")

    # ---- 1. Snapshot at breakdown moment ----------------------------------
    snap = _snapshot_at_breakdown(
        original_result.sequences,
        breakdown_hours=breakdown_hours,
        affected_line=affected_line,
        edge_cost=edge_cost,
        node_cost=node_cost,
    )

    # ---- 2. Per-line baseline (load the new plan starts on top of) -------
    # Non-affected line: continues with its in-flight SKU, so its baseline
    # is the end-time of the last committed SKU (already includes any
    # mid-flight SKU because we mark "started" SKUs as committed).
    # Affected line: dead from T_b for maintenance_hours, then resumes
    # from scratch on the residual. Baseline = breakdown + maintenance.
    baseline: dict[int, float] = {l: snap[l].baseline_h for l in line_ids_t}
    baseline[affected_line] = round(
        float(breakdown_hours) + float(maintenance_hours), 4,
    )

    # ---- 3. Residual SKU pool (deduplicated, stable order) ---------------
    residual_set: list[SkuId] = []
    seen: set[SkuId] = set()
    for line in line_ids_t:
        for sku in snap[line].residual:
            if sku not in seen:
                residual_set.append(sku)
                seen.add(sku)

    # ---- 4. Inject phantom baseline nodes --------------------------------
    # One phantom per line. Each phantom is feasible only on its own line,
    # costs `baseline[line]` to produce, and is free to traverse on edges.
    # That makes the partitioner balance the *real* load against the
    # baseline — exactly the rebalancing we want post-breakdown.
    phantom_by_line: dict[int, _BaselinePhantom] = {
        l: _BaselinePhantom(line_id=l) for l in line_ids_t
    }
    phantoms: tuple[_BaselinePhantom, ...] = tuple(phantom_by_line.values())
    augmented_ids: list[SkuId] = list(residual_set) + list(phantoms)

    def aug_can_produce(sku: SkuId, line: int) -> bool:
        if _is_phantom(sku):
            return phantom_by_line[line] == sku
        return can_produce(sku, line)

    def aug_edge_cost(a: SkuId, b: SkuId, line: int) -> float:
        if _is_phantom(a) or _is_phantom(b):
            return 0.0
        return float(edge_cost(a, b, line))

    def aug_node_cost(sku: SkuId, line: int) -> float:
        if _is_phantom(sku):
            return baseline[line] if phantom_by_line[line] == sku else 0.0
        return float(node_cost(sku, line))

    aug_units: dict[SkuId, int] = (
        dict(units_by_sku) if units_by_sku is not None else {}
    )
    for ph in phantoms:
        aug_units.setdefault(ph, 0)

    # ---- 5. Re-plan ------------------------------------------------------
    aug_result = partition_lines(
        augmented_ids,
        list(line_ids_t),
        aug_can_produce,
        aug_edge_cost,
        aug_node_cost,
        units_by_sku=aug_units,
        **partition_kwargs,
    )

    # ---- 6. Strip phantoms + recompute residual loads --------------------
    # The phantom contributes its baseline load and nothing else; we pull
    # it out for display and recompute prod / changeover on the real SKUs
    # only, so the per-line breakdown is clean.
    new_seq: dict[int, tuple[SkuId, ...]] = {}
    residual_prod: dict[int, float] = {}
    residual_chg: dict[int, float] = {}
    for line in line_ids_t:
        raw = list(aug_result.sequences.get(line, ()))
        clean = tuple(s for s in raw if not _is_phantom(s))
        new_seq[line] = clean
        residual_prod[line] = round(
            sum(float(node_cost(s, line)) for s in clean), 4,
        )
        residual_chg[line] = round(
            sum(
                float(edge_cost(clean[i - 1], clean[i], line))
                for i in range(1, len(clean))
            ),
            4,
        )

    residual_h = {
        l: round(residual_prod[l] + residual_chg[l], 4) for l in line_ids_t
    }
    total_h = {
        l: round(baseline[l] + residual_h[l], 4) for l in line_ids_t
    }
    makespan = max(total_h.values())

    # ---- 7. Diagnostics: which SKUs moved, which are stranded -----------
    orig_line_by_sku: dict[SkuId, int] = {}
    for line, seq in original_result.sequences.items():
        for sku in seq:
            orig_line_by_sku[sku] = line

    moved: list[tuple[SkuId, int, int]] = []
    for line in line_ids_t:
        for sku in new_seq[line]:
            orig = orig_line_by_sku.get(sku)
            if orig is not None and orig != line:
                moved.append((sku, orig, line))

    # SKUs that remain on the affected line *because* no other line can
    # take them — the "wait for the machine to come back" cohort.
    stranded: list[SkuId] = []
    for sku in new_seq[affected_line]:
        feasible_elsewhere = any(
            can_produce(sku, l) for l in line_ids_t if l != affected_line
        )
        if not feasible_elsewhere:
            stranded.append(sku)

    elapsed = time.perf_counter() - t0

    # Solver log re-targeted at the what-if framing — keeps the same
    # shape as PartitionResult.solver_log so downstream consumers can
    # render it identically.
    moved_summary = (
        ", ".join(f"{s}: L{a}->L{b}" for s, a, b in moved[:5])
        + (" ..." if len(moved) > 5 else "")
        if moved
        else "none"
    )
    log = (
        f"What-If Breakdown | week={week_id or '—'} "
        f"line L{affected_line}  T_b={breakdown_hours:.2f}h  "
        f"maintenance={maintenance_hours:.2f}h\n"
        f"  residual SKUs to replan : {len(residual_set)}\n"
        f"  baseline per line       : "
        + " | ".join(f"L{l}={baseline[l]:.2f}h" for l in line_ids_t)
        + "\n"
        f"  residual per line       : "
        + " | ".join(f"L{l}={residual_h[l]:.2f}h" for l in line_ids_t)
        + "\n"
        f"  total per line          : "
        + " | ".join(f"L{l}={total_h[l]:.2f}h" for l in line_ids_t)
        + "\n"
        f"  makespan (new vs orig)  : {makespan:.2f}h vs "
        f"{original_result.makespan_hours:.2f}h "
        f"(delta={makespan - original_result.makespan_hours:+.2f}h)\n"
        f"  moved SKUs              : {len(moved)}  ({moved_summary})\n"
        f"  stranded on L{affected_line}            : {len(stranded)}\n"
        f"  underlying partitioner  : {aug_result.iterations} iters, "
        f"{aug_result.elapsed_s*1000:.0f} ms"
    )

    return WhatIfResult(
        week_id=week_id or "",
        breakdown_hours=float(breakdown_hours),
        affected_line=int(affected_line),
        maintenance_hours=float(maintenance_hours),
        committed_per_line={l: snap[l].committed for l in line_ids_t},
        redistributed_per_line={
            l: tuple(s for s in new_seq[l] if s in seen) for l in line_ids_t
        },
        new_sequences=new_seq,
        baseline_hours_per_line=baseline,
        residual_production_hours_per_line=residual_prod,
        residual_changeover_hours_per_line=residual_chg,
        residual_hours_per_line=residual_h,
        total_hours_per_line=total_h,
        makespan_hours=round(makespan, 4),
        original_makespan_hours=round(original_result.makespan_hours, 4),
        moved_skus=tuple(moved),
        stranded_on_affected=tuple(stranded),
        underlying_result=aug_result,
        iterations=aug_result.iterations,
        elapsed_s=round(elapsed, 4),
        solver_log=log,
    )


def what_if_urgent_demand(
    original_result: PartitionResult,
    *,
    introduced_at_hours: float,
    required_by_hours: float,
    urgent_sku: SkuId,
    urgent_node: SkuId,
    urgent_units: int,
    sku_ids: Sequence[SkuId],
    line_ids: Sequence[int],
    can_produce: CanProduce,
    edge_cost: EdgeCost,
    node_cost: NodeCost,
    units_by_sku: Mapping[SkuId, int] | None = None,
    week_id: str | None = None,
    **partition_kwargs: Any,
) -> UrgentDemandResult:
    """Re-plan the remaining week after urgent demand arrives.

    The urgent order is a *new demand node*, separate from any existing SKU
    node for the same product. The algorithm evaluates every feasible line
    for the urgent order, freezes work that had already started when the
    order arrived, then re-runs the v1 partitioner on the residual demand.

    For each candidate line the urgent order is locked as the first new job
    after the frozen prefix. Candidate lines whose earliest completion time
    exceeds ``required_by_hours`` are rejected, so the returned solution
    respects the requested time window by construction.
    """
    t0 = time.perf_counter()
    line_ids_t = tuple(int(l) for l in line_ids)
    if introduced_at_hours < 0:
        raise ValueError(
            f"introduced_at_hours must be ≥ 0, got {introduced_at_hours}"
        )
    if required_by_hours < introduced_at_hours:
        raise ValueError(
            "required_by_hours must be greater than or equal to "
            f"introduced_at_hours ({required_by_hours} < {introduced_at_hours})"
        )
    if urgent_units <= 0:
        raise ValueError(f"urgent_units must be positive, got {urgent_units}")

    existing_ids = set(sku_ids)
    existing_ids.update(
        sku for seq in original_result.sequences.values() for sku in seq
    )
    if urgent_node in existing_ids:
        raise ValueError(
            "urgent_node must be a distinct demand node; pass a synthetic ID "
            "when the urgent order is for an SKU already present in the plan"
        )

    feasible_urgent_lines = [
        line for line in line_ids_t if can_produce(urgent_node, line)
    ]
    if not feasible_urgent_lines:
        raise ValueError(
            f"urgent demand {urgent_sku!r} cannot be produced on any line"
        )

    snap = _snapshot_at_time(
        original_result.sequences,
        at_hours=float(introduced_at_hours),
        edge_cost=edge_cost,
        node_cost=node_cost,
    )
    baseline: dict[int, float] = {
        line: round(max(snap[line].baseline_h, float(introduced_at_hours)), 4)
        for line in line_ids_t
    }

    residual_set: list[SkuId] = []
    seen: set[SkuId] = set()
    for line in line_ids_t:
        for sku in snap[line].residual:
            if sku not in seen:
                residual_set.append(sku)
                seen.add(sku)

    orig_line_by_sku: dict[SkuId, int] = {}
    for line, seq in original_result.sequences.items():
        for sku in seq:
            orig_line_by_sku[sku] = line

    units_lookup: dict[SkuId, int] = (
        dict(units_by_sku) if units_by_sku is not None else {}
    )
    eps = float(partition_kwargs.get("eps", 1e-3))
    best_payload: tuple[float, float, UrgentDemandResult] | None = None
    late_candidates: list[tuple[int, float]] = []

    for urgent_line in feasible_urgent_lines:
        previous_sku = snap[urgent_line].committed[-1] if snap[urgent_line].committed else None
        setup_h = (
            float(edge_cost(previous_sku, urgent_node, urgent_line))
            if previous_sku is not None
            else 0.0
        )
        urgent_prod_h = float(node_cost(urgent_node, urgent_line))
        urgent_start = round(baseline[urgent_line] + setup_h, 4)
        urgent_end = round(urgent_start + urgent_prod_h, 4)
        late_candidates.append((urgent_line, urgent_end))
        if urgent_end > required_by_hours + 1e-9:
            continue

        phantom_by_line: dict[int, SkuId] = {}
        for line in line_ids_t:
            if line == urgent_line:
                phantom_by_line[line] = _UrgentPrefixPhantom(
                    line_id=line,
                    urgent_node=urgent_node,
                )
            else:
                phantom_by_line[line] = _BaselinePhantom(line_id=line)

        phantoms = tuple(phantom_by_line.values())
        augmented_ids: list[SkuId] = list(residual_set) + list(phantoms)

        def aug_can_produce(sku: SkuId, line: int) -> bool:
            if _is_phantom(sku):
                return phantom_by_line[line] == sku
            return can_produce(sku, line)

        def aug_node_cost(sku: SkuId, line: int) -> float:
            if _is_urgent_prefix(sku):
                if phantom_by_line[line] != sku:
                    return 0.0
                return baseline[line] + setup_h + urgent_prod_h
            if _is_phantom(sku):
                return baseline[line] if phantom_by_line[line] == sku else 0.0
            return float(node_cost(sku, line))

        def aug_edge_cost(a: SkuId, b: SkuId, line: int) -> float:
            if _is_urgent_prefix(a) and not _is_phantom(b):
                return float(edge_cost(urgent_node, b, line))
            if _is_urgent_prefix(b) and not _is_phantom(a):
                return _FORCED_PREFIX_PENALTY_HOURS
            if _is_phantom(a) or _is_phantom(b):
                return 0.0
            return float(edge_cost(a, b, line))

        aug_units = dict(units_lookup)
        for ph in phantoms:
            aug_units.setdefault(ph, 0)

        aug_result = partition_lines(
            augmented_ids,
            list(line_ids_t),
            aug_can_produce,
            aug_edge_cost,
            aug_node_cost,
            units_by_sku=aug_units,
            **partition_kwargs,
        )

        new_seq: dict[int, tuple[SkuId, ...]] = {}
        pre_urgent_chg = {line: 0.0 for line in line_ids_t}
        pre_urgent_chg[urgent_line] = round(setup_h, 4)
        residual_prod: dict[int, float] = {}
        residual_chg: dict[int, float] = {}
        for line in line_ids_t:
            raw = list(aug_result.sequences.get(line, ()))
            clean = tuple(s for s in raw if not _is_phantom(s))
            displayed = (urgent_node, *clean) if line == urgent_line else clean
            new_seq[line] = displayed
            residual_prod[line] = round(
                sum(float(node_cost(s, line)) for s in displayed), 4,
            )
            residual_chg[line] = round(
                pre_urgent_chg[line]
                + sum(
                    float(edge_cost(displayed[i - 1], displayed[i], line))
                    for i in range(1, len(displayed))
                ),
                4,
            )

        residual_h = {
            line: round(residual_prod[line] + residual_chg[line], 4)
            for line in line_ids_t
        }
        total_h = {
            line: round(baseline[line] + residual_h[line], 4)
            for line in line_ids_t
        }
        makespan = max(total_h.values())
        objective = makespan + eps * sum(total_h.values())

        moved: list[tuple[SkuId, int, int]] = []
        for line in line_ids_t:
            for sku in new_seq[line]:
                orig = orig_line_by_sku.get(sku)
                if orig is not None and orig != line:
                    moved.append((sku, orig, line))

        moved_summary = (
            ", ".join(f"{s}: L{a}->L{b}" for s, a, b in moved[:5])
            + (" ..." if len(moved) > 5 else "")
            if moved
            else "none"
        )
        log = (
            f"What-If Urgent Demand | week={week_id or '—'} "
            f"sku={urgent_sku} units={urgent_units:,} "
            f"arrives={introduced_at_hours:.2f}h due={required_by_hours:.2f}h\n"
            f"  assigned line          : L{urgent_line}\n"
            f"  urgent slot            : {urgent_start:.2f}h → {urgent_end:.2f}h "
            f"(within window: yes)\n"
            f"  residual SKUs to replan : {len(residual_set)}\n"
            f"  baseline per line       : "
            + " | ".join(f"L{l}={baseline[l]:.2f}h" for l in line_ids_t)
            + "\n"
            f"  residual per line       : "
            + " | ".join(f"L{l}={residual_h[l]:.2f}h" for l in line_ids_t)
            + "\n"
            f"  total per line          : "
            + " | ".join(f"L{l}={total_h[l]:.2f}h" for l in line_ids_t)
            + "\n"
            f"  makespan (new vs orig)  : {makespan:.2f}h vs "
            f"{original_result.makespan_hours:.2f}h "
            f"(delta={makespan - original_result.makespan_hours:+.2f}h)\n"
            f"  moved SKUs              : {len(moved)}  ({moved_summary})\n"
            f"  underlying partitioner  : {aug_result.iterations} iters, "
            f"{aug_result.elapsed_s*1000:.0f} ms"
        )

        candidate = UrgentDemandResult(
            week_id=week_id or "",
            introduced_at_hours=float(introduced_at_hours),
            required_by_hours=float(required_by_hours),
            urgent_sku=urgent_sku,
            urgent_node=urgent_node,
            urgent_units=int(urgent_units),
            assigned_line=int(urgent_line),
            urgent_start_hours=urgent_start,
            urgent_end_hours=urgent_end,
            due_window_met=True,
            committed_per_line={line: snap[line].committed for line in line_ids_t},
            redistributed_per_line={
                line: tuple(s for s in new_seq[line] if s in seen)
                for line in line_ids_t
            },
            new_sequences=new_seq,
            baseline_hours_per_line=baseline,
            pre_urgent_changeover_hours_per_line=pre_urgent_chg,
            residual_production_hours_per_line=residual_prod,
            residual_changeover_hours_per_line=residual_chg,
            residual_hours_per_line=residual_h,
            total_hours_per_line=total_h,
            makespan_hours=round(makespan, 4),
            original_makespan_hours=round(original_result.makespan_hours, 4),
            moved_skus=tuple(moved),
            underlying_result=aug_result,
            iterations=aug_result.iterations,
            elapsed_s=round(time.perf_counter() - t0, 4),
            solver_log=log,
        )
        ranking_key = (objective, urgent_end, candidate)
        if best_payload is None or ranking_key[:2] < best_payload[:2]:
            best_payload = ranking_key

    if best_payload is None:
        earliest_line, earliest_end = min(late_candidates, key=lambda item: item[1])
        raise ValueError(
            "urgent demand cannot fit in the required time window: earliest "
            f"completion is L{earliest_line} at {earliest_end:.2f}h, "
            f"deadline is {required_by_hours:.2f}h"
        )

    return best_payload[2]


# ---------------------------------------------------------------------------
# Demo — wire to real ETL data and run a representative scenario
# ---------------------------------------------------------------------------

def _demo() -> None:
    """End-to-end demo on the real ``data/clean`` CSVs.

    1. Build the baseline weekly plan with :func:`partition_lines`.
    2. Inject a breakdown on L19 ~25% into the makespan with 12h
       maintenance.
    3. Print the before/after report.

    Falls back to the synthetic dataset if the real ETL is missing, so
    the demo runs offline."""
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
        week_id = ds.window_id

        def edge_cost(a: str, b: str, line: int) -> float:
            return _real_edge_cost(a, b, line)

        def node_cost(sku: str, line: int) -> float:
            return _real_node_cost(sku, ds.units_by_sku[sku], line)

        print(f"[what-if demo] real window={week_id}  n_skus={len(sku_ids)}")
    except (FileNotFoundError, ImportError):
        from generate_test_data import (
            DEFAULT_OUT_PATH,
            LINE_CONTAINER_TYPES,
            LINE_IDS,
            build_sku_catalog,
            get_node_cost as _syn_node_cost,
            get_transition_cost as _syn_edge_cost,
            read_sheet,
        )
        catalog = build_sku_catalog()
        sku_by_id = {s.sku_id: s for s in catalog}
        demand_rows = read_sheet(DEFAULT_OUT_PATH, "demand")
        units_by_sku = {r["sku_id"]: int(r["units_demanded"]) for r in demand_rows}
        sku_ids = [s.sku_id for s in catalog]
        week_id = "SYNTHETIC"

        def can_produce(sku_id: str, line_id: int) -> bool:  # type: ignore[no-redef]
            return sku_by_id[sku_id].container_type in LINE_CONTAINER_TYPES[line_id]

        def edge_cost(a: str, b: str, line: int) -> float:
            return _syn_edge_cost(sku_by_id[a], sku_by_id[b], line)

        def node_cost(sku_id: str, line: int) -> float:
            return _syn_node_cost(sku_by_id[sku_id], units_by_sku[sku_id], line)

        print(f"[what-if demo] SYNTHETIC fallback  n_skus={len(sku_ids)}")

    # ---- Baseline plan ----------------------------------------------------
    common_kw = dict(
        time_budget_s=4.0,
        sequence_budget_s=0.05,
        delta_balance_h=0.5,
        eps=1e-3,
        move_strategy="best_improvement",
        max_iterations=500,
        max_no_improve=50,
    )
    baseline_plan = partition_lines(
        sku_ids, list(LINE_IDS), can_produce, edge_cost, node_cost,
        units_by_sku=units_by_sku, **common_kw,
    )

    print(f"\n=== Baseline plan (week {week_id}) ===")
    for line in LINE_IDS:
        seq = baseline_plan.sequences[line]
        print(
            f"  L{line}: n={len(seq):2d}  "
            f"prod={baseline_plan.production_hours_per_line[line]:6.2f}h  "
            f"chg={baseline_plan.changeover_hours_per_line[line]:5.2f}h  "
            f"load={baseline_plan.makespan_per_line_hours[line]:6.2f}h"
        )
    print(f"  makespan = {baseline_plan.makespan_hours:.2f}h")

    # ---- Inject breakdown: L19 fails 25% into makespan, 12h repair -------
    breakdown_hours = round(baseline_plan.makespan_hours * 0.25, 2)
    affected_line = 19
    maintenance_hours = 12.0

    wif = what_if_breakdown(
        baseline_plan,
        breakdown_hours=breakdown_hours,
        affected_line=affected_line,
        maintenance_hours=maintenance_hours,
        sku_ids=sku_ids,
        line_ids=list(LINE_IDS),
        can_produce=can_produce,
        edge_cost=edge_cost,
        node_cost=node_cost,
        units_by_sku=units_by_sku,
        week_id=week_id,
        **common_kw,
    )

    print(
        f"\n=== What-if: L{affected_line} breaks at T_b={breakdown_hours}h, "
        f"maintenance={maintenance_hours}h ==="
    )
    for line in LINE_IDS:
        committed = wif.committed_per_line[line]
        new = wif.new_sequences[line]
        print(
            f"  L{line}: committed={len(committed):2d} "
            f"(baseline={wif.baseline_hours_per_line[line]:6.2f}h) "
            f"+ new={len(new):2d} "
            f"(residual={wif.residual_hours_per_line[line]:6.2f}h)  "
            f"-> total={wif.total_hours_per_line[line]:6.2f}h"
        )

    print(
        f"\n  makespan  : {wif.makespan_hours:6.2f}h  "
        f"(baseline {wif.original_makespan_hours:.2f}h, "
        f"delta {wif.makespan_hours - wif.original_makespan_hours:+.2f}h)"
    )
    print(f"  moved SKUs    : {len(wif.moved_skus)}")
    for sku, a, b in wif.moved_skus[:10]:
        print(f"     - {sku}  L{a} -> L{b}")
    if len(wif.moved_skus) > 10:
        print(f"     ... and {len(wif.moved_skus) - 10} more")
    print(
        f"  stranded on L{affected_line}: "
        f"{len(wif.stranded_on_affected)} SKUs that no other line can produce"
    )
    for sku in wif.stranded_on_affected[:10]:
        print(f"     - {sku}")
    if len(wif.stranded_on_affected) > 10:
        print(f"     ... and {len(wif.stranded_on_affected) - 10} more")

    print("\n  --- solver log ---")
    for line in (wif.solver_log or "").splitlines():
        print(f"  {line}")


if __name__ == "__main__":
    _demo()
