from __future__ import annotations

import os
from dataclasses import dataclass
from typing import cast

from finance_advisor.market.cache_provider import CacheProvider
from finance_advisor.market.fixture_provider import FixtureProvider
from finance_advisor.market.models import MarketSeries
from finance_advisor.market.provider import (
    MarketCatalogProvider,
    MarketDataProvider,
    MarketProviderError,
    ProviderErrorCode,
    classify_provider_exception,
)
from finance_advisor.market.symbols import SymbolInfo


@dataclass(frozen=True, slots=True)
class MarketPolicy:
    snapshot_ttl_seconds: int = 60
    history_ttl_seconds: int = 6 * 60 * 60


@dataclass(frozen=True, slots=True)
class ProviderFailure:
    provider: str
    code: ProviderErrorCode


class MarketServiceError(RuntimeError):
    def __init__(self, message: str, failures: list[ProviderFailure]) -> None:
        super().__init__(message)
        self.failures = tuple(failures)


@dataclass(frozen=True, slots=True)
class CatalogSearchResult:
    items: list[SymbolInfo]
    source: str
    failures: tuple[ProviderFailure, ...] = ()


class MarketService:
    def __init__(
        self,
        live: MarketDataProvider,
        cache: CacheProvider,
        fixture: FixtureProvider,
        *,
        supplemental: MarketDataProvider | None = None,
        policy: MarketPolicy | None = None,
        force_fixture: bool | None = None,
    ) -> None:
        self.live = live
        self.primary = live
        self.supplemental = supplemental
        self.cache = cache
        self.fixture = fixture
        self.policy = policy or MarketPolicy()
        self.force_fixture = (
            os.getenv("FINANCE_FORCE_FIXTURE", "").lower() in {"1", "true", "yes"}
            if force_fixture is None
            else force_fixture
        )

    def get_snapshot(self, symbol: SymbolInfo) -> MarketSeries:
        return self._get_series(
            symbol,
            lookback_days=5,
            cache_key=f"snapshot_{symbol.symbol}",
            ttl_seconds=self.policy.snapshot_ttl_seconds,
        )

    def get_history(self, symbol: SymbolInfo, lookback_days: int) -> MarketSeries:
        return self._get_series(
            symbol,
            lookback_days=lookback_days,
            cache_key=f"history_{symbol.symbol}_{lookback_days}",
            ttl_seconds=self.policy.history_ttl_seconds,
        )

    def _provider_name(self, provider: MarketDataProvider) -> str:
        fallback = "akshare" if provider is self.primary else "tushare"
        return str(getattr(provider, "name", fallback))

    def _failure(self, provider: MarketDataProvider, exc: Exception) -> ProviderFailure:
        code = (
            exc.code if isinstance(exc, MarketProviderError) else classify_provider_exception(exc)
        )
        return ProviderFailure(provider=self._provider_name(provider), code=code)

    def search_etfs(self, query: str, *, limit: int = 50) -> CatalogSearchResult:
        failures: list[ProviderFailure] = []
        providers = [item for item in (self.primary, self.supplemental) if item is not None]
        for provider in providers:
            if not provider.available():
                failures.append(
                    ProviderFailure(
                        provider=self._provider_name(provider),
                        code=ProviderErrorCode.CONFIGURATION_MISSING,
                    )
                )
                continue
            if not hasattr(provider, "search_etfs"):
                failures.append(
                    ProviderFailure(
                        provider=self._provider_name(provider),
                        code=ProviderErrorCode.CONFIGURATION_MISSING,
                    )
                )
                continue
            try:
                catalog_provider = cast(MarketCatalogProvider, provider)
                items = catalog_provider.search_etfs(query, limit=limit)
                return CatalogSearchResult(
                    items=items,
                    source=self._provider_name(provider),
                    failures=tuple(failures),
                )
            except Exception as exc:
                failures.append(self._failure(provider, exc))
        raise MarketServiceError(
            "AKShare与Tushare标的目录均不可用",
            failures,
        )

    def _get_series(
        self,
        symbol: SymbolInfo,
        *,
        lookback_days: int,
        cache_key: str,
        ttl_seconds: int,
    ) -> MarketSeries:
        if self.force_fixture:
            return self.fixture.fetch_history(symbol, lookback_days)

        failures: list[ProviderFailure] = []
        providers = [item for item in (self.primary, self.supplemental) if item is not None]
        for index, provider in enumerate(providers):
            if not provider.available():
                failures.append(
                    ProviderFailure(
                        provider=self._provider_name(provider),
                        code=ProviderErrorCode.CONFIGURATION_MISSING,
                    )
                )
                continue
            try:
                series = provider.fetch_history(symbol, lookback_days)
                if index > 0:
                    series = series.model_copy(
                        update={
                            "is_fallback": True,
                            "warning": "AKShare暂不可用，已切换到Tushare补充行情",
                        }
                    )
                self.cache.save(cache_key, series)
                return series
            except Exception as exc:
                failures.append(self._failure(provider, exc))

        cached = self.cache.load(
            cache_key,
            max_age_seconds=ttl_seconds,
            allow_stale=True,
        )
        if cached is not None:
            return cached

        raise MarketServiceError(
            "AKShare、Tushare与真实行情缓存均不可用",
            failures,
        )
