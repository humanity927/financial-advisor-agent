from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from finance_advisor.allocation.service import ASSET_CLASSES
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


def _profile_payload() -> dict[str, object]:
    return {
        "amount_cny": 50_000,
        "horizon_months": 12,
        "max_loss_pct": 10,
        "income_stability": "stable",
        "experience": "basic",
        "liquidity_need": "medium",
        "emergency_fund_months": 6,
    }


def test_portfolio_plan_returns_web_contract(client: TestClient) -> None:
    response = client.post("/api/portfolio/plan", json=_profile_payload())

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["meta"]["source"] == "system"
    data = payload["data"]
    assert data["total_amount_cny"] == 50_000
    assert round(sum(data["allocation_pct"].values()), 1) == 100.0
    assert data["current_allocation_pct"] is None
    assert data["current_allocation_amount_cny"] is None
    assert data["allocation_deviation_pct"] is None
    assert data["allocation_deviation_amount_cny"] is None
    assert data["adjustment_steps"]
    assert data["rationale"]


def test_portfolio_plan_compares_current_allocation(client: TestClient) -> None:
    request = _profile_payload()
    request["current_allocation_pct"] = {asset: 25.0 for asset in ASSET_CLASSES}

    response = client.post("/api/portfolio/plan", json=request)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["current_allocation_pct"] == request["current_allocation_pct"]
    assert round(sum(data["current_allocation_amount_cny"].values()), 2) == 50_000.0
    assert round(sum(data["allocation_deviation_pct"].values()), 1) == 0.0
    assert round(sum(data["allocation_deviation_amount_cny"].values()), 2) == 0.0


def test_portfolio_plan_rejects_invalid_current_allocation(client: TestClient) -> None:
    request = _profile_payload()
    request["current_allocation_pct"] = {asset: 10.0 for asset in ASSET_CLASSES}

    response = client.post("/api/portfolio/plan", json=request)

    assert response.status_code == 400
    payload = response.json()
    assert payload["ok"] is False
    assert payload["error"]["code"] == "invalid_portfolio_plan_request"


def test_portfolio_plan_rejects_boolean_current_allocation(client: TestClient) -> None:
    request = _profile_payload()
    request["current_allocation_pct"] = {
        "现金": True,
        "债券": 64.0,
        "股票": 25.0,
        "黄金": 10.0,
    }

    response = client.post("/api/portfolio/plan", json=request)

    assert response.status_code == 422
