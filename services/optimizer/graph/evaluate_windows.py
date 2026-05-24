"""Evaluate the two-level partitioner across every week in ``demand.csv``.

For each ``window_id`` present in ``data/clean/demand.csv`` this script:

1. Builds the canonical planning graph via
   :func:`services.optimizer.app.graph_builder.build_planning_graph`.
2. Runs :func:`line_partitioner.partition_from_graph` (the two-level
   greedy + Held-Karp + best-improvement local search).
3. Independently recomputes the makespan via
   :func:`line_partitioner.verify_partition` so each row is self-checked.

Reports the **mean / median / stdev / P25 / P75 / min / max** of the
makespan (max line load) along with per-line breakdowns, drop counts and
wall-clock time. This is the canonical *aggregate quality* metric for the
partitioner over the full 2025 history.

Outputs
-------

* Console: one line per window, then the summary block.
* CSV: ``data_experiment/evaluation_all_windows.csv`` — one row per window
  with every per-line load, production / changeover split, dropped count,
  iterations, wall-clock time, and the verify-OK flag.

Usage
-----

.. code-block:: bash

    python services/optimizer/graph/evaluate_windows.py
    python services/optimizer/graph/evaluate_windows.py --budget 6.0
    python services/optimizer/graph/evaluate_windows.py --strategy first_improvement
    python services/optimizer/graph/evaluate_windows.py --limit 5      # smoke test
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any

import pandas as pd

# --- path setup -------------------------------------------------------------
# graph_builder.py lives at services/optimizer/app/ and imports services.*
# package-style → repo root must be on sys.path.
# line_partitioner.py lives at services/optimizer/graph/ and imports
# sequence_optimizer module-style → that folder must be on sys.path too.
REPO_ROOT: Path = Path(__file__).resolve().parents[3]
_GRAPH_DIR: Path = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(_GRAPH_DIR) not in sys.path:
    sys.path.insert(0, str(_GRAPH_DIR))

from services.optimizer.app.graph_builder import (  # noqa: E402
    build_historical_wo_graph,
    build_planning_graph,
)
from services.node_cost_ml.app.inference import load_artefacts  # noqa: E402

from line_partitioner import (  # noqa: E402  (after path setup)
    PartitionResult,
    partition_from_graph,
    verify_partition,
)

# --- data paths -------------------------------------------------------------
CLEAN_DIR: Path = REPO_ROOT / "data" / "clean"
DEMAND_CSV: Path = CLEAN_DIR / "demand.csv"
CAPABILITY_CSV: Path = CLEAN_DIR / "line_capability.csv"
CHANGEOVER_CSV: Path = CLEAN_DIR / "changeover_costs.csv"
WO_MASTER_CSV: Path = CLEAN_DIR / "wo_master.csv"
WO_CHANGEOVERS_CSV: Path = CLEAN_DIR / "wo_changeovers.csv"
OUT_CSV: Path = REPO_ROOT / "data_experiment" / "evaluation_all_windows.csv"

LINE_IDS: tuple[int, ...] = (14, 17, 19)
_MISSING_EDGE_HOURS: float = 8.0


# ---------------------------------------------------------------------------
# Per-window evaluation
# ---------------------------------------------------------------------------

def _verify_callables(G: Any) -> tuple[Any, Any, Any]:
    """Build the three cost callables verify_partition needs.

    Mirrors the closures inside ``partition_from_graph`` so the
    independent recomputation hits the exact same edge/node values."""

    def can_produce(sku: str, line: int, _G=G) -> bool:
        return line in _G.nodes[sku].get("line_data", {})

    def node_cost(sku: str, line: int, _G=G) -> float:
        ld = _G.nodes[sku].get("line_data", {}).get(line)
        if ld is None:
            return _MISSING_EDGE_HOURS
        return float(ld["predicted_hours"])

    def edge_cost(a: str, b: str, line: int, _G=G) -> float:
        if a == b:
            return 0.0
        d = _G.get_edge_data(a, b, key=line)
        if d is None:
            return _MISSING_EDGE_HOURS
        return float(d["hours"])

    return can_produce, edge_cost, node_cost


def _historical_baseline(
    wid: str,
    demand_df: pd.DataFrame,
    wo_df: pd.DataFrame,
    wo_co_df: pd.DataFrame,
    lm: Any,
) -> dict[str, Any] | None:
    """Compute the *no-optimiser* baseline makespan from the historical plan.

    The baseline is built from :func:`build_historical_wo_graph`, which
    reconstructs the actual production path taken on each line during
    ``window_id`` (one ``nx.DiGraph`` per line, run-nodes in execution order
    with theoretical changeover edges from the same Tabla CF Prat used by
    the optimiser).

    For each line we sum:

    * ``prod_pred`` — ML ``predicted_hours`` on every run-node. Uses the same
      CatBoost model the optimiser scores against, so this is an
      apples-to-apples comparison *of the cost model*; the only difference
      is the ordering / partitioning.
    * ``prod_actual`` — the real ``productive_hours`` from ``wo_master.csv``
      (machine-running time only — excludes downtime / incidents the
      optimiser cannot see). This is the "what really happened on the floor"
      number, useful as context but biased by realised incidents.
    * ``chg`` — theoretical changeover hours on the historical sequence
      edges (same source as the optimiser's edge cost — Tabla CF Prat).

    Returns ``None`` for forecast windows (no historical production WOs
    falling in this window's ``end_day`` range) — the caller skips those
    rows from the baseline-comparison aggregate.
    """
    graphs = build_historical_wo_graph(
        wid, demand_df=demand_df, wo_df=wo_df, wo_co_df=wo_co_df, ml_model=lm,
    )
    if not any(g.number_of_nodes() > 0 for g in graphs.values()):
        return None

    per_line: dict[int, dict[str, float]] = {}
    for line, G in graphs.items():
        prod_pred = sum(d.get("predicted_hours", 0.0) for _, d in G.nodes(data=True))
        prod_actual = sum(d.get("actual_hours", 0.0) for _, d in G.nodes(data=True))
        chg = sum(d.get("hours", 0.0) for _, _, d in G.edges(data=True))
        per_line[line] = {
            "prod_pred_h": prod_pred,
            "prod_actual_h": prod_actual,
            "chg_h": chg,
            "load_pred_h": prod_pred + chg,
            "load_actual_h": prod_actual + chg,
            "n_runs": G.number_of_nodes(),
        }
    makespan_pred = max(v["load_pred_h"] for v in per_line.values())
    makespan_actual = max(v["load_actual_h"] for v in per_line.values())
    return {
        "per_line": per_line,
        "makespan_pred_h": makespan_pred,
        "makespan_actual_h": makespan_actual,
    }


def _record(
    wid: str,
    n_demand_skus: int,
    G: Any,
    result: PartitionResult,
    verify_ok: bool,
    graph_build_s: float,
    baseline: dict[str, Any] | None,
) -> dict[str, Any]:
    """Flatten one window's outcome into a single CSV row.

    ``baseline`` (if not ``None``) injects the historical no-optimiser
    makespan and the resulting improvement metrics so each row carries the
    optimiser vs baseline diff for downstream analysis."""
    spread = (
        result.makespan_hours - min(result.makespan_per_line_hours.values())
        if result.makespan_per_line_hours
        else 0.0
    )
    row: dict[str, Any] = {
        "window_id": wid,
        "n_skus_in_demand": n_demand_skus,
        "n_skus_in_graph": G.number_of_nodes(),
        "makespan_h": round(result.makespan_hours, 4),
        "total_h": round(result.total_hours, 4),
        "spread_h": round(spread, 4),
        "dropped": len(result.dropped),
        "feasible": result.feasible,
        "iterations": result.iterations,
        "elapsed_s": round(result.elapsed_s, 4),
        "graph_build_s": round(graph_build_s, 4),
        "verify_ok": verify_ok,
    }
    for line in LINE_IDS:
        row[f"n_L{line}"] = len(result.sequences.get(line, ()))
        row[f"prod_L{line}_h"] = round(result.production_hours_per_line.get(line, 0.0), 4)
        row[f"chg_L{line}_h"] = round(result.changeover_hours_per_line.get(line, 0.0), 4)
        row[f"load_L{line}_h"] = round(result.makespan_per_line_hours.get(line, 0.0), 4)

    if baseline is None:
        row["baseline_pred_h"] = None
        row["baseline_actual_h"] = None
        row["improvement_vs_pred_h"] = None
        row["improvement_vs_pred_pct"] = None
        row["improvement_vs_actual_h"] = None
        row["improvement_vs_actual_pct"] = None
    else:
        bp = float(baseline["makespan_pred_h"])
        ba = float(baseline["makespan_actual_h"])
        row["baseline_pred_h"] = round(bp, 4)
        row["baseline_actual_h"] = round(ba, 4)
        row["improvement_vs_pred_h"] = round(bp - result.makespan_hours, 4)
        row["improvement_vs_pred_pct"] = (
            round((bp - result.makespan_hours) / bp * 100.0, 2) if bp > 0 else None
        )
        row["improvement_vs_actual_h"] = round(ba - result.makespan_hours, 4)
        row["improvement_vs_actual_pct"] = (
            round((ba - result.makespan_hours) / ba * 100.0, 2) if ba > 0 else None
        )
    return row


def run_all(
    *,
    time_budget_s: float,
    move_strategy: str,
    delta_balance_h: float,
    limit: int | None,
) -> pd.DataFrame:
    """Run the partitioner on every window. Returns the per-window DataFrame.

    Loads the demand / capability / changeover tables exactly once and reuses
    them across every ``build_planning_graph`` call so we're measuring the
    *algorithm* — not pandas CSV parsing.
    """
    demand = pd.read_csv(DEMAND_CSV)
    capability = pd.read_csv(CAPABILITY_CSV)
    changeovers = pd.read_csv(CHANGEOVER_CSV)
    wo_master = pd.read_csv(WO_MASTER_CSV, parse_dates=["end_day"])
    wo_changeovers = pd.read_csv(WO_CHANGEOVERS_CSV, parse_dates=["transition_day"])
    lm = load_artefacts()

    windows = sorted(demand["window_id"].unique())
    if limit is not None:
        windows = windows[:limit]

    records: list[dict[str, Any]] = []
    n_total = len(windows)
    for i, wid in enumerate(windows, 1):
        n_demand = int(demand[demand["window_id"] == wid]["sku_id"].nunique())

        t0 = time.perf_counter()
        G = build_planning_graph(
            wid,
            demand_df=demand,
            capability_df=capability,
            changeover_df=changeovers,
            ml_model=lm,
        )
        graph_build_s = time.perf_counter() - t0

        if G.number_of_nodes() == 0:
            print(f"[{i:>2}/{n_total}] {wid}  (empty graph — skipped)")
            continue

        result = partition_from_graph(
            G,
            time_budget_s=time_budget_s,
            move_strategy=move_strategy,
            delta_balance_h=delta_balance_h,
        )
        can_p, ec, nc = _verify_callables(G)
        report = verify_partition(result, list(G.nodes), can_p, ec, nc)

        baseline = _historical_baseline(wid, demand, wo_master, wo_changeovers, lm)

        records.append(
            _record(wid, n_demand, G, result, report.ok, graph_build_s, baseline)
        )

        spread = (
            result.makespan_hours - min(result.makespan_per_line_hours.values())
        )
        flag = "OK" if report.ok else "FAIL"
        if baseline is not None:
            bp = baseline["makespan_pred_h"]
            ba = baseline["makespan_actual_h"]
            imp_pred_pct = (bp - result.makespan_hours) / bp * 100.0 if bp else 0.0
            imp_actual_pct = (ba - result.makespan_hours) / ba * 100.0 if ba else 0.0
            base_txt = (
                f"base(pred)={bp:6.2f}h ({imp_pred_pct:+5.1f}%)  "
                f"base(act)={ba:6.2f}h ({imp_actual_pct:+5.1f}%)"
            )
        else:
            base_txt = "base=N/A (forecast window)"
        print(
            f"[{i:>2}/{n_total}] {wid}  n={n_demand:>2}  "
            f"makespan={result.makespan_hours:6.2f}h  "
            f"{base_txt}  "
            f"spread={spread:4.1f}h  drop={len(result.dropped)}  "
            f"t={result.elapsed_s:5.2f}s  verify={flag}"
        )

    return pd.DataFrame.from_records(records)


# ---------------------------------------------------------------------------
# Summary block
# ---------------------------------------------------------------------------

def summarise(df: pd.DataFrame) -> None:
    """Print the headline aggregate stats on stdout."""
    if df.empty:
        print("\nNo windows evaluated.")
        return

    ms = df["makespan_h"]
    print(f"\n=== Aggregate stats across {len(df)} windows ===")
    print(f"  mean   max time (makespan): {ms.mean():7.2f} h    <- headline metric")
    print(f"  median max time           : {ms.median():7.2f} h")
    print(f"  stdev  max time           : {ms.std():7.2f} h")
    print(f"  min  / max                : {ms.min():7.2f} h / {ms.max():7.2f} h")
    print(f"  P25  / P75                : {ms.quantile(0.25):7.2f} h / {ms.quantile(0.75):7.2f} h")

    print(f"\n  mean total work (sum T_i) : {df['total_h'].mean():7.2f} h")
    print(f"  mean spread (max-min)     : {df['spread_h'].mean():7.2f} h")
    print(f"  mean SKUs / window        : {df['n_skus_in_graph'].mean():7.2f}")
    print(f"  mean iterations           : {df['iterations'].mean():7.2f}")
    print(f"  mean elapsed (algo only)  : {df['elapsed_s'].mean():7.2f} s")
    print(f"  mean graph-build time     : {df['graph_build_s'].mean():7.2f} s")

    drops = (df["dropped"] > 0).sum()
    print(f"\n  windows with drops        : {drops}/{len(df)}")
    print(f"  windows verify-OK         : {df['verify_ok'].sum()}/{len(df)}")
    if not df["verify_ok"].all():
        bad = df[~df["verify_ok"]]["window_id"].tolist()
        print(f"  ! verify failures         : {bad}")

    # --- baseline comparison block ----------------------------------------
    base_df = df.dropna(subset=["baseline_pred_h"])
    n_base = len(base_df)
    if n_base == 0:
        print("\n  (no historical baseline available — all windows are forecasts)")
    else:
        opt_ms = base_df["makespan_h"]
        bp = base_df["baseline_pred_h"]
        ba = base_df["baseline_actual_h"]
        imp_p = base_df["improvement_vs_pred_h"]
        imp_a = base_df["improvement_vs_actual_h"]
        imp_pp = base_df["improvement_vs_pred_pct"]
        imp_ap = base_df["improvement_vs_actual_pct"]
        wins_p = (imp_p > 0).sum()
        wins_a = (imp_a > 0).sum()

        print(
            f"\n=== Baseline comparison "
            f"({n_base} windows with historical data; "
            f"{len(df) - n_base} forecast windows excluded) ==="
        )
        print(f"  optimiser mean max time   : {opt_ms.mean():7.2f} h")
        print(f"  baseline  mean max (pred) : {bp.mean():7.2f} h    "
              f"<- apples-to-apples ML cost on historical order")
        print(f"  baseline  mean max (act)  : {ba.mean():7.2f} h    "
              f"<- real productive_hours on historical order")
        print()
        print(f"  mean improvement (pred)   : {imp_p.mean():+7.2f} h  "
              f"({imp_pp.mean():+5.2f}%)")
        print(f"  mean improvement (actual) : {imp_a.mean():+7.2f} h  "
              f"({imp_ap.mean():+5.2f}%)")
        print(f"  median improvement (pred) : {imp_p.median():+7.2f} h  "
              f"({imp_pp.median():+5.2f}%)")
        print(f"  median improvement (act)  : {imp_a.median():+7.2f} h  "
              f"({imp_ap.median():+5.2f}%)")
        print()
        print(f"  optimiser wins vs pred    : {wins_p}/{n_base}")
        print(f"  optimiser wins vs actual  : {wins_a}/{n_base}")

    # Per-line averages
    print("\n  per-line average load (h):")
    for line in LINE_IDS:
        col = f"load_L{line}_h"
        if col in df.columns:
            print(
                f"    L{line}: load={df[col].mean():6.2f}  "
                f"prod={df[f'prod_L{line}_h'].mean():6.2f}  "
                f"chg={df[f'chg_L{line}_h'].mean():5.2f}"
            )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--budget", type=float, default=4.0,
        help="time_budget_s per window (default: 4.0)",
    )
    p.add_argument(
        "--strategy", choices=["best_improvement", "first_improvement"],
        default="best_improvement",
        help="move acceptance strategy (default: best_improvement)",
    )
    p.add_argument(
        "--delta", type=float, default=0.5,
        help="delta_balance_h threshold for balance-repair (default: 0.5, grid-search Pareto knee)",
    )
    p.add_argument(
        "--limit", type=int, default=None,
        help="evaluate only the first N windows (smoke test)",
    )
    p.add_argument(
        "--csv", type=Path, default=OUT_CSV,
        help=f"output CSV path (default: {OUT_CSV.relative_to(REPO_ROOT)})",
    )
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    print(
        f"Evaluation config: budget={args.budget}s  strategy={args.strategy}  "
        f"delta_balance={args.delta}h  limit={args.limit}\n"
    )
    df = run_all(
        time_budget_s=args.budget,
        move_strategy=args.strategy,
        delta_balance_h=args.delta,
        limit=args.limit,
    )
    summarise(df)

    args.csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.csv, index=False)
    print(f"\nWrote: {args.csv.relative_to(REPO_ROOT)}  ({len(df)} rows)")


if __name__ == "__main__":
    main()
