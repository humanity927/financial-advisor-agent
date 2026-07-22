from __future__ import annotations

import os
import re
import threading
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from finance_advisor.agent.actions import ProfilePatch, UiAction
from finance_advisor.schemas import now_iso

SENSITIVE_NUMBER = re.compile(r"(?<!\d)(?:\d[ -]?){15,18}[\dXx](?!\d)")


def sanitize_message(content: str) -> str:
    return SENSITIVE_NUMBER.sub("[敏感信息已移除]", content.strip())


class StoredToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool: str
    called_at: str
    ok: bool
    source: str
    as_of: str | None = None
    is_fallback: bool = False
    error_code: str | None = None
    summary: dict[str, object] = Field(default_factory=dict)


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: str(uuid4()))
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=50_000)
    created_at: str = Field(default_factory=now_iso)
    status: Literal["complete", "error", "cancelled"] = "complete"
    context_status: Literal["current", "historical"] = "current"
    source: str = "system"
    as_of: str | None = None
    is_fallback: bool = False
    tool_calls: list[StoredToolCall] = Field(default_factory=list)
    actions: list[UiAction] = Field(default_factory=list)


class ChatSession(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: str(uuid4()))
    title: str = "新咨询"
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)
    profile: ProfilePatch = Field(default_factory=ProfilePatch)
    symbols: list[str] = Field(default_factory=list, max_length=8)
    risk_symbol: str | None = None
    current_allocation_pct: dict[str, float] | None = None
    personalization_active: bool = False
    messages: list[ChatMessage] = Field(default_factory=list)

    @field_serializer("profile")
    def serialize_profile(self, profile: ProfilePatch) -> dict[str, object]:
        return profile.present()


class SessionSummary(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str
    message_count: int
    symbols: list[str]
    profile_fields: int


def session_directory() -> Path:
    project_root = Path(__file__).resolve().parents[3]
    return Path(os.getenv("FINANCE_SESSION_DIR", project_root / ".runtime" / "sessions")).resolve()


class SessionStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = (root or session_directory()).resolve()
        self._lock = threading.RLock()

    def _path(self, session_id: str) -> Path:
        normalized = str(UUID(session_id))
        return self.root / f"{normalized}.json"

    def create(self, *, title: str = "新咨询") -> ChatSession:
        session = ChatSession(title=title.strip()[:40] or "新咨询")
        self.save(session)
        return session

    def save(self, session: ChatSession) -> None:
        with self._lock:
            self.root.mkdir(parents=True, exist_ok=True)
            session.updated_at = now_iso()
            path = self._path(session.id)
            temporary = path.with_suffix(".tmp")
            temporary.write_text(
                session.model_dump_json(indent=2),
                encoding="utf-8",
            )
            temporary.replace(path)

    def get(self, session_id: str) -> ChatSession | None:
        try:
            path = self._path(session_id)
        except ValueError:
            return None
        with self._lock:
            if not path.is_file():
                return None
            try:
                session = ChatSession.model_validate_json(path.read_text(encoding="utf-8"))
                for message in session.messages:
                    if message.role == "assistant" and any(
                        call.tool in {"get_market_snapshot", "analyze_asset_risk"}
                        for call in message.tool_calls
                    ):
                        message.context_status = "historical"
                return session
            except (OSError, ValueError):
                return None

    def list(self) -> list[SessionSummary]:
        with self._lock:
            if not self.root.is_dir():
                return []
            sessions: list[ChatSession] = []
            for path in self.root.glob("*.json"):
                try:
                    sessions.append(
                        ChatSession.model_validate_json(path.read_text(encoding="utf-8"))
                    )
                except (OSError, ValueError):
                    continue
        sessions.sort(key=lambda item: item.updated_at, reverse=True)
        return [
            SessionSummary(
                id=item.id,
                title=item.title,
                created_at=item.created_at,
                updated_at=item.updated_at,
                message_count=len(item.messages),
                symbols=item.symbols,
                profile_fields=len(item.profile.present()),
            )
            for item in sessions
        ]

    def delete(self, session_id: str) -> bool:
        try:
            path = self._path(session_id)
        except ValueError:
            return False
        with self._lock:
            if not path.is_file():
                return False
            path.unlink()
            return True

    def clear(self) -> int:
        with self._lock:
            if not self.root.is_dir():
                return 0
            paths = list(self.root.glob("*.json"))
            for path in paths:
                path.unlink()
            return len(paths)


_store: SessionStore | None = None


def get_session_store() -> SessionStore:
    global _store
    expected = session_directory()
    if _store is None or _store.root != expected:
        _store = SessionStore(expected)
    return _store


def reset_session_store_for_tests() -> None:
    global _store
    _store = None
