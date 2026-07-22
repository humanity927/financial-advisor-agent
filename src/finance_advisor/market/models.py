from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

MarketProviderName = Literal["akshare", "tushare", "fixture"]
MarketSource = Literal["akshare", "tushare", "cache", "fixture"]
CacheStatus = Literal["not_used", "fresh", "stale"]


class MarketBar(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: date
    close: float = Field(gt=0)


class MarketSeries(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    name: str
    asset_class: str
    bars: list[MarketBar]
    source: MarketSource
    provider: MarketProviderName | None = None
    fetched_at: str
    latest_trade_date: date | None = None
    cache_status: CacheStatus = "not_used"
    stale: bool = False
    is_fallback: bool = False
    origin_source: MarketProviderName | None = None
    warning: str | None = None
    cached_at: str | None = None
    cache_age_seconds: int | None = Field(default=None, ge=0)
    is_stale: bool = False

    @model_validator(mode="after")
    def populate_metadata(self) -> MarketSeries:
        if self.latest_trade_date is None and self.bars:
            self.latest_trade_date = self.bars[-1].date
        if self.provider is None:
            if self.source in {"akshare", "tushare", "fixture"}:
                self.provider = self.source
            elif self.origin_source is not None:
                self.provider = self.origin_source
        if self.stale or self.is_stale:
            self.stale = True
            self.is_stale = True
            self.cache_status = "stale"
        return self

    def snapshot(self) -> dict[str, object]:
        latest = self.bars[-1]
        previous = self.bars[-2] if len(self.bars) >= 2 else latest
        daily_change = (latest.close / previous.close - 1.0) * 100 if previous.close else 0.0
        return {
            "symbol": self.symbol,
            "name": self.name,
            "asset_class": self.asset_class,
            "latest_price": round(latest.close, 4),
            "previous_close": round(previous.close, 4),
            "daily_change_pct": round(daily_change, 4),
            "trade_date": latest.date.isoformat(),
            "source": self.source,
            "provider": self.provider,
            "origin_source": self.origin_source,
            "is_fallback": self.is_fallback,
            "warning": self.warning,
            "fetched_at": self.fetched_at,
            "latest_trade_date": (
                self.latest_trade_date.isoformat() if self.latest_trade_date else None
            ),
            "cache_status": self.cache_status,
            "stale": self.stale,
            "cached_at": self.cached_at,
            "is_stale": self.is_stale,
        }
