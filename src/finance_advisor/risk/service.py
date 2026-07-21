from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Annotated, Any

from pydantic import BeforeValidator

from finance_advisor.market.models import MarketSeries
from finance_advisor.market.service import MarketService
from finance_advisor.market.symbols import SymbolInfo, normalize_symbol, normalize_symbols
from finance_advisor.risk.metrics import InsufficientDataError, calculate_risk_metrics
from finance_advisor.risk.portfolio import (
    InsufficientCommonDataError,
    PortfolioValidationError,
    calculate_portfolio_risk,
    validate_portfolio_weights,
)
from finance_advisor.risk.profile import assess_profile, profile_chart_data
from finance_advisor.schemas import InvestorProfileInput

MIN_LOOKBACK_DAYS = 60
MAX_LOOKBACK_DAYS = 1260
MAX_RISK_SYMBOLS = 4
ASSET_RISK_METHOD = "历史数据统计，不代表未来表现"
PORTFOLIO_RISK_METHOD = "固定权重每日再平衡的历史组合统计，不代表未来表现"


def _validate_weight_input(value: Any) -> Any:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("组合权重必须使用JSON数值，不能使用布尔值或字符串")
    return value


PortfolioWeight = Annotated[float, BeforeValidator(_validate_weight_input)]


class InvalidLookbackError(ValueError):
    """Raised when the requested history window is outside the supported range."""


class RiskDataUnavailableError(RuntimeError):
    """Raised when required market history cannot be loaded."""


@dataclass(frozen=True, slots=True)
class RiskReport:
    data: dict[str, Any]
    source: str
    as_of: str
    is_fallback: bool
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class HistoryOutcome:
    symbol: SymbolInfo
    series: MarketSeries | None


def validate_lookback_days(lookback_days: int) -> int:
    if lookback_days < MIN_LOOKBACK_DAYS or lookback_days > MAX_LOOKBACK_DAYS:
        raise InvalidLookbackError(
            f"lookback_days必须在{MIN_LOOKBACK_DAYS}到{MAX_LOOKBACK_DAYS}之间"
        )
    return lookback_days


def profile_assessment_data(profile: InvestorProfileInput) -> dict[str, Any]:
    assessment = assess_profile(profile)
    data = assessment.model_dump(mode="json")
    data["dimensions"] = profile_chart_data(assessment)
    return data


def normalize_portfolio_request(
    weights_pct: dict[str, float],
) -> tuple[list[SymbolInfo], dict[str, float]]:
    if not weights_pct:
        raise PortfolioValidationError("weights_pct至少需要一个标的")
    if len(weights_pct) > MAX_RISK_SYMBOLS:
        raise PortfolioValidationError(f"weights_pct一次最多包含{MAX_RISK_SYMBOLS}个标的")

    symbols: list[SymbolInfo] = []
    normalized: dict[str, float] = {}
    for raw_symbol, weight in weights_pct.items():
        symbol = normalize_symbol(raw_symbol)
        if symbol.symbol in normalized:
            raise PortfolioValidationError(f"标的{symbol.symbol}通过代码或别名重复出现")
        symbols.append(symbol)
        normalized[symbol.symbol] = weight
    return symbols, validate_portfolio_weights(normalized)


def _load_history(
    service: MarketService,
    symbols: list[SymbolInfo],
    lookback_days: int,
) -> list[HistoryOutcome]:
    def load(symbol: SymbolInfo) -> HistoryOutcome:
        try:
            return HistoryOutcome(symbol=symbol, series=service.get_history(symbol, lookback_days))
        except Exception:
            return HistoryOutcome(symbol=symbol, series=None)

    with ThreadPoolExecutor(
        max_workers=min(MAX_RISK_SYMBOLS, len(symbols)),
        thread_name_prefix="risk-history",
    ) as executor:
        return list(executor.map(load, symbols))


def _unique(values: list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value for value in values if value))


def _source_for(series: list[MarketSeries]) -> str:
    sources = {item.source for item in series}
    return next(iter(sources)) if len(sources) == 1 else "mixed"


def _as_of(series: list[MarketSeries]) -> str:
    trade_dates = [bar.date.isoformat() for item in series for bar in item.bars]
    if trade_dates:
        return max(trade_dates)
    return max(item.fetched_at for item in series)


