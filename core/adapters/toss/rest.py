"""
Toss증권 REST API 클라이언트.

엔드포인트 베이스: https://openapi.tossinvest.com
인증: Authorization: Bearer {access_token}
계좌: X-Tossinvest-Account: {accountSeq}

Rate Limit 그룹 분리:
  - MARKET_DATA: 시세·잔고 조회 (별도 FixedIntervalThrottler)
  - ORDER: 주문 생성 (별도 FixedIntervalThrottler)
  주문 전송이 시세 폴링 버킷을 소모하지 않도록 격리한다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import httpx

from core.adapters.kis.rest import BalanceInfo, BalanceItem, PriceInfo
from core.adapters.kis.throttler import FixedIntervalThrottler, ThrottlerConfig
from core.adapters.toss.auth import TossAuth
from core.config.settings import Market

if TYPE_CHECKING:
    from core.execution.executor import OrderAck
    from core.risk.models import Order

logger = logging.getLogger(__name__)

_TOSS_BASE_URL = "https://openapi.tossinvest.com"

# Rate Limit: Toss 공식 가이드 기준값 (보수적 적용)
_MARKET_DATA_THROTTLER_CONFIG = ThrottlerConfig(calls_per_second=5.0)
_ORDER_THROTTLER_CONFIG = ThrottlerConfig(calls_per_second=2.0)


# ---------------------------------------------------------------------------
# TossRestClient
# ---------------------------------------------------------------------------


class TossRestClient:
    """Toss증권 REST API 클라이언트.

    BrokerAdapter Protocol을 만족하며 get_price / get_balance / place_order를 구현한다.

    Args:
        auth: TossAuth 인스턴스 (토큰 관리).
        http_client: 테스트 인젝션용 httpx.AsyncClient.
        market_throttler: 시세·잔고용 스로틀러. None이면 기본값 생성.
        order_throttler: 주문용 스로틀러. None이면 기본값 생성.
    """

    def __init__(
        self,
        auth: TossAuth,
        http_client: httpx.AsyncClient | None = None,
        market_throttler: FixedIntervalThrottler | None = None,
        order_throttler: FixedIntervalThrottler | None = None,
    ) -> None:
        self._auth = auth
        self._http_client = http_client
        self._market_throttler = market_throttler or FixedIntervalThrottler(_MARKET_DATA_THROTTLER_CONFIG)
        self._order_throttler = order_throttler or FixedIntervalThrottler(_ORDER_THROTTLER_CONFIG)
        self._account_seq: str | None = None

    # ------------------------------------------------------------------
    # 초기화: 계좌 시퀀스 조회
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        """앱 시작 시 accountSeq를 획득한다.

        이후 모든 계좌 관련 API 호출에 X-Tossinvest-Account 헤더로 사용한다.
        """
        data = await self._request_market("GET", "/api/v1/accounts")
        accounts = data.get("result", [])
        if not accounts:
            raise RuntimeError("Toss 계좌 목록이 비어있습니다. 계좌 개설 여부를 확인하세요.")
        self._account_seq = str(accounts[0]["accountSeq"])
        logger.info("Toss accountSeq 획득: %s", self._account_seq)

    def _get_account_seq(self) -> str:
        if self._account_seq is None:
            raise RuntimeError("TossRestClient.initialize()가 먼저 호출되어야 합니다.")
        return self._account_seq

    # ------------------------------------------------------------------
    # 공통 요청 헬퍼
    # ------------------------------------------------------------------

    async def _get_headers(self) -> dict[str, str]:
        """Authorization 헤더를 포함한 공통 헤더를 반환한다.

        401 수신 시 자동으로 토큰을 재발급한다.
        """
        token = await self._auth.get_access_token()
        return {
            "Authorization": f"Bearer {token.access_token}",
            "Content-Type": "application/json",
        }

    async def _do_request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str],
        params: dict | None = None,
        json: dict | None = None,
    ) -> dict[str, Any]:
        """HTTP 요청을 실행하고 응답을 반환한다. 401 시 재발급 후 1회 재시도."""
        for attempt in range(2):
            if self._http_client:
                resp = await self._http_client.request(
                    method, url, headers=headers, params=params, json=json, timeout=10.0
                )
            else:
                async with httpx.AsyncClient() as client:
                    resp = await client.request(
                        method, url, headers=headers, params=params, json=json, timeout=10.0
                    )

            if resp.status_code == 401 and attempt == 0:
                logger.warning("Toss API 401 수신 — 토큰 재발급 후 재시도")
                new_token = await self._auth.refresh_on_401()
                headers["Authorization"] = f"Bearer {new_token.access_token}"
                continue

            if resp.status_code == 409:
                # 주문 중복 (request-in-progress) — 멱등키로 재조회 권장
                body = resp.json()
                err_code = body.get("error", {}).get("code", "")
                raise RuntimeError(f"Toss API 409 충돌 (code={err_code}): {body}")

            resp.raise_for_status()

            body = resp.json()
            if "error" in body:
                err = body["error"]
                raise RuntimeError(
                    f"Toss API 오류 (code={err.get('code')}, message={err.get('message')})"
                )
            return body

        raise RuntimeError("Toss API 인증 실패: 토큰 재발급 후에도 401 지속")

    async def _request_market(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        json: dict | None = None,
        with_account: bool = False,
    ) -> dict[str, Any]:
        """MARKET_DATA 그룹 스로틀러를 사용하는 요청."""
        await self._market_throttler.acquire()
        headers = await self._get_headers()
        if with_account:
            headers["X-Tossinvest-Account"] = self._get_account_seq()
        return await self._do_request(method, f"{_TOSS_BASE_URL}{path}", headers=headers, params=params, json=json)

    async def _request_order(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        json: dict | None = None,
    ) -> dict[str, Any]:
        """ORDER 그룹 스로틀러를 사용하는 요청 (비멱등 — 주문 전송)."""
        await self._order_throttler.acquire()
        headers = await self._get_headers()
        headers["X-Tossinvest-Account"] = self._get_account_seq()
        return await self._do_request(method, f"{_TOSS_BASE_URL}{path}", headers=headers, params=params, json=json)

    # ------------------------------------------------------------------
    # 현재가 조회 (BrokerAdapter.get_price)
    # ------------------------------------------------------------------

    async def get_price(self, symbol: str) -> PriceInfo:
        """현재가를 조회한다.

        GET /api/v1/prices?symbols={symbol}

        Returns:
            PriceInfo — KIS 어댑터와 동일한 타입을 반환해 상위 레이어 무수정.
        """
        data = await self._request_market("GET", "/api/v1/prices", params={"symbols": symbol})
        results = data.get("result", [])
        if not results:
            raise RuntimeError(f"Toss 현재가 조회 결과 없음: symbol={symbol}")

        item = results[0]
        market_country = item.get("marketCountry", "KR")
        market = Market.DOMESTIC if market_country == "KR" else Market.OVERSEAS

        return PriceInfo(
            symbol=symbol,
            current_price=float(item.get("lastPrice", 0)),
            open_price=float(item.get("openPrice", 0)),
            high_price=float(item.get("highPrice", 0)),
            low_price=float(item.get("lowPrice", 0)),
            volume=int(item.get("volume", 0)),
            market=market,
            raw=item,
        )

    # ------------------------------------------------------------------
    # 잔고 조회 (BrokerAdapter.get_balance)
    # ------------------------------------------------------------------

    async def get_balance(self, symbol: str | None = None) -> BalanceInfo:
        """계좌 보유 자산을 조회한다.

        GET /api/v1/holdings (X-Tossinvest-Account 헤더 필요)

        Args:
            symbol: 특정 종목 필터. None이면 전체 잔고.
        """
        data = await self._request_market("GET", "/api/v1/holdings", with_account=True)
        result = data.get("result", {})
        holding_items = result.get("items", [])

        items: list[BalanceItem] = []
        for row in holding_items:
            if symbol and row.get("symbol") != symbol:
                continue
            qty = int(row.get("quantity", 0))
            if qty == 0:
                continue
            items.append(
                BalanceItem(
                    symbol=row.get("symbol", ""),
                    symbol_name=row.get("name", ""),
                    qty=qty,
                    avg_price=float(row.get("averagePurchasePrice", 0)),
                    current_price=float(row.get("currentPrice", 0)),
                    eval_amount=float(row.get("marketValue", 0)),
                    profit_loss=float(row.get("unrealizedGainLoss", 0)),
                    profit_loss_rate=float(row.get("unrealizedGainLossRate", 0)),
                )
            )

        summary = result.get("summary", {})
        return BalanceInfo(
            items=items,
            total_eval_amount=float(summary.get("totalMarketValue", 0)),
            total_profit_loss=float(summary.get("totalUnrealizedGainLoss", 0)),
            deposit=float(summary.get("cashBalance", 0)),
        )

    # ------------------------------------------------------------------
    # 주문 생성 (BrokerAdapter.place_order)
    # ------------------------------------------------------------------

    async def place_order(self, order: Order) -> OrderAck:
        """매수/매도 주문을 Toss에 전송한다.

        POST /api/v1/orders
        clientOrderId 네이티브 지원 — 멱등성은 Toss 서버가 보장한다.

        Args:
            order: Risk Manager가 승인한 주문.

        Returns:
            OrderAck: Toss 주문 응답 (orderId 포함).

        Raises:
            RuntimeError: Toss API 오류 또는 409 충돌 시.
        """
        from core.execution.executor import OrderAck
        from core.risk.models import OrderSide, OrderType

        side = "BUY" if order.side == OrderSide.BUY else "SELL"
        order_type = "LIMIT" if order.order_type == OrderType.LIMIT else "MARKET"

        body: dict[str, Any] = {
            "clientOrderId": order.client_order_id,
            "symbol": order.symbol,
            "side": side,
            "orderType": order_type,
            "quantity": order.qty,
        }
        if order.order_type == OrderType.LIMIT:
            body["price"] = str(Decimal(str(order.price)))

        data = await self._request_order("POST", "/api/v1/orders", json=body)
        result = data.get("result", {})
        toss_order_id = result.get("orderId", "")

        return OrderAck(
            client_order_id=order.client_order_id,
            broker_order_id=toss_order_id,
            symbol=order.symbol,
            status="submitted",
            raw=result,
        )
