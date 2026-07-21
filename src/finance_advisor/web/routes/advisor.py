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
from finance_advisor.allocation.service import build_portfolio_plan
from finance_advisor.market.symbols import SymbolValidationError, normalize_symbols
from finance_advisor.schemas import InvestorProfileInput, error_response, success_response
from finance_advisor.web.common import (
    PROJECT_ROOT,
    get_market_service,
    load_market_series,
    source_for,
    warnings_for,
)

LOGGER = logging.getLogger(__name__)


class AdvisorReportRequest(InvestorProfileInput):
    symbols: list[str] = Field(default_factory=lambda: ["510300", "511010", "518880", "511880"])
    current_allocation_pct: dict[str, float] | None = None


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
    source: str,
    as_of: str,
    warnings: list[str],
) -> str:
    facts: dict[str, Any] = {
        "investor_profile": profile.model_dump(
            mode="json",
            exclude={"symbols", "current_allocation_pct"},
        ),
        "market_snapshots": snapshots,
        "portfolio_plan": portfolio_plan,
        "source": source,
        "as_of": as_of,
        "warnings": warnings,
    }
    return (
        "你是金融理财课程演示系统的报告撰写 Agent。"
        "只能基于下方 JSON 中的确定性事实生成报告，不得编造行情、比例或收益。"
        "报告必须包含：用户画像、行情摘要、风险与约束、资产配置建议、建议原因、"
        "数据时间与来源、风险提示。禁止承诺收益，禁止给出买入、卖出、加仓等真实交易指令。\n\n"
        f"确定性事实 JSON：\n{json.dumps(facts, ensure_ascii=False, indent=2)}"
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
        source=source,
        as_of=as_of,
        warnings=warnings,
    )
    try:
        content = get_hermes_adapter().generate_report(prompt)
    except FileNotFoundError:
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
