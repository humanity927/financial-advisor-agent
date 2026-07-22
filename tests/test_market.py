from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from finance_advisor.market.akshare_provider import AkshareProvider
from finance_advisor.market.cache_provider import CacheProvider
from finance_advisor.market.fixture_provider import FixtureProvider
from finance_advisor.market.models import MarketBar, MarketSeries
from finance_advisor.market.provider import ProviderErrorCode, classify_provider_exception
from finance_advisor.market.service import MarketPolicy, MarketService
from finance_advisor.market.symbols import (
    SymbolCatalog,
    SymbolInfo,
    SymbolValidationError,
    normalize_symbol,
    normalize_symbols,
)
from finance_advisor.market.tushare_provider import TushareProvider


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
    def __init__(
        self,
        result: MarketSeries | Exception,
        *,
        name: str = "akshare",
        available: bool = True,
    ) -> None:
        self.result = result
        self.name = name
        self.is_available = available
        self.calls = 0

    def available(self) -> bool:
        return self.is_available

    def fetch_history(self, _symbol: object, _lookback_days: int) -> MarketSeries:
        self.calls += 1
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def test_symbol_aliases_and_limits() -> None:
    assert normalize_symbol("沪深300").symbol == "510300"
    assert len(normalize_symbols(["510300", "沪深300"])) == 1
    try:
        normalize_symbols(["510300"] * 9)
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


def test_service_prefers_primary_even_when_cache_is_fresh(tmp_path: Path) -> None:
    live = FakeLive(_live_series())
    service = MarketService(
        live,  # type: ignore[arg-type]
        CacheProvider(tmp_path),
        FixtureProvider(_fixture_path()),
        policy=MarketPolicy(snapshot_ttl_seconds=60),
    )
    symbol = normalize_symbol("510300")

    assert service.get_snapshot(symbol).source == "akshare"
    second = service.get_snapshot(symbol)

    assert live.calls == 2
    assert second.source == "akshare"


def test_service_uses_tushare_after_primary_failure(tmp_path: Path) -> None:
    primary = FakeLive(RuntimeError("proxy"), name="akshare")
    tushare_series = _live_series().model_copy(update={"source": "tushare", "provider": "tushare"})
    supplemental = FakeLive(tushare_series, name="tushare")
    service = MarketService(
        primary,  # type: ignore[arg-type]
        CacheProvider(tmp_path),
        FixtureProvider(_fixture_path()),
        supplemental=supplemental,  # type: ignore[arg-type]
    )

    result = service.get_snapshot(normalize_symbol("510300"))

    assert primary.calls == supplemental.calls == 1
    assert result.source == "tushare"
    assert result.provider == "tushare"
    assert result.is_fallback is True
    assert "切换" in (result.warning or "")


def test_service_does_not_use_fixture_when_live_and_cache_fail(tmp_path: Path) -> None:
    service = MarketService(
        FakeLive(RuntimeError("network")),  # type: ignore[arg-type]
        CacheProvider(tmp_path),
        FixtureProvider(_fixture_path()),
    )

    with pytest.raises(RuntimeError, match="Tushare.*真实行情缓存"):
        service.get_history(normalize_symbol("518880"), 60)


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
    assert "已过期" in (result.warning or "")
    assert result.origin_source == "akshare"
    assert result.is_stale is True
    assert result.stale is True
    assert result.cache_status == "stale"


def test_service_uses_fresh_real_cache_after_both_sources_fail(tmp_path: Path) -> None:
    cache = CacheProvider(tmp_path)
    cache.save("snapshot_510300", _live_series())
    service = MarketService(
        FakeLive(RuntimeError("primary"), name="akshare"),  # type: ignore[arg-type]
        cache,
        FixtureProvider(_fixture_path()),
        supplemental=FakeLive(RuntimeError("secondary"), name="tushare"),  # type: ignore[arg-type]
    )

    result = service.get_snapshot(normalize_symbol("510300"))

    assert result.source == "cache"
    assert result.origin_source == "akshare"
    assert result.cache_status == "fresh"
    assert result.stale is False


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
    assert result.provider == "akshare"
    assert result.latest_trade_date == date(2026, 7, 18)


