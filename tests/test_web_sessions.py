from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from finance_advisor.agent.sessions import reset_session_store_for_tests
from finance_advisor.schemas import error_response, success_response
from finance_advisor.web.app import create_app
from finance_advisor.web.routes import sessions as session_routes


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TestClient:
    monkeypatch.setenv("FINANCE_SESSION_DIR", str(tmp_path / "sessions"))
    reset_session_store_for_tests()
    app = create_app(static_dir=tmp_path / "frontend-dist")
    with TestClient(app) as test_client:
        yield test_client
    reset_session_store_for_tests()


def _create(client: TestClient) -> str:
    response = client.post("/api/sessions", json={"title": "新咨询"})
    assert response.status_code == 200
    assert response.json()["data"]["profile"] == {}
    return str(response.json()["data"]["id"])


def _fake_report(_request: object) -> dict[str, object]:
    calls = [
        {
            "tool": name,
            "called_at": "2026-07-21T10:00:00+08:00",
            "ok": True,
            "source": "system"
            if name in {"assess_investor_profile", "build_allocation"}
            else "cache",
            "as_of": "2026-07-20",
            "error_code": None,
            "summary": {},
        }
        for name in (
            "assess_investor_profile",
            "get_market_snapshot",
            "analyze_asset_risk",
            "build_allocation",
        )
    ]
    return success_response(
        {
            "content": "## 用户画像\n稳健型\n\n## 风险提示\n历史表现不代表未来收益。",
            "source": "cache",
            "as_of": "2026-07-20",
            "is_fallback": True,
            "tool_calls": calls,
        },
        source="cache",
        as_of="2026-07-20",
        is_fallback=True,
    )


