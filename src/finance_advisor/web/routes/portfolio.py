from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import Field

from finance_advisor.allocation.service import AllocationPercentage, build_portfolio_plan
from finance_advisor.schemas import InvestorProfileInput, error_response, success_response


class PortfolioPlanRequest(InvestorProfileInput):
    current_allocation_pct: dict[str, AllocationPercentage] | None = Field(
        default=None,
        description="Optional current allocation percentages keyed by asset class.",
    )


router = APIRouter()


@router.post("/plan", response_model=None)
def portfolio_plan(request: PortfolioPlanRequest) -> dict[str, object] | JSONResponse:
    try:
        plan = build_portfolio_plan(request, request.current_allocation_pct)
    except ValueError as exc:
        return JSONResponse(
            status_code=400,
            content=error_response("invalid_portfolio_plan_request", str(exc)),
        )

    return success_response(
        plan,
        source="system",
        warnings=["该配置计划仅用于课程演示，不构成投资建议。"],
    )
