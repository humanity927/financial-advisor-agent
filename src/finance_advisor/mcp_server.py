from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any
from uuid import uuid4

from mcp.server.fastmcp import FastMCP
from pydantic import ValidationError

from finance_advisor.allocation.service import build_portfolio_allocation
from finance_advisor.market.akshare_provider import AkshareProvider
from finance_advisor.market.cache_provider import CacheProvider
from finance_advisor.market.fixture_provider import FixtureProvider
from finance_advisor.market.models import MarketSeries
from finance_advisor.market.service import MarketService
from finance_advisor.market.symbols import (
    SymbolInfo,
    SymbolValidationError,
    normalize_symbol,
    normalize_symbols,
)
from finance_advisor.risk.metrics import InsufficientDataError, calculate_risk_metrics
from finance_advisor.risk.portfolio import (
    InsufficientCommonDataError,
    PortfolioValidationError,
    calculate_portfolio_risk,
    validate_portfolio_weights,
)
from finance_advisor.risk.profile import assess_profile, profile_chart_data
from finance_advisor.schemas import (
    IncomeStability,
    InvestmentExperience,
    InvestorProfileInput,
    LiquidityNeed,
    error_response,
    success_response,
)

logging.basicConfig(
    level=os.getenv("FINANCE_LOG_LEVEL", "INFO"),
    stream=sys.stderr,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
LOGGER = logging.getLogger(__name__)

PROJECT_ROOT = Path(
    os.getenv("FINANCE_PROJECT_ROOT", Path(__file__).resolve().parents[2])
).resolve()
CACHE_DIR = Path(os.getenv("FINANCE_CACHE_DIR", PROJECT_ROOT / ".runtime" / "cache"))
FIXTURE_PATH = Path(
    os.getenv(
        "FINANCE_FIXTURE_PATH",
        PROJECT_ROOT / "data" / "fixtures" / "market_data.json",
    )
)

mcp = FastMCP("finance")
_market_service: MarketService | None = None


def get_market_service() -> MarketService:
    global _market_service
    if _market_service is None:
        _market_service = MarketService(
            AkshareProvider(timeout_seconds=8.0, max_retries=2),
            CacheProvider(CACHE_DIR),
            FixtureProvider(FIXTURE_PATH),
        )
    return _market_service


def _source_for(series: list[MarketSeries]) -> str:
    sources = {item.source for item in series}
    return next(iter(sources)) if len(sources) == 1 else "mixed"


def _warnings_for(series: list[MarketSeries]) -> list[str]:
    return list(dict.fromkeys(item.warning for item in series if item.warning))


def _normalize_portfolio_weights(
    weights_pct: dict[str, float],
) -> tuple[list[SymbolInfo], dict[str, float]]:
    if not weights_pct:
        raise PortfolioValidationError("weights_pct至少需要一个标的")
    if len(weights_pct) > 4:
        raise PortfolioValidationError("weights_pct一次最多包含4个标的")

    symbols: list[SymbolInfo] = []
    normalized: dict[str, float] = {}
    for raw_symbol, weight in weights_pct.items():
        symbol = normalize_symbol(raw_symbol)
        if symbol.symbol in normalized:
            raise PortfolioValidationError(f"标的{symbol.symbol}通过代码或别名重复出现")
        symbols.append(symbol)
        normalized[symbol.symbol] = weight
    return symbols, validate_portfolio_weights(normalized)


PROFILE_FIELDS = {
    "amount_cny": "投资金额",
    "horizon_months": "投资期限（月）",
    "max_loss_pct": "最大可承受亏损（%）",
    "income_stability": "收入稳定性",
    "experience": "投资经验",
    "liquidity_need": "流动性需求",
    "emergency_fund_months": "应急资金可覆盖月数",
}


def _profile_or_error(**values: Any) -> InvestorProfileInput | dict[str, Any]:
    missing = [PROFILE_FIELDS[name] for name, value in values.items() if value is None]
    if missing:
        return error_response(
            "missing_fields",
            "用户信息不完整，请先追问缺失字段",
            data={"missing_fields": missing},
        )
    try:
        return InvestorProfileInput.model_validate(values)
    except ValidationError as exc:
        errors = [
            {"field": ".".join(str(part) for part in item["loc"]), "message": item["msg"]}
            for item in exc.errors(include_url=False, include_input=False)
        ]
        return error_response(
            "invalid_profile",
            "投资者信息格式或取值无效",
            data={"validation_errors": errors},
        )


@mcp.tool()
def finance_health() -> dict[str, Any]:
    """检查金融MCP、AKShare、缓存目录和离线演示数据是否可用，不请求实时行情。"""
    request_id = str(uuid4())
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        service = get_market_service()
        data = {
            "status": "healthy",
            "akshare_installed": service.live.available(),
            "cache_directory": str(CACHE_DIR),
            "cache_writable": os.access(CACHE_DIR, os.W_OK),
            "fixture_path": str(FIXTURE_PATH),
            "fixture_available": service.fixture.available(),
            "force_fixture": service.force_fixture,
            "supported_symbol_count": 4,
        }
        return success_response(data, request_id=request_id)
    except Exception:
        LOGGER.exception("finance_health failed request_id=%s", request_id)
        return error_response(
            "health_check_failed",
            "金融工具健康检查失败，请检查本地配置",
            request_id=request_id,
        )


@mcp.tool()
def get_market_snapshot(symbols: list[str]) -> dict[str, Any]:
    """查询1到4个白名单ETF的最近行情；所有价格均来自AKShare、缓存或明确标记的演示数据。"""
    request_id = str(uuid4())
    try:
        normalized = normalize_symbols(symbols)
        series = [get_market_service().get_snapshot(symbol) for symbol in normalized]
        snapshots = [item.snapshot() for item in series]
        as_of = max(str(item["trade_date"]) for item in snapshots)
        return success_response(
            {"snapshots": snapshots},
            source=_source_for(series),
            as_of=as_of,
            is_fallback=any(item.is_fallback for item in series),
            warnings=_warnings_for(series),
            request_id=request_id,
        )
    except SymbolValidationError as exc:
        return error_response("invalid_symbol", str(exc), request_id=request_id)
    except Exception:
        LOGGER.exception("get_market_snapshot failed request_id=%s", request_id)
        return error_response(
            "market_data_unavailable",
            "行情查询失败，且缓存与演示数据均不可用",
            retryable=True,
            request_id=request_id,
        )


@mcp.tool()
def assess_investor_profile(
    amount_cny: float | None = None,
    horizon_months: int | None = None,
    max_loss_pct: float | None = None,
    income_stability: IncomeStability | None = None,
    experience: InvestmentExperience | None = None,
    liquidity_need: LiquidityNeed | None = None,
    emergency_fund_months: int | None = None,
) -> dict[str, Any]:
    """根据用户明确提供的7项信息计算可复现的风险分数；缺失信息会返回missing_fields。"""
    profile = _profile_or_error(
        amount_cny=amount_cny,
        horizon_months=horizon_months,
        max_loss_pct=max_loss_pct,
        income_stability=income_stability,
        experience=experience,
        liquidity_need=liquidity_need,
        emergency_fund_months=emergency_fund_months,
    )
    if isinstance(profile, dict):
        return profile
    assessment = assess_profile(profile)
    data = assessment.model_dump(mode="json")
    data["dimensions"] = profile_chart_data(assessment)
    return success_response(data)


@mcp.tool()
def analyze_asset_risk(
    symbols: list[str],
    lookback_days: int = 252,
) -> dict[str, Any]:
    """使用历史收盘价计算年化收益、波动率、最大回撤、95% VaR和CVaR；不预测未来。"""
    request_id = str(uuid4())
    if lookback_days < 60 or lookback_days > 1260:
        return error_response(
            "invalid_lookback",
            "lookback_days必须在60到1260之间",
            request_id=request_id,
        )
    try:
        normalized = normalize_symbols(symbols)
    except SymbolValidationError as exc:
        return error_response("invalid_symbol", str(exc), request_id=request_id)

    results: list[dict[str, Any]] = []
    loaded: list[MarketSeries] = []
    warnings: list[str] = []
    for symbol in normalized:
        try:
            series = get_market_service().get_history(symbol, lookback_days)
            loaded.append(series)
            metrics = calculate_risk_metrics(series.bars)
            results.append(
                {
                    "symbol": symbol.symbol,
                    "name": symbol.name,
                    "metrics": metrics.as_dict(),
                    "source": series.source,
                    "warning": series.warning,
                }
            )
        except InsufficientDataError as exc:
            warnings.append(str(exc))
            results.append(
                {
                    "symbol": symbol.symbol,
                    "name": symbol.name,
                    "metrics": None,
                    "error": "insufficient_data",
                }
            )
        except Exception:
            LOGGER.exception(
                "risk analysis failed symbol=%s request_id=%s", symbol.symbol, request_id
            )
            warnings.append(f"{symbol.name}风险计算失败")
            results.append(
                {
                    "symbol": symbol.symbol,
                    "name": symbol.name,
                    "metrics": None,
                    "error": "analysis_failed",
                }
            )

    if not loaded:
        return error_response(
            "risk_analysis_failed",
            "所有标的的历史数据均不可用",
            data={"assets": results},
            retryable=True,
            request_id=request_id,
        )
    as_of = max(item.bars[-1].date.isoformat() for item in loaded)
    return success_response(
        {"assets": results, "method": "历史数据统计，不代表未来表现"},
        source=_source_for(loaded),
        as_of=as_of,
        is_fallback=any(item.is_fallback for item in loaded),
        warnings=list(dict.fromkeys(_warnings_for(loaded) + warnings)),
        request_id=request_id,
    )


@mcp.tool()
def analyze_portfolio_risk(
    weights_pct: dict[str, float],
    lookback_days: int = 252,
) -> dict[str, Any]:
    """计算1到4个白名单ETF固定权重组合的历史相关性、净值、回撤、VaR和CVaR。"""
    request_id = str(uuid4())
    if lookback_days < 60 or lookback_days > 1260:
        return error_response(
            "invalid_lookback",
            "lookback_days必须在60到1260之间",
            request_id=request_id,
        )

    try:
        symbols, normalized_weights = _normalize_portfolio_weights(weights_pct)
    except SymbolValidationError as exc:
        return error_response("invalid_symbol", str(exc), request_id=request_id)
    except PortfolioValidationError as exc:
        return error_response("invalid_weights", str(exc), request_id=request_id)

    try:
        loaded = [get_market_service().get_history(symbol, lookback_days) for symbol in symbols]
    except Exception:
        LOGGER.exception("portfolio history loading failed request_id=%s", request_id)
        return error_response(
            "portfolio_risk_failed",
            "组合历史数据加载失败，请检查行情服务",
            retryable=True,
            request_id=request_id,
        )

    assets = [
        {
            "symbol": symbol.symbol,
            "name": symbol.name,
            "asset_class": symbol.asset_class,
            "weight_pct": normalized_weights[symbol.symbol],
            "source": item.source,
            "warning": item.warning,
        }
        for symbol, item in zip(symbols, loaded, strict=True)
    ]
    bar_dates = [bar.date.isoformat() for item in loaded for bar in item.bars]
    as_of = max(bar_dates) if bar_dates else max(item.fetched_at for item in loaded)

    try:
        analysis = calculate_portfolio_risk(loaded, normalized_weights)
    except InsufficientCommonDataError as exc:
        return success_response(
            {
                "portfolio": None,
                "assets": assets,
                "method": "历史数据统计，不代表未来表现",
            },
            source=_source_for(loaded),
            as_of=as_of,
            is_fallback=any(item.is_fallback for item in loaded),
            warnings=list(dict.fromkeys(_warnings_for(loaded) + [str(exc)])),
            request_id=request_id,
        )
    except PortfolioValidationError as exc:
        return error_response("invalid_weights", str(exc), request_id=request_id)
    except Exception:
        LOGGER.exception("portfolio risk calculation failed request_id=%s", request_id)
        return error_response(
            "portfolio_risk_failed",
            "组合风险计算失败，请检查历史数据和权重",
            retryable=True,
            request_id=request_id,
        )

    return success_response(
        {
            "portfolio": analysis.as_dict(),
            "assets": assets,
            "method": "固定权重每日再平衡的历史组合统计，不代表未来表现",
        },
        source=_source_for(loaded),
        as_of=analysis.metrics.end_date,
        is_fallback=any(item.is_fallback for item in loaded),
        warnings=list(
            dict.fromkeys(
                _warnings_for(loaded)
                + list(analysis.warnings)
                + ["历史相关性和风险指标不代表未来表现"]
            )
        ),
        request_id=request_id,
    )


@mcp.tool()
def build_allocation(
    amount_cny: float | None = None,
    horizon_months: int | None = None,
    max_loss_pct: float | None = None,
    income_stability: IncomeStability | None = None,
    experience: InvestmentExperience | None = None,
    liquidity_need: LiquidityNeed | None = None,
    emergency_fund_months: int | None = None,
) -> dict[str, Any]:
    """根据完整用户画像生成透明、确定性的四类资产配置，不执行交易。"""
    profile = _profile_or_error(
        amount_cny=amount_cny,
        horizon_months=horizon_months,
        max_loss_pct=max_loss_pct,
        income_stability=income_stability,
        experience=experience,
        liquidity_need=liquidity_need,
        emergency_fund_months=emergency_fund_months,
    )
    if isinstance(profile, dict):
        return profile
    return success_response(
        build_portfolio_allocation(profile),
        warnings=["该配置仅用于教学演示，不构成投资建议"],
    )


def main() -> None:
    mcp.run()


if __name__ == "__main__":  # pragma: no cover
    main()