def test_session_follows_up_one_missing_profile_field_at_a_time(client: TestClient) -> None:
    session_id = _create(client)

    response = client.post(
        f"/api/sessions/{session_id}/messages",
        json={"content": "我想关注沪深300ETF", "client_request_id": "followup-request"},
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["missing_fields"][0] == "amount_cny"
    assert payload["message"]["content"] == "这次计划投入多少金额？请用元或万元说明。"
    assert [item["type"] for item in payload["actions"]] == [
        "market.symbol.add",
        "risk.symbol.select",
    ]


def test_complete_chat_extracts_profile_invokes_report_and_restores_session(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(session_routes, "advisor_report", _fake_report)
    session_id = _create(client)
    content = (
        "我计划投入10万元，投资期限2年，最大可承受亏损15%，收入稳定，"
        "有基础投资经验，流动性中等，应急资金可覆盖6个月，关注510300。"
    )

    response = client.post(
        f"/api/sessions/{session_id}/messages",
        json={"content": content, "client_request_id": "complete-request"},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["missing_fields"] == []
    assert data["session"]["profile"] == {
        "amount_cny": 100_000.0,
        "horizon_months": 24,
        "max_loss_pct": 15.0,
        "income_stability": "stable",
        "experience": "basic",
        "liquidity_need": "medium",
        "emergency_fund_months": 6,
    }
    assert [call["tool"] for call in data["message"]["tool_calls"]] == [
        "assess_investor_profile",
        "get_market_snapshot",
        "analyze_asset_risk",
        "build_allocation",
    ]
    restored = client.get(f"/api/sessions/{session_id}").json()["data"]
    assert len(restored["messages"]) == 2
    assert restored["messages"][-1]["as_of"] == "2026-07-20"


def test_sensitive_numbers_are_redacted_before_persistence(client: TestClient) -> None:
    session_id = _create(client)
    response = client.post(
        f"/api/sessions/{session_id}/messages",
        json={
            "content": "我的身份证是110101199001011234，请帮我做规划",
            "client_request_id": "sensitive-request",
        },
    )

    assert response.status_code == 200
    stored = client.get(f"/api/sessions/{session_id}").json()["data"]
    assert "110101199001011234" not in stored["messages"][0]["content"]
    assert "[敏感信息已移除]" in stored["messages"][0]["content"]


def test_unknown_and_invalid_ui_actions_are_rejected(client: TestClient) -> None:
    session_id = _create(client)
    unknown = client.post(
        f"/api/sessions/{session_id}/actions",
        json={"action": {"type": "dom.execute", "payload": {}}},
    )
    invalid_symbol = client.post(
        f"/api/sessions/{session_id}/actions",
        json={"action": {"type": "market.symbol.add", "payload": {"symbol": "999999"}}},
    )

    assert unknown.status_code == 422
    assert invalid_symbol.status_code == 400
    assert invalid_symbol.json()["error"]["code"] == "invalid_ui_action"


@pytest.mark.parametrize(
    "allocation",
    [
        {"现金": 20, "债券": 45, "股票": 25, "加密资产": 10},
        {"现金": 20, "债券": 45, "股票": 25},
        {"现金": 20, "债券": 45, "股票": 135, "黄金": -100},
        {"现金": True, "债券": 45, "股票": 25, "黄金": 10},
    ],
)
def test_portfolio_action_rejects_invalid_allocation_boundaries(
    client: TestClient,
    allocation: dict[str, object],
) -> None:
    session_id = _create(client)

    response = client.post(
        f"/api/sessions/{session_id}/actions",
        json={
            "action": {
                "type": "portfolio.inputs.patch",
                "payload": {"current_allocation_pct": allocation},
            }
        },
    )

    assert response.status_code == 422


def test_allowed_ui_actions_patch_portfolio_and_symbol_state(client: TestClient) -> None:
    session_id = _create(client)
    profile = client.post(
        f"/api/sessions/{session_id}/actions",
        json={
            "action": {
                "type": "portfolio.inputs.patch",
                "payload": {
                    "profile": {"amount_cny": 80_000},
                    "current_allocation_pct": {
                        "现金": 20,
                        "债券": 45,
                        "股票": 25,
                        "黄金": 10,
                    },
                },
            }
        },
    )
    added = client.post(
        f"/api/sessions/{session_id}/actions",
        json={"action": {"type": "market.symbol.add", "payload": {"symbol": "000001"}}},
    )
    selected = client.post(
        f"/api/sessions/{session_id}/actions",
        json={"action": {"type": "risk.symbol.select", "payload": {"symbol": "000001"}}},
    )
    removed = client.post(
        f"/api/sessions/{session_id}/actions",
        json={"action": {"type": "market.symbol.remove", "payload": {"symbol": "000001"}}},
    )

    assert profile.status_code == 200
    assert added.status_code == selected.status_code == removed.status_code == 200
    session = removed.json()["data"]["session"]
    assert session["profile"]["amount_cny"] == 80_000
    assert sum(session["current_allocation_pct"].values()) == 100
    assert session["symbols"] == []
    assert session["risk_symbol"] == "000001"


def test_regenerate_replaces_last_assistant_message(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(session_routes, "advisor_report", _fake_report)
    session_id = _create(client)
    content = (
        "投入10万元，投资期限2年，最大可承受亏损15%，收入稳定，"
        "有基础投资经验，流动性中等，应急资金6个月。"
    )
    client.post(
        f"/api/sessions/{session_id}/messages",
        json={"content": content, "client_request_id": "first-generation"},
    )

    response = client.post(f"/api/sessions/{session_id}/regenerate")

    assert response.status_code == 200
    assert len(response.json()["data"]["session"]["messages"]) == 2


def test_report_failure_is_safe_and_recorded(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failed_report(_request: object) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content=error_response(
                "model_rate_limited",
                "模型服务当前请求过多，请稍后重试。",
                retryable=True,
            ),
        )

    monkeypatch.setattr(session_routes, "advisor_report", failed_report)
    session_id = _create(client)
    response = client.post(
        f"/api/sessions/{session_id}/messages",
        json={
            "content": (
                "投入10万元，投资期限2年，最大可承受亏损15%，收入稳定，"
                "有基础投资经验，流动性中等，应急资金6个月。"
            ),
            "client_request_id": "failed-generation",
        },
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "model_rate_limited"
    stored = client.get(f"/api/sessions/{session_id}").json()["data"]
    assert stored["messages"][-1]["status"] == "error"
    assert "请求过多" in stored["messages"][-1]["content"]


def test_session_list_delete_and_clear(client: TestClient) -> None:
    first = _create(client)
    second = _create(client)
    assert len(client.get("/api/sessions").json()["data"]["sessions"]) == 2

    deleted = client.delete(f"/api/sessions/{first}")
    cleared = client.delete("/api/sessions")

    assert deleted.json()["data"]["deleted"] is True
    assert cleared.json()["data"]["deleted"] == 1
    assert client.get(f"/api/sessions/{second}").status_code == 404
