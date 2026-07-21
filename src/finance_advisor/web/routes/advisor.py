from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import Field

from finance_advisor.agent.hermes_cli_adapter import HermesCliAdapter, HermesCliError
from finance_advisor.allocation.service import AllocationPercentage, build_portfolio_plan
from finance_advisor.market.symbols import SymbolValidationError, normalize_symbols
from finance_advisor.risk.service import build_asset_risk_report
from finance_advisor.schemas import InvestorProfileInput, error_response, success_response
from finance_advisor.web.common import (
    PROJECT_ROOT,
    get_market_service,
    load_market_series,
    source_for,
    warnings_for,
)

LOGGER = logging.getLogger(__name__)
REQUIRED_REPORT_SECTIONS = (
    "用户画像",
    "行情摘要",
    "风险指标",
    "配置建议",
    "建议原因",
    "数据时间与来源",
    "风险提示",
)
REQUIRED_RISK_TERMS = ("年化波动率", "最大回撤", "VaR", "CVaR")


class AdvisorReportRequest(InvestorProfileInput):
    symbols: list[str] = Field(
        default_factory=lambda: ["510300", "511010", "518880", "511880"],
        min_length=1,
        max_length=4,
    )
    current_allocation_pct: dict[str, AllocationPercentage] | None = None


router = APIRouter()


def get_hermes_adapter() -> HermesCliAdapter:
    executable = os.getenv("HERMES_CLI")
    if not executable:
        bundled = PROJECT_ROOT / ".venv" / "Scripts" / "hermes.exe"
        executable = str(bundled) if bundled.is_file() else "hermes"
    return HermesCliAdapter(
        project_root=PROJECT_ROOT,
        hermes_home=_adapter_home(),
        executable=executable,
    )


def _adapter_home() -> Path:
    configured = os.getenv("HERMES_HOME")
    if configured:
        configured_path = Path(configured)
        return configured_path if configured_path.is_absolute() else PROJECT_ROOT / configured_path
    return PROJECT_ROOT / ".runtime" / "hermes"


def _build_report_prompt(
    *,
    profile: AdvisorReportRequest,
    portfolio_plan: dict[str, object],
    snapshots: list[dict[str, object]],
    asset_risk: dict[str, Any],
    source: str,
    as_of: str,
    warnings: list[str],
) -> str:
    request_data = profile.model_dump(mode="json")
    deterministic_comparison: dict[str, Any] = {
        key: portfolio_plan[key]
        for key in (
            "current_allocation_pct",
            "current_allocation_amount_cny",
            "allocation_deviation_pct",
            "allocation_deviation_amount_cny",
        )
        if portfolio_plan.get(key) is not None
    }
    deterministic_portfolio: dict[str, Any] = {
        key: portfolio_plan[key]
        for key in (
            "risk_score",
            "scored_risk_level",
            "effective_risk_level",
            "constraints_applied",
            "allocation_pct",
            "allocation_amount_cny",
            "rationale",
        )
    }
    context: dict[str, Any] = {
        "validated_request": request_data,
        "deterministic_market_snapshots": snapshots,
        "deterministic_asset_risk": asset_risk,
        "deterministic_portfolio": deterministic_portfolio,
        "deterministic_current_vs_target": deterministic_comparison or None,
        "market_metadata_preflight": {
            "source": source,
            "as_of": as_of,
            "warnings": warnings,
        },
    }
    return (
        "你是金融理财课程演示系统的报告撰写 Agent。必须实际调用 finance MCP 工具，"
        "不得仅凭提示词自行计算或编造金融数值。为控制响应时间，请在同一轮并行调用以下"
        "四个只读工具：\n"
        "- assess_investor_profile：评估完整七项画像；\n"
        "- get_market_snapshot：查询 validated_request.symbols；\n"
        "- analyze_asset_risk：分析相同标的，lookback_days=252；\n"
        "- build_allocation：生成确定性配置比例和金额。\n"
        "工具结果返回后再统一撰写报告。如任一工具失败，明确说明失败和缺失内容，不得补造数字。\n"
        "deterministic_* 字段由相同的确定性金融服务预先计算，仅用于核验工具结果和防止遗漏，"
        "可以引用但不得改写或重新计算。报告必须使用以下完全一致的 Markdown 二级标题并按"
        "顺序输出：用户画像、行情摘要、风险指标、配置建议、建议原因、数据时间与来源、风险提示。"
        "风险指标必须逐项写明可用标的的年化波动率、最大回撤、VaR 和 CVaR；配置建议必须写明"
        "比例与金额。fixture 必须显著标注"
        "“演示数据/非实时数据”。禁止承诺收益，禁止预测必涨必跌，禁止给出买入、卖出、"
        "加仓等真实交易指令。风险提示必须包含“历史表现不代表未来收益”。\n\n"
        f"已校验请求上下文 JSON：\n{json.dumps(context, ensure_ascii=False, indent=2)}"
    )


