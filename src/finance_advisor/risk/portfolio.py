from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date

from finance_advisor.market.models import MarketBar, MarketSeries
from finance_advisor.risk.metrics import InsufficientDataError, RiskMetrics, calculate_risk_metrics

MIN_COMMON_PRICES = 60
WEIGHT_TOTAL_PCT = 100.0
WEIGHT_TOLERANCE = 1e-6


class PortfolioValidationError(ValueError):
    """Raised when portfolio symbols or weights do not form a valid portfolio."""


class InsufficientCommonDataError(InsufficientDataError):
    """Raised when assets do not share enough valid closing-price dates."""


@dataclass(frozen=True, slots=True)
class CurvePoint:
    date: str
    value: float

    def as_dict(self) -> dict[str, str | float]:
        return {"date": self.date, "value": self.value}


@dataclass(frozen=True, slots=True)
class CorrelationMatrix:
    symbols: tuple[str, ...]
    values: tuple[tuple[float | None, ...], ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "symbols": list(self.symbols),
            "values": [list(row) for row in self.values],
        }


@dataclass(frozen=True, slots=True)
class PortfolioRiskAnalysis:
    weights_pct: dict[str, float]
    metrics: RiskMetrics
    correlation: CorrelationMatrix
    net_value_curve: tuple[CurvePoint, ...]
    drawdown_curve: tuple[CurvePoint, ...]
    warnings: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "weights_pct": self.weights_pct,
            "portfolio_metrics": self.metrics.as_dict(),
            "correlation_matrix": self.correlation.as_dict(),
            "net_value_curve": [point.as_dict() for point in self.net_value_curve],
            "drawdown_curve": [point.as_dict() for point in self.drawdown_curve],
            "methodology": {
                "portfolio_return": "固定权重每日再平衡的加权日收益",
                "annualization": "每年252个交易日",
                "var_cvar": "历史模拟法，单日95%置信水平",
                "data_alignment": "仅使用全部标的共有的有效收盘价日期",
            },
        }


def _validated_weights(
    series: list[MarketSeries], weights_pct: dict[str, float]
) -> tuple[tuple[str, ...], dict[str, float]]:
    if not series:
        raise PortfolioValidationError("至少需要一个资产序列")

    symbols = tuple(item.symbol for item in series)
    if len(set(symbols)) != len(symbols):
        raise PortfolioValidationError("资产序列中存在重复标的")
    if set(weights_pct) != set(symbols):
        raise PortfolioValidationError("权重标的必须与资产序列完全一致")

    return symbols, validate_portfolio_weights(weights_pct, symbol_order=symbols)


def validate_portfolio_weights(
    weights_pct: dict[str, float], *, symbol_order: tuple[str, ...] | None = None
) -> dict[str, float]:
    """Validate non-negative finite percentages and return a stable symbol order."""
    if not weights_pct:
        raise PortfolioValidationError("至少需要一个资产权重")

    normalized: dict[str, float] = {}
    for symbol in symbol_order or tuple(weights_pct):
        raw_value = weights_pct[symbol]
        if isinstance(raw_value, bool):
            raise PortfolioValidationError("所有权重必须是非负有限数值")
        value = float(raw_value)
        if not math.isfinite(value) or value < 0:
            raise PortfolioValidationError("所有权重必须是非负有限数值")
        normalized[symbol] = value

    total = math.fsum(normalized.values())
    if not math.isclose(total, WEIGHT_TOTAL_PCT, rel_tol=0.0, abs_tol=WEIGHT_TOLERANCE):
        raise PortfolioValidationError(f"权重合计必须为100%，当前为{total:.6f}%")
    return normalized


def _valid_closes(series: MarketSeries) -> dict[date, float]:
    closes: dict[date, float] = {}
    for bar in series.bars:
        if math.isfinite(bar.close) and bar.close > 0:
            closes[bar.date] = float(bar.close)
    return closes


