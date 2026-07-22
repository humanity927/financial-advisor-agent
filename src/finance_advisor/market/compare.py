from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from finance_advisor.market.models import MarketSeries

RETURN_WINDOWS: tuple[int, ...] = (20, 60, 252)
RANGE_LOOKBACK_DAYS: dict[str, int] = {"1M": 20, "3M": 60, "1Y": 252}


class MarketCompareRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbols: list[str] = Field(default_factory=lambda: ["510300", "511010", "518880", "511880"])
    range: str = Field(default="3M", pattern="^(1M|3M|1Y)$")
    lookback_days: int | None = Field(default=None, ge=20, le=1260)

    def display_lookback_days(self) -> int:
        if self.lookback_days is not None:
            return self.lookback_days
        return RANGE_LOOKBACK_DAYS[self.range]


def required_history_days(display_lookback_days: int) -> int:
    return max(display_lookback_days, max(RETURN_WINDOWS))


def _bar_map(series: MarketSeries) -> dict[date, float]:
    result: dict[date, float] = {}
    for bar in series.bars:
        result[bar.date] = bar.close
    return result


def _common_dates(price_maps: list[dict[date, float]]) -> list[date]:
    if not price_maps:
        return []
    common = set(price_maps[0])
    for item in price_maps[1:]:
        common &= set(item)
    return sorted(common)


def _source_details(series_list: list[MarketSeries]) -> list[dict[str, Any]]:
    return [
        {
            "symbol": series.symbol,
            "name": series.name,
            "source": series.source,
            "provider": series.provider,
            "origin_source": series.origin_source,
            "fetched_at": series.fetched_at,
            "latest_trade_date": series.latest_trade_date,
            "cache_status": series.cache_status,
            "stale": series.stale,
            "is_fallback": series.is_fallback,
            "warning": series.warning,
        }
        for series in series_list
    ]


def _interval_return(
    prices: dict[date, float],
    common_dates: list[date],
    trading_days: int,
) -> float | None:
    if len(common_dates) <= trading_days:
        return None
    latest_date = common_dates[-1]
    start_date = common_dates[-(trading_days + 1)]
    start_price = prices[start_date]
    latest_price = prices[latest_date]
    if start_price <= 0:
        return None
    return round((latest_price / start_price - 1.0) * 100.0, 4)


def compare_market_performance(
    series_list: list[MarketSeries],
    *,
    display_lookback_days: int,
    return_windows: tuple[int, ...] = RETURN_WINDOWS,
) -> dict[str, Any]:
    """Compare aligned ETF histories without forward-filling missing dates."""
    if not series_list:
        raise ValueError("至少需要一个行情序列")
    if display_lookback_days < 20 or display_lookback_days > 1260:
        raise ValueError("display_lookback_days必须在20到1260之间")

    price_maps = [_bar_map(series) for series in series_list]
    common_dates = _common_dates(price_maps)
    warnings: list[str] = []
    if len(common_dates) < 2:
        return {
            "symbols": [
                {
                    "symbol": series.symbol,
                    "name": series.name,
                    "asset_class": series.asset_class,
                }
                for series in series_list
            ],
            "range_days": display_lookback_days,
            "common_start_date": None,
            "latest_trade_date": None,
            "observation_count": len(common_dates),
            "normalized_series": [],
            "interval_returns": [],
            "snapshots": [series.snapshot() for series in series_list],
            "source_details": _source_details(series_list),
            "method": "共同交易日对齐，不前向填充缺口；历史表现不代表未来收益",
            "warnings": ["共同交易日不足，无法生成可比较曲线"],
        }

    display_dates = common_dates[-(display_lookback_days + 1) :]
    if len(display_dates) <= display_lookback_days:
        warnings.append(f"共同交易日少于{display_lookback_days + 1}个，已使用可用区间")

    normalized_series: list[dict[str, Any]] = []
    interval_returns: list[dict[str, Any]] = []
    for series, prices in zip(series_list, price_maps, strict=True):
        start_date = display_dates[0]
        start_price = prices[start_date]
        points = [
            {
                "date": item_date.isoformat(),
                "close": round(prices[item_date], 4),
                "normalized": round(prices[item_date] / start_price * 100.0, 4),
            }
            for item_date in display_dates
        ]
        normalized_series.append(
            {
                "symbol": series.symbol,
                "name": series.name,
                "asset_class": series.asset_class,
                "points": points,
            }
        )

        returns: dict[str, float | None] = {}
        for window in return_windows:
            value = _interval_return(prices, common_dates, window)
            returns[f"{window}d"] = value
            if value is None:
                warnings.append(f"{series.name}缺少近{window}个共同交易日收益")
        interval_returns.append(
            {
                "symbol": series.symbol,
                "name": series.name,
                "asset_class": series.asset_class,
                "returns": returns,
            }
        )

    return {
        "symbols": [
            {
                "symbol": series.symbol,
                "name": series.name,
                "asset_class": series.asset_class,
            }
            for series in series_list
        ],
        "range_days": display_lookback_days,
        "common_start_date": display_dates[0].isoformat(),
        "latest_trade_date": common_dates[-1].isoformat(),
        "observation_count": len(common_dates),
        "normalized_series": normalized_series,
        "interval_returns": interval_returns,
        "snapshots": [series.snapshot() for series in series_list],
        "source_details": _source_details(series_list),
        "method": "共同交易日对齐，不前向填充缺口；历史表现不代表未来收益",
        "warnings": list(dict.fromkeys(warnings)),
    }
