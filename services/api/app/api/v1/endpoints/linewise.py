"""LineWise endpoints — implements points 1, 2, 3 of LINEWISE_API_CONTRACT.md.

All routes are public (no auth) for demo convenience.
Base prefix /api/v1 is added by the parent router.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.schemas.linewise import (
    CompareBundle,
    PlanOptimizeRequest,
    PlanOptimizeResponse,
    ReplanRequest,
    ReplanScenario,
    WeekOption,
)
from app.services.linewise_orchestrator import orchestrator

router = APIRouter(prefix="/linewise", tags=["linewise"])


# ---------------------------------------------------------------------------
# 1. List comparable weeks
# ---------------------------------------------------------------------------

@router.get("/weeks", response_model=list[WeekOption])
async def list_weeks() -> list[WeekOption]:
    """Return selectable planning weeks with production stats."""
    try:
        return orchestrator.list_weeks()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# 2. Compare real vs LineWise for a given week
# ---------------------------------------------------------------------------

@router.get("/compare", response_model=CompareBundle)
async def compare_week(
    week_id: str = Query(..., description="Window ID, e.g. 2025-W30-7d"),
) -> CompareBundle:
    """Build real + optimised sequences and simulation reports for a week."""
    try:
        return orchestrator.compare(week_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# 3. Optimize an ad-hoc demand plan
# ---------------------------------------------------------------------------

@router.post("/optimize", response_model=PlanOptimizeResponse)
async def optimize_plan(body: PlanOptimizeRequest) -> PlanOptimizeResponse:
    """Build planning graph for the given demand and return the optimised path."""
    if not body.products:
        raise HTTPException(status_code=422, detail="products list must not be empty")
    try:
        return orchestrator.optimize(body)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# 4. What-if replan after a line breakdown
# ---------------------------------------------------------------------------

@router.post("/replan", response_model=ReplanScenario)
async def replan_scenario(body: ReplanRequest) -> ReplanScenario:
    """Re-plan the remainder of the week after a line goes offline for maintenance."""
    if body.breakdown_line is None or body.breakdown_day is None:
        raise HTTPException(
            status_code=422,
            detail="breakdown_line and breakdown_day are required",
        )
    try:
        return orchestrator.replan(body)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