def _validate_report_content(content: str, *, require_fixture_label: bool) -> None:
    missing = [section for section in REQUIRED_REPORT_SECTIONS if section not in content]
    missing.extend(term for term in REQUIRED_RISK_TERMS if term not in content)
    if "历史表现不代表未来收益" not in content:
        missing.append("历史表现不代表未来收益")
    if require_fixture_label and not ("演示数据" in content and "非实时数据" in content):
        missing.append("演示数据/非实时数据")
    if missing:
        raise HermesCliError(
            "hermes_incomplete_report",
            f"Hermes 报告缺少必要内容：{'、'.join(missing)}",
            retryable=True,
        )


@router.post("/report", response_model=None)
def advisor_report(request: AdvisorReportRequest) -> dict[str, object] | JSONResponse:
    try:
        normalized = normalize_symbols(request.symbols)
    except SymbolValidationError as exc:
        return JSONResponse(
            status_code=400,
            content=error_response("invalid_symbol", str(exc)),
        )

    try:
        service = get_market_service()
        loaded = load_market_series(normalized, service.get_snapshot)
        snapshots = [item.snapshot() for item in loaded]
        as_of = max(str(item["trade_date"]) for item in snapshots)
        source = source_for(loaded)
        warnings = warnings_for(loaded)
        portfolio_plan = build_portfolio_plan(request, request.current_allocation_pct)
        risk_report = build_asset_risk_report(
            service,
            [symbol.symbol for symbol in normalized],
            252,
        )
    except ValueError as exc:
        return JSONResponse(
            status_code=400,
            content=error_response("invalid_advisor_report_request", str(exc)),
        )
    except Exception:
        LOGGER.exception("advisor deterministic data preparation failed")
        return JSONResponse(
            status_code=503,
            content=error_response(
                "advisor_data_unavailable",
                "报告所需的行情、画像或配置数据暂不可用。",
                retryable=True,
            ),
        )

    prompt = _build_report_prompt(
        profile=request,
        portfolio_plan=portfolio_plan,
        snapshots=snapshots,
        asset_risk=risk_report.data,
        source=source,
        as_of=as_of,
        warnings=warnings,
    )
    try:
        content = get_hermes_adapter().generate_report(prompt)
        _validate_report_content(
            content,
            require_fixture_label=any(item.source == "fixture" for item in loaded),
        )
    except OSError as exc:
        LOGGER.warning("Hermes CLI could not start error_type=%s", type(exc).__name__)
        return JSONResponse(
            status_code=503,
            content=error_response(
                "model_unavailable",
                "Hermes CLI 未安装或不在 PATH 中，请先完成运行环境配置。",
                retryable=True,
            ),
        )
    except HermesCliError as exc:
        return JSONResponse(
            status_code=503 if exc.retryable else 400,
            content=error_response(exc.code, exc.message, retryable=exc.retryable),
        )

    return success_response(
        {
            "content": content,
            "source": source,
            "as_of": as_of,
            "is_fallback": any(item.is_fallback for item in loaded),
            "warnings": warnings,
        },
        source=source,
        as_of=as_of,
        is_fallback=any(item.is_fallback for item in loaded),
        warnings=warnings,
    )
