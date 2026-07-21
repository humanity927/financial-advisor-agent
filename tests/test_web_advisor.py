from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from finance_advisor.agent.hermes_cli_adapter import MAX_PROMPT_CHARS, HermesCliError
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


def _complete_report() -> str:
    return """# 课程报告

## 用户画像
稳健型。
## 行情摘要
演示数据/非实时数据。
## 风险指标
年化波动率、最大回撤、VaR 和 CVaR 均来自工具结果。
## 配置建议
比例与金额来自确定性工具。
## 建议原因
遵守风险约束。
## 数据时间与来源
fixture，数据截至最近交易日。
## 风险提示
历史表现不代表未来收益。
"""


def test_advisor_report_uses_hermes_adapter(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, str] = {}

    class FakeAdapter:
        def generate_report(self, prompt: str) -> str:
            captured["prompt"] = prompt
            return _complete_report()

    monkeypatch.setattr(advisor_routes, "get_hermes_adapter", lambda: FakeAdapter())

    request = _report_payload()
    request["current_allocation_pct"] = {
        "现金": 30.0,
        "债券": 35.0,
        "股票": 25.0,
        "黄金": 10.0,
    }
    response = client.post("/api/advisor/report", json=request)

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["meta"]["source"] == "fixture"
    assert payload["meta"]["is_fallback"] is True
    assert payload["data"]["content"].startswith("# 课程报告")
    assert "deterministic_current_vs_target" in captured["prompt"]
    assert "deterministic_asset_risk" in captured["prompt"]
    assert len(captured["prompt"]) <= MAX_PROMPT_CHARS
    assert "allocation_deviation_amount_cny" in captured["prompt"]
    assert "同一轮并行调用" in captured["prompt"]
    for tool_name in (
        "assess_investor_profile",
        "get_market_snapshot",
        "analyze_asset_risk",
        "build_allocation",
    ):
        assert tool_name in captured["prompt"]


def test_advisor_report_rejects_incomplete_model_output(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class IncompleteAdapter:
        def generate_report(self, _prompt: str) -> str:
            return "## 用户画像\n只有一个章节。"

    monkeypatch.setattr(advisor_routes, "get_hermes_adapter", lambda: IncompleteAdapter())

    response = client.post("/api/advisor/report", json=_report_payload())

    assert response.status_code == 503
    payload = response.json()
    assert payload["error"]["code"] == "hermes_incomplete_report"
    assert payload["error"]["retryable"] is True


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


def test_advisor_report_rejects_boolean_current_allocation(client: TestClient) -> None:
    request = _report_payload()
    request["current_allocation_pct"] = {
        "现金": True,
        "债券": 64.0,
        "股票": 25.0,
        "黄金": 10.0,
    }

    response = client.post("/api/advisor/report", json=request)

    assert response.status_code == 422


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
