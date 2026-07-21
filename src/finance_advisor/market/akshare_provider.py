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
    """A sanitized error raised when AKShare cannot return usable data."""


class AkshareProvider:
    def __init__(
        self,
        *,
        timeout_seconds: float = 8.0,
        max_retries: int = 2,
        fetcher: Callable[..., pd.DataFrame] | None = None,
        index_fetcher: Callable[..., pd.DataFrame] | None = None,
        catalog_fetcher: Callable[..., pd.DataFrame] | None = None,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self._fetcher = fetcher
        self._index_fetcher = index_fetcher
        self._catalog_fetcher = catalog_fetcher

    def available(self) -> bool:
        if self._fetcher is not None:
            return True
        try:
            import akshare  # noqa: F401
        except ImportError:
            return False
        return True

    def _resolve_history_fetcher(self, asset_type: str) -> Callable[..., pd.DataFrame]:
        if asset_type == "index" and self._index_fetcher is not None:
            return self._index_fetcher
        if asset_type == "etf" and self._fetcher is not None:
            return self._fetcher
        try:
            import akshare as ak
        except ImportError as exc:
            raise MarketProviderError("AKShare未安装") from exc
        if asset_type == "index":
            return cast(Callable[..., pd.DataFrame], ak.stock_zh_index_daily_em)
        return cast(Callable[..., pd.DataFrame], ak.fund_etf_hist_em)

    def _resolve_catalog_fetcher(self) -> Callable[..., pd.DataFrame]:
        if self._catalog_fetcher is not None:
            return self._catalog_fetcher
        try:
            import akshare as ak
        except ImportError as exc:
            raise MarketProviderError("AKShare未安装") from exc
        return cast(Callable[..., pd.DataFrame], ak.fund_etf_spot_em)

    def _fetch_once(
        self,
        fetcher: Callable[..., pd.DataFrame],
        **kwargs: Any,
    ) -> pd.DataFrame:
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="akshare")
        future = executor.submit(fetcher, **kwargs)
        try:
            return future.result(timeout=self.timeout_seconds)
        except FutureTimeoutError as exc:
            future.cancel()
            raise MarketProviderError(f"AKShare请求超过{self.timeout_seconds:g}秒") from exc
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    def _fetch_with_retries(
        self,
        label: str,
        fetcher: Callable[..., pd.DataFrame],
        **kwargs: Any,
    ) -> pd.DataFrame:
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                return self._fetch_once(fetcher, **kwargs)
            except Exception as exc:
                last_error = exc
                LOGGER.warning(
                    "AKShare attempt %s failed for %s error_type=%s",
                    attempt + 1,
                    label,
                    type(exc).__name__,
                )
                if attempt < self.max_retries:
                    time.sleep(0.5 * (attempt + 1))
        raise MarketProviderError("AKShare行情请求失败") from last_error

    @staticmethod
    def _history_columns(frame: pd.DataFrame) -> tuple[str, str]:
        date_column = next(
            (name for name in ("日期", "date") if name in frame.columns),
            "",
        )
        close_column = next(
            (name for name in ("收盘", "close") if name in frame.columns),
            "",
        )
        if not date_column or not close_column:
            raise MarketProviderError("AKShare返回字段不完整")
        return date_column, close_column

    def fetch_history(self, symbol: SymbolInfo, lookback_days: int) -> MarketSeries:
        calendar_days = max(365, lookback_days * 2)
        end = date.today()
        start = end - timedelta(days=calendar_days)
        if symbol.asset_type == "index":
            provider_symbol = symbol.provider_symbol or (
                f"sz{symbol.symbol}" if symbol.market == "SZ" else f"sh{symbol.symbol}"
            )
            kwargs = {
                "symbol": provider_symbol,
                "start_date": start.strftime("%Y%m%d"),
                "end_date": end.strftime("%Y%m%d"),
            }
        else:
            kwargs = {
                "symbol": symbol.symbol,
                "period": "daily",
                "start_date": start.strftime("%Y%m%d"),
                "end_date": end.strftime("%Y%m%d"),
                "adjust": "qfq",
            }

        frame = self._fetch_with_retries(
            symbol.symbol,
            self._resolve_history_fetcher(symbol.asset_type),
            **kwargs,
        )
        if frame.empty:
            raise MarketProviderError("AKShare返回空数据")
        date_column, close_column = self._history_columns(frame)

        normalized = frame.loc[:, [date_column, close_column]].copy()
        normalized.columns = ["date", "close"]
        normalized["date"] = pd.to_datetime(normalized["date"], errors="coerce")
        normalized["close"] = pd.to_numeric(normalized["close"], errors="coerce")
        normalized = normalized.dropna().drop_duplicates(subset=["date"], keep="last")
        normalized = normalized.loc[normalized["close"] > 0].sort_values("date")
        normalized = normalized.tail(lookback_days + 1)
        if normalized.empty:
            raise MarketProviderError("AKShare没有返回有效收盘价")

        bars = [
            MarketBar(date=row["date"].date(), close=float(row["close"]))
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
        frame = self._fetch_with_retries("ETF目录", self._resolve_catalog_fetcher())
        if frame.empty or "代码" not in frame.columns or "名称" not in frame.columns:
            raise MarketProviderError("AKShare ETF目录为空或字段不完整")
        needle = query.strip().lower()
        results: list[SymbolInfo] = []
        for _, row in frame.loc[:, ["代码", "名称"]].iterrows():
            symbol = str(row["代码"]).strip().zfill(6)
            name = str(row["名称"]).strip()
            if needle and needle not in symbol.lower() and needle not in name.lower():
                continue
            market = "SZ" if symbol.startswith(("15", "16")) else "SH"
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
