from __future__ import annotations

import os
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from finance_advisor.market.akshare_provider import AkshareProvider
from finance_advisor.market.cache_provider import CacheProvider
from finance_advisor.market.fixture_provider import FixtureProvider
from finance_advisor.market.models import MarketSeries
from finance_advisor.market.service import MarketService
from finance_advisor.market.symbols import SymbolInfo
from finance_advisor.market.tushare_provider import TushareProvider

PROJECT_ROOT = Path(
    os.getenv("FINANCE_PROJECT_ROOT", Path(__file__).resolve().parents[3])
).resolve()
CACHE_DIR = Path(os.getenv("FINANCE_CACHE_DIR", PROJECT_ROOT / ".runtime" / "cache"))
FIXTURE_PATH = Path(
    os.getenv(
        "FINANCE_FIXTURE_PATH",
        PROJECT_ROOT / "data" / "fixtures" / "market_data.json",
    )
)

_market_service: MarketService | None = None


def get_cache_dir() -> Path:
    return Path(os.getenv("FINANCE_CACHE_DIR", CACHE_DIR)).resolve()


def get_fixture_path() -> Path:
    return Path(os.getenv("FINANCE_FIXTURE_PATH", FIXTURE_PATH)).resolve()


def get_market_service() -> MarketService:
    global _market_service
    if _market_service is None:
        _market_service = MarketService(
            AkshareProvider(timeout_seconds=30.0, max_retries=1),
            CacheProvider(get_cache_dir()),
            FixtureProvider(get_fixture_path()),
            supplemental=TushareProvider(timeout_seconds=8.0, max_retries=1),
        )
    return _market_service


def reset_market_service_for_tests() -> None:
    global _market_service
    _market_service = None


def load_market_series(
    symbols: Sequence[SymbolInfo],
    loader: Callable[[SymbolInfo], MarketSeries],
) -> list[MarketSeries]:
    """Load independent read-only symbols concurrently while preserving input order."""
    if not symbols:
        return []
    with ThreadPoolExecutor(
        max_workers=min(4, len(symbols)),
        thread_name_prefix="market-data",
    ) as executor:
        return list(executor.map(loader, symbols))


def source_for(series: list[MarketSeries]) -> str:
    sources = {item.source for item in series}
    return next(iter(sources)) if len(sources) == 1 else "mixed"


def warnings_for(series: list[MarketSeries]) -> list[str]:
    return list(dict.fromkeys(item.warning for item in series if item.warning))