def test_akshare_index_uses_verified_index_interface() -> None:
    captured: dict[str, object] = {}

    def index_fetcher(**kwargs: object) -> pd.DataFrame:
        captured.update(kwargs)
        return pd.DataFrame({"date": ["2026-07-18", "2026-07-21"], "close": [3500, 3520]})

    provider = AkshareProvider(index_fetcher=index_fetcher, max_retries=0)
    result = provider.fetch_history(normalize_symbol("000001"), 60)

    assert captured["symbol"] == "sh000001"
    assert "period" not in captured
    assert result.symbol == "000001"
    assert result.source == "akshare"


def test_akshare_catalog_search_and_persistence(tmp_path: Path) -> None:
    provider = AkshareProvider(
        catalog_fetcher=lambda: pd.DataFrame(
            {"代码": ["159915", "511010"], "名称": ["创业板ETF", "国债ETF"]}
        ),
        max_retries=0,
    )
    found = provider.search_etfs("创业板")
    catalog = SymbolCatalog(tmp_path / "catalog.json")
    catalog.register_akshare(found)
    restored = SymbolCatalog(tmp_path / "catalog.json")

    assert found == [SymbolInfo("159915", "创业板ETF", "股票", "SZ", "etf")]
    assert restored.get("159915") == found[0]
    assert restored.fetched_at is not None


class FakeTushareClient:
    def __init__(self, history: pd.DataFrame, catalog: pd.DataFrame | None = None) -> None:
        self.history = history
        self.catalog = catalog if catalog is not None else pd.DataFrame()
        self.calls: list[tuple[str, dict[str, object]]] = []

    def fund_daily(self, **kwargs: object) -> pd.DataFrame:
        self.calls.append(("fund_daily", kwargs))
        return self.history

    def index_daily(self, **kwargs: object) -> pd.DataFrame:
        self.calls.append(("index_daily", kwargs))
        return self.history

    def fund_basic(self, **kwargs: object) -> pd.DataFrame:
        self.calls.append(("fund_basic", kwargs))
        return self.catalog


def test_tushare_verified_interfaces_and_normalization() -> None:
    frame = pd.DataFrame(
        {
            "trade_date": ["20260721", "20260718", "bad"],
            "close": [3520.0, 3500.0, "bad"],
        }
    )
    client = FakeTushareClient(frame)
    provider = TushareProvider(client=client, max_retries=0)

    result = provider.fetch_history(normalize_symbol("000300"), 60)

    assert client.calls[0][0] == "index_daily"
    assert client.calls[0][1]["ts_code"] == "000300.SH"
    assert [bar.close for bar in result.bars] == [3500.0, 3520.0]
    assert result.source == "tushare"
    assert result.latest_trade_date == date(2026, 7, 21)


def test_tushare_short_history_is_not_fabricated() -> None:
    client = FakeTushareClient(pd.DataFrame({"trade_date": ["20260721"], "close": [4.2]}))
    result = TushareProvider(client=client).fetch_history(normalize_symbol("510300"), 252)

    assert len(result.bars) == 1


def test_tushare_catalog_normalizes_market_suffix() -> None:
    client = FakeTushareClient(
        pd.DataFrame(),
        pd.DataFrame(
            {
                "ts_code": ["159915.SZ", "510300.SH"],
                "name": ["创业板ETF", "沪深300ETF"],
            }
        ),
    )
    found = TushareProvider(client=client).search_etfs("创业板")

    assert found == [SymbolInfo("159915", "创业板ETF", "股票", "SZ", "etf")]


def test_tushare_access_permission_message_is_classified() -> None:
    error = Exception("抱歉，您没有接口(fund_daily)访问权限")

    assert classify_provider_exception(error) is ProviderErrorCode.PERMISSION_DENIED


def test_normal_cache_rejects_fixture_origin(tmp_path: Path) -> None:
    cache = CacheProvider(tmp_path)
    fixture = FixtureProvider(_fixture_path()).fetch_history(normalize_symbol("510300"), 60)
    cache.save("fixture", fixture)

    assert cache.load("fixture", max_age_seconds=60, allow_stale=True) is None
