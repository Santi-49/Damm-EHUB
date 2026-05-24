"""Real-data adapter for the ``/graph`` prototype.

Loads ``data/clean/*.csv`` (the canonical ETL output described in
``docs/data/overview.md``) and exposes the **same callable API** the
synthetic ``generate_test_data`` module does, so the rest of the pipeline
(``sequence_optimizer``, ``line_partitioner``, ``visualize_graph``) is
unchanged.

Mapping summary
---------------

* ``SKU`` metadata  — ``data/clean/skus.csv``           ➜ :class:`SkuMeta`
* SKU × line feasibility & speed — ``data/clean/line_capability.csv``
* Per-line changeover hours      — ``data/clean/changeover_costs.csv``
                                   (source: ``tabla_cf_prat``, symmetric)
* Weekly demand                  — ``data/clean/demand.csv``
* Historical work-order context  — ``data/clean/wo_master.csv``
                                   (used only for UI tooltips; the planner
                                   itself ignores it)

Choice of demo window
---------------------

The mean number of unique SKUs per week in ``demand.csv`` is **~32**
(median 33, P25/P75 = 29/37, min/max = 7/45). :func:`pick_demo_window`
returns the window whose SKU count is closest to that mean — by default
``2025-W13-7d`` (n=32). The graph algorithms are therefore tuned for the
**mean case**: ~32 nodes total, ~10-12 per line.

All API entry points are *line-aware* and pure functions of their inputs —
they close over the loaded tables once and stay cheap (~O(1) dict lookups)
per call, so the ALNS partitioner can re-evaluate edges thousands of times
within its time budget.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Hashable

import pandas as pd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT: Path = Path(__file__).resolve().parents[3]
CLEAN_DIR: Path = REPO_ROOT / "data" / "clean"

DEMAND_CSV: Path = CLEAN_DIR / "demand.csv"
SKUS_CSV: Path = CLEAN_DIR / "skus.csv"
LINE_CAPABILITY_CSV: Path = CLEAN_DIR / "line_capability.csv"
CHANGEOVER_COSTS_CSV: Path = CLEAN_DIR / "changeover_costs.csv"
WO_MASTER_CSV: Path = CLEAN_DIR / "wo_master.csv"


# ---------------------------------------------------------------------------
# Domain constants (mirror the LineWise hard capability matrix)
# ---------------------------------------------------------------------------

LINE_IDS: tuple[int, ...] = (14, 17, 19)

LINE_CONTAINER_TYPES: dict[int, frozenset[str]] = {
    14: frozenset({"1/3", "1/2"}),
    17: frozenset({"1/3"}),
    19: frozenset({"1/3", "1/2", "2/5"}),
}

# ---------------------------------------------------------------------------
# Node-cost constants (kept aligned with generate_test_data — the user
# confirmed the synthetic formula `units / speed + ramp_up` is the right
# shape; here we just use the *real* per-line speed from line_capability).
# ---------------------------------------------------------------------------

RAMP_UP_HOURS: float = 0.5
# Fallback speed if a (sku, line) is missing from line_capability — keeps
# the cost finite so the ALNS penalty (not the lookup) is what discourages
# infeasible placements.
_FALLBACK_SPEED_UDS_H: float = 60_000.0
# Missing edge cost (should not happen if partitioner respects can_produce;
# kept as a finite penalty so a stray lookup doesn't crash the optimiser).
_MISSING_EDGE_HOURS: float = 8.0


# ---------------------------------------------------------------------------
# SKU dataclass — minimal compatible with what visualize / partitioner need
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SkuMeta:
    sku_id: str
    container_type: str
    brand: str
    family: str
    primary_packaging: str
    secondary_packaging: str
    units_per_case: int
    volume_cl: int

    @staticmethod
    def _container_to_cl(ct: str) -> int:
        return {"1/3": 33, "1/2": 50, "2/5": 44}.get(ct, 0)

    @classmethod
    def from_row(cls, row: pd.Series) -> "SkuMeta":
        return cls(
            sku_id=str(row["sku_id"]),
            container_type=str(row["container_type"]),
            brand=str(row.get("brand", "UNKNOWN") or "UNKNOWN"),
            family=str(row.get("family", "UNKNOWN") or "UNKNOWN"),
            primary_packaging=str(row.get("primary_packaging", "UNKNOWN") or "UNKNOWN"),
            secondary_packaging=str(row.get("secondary_packaging", "UNKNOWN") or "UNKNOWN"),
            units_per_case=int(row.get("units_per_case") or 24),
            volume_cl=cls._container_to_cl(str(row["container_type"])),
        )


# ---------------------------------------------------------------------------
# Cached loaders — read CSVs exactly once, then everything is in-memory
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def load_sku_catalog() -> dict[str, SkuMeta]:
    """Return ``{sku_id: SkuMeta}`` for every SKU in ``skus.csv``."""
    df = pd.read_csv(SKUS_CSV)
    return {str(r["sku_id"]): SkuMeta.from_row(r) for _, r in df.iterrows()}


@lru_cache(maxsize=1)
def load_capability() -> tuple[dict[tuple[str, int], bool], dict[tuple[str, int], float]]:
    """Return (``can_produce_map``, ``median_speed_map``).

    Keyed by ``(sku_id, line_id)``. ``can_produce_map`` defaults to
    ``False`` for missing pairs; ``median_speed_map`` defaults to
    :data:`_FALLBACK_SPEED_UDS_H`.
    """
    df = pd.read_csv(LINE_CAPABILITY_CSV)
    can: dict[tuple[str, int], bool] = {}
    spd: dict[tuple[str, int], float] = {}
    for _, r in df.iterrows():
        key = (str(r["sku_id"]), int(r["line_id"]))
        can[key] = bool(r["can_produce"])
        spd[key] = float(r["median_speed_uds_per_hour"])
    return can, spd


@lru_cache(maxsize=1)
def load_changeover_costs() -> dict[tuple[int, str, str], float]:
    """Return ``{(line_id, sku_from, sku_to): total_hours}`` from
    ``tabla_cf_prat``. Symmetric in the source data; the optimiser does
    not assume symmetry so future ML deltas can drop in without changes.
    """
    df = pd.read_csv(CHANGEOVER_COSTS_CSV, usecols=["line_id", "sku_from_id", "sku_to_id", "total_hours"])
    return {
        (int(r.line_id), str(r.sku_from_id), str(r.sku_to_id)): float(r.total_hours)
        for r in df.itertuples(index=False)
    }


@lru_cache(maxsize=1)
def load_demand_table() -> pd.DataFrame:
    """Return the raw ``demand.csv`` (a single table covering every window)."""
    return pd.read_csv(DEMAND_CSV)


@lru_cache(maxsize=1)
def load_wo_last_per_sku() -> dict[str, str]:
    """Return ``{sku_id: most_recent_production_wo_id}`` for UI tooltips."""
    if not WO_MASTER_CSV.exists():
        return {}
    df = pd.read_csv(WO_MASTER_CSV, usecols=["wo_id", "sku_id", "end_day", "wo_kind"])
    df = df[df["wo_kind"] == "production"].copy()
    df["end_day"] = pd.to_datetime(df["end_day"], errors="coerce")
    df = df.sort_values("end_day", ascending=False)
    return df.groupby("sku_id")["wo_id"].first().to_dict()


# ---------------------------------------------------------------------------
# Demand window selection
# ---------------------------------------------------------------------------

def list_demand_windows() -> pd.DataFrame:
    """Diagnostic helper — counts of SKUs and units per window."""
    d = load_demand_table()
    return (
        d.groupby("window_id")
        .agg(n_skus=("sku_id", "nunique"), total_units=("units_demanded", "sum"))
        .sort_index()
    )


def pick_demo_window(target_n_skus: int = 32) -> str:
    """Pick the demand window whose SKU count is closest to ``target_n_skus``.

    The 2025 history has mean=32, median=33 SKUs per week, so the default
    32 lands on the *mean* case the graph algorithms are tuned for.
    """
    counts = list_demand_windows()["n_skus"]
    delta = (counts - target_n_skus).abs()
    return str(delta.sort_values().index[0])


def load_window_demand(window_id: str) -> list[dict[str, Any]]:
    """Return demand rows for one window, shape-compatible with
    ``generate_test_data.build_demand`` so downstream code is identical.
    """
    d = load_demand_table()
    sub = d[d["window_id"] == window_id]
    if sub.empty:
        raise KeyError(f"window {window_id!r} not in demand.csv")
    # Aggregate in case a SKU appears twice in one window (shouldn't, but cheap)
    agg = (
        sub.groupby(["window_id", "window_start", "window_end", "sku_id"], as_index=False)
        .agg(units_demanded=("units_demanded", "sum"), priority=("priority", "min"))
    )
    agg["source"] = "real_history"
    return agg.to_dict(orient="records")


# ---------------------------------------------------------------------------
# Public cost callables — drop-in replacement for generate_test_data
# ---------------------------------------------------------------------------

def can_produce(sku_id: str, line_id: int) -> bool:
    can, _ = load_capability()
    # Trust the explicit table; fall back to the container-type rule for
    # SKUs the table has no row for (defensive — should not happen on the
    # canonical ETL output).
    if (sku_id, line_id) in can:
        return can[(sku_id, line_id)]
    sku = load_sku_catalog().get(sku_id)
    if sku is None:
        return False
    return sku.container_type in LINE_CONTAINER_TYPES[line_id]


def median_speed_uds_per_hour(sku_id: str, line_id: int) -> float:
    _, spd = load_capability()
    return spd.get((sku_id, line_id), _FALLBACK_SPEED_UDS_H)


def get_node_cost(sku_id: str, units_demanded: int, line_id: int) -> float:
    """Production hours on ``line_id`` for ``units_demanded`` of ``sku_id``.

    Same shape as the synthetic formula (``units / speed + ramp_up``) but
    the speed is the *real* ``median_speed_uds_per_hour`` from
    ``line_capability.csv``.
    """
    speed = max(median_speed_uds_per_hour(sku_id, line_id), 1.0)
    return round(units_demanded / speed + RAMP_UP_HOURS, 4)


def get_transition_cost(sku_a_id: str, sku_b_id: str, line_id: int) -> float:
    """Per-line changeover hours from ``tabla_cf_prat``.

    Symmetric in the source. Missing pairs (one of the SKUs not feasible on
    the line) return a finite penalty rather than ``inf`` so the ALNS
    arithmetic stays well-conditioned.
    """
    if sku_a_id == sku_b_id:
        return 0.0
    return load_changeover_costs().get(
        (line_id, sku_a_id, sku_b_id), _MISSING_EDGE_HOURS,
    )


def get_last_wo_for_sku(sku_id: str) -> str:
    """Most recent historical production WO for ``sku_id`` — UI only."""
    return load_wo_last_per_sku().get(sku_id, "—")


# ---------------------------------------------------------------------------
# Convenience: build the four datasets the demo scripts consume
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class WindowDataset:
    window_id: str
    sku_ids: tuple[str, ...]
    units_by_sku: dict[str, int]
    sku_by_id: dict[str, SkuMeta]


def load_window_dataset(window_id: str | None = None) -> WindowDataset:
    """Bundle window demand + SKU metadata in one ready-to-use object."""
    wid = window_id or pick_demo_window()
    demand = load_window_demand(wid)
    catalog = load_sku_catalog()
    sku_ids = tuple(r["sku_id"] for r in demand)
    units = {r["sku_id"]: int(r["units_demanded"]) for r in demand}
    sku_by = {sid: catalog[sid] for sid in sku_ids if sid in catalog}
    if len(sku_by) != len(sku_ids):
        missing = [s for s in sku_ids if s not in catalog]
        raise KeyError(f"{len(missing)} demand SKUs not in skus.csv: {missing[:5]}…")
    return WindowDataset(
        window_id=wid, sku_ids=sku_ids, units_by_sku=units, sku_by_id=sku_by,
    )


# ---------------------------------------------------------------------------
# Self-check entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    counts = list_demand_windows()
    print(f"[demand] {len(counts)} weeks, "
          f"mean={counts['n_skus'].mean():.2f} median={counts['n_skus'].median():.0f} "
          f"min={counts['n_skus'].min()} max={counts['n_skus'].max()} SKUs/week")
    wid = pick_demo_window()
    ds = load_window_dataset(wid)
    print(f"[demo window] {ds.window_id}  n_skus={len(ds.sku_ids)} "
          f"total_units={sum(ds.units_by_sku.values()):,}")
    # Smoke-test the callables on the first feasible pair
    a, b = ds.sku_ids[0], ds.sku_ids[1]
    for ln in LINE_IDS:
        print(
            f"  L{ln}: can_produce({a})={can_produce(a, ln)}  "
            f"node_cost({a}, {ds.units_by_sku[a]:,})={get_node_cost(a, ds.units_by_sku[a], ln):.2f}h  "
            f"edge({a}->{b})={get_transition_cost(a, b, ln):.2f}h"
        )
