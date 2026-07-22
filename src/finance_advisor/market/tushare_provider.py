from __future__ import annotations

import logging
import os
import time
from datetime import date, timedelta
from typing import Any, Protocol, cast

import pandas as pd

from finance_advisor.market.models import MarketBar, MarketProviderName, MarketSeries
from finance_advisor.market.provider import (
    MarketProviderError,
    ProviderErrorCode,
    classify_provider_exception,
    retryable_error,
)
from finance_advisor.market.symbols import SymbolInfo
from finance_advisor.schemas import now_iso

LOGGER = logging.getLogger(__name__)


class TushareClient(Protocol):
    def fund_daily(self, **kwargs: Any) -> pd.DataFrame: ...

    def index_daily(self, **kwargs: Any) -> pd.DataFrame: ...

    def fund_basic(self, **kwargs: Any) -> pd.DataFrame: ...


class TushareProvider:
    """Tushare Pro fallback for A-share ETF and index histories."""

    name: MarketProviderName = "tushare"

    def __init__(
        self,
        *,
        timeout_seconds: float = 8.0,
        max_retries: int = 1,
        client: TushareClient | None = None,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("Tushare超时必须大于0")
        if max_retries < 0 or max_retries > 5:
            raise ValueError("Tushare重试次数必须在0到5之间")
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self._client = client

    def available(self) -> bool:
        if self._client is not None:
            return True
        if not os.getenv("TUSHARE_TOKEN", "").strip():
            return False
        try:
            import tushare  # noqa: F401
        except ImportError:
            return False
        return True

    def _resolve_client(self) -> TushareClient:
        if self._client is not None:
            return self._client
        token = os.getenv("TUSHARE_TOKEN", "").strip()
        if not token:
            raise MarketProviderError(
                "tushare",
                ProviderErrorCode.CONFIGURATION_MISSING,
                "Tushare凭据未配置",
                retryable=False,
            )
        try:
            import tushare as ts
        except ImportError as exc:
            raise MarketProviderError(
                "tushare",
                ProviderErrorCode.CONFIGURATION_MISSING,
                "Tushare未安装",
                retryable=False,
            ) from exc
        return cast(TushareClient, ts.pro_api(token, timeout=self.timeout_seconds))

    def _call(self, label: str, method_name: str, **kwargs: Any) -> pd.DataFrame:
        last_error: Exception | None = None
        last_code = ProviderErrorCode.INVALID_RESPONSE
        for attempt in range(self.max_retries + 1):
            try:
                method = getattr(self._resolve_client(), method_name)
                frame = method(**kwargs)
                if not isinstance(frame, pd.DataFrame):
                    raise TypeError("Tushare response is not a DataFrame")
                return frame
            except Exception as exc:
                last_error = exc
                last_code = (
                    exc.code
                    if isinstance(exc, MarketProviderError)
                    else classify_provider_exception(exc)
                )
                LOGGER.warning(
                    "Tushare attempt %s failed for %s error_code=%s error_type=%s",
                    attempt + 1,
                    label,
                    last_code,
                    type(exc).__name__,
                )
                if attempt < self.max_retries and retryable_error(last_code):
                    time.sleep(0.5 * (attempt + 1))
                else:
                    break
        raise MarketProviderError(
            "tushare",
            last_code,
            "Tushare行情请求失败",
            retryable=retryable_error(last_code),
        ) from last_error

    @staticmethod
    def _ts_code(symbol: SymbolInfo) -> str:
        return f"{symbol.symbol}.{symbol.market}"

    def fetch_history(self, symbol: SymbolInfo, lookback_days: int) -> MarketSeries:
        calendar_days = max(365, lookback_days * 2)
        end = date.today()
        start = end - timedelta(days=calendar_days)
        method_name = "index_daily" if symbol.asset_type == "index" else "fund_daily"
        frame = self._call(
            symbol.symbol,
            method_name,
            ts_code=self._ts_code(symbol),
            start_date=start.strftime("%Y%m%d"),
            end_date=end.strftime("%Y%m%d"),
            fields="ts_code,trade_date,close",
        )
        if frame.empty:
            raise MarketProviderError(
                "tushare",
                ProviderErrorCode.EMPTY_DATA,
                "Tushare返回空数据",
                retryable=True,
            )
        if "trade_date" not in frame.columns or "close" not in frame.columns:
            raise MarketProviderError(
                "tushare",
                ProviderErrorCode.INVALID_RESPONSE,
                "Tushare返回字段不完整",
                retryable=True,
            )

        normalized = frame.loc[:, ["trade_date", "close"]].copy()
        normalized.columns = ["date", "close"]
        normalized["date"] = pd.to_datetime(normalized["date"], errors="coerce")
        normalized["close"] = pd.to_numeric(normalized["close"], errors="coerce")
        normalized = normalized.dropna().drop_duplicates(subset=["date"], keep="last")
        normalized = normalized.loc[normalized["close"] > 0].sort_values("date")
        normalized = normalized.tail(lookback_days + 1)
        if normalized.empty:
            raise MarketProviderError(
                "tushare",
                ProviderErrorCode.INVALID_RESPONSE,
                "Tushare没有返回有效收盘价",
                retryable=True,
            )
        bars = [
            MarketBar(date=row["date"].date(), close=float(row["close"]))
            for _, row in normalized.iterrows()
        ]
        return MarketSeries(
            symbol=symbol.symbol,
            name=symbol.name,
            asset_class=symbol.asset_class,
            bars=bars,
            source="tushare",
            provider="tushare",
            fetched_at=now_iso(),
        )

    @staticmethod
    def _asset_class_for_etf(name: str) -> str:
        if any(term in name for term in ("货币", "现金", "银华日利", "华宝添益")):
            return "现金"
        if any(term in name for term in ("债", "国开", "政金")):
            return "债券"
        if any(term in name for term in ("黄金", "金ETF")):
            return "黄金"
        return "股票"

    def search_etfs(self, query: str, *, limit: int = 50) -> list[SymbolInfo]:
        frame = self._call(
            "ETF目录",
            "fund_basic",
            market="E",
            status="L",
            fields="ts_code,name,status",
        )
        if frame.empty or "ts_code" not in frame.columns or "name" not in frame.columns:
            raise MarketProviderError(
                "tushare",
                ProviderErrorCode.INVALID_RESPONSE,
                "Tushare ETF目录为空或字段不完整",
                retryable=True,
            )
        needle = query.strip().lower()
        results: list[SymbolInfo] = []
        for _, row in frame.loc[:, ["ts_code", "name"]].iterrows():
            ts_code = str(row["ts_code"]).strip().upper()
            parts = ts_code.split(".", maxsplit=1)
            if len(parts) != 2 or parts[1] not in {"SH", "SZ"}:
                continue
            symbol, market = parts
            name = str(row["name"]).strip()
            if needle and needle not in symbol.lower() and needle not in name.lower():
                continue
            results.append(
                SymbolInfo(
                    symbol=symbol,
                    name=name,
                    asset_class=self._asset_class_for_etf(name),
                    market=market,
                    asset_type="etf",
                )
            )
            if len(results) >= limit:
                break
        return results
