from __future__ import annotations

import json
from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from finance_advisor.agent.actions import (
    MarketSymbolAddAction,
    MarketSymbolRemoveAction,
    PortfolioInputsPatchAction,
    ProfilePatchAction,
    RiskSymbolSelectAction,
    SymbolActionPayload,
    UiAction,
    extract_profile_patch,
    extract_symbols,
)
from finance_advisor.agent.sessions import (
    ChatMessage,
    ChatSession,
    StoredToolCall,
    get_session_store,
    sanitize_message,
)
from finance_advisor.market.symbols import (
    SymbolValidationError,
    get_symbol_catalog,
    normalize_symbol,
)
from finance_advisor.schemas import error_response, success_response
from finance_advisor.web.routes.advisor import AdvisorReportRequest, advisor_report

router = APIRouter()

FIELD_QUESTIONS = {
    "amount_cny": "这次计划投入多少金额？请用元或万元说明。",
    "horizon_months": "计划投资或持有多长时间？请用月或年说明。",
    "max_loss_pct": "最多可以承受本金亏损百分之多少？",
    "income_stability": "目前收入稳定性如何：不稳定、稳定还是非常稳定？",
    "experience": "投资经验属于无经验、基础、定期投资还是专业？",
    "liquidity_need": "这笔资金的流动性需求是高、中等还是低？",
    "emergency_fund_months": "现有应急资金可以覆盖几个月日常支出？",
}


class CreateSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(default="新咨询", min_length=1, max_length=40)


class ChatTurnRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=4_000)
    client_request_id: str = Field(
        default_factory=lambda: str(uuid4()), min_length=8, max_length=100
    )


class ApplyActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: UiAction


def _not_found() -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content=error_response("session_not_found", "会话不存在或已删除"),
    )


def _merge_profile(session: ChatSession, patch: dict[str, object]) -> None:
    session.profile = session.profile.model_copy(update=patch)


def _apply_action(session: ChatSession, action: UiAction) -> None:
    if isinstance(action, ProfilePatchAction):
        _merge_profile(session, action.payload.present())
        return
    if isinstance(action, PortfolioInputsPatchAction):
        if action.payload.profile is not None:
            _merge_profile(session, action.payload.profile.present())
        if action.payload.current_allocation_pct is not None:
            session.current_allocation_pct = action.payload.current_allocation_pct
        return

    symbol = normalize_symbol(action.payload.symbol).symbol
    if isinstance(action, MarketSymbolAddAction):
        if symbol not in session.symbols:
            if len(session.symbols) >= 8:
                raise ValueError("关注标的一次最多8个")
            session.symbols.append(symbol)
    elif isinstance(action, MarketSymbolRemoveAction):
        session.symbols = [item for item in session.symbols if item != symbol]
    elif isinstance(action, RiskSymbolSelectAction):
        session.risk_symbol = symbol


def _response_payload(
    session: ChatSession, message: ChatMessage, missing: list[str]
) -> dict[str, Any]:
    return {
        "session": session.model_dump(mode="json"),
        "message": message.model_dump(mode="json"),
        "missing_fields": missing,
        "actions": [action.model_dump(mode="json") for action in message.actions],
    }


def _decode_report(response: dict[str, object] | JSONResponse) -> tuple[int, dict[str, Any]]:
    if isinstance(response, JSONResponse):
        return response.status_code, json.loads(bytes(response.body).decode("utf-8"))
    return 200, response


