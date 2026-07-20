from __future__ import annotations

from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from finance_advisor.market.models import MarketBar
from finance_advisor.risk.metrics import InsufficientDataError, calculate_risk_metrics


def _bars(prices: list[float]) -> list[MarketBar]:
    start = date(2025, 1, 1)
    return [
        MarketBar(date=start + timedelta(days=index), close=price)
        for index, price in enumerate(prices)
    ]


def test_constant_growth_metrics() -> None:
    prices = [100 * (1.001**index) for index in range(100)]

    result = calculate_risk_metrics(_bars(prices))

    assert result.observation_count == 100
    assert result.annual_return_pct == pytest.approx(28.64, abs=0.1)
    assert result.annual_volatility_pct == pytest.approx(0.0, abs=1e-8)
    assert result.max_drawdown_pct == 0.0
    assert result.daily_var_95_pct == 0.0


def test_drawdown_and_tail_loss_are_reported() -> None:
    prices = [100 + index * 0.1 for index in range(70)] + [105 - index * 2 for index in range(15)]

    result = calculate_risk_metrics(_bars(prices))

    assert result.max_drawdown_pct < -20
    assert result.daily_var_95_pct > 0
    assert result.daily_cvar_95_pct >= result.daily_var_95_pct


def test_duplicate_dates_keep_last_valid_value() -> None:
    bars = _bars([100 + index for index in range(60)])
    bars.append(MarketBar(date=bars[-1].date, close=200))

    result = calculate_risk_metrics(bars)

    assert result.observation_count == 60
    assert result.end_date == bars[-1].date.isoformat()


def test_insufficient_data_is_explicit() -> None:
    with pytest.raises(InsufficientDataError, match="至少需要60条"):
        calculate_risk_metrics(_bars([100, 101, 102]))


def test_market_bar_rejects_non_positive_prices() -> None:
    with pytest.raises(ValidationError):
        MarketBar(date=date.today(), close=0)
