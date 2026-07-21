from __future__ import annotations

import os
from dataclasses import dataclass

from finance_advisor.market.akshare_provider import AkshareProvider
from finance_advisor.market.cache_provider import CacheProvider
from finance_advisor.market.fixture_provider import FixtureProvider
from finance_advisor.market.models import MarketSeries
from finance_advisor.market.symbols import SymbolInfo


@dataclass(frozen=True, slots=True)
class MarketPolicy:
    snapshot_ttl_seconds: int = 60
    history_ttl_seconds: int = 6 * 60 * 60


class MarketService:
    def __init__(
        self,
        live: AkshareProvider,
        cache: CacheProvider,
        fixture: FixtureProvider,
        *,
        policy: MarketPolicy | None = None,
        force_fixture: bool | None = None,
    ) -> None:
        self.live = live
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

        cached = self.cache.load(cache_key, max_age_seconds=ttl_seconds)
        if cached is not None:
            return cached

        live_error: Exception | None = None
        if self.live.available():
            try:
                series = self.live.fetch_history(symbol, lookback_days)
                self.cache.save(cache_key, series)
                return series
            except Exception as exc:
                live_error = exc

        stale = self.cache.load(
            cache_key,
            max_age_seconds=ttl_seconds,
            allow_stale=True,
        )
        if stale is not None:
            return stale

        if live_error is not None:
            raise RuntimeError("AKShare请求失败，且没有可用的真实行情缓存") from live_error
        raise RuntimeError("AKShare不可用，且没有可用的真实行情缓存")
