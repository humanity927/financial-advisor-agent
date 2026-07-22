from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from finance_advisor.market.akshare_provider import AkshareProvider
from finance_advisor.market.cache_provider import CacheProvider
from finance_advisor.market.fixture_provider import FixtureProvider
from finance_advisor.market.models import MarketProviderName, MarketSeries
from finance_advisor.market.provider import (
    MarketProviderError,
    ProviderErrorCode,
)
from finance_advisor.market.service import MarketService, MarketServiceError
from finance_advisor.market.symbols import SymbolInfo, get_symbol_catalog
from finance_advisor.market.tushare_provider import TushareProvider


class UnavailableProvider:
    def __init__(self, name: MarketProviderName) -> None:
        self.name = name

    def available(self) -> bool:
        return True

    def fetch_history(self, _symbol: SymbolInfo, _lookback_days: int) -> MarketSeries:
        raise MarketProviderError(
            self.name,
            ProviderErrorCode.NETWORK_ERROR,
            "provider intentionally unavailable during cache verification",
            retryable=True,
        )


def _series_result(series: MarketSeries) -> dict[str, Any]:
    return {
        "ok": True,
        "source": series.source,
        "provider": series.provider,
        "latest_trade_date": (
            series.latest_trade_date.isoformat() if series.latest_trade_date else None
        ),
        "cache_status": series.cache_status,
        "stale": series.stale,
        "observations": len(series.bars),
    }


def _provider_result(
    provider: AkshareProvider | TushareProvider,
    symbol: SymbolInfo,
    lookback_days: int,
) -> dict[str, Any]:
    try:
        return _series_result(provider.fetch_history(symbol, lookback_days))
    except MarketProviderError as exc:
        return {"ok": False, "provider": exc.provider, "error_code": exc.code}


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    runtime_dir = project_root / ".runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    temporary_cache = TemporaryDirectory(prefix="validation-cache-", dir=runtime_dir)
    cache_root = Path(temporary_cache.name)
    primary_cache = CacheProvider(cache_root / "primary")
    supplemental_cache = CacheProvider(cache_root / "supplemental")
    fixture = FixtureProvider(project_root / "data" / "fixtures" / "market_data.json")
    catalog = get_symbol_catalog()
    index = catalog.get("000001")
    etf = catalog.get("510300")
    if index is None or etf is None:
        print(json.dumps({"ok": False, "error_code": "catalog_missing"}))
        return 1

    akshare = AkshareProvider(timeout_seconds=5.0, max_retries=0)
    # Keep the probe to one request per step so validation does not consume a
    # low-volume Tushare account's minute quota through retries.
    tushare = TushareProvider(timeout_seconds=8.0, max_retries=0)
    results: dict[str, Any] = {
        "akshare_index": _provider_result(akshare, index, 30),
        "tushare_index": _provider_result(tushare, index, 30),
        "tushare_etf": _provider_result(tushare, etf, 30),
    }

    service = MarketService(
        akshare,
        primary_cache,
        fixture,
        supplemental=tushare,
        force_fixture=False,
    )
    try:
        results["service_index"] = _series_result(service.get_history(index, 30))
    except MarketServiceError as exc:
        results["service_index"] = {
            "ok": False,
            "failures": [
                {"provider": item.provider, "error_code": item.code} for item in exc.failures
            ],
        }

    primary_offline = MarketService(
        UnavailableProvider("akshare"),
        primary_cache,
        fixture,
        supplemental=UnavailableProvider("tushare"),
        force_fixture=False,
    )
    try:
        results["primary_cache_index"] = _series_result(primary_offline.get_history(index, 30))
    except MarketServiceError as exc:
        results["primary_cache_index"] = {
            "ok": False,
            "failures": [
                {"provider": item.provider, "error_code": item.code} for item in exc.failures
            ],
        }

    supplemental_service = MarketService(
        UnavailableProvider("akshare"),
        supplemental_cache,
        fixture,
        supplemental=tushare,
        force_fixture=False,
    )
    try:
        results["service_tushare_index"] = _series_result(
            supplemental_service.get_history(index, 30)
        )
    except MarketServiceError as exc:
        results["service_tushare_index"] = {
            "ok": False,
            "failures": [
                {"provider": item.provider, "error_code": item.code} for item in exc.failures
            ],
        }

    offline = MarketService(
        UnavailableProvider("akshare"),
        supplemental_cache,
        fixture,
        supplemental=UnavailableProvider("tushare"),
        force_fixture=False,
    )
    try:
        results["tushare_cache_index"] = _series_result(offline.get_history(index, 30))
    except MarketServiceError as exc:
        results["tushare_cache_index"] = {
            "ok": False,
            "failures": [
                {"provider": item.provider, "error_code": item.code} for item in exc.failures
            ],
        }

    print(json.dumps(results, ensure_ascii=False, sort_keys=True))
    required_ok = (
        bool(results["primary_cache_index"].get("ok"))
        and results["primary_cache_index"].get("source") == "cache"
        and results["primary_cache_index"].get("provider") == "akshare"
        and bool(results["tushare_index"].get("ok"))
        and bool(results["service_tushare_index"].get("ok"))
        and results["service_tushare_index"].get("source") == "tushare"
        and bool(results["tushare_cache_index"].get("ok"))
        and results["tushare_cache_index"].get("source") == "cache"
        and results["tushare_cache_index"].get("provider") == "tushare"
    )
    temporary_cache.cleanup()
    return 0 if required_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
