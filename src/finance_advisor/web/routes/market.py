from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from finance_advisor.market.compare import (
    MarketCompareRequest,
    compare_market_performance,
    required_history_days,
)
from finance_advisor.market.symbols import SymbolValidationError, normalize_symbols
from finance_advisor.schemas import error_response, success_response
from finance_advisor.web.common import (
    get_market_service,
    load_market_series,
    source_for,
    warnings_for,
)

LOGGER = logging.getLogger(__name__)

router = APIRouter()


@router.get("/snapshot", response_model=None)
def market_snapshot(
    symbols: str = Query(..., min_length=1, description="逗号分隔的白名单 ETF 代码"),
) -> dict[str, Any] | JSONResponse:
    try:
        normalized = normalize_symbols(symbols.split(","))
    except SymbolValidationError as exc:
        return JSONResponse(
            status_code=400,
            content=error_response("invalid_symbol", str(exc)),
        )

    loaded = []
    try:
        service = get_market_service()
        loaded = load_market_series(normalized, service.get_snapshot)
        snapshots = [item.snapshot() for item in loaded]
    except Exception:
        LOGGER.exception("market snapshot failed")
        return JSONResponse(
            status_code=503,
            content=error_response(
                "market_data_unavailable",
                "行情快照失败，且缓存与演示数据均不可用",
                retryable=True,
            ),
        )

    as_of = max(str(item["trade_date"]) for item in snapshots)
    return success_response(
        {"snapshots": snapshots},
        source=source_for(loaded),
        as_of=as_of,
        is_fallback=any(item.is_fallback for item in loaded),
        warnings=warnings_for(loaded),
    )


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
        loaded = load_market_series(
            symbols,
            lambda symbol: service.get_history(symbol, fetch_days),
        )
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
