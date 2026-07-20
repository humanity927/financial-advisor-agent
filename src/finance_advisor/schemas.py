from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

CHINA_TIMEZONE = timezone(timedelta(hours=8))


def now_iso() -> str:
    """Return a timezone-aware timestamp suitable for user-facing metadata."""
    return datetime.now(CHINA_TIMEZONE).isoformat(timespec="seconds")


class IncomeStability(StrEnum):
    UNSTABLE = "unstable"
    STABLE = "stable"
    VERY_STABLE = "very_stable"


class InvestmentExperience(StrEnum):
    NONE = "none"
    BASIC = "basic"
    REGULAR = "regular"
    EXPERT = "expert"


class LiquidityNeed(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class InvestorProfileInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount_cny: float = Field(gt=0, le=1_000_000_000)
    horizon_months: int = Field(ge=1, le=600)
    max_loss_pct: float = Field(ge=0, le=100)
    income_stability: IncomeStability
    experience: InvestmentExperience
    liquidity_need: LiquidityNeed
    emergency_fund_months: int = Field(ge=0, le=120)


class RiskAssessment(BaseModel):
    score: int = Field(ge=0, le=100)
    risk_level: str
    score_breakdown: dict[str, int]
    hard_limits: list[str] = Field(default_factory=list)


def success_response(
    data: Any,
    *,
    source: str = "system",
    as_of: str | None = None,
    is_fallback: bool = False,
    warnings: list[str] | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    return {
        "ok": True,
        "data": data,
        "meta": {
            "source": source,
            "as_of": as_of or now_iso(),
            "request_id": request_id or str(uuid4()),
            "is_fallback": is_fallback,
        },
        "warnings": warnings or [],
    }


def error_response(
    code: str,
    message: str,
    *,
    retryable: bool = False,
    data: Any = None,
    source: str = "system",
    request_id: str | None = None,
) -> dict[str, Any]:
    return {
        "ok": False,
        "data": data,
        "meta": {
            "source": source,
            "as_of": now_iso(),
            "request_id": request_id or str(uuid4()),
            "is_fallback": False,
        },
        "warnings": [],
        "error": {
            "code": code,
            "message": message,
            "retryable": retryable,
        },
    }
