from __future__ import annotations

import os
from pathlib import Path

from finance_advisor.market.akshare_provider import AkshareProvider
from finance_advisor.market.cache_provider import CacheProvider
from finance_advisor.market.fixture_provider import FixtureProvider
from finance_advisor.market.models import MarketSeries
from finance_advisor.market.service import MarketService

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


def get_market_service() -> MarketService:
    global _market_service
    if _market_service is None:
        cache_dir = Path(os.getenv("FINANCE_CACHE_DIR", CACHE_DIR))
        fixture_path = Path(os.getenv("FINANCE_FIXTURE_PATH", FIXTURE_PATH))
        _market_service = MarketService(
            AkshareProvider(timeout_seconds=8.0, max_retries=2),
            CacheProvider(cache_dir),
            FixtureProvider(fixture_path),
        )
    return _market_service


def reset_market_service_for_tests() -> None:
    global _market_service
    _market_service = None


def source_for(series: list[MarketSeries]) -> str:
    sources = {item.source for item in series}
    return next(iter(sources)) if len(sources) == 1 else "mixed"


def warnings_for(series: list[MarketSeries]) -> list[str]:
    return list(dict.fromkeys(item.warning for item in series if item.warning))
