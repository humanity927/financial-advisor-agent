from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from finance_advisor.market.compare import (
    MarketCompareRequest,
    compare_market_performance,
    required_history_days,
)
from finance_advisor.market.service import MarketServiceError
from finance_advisor.market.symbols import (
    SymbolValidationError,
    get_symbol_catalog,
    normalize_symbols,
)
from finance_advisor.market.watchlist import (
    WatchlistError,
    WatchlistState,
    get_watchlist_store,
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


class WatchlistSymbolRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(pattern=r"^\d{6}$")


class WatchlistComparisonRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbols: list[str] = Field(default_factory=list, max_length=8)


def _watchlist_payload(state: WatchlistState) -> dict[str, Any]:
    catalog = get_symbol_catalog()
    return {
        "items": [asdict(item) for symbol in state.symbols if (item := catalog.get(symbol))],
        "current_symbol": state.current_symbol,
        "comparison_symbols": state.comparison_symbols,
        "updated_at": state.updated_at,
    }


def _watchlist_error(exc: WatchlistError) -> JSONResponse:
    status = 409 if exc.code in {"duplicate_symbol", "watchlist_limit"} else 400
    return JSONResponse(
        status_code=status,
        content=error_response(exc.code, exc.message),
    )


@router.get("/catalog/search", response_model=None)
def search_market_catalog(
    q: str = Query(default="", max_length=80),
    refresh: bool = Query(default=True),
    representative: bool = Query(default=False),
) -> dict[str, Any] | JSONResponse:
    catalog = get_symbol_catalog()
    warnings: list[str] = []
    source = catalog.source or ("cache" if catalog.fetched_at else "system")
    if refresh and q.strip():
        try:
            result = get_market_service().search_etfs(q, limit=50)
            if result.items:
                catalog.register_provider(result.items, source=result.source)
            source = result.source
            if result.failures:
                warnings.append("AKShare标的目录暂不可用，已切换到Tushare补充目录")
        except MarketServiceError as exc:
            LOGGER.warning(
                "market catalog unavailable query_length=%s failures=%s",
                len(q.strip()),
                [(item.provider, item.code) for item in exc.failures],
            )
            warnings.append("AKShare与Tushare标的目录暂不可用，已展示本地已校验目录")

    items = (
        catalog.representatives()
        if representative and not q.strip()
        else catalog.search(q, limit=50)
    )
    if not items and warnings:
        return JSONResponse(
            status_code=503,
            content=error_response(
                "catalog_unavailable",
                "标的搜索失败，AKShare、Tushare与本地真实目录均无可用结果",
                retryable=True,
            ),
        )
    return success_response(
        {
            "items": [asdict(item) for item in items],
            "catalog_fetched_at": catalog.fetched_at,
            "query": q.strip(),
            "selection_note": (
                "覆盖大盘、核心宽基、中小盘、成长、债券与黄金方向"
                if representative and not q.strip()
                else None
            ),
        },
        source=source,
        as_of=catalog.fetched_at,
        is_fallback=bool(warnings),
        warnings=warnings,
    )


@router.get("/watchlist", response_model=None)
def get_watchlist() -> dict[str, Any]:
    state = get_watchlist_store(get_symbol_catalog()).get()
    return success_response(_watchlist_payload(state), source="local")


@router.post("/watchlist/items", response_model=None)
def add_watchlist_item(request: WatchlistSymbolRequest) -> dict[str, Any] | JSONResponse:
    try:
        state = get_watchlist_store(get_symbol_catalog()).add(request.symbol)
    except WatchlistError as exc:
        return _watchlist_error(exc)
    return success_response(_watchlist_payload(state), source="local")


@router.delete("/watchlist/items/{symbol}", response_model=None)
def remove_watchlist_item(symbol: str) -> dict[str, Any] | JSONResponse:
    try:
        state = get_watchlist_store(get_symbol_catalog()).remove(symbol)
    except WatchlistError as exc:
        return _watchlist_error(exc)
    return success_response(_watchlist_payload(state), source="local")


@router.post("/watchlist/current", response_model=None)
def set_watchlist_current(request: WatchlistSymbolRequest) -> dict[str, Any] | JSONResponse:
    try:
        state = get_watchlist_store(get_symbol_catalog()).set_current(request.symbol)
    except WatchlistError as exc:
        return _watchlist_error(exc)
    return success_response(_watchlist_payload(state), source="local")


@router.post("/watchlist/comparison", response_model=None)
def set_watchlist_comparison(
    request: WatchlistComparisonRequest,
) -> dict[str, Any] | JSONResponse:
    try:
        state = get_watchlist_store(get_symbol_catalog()).set_comparison(request.symbols)
    except WatchlistError as exc:
        return _watchlist_error(exc)
    return success_response(_watchlist_payload(state), source="local")


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
    except MarketServiceError as exc:
        LOGGER.warning(
            "market snapshot unavailable failures=%s",
            [(item.provider, item.code) for item in exc.failures],
        )
        return JSONResponse(
            status_code=503,
            content=error_response(
                "market_data_unavailable",
                "行情快照失败，AKShare、Tushare与真实行情缓存均不可用",
                retryable=True,
            ),
        )
    except Exception as exc:
        LOGGER.warning("market snapshot failed error_type=%s", type(exc).__name__)
        return JSONResponse(
            status_code=503,
            content=error_response(
                "market_data_unavailable",
                "行情快照失败，返回数据无效",
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
    except MarketServiceError as exc:
        LOGGER.warning(
            "market comparison unavailable failures=%s",
            [(item.provider, item.code) for item in exc.failures],
        )
        return JSONResponse(
            status_code=503,
            content=error_response(
                "market_data_unavailable",
                "行情对比失败，AKShare、Tushare与真实行情缓存均不可用",
                retryable=True,
            ),
        )
    except Exception as exc:
        LOGGER.warning("market comparison failed error_type=%s", type(exc).__name__)
        return JSONResponse(
            status_code=503,
            content=error_response(
                "market_data_unavailable",
                "行情对比失败，返回数据无效",
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
