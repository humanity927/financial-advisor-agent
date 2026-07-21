from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from finance_advisor.market.models import MarketSeries
from finance_advisor.market.symbols import SymbolInfo
from finance_advisor.web import common as web_common
from finance_advisor.web.app import create_app
from finance_advisor.web.common import reset_market_service_for_tests
from finance_advisor.web.routes import market as market_routes


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TestClient:
    monkeypatch.setenv("FINANCE_FORCE_FIXTURE", "1")
    monkeypatch.setenv("FINANCE_CACHE_DIR", str(tmp_path / "cache"))
    reset_market_service_for_tests()
    app = create_app(static_dir=tmp_path / "frontend-dist")
    with TestClient(app) as test_client:
        yield test_client
    reset_market_service_for_tests()


def test_market_compare_returns_normalized_fixture_series(client: TestClient) -> None:
    response = client.post(
        "/api/market/compare",
        json={"symbols": ["510300", "511010", "518880", "511880"], "range": "1M"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["meta"]["source"] == "fixture"
    assert payload["meta"]["is_fallback"] is True
    assert any("非实时" in item for item in payload["warnings"])

    data = payload["data"]
    assert data["range_days"] == 20
    assert len(data["symbols"]) == 4
    assert len(data["normalized_series"]) == 4
    assert len(data["normalized_series"][0]["points"]) == 21
    assert data["normalized_series"][0]["points"][0]["normalized"] == 100.0
    assert data["source_details"][0]["fetched_at"]
    assert data["source_details"][0]["is_fallback"] is True
    assert set(data["interval_returns"][0]["returns"]) == {"20d", "60d", "252d"}
    assert data["latest_trade_date"] == payload["meta"]["as_of"]


def test_market_snapshot_supports_overview_contract(client: TestClient) -> None:
    response = client.get(
        "/api/market/snapshot",
        params={"symbols": "510300,511010,518880,511880"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["meta"]["source"] == "fixture"
    assert payload["meta"]["is_fallback"] is True
    assert any("演示数据" in item for item in payload["warnings"])
    assert [item["symbol"] for item in payload["data"]["snapshots"]] == [
        "510300",
        "511010",
        "518880",
        "511880",
    ]


def test_catalog_search_supports_code_name_and_empty_results(client: TestClient) -> None:
    by_name = client.get("/api/market/catalog/search", params={"q": "沪深300", "refresh": "false"})
    by_code = client.get("/api/market/catalog/search", params={"q": "000001", "refresh": "false"})
    empty = client.get(
        "/api/market/catalog/search", params={"q": "不存在的标的", "refresh": "false"}
    )

    assert by_name.status_code == 200
    assert any(item["symbol"] == "510300" for item in by_name.json()["data"]["items"])
    assert by_code.json()["data"]["items"][0]["asset_type"] == "index"
    assert empty.status_code == 200
    assert empty.json()["data"]["items"] == []


def test_market_snapshot_rejects_unsupported_symbol(client: TestClient) -> None:
    response = client.get("/api/market/snapshot", params={"symbols": "999999"})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_symbol"


def test_market_compare_loads_symbols_concurrently(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    delegate = web_common.get_market_service()
    barrier = threading.Barrier(4, timeout=2)
    thread_ids: set[int] = set()
    lock = threading.Lock()

    class ConcurrentService:
        def get_history(self, symbol: SymbolInfo, lookback_days: int) -> MarketSeries:
            with lock:
                thread_ids.add(threading.get_ident())
            barrier.wait()
            return delegate.get_history(symbol, lookback_days)

    monkeypatch.setattr(market_routes, "get_market_service", ConcurrentService)
    response = client.post(
        "/api/market/compare",
        json={"symbols": ["510300", "511010", "518880", "511880"], "range": "1M"},
    )

    assert response.status_code == 200
    assert len(thread_ids) == 4


def test_market_compare_rejects_unsupported_symbol(client: TestClient) -> None:
    response = client.post(
        "/api/market/compare",
        json={"symbols": ["999999"], "range": "3M"},
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["ok"] is False
    assert payload["error"]["code"] == "invalid_symbol"


def test_market_compare_validation_errors_are_unified(client: TestClient) -> None:
    response = client.post(
        "/api/market/compare",
        json={"symbols": ["510300"], "lookback_days": 1261},
    )

    assert response.status_code == 422
    payload = response.json()
    assert payload["ok"] is False
    assert payload["error"]["code"] == "validation_error"
    assert payload["data"]["validation_errors"]


def test_market_compare_contract_request_example_is_accepted(client: TestClient) -> None:
    root = Path(__file__).resolve().parents[1]
    contracts_dir = root / "data" / "fixtures" / "api_contracts"
    request_payload = json.loads(
        (contracts_dir / "market_compare_request.json").read_text(encoding="utf-8")
    )
    response_example = json.loads(
        (contracts_dir / "market_compare_response.json").read_text(encoding="utf-8")
    )

    response = client.post("/api/market/compare", json=request_payload)

    payload = response.json()
    assert response.status_code == 200
    assert payload["ok"] == response_example["ok"]
    assert set(payload["data"]) == set(response_example["data"])
    assert payload["data"]["symbols"][0]["symbol"] == request_payload["symbols"][0]
