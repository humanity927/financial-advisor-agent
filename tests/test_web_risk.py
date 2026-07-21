from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from finance_advisor.web.app import create_app
from finance_advisor.web.common import reset_market_service_for_tests


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TestClient:
    monkeypatch.setenv("FINANCE_FORCE_FIXTURE", "1")
    monkeypatch.setenv("FINANCE_CACHE_DIR", str(tmp_path / "cache"))
    reset_market_service_for_tests()
    app = create_app(static_dir=tmp_path / "frontend-dist")
    with TestClient(app) as test_client:
        yield test_client
    reset_market_service_for_tests()


PROFILE = {
    "amount_cny": 50_000,
    "horizon_months": 12,
    "max_loss_pct": 10,
    "income_stability": "stable",
    "experience": "basic",
    "liquidity_need": "medium",
    "emergency_fund_months": 6,
}


def test_profile_returns_six_dimensions(client: TestClient) -> None:
    response = client.post("/api/risk/profile", json=PROFILE)

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["data"]["risk_level"] == "稳健型"
    assert len(payload["data"]["dimensions"]) == 6
    assert sum(item["max_score"] for item in payload["data"]["dimensions"]) == 100


def test_asset_risk_returns_fixture_metrics(client: TestClient) -> None:
    response = client.post(
        "/api/risk/assets",
        json={"symbols": ["510300", "511010"], "lookback_days": 252},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["meta"]["source"] == "fixture"
    assert payload["meta"]["is_fallback"] is True
    assert len(payload["data"]["assets"]) == 2
    assert payload["data"]["assets"][0]["metrics"]["observation_count"] >= 60


def test_portfolio_risk_returns_curves_and_correlation(client: TestClient) -> None:
    response = client.post(
        "/api/risk/portfolio",
        json={
            "weights_pct": {"510300": 40, "511010": 30, "518880": 20, "511880": 10},
            "lookback_days": 252,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    analysis = payload["data"]["portfolio"]
    assert payload["ok"] is True
    assert len(analysis["net_value_curve"]) >= 60
    assert len(analysis["correlation_matrix"]["symbols"]) == 4
    assert analysis["portfolio_metrics"]["observation_count"] >= 60


def test_portfolio_risk_rejects_weights_that_do_not_sum_to_100(client: TestClient) -> None:
    response = client.post(
        "/api/risk/portfolio",
        json={"weights_pct": {"510300": 60, "511010": 30}, "lookback_days": 252},
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["ok"] is False
    assert payload["error"]["code"] == "invalid_weights"


@pytest.mark.parametrize("invalid_weight", [True, "40"])
def test_portfolio_risk_rejects_non_numeric_json_weights(
    client: TestClient,
    invalid_weight: object,
) -> None:
    response = client.post(
        "/api/risk/portfolio",
        json={
            "weights_pct": {"510300": invalid_weight, "511010": 60},
            "lookback_days": 252,
        },
    )

    assert response.status_code == 422
    payload = response.json()
    assert payload["ok"] is False
    assert payload["error"]["code"] == "validation_error"


def test_risk_validation_errors_keep_unified_envelope(client: TestClient) -> None:
    response = client.post("/api/risk/assets", json={"symbols": [], "lookback_days": 20})

    assert response.status_code == 422
    payload = response.json()
    assert payload["ok"] is False
    assert payload["error"]["code"] == "validation_error"
    assert payload["data"]["validation_errors"]


def test_frontend_risk_fixtures_follow_http_contract(client: TestClient) -> None:
    root = Path(__file__).resolve().parents[1]
    mock_dir = root / "frontend" / "mock"
    profile_fixture = json.loads((mock_dir / "risk-profile.json").read_text(encoding="utf-8"))
    assets_fixture = json.loads((mock_dir / "risk-assets.json").read_text(encoding="utf-8"))
    portfolio_fixture = json.loads((mock_dir / "risk-portfolio.json").read_text(encoding="utf-8"))

    profile = client.post("/api/risk/profile", json=PROFILE).json()
    assets = client.post(
        "/api/risk/assets",
        json={"symbols": ["510300", "511010"], "lookback_days": 252},
    ).json()
    portfolio = client.post(
        "/api/risk/portfolio",
        json={
            "weights_pct": {"510300": 40, "511010": 30, "518880": 20, "511880": 10},
            "lookback_days": 252,
        },
    ).json()

    assert set(profile_fixture["data"]) == set(profile["data"])
    assert set(assets_fixture["data"]) == set(assets["data"])
    assert set(assets_fixture["data"]["assets"][0]) == set(assets["data"]["assets"][0])
    assert set(portfolio_fixture["data"]) == set(portfolio["data"])
    assert set(portfolio_fixture["data"]["portfolio"]) == set(portfolio["data"]["portfolio"])
    assert set(portfolio_fixture["data"]["portfolio"]["portfolio_metrics"]) == set(
        portfolio["data"]["portfolio"]["portfolio_metrics"]
    )
