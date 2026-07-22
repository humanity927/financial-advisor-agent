from __future__ import annotations

import os
from collections.abc import Callable
from functools import wraps
from pathlib import Path
from typing import Any, ParamSpec, TypeVar, cast

from pydantic import BaseModel, ConfigDict, Field

from finance_advisor.schemas import now_iso

REQUIRED_REPORT_TOOLS = (
    "assess_investor_profile",
    "get_market_snapshot",
    "analyze_asset_risk",
    "build_allocation",
)

P = ParamSpec("P")
R = TypeVar("R", bound=dict[str, Any])


class ToolAuditEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    audit_id: str = Field(min_length=1, max_length=100)
    tool: str = Field(min_length=1, max_length=100)
    called_at: str
    ok: bool
    source: str = "system"
    as_of: str | None = None
    is_fallback: bool = False
    error_code: str | None = None
    summary: dict[str, Any] = Field(default_factory=dict)


def audit_path() -> Path:
    project_root = Path(__file__).resolve().parents[3]
    return Path(
        os.getenv(
            "FINANCE_TOOL_AUDIT_PATH",
            project_root / ".runtime" / "logs" / "mcp-tool-audit.jsonl",
        )
    ).resolve()


def _summary(tool: str, result: dict[str, Any]) -> dict[str, Any]:
    raw_data = result.get("data")
    data: dict[str, Any] = raw_data if isinstance(raw_data, dict) else {}
    if tool == "assess_investor_profile":
        return {
            "risk_level": data.get("risk_level"),
            "score": data.get("score"),
        }
    if tool == "get_market_snapshot":
        raw_snapshots = data.get("snapshots")
        snapshots: list[Any] = raw_snapshots if isinstance(raw_snapshots, list) else []
        return {
            "symbols": [item.get("symbol") for item in snapshots if isinstance(item, dict)],
            "trade_dates": [item.get("trade_date") for item in snapshots if isinstance(item, dict)],
        }
    if tool == "analyze_asset_risk":
        raw_assets = data.get("assets")
        assets: list[Any] = raw_assets if isinstance(raw_assets, list) else []
        return {
            "symbols": [item.get("symbol") for item in assets if isinstance(item, dict)],
            "available": [bool(item.get("metrics")) for item in assets if isinstance(item, dict)],
        }
    if tool == "build_allocation":
        return {
            "risk_level": data.get("effective_risk_level"),
            "allocation_pct": data.get("allocation_pct"),
        }
    return {}


def record_tool_result(
    tool: str,
    result: dict[str, Any],
    *,
    audit_id: str | None = None,
) -> None:
    audit_id = str(audit_id or os.getenv("FINANCE_AUDIT_ID") or "").strip()
    if not audit_id:
        return
    raw_meta = result.get("meta")
    raw_error = result.get("error")
    meta: dict[str, Any] = raw_meta if isinstance(raw_meta, dict) else {}
    error: dict[str, Any] = raw_error if isinstance(raw_error, dict) else {}
    event = ToolAuditEvent(
        audit_id=audit_id,
        tool=tool,
        called_at=now_iso(),
        ok=bool(result.get("ok")),
        source=str(meta.get("source") or "system"),
        as_of=str(meta.get("as_of")) if meta.get("as_of") else None,
        is_fallback=bool(meta.get("is_fallback")),
        error_code=str(error.get("code")) if error.get("code") else None,
        summary=_summary(tool, result),
    )
    path = audit_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(event.model_dump_json() + "\n")


def audit_tool(tool: str) -> Callable[[Callable[P, R]], Callable[P, R]]:
    def decorate(function: Callable[P, R]) -> Callable[P, R]:
        @wraps(function)
        def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
            result = function(*args, **kwargs)
            raw_audit_id = kwargs.get("audit_id")
            record_tool_result(
                tool,
                cast(dict[str, Any], result),
                audit_id=str(raw_audit_id) if raw_audit_id else None,
            )
            return result

        return wrapped

    return decorate


def read_tool_audit(audit_id: str) -> list[ToolAuditEvent]:
    path = audit_path()
    if not path.is_file():
        return []
    events: list[ToolAuditEvent] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if audit_id not in line:
                continue
            event = ToolAuditEvent.model_validate_json(line)
            if event.audit_id == audit_id:
                events.append(event)
    except (OSError, ValueError):
        return []
    return events


def missing_required_tools(events: list[ToolAuditEvent]) -> list[str]:
    called = {event.tool for event in events}
    return [tool for tool in REQUIRED_REPORT_TOOLS if tool not in called]
