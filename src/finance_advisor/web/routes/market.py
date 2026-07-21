from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from finance_advisor.market.akshare_provider import MarketProviderError
from finance_advisor.market.compare import (
    MarketCompareRequest,
    compare_market_performance,
    required_history_days,
)
from finance_advisor.market.symbols import (
    SymbolValidationError,
    get_symbol_catalog,
    normalize_symbols,
)
from finance_advisor.schemas import error_response, success_response
from finance_advisor.web.common import (
    get_market_service,
    load_market_series,
    source_for,
    warnings_for,
)

LOGGER = logging.getLogger(__name__)

router = APIRouter()


@router.get("/catalog/search", response_model=None)
def search_market_catalog(
    q: str = Query(default="", max_length=80),
    refresh: bool = Query(default=True),
) -> dict[str, Any] | JSONResponse:
    catalog = get_symbol_catalog()
    warnings: list[str] = []
    source = "cache" if catalog.fetched_at else "system"
    if refresh and q.strip():
        try:
            live_items = get_market_service().live.search_etfs(q, limit=50)
            if live_items:
                catalog.register_akshare(live_items)
            source = "akshare"
        except MarketProviderError:
            LOGGER.warning("AKShare catalog search failed query_length=%s", len(q.strip()))
            warnings.append("AKShare标的目录暂不可用，已展示本地已校验目录")

    items = catalog.search(q, limit=50)
    if not items and warnings:
        return JSONResponse(
            status_code=503,
            content=error_response(
                "catalog_unavailable",
                "标的搜索失败，AKShare与本地真实目录均无可用结果",
                retryable=True,
            ),
        )
    return success_response(
        {
            "items": [asdict(item) for item in items],
            "catalog_fetched_at": catalog.fetched_at,
            "query": q.strip(),
        },
        source=source,
        as_of=catalog.fetched_at,
        is_fallback=bool(warnings),
        warnings=warnings,
    )


@router.get("/snapshot", response_model=None)
def market_snapshot(
    symbols: str = Query(..., min_length=1, description="逗号分隔的已校验A股指数或ETF代码"),
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
                "行情快照失败，AKShare与真实行情缓存均不可用",
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
                "行情对比失败，AKShare与真实行情缓存均不可用",
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
