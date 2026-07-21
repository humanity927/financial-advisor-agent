from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import Field

from finance_advisor.agent.hermes_cli_adapter import (
    HermesCliAdapter,
    HermesCliError,
    cancel_run,
)
from finance_advisor.agent.tool_audit import (
    ToolAuditEvent,
    missing_required_tools,
    read_tool_audit,
)
from finance_advisor.allocation.service import AllocationPercentage
from finance_advisor.market.symbols import SymbolValidationError, normalize_symbols
from finance_advisor.schemas import InvestorProfileInput, error_response, success_response
from finance_advisor.web.common import PROJECT_ROOT

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
        max_length=8,
    )
    current_allocation_pct: dict[str, AllocationPercentage] | None = None
    client_request_id: str | None = Field(default=None, min_length=8, max_length=100)


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


def _build_report_prompt(*, profile: AdvisorReportRequest, audit_id: str) -> str:
    tool_profile = profile.model_dump(
        mode="json",
        exclude={"current_allocation_pct", "client_request_id", "symbols"},
    )
    context = {
        "profile": tool_profile,
        "symbols": profile.symbols,
    }
    audited_profile = {**tool_profile, "audit_id": audit_id}
    profile_arguments = json.dumps(audited_profile, ensure_ascii=False, separators=(",", ":"))
    symbol_arguments = json.dumps(
        {"symbols": profile.symbols, "audit_id": audit_id},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    risk_arguments = json.dumps(
        {"symbols": profile.symbols, "lookback_days": 252, "audit_id": audit_id},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return (
        "你是金融理财课程演示系统的报告 Agent。下方 JSON 只包含经过 Pydantic 校验的"
        "用户输入，不包含任何金融结果。必须实际调用 finance MCP（工具名可能带"
        " mcp_finance_ 前缀）的四个工具，并且每个工具"
        "恰好使用 JSON 中对应参数：assess_investor_profile、get_market_snapshot、"
        "analyze_asset_risk（lookback_days=252）、build_allocation。不得自行计算、改写或"
        "补造价格、风险指标、比例和金额。第一步必须直接发起以下四个工具调用，在四个结果"
        "全部返回前不要输出报告正文：\n"
        f"1. assess_investor_profile({profile_arguments})\n"
        f"2. get_market_snapshot({symbol_arguments})\n"
        f"3. analyze_asset_risk({risk_arguments})\n"
        f"4. build_allocation({profile_arguments})\n"
        "任一工具返回失败时，仍须明确写出失败项和来源，"
        "不能用常识补数。\n"
        "最终回答必须按顺序使用以下 Markdown 二级标题：用户画像、行情摘要、风险指标、"
        "配置建议、建议原因、数据时间与来源、风险提示。风险指标逐项包含年化波动率、"
        "最大回撤、VaR、CVaR；配置包含工具返回的比例与金额。缓存必须写明缓存和过期状态；"
        "fixture 必须显著写明“演示数据/非实时数据”。禁止收益承诺、涨跌预测和买入、卖出、"
        "加仓等交易指令。风险提示必须原样包含“历史表现不代表未来收益”和"
        "“VaR/CVaR不覆盖所有极端市场事件”。\n"
        f"已校验输入 JSON：{json.dumps(context, ensure_ascii=False, separators=(',', ':'))}"
    )


def _validate_report_content(content: str, *, require_fixture_label: bool) -> None:
    missing = [section for section in REQUIRED_REPORT_SECTIONS if section not in content]
    missing.extend(term for term in REQUIRED_RISK_TERMS if term not in content)
    if "历史表现不代表未来收益" not in content:
        missing.append("历史表现不代表未来收益")
    if "VaR/CVaR不覆盖所有极端市场事件" not in content.replace(" ", ""):
        missing.append("VaR/CVaR不覆盖所有极端市场事件")
    if require_fixture_label and not ("演示数据" in content and "非实时数据" in content):
        missing.append("演示数据/非实时数据")
    if missing:
        raise HermesCliError(
            "hermes_incomplete_report",
            f"Hermes 报告缺少必要内容：{'、'.join(dict.fromkeys(missing))}",
            retryable=True,
        )


def _tool_status(events: list[ToolAuditEvent]) -> list[dict[str, Any]]:
    return [event.model_dump(mode="json", exclude={"audit_id"}) for event in events]


def _report_metadata(events: list[ToolAuditEvent]) -> tuple[str, str | None, bool, list[str]]:
    financial = [
        event for event in events if event.tool in {"get_market_snapshot", "analyze_asset_risk"}
    ]
    sources = {event.source for event in financial if event.source}
    source = next(iter(sources)) if len(sources) == 1 else "mixed" if sources else "system"
    dates = [event.as_of for event in financial if event.as_of]
    as_of = max(dates) if dates else None
    is_fallback = any(event.source in {"cache", "fixture"} for event in financial)
    warnings = [
        f"{event.tool} 调用失败（{event.error_code or 'unknown_error'}）"
        for event in events
        if not event.ok
    ]
    return source, as_of, is_fallback, warnings


@router.post("/report", response_model=None)
def advisor_report(request: AdvisorReportRequest) -> dict[str, object] | JSONResponse:
    try:
        normalized = normalize_symbols(request.symbols)
    except SymbolValidationError as exc:
        return JSONResponse(status_code=400, content=error_response("invalid_symbol", str(exc)))
    request.symbols = [item.symbol for item in normalized]

    audit_id = request.client_request_id or str(uuid4())
    adapter = get_hermes_adapter()
    configuration_error = adapter.configuration_error()
    if configuration_error is not None:
        return JSONResponse(
            status_code=400,
            content=error_response(
                configuration_error.code,
                configuration_error.message,
                retryable=configuration_error.retryable,
            ),
        )

    try:
        prompt = _build_report_prompt(profile=request, audit_id=audit_id)
        content = adapter.generate_report(prompt, audit_id=audit_id)
        events = read_tool_audit(audit_id)
        missing_tools = missing_required_tools(events)
        if missing_tools:
            retry_prompt = (
                prompt + "\n上一轮未执行任何必要工具，报告因此被拒绝。现在必须先实际调用上述四个"
                " finance MCP 工具；不要仅复述工具名称或根据输入直接写报告。"
            )
            content = adapter.generate_report(retry_prompt, audit_id=audit_id)
            events = read_tool_audit(audit_id)
            missing_tools = missing_required_tools(events)
        if missing_tools:
            raise HermesCliError(
                "mcp_tool_calls_incomplete",
                f"Hermes 未完成必要金融工具调用：{'、'.join(missing_tools)}",
                retryable=True,
            )
        _validate_report_content(
            content,
            require_fixture_label=any(event.source == "fixture" for event in events),
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

    source, as_of, is_fallback, warnings = _report_metadata(events)
    return success_response(
        {
            "content": content,
            "source": source,
            "as_of": as_of,
            "is_fallback": is_fallback,
            "warnings": warnings,
            "tool_calls": _tool_status(events),
            "request_id": audit_id,
        },
        source=source,
        as_of=as_of,
        is_fallback=is_fallback,
        warnings=warnings,
        request_id=audit_id,
    )


@router.post("/runs/{request_id}/cancel", response_model=None)
def cancel_advisor_run(request_id: str) -> dict[str, object]:
    cancelled = cancel_run(request_id)
    return success_response(
        {"request_id": request_id, "cancelled": cancelled},
        request_id=request_id,
    )
