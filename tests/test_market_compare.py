from __future__ import annotations

from datetime import date, timedelta

from finance_advisor.market.compare import compare_market_performance, required_history_days
from finance_advisor.market.models import MarketBar, MarketSeries


def _series(
    symbol: str,
    *,
    start: date = date(2026, 1, 1),
    count: int = 70,
    base: float = 100.0,
    step: float = 1.0,
    skip_every: int | None = None,
) -> MarketSeries:
    bars: list[MarketBar] = []
    index = 0
    current_date = start
    while len(bars) < count:
        if skip_every is None or index % skip_every != 0:
            bars.append(MarketBar(date=current_date, close=base + len(bars) * step))
        current_date += timedelta(days=1)
        index += 1
    return MarketSeries(
        symbol=symbol,
        name=f"{symbol}ETF",
        asset_class="测试资产",
        bars=bars,
        source="fixture",
        fetched_at="2026-07-20T10:00:00+08:00",
        is_fallback=True,
        warning="演示数据/非实时数据",
    )


def test_required_history_days_covers_fixed_return_windows() -> None:
    assert required_history_days(20) == 252
    assert required_history_days(300) == 300


def test_compare_market_performance_aligns_common_dates_and_normalizes() -> None:
    first = _series("510300", count=80, base=100.0, step=1.0)
    second = _series("511010", start=date(2026, 1, 3), count=80, base=200.0, step=2.0)

    result = compare_market_performance([first, second], display_lookback_days=20)

    assert result["range_days"] == 20
    assert result["latest_trade_date"] == "2026-03-21"
    assert result["common_start_date"] == "2026-03-01"
    assert result["normalized_series"][0]["points"][0]["normalized"] == 100.0
    assert result["normalized_series"][1]["points"][0]["normalized"] == 100.0
    assert len(result["normalized_series"][0]["points"]) == 21
    assert result["interval_returns"][0]["returns"]["20d"] == round((179 / 159 - 1) * 100, 4)
    assert result["interval_returns"][1]["returns"]["20d"] == round((354 / 314 - 1) * 100, 4)
    assert result["interval_returns"][0]["returns"]["252d"] is None
    assert any("252" in item for item in result["warnings"])


def test_compare_market_performance_uses_common_dates_without_forward_fill() -> None:
    full = _series("510300", count=40, base=100.0, step=1.0)
    sparse = _series("518880", count=40, base=50.0, step=0.5, skip_every=3)

    result = compare_market_performance([full, sparse], display_lookback_days=20)
    first_points = result["normalized_series"][0]["points"]
    second_points = result["normalized_series"][1]["points"]

    assert [item["date"] for item in first_points] == [item["date"] for item in second_points]
    assert len(first_points) == 21


def test_compare_market_performance_returns_warning_for_no_overlap() -> None:
    first = _series("510300", start=date(2026, 1, 1), count=3)
    second = _series("511010", start=date(2026, 2, 1), count=3)

    result = compare_market_performance([first, second], display_lookback_days=20)

    assert result["common_start_date"] is None
    assert result["normalized_series"] == []
    assert "共同交易日不足" in result["warnings"][0]
