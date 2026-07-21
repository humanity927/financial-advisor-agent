from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from finance_advisor.agent.hermes_cli_adapter import HermesCliError
from finance_advisor.web import common as web_common
from finance_advisor.web.app import create_app
from finance_advisor.web.common import reset_market_service_for_tests
from finance_advisor.web.routes import advisor as advisor_routes


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TestClient:
    monkeypatch.setenv("FINANCE_FORCE_FIXTURE", "1")
    monkeypatch.setenv("FINANCE_CACHE_DIR", str(tmp_path / "cache"))
    reset_market_service_for_tests()
    app = create_app(static_dir=tmp_path / "frontend-dist")
    with TestClient(app) as test_client:
        yield test_client
    reset_market_service_for_tests()


def _report_payload() -> dict[str, object]:
    return {
        "amount_cny": 50_000,
        "horizon_months": 12,
        "max_loss_pct": 10,
        "income_stability": "stable",
        "experience": "basic",
        "liquidity_need": "medium",
        "emergency_fund_months": 6,
        "symbols": ["510300", "511010", "518880", "511880"],
    }


def test_advisor_report_uses_hermes_adapter(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, str] = {}

    class FakeAdapter:
        def generate_report(self, prompt: str) -> str:
            captured["prompt"] = prompt
            return "# 课程报告\n\n仅基于确定性事实生成。"

    monkeypatch.setattr(advisor_routes, "get_hermes_adapter", lambda: FakeAdapter())

    response = client.post("/api/advisor/report", json=_report_payload())

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["meta"]["source"] == "fixture"
    assert payload["meta"]["is_fallback"] is True
    assert payload["data"]["content"].startswith("# 课程报告")
    assert "market_snapshots" in captured["prompt"]
    assert "portfolio_plan" in captured["prompt"]


def test_advisor_report_returns_stable_error_when_hermes_is_missing(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class MissingAdapter:
        def generate_report(self, _prompt: str) -> str:
            raise FileNotFoundError("hermes")

    monkeypatch.setattr(advisor_routes, "get_hermes_adapter", lambda: MissingAdapter())

    response = client.post("/api/advisor/report", json=_report_payload())

    assert response.status_code == 503
    payload = response.json()
    assert payload["ok"] is False
    assert payload["error"]["code"] == "model_unavailable"
    assert payload["error"]["retryable"] is True


def test_advisor_report_maps_hermes_retryable_error(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class TimeoutAdapter:
        def generate_report(self, _prompt: str) -> str:
            raise HermesCliError("hermes_timeout", "timeout", retryable=True)

    monkeypatch.setattr(advisor_routes, "get_hermes_adapter", lambda: TimeoutAdapter())

    response = client.post("/api/advisor/report", json=_report_payload())

    assert response.status_code == 503
    payload = response.json()
    assert payload["error"]["code"] == "hermes_timeout"
    assert payload["error"]["retryable"] is True


def test_advisor_report_rejects_invalid_symbol(client: TestClient) -> None:
    request = _report_payload()
    request["symbols"] = ["000001"]

    response = client.post("/api/advisor/report", json=request)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_symbol"


def test_advisor_report_returns_stable_error_when_market_fails(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class BrokenService:
        def get_snapshot(self, _symbol: object) -> object:
            raise RuntimeError("boom")

    monkeypatch.setattr(web_common, "get_market_service", BrokenService)
    monkeypatch.setattr(advisor_routes, "get_market_service", BrokenService)

    response = client.post("/api/advisor/report", json=_report_payload())

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "advisor_data_unavailable"
