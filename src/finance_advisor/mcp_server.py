from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Annotated, Any
from uuid import uuid4

from mcp.server.fastmcp import FastMCP
from pydantic import Field, ValidationError

from finance_advisor.agent.tool_audit import audit_tool
from finance_advisor.allocation.service import build_portfolio_allocation
from finance_advisor.market.akshare_provider import AkshareProvider
from finance_advisor.market.cache_provider import CacheProvider
from finance_advisor.market.fixture_provider import FixtureProvider
from finance_advisor.market.models import MarketSeries
from finance_advisor.market.service import MarketService
from finance_advisor.market.symbols import (
    SymbolValidationError,
    get_symbol_catalog,
    normalize_symbols,
)
from finance_advisor.market.tushare_provider import TushareProvider
from finance_advisor.risk.portfolio import PortfolioValidationError
from finance_advisor.risk.service import (
    InvalidLookbackError,
    PortfolioWeight,
    RiskDataUnavailableError,
    build_asset_risk_report,
    build_portfolio_risk_report,
    profile_assessment_data,
)
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
            AkshareProvider(timeout_seconds=10.0, max_retries=1),
            CacheProvider(CACHE_DIR),
            FixtureProvider(FIXTURE_PATH),
            supplemental=TushareProvider(timeout_seconds=8.0, max_retries=1),
        )
    return _market_service


def _source_for(series: list[MarketSeries]) -> str:
    sources = {item.source for item in series}
    return next(iter(sources)) if len(sources) == 1 else "mixed"


def _warnings_for(series: list[MarketSeries]) -> list[str]:
    return list(dict.fromkeys(item.warning for item in series if item.warning))


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
@audit_tool("finance_health")
def finance_health() -> dict[str, Any]:
    """检查金融MCP、AKShare、Tushare、缓存目录和演示数据，不请求实时行情。"""
    request_id = str(uuid4())
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        service = get_market_service()
        data = {
            "status": "healthy",
            "akshare_installed": service.live.available(),
            "tushare_configured": bool(service.supplemental and service.supplemental.available()),
            "provider_priority": ["akshare", "tushare", "cache"],
            "cache_directory": str(CACHE_DIR),
            "cache_writable": os.access(CACHE_DIR, os.W_OK),
            "fixture_path": str(FIXTURE_PATH),
            "fixture_available": service.fixture.available(),
            "force_fixture": service.force_fixture,
            "supported_symbol_count": len(get_symbol_catalog().all()),
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
@audit_tool("get_market_snapshot")
def get_market_snapshot(
    symbols: list[str],
    audit_id: Annotated[str | None, Field(min_length=8, max_length=100)] = None,
) -> dict[str, Any]:
    """查询1到8个已校验A股指数或ETF；正常模式按AKShare、Tushare、真实缓存降级。"""
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
            "行情查询失败，AKShare、Tushare与真实行情缓存均不可用",
            retryable=True,
            request_id=request_id,
        )


@mcp.tool()
@audit_tool("assess_investor_profile")
def assess_investor_profile(
    amount_cny: float | None = None,
    horizon_months: int | None = None,
    max_loss_pct: float | None = None,
    income_stability: IncomeStability | None = None,
    experience: InvestmentExperience | None = None,
    liquidity_need: LiquidityNeed | None = None,
    emergency_fund_months: int | None = None,
    audit_id: Annotated[str | None, Field(min_length=8, max_length=100)] = None,
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
    return success_response(profile_assessment_data(profile))


@mcp.tool()
@audit_tool("analyze_asset_risk")
def analyze_asset_risk(
    symbols: list[str],
    lookback_days: int = 252,
    audit_id: Annotated[str | None, Field(min_length=8, max_length=100)] = None,
) -> dict[str, Any]:
    """使用历史收盘价计算年化收益、波动率、最大回撤、95% VaR和CVaR；不预测未来。"""
    request_id = str(uuid4())
    try:
        report = build_asset_risk_report(get_market_service(), symbols, lookback_days)
    except InvalidLookbackError as exc:
        return error_response("invalid_lookback", str(exc), request_id=request_id)
    except SymbolValidationError as exc:
        return error_response("invalid_symbol", str(exc), request_id=request_id)
    except RiskDataUnavailableError as exc:
        return error_response(
            "risk_analysis_failed",
            str(exc),
            retryable=True,
            request_id=request_id,
        )
    except Exception:
        LOGGER.exception("risk analysis failed request_id=%s", request_id)
        return error_response(
            "risk_analysis_failed",
            "风险分析失败，请检查历史数据和行情服务",
            retryable=True,
            request_id=request_id,
        )
    return success_response(
        report.data,
        source=report.source,
        as_of=report.as_of,
        is_fallback=report.is_fallback,
        warnings=list(report.warnings),
        request_id=request_id,
    )


@mcp.tool()
@audit_tool("analyze_portfolio_risk")
def analyze_portfolio_risk(
    weights_pct: dict[str, PortfolioWeight],
    lookback_days: int = 252,
) -> dict[str, Any]:
    """计算1到4个白名单ETF固定权重组合的历史相关性、净值、回撤、VaR和CVaR。"""
    request_id = str(uuid4())
    try:
        report = build_portfolio_risk_report(
            get_market_service(),
            weights_pct,
            lookback_days,
        )
    except InvalidLookbackError as exc:
        return error_response("invalid_lookback", str(exc), request_id=request_id)
    except SymbolValidationError as exc:
        return error_response("invalid_symbol", str(exc), request_id=request_id)
    except PortfolioValidationError as exc:
        return error_response("invalid_weights", str(exc), request_id=request_id)
    except RiskDataUnavailableError as exc:
        return error_response(
            "portfolio_risk_failed",
            str(exc),
            retryable=True,
            request_id=request_id,
        )
    except Exception:
        LOGGER.exception("portfolio risk failed request_id=%s", request_id)
        return error_response(
            "portfolio_risk_failed",
            "组合风险计算失败，请检查历史数据和权重",
            retryable=True,
            request_id=request_id,
        )

    return success_response(
        report.data,
        source=report.source,
        as_of=report.as_of,
        is_fallback=report.is_fallback,
        warnings=list(report.warnings),
        request_id=request_id,
    )


@mcp.tool()
@audit_tool("build_allocation")
def build_allocation(
    amount_cny: float | None = None,
    horizon_months: int | None = None,
    max_loss_pct: float | None = None,
    income_stability: IncomeStability | None = None,
    experience: InvestmentExperience | None = None,
    liquidity_need: LiquidityNeed | None = None,
    emergency_fund_months: int | None = None,
    audit_id: Annotated[str | None, Field(min_length=8, max_length=100)] = None,
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
