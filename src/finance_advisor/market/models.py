from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

MarketSource = Literal["akshare", "cache", "fixture"]


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
    fetched_at: str
    is_fallback: bool = False
    origin_source: MarketSource | None = None
    warning: str | None = None
    cached_at: str | None = None
    cache_age_seconds: int | None = Field(default=None, ge=0)
    is_stale: bool = False

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
            "origin_source": self.origin_source,
            "is_fallback": self.is_fallback,
            "warning": self.warning,
            "fetched_at": self.fetched_at,
            "cached_at": self.cached_at,
            "is_stale": self.is_stale,
        }
