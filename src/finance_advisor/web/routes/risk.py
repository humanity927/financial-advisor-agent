from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from finance_advisor.market.symbols import SymbolValidationError
from finance_advisor.risk.portfolio import PortfolioValidationError
from finance_advisor.risk.service import (
    InvalidLookbackError,
    RiskDataUnavailableError,
    build_asset_risk_report,
    build_portfolio_risk_report,
    profile_assessment_data,
)
from finance_advisor.schemas import InvestorProfileInput, error_response, success_response
from finance_advisor.web.common import get_market_service

LOGGER = logging.getLogger(__name__)
router = APIRouter()


class AssetRiskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbols: list[str] = Field(min_length=1, max_length=4)
    lookback_days: int = Field(default=252, ge=60, le=1260)


class PortfolioRiskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    weights_pct: dict[str, float] = Field(min_length=1, max_length=4)
    lookback_days: int = Field(default=252, ge=60, le=1260)


def _json_error(
    status_code: int,
    code: str,
    message: str,
    *,
    retryable: bool = False,
    data: Any = None,
    request_id: str | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=error_response(
            code,
            message,
            retryable=retryable,
            data=data,
            request_id=request_id,
        ),
    )


@router.post("/profile", response_model=None)
def risk_profile(request: InvestorProfileInput) -> dict[str, Any]:
    """Return deterministic six-dimension investor risk assessment."""
    return success_response(profile_assessment_data(request))


@router.post("/assets", response_model=None)
def asset_risk(request: AssetRiskRequest) -> dict[str, Any] | JSONResponse:
    """Calculate historical risk metrics for up to four supported ETFs."""
    request_id = str(uuid4())
    try:
        report = build_asset_risk_report(
            get_market_service(),
            request.symbols,
            request.lookback_days,
        )
    except InvalidLookbackError as exc:
        return _json_error(400, "invalid_lookback", str(exc), request_id=request_id)
    except SymbolValidationError as exc:
        return _json_error(400, "invalid_symbol", str(exc), request_id=request_id)
    except RiskDataUnavailableError as exc:
        return _json_error(
            503,
            "risk_analysis_failed",
            str(exc),
            retryable=True,
            request_id=request_id,
        )
    except Exception:
        LOGGER.exception("asset risk failed request_id=%s", request_id)
        return _json_error(
            503,
            "risk_analysis_failed",
            "风险分析失败，请检查历史数据和行情服务",
            retryable=True,
            request_id=request_id,
        )
    return success_response(
        report.data,
        source=report.source,
        as_of=report.as_of,
        is_fallback=report.is_fallback,
        warnings=list(report.warnings),
        request_id=request_id,
    )


@router.post("/portfolio", response_model=None)
def portfolio_risk(request: PortfolioRiskRequest) -> dict[str, Any] | JSONResponse:
    """Calculate historical risk for a fixed-weight daily-rebalanced portfolio."""
    request_id = str(uuid4())
    try:
        report = build_portfolio_risk_report(
            get_market_service(),
            request.weights_pct,
            request.lookback_days,
        )
    except InvalidLookbackError as exc:
        return _json_error(400, "invalid_lookback", str(exc), request_id=request_id)
    except SymbolValidationError as exc:
        return _json_error(400, "invalid_symbol", str(exc), request_id=request_id)
    except PortfolioValidationError as exc:
        return _json_error(400, "invalid_weights", str(exc), request_id=request_id)
    except RiskDataUnavailableError as exc:
        return _json_error(
            503,
            "portfolio_risk_failed",
            str(exc),
            retryable=True,
            request_id=request_id,
        )
    except Exception:
        LOGGER.exception("portfolio risk failed request_id=%s", request_id)
        return _json_error(
            503,
            "portfolio_risk_failed",
            "组合风险计算失败，请检查历史数据和权重",
            retryable=True,
            request_id=request_id,
        )

    return success_response(
        report.data,
        source=report.source,
        as_of=report.as_of,
        is_fallback=report.is_fallback,
        warnings=list(report.warnings),
        request_id=request_id,
    )
