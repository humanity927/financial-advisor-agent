from __future__ import annotations

from pathlib import Path

import finance_advisor.mcp_server as server
from finance_advisor.market.akshare_provider import AkshareProvider
from finance_advisor.market.cache_provider import CacheProvider
from finance_advisor.market.fixture_provider import FixtureProvider
from finance_advisor.market.service import MarketService


def _fixture_service(tmp_path: Path) -> MarketService:
    fixture = Path(__file__).resolve().parents[1] / "data" / "fixtures" / "market_data.json"
    return MarketService(
        AkshareProvider(fetcher=lambda **_kwargs: None),  # type: ignore[arg-type]
        CacheProvider(tmp_path),
        FixtureProvider(fixture),
        force_fixture=True,
    )


def test_missing_profile_fields_are_returned_for_followup() -> None:
    result = server.assess_investor_profile(amount_cny=50_000)

    assert result["ok"] is False
    assert result["error"]["code"] == "missing_fields"
    assert len(result["data"]["missing_fields"]) == 6


def test_profile_and_allocation_tools() -> None:
    values = {
        "amount_cny": 50_000,
        "horizon_months": 12,
        "max_loss_pct": 10,
        "income_stability": "stable",
        "experience": "basic",
        "liquidity_need": "medium",
        "emergency_fund_months": 6,
    }

    profile = server.assess_investor_profile(**values)
    allocation = server.build_allocation(**values)

    assert profile["data"]["risk_level"] == "稳健型"
    assert allocation["data"]["effective_risk_level"] == "稳健型"
    assert sum(allocation["data"]["allocation_pct"].values()) == 100.0


def test_market_and_risk_tools_use_explicit_fixture(monkeypatch: object, tmp_path: Path) -> None:
    service = _fixture_service(tmp_path)
    monkeypatch.setattr(server, "_market_service", service)  # type: ignore[attr-defined]

    snapshot = server.get_market_snapshot(["510300", "黄金ETF"])
    risk = server.analyze_asset_risk(["510300"], 80)

    assert snapshot["ok"] is True
    assert snapshot["meta"]["source"] == "fixture"
    assert "非实时" in snapshot["warnings"][0]
    assert risk["ok"] is True
    assert risk["data"]["assets"][0]["metrics"]["observation_count"] == 81

    portfolio = server.analyze_portfolio_risk({"510300": 60.0, "511010": 40.0}, 80)
    assert portfolio["ok"] is True
    assert portfolio["meta"]["source"] == "fixture"
    assert portfolio["data"]["portfolio"]["portfolio_metrics"]["observation_count"] == 81
    assert portfolio["data"]["portfolio"]["correlation_matrix"]["symbols"] == [
        "510300",
        "511010",
    ]


def test_invalid_symbol_and_lookback_are_structured_errors() -> None:
    invalid_symbol = server.get_market_snapshot(["000001"])
    invalid_lookback = server.analyze_asset_risk(["510300"], 10)

    assert invalid_symbol["error"]["code"] == "invalid_symbol"
    assert invalid_lookback["error"]["code"] == "invalid_lookback"


def test_invalid_portfolio_weights_are_structured_errors() -> None:
    bad_total = server.analyze_portfolio_risk({"510300": 80.0}, 80)
    duplicate_alias = server.analyze_portfolio_risk({"510300": 50.0, "沪深300": 50.0}, 80)

    assert bad_total["error"]["code"] == "invalid_weights"
    assert duplicate_alias["error"]["code"] == "invalid_weights"
