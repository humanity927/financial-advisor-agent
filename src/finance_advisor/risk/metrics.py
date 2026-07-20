from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from finance_advisor.market.models import MarketBar


class InsufficientDataError(ValueError):
    """Raised when fewer than the required observations remain after cleaning."""


@dataclass(frozen=True, slots=True)
class RiskMetrics:
    observation_count: int
    start_date: str
    end_date: str
    annual_return_pct: float
    annual_volatility_pct: float
    max_drawdown_pct: float
    daily_var_95_pct: float
    daily_cvar_95_pct: float

    def as_dict(self) -> dict[str, int | float | str]:
        return {
            "observation_count": self.observation_count,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "annual_return_pct": self.annual_return_pct,
            "annual_volatility_pct": self.annual_volatility_pct,
            "max_drawdown_pct": self.max_drawdown_pct,
            "daily_var_95_pct": self.daily_var_95_pct,
            "daily_cvar_95_pct": self.daily_cvar_95_pct,
        }


def calculate_risk_metrics(bars: list[MarketBar], *, min_observations: int = 60) -> RiskMetrics:
    by_date: dict[date, float] = {}
    for bar in bars:
        if math.isfinite(bar.close) and bar.close > 0:
            by_date[bar.date] = float(bar.close)

    ordered = sorted(by_date.items(), key=lambda item: item[0])
    if len(ordered) < min_observations:
        raise InsufficientDataError(f"有效收盘价只有{len(ordered)}条，至少需要{min_observations}条")

    dates = [item[0] for item in ordered]
    prices = pd.Series([item[1] for item in ordered], dtype="float64")
    returns = prices.pct_change().replace([np.inf, -np.inf], np.nan).dropna()
    periods = len(prices) - 1

    annual_return = (prices.iloc[-1] / prices.iloc[0]) ** (252.0 / periods) - 1.0
    annual_volatility = float(returns.std(ddof=1) * math.sqrt(252.0))
    drawdown = prices / prices.cummax() - 1.0
    max_drawdown = float(drawdown.min())
    quantile = float(returns.quantile(0.05))
    tail = returns.loc[returns <= quantile]
    cvar = float(tail.mean()) if not tail.empty else quantile

    return RiskMetrics(
        observation_count=len(prices),
        start_date=dates[0].isoformat(),
        end_date=dates[-1].isoformat(),
        annual_return_pct=round(float(annual_return) * 100, 4),
        annual_volatility_pct=round(annual_volatility * 100, 4),
        max_drawdown_pct=round(max_drawdown * 100, 4),
        daily_var_95_pct=round(max(0.0, -quantile * 100), 4),
        daily_cvar_95_pct=round(max(0.0, -cvar * 100), 4),
    )
