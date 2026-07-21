from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from finance_advisor.market.models import MarketSeries
from finance_advisor.market.symbols import (
    SymbolValidationError,
    normalize_symbol,
    normalize_symbols,
)
from finance_advisor.risk.metrics import InsufficientDataError, calculate_risk_metrics
from finance_advisor.risk.portfolio import (
    InsufficientCommonDataError,
    PortfolioValidationError,
    calculate_portfolio_risk,
    validate_portfolio_weights,
)
from finance_advisor.risk.profile import assess_profile, profile_chart_data
from finance_advisor.schemas import InvestorProfileInput, error_response, success_response
from finance_advisor.web.common import get_market_service, source_for, warnings_for

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


def _asset_results(
    loaded: list[MarketSeries],
    *,
    request_id: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    results: list[dict[str, Any]] = []
    warnings: list[str] = []
    for series in loaded:
        try:
            metrics = calculate_risk_metrics(series.bars)
            results.append(
                {
                    "symbol": series.symbol,
                    "name": series.name,
                    "asset_class": series.asset_class,
                    "metrics": metrics.as_dict(),
                    "source": series.source,
                    "warning": series.warning,
                }
            )
        except InsufficientDataError as exc:
            warning = f"{series.name}：{exc}"
            warnings.append(warning)
            results.append(
                {
                    "symbol": series.symbol,
                    "name": series.name,
                    "asset_class": series.asset_class,
                    "metrics": None,
                    "source": series.source,
                    "warning": warning,
                    "error": "insufficient_data",
                }
            )
        except Exception:
            LOGGER.exception(
                "asset risk calculation failed symbol=%s request_id=%s", series.symbol, request_id
            )
            warning = f"{series.name}风险计算失败"
            warnings.append(warning)
            results.append(
                {
                    "symbol": series.symbol,
                    "name": series.name,
                    "asset_class": series.asset_class,
                    "metrics": None,
                    "source": series.source,
                    "warning": warning,
                    "error": "analysis_failed",
                }
            )
    return results, warnings


@router.post("/profile", response_model=None)
def risk_profile(request: InvestorProfileInput) -> dict[str, Any]:
    """Return deterministic six-dimension investor risk assessment."""
    assessment = assess_profile(request)
    data = assessment.model_dump(mode="json")
    data["dimensions"] = profile_chart_data(assessment)
    return success_response(data)


@router.post("/assets", response_model=None)
def asset_risk(request: AssetRiskRequest) -> dict[str, Any] | JSONResponse:
    """Calculate historical risk metrics for up to four supported ETFs."""
    request_id = str(uuid4())
    try:
        symbols = normalize_symbols(request.symbols)
    except SymbolValidationError as exc:
        return _json_error(400, "invalid_symbol", str(exc), request_id=request_id)

    try:
        loaded = [
            get_market_service().get_history(symbol, request.lookback_days) for symbol in symbols
        ]
        results, result_warnings = _asset_results(loaded, request_id=request_id)
    except Exception:
        LOGGER.exception("asset risk history loading failed request_id=%s", request_id)
        return _json_error(
            503,
            "risk_analysis_failed",
            "风险历史数据加载失败，请检查行情服务",
            retryable=True,
            request_id=request_id,
        )

    usable = [item for item in results if item["metrics"] is not None]
    if not usable:
        return _json_error(
            503,
            "risk_analysis_failed",
            "所有标的的历史数据均不可用",
            retryable=True,
            data={"assets": results},
            request_id=request_id,
        )

    as_of = max(item.bars[-1].date.isoformat() for item in loaded if item.bars)
    return success_response(
        {"assets": results, "method": "历史数据统计，不代表未来表现"},
        source=source_for(loaded),
        as_of=as_of,
        is_fallback=any(item.is_fallback for item in loaded),
        warnings=list(dict.fromkeys(warnings_for(loaded) + result_warnings)),
        request_id=request_id,
    )


def _normalized_weights(weights_pct: dict[str, float]) -> tuple[list[Any], dict[str, float]]:
    if not weights_pct:
        raise PortfolioValidationError("weights_pct至少需要一个标的")
    symbols = []
    normalized: dict[str, float] = {}
    for raw_symbol, raw_weight in weights_pct.items():
        symbol = normalize_symbol(raw_symbol)
        if symbol.symbol in normalized:
            raise PortfolioValidationError(f"标的{symbol.symbol}通过代码或别名重复出现")
        symbols.append(symbol)
        normalized[symbol.symbol] = raw_weight
    return symbols, validate_portfolio_weights(normalized)


@router.post("/portfolio", response_model=None)
def portfolio_risk(request: PortfolioRiskRequest) -> dict[str, Any] | JSONResponse:
    """Calculate historical risk for a fixed-weight daily-rebalanced portfolio."""
    request_id = str(uuid4())
    try:
        symbols, normalized_weights = _normalized_weights(request.weights_pct)
    except SymbolValidationError as exc:
        return _json_error(400, "invalid_symbol", str(exc), request_id=request_id)
    except PortfolioValidationError as exc:
        return _json_error(400, "invalid_weights", str(exc), request_id=request_id)

    try:
        loaded = [
            get_market_service().get_history(symbol, request.lookback_days) for symbol in symbols
        ]
    except Exception:
        LOGGER.exception("portfolio history loading failed request_id=%s", request_id)
        return _json_error(
            503,
            "portfolio_risk_failed",
            "组合历史数据加载失败，请检查行情服务",
            retryable=True,
            request_id=request_id,
        )

    assets = [
        {
            "symbol": symbol.symbol,
            "name": symbol.name,
            "asset_class": symbol.asset_class,
            "weight_pct": normalized_weights[symbol.symbol],
            "source": series.source,
            "warning": series.warning,
        }
        for symbol, series in zip(symbols, loaded, strict=True)
    ]
    as_of = max(series.bars[-1].date.isoformat() for series in loaded if series.bars)

    try:
        analysis = calculate_portfolio_risk(loaded, normalized_weights)
    except InsufficientCommonDataError as exc:
        return success_response(
            {"portfolio": None, "assets": assets, "method": "历史数据统计，不代表未来表现"},
            source=source_for(loaded),
            as_of=as_of,
            is_fallback=any(item.is_fallback for item in loaded),
            warnings=list(dict.fromkeys(warnings_for(loaded) + [str(exc)])),
            request_id=request_id,
        )
    except PortfolioValidationError as exc:
        return _json_error(400, "invalid_weights", str(exc), request_id=request_id)
    except Exception:
        LOGGER.exception("portfolio risk calculation failed request_id=%s", request_id)
        return _json_error(
            503,
            "portfolio_risk_failed",
            "组合风险计算失败，请检查历史数据和权重",
            retryable=True,
            request_id=request_id,
        )

    return success_response(
        {
            "portfolio": analysis.as_dict(),
            "assets": assets,
            "method": "固定权重每日再平衡的历史组合统计，不代表未来表现",
        },
        source=source_for(loaded),
        as_of=analysis.metrics.end_date,
        is_fallback=any(item.is_fallback for item in loaded),
        warnings=list(
            dict.fromkeys(
                warnings_for(loaded)
                + list(analysis.warnings)
                + ["历史相关性和风险指标不代表未来表现"]
            )
        ),
        request_id=request_id,
    )
