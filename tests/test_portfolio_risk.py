from __future__ import annotations

from datetime import date, timedelta

import pytest

from finance_advisor.market.models import MarketBar, MarketSeries
from finance_advisor.risk.metrics import calculate_risk_metrics
from finance_advisor.risk.portfolio import (
    InsufficientCommonDataError,
    PortfolioValidationError,
    calculate_portfolio_risk,
)


def _series(
    symbol: str,
    prices: list[float],
    *,
    start_offset: int = 0,
) -> MarketSeries:
    start = date(2025, 1, 1) + timedelta(days=start_offset)
    return MarketSeries(
        symbol=symbol,
        name=symbol,
        asset_class="测试",
        bars=[
            MarketBar(date=start + timedelta(days=index), close=price)
            for index, price in enumerate(prices)
        ],
        source="fixture",
        fetched_at="2026-07-20T00:00:00+08:00",
        is_fallback=True,
        warning="演示数据/非实时数据",
    )


def test_single_asset_portfolio_matches_asset_metrics() -> None:
    prices = [100 * (1.001**index) for index in range(80)]
    series = _series("510300", prices)

    result = calculate_portfolio_risk([series], {"510300": 100.0})
    asset_metrics = calculate_risk_metrics(series.bars)

    assert result.metrics.as_dict() == asset_metrics.as_dict()
    assert result.correlation.values == ((1.0,),)
    assert result.net_value_curve[0].value == 1.0
    assert result.drawdown_curve[0].value == 0.0


def test_common_dates_weights_correlation_and_drawdown_are_reproducible() -> None:
    stock = _series("510300", [100 + index * 0.4 for index in range(75)])
    bond_prices = [100 + index * 0.08 for index in range(75)]
    bond_prices[-8:] = [bond_prices[-9] - index * 0.2 for index in range(1, 9)]
    bond = _series("511010", bond_prices, start_offset=3)

    result = calculate_portfolio_risk(
        [stock, bond],
        {"510300": 60.0, "511010": 40.0},
    )

    assert result.metrics.observation_count == 72
    assert result.metrics.start_date == (date(2025, 1, 4)).isoformat()
    assert result.weights_pct == {"510300": 60.0, "511010": 40.0}
    assert result.correlation.symbols == ("510300", "511010")
    assert result.correlation.values[0][0] == 1.0
    assert result.correlation.values[1][1] == 1.0
    assert result.correlation.values[0][1] == result.correlation.values[1][0]
    assert result.metrics.max_drawdown_pct <= 0
    assert len(result.net_value_curve) == result.metrics.observation_count
    assert len(result.drawdown_curve) == result.metrics.observation_count


@pytest.mark.parametrize(
    "weights",
    [
        {"510300": 90.0},
        {"510300": -10.0, "511010": 110.0},
        {"510300": float("nan"), "511010": 100.0},
    ],
)
def test_invalid_weights_are_rejected(weights: dict[str, float]) -> None:
    series = [
        _series("510300", [100 + index for index in range(60)]),
        _series("511010", [100 + index for index in range(60)]),
    ]
    with pytest.raises(PortfolioValidationError):
        calculate_portfolio_risk(series, weights)


def test_insufficient_common_dates_are_explicit() -> None:
    left = _series("510300", [100 + index for index in range(60)])
    right = _series("511010", [100 + index for index in range(60)], start_offset=30)

    with pytest.raises(InsufficientCommonDataError, match="共同有效收盘价只有30条"):
        calculate_portfolio_risk([left, right], {"510300": 50.0, "511010": 50.0})


def test_constant_asset_marks_cross_correlation_unavailable() -> None:
    moving = _series("510300", [100 + index * index / 100 for index in range(70)])
    constant = _series("511880", [100.0 for _ in range(70)])

    result = calculate_portfolio_risk(
        [moving, constant],
        {"510300": 50.0, "511880": 50.0},
    )

    assert result.correlation.values[0][1] is None
    assert result.correlation.values[1][0] is None
    assert len(result.warnings) == 1
