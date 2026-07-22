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
from finance_advisor.agent.conversation import (
    ConversationPlan,
    build_conversation_prompt,
    plan_conversation_turn,
)
from finance_advisor.agent.hermes_cli_adapter import HermesCliError
from finance_advisor.agent.sessions import (
    ChatMessage,
    ChatSession,
    StoredToolCall,
    get_session_store,
    sanitize_message,
)
from finance_advisor.agent.tool_audit import ToolAuditEvent, read_tool_audit
from finance_advisor.market.symbols import (
    SymbolValidationError,
    get_symbol_catalog,
    normalize_symbol,
)
from finance_advisor.schemas import error_response, success_response
from finance_advisor.web.routes.advisor import (
    AdvisorReportRequest,
    advisor_report,
    get_hermes_adapter,
)

router = APIRouter()


class CreateSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(default="新咨询", min_length=1, max_length=40)


class ChatTurnRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=4_000)
    client_request_id: str = Field(
        default_factory=lambda: str(uuid4()), min_length=8, max_length=100
    )


class RegenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

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


def _event_metadata(
    events: list[ToolAuditEvent],
) -> tuple[str, str | None, bool]:
    financial = [
        event for event in events if event.tool in {"get_market_snapshot", "analyze_asset_risk"}
    ]
    sources = {event.source for event in financial if event.source}
    source = next(iter(sources)) if len(sources) == 1 else "mixed" if sources else "system"
    dates = [event.as_of for event in financial if event.as_of]
    return source, max(dates) if dates else None, any(event.is_fallback for event in financial)


def _stored_tool_calls(events: list[ToolAuditEvent]) -> list[StoredToolCall]:
    return [
        StoredToolCall.model_validate(event.model_dump(exclude={"audit_id"})) for event in events
    ]


def _missing_tools(plan: ConversationPlan, events: list[ToolAuditEvent]) -> list[str]:
    called = {event.tool for event in events}
    return [tool for tool in plan.required_tools if tool not in called]


def _natural_agent_message(
    session: ChatSession,
    request: ChatTurnRequest,
    cleaned: str,
    plan: ConversationPlan,
    actions: list[UiAction],
) -> ChatMessage:
    adapter = get_hermes_adapter()
    configuration_error = adapter.configuration_error()
    if configuration_error is not None:
        raise configuration_error

    prompt = build_conversation_prompt(
        messages=session.messages,
        latest_content=cleaned,
        plan=plan,
        profile=session.profile,
        audit_id=request.client_request_id,
    )
    content = adapter.generate_response(prompt, audit_id=request.client_request_id)
    events = read_tool_audit(request.client_request_id)
    missing_tools = _missing_tools(plan, events)
    if missing_tools and not events:
        retry_prompt = (
            prompt + "\n上一轮没有实际调用本轮必需工具，响应已被拒绝。"
            "现在先调用指定工具，收到结果后再回答；最多执行这一次纠正。"
        )
        content = adapter.generate_response(retry_prompt, audit_id=request.client_request_id)
        events = read_tool_audit(request.client_request_id)
        missing_tools = _missing_tools(plan, events)
    if missing_tools:
        raise HermesCliError(
            "mcp_tool_calls_incomplete",
            f"Agent 未完成必要金融工具调用：{'、'.join(missing_tools)}",
            retryable=True,
        )

    source, as_of, is_fallback = _event_metadata(events)
    return ChatMessage(
        role="assistant",
        content=content,
        source=source,
        as_of=as_of,
        is_fallback=is_fallback,
        tool_calls=_stored_tool_calls(events),
        actions=actions,
    )


def _agent_error_response(
    session: ChatSession,
    *,
    actions: list[UiAction],
    code: str,
    message: str,
    retryable: bool,
    status_code: int,
) -> JSONResponse:
    session.messages.append(
        ChatMessage(
            role="assistant",
            content=message,
            status="cancelled" if code == "generation_cancelled" else "error",
            actions=actions,
        )
    )
    get_session_store().save(session)
    return JSONResponse(
        status_code=status_code,
        content=error_response(code, message, retryable=retryable),
    )


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

    mentioned_symbols = extract_symbols(cleaned, get_symbol_catalog())
    for symbol in mentioned_symbols:
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

    plan = plan_conversation_turn(
        cleaned,
        profile=session.profile,
        mentioned_symbols=mentioned_symbols,
        contextual_symbols=(
            [session.risk_symbol] if session.risk_symbol is not None else session.symbols
        ),
        personalization_active=session.personalization_active,
    )
    session.personalization_active = plan.kind in {"personalized_followup", "formal_report"}
    if plan.kind != "formal_report":
        try:
            message = _natural_agent_message(session, request, cleaned, plan, actions)
        except OSError:
            return _agent_error_response(
                session,
                actions=actions,
                code="model_unavailable",
                message="Hermes CLI 未安装或无法启动，请先完成本地运行环境配置。",
                retryable=True,
                status_code=503,
            )
        except HermesCliError as exc:
            status_code = (
                409 if exc.code == "generation_cancelled" else 503 if exc.retryable else 400
            )
            return _agent_error_response(
                session,
                actions=actions,
                code=exc.code,
                message=exc.message,
                retryable=exc.retryable,
                status_code=status_code,
            )
        session.messages.append(message)
        store.save(session)
        return success_response(
            _response_payload(session, message, plan.missing_fields),
            source=message.source,
            as_of=message.as_of,
            is_fallback=message.is_fallback,
            request_id=request.client_request_id,
        )

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
        code = str(error.get("code") or "advisor_unavailable")
        return _agent_error_response(
            session,
            actions=actions,
            code=code,
            message=str(error.get("message") or "Agent 咨询暂不可用，请稍后重试。"),
            retryable=bool(error.get("retryable")),
            status_code=status,
        )

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
    session.personalization_active = False
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
def regenerate_message(
    session_id: str,
    request: Annotated[RegenerateRequest | None, Body()] = None,
) -> dict[str, object] | JSONResponse:
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
    turn_request = ChatTurnRequest(
        content=user_message.content,
        client_request_id=(request.client_request_id if request is not None else str(uuid4())),
    )
    return _run_turn(session, turn_request, append_user=False)


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
