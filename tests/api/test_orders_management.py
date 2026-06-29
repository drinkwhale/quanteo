"""POST /orders/{id}/cancel, POST /orders/{id}/modify 라우터 테스트."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from core.adapters.toss.models import OrderOperationResponse
from core.api.app import create_app
from core.api.deps import AppContainer
from core.events.bus import EventBus
from core.risk.manager import RiskManager
from core.store.db import StateStore


# ---------------------------------------------------------------------------
# 픽스처
# ---------------------------------------------------------------------------


@pytest.fixture
async def store(tmp_path):
    s = StateStore(db_path=str(tmp_path / "test.db"))
    await s.open()
    yield s
    await s.close()


def _make_broker(
    cancel_result: OrderOperationResponse | None = None,
    modify_result: OrderOperationResponse | None = None,
    cancel_raises: Exception | None = None,
    modify_raises: Exception | None = None,
) -> MagicMock:
    broker = MagicMock()
    if cancel_raises:
        broker.cancel_order = AsyncMock(side_effect=cancel_raises)
    else:
        broker.cancel_order = AsyncMock(
            return_value=cancel_result or OrderOperationResponse(order_id="toss-001")
        )
    if modify_raises:
        broker.modify_order = AsyncMock(side_effect=modify_raises)
    else:
        broker.modify_order = AsyncMock(
            return_value=modify_result or OrderOperationResponse(order_id="toss-001")
        )
    return broker


def _make_client(store: StateStore, broker: MagicMock | None = None) -> TestClient:
    bus = EventBus()
    risk = RiskManager(bus=bus)
    container = AppContainer(
        store=store, risk=risk, bus=bus, env="vps", market="domestic", broker=broker
    )
    return TestClient(create_app(container))


# ---------------------------------------------------------------------------
# POST /orders/{id}/cancel
# ---------------------------------------------------------------------------


def test_cancel_503_without_broker(store):
    client = _make_client(store, broker=None)
    res = client.post("/orders/toss-001/cancel")
    assert res.status_code == 503


def test_cancel_200_success(store):
    broker = _make_broker()
    client = _make_client(store, broker=broker)
    res = client.post("/orders/toss-001/cancel")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["order_id"] == "toss-001"


def test_cancel_400_on_broker_error(store):
    broker = _make_broker(cancel_raises=RuntimeError("주문 취소 불가 상태"))
    client = _make_client(store, broker=broker)
    res = client.post("/orders/toss-001/cancel")
    assert res.status_code == 400
    assert "주문 취소 불가 상태" in res.json()["detail"]


def test_cancel_400_on_network_error(store):
    broker = _make_broker(cancel_raises=ConnectionError("네트워크 오류"))
    client = _make_client(store, broker=broker)
    res = client.post("/orders/toss-001/cancel")
    assert res.status_code == 400


# ---------------------------------------------------------------------------
# POST /orders/{id}/modify
# ---------------------------------------------------------------------------


def test_modify_503_without_broker(store):
    client = _make_client(store, broker=None)
    res = client.post("/orders/toss-001/modify", json={"order_type": "LIMIT", "quantity": 5})
    assert res.status_code == 503


def test_modify_200_quantity_only(store):
    broker = _make_broker()
    client = _make_client(store, broker=broker)
    res = client.post("/orders/toss-001/modify", json={"order_type": "LIMIT", "quantity": 5})
    assert res.status_code == 200
    assert res.json()["success"] is True


def test_modify_200_price_only(store):
    broker = _make_broker()
    client = _make_client(store, broker=broker)
    res = client.post("/orders/toss-001/modify", json={"order_type": "LIMIT", "price": "73000"})
    assert res.status_code == 200
    assert res.json()["success"] is True


def test_modify_200_both_params(store):
    broker = _make_broker()
    client = _make_client(store, broker=broker)
    res = client.post(
        "/orders/toss-001/modify",
        json={"order_type": "LIMIT", "quantity": 5, "price": "73000"},
    )
    assert res.status_code == 200


def test_modify_400_on_broker_error(store):
    broker = _make_broker(modify_raises=RuntimeError("정정 불가 상태"))
    client = _make_client(store, broker=broker)
    res = client.post("/orders/toss-001/modify", json={"order_type": "LIMIT", "quantity": 3})
    assert res.status_code == 400
    assert "정정 불가 상태" in res.json()["detail"]


def test_modify_confirm_high_value_passed_to_broker(store):
    broker = _make_broker()
    client = _make_client(store, broker=broker)
    client.post(
        "/orders/toss-001/modify",
        json={"order_type": "LIMIT", "quantity": 1000, "price": "100000", "confirm_high_value": True},
    )
    _, kwargs = broker.modify_order.call_args
    assert kwargs.get("confirm_high_value") is True
