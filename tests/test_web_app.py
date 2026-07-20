from __future__ import annotations

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


def test_health_uses_unified_envelope(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["data"]["status"] == "healthy"
    assert payload["meta"]["source"] == "system"
    assert payload["data"]["fixture_available"] is True


def test_spa_fallback_does_not_intercept_unknown_api(client: TestClient) -> None:
    response = client.get("/api/unknown")

    assert response.status_code == 404
    payload = response.json()
    assert payload["ok"] is False
    assert payload["error"]["code"] == "not_found"


def test_root_reports_missing_frontend_without_breaking_api(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "金融工作台后端已启动" in response.text