def _pearson(left: list[float], right: list[float]) -> float | None:
    if len(left) != len(right) or len(left) < 2:
        return None
    left_mean = math.fsum(left) / len(left)
    right_mean = math.fsum(right) / len(right)
    left_delta = [value - left_mean for value in left]
    right_delta = [value - right_mean for value in right]
    denominator = math.sqrt(
        math.fsum(value * value for value in left_delta)
        * math.fsum(value * value for value in right_delta)
    )
    if denominator <= 1e-15:
        return None
    value = math.fsum(a * b for a, b in zip(left_delta, right_delta, strict=True))
    return max(-1.0, min(1.0, value / denominator))


def _correlation_matrix(
    symbols: tuple[str, ...], returns: dict[str, list[float]]
) -> tuple[CorrelationMatrix, list[str]]:
    rows: list[tuple[float | None, ...]] = []
    warnings: list[str] = []
    for row_symbol in symbols:
        row: list[float | None] = []
        for column_symbol in symbols:
            if row_symbol == column_symbol:
                row.append(1.0)
                continue
            value = _pearson(returns[row_symbol], returns[column_symbol])
            row.append(round(value, 6) if value is not None else None)
            if value is None:
                pair = sorted((row_symbol, column_symbol))
                warning = f"{pair[0]}与{pair[1]}收益序列波动不足，相关系数不可计算"
                if warning not in warnings:
                    warnings.append(warning)
        rows.append(tuple(row))
    return CorrelationMatrix(symbols=symbols, values=tuple(rows)), warnings


def calculate_portfolio_risk(
    series: list[MarketSeries],
    weights_pct: dict[str, float],
    *,
    min_observations: int = MIN_COMMON_PRICES,
) -> PortfolioRiskAnalysis:
    """Calculate historical risk for a daily-rebalanced, fixed-weight portfolio."""
    symbols, validated_weights = _validated_weights(series, weights_pct)
    if min_observations < 3:
        raise PortfolioValidationError("min_observations至少为3")

    closes = {item.symbol: _valid_closes(item) for item in series}
    date_sets = [set(closes[symbol]) for symbol in symbols]
    common_dates = sorted(set.intersection(*date_sets))
    if len(common_dates) < min_observations:
        raise InsufficientCommonDataError(
            f"共同有效收盘价只有{len(common_dates)}条，至少需要{min_observations}条"
        )

    asset_returns: dict[str, list[float]] = {symbol: [] for symbol in symbols}
    portfolio_returns: list[float] = []
    for index in range(1, len(common_dates)):
        previous_date = common_dates[index - 1]
        current_date = common_dates[index]
        daily_returns: dict[str, float] = {}
        for symbol in symbols:
            daily_return = closes[symbol][current_date] / closes[symbol][previous_date] - 1.0
            asset_returns[symbol].append(daily_return)
            daily_returns[symbol] = daily_return
        portfolio_returns.append(
            math.fsum(
                daily_returns[symbol] * validated_weights[symbol] / WEIGHT_TOTAL_PCT
                for symbol in symbols
            )
        )

    net_values = [1.0]
    for daily_return in portfolio_returns:
        net_values.append(net_values[-1] * (1.0 + daily_return))

    portfolio_bars = [
        MarketBar(date=day, close=value)
        for day, value in zip(common_dates, net_values, strict=True)
    ]
    metrics = calculate_risk_metrics(portfolio_bars, min_observations=min_observations)

    running_peak = 0.0
    net_value_curve: list[CurvePoint] = []
    drawdown_curve: list[CurvePoint] = []
    for day, value in zip(common_dates, net_values, strict=True):
        running_peak = max(running_peak, value)
        drawdown_pct = (value / running_peak - 1.0) * 100.0
        net_value_curve.append(CurvePoint(day.isoformat(), round(value, 6)))
        drawdown_curve.append(CurvePoint(day.isoformat(), round(drawdown_pct, 4)))

    correlation, warnings = _correlation_matrix(symbols, asset_returns)
    return PortfolioRiskAnalysis(
        weights_pct=validated_weights,
        metrics=metrics,
        correlation=correlation,
        net_value_curve=tuple(net_value_curve),
        drawdown_curve=tuple(drawdown_curve),
        warnings=tuple(warnings),
    )
