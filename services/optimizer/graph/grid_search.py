"""Grid search over the two-level partitioner's hyperparameters.

Sweeps the algorithmic knobs that the LineWise partitioner exposes, runs each
combination on several real demand windows (low / median / high SKU count),
and ranks configurations by the lexicographic key:

    (mean_makespan_h, mean_total_h, mean_elapsed_s)

— so the headline objective (min-max makespan) dominates, the
sum-of-loads tie-breaker comes next, and wall-clock is the final
discriminator. Output:

* ``data_experiment/grid_search_results.csv`` — one row per (config, window).
* Console summary — top-5 configs by mean rank, with per-window detail.

Parameters swept
----------------

* ``move_strategy``      ∈ {first_improvement, best_improvement}
* ``delta_balance_h``    ∈ {0.5, 2.0, 4.0}
* ``max_no_improve``     ∈ {20, 50, 100}
* ``eps``                ∈ {1e-4, 1e-3}
* ``sequence_budget_s``  fixed at 0.05 (HK is exact at n ≤ 15 → budget is
                          slack, not a quality knob).

Fixed: ``time_budget_s=8.0`` per run (enough headroom for best_improvement
to land at least one full iteration on n=45), ``seed=42`` for reproducibility.

Total runs: 2 × 3 × 3 × 2 = 36 configs × N windows. With 3 windows that's
108 runs ≈ 5-15 minutes wall-clock, depending on hardware.

Usage
-----

::

    python grid_search.py                # default — 3 windows, 36 configs
    python grid_search.py --windows 5    # use 5 evaluation windows
    python grid_search.py --quick        # smaller grid, ~1 minute

Read the printed top-5 and the ``grid_search_results.csv`` to choose
defaults for :func:`line_partitioner.partition_lines`.
"""

from __future__ import annotations

import argparse
import csv
import itertools
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable

from line_partitioner import partition_lines, verify_partition
from real_data_loader import (
    LINE_IDS, can_produce, get_node_cost, get_transition_cost,
    list_demand_windows, load_window_dataset,
)


OUT_DIR: Path = Path(__file__).resolve().parent / "data_experiment"
RESULTS_CSV: Path = OUT_DIR / "grid_search_results.csv"


# ---------------------------------------------------------------------------
# Config + result dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GridConfig:
    move_strategy: str
    delta_balance_h: float
    max_no_improve: int
    eps: float


@dataclass(frozen=True)
class RunRecord:
    window_id: str
    n_skus: int
    move_strategy: str
    delta_balance_h: float
    max_no_improve: int
    eps: float
    makespan_h: float
    total_h: float
    spread_h: float
    dropped: int
    iterations: int
    elapsed_s: float
    feasible: bool
    verify_ok: bool


# ---------------------------------------------------------------------------
# Grid + window selection
# ---------------------------------------------------------------------------

def default_grid() -> list[GridConfig]:
    """36-cell grid: 2 strategies × 3 balance × 3 patience × 2 epsilons."""
    strategies = ["first_improvement", "best_improvement"]
    deltas = [0.5, 2.0, 4.0]
    patiences = [20, 50, 100]
    epses = [1e-4, 1e-3]
    return [
        GridConfig(s, d, p, e)
        for s, d, p, e in itertools.product(strategies, deltas, patiences, epses)
    ]


def quick_grid() -> list[GridConfig]:
    """8-cell smoke-test grid for fast iteration."""
    return [
        GridConfig(s, d, 50, 1e-4)
        for s in ("first_improvement", "best_improvement")
        for d in (0.5, 2.0, 4.0, 8.0)
    ]


def pick_windows(n: int) -> list[str]:
    """Spread evaluation windows across the SKU-count distribution.

    Returns evenly-spaced quantile picks so the grid measures generalisation
    rather than overfitting to one window's idiosyncrasies."""
    counts = list_demand_windows().sort_values("n_skus")
    if n >= len(counts):
        return list(counts.index)
    # Evenly spaced quantile picks.
    idx = [int(round(i * (len(counts) - 1) / (n - 1))) for i in range(n)]
    return [str(counts.index[i]) for i in idx]