def _series_warnings(series: list[MarketSeries]) -> list[str]:
    return [item.warning for item in series if item.warning]


def build_asset_risk_report(
    service: MarketService,
    raw_symbols: list[str],
    lookback_days: int,
) -> RiskReport:
    validate_lookback_days(lookback_days)
    symbols = normalize_symbols(raw_symbols)
    outcomes = _load_history(service, symbols, lookback_days)
    loaded = [outcome.series for outcome in outcomes if outcome.series is not None]
    if not loaded:
        raise RiskDataUnavailableError("所有标的的历史数据均不可用")

    assets: list[dict[str, Any]] = []
    warnings = _series_warnings(loaded)
    for outcome in outcomes:
        symbol = outcome.symbol
        series = outcome.series
        if series is None:
            warning = f"{symbol.name}历史数据不可用"
            warnings.append(warning)
            assets.append(
                {
                    "symbol": symbol.symbol,
                    "name": symbol.name,
                    "asset_class": symbol.asset_class,
                    "metrics": None,
                    "source": None,
                    "warning": warning,
                    "error": "data_unavailable",
                }
            )
            continue

        try:
            metrics = calculate_risk_metrics(series.bars)
            assets.append(
                {
                    "symbol": symbol.symbol,
                    "name": symbol.name,
                    "asset_class": symbol.asset_class,
                    "metrics": metrics.as_dict(),
                    "source": series.source,
                    "warning": series.warning,
                }
            )
        except InsufficientDataError as exc:
            warning = f"{symbol.name}：{exc}"
            warnings.append(warning)
            assets.append(
                {
                    "symbol": symbol.symbol,
                    "name": symbol.name,
                    "asset_class": symbol.asset_class,
                    "metrics": None,
                    "source": series.source,
                    "warning": warning,
                    "error": "insufficient_data",
                }
            )
        except Exception:
            warning = f"{symbol.name}风险计算失败"
            warnings.append(warning)
            assets.append(
                {
                    "symbol": symbol.symbol,
                    "name": symbol.name,
                    "asset_class": symbol.asset_class,
                    "metrics": None,
                    "source": series.source,
                    "warning": warning,
                    "error": "analysis_failed",
                }
            )

    return RiskReport(
        data={"assets": assets, "method": ASSET_RISK_METHOD},
        source=_source_for(loaded),
        as_of=_as_of(loaded),
        is_fallback=any(item.is_fallback for item in loaded),
        warnings=_unique(warnings),
    )


def build_portfolio_risk_report(
    service: MarketService,
    weights_pct: dict[str, float],
    lookback_days: int,
) -> RiskReport:
    validate_lookback_days(lookback_days)
    symbols, normalized_weights = normalize_portfolio_request(weights_pct)
    outcomes = _load_history(service, symbols, lookback_days)
    unavailable = [outcome.symbol.name for outcome in outcomes if outcome.series is None]
    if unavailable:
        raise RiskDataUnavailableError(f"组合历史数据不可用：{'、'.join(unavailable)}")

    loaded = [outcome.series for outcome in outcomes if outcome.series is not None]
    assets = [
        {
            "symbol": symbol.symbol,
            "name": symbol.name,
            "asset_class": symbol.asset_class,
            "weight_pct": normalized_weights[symbol.symbol],
            "source": series.source,
            "warning": series.warning,
        }
        for symbol, series in zip(symbols, loaded, strict=True)
    ]
    warnings = _series_warnings(loaded)
    as_of = _as_of(loaded)
    data: dict[str, Any]

    try:
        analysis = calculate_portfolio_risk(loaded, normalized_weights)
    except InsufficientCommonDataError as exc:
        warnings.append(str(exc))
        data = {
            "portfolio": None,
            "assets": assets,
            "method": ASSET_RISK_METHOD,
        }
    else:
        warnings.extend(analysis.warnings)
        warnings.append("历史相关性和风险指标不代表未来表现")
        data = {
            "portfolio": analysis.as_dict(),
            "assets": assets,
            "method": PORTFOLIO_RISK_METHOD,
        }
        as_of = analysis.metrics.end_date

    return RiskReport(
        data=data,
        source=_source_for(loaded),
        as_of=as_of,
        is_fallback=any(item.is_fallback for item in loaded),
        warnings=_unique(warnings),
    )
