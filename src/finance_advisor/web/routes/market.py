from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from finance_advisor.market.compare import (
    MarketCompareRequest,
    compare_market_performance,
    required_history_days,
)
from finance_advisor.market.symbols import SymbolValidationError, normalize_symbols
from finance_advisor.schemas import error_response, success_response
from finance_advisor.web.common import get_market_service, source_for, warnings_for

LOGGER = logging.getLogger(__name__)

router = APIRouter()


@router.post("/compare", response_model=None)
def compare_market(request: MarketCompareRequest) -> dict[str, Any] | JSONResponse:
    display_days = request.display_lookback_days()
    fetch_days = required_history_days(display_days)
    try:
        symbols = normalize_symbols(request.symbols)
    except SymbolValidationError as exc:
        return JSONResponse(
            status_code=400,
            content=error_response("invalid_symbol", str(exc)),
        )

    loaded = []
    try:
        service = get_market_service()
        loaded = [service.get_history(symbol, fetch_days) for symbol in symbols]
        comparison = compare_market_performance(loaded, display_lookback_days=display_days)
    except ValueError as exc:
        return JSONResponse(
            status_code=400,
            content=error_response("invalid_market_compare_request", str(exc)),
        )
    except Exception:
        LOGGER.exception("market comparison failed")
        return JSONResponse(
            status_code=503,
            content=error_response(
                "market_data_unavailable",
                "行情对比失败，且缓存与演示数据均不可用",
                retryable=True,
            ),
        )

    combined_warnings = warnings_for(loaded) + list(comparison.get("warnings", []))
    latest_trade_date = comparison.get("latest_trade_date")
    return success_response(
        comparison,
        source=source_for(loaded),
        as_of=str(latest_trade_date) if latest_trade_date else None,
        is_fallback=any(item.is_fallback for item in loaded),
        warnings=list(dict.fromkeys(combined_warnings)),
    )