def _run_turn(
    session: ChatSession,
    request: ChatTurnRequest,
    *,
    append_user: bool,
) -> dict[str, object] | JSONResponse:
    store = get_session_store()
    cleaned = sanitize_message(request.content)
    if not cleaned:
        return JSONResponse(
            status_code=400,
            content=error_response("empty_message", "咨询内容不能为空"),
        )

    if append_user:
        session.messages.append(ChatMessage(role="user", content=cleaned))
        if session.title == "新咨询":
            session.title = cleaned.replace("\n", " ")[:24]

    profile_patch = extract_profile_patch(cleaned)
    actions: list[UiAction] = []
    if profile_patch.present():
        profile_action = ProfilePatchAction(type="profile.patch", payload=profile_patch)
        _apply_action(session, profile_action)
        actions.append(profile_action)

    for symbol in extract_symbols(cleaned, get_symbol_catalog()):
        symbol_action = MarketSymbolAddAction(
            type="market.symbol.add",
            payload=SymbolActionPayload(symbol=symbol),
        )
        _apply_action(session, symbol_action)
        actions.append(symbol_action)
    if session.symbols and session.risk_symbol is None:
        risk_action = RiskSymbolSelectAction(
            type="risk.symbol.select",
            payload=SymbolActionPayload(symbol=session.symbols[0]),
        )
        _apply_action(session, risk_action)
        actions.append(risk_action)

    missing = session.profile.missing_fields()
    if missing:
        message = ChatMessage(
            role="assistant",
            content=FIELD_QUESTIONS[missing[0]],
            actions=actions,
        )
        session.messages.append(message)
        store.save(session)
        return success_response(_response_payload(session, message, missing))

    report_request = AdvisorReportRequest.model_validate(
        {
            **session.profile.present(),
            "symbols": session.symbols or ["510300", "511010", "518880", "511880"],
            "current_allocation_pct": session.current_allocation_pct,
            "client_request_id": request.client_request_id,
        }
    )
    status, report = _decode_report(advisor_report(report_request))
    if status >= 400 or not report.get("ok"):
        raw_error = report.get("error")
        error = raw_error if isinstance(raw_error, dict) else {}
        message = ChatMessage(
            role="assistant",
            content=str(error.get("message") or "Agent 咨询暂不可用，请稍后重试。"),
            status="error",
            actions=actions,
        )
        session.messages.append(message)
        store.save(session)
        return JSONResponse(status_code=status, content=report)

    data = report.get("data")
    report_data = data if isinstance(data, dict) else {}
    raw_calls = report_data.get("tool_calls")
    calls = raw_calls if isinstance(raw_calls, list) else []
    message = ChatMessage(
        role="assistant",
        content=str(report_data.get("content") or ""),
        source=str(report_data.get("source") or "system"),
        as_of=str(report_data.get("as_of")) if report_data.get("as_of") else None,
        is_fallback=bool(report_data.get("is_fallback")),
        tool_calls=[StoredToolCall.model_validate(item) for item in calls],
        actions=actions,
    )
    session.messages.append(message)
    store.save(session)
    return success_response(
        _response_payload(session, message, []),
        source=message.source,
        as_of=message.as_of,
        is_fallback=message.is_fallback,
        request_id=request.client_request_id,
    )


@router.post("", response_model=None)
def create_session(request: CreateSessionRequest) -> dict[str, object]:
    session = get_session_store().create(title=request.title)
    return success_response(session.model_dump(mode="json"))


@router.get("", response_model=None)
def list_sessions() -> dict[str, object]:
    summaries = get_session_store().list()
    return success_response({"sessions": [item.model_dump(mode="json") for item in summaries]})


@router.delete("", response_model=None)
def clear_sessions() -> dict[str, object]:
    deleted = get_session_store().clear()
    return success_response({"deleted": deleted})


@router.get("/{session_id}", response_model=None)
def get_session(session_id: str) -> dict[str, object] | JSONResponse:
    session = get_session_store().get(session_id)
    if session is None:
        return _not_found()
    return success_response(session.model_dump(mode="json"))


@router.delete("/{session_id}", response_model=None)
def delete_session(session_id: str) -> dict[str, object] | JSONResponse:
    if not get_session_store().delete(session_id):
        return _not_found()
    return success_response({"deleted": True, "session_id": session_id})


@router.post("/{session_id}/messages", response_model=None)
def send_message(session_id: str, request: ChatTurnRequest) -> dict[str, object] | JSONResponse:
    session = get_session_store().get(session_id)
    if session is None:
        return _not_found()
    return _run_turn(session, request, append_user=True)


@router.post("/{session_id}/regenerate", response_model=None)
def regenerate_message(session_id: str) -> dict[str, object] | JSONResponse:
    session = get_session_store().get(session_id)
    if session is None:
        return _not_found()
    user_message = next((item for item in reversed(session.messages) if item.role == "user"), None)
    if user_message is None:
        return JSONResponse(
            status_code=400,
            content=error_response("no_user_message", "当前会话没有可重新生成的用户消息"),
        )
    if session.messages and session.messages[-1].role == "assistant":
        session.messages.pop()
    request = ChatTurnRequest(content=user_message.content)
    return _run_turn(session, request, append_user=False)


@router.post("/{session_id}/actions", response_model=None)
def apply_action(
    session_id: str,
    request: Annotated[ApplyActionRequest, Body()],
) -> dict[str, object] | JSONResponse:
    session = get_session_store().get(session_id)
    if session is None:
        return _not_found()
    try:
        _apply_action(session, request.action)
    except (SymbolValidationError, ValueError) as exc:
        return JSONResponse(
            status_code=400,
            content=error_response("invalid_ui_action", str(exc)),
        )
    get_session_store().save(session)
    return success_response(
        {
            "session": session.model_dump(mode="json"),
            "action": request.action.model_dump(mode="json"),
        }
    )
