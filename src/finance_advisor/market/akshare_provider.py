from __future__ import annotations

import logging
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from datetime import date, timedelta
from typing import Any, cast

import pandas as pd

from finance_advisor.market.models import MarketBar, MarketSeries
from finance_advisor.market.symbols import SymbolInfo
from finance_advisor.schemas import now_iso

LOGGER = logging.getLogger(__name__)


class MarketProviderError(RuntimeError):
    """A sanitized error raised when the live provider cannot return data."""


class AkshareProvider:
    def __init__(
        self,
        *,
        timeout_seconds: float = 8.0,
        max_retries: int = 2,
        fetcher: Callable[..., pd.DataFrame] | None = None,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self._fetcher = fetcher

    def available(self) -> bool:
        if self._fetcher is not None:
            return True
        try:
            import akshare  # noqa: F401
        except ImportError:
            return False
        return True

    def _resolve_fetcher(self) -> Callable[..., pd.DataFrame]:
        if self._fetcher is not None:
            return self._fetcher
        try:
            import akshare as ak
        except ImportError as exc:
            raise MarketProviderError("AKShare未安装") from exc
        return cast(Callable[..., pd.DataFrame], ak.fund_etf_hist_em)

    def _fetch_once(self, **kwargs: Any) -> pd.DataFrame:
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="akshare")
        future = executor.submit(self._resolve_fetcher(), **kwargs)
        try:
            return future.result(timeout=self.timeout_seconds)
        except FutureTimeoutError as exc:
            future.cancel()
            raise MarketProviderError(f"AKShare请求超过{self.timeout_seconds:g}秒") from exc
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    def fetch_history(self, symbol: SymbolInfo, lookback_days: int) -> MarketSeries:
        calendar_days = max(365, lookback_days * 2)
        end = date.today()
        start = end - timedelta(days=calendar_days)
        kwargs = {
            "symbol": symbol.symbol,
            "period": "daily",
            "start_date": start.strftime("%Y%m%d"),
            "end_date": end.strftime("%Y%m%d"),
            "adjust": "qfq",
        }

        last_error: Exception | None = None
        frame: pd.DataFrame | None = None
        for attempt in range(self.max_retries + 1):
            try:
                frame = self._fetch_once(**kwargs)
                break
            except Exception as exc:  # provider errors are normalized below
                last_error = exc
                LOGGER.warning(
                    "AKShare attempt %s failed for %s: %s", attempt + 1, symbol.symbol, exc
                )
                if attempt < self.max_retries:
                    time.sleep(0.5 * (attempt + 1))

        if frame is None:
            raise MarketProviderError("AKShare行情请求失败") from last_error
        if frame.empty or "日期" not in frame.columns or "收盘" not in frame.columns:
            raise MarketProviderError("AKShare返回空数据或字段不完整")

        normalized = frame.loc[:, ["日期", "收盘"]].copy()
        normalized["日期"] = pd.to_datetime(normalized["日期"], errors="coerce")
        normalized["收盘"] = pd.to_numeric(normalized["收盘"], errors="coerce")
        normalized = normalized.dropna().drop_duplicates(subset=["日期"], keep="last")
        normalized = normalized.loc[normalized["收盘"] > 0].sort_values("日期")
        normalized = normalized.tail(lookback_days + 1)
        if normalized.empty:
            raise MarketProviderError("AKShare没有返回有效收盘价")

        bars = [
            MarketBar(date=row["日期"].date(), close=float(row["收盘"]))
            for _, row in normalized.iterrows()
        ]
        return MarketSeries(
            symbol=symbol.symbol,
            name=symbol.name,
            asset_class=symbol.asset_class,
            bars=bars,
            source="akshare",
            fetched_at=now_iso(),
        )
