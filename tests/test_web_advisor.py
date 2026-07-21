from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from finance_advisor.agent.hermes_cli_adapter import MAX_PROMPT_CHARS, HermesCliError
from finance_advisor.agent.tool_audit import record_tool_result
from finance_advisor.schemas import success_response
from finance_advisor.web.app import create_app
from finance_advisor.web.common import reset_market_service_for_tests
from finance_advisor.web.routes import advisor as advisor_routes


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TestClient:
    monkeypatch.setenv("FINANCE_FORCE_FIXTURE", "1")
    monkeypatch.setenv("FINANCE_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("FINANCE_TOOL_AUDIT_PATH", str(tmp_path / "tool-audit.jsonl"))
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
历史表现不代表未来收益。VaR/CVaR不覆盖所有极端市场事件。
"""


def _record_required_tools(audit_id: str) -> None:
    record_tool_result(
        "assess_investor_profile",
        success_response({"risk_level": "稳健型", "score": 46}),
        audit_id=audit_id,
    )
    record_tool_result(
        "get_market_snapshot",
        success_response(
            {"snapshots": [{"symbol": "510300", "trade_date": "2026-07-20"}]},
            source="fixture",
            as_of="2026-07-20",
            is_fallback=True,
        ),
        audit_id=audit_id,
    )
    record_tool_result(
        "analyze_asset_risk",
        success_response(
            {"assets": [{"symbol": "510300", "metrics": {"annual_volatility_pct": 10}}]},
            source="fixture",
            as_of="2026-07-20",
            is_fallback=True,
        ),
        audit_id=audit_id,
    )
    record_tool_result(
        "build_allocation",
        success_response({"effective_risk_level": "稳健型", "allocation_pct": {"现金": 20}}),
        audit_id=audit_id,
    )


class FakeAdapter:
    def configuration_error(self) -> None:
        return None


def test_advisor_report_uses_hermes_adapter_and_audits_tools(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, str] = {}

    class CompleteAdapter(FakeAdapter):
        def generate_report(self, prompt: str, *, audit_id: str | None = None) -> str:
            assert audit_id
            captured["prompt"] = prompt
            captured["audit_id"] = audit_id
            _record_required_tools(audit_id)
            return _complete_report()

    monkeypatch.setattr(advisor_routes, "get_hermes_adapter", lambda: CompleteAdapter())
    request = _report_payload()
    request["client_request_id"] = "test-audit-request"
    response = client.post("/api/advisor/report", json=request)

    assert response.status_code == 200
    payload = response.json()
    assert payload["meta"]["source"] == "fixture"
    assert payload["meta"]["is_fallback"] is True
    assert payload["data"]["content"].startswith("# 课程报告")
    assert [item["tool"] for item in payload["data"]["tool_calls"]] == [
        "assess_investor_profile",
        "get_market_snapshot",
        "analyze_asset_risk",
        "build_allocation",
    ]
    assert captured["audit_id"] == "test-audit-request"
    assert len(captured["prompt"]) <= MAX_PROMPT_CHARS
    assert '"audit_id":"test-audit-request"' in captured["prompt"]
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
    class IncompleteAdapter(FakeAdapter):
        def generate_report(self, _prompt: str, *, audit_id: str | None = None) -> str:
            assert audit_id
            _record_required_tools(audit_id)
            return "## 用户画像\n只有一个章节。"

    monkeypatch.setattr(advisor_routes, "get_hermes_adapter", lambda: IncompleteAdapter())
    response = client.post("/api/advisor/report", json=_report_payload())

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "hermes_incomplete_report"


def test_advisor_report_rejects_missing_tool_calls(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class NoToolsAdapter(FakeAdapter):
        def generate_report(self, _prompt: str, *, audit_id: str | None = None) -> str:
            return _complete_report()

    monkeypatch.setattr(advisor_routes, "get_hermes_adapter", lambda: NoToolsAdapter())
    response = client.post("/api/advisor/report", json=_report_payload())

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "mcp_tool_calls_incomplete"


def test_advisor_report_returns_stable_error_when_hermes_is_missing(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class MissingAdapter(FakeAdapter):
        def generate_report(self, _prompt: str, *, audit_id: str | None = None) -> str:
            raise FileNotFoundError("hermes")

    monkeypatch.setattr(advisor_routes, "get_hermes_adapter", lambda: MissingAdapter())
    response = client.post("/api/advisor/report", json=_report_payload())

    assert response.status_code == 503
    payload = response.json()
    assert payload["error"]["code"] == "model_unavailable"
    assert "FileNotFoundError" not in payload["error"]["message"]
    assert "\\" not in payload["error"]["message"]


def test_advisor_report_maps_hermes_retryable_error(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class TimeoutAdapter(FakeAdapter):
        def generate_report(self, _prompt: str, *, audit_id: str | None = None) -> str:
            raise HermesCliError("hermes_timeout", "报告生成超时", retryable=True)

    monkeypatch.setattr(advisor_routes, "get_hermes_adapter", lambda: TimeoutAdapter())
    response = client.post("/api/advisor/report", json=_report_payload())

    assert response.status_code == 503
    assert response.json()["error"] == {
        "code": "hermes_timeout",
        "message": "报告生成超时",
        "retryable": True,
    }


def test_advisor_report_rejects_invalid_symbol(client: TestClient) -> None:
    request = _report_payload()
    request["symbols"] = ["999999"]

    response = client.post("/api/advisor/report", json=request)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_symbol"


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
