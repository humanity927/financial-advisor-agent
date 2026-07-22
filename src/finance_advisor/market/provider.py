from __future__ import annotations

from enum import StrEnum
from typing import Protocol

from finance_advisor.market.models import MarketProviderName, MarketSeries
from finance_advisor.market.symbols import SymbolInfo


class ProviderErrorCode(StrEnum):
    CONFIGURATION_MISSING = "configuration_missing"
    AUTHENTICATION_FAILED = "authentication_failed"
    PERMISSION_DENIED = "permission_denied"
    RATE_LIMITED = "rate_limited"
    TIMEOUT = "timeout"
    NETWORK_ERROR = "network_error"
    SERVICE_UNAVAILABLE = "service_unavailable"
    INVALID_RESPONSE = "invalid_response"
    EMPTY_DATA = "empty_data"


class MarketProviderError(RuntimeError):
    """Sanitized provider failure safe for classification and logs."""

    def __init__(
        self,
        provider: MarketProviderName,
        code: ProviderErrorCode,
        message: str,
        *,
        retryable: bool,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.code = code
        self.message = message
        self.retryable = retryable


def classify_provider_exception(exc: Exception) -> ProviderErrorCode:
    name = type(exc).__name__.lower()
    message = str(exc).lower()
    if "timeout" in name or "timed out" in message or "超时" in message:
        return ProviderErrorCode.TIMEOUT
    if any(term in name for term in ("proxy", "connection", "connect")):
        return ProviderErrorCode.NETWORK_ERROR
    if any(term in message for term in ("401", "unauthorized", "invalid token", "token无效")):
        return ProviderErrorCode.AUTHENTICATION_FAILED
    if any(
        term in message
        for term in (
            "permission",
            "没有权限",
            "无权限",
            "访问权限",
            "权限不足",
            "积分不足",
        )
    ):
        return ProviderErrorCode.PERMISSION_DENIED
    if any(
        term in message for term in ("429", "rate limit", "too many requests", "频率", "每分钟最多")
    ):
        return ProviderErrorCode.RATE_LIMITED
    if any(term in message for term in ("502", "503", "504", "service unavailable")):
        return ProviderErrorCode.SERVICE_UNAVAILABLE
    return ProviderErrorCode.INVALID_RESPONSE


def retryable_error(code: ProviderErrorCode) -> bool:
    return code in {
        ProviderErrorCode.RATE_LIMITED,
        ProviderErrorCode.TIMEOUT,
        ProviderErrorCode.NETWORK_ERROR,
        ProviderErrorCode.SERVICE_UNAVAILABLE,
    }


class MarketDataProvider(Protocol):
    name: MarketProviderName

    def available(self) -> bool: ...

    def fetch_history(self, symbol: SymbolInfo, lookback_days: int) -> MarketSeries: ...


class MarketCatalogProvider(MarketDataProvider, Protocol):
    def search_etfs(self, query: str, *, limit: int = 50) -> list[SymbolInfo]: ...
