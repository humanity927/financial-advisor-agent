from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from finance_advisor.market.akshare_provider import AkshareProvider
from finance_advisor.market.cache_provider import CacheProvider
from finance_advisor.market.fixture_provider import FixtureProvider
from finance_advisor.market.models import MarketBar, MarketSeries
from finance_advisor.market.service import MarketPolicy, MarketService
from finance_advisor.market.symbols import (
    SymbolValidationError,
    normalize_symbol,
    normalize_symbols,
)


def _fixture_path() -> Path:
    return Path(__file__).resolve().parents[1] / "data" / "fixtures" / "market_data.json"


def _live_series() -> MarketSeries:
    start = date(2026, 1, 1)
    return MarketSeries(
        symbol="510300",
        name="沪深300ETF",
        asset_class="股票",
        bars=[
            MarketBar(date=start + timedelta(days=index), close=4 + index / 100)
            for index in range(6)
        ],
        source="akshare",
        fetched_at="2026-07-20T10:00:00+08:00",
    )


class FakeLive:
    def __init__(self, result: MarketSeries | Exception) -> None:
        self.result = result
        self.calls = 0

    def available(self) -> bool:
        return True

    def fetch_history(self, _symbol: object, _lookback_days: int) -> MarketSeries:
        self.calls += 1
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def test_symbol_aliases_and_limits() -> None:
    assert normalize_symbol("沪深300").symbol == "510300"
    assert len(normalize_symbols(["510300", "沪深300"])) == 1
    try:
        normalize_symbols(["1", "2", "3", "4", "5"])
    except SymbolValidationError as exc:
        assert "最多" in str(exc)
    else:
        raise AssertionError("expected SymbolValidationError")


def test_fixture_is_deterministic_and_marked_non_realtime() -> None:
    provider = FixtureProvider(_fixture_path())
    symbol = normalize_symbol("510300")

    first = provider.fetch_history(symbol, 80)
    second = provider.fetch_history(symbol, 80)

    assert first.bars == second.bars
    assert len(first.bars) == 81
    assert first.source == "fixture"
    assert first.is_fallback is True
    assert "非实时" in (first.warning or "")


def test_service_caches_live_result(tmp_path: Path) -> None:
    live = FakeLive(_live_series())
    service = MarketService(
        live,  # type: ignore[arg-type]
        CacheProvider(tmp_path),
        FixtureProvider(_fixture_path()),
        policy=MarketPolicy(snapshot_ttl_seconds=60),
    )
    symbol = normalize_symbol("510300")

    assert service.get_snapshot(symbol).source == "akshare"
    cached = service.get_snapshot(symbol)

    assert live.calls == 1
    assert cached.source == "cache"
    assert cached.origin_source == "akshare"


def test_service_falls_back_to_fixture_when_live_fails(tmp_path: Path) -> None:
    service = MarketService(
        FakeLive(RuntimeError("network")),  # type: ignore[arg-type]
        CacheProvider(tmp_path),
        FixtureProvider(_fixture_path()),
    )

    result = service.get_history(normalize_symbol("518880"), 60)

    assert result.source == "fixture"
    assert result.is_fallback is True
    assert "实时行情不可用" in (result.warning or "")


def test_stale_cache_is_used_before_fixture(tmp_path: Path) -> None:
    cache = CacheProvider(tmp_path)
    cache.save("snapshot_510300", _live_series())
    path = tmp_path / "snapshot_510300.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["cached_at"] = "2020-01-01T00:00:00+08:00"
    path.write_text(json.dumps(payload), encoding="utf-8")
    service = MarketService(
        FakeLive(RuntimeError("network")),  # type: ignore[arg-type]
        cache,
        FixtureProvider(_fixture_path()),
    )

    result = service.get_snapshot(normalize_symbol("510300"))

    assert result.source == "cache"
    assert "过期缓存" in (result.warning or "")


def test_akshare_frame_is_normalized() -> None:
    def fetcher(**_kwargs: object) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "日期": ["2026-07-18", "2026-07-17", "bad"],
                "收盘": [4.2, 4.1, "bad"],
            }
        )

    provider = AkshareProvider(fetcher=fetcher)
    result = provider.fetch_history(normalize_symbol("510300"), 10)

    assert [bar.close for bar in result.bars] == [4.1, 4.2]
    assert result.source == "akshare"
