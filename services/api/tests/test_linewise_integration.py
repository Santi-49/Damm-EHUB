"""Integration tests for LinewiseOrchestrator — real inference, no mocking.

Calls the orchestrator functions directly (no HTTP layer) to get accurate
timing per stage. Run from the repo root:

    python -m pytest services/api/tests/test_linewise_integration.py -v -s

Requires clean CSV data at data/clean/*.csv.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

# Make sure repo root and services/api/app are importable
_REPO_ROOT = Path(__file__).resolve().parents[3]
_API_APP = _REPO_ROOT / "services" / "api"
for p in [str(_REPO_ROOT), str(_API_APP)]:
    if p not in sys.path:
        sys.path.insert(0, p)

# ---- Import orchestrator (and transitively optimizer) ----
from app.services.linewise_orchestrator import LinewiseOrchestrator  # noqa: E402
from app.schemas.linewise import (  # noqa: E402
    CompareBundle,
    PlanOptimizeRequest,
    PlanOptimizeResponse,
    ProductDemand,
    ReplanRequest,
    ReplanScenario,
    WeekOption,
)

# Week choices
FAST_WEEK_ID = "2025-W01-7d"    # 7 SKUs  — fastest
MEDIUM_WEEK_ID = "2025-W10-7d"  # 38 SKUs — same as benchmark report

# SKUs that exist in demand.csv for FAST_WEEK_ID
FAST_WEEK_SKUS = ["ED13LP12", "ED13LTW", "TU13LTN", "VI13L6N"]
ALL_FAST_WEEK_SKUS = [
    "ED13LP12", "ED13LTW", "TU13LTN", "VI13L6N",
    "VI13LN", "VI13LP6M", "VO13LTNN",
]

_timings: dict[str, float] = {}


# ---------------------------------------------------------------------------
# Shared fixture — one orchestrator per session to reuse CSV caches
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def orc() -> LinewiseOrchestrator:
    return LinewiseOrchestrator()


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _timed(label: str, fn, *args, **kwargs):
    t0 = time.perf_counter()
    result = fn(*args, **kwargs)
    elapsed = time.perf_counter() - t0
    _timings[label] = elapsed
    return result, elapsed


# ---------------------------------------------------------------------------
# 1. list_weeks
# ---------------------------------------------------------------------------

class TestListWeeks:

    def test_returns_list(self, orc):
        weeks, elapsed = _timed("list_weeks()", orc.list_weeks)
        print(f"\n  list_weeks(): {elapsed:.3f}s — {len(weeks)} weeks")
        assert isinstance(weeks, list)
        assert len(weeks) > 0

    def test_schema(self, orc):
        weeks = orc.list_weeks()
        for w in weeks:
            assert isinstance(w, WeekOption)
            assert w.id
            assert w.source in ("demo", "historical")

    def test_timing(self, orc):
        _, elapsed = _timed("list_weeks() [2nd call]", orc.list_weeks)
        print(f"\n  list_weeks() (cached): {elapsed:.3f}s")
        assert elapsed < 5.0


# ---------------------------------------------------------------------------
# 2a. compare — fast week (7 SKUs)
# ---------------------------------------------------------------------------

class TestCompareFastWeek:

    @pytest.fixture(scope="class")
    def bundle(self, orc):
        result, elapsed = _timed(f"compare({FAST_WEEK_ID})", orc.compare, FAST_WEEK_ID)
        print(f"\n  compare({FAST_WEEK_ID}, 7 SKUs): {elapsed:.3f}s")
        return result

    def test_returns_bundle(self, bundle):
        assert isinstance(bundle, CompareBundle)

    def test_sequences_not_empty(self, bundle):
        assert len(bundle.real_sequence.slots) > 0, "real_sequence has no slots"
        assert len(bundle.opt_sequence.slots) > 0, "opt_sequence has no slots"

    def test_sequence_sources(self, bundle):
        assert bundle.real_sequence.source == "real"
        assert bundle.opt_sequence.source == "opt"

    def test_slot_lines_valid(self, bundle):
        for slot in bundle.opt_sequence.slots:
            assert slot.line in (14, 17, 19), f"Invalid line: {slot.line}"

    def test_slot_kinds_valid(self, bundle):
        valid_kinds = {"production", "changeover", "cleaning", "maintenance"}
        for slot in bundle.opt_sequence.slots + bundle.real_sequence.slots:
            assert slot.kind in valid_kinds, f"Invalid kind: {slot.kind}"

    def test_simulation_reports(self, bundle):
        for rep in (bundle.real_simulation, bundle.opt_simulation):
            assert 0.0 <= rep.oee_global <= 1.0, f"oee_global out of range: {rep.oee_global}"
            assert rep.h_productive >= 0.0
            assert rep.makespan_h >= 0.0
            assert 0.0 <= rep.coverage <= 1.0

    def test_delta_computed(self, bundle):
        d = bundle.delta
        assert isinstance(d.oee_pp, float)
        assert isinstance(d.h_changes_saved, float)
        assert isinstance(d.h_productive_gained, float)
        assert isinstance(d.coverage_delta, float)

    def test_week_ids_match(self, bundle):
        assert bundle.real_sequence.week_id == FAST_WEEK_ID
        assert bundle.opt_sequence.week_id == FAST_WEEK_ID

    def test_no_duplicate_slot_ids(self, bundle):
        opt_ids = [s.id for s in bundle.opt_sequence.slots]
        assert len(opt_ids) == len(set(opt_ids)), "Duplicate slot IDs in opt_sequence"

    def test_timestamps_ordered(self, bundle):
        for seq in (bundle.real_sequence, bundle.opt_sequence):
            line_slots: dict[int, list] = {}
            for slot in seq.slots:
                line_slots.setdefault(slot.line, []).append(slot)
            for line, slots in line_slots.items():
                for i in range(len(slots) - 1):
                    assert slots[i].end <= slots[i + 1].start, (
                        f"Line {line}: slot {i} end ({slots[i].end}) > "
                        f"slot {i+1} start ({slots[i+1].start})"
                    )

    def test_timing(self, orc):
        _, elapsed = _timed(f"compare({FAST_WEEK_ID}) [2nd call]", orc.compare, FAST_WEEK_ID)
        print(f"\n  compare({FAST_WEEK_ID}) 2nd call: {elapsed:.3f}s")
        assert elapsed < 60.0


# ---------------------------------------------------------------------------
# 2b. compare — medium week (38 SKUs)
# ---------------------------------------------------------------------------

class TestCompareMediumWeek:

    @pytest.fixture(scope="class")
    def bundle(self, orc):
        result, elapsed = _timed(f"compare({MEDIUM_WEEK_ID})", orc.compare, MEDIUM_WEEK_ID)
        print(f"\n  compare({MEDIUM_WEEK_ID}, 38 SKUs): {elapsed:.3f}s")
        return result

    def test_returns_bundle(self, bundle):
        assert isinstance(bundle, CompareBundle)

    def test_opt_slots_not_empty(self, bundle):
        assert len(bundle.opt_sequence.slots) > 0

    def test_all_lines_covered(self, bundle):
        lines_used = {s.line for s in bundle.opt_sequence.slots if s.kind == "production"}
        assert len(lines_used) >= 1, "No production slots assigned"

    def test_coverage_valid(self, bundle):
        assert 0.0 <= bundle.opt_simulation.coverage <= 1.0

    def test_timing(self, orc):
        _, elapsed = _timed(f"compare({MEDIUM_WEEK_ID}) [2nd call]", orc.compare, MEDIUM_WEEK_ID)
        print(f"\n  compare({MEDIUM_WEEK_ID}) 2nd call: {elapsed:.3f}s")
        assert elapsed < 120.0


# ---------------------------------------------------------------------------
# 3. optimize (ad-hoc plan)
# ---------------------------------------------------------------------------

class TestOptimize:

    @pytest.fixture(scope="class")
    def response_4skus(self, orc):
        req = PlanOptimizeRequest(
            products=[
                ProductDemand(sku_id=sku, quantity_units=50_000)
                for sku in FAST_WEEK_SKUS
            ]
        )
        result, elapsed = _timed("optimize(4 SKUs)", orc.optimize, req)
        print(f"\n  optimize(4 SKUs): {elapsed:.3f}s")
        return result

    @pytest.fixture(scope="class")
    def response_7skus(self, orc):
        req = PlanOptimizeRequest(
            products=[
                ProductDemand(sku_id=sku, quantity_units=100_000)
                for sku in ALL_FAST_WEEK_SKUS
            ]
        )
        result, elapsed = _timed("optimize(7 SKUs)", orc.optimize, req)
        print(f"\n  optimize(7 SKUs): {elapsed:.3f}s")
        return result

    def test_returns_response(self, response_4skus):
        assert isinstance(response_4skus, PlanOptimizeResponse)

    def test_makespan_positive(self, response_4skus):
        assert response_4skus.makespan_h >= 0.0

    def test_coverage_valid(self, response_4skus):
        assert 0.0 <= response_4skus.coverage_pct <= 1.0

    def test_node_line_ids_valid(self, response_4skus):
        for node in response_4skus.nodes:
            assert node.line_id in (14, 17, 19)

    def test_edge_path_values(self, response_4skus):
        for edge in response_4skus.edges:
            assert edge.path in ("opt", "baseline")

    def test_7_sku_plan(self, response_7skus):
        assert isinstance(response_7skus, PlanOptimizeResponse)
        assert response_7skus.makespan_h >= 0.0

    def test_timing_4_skus(self, orc):
        req = PlanOptimizeRequest(
            products=[ProductDemand(sku_id=sku, quantity_units=50_000) for sku in FAST_WEEK_SKUS]
        )
        _, elapsed = _timed("optimize(4 SKUs) [2nd call]", orc.optimize, req)
        print(f"\n  optimize(4 SKUs) 2nd call: {elapsed:.3f}s")
        assert elapsed < 60.0

    def test_empty_products_raises(self, orc):
        with pytest.raises(Exception):
            orc.optimize(PlanOptimizeRequest(products=[]))


# ---------------------------------------------------------------------------
# 4. replan what-if
# ---------------------------------------------------------------------------

class TestReplan:

    def test_urgent_replan_uses_explicit_week_id(self, orc):
        req = ReplanRequest(
            week_id=FAST_WEEK_ID,
            scenario_id="urgent-demand",
            introduced_at="2024-12-31T08:00:00",
            required_by="2025-01-03T18:00:00",
            urgent_sku="ED13LP12",
            urgent_units=1_000,
        )
        result, elapsed = _timed("replan(urgent, explicit week)", orc.replan, req)
        print(f"\n  replan(urgent, explicit week): {elapsed:.3f}s")

        assert isinstance(result, ReplanScenario)
        assert result.base_sequence.week_id == FAST_WEEK_ID
        assert result.sequence.week_id == FAST_WEEK_ID
        urgent_slots = [slot for slot in result.sequence.slots if slot.is_urgent]
        assert len(urgent_slots) == 1
        assert urgent_slots[0].units == 1_000


# ---------------------------------------------------------------------------
# 5. Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:

    def test_unknown_week_raises_key_error(self, orc):
        with pytest.raises(KeyError):
            orc.compare("2099-W99-7d")

    def test_weeks_all_have_ids(self, orc):
        for w in orc.list_weeks():
            assert w.id, "WeekOption has empty id"

    def test_optimize_unknown_skus(self, orc):
        req = PlanOptimizeRequest(
            products=[ProductDemand(sku_id="UNKNOWN_SKU_999", quantity_units=1000)]
        )
        # Should return empty nodes (SKU has no capability), not raise
        result = orc.optimize(req)
        assert isinstance(result, PlanOptimizeResponse)


# ---------------------------------------------------------------------------
# Summary hook
# ---------------------------------------------------------------------------

def pytest_terminal_summary(terminalreporter, exitstatus, config):
    if not _timings:
        return
    terminalreporter.write_sep("=", "LineWise timing summary")
    max_len = max(len(k) for k in _timings)
    rows = sorted(_timings.items(), key=lambda x: x[1], reverse=True)
    for label, t in rows:
        bar = "#" * min(40, int(t * 2))
        terminalreporter.write_line(f"  {label:<{max_len}}  {t:7.2f}s  {bar}")
