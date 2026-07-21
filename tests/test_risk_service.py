from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import finance_advisor.mcp_server as mcp_server
import finance_advisor.web.common as web_common
from finance_advisor.market.akshare_provider import AkshareProvider
from finance_advisor.market.cache_provider import CacheProvider
from finance_advisor.market.fixture_provider import FixtureProvider
from finance_advisor.market.models import MarketBar, MarketSeries
from finance_advisor.market.service import MarketService
from finance_advisor.market.symbols import SymbolInfo
from finance_advisor.risk.service import (
    InvalidLookbackError,
    RiskDataUnavailableError,
    build_asset_risk_report,
    build_portfolio_risk_report,
)
from finance_advisor.web.app import create_app


def _fixture_service(tmp_path: Path) -> MarketService:
    fixture = Path(__file__).resolve().parents[1] / "data" / "fixtures" / "market_data.json"
    return MarketService(
        AkshareProvider(fetcher=lambda **_kwargs: None),  # type: ignore[arg-type]
        CacheProvider(tmp_path),
        FixtureProvider(fixture),
        force_fixture=True,
    )


def test_asset_report_keeps_order_and_marks_partial_history_failure(tmp_path: Path) -> None:
    delegate = _fixture_service(tmp_path)

    class PartialService(MarketService):
        def __init__(self) -> None:
            pass

        def get_history(self, symbol: SymbolInfo, lookback_days: int) -> MarketSeries:
            if symbol.symbol == "511010":
                raise RuntimeError("offline")
            return delegate.get_history(symbol, lookback_days)

    report = build_asset_risk_report(PartialService(), ["510300", "511010"], 80)

    assert [item["symbol"] for item in report.data["assets"]] == ["510300", "511010"]
    assert report.data["assets"][0]["metrics"] is not None
    assert report.data["assets"][1]["error"] == "data_unavailable"
    assert report.source == "fixture"
    assert report.is_fallback is True
    assert any("国债ETF历史数据不可用" in warning for warning in report.warnings)


def test_asset_report_returns_success_when_loaded_history_is_insufficient() -> None:
    start = date(2026, 1, 1)

    class ShortHistoryService(MarketService):
        def __init__(self) -> None:
            pass

        def get_history(self, symbol: SymbolInfo, _lookback_days: int) -> MarketSeries:
            return MarketSeries(
                symbol=symbol.symbol,
                name=symbol.name,
                asset_class=symbol.asset_class,
                bars=[
                    MarketBar(date=start + timedelta(days=index), close=100 + index)
                    for index in range(20)
                ],
                source="fixture",
                fetched_at="2026-07-21T00:00:00+08:00",
                is_fallback=True,
                warning="演示数据/非实时数据",
            )

    report = build_asset_risk_report(ShortHistoryService(), ["510300"], 80)

    assert report.data["assets"][0]["metrics"] is None
    assert report.data["assets"][0]["error"] == "insufficient_data"
    assert any("至少需要60条" in warning for warning in report.warnings)


def test_all_history_failures_are_explicit() -> None:
    class FailingService(MarketService):
        def __init__(self) -> None:
            pass

        def get_history(self, _symbol: SymbolInfo, _lookback_days: int) -> MarketSeries:
            raise RuntimeError("offline")

    with pytest.raises(RiskDataUnavailableError, match="所有标的"):
        build_asset_risk_report(FailingService(), ["510300"], 80)

    with pytest.raises(RiskDataUnavailableError, match="组合历史数据不可用"):
        build_portfolio_risk_report(FailingService(), {"510300": 100.0}, 80)


def test_invalid_lookback_is_shared_by_asset_and_portfolio(tmp_path: Path) -> None:
    service = _fixture_service(tmp_path)

    with pytest.raises(InvalidLookbackError, match="60到1260"):
        build_asset_risk_report(service, ["510300"], 10)
    with pytest.raises(InvalidLookbackError, match="60到1260"):
        build_portfolio_risk_report(service, {"510300": 100.0}, 1261)


def test_mcp_and_http_portfolio_contracts_match(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    service = _fixture_service(tmp_path)
    monkeypatch.setattr(mcp_server, "_market_service", service)
    monkeypatch.setattr(web_common, "_market_service", service)
    weights = {"510300": 60.0, "511010": 40.0}

    mcp_payload = mcp_server.analyze_portfolio_risk(weights, 80)
    with TestClient(create_app(static_dir=tmp_path / "frontend-dist")) as client:
        http_response = client.post(
            "/api/risk/portfolio",
            json={"weights_pct": weights, "lookback_days": 80},
        )

    assert http_response.status_code == 200
    http_payload = http_response.json()
    assert mcp_payload["data"] == http_payload["data"]
    assert mcp_payload["warnings"] == http_payload["warnings"]
    assert mcp_payload["meta"]["source"] == http_payload["meta"]["source"]
    assert mcp_payload["meta"]["as_of"] == http_payload["meta"]["as_of"]
    assert mcp_payload["meta"]["is_fallback"] == http_payload["meta"]["is_fallback"]