# ---------------------------------------------------------------------------
# Single run
# ---------------------------------------------------------------------------

def run_one(
    window_id: str, cfg: GridConfig, *, time_budget_s: float = 8.0,
) -> RunRecord:
    ds = load_window_dataset(window_id)
    sku_ids = list(ds.sku_ids)
    units = ds.units_by_sku

    def edge(a: str, b: str, l: int) -> float:
        return get_transition_cost(a, b, l)

    def node(s: str, l: int) -> float:
        return get_node_cost(s, units[s], l)

    r = partition_lines(
        sku_ids, list(LINE_IDS), can_produce, edge, node,
        units_by_sku=units,
        time_budget_s=time_budget_s,
        sequence_budget_s=0.05,
        eps=cfg.eps,
        delta_balance_h=cfg.delta_balance_h,
        max_no_improve=cfg.max_no_improve,
        max_iterations=500,
        move_strategy=cfg.move_strategy,
    )
    rep = verify_partition(r, sku_ids, can_produce, edge, node, eps=cfg.eps)
    spread = (
        r.makespan_hours - min(r.makespan_per_line_hours.values())
        if r.makespan_per_line_hours else 0.0
    )
    return RunRecord(
        window_id=window_id,
        n_skus=len(sku_ids),
        move_strategy=cfg.move_strategy,
        delta_balance_h=cfg.delta_balance_h,
        max_no_improve=cfg.max_no_improve,
        eps=cfg.eps,
        makespan_h=round(r.makespan_hours, 4),
        total_h=round(r.total_hours, 4),
        spread_h=round(spread, 4),
        dropped=len(r.dropped),
        iterations=r.iterations,
        elapsed_s=round(r.elapsed_s, 3),
        feasible=r.feasible,
        verify_ok=rep.ok,
    )


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def run_grid(
    grid: Iterable[GridConfig], windows: Iterable[str],
    *, time_budget_s: float, csv_path: Path,
) -> list[RunRecord]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    grid = list(grid)
    windows = list(windows)
    total = len(grid) * len(windows)
    print(f"[grid] {len(grid)} configs × {len(windows)} windows = {total} runs")
    print(f"[grid] windows: {windows}")
    print(f"[grid] time budget per run: {time_budget_s}s "
          f"(worst-case total: {total * time_budget_s / 60:.1f} min)")
    records: list[RunRecord] = []
    t0 = time.perf_counter()
    for i, (cfg, wid) in enumerate(itertools.product(grid, windows), start=1):
        rec = run_one(wid, cfg, time_budget_s=time_budget_s)
        records.append(rec)
        eta = (time.perf_counter() - t0) / i * (total - i)
        flag = "OK" if rec.verify_ok else "FAIL"
        print(
            f"  [{i:3d}/{total}] {wid}  "
            f"strat={cfg.move_strategy[:5]} d={cfg.delta_balance_h} "
            f"p={cfg.max_no_improve} eps={cfg.eps:g}  "
            f"-> makespan={rec.makespan_h:6.2f}h  spread={rec.spread_h:5.2f}h  "
            f"iter={rec.iterations:3d}  el={rec.elapsed_s:5.2f}s  {flag}  "
            f"(ETA {eta:5.0f}s)"
        )
    # Write CSV
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(asdict(records[0]).keys()))
        w.writeheader()
        for r in records:
            w.writerow(asdict(r))
    print(f"\n[grid] wrote {csv_path}")
    return records


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def summarise(records: list[RunRecord], top: int = 5) -> None:
    """Group records by config, average across windows, rank by makespan."""
    by_cfg: dict[tuple, list[RunRecord]] = {}
    for r in records:
        key = (r.move_strategy, r.delta_balance_h, r.max_no_improve, r.eps)
        by_cfg.setdefault(key, []).append(r)

    rows = []
    for key, recs in by_cfg.items():
        if any(not r.verify_ok for r in recs):
            continue  # exclude broken configs
        mean_makespan = sum(r.makespan_h for r in recs) / len(recs)
        mean_total = sum(r.total_h for r in recs) / len(recs)
        mean_spread = sum(r.spread_h for r in recs) / len(recs)
        mean_elapsed = sum(r.elapsed_s for r in recs) / len(recs)
        mean_iter = sum(r.iterations for r in recs) / len(recs)
        dropped_any = sum(r.dropped for r in recs)
        rows.append({
            "config": key,
            "mean_makespan": mean_makespan,
            "mean_total": mean_total,
            "mean_spread": mean_spread,
            "mean_elapsed": mean_elapsed,
            "mean_iterations": mean_iter,
            "dropped_total": dropped_any,
            "per_window": recs,
        })
    rows.sort(key=lambda r: (r["mean_makespan"], r["mean_total"], r["mean_elapsed"]))

    print(f"\n=== Top {top} configs (ranked by mean makespan over windows) ===\n")
    headers = (
        "rank", "strategy", "delta", "patience", "eps",
        "mean_makespan", "mean_spread", "mean_elapsed", "iter", "drop",
    )
    print(
        f"{'rank':>4} {'strategy':<20} {'delta':>6} {'patience':>9} "
        f"{'eps':>7} {'makespan':>9} {'spread':>7} {'elapsed':>8} "
        f"{'iter':>5} {'drop':>5}"
    )
    print("-" * 100)
    for rank, r in enumerate(rows[:top], start=1):
        strat, d, p, e = r["config"]
        print(
            f"{rank:>4} {strat:<20} {d:>6.2f} {p:>9d} {e:>7.0e} "
            f"{r['mean_makespan']:>8.2f}h {r['mean_spread']:>6.2f}h "
            f"{r['mean_elapsed']:>6.2f}s {r['mean_iterations']:>5.1f} {r['dropped_total']:>5d}"
        )

    if not rows:
        print("(no configs passed verification — investigate!)")
        return

    # Per-window detail for the winner
    winner = rows[0]
    print(f"\n--- per-window detail for #1 {winner['config']} ---")
    for rec in winner["per_window"]:
        print(
            f"  {rec.window_id}  n={rec.n_skus:2d}  makespan={rec.makespan_h:6.2f}h  "
            f"spread={rec.spread_h:5.2f}h  iter={rec.iterations:3d}  "
            f"elapsed={rec.elapsed_s:5.2f}s"
        )

    # Speed-quality Pareto: also surface the fastest config within 1% of best
    best_ms = rows[0]["mean_makespan"]
    fast_rows = [
        r for r in rows
        if r["mean_makespan"] <= best_ms * 1.01
    ]
    fast_rows.sort(key=lambda r: r["mean_elapsed"])
    if fast_rows and fast_rows[0]["config"] != winner["config"]:
        f = fast_rows[0]
        strat, d, p, e = f["config"]
        print(
            f"\n--- fastest config within 1% of best makespan ---"
            f"\n  {strat}  delta={d} patience={p} eps={e:g}  "
            f"makespan={f['mean_makespan']:.2f}h  elapsed={f['mean_elapsed']:.2f}s"
        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--windows", type=int, default=3,
                    help="Number of evaluation windows (default 3, spread across n_skus quantiles).")
    ap.add_argument("--budget", type=float, default=8.0,
                    help="Per-run time budget in seconds (default 8.0).")
    ap.add_argument("--quick", action="store_true",
                    help="Use the smaller 8-cell quick grid for smoke-testing.")
    ap.add_argument("--top", type=int, default=5,
                    help="How many configs to report in the summary.")
    ap.add_argument("--csv", type=Path, default=RESULTS_CSV,
                    help="Output CSV path.")
    args = ap.parse_args(argv)

    grid = quick_grid() if args.quick else default_grid()
    windows = pick_windows(args.windows)
    records = run_grid(grid, windows, time_budget_s=args.budget, csv_path=args.csv)
    summarise(records, top=args.top)
    return 0


if __name__ == "__main__":
    sys.exit(main())
