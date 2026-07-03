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

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Literal

import httpx

from core.adapters.models import BalanceInfo, BalanceItem, PriceInfo
from core.adapters.throttler import FixedIntervalThrottler, ThrottlerConfig
from core.adapters.toss.auth import TossAuth
from core.adapters.toss.models import (
    BuyingPowerInfo,
    Commission,
    ExchangeRate,
    Fill,
    KrMarketCalendar,
    KrMarketDay,
    OrderExecution,
    OrderOperationResponse,
    PriceLimits,
    StockInfo,
    StockWarning,
    TossCandle,
    TossOrder,
    UsMarketCalendar,
    UsMarketDay,
)
from core.config.settings import Market

if TYPE_CHECKING:
    from core.execution.executor import OrderAck
    from core.risk.models import Order

logger = logging.getLogger(__name__)

_TOSS_BASE_URL = "https://openapi.tossinvest.com"


class TossConflictError(RuntimeError):
    """Toss API 409 Conflict — 동시 처리 중인 요청과 충돌. cancel_order에서 구조적으로 catch한다."""


def _safe_float(value: Any, field: str) -> float:
    """숫자 문자열을 float으로 변환한다. 실패 시 RuntimeError."""
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"Toss API 비정상 숫자 값 ({field}={value!r})") from exc


def _safe_int(value: Any, field: str) -> int:
    """숫자 문자열을 int로 변환한다. 실패 시 RuntimeError."""
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"Toss API 비정상 정수 값 ({field}={value!r})") from exc


def _safe_nested_dict(row: dict[str, Any], key: str) -> dict[str, Any]:
    """중첩 객체 필드를 꺼낸다. 없거나 dict가 아니면 경고를 남기고 빈 dict를 반환한다.

    스펙상(specs/tossinvest/asset.json) 필수 필드지만, 응답이 스펙과 어긋나는
    경우를 대비해 예외를 던지지 않고 방어적으로 처리한다 — 대신 조용히 0으로
    떨어뜨리지 않도록 반드시 로그를 남긴다.
    """
    value = row.get(key)
    if not isinstance(value, dict):
        logger.warning("Toss holdings 응답에 %s 필드가 없거나 형식이 다릅니다 (값=%r)", key, value)
        return {}
    return value


def _safe_get(container: dict[str, Any], key: str, field_label: str) -> Any:
    """중첩 dict에서 값을 꺼낸다. 키가 없으면 경고를 남기고 0을 반환한다."""
    if key not in container:
        logger.warning("Toss holdings 응답에 %s.%s 필드가 없습니다 — 0으로 처리합니다.", field_label, key)
        return 0
    return container[key]


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
        # 환율 캐시: TTL 60초, asyncio.Lock으로 동시 다중 호출 방지 (인스턴스별 격리)
        self._exchange_rate_cache: dict[str, tuple[ExchangeRate, float]] = {}
        self._exchange_rate_lock: asyncio.Lock = asyncio.Lock()

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
        json_body: dict | None = None,
    ) -> dict[str, Any]:
        """HTTP 요청을 실행하고 응답을 반환한다. 401 시 재발급 후 1회 재시도."""
        for attempt in range(2):
            if self._http_client:
                resp = await self._http_client.request(
                    method, url, headers=headers, params=params, json=json_body, timeout=10.0
                )
            else:
                async with httpx.AsyncClient() as client:
                    resp = await client.request(
                        method, url, headers=headers, params=params, json=json_body, timeout=10.0
                    )

            if resp.status_code == 401:
                if attempt == 0:
                    logger.warning("Toss API 401 수신 — 토큰 재발급 후 재시도")
                    new_token = await self._auth.refresh_on_401()
                    headers["Authorization"] = f"Bearer {new_token.access_token}"
                    continue
                raise RuntimeError("Toss API 인증 실패: 토큰 재발급 후에도 401 지속")

            if resp.status_code == 409:
                body = resp.json()
                err_code = body.get("error", {}).get("code", "")
                # TossConflictError로 구별 — cancel_order에서 명시적으로 catch해 재조회 처리
                raise TossConflictError(f"Toss API 409 충돌 (code={err_code}): {body}")

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
        return await self._do_request(method, f"{_TOSS_BASE_URL}{path}", headers=headers, params=params, json_body=json)

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
        return await self._do_request(method, f"{_TOSS_BASE_URL}{path}", headers=headers, params=params, json_body=json)

    # ------------------------------------------------------------------
    # 현재가 조회 (BrokerAdapter.get_price)
    # ------------------------------------------------------------------

    async def get_price(self, symbol: str) -> PriceInfo:
        """현재가를 조회한다.

        GET /api/v1/prices?symbols={symbol}

        Returns:
            PriceInfo를 반환해 상위 레이어 변경 없이 호환된다.
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
            current_price=_safe_float(item.get("lastPrice", 0), "lastPrice"),
            open_price=_safe_float(item.get("openPrice", 0), "openPrice"),
            high_price=_safe_float(item.get("highPrice", 0), "highPrice"),
            low_price=_safe_float(item.get("lowPrice", 0), "lowPrice"),
            volume=_safe_int(item.get("volume", 0), "volume"),
            market=market,
            raw=item,
        )

    # ------------------------------------------------------------------
    # 잔고 조회 (BrokerAdapter.get_balance)
    # ------------------------------------------------------------------

    async def get_balance(self, symbol: str | None = None) -> BalanceInfo:
        """계좌 보유 자산을 조회한다.

        GET /api/v1/holdings (X-Tossinvest-Account 헤더 필요)

        실제 응답 스펙(specs/tossinvest/asset.json #HoldingsOverview)은
        marketValue/profitLoss가 통화별 중첩 객체이고, 요약 필드는 "summary"로
        감싸져 있지 않고 top-level(totalPurchaseAmount/marketValue/profitLoss)에
        바로 존재한다. total_* 필드는 KRW 기준 합산만 반영한다 (USD 보유분은
        원화 환산 없이는 단순 합산할 수 없어 items 레벨에서 종목별로 확인한다).

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
            # 소수점 단위 매매(fractional investing)를 지원하는 해외주식은 정수가
            # 아닐 수 있어 float로 파싱한다 (예: "10.5").
            qty = _safe_float(row.get("quantity", 0), "quantity")
            if qty == 0:
                continue
            market_value = _safe_nested_dict(row, "marketValue")
            profit_loss = _safe_nested_dict(row, "profitLoss")
            country = row.get("marketCountry", "KR")
            items.append(
                BalanceItem(
                    symbol=row.get("symbol", ""),
                    symbol_name=row.get("name", ""),
                    qty=qty,
                    avg_price=_safe_float(row.get("averagePurchasePrice", 0), "averagePurchasePrice"),
                    current_price=_safe_float(row.get("lastPrice", 0), "lastPrice"),
                    eval_amount=_safe_float(_safe_get(market_value, "amount", "marketValue"), "marketValue.amount"),
                    profit_loss=_safe_float(_safe_get(profit_loss, "amount", "profitLoss"), "profitLoss.amount"),
                    profit_loss_rate=_safe_float(_safe_get(profit_loss, "rate", "profitLoss"), "profitLoss.rate"),
                    market=Market.OVERSEAS if country == "US" else Market.DOMESTIC,
                )
            )

        total_market_value = _safe_get(_safe_nested_dict(result, "marketValue"), "amount", "marketValue") or {}
        total_profit_loss = _safe_get(_safe_nested_dict(result, "profitLoss"), "amount", "profitLoss") or {}
        return BalanceInfo(
            items=items,
            total_eval_amount_krw=_safe_float(
                _safe_get(total_market_value, "krw", "marketValue.amount"), "marketValue.amount.krw"
            ),
            total_profit_loss_krw=_safe_float(
                _safe_get(total_profit_loss, "krw", "profitLoss.amount"), "profitLoss.amount.krw"
            ),
            # holdings 응답에는 예수금(deposit)이 없다 — 별도 계좌 잔고 API 연동 전까지는 0 고정.
            deposit=0.0,
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
        toss_order_id = result.get("orderId")
        if not toss_order_id:
            raise RuntimeError(
                f"Toss 주문 응답에 orderId가 없습니다 (client_order_id={order.client_order_id}). "
                f"응답: {result}"
            )

        return OrderAck(
            client_order_id=order.client_order_id,
            broker_order_id=toss_order_id,
            symbol=order.symbol,
            status="submitted",
            raw=result,
        )

    # ------------------------------------------------------------------
    # T049 — 매수가능금액 · 판매가능수량 · 수수료
    # ------------------------------------------------------------------

    async def get_buying_power(self, currency: str = "KRW") -> BuyingPowerInfo:
        """매수가능금액을 조회한다.

        GET /api/v1/buying-power?currency={currency}

        Args:
            currency: 통화 코드 (기본 KRW).

        Returns:
            BuyingPowerInfo — 현금 기반 매수 가능 금액.
        """
        data = await self._request_market(
            "GET", "/api/v1/buying-power",
            params={"currency": currency},
            with_account=True,
        )
        result = data.get("result", {})
        return BuyingPowerInfo(
            currency=result.get("currency", currency),
            cash_buying_power=Decimal(str(result.get("cashBuyingPower", "0"))),
        )

    async def get_sellable_quantity(self, symbol: str) -> int:
        """판매가능수량을 조회한다.

        GET /api/v1/sellable-quantity?symbol={symbol}

        Args:
            symbol: 종목 심볼.

        Returns:
            판매가능 수량 (정수).
        """
        data = await self._request_market(
            "GET", "/api/v1/sellable-quantity",
            params={"symbol": symbol},
            with_account=True,
        )
        result = data.get("result", {})
        raw = result.get("sellableQuantity", "0")
        return int(Decimal(str(raw)))

    async def get_commissions(self) -> list[Commission]:
        """수수료 정책 목록을 조회한다.

        GET /api/v1/commissions

        Returns:
            Commission 리스트.
        """
        data = await self._request_market("GET", "/api/v1/commissions", with_account=True)
        items = data.get("result", [])
        return [
            Commission(
                market_country=item.get("marketCountry", ""),
                commission_rate=Decimal(str(item.get("commissionRate", "0"))),
                start_date=item.get("startDate"),
                end_date=item.get("endDate"),
            )
            for item in items
        ]

    # ------------------------------------------------------------------
    # T050 — 주문 관리 (목록·단건·취소·정정)
    # ------------------------------------------------------------------

    async def list_orders(
        self,
        status: Literal["OPEN", "CLOSED"],
        symbol: str | None = None,
        cursor: str | None = None,
        limit: int = 100,
    ) -> tuple[list[TossOrder], str | None]:
        """주문 목록을 조회한다.

        GET /api/v1/orders

        Args:
            status: 주문 상태 필터 (OPEN 또는 CLOSED). 필수.
            symbol: 특정 종목 필터. None이면 전체.
            cursor: 페이지네이션 커서.
            limit: 최대 반환 건수 (기본 100).

        Returns:
            (주문 목록, 다음 페이지 커서) 튜플.
            다음 페이지가 없으면 커서가 None.
        """
        params: dict[str, Any] = {"status": status, "limit": limit}
        if symbol:
            params["symbol"] = symbol
        if cursor:
            params["cursor"] = cursor

        data = await self._request_market("GET", "/api/v1/orders", params=params, with_account=True)
        result = data.get("result", {})
        items_raw = result.get("orders", [])
        has_next = result.get("hasNext", False)
        next_cursor: str | None = result.get("nextCursor") if has_next else None

        orders = [self._parse_toss_order(item) for item in items_raw]
        return orders, next_cursor

    async def get_order(self, order_id: str) -> TossOrder:
        """주문 단건을 조회한다.

        GET /api/v1/orders/{orderId}

        Args:
            order_id: Toss 주문 식별자.

        Returns:
            TossOrder 인스턴스.
        """
        data = await self._request_market(
            "GET", f"/api/v1/orders/{order_id}", with_account=True
        )
        result = data.get("result", {})
        return self._parse_toss_order(result)

    async def cancel_order(self, order_id: str) -> OrderOperationResponse:
        """주문을 취소한다.

        POST /api/v1/orders/{orderId}/cancel

        409 충돌(request-in-progress) 발생 시 주문을 재조회해 현재 상태를 확인한다.

        Args:
            order_id: 취소할 Toss 주문 식별자.

        Returns:
            OrderOperationResponse — 취소 후 새로 발급된 주문 ID.
        """
        try:
            data = await self._request_order(
                "POST", f"/api/v1/orders/{order_id}/cancel"
            )
        except TossConflictError:
            # 이미 처리 중인 취소 요청 — 현재 주문 상태를 재조회해 반환
            logger.warning("주문 취소 409 충돌 — 주문 재조회: order_id=%s", order_id)
            current = await self.get_order(order_id)
            return OrderOperationResponse(order_id=current.order_id)

        result = data.get("result", {})
        return OrderOperationResponse(order_id=result.get("orderId", order_id))

    async def modify_order(
        self,
        order_id: str,
        order_type: str,
        quantity: int | None = None,
        price: Decimal | None = None,
        confirm_high_value: bool = False,
    ) -> OrderOperationResponse:
        """주문을 정정한다.

        POST /api/v1/orders/{orderId}/modify

        Args:
            order_id: 정정할 Toss 주문 식별자.
            order_type: 정정 주문 유형 (LIMIT, MARKET). 필수.
            quantity: 정정 수량. None이면 원주문 수량 유지.
            price: 정정 가격. None이면 원주문 가격 유지.
            confirm_high_value: 고액 주문 확인 플래그.

        Returns:
            OrderOperationResponse — 정정 후 새로 발급된 주문 ID.
        """
        body: dict[str, Any] = {"orderType": order_type}
        if quantity is not None:
            body["quantity"] = quantity
        if price is not None:
            body["price"] = str(price)
        if confirm_high_value:
            body["confirmHighValueOrder"] = True

        data = await self._request_order(
            "POST", f"/api/v1/orders/{order_id}/modify", json=body
        )
        result = data.get("result", {})
        return OrderOperationResponse(order_id=result.get("orderId", order_id))

    def _parse_toss_order(self, item: dict[str, Any]) -> TossOrder:
        """Toss API 주문 객체를 TossOrder로 변환한다."""
        execution_raw = item.get("execution", {})
        execution = OrderExecution(
            filled_quantity=_safe_int(execution_raw.get("filledQuantity", 0), "filledQuantity"),
            avg_fill_price=(
                Decimal(str(execution_raw["averageFilledPrice"]))
                if execution_raw.get("averageFilledPrice") is not None
                else None
            ),
            fees=(
                Decimal(str(execution_raw["fees"]))
                if execution_raw.get("fees") is not None
                else None
            ),
        )
        raw_ts = item.get("orderedAt", "")
        try:
            ordered_at = datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00"))
        except Exception:
            ordered_at = datetime.now(UTC)

        raw_price = item.get("price")
        price = Decimal(str(raw_price)) if raw_price is not None else None

        return TossOrder(
            order_id=item.get("orderId", ""),
            client_order_id=item.get("clientOrderId"),
            symbol=item.get("symbol", ""),
            side=item.get("side", "BUY"),
            order_type=item.get("orderType", "LIMIT"),
            status=item.get("status", "PENDING"),
            quantity=_safe_int(item.get("quantity", 0), "quantity"),
            price=price,
            currency=item.get("currency", "KRW"),
            ordered_at=ordered_at,
            execution=execution,
        )

    # ------------------------------------------------------------------
    # T051 — 체결 내역
    # ------------------------------------------------------------------

    async def get_trades(self, count: int = 100) -> list[Fill]:
        """체결 내역을 조회한다.

        GET /api/v1/trades

        Args:
            count: 최대 반환 건수.

        Returns:
            Fill 리스트 (최신 체결 순).
        """
        data = await self._request_market(
            "GET", "/api/v1/trades",
            params={"count": count},
            with_account=True,
        )
        results = data.get("result", [])
        return [_normalize_toss_trade(item) for item in results]

    # ------------------------------------------------------------------
    # T052 — 마켓 정보 & 캘린더
    # ------------------------------------------------------------------

    async def get_price_limits(self, symbol: str) -> PriceLimits:
        """상하한가를 조회한다.

        GET /api/v1/price-limits?symbol={symbol}

        Args:
            symbol: 종목 심볼.

        Returns:
            PriceLimits 인스턴스.
        """
        data = await self._request_market(
            "GET", "/api/v1/price-limits", params={"symbol": symbol}
        )
        result = data.get("result", {})
        raw_ts = result.get("timestamp", "")
        try:
            timestamp = datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00"))
        except Exception:
            timestamp = datetime.now(UTC)

        return PriceLimits(
            symbol=symbol,
            upper_limit_price=(
                Decimal(str(result["upperLimitPrice"]))
                if result.get("upperLimitPrice") is not None
                else None
            ),
            lower_limit_price=(
                Decimal(str(result["lowerLimitPrice"]))
                if result.get("lowerLimitPrice") is not None
                else None
            ),
            timestamp=timestamp,
            currency=result.get("currency", "KRW"),
        )

    async def get_market_calendar_kr(self, date: str | None = None) -> KrMarketCalendar:
        """국내 마켓 캘린더를 조회한다.

        GET /api/v1/market-calendar/KR

        Args:
            date: 기준일 (YYYY-MM-DD). None이면 오늘 기준.

        Returns:
            KrMarketCalendar 인스턴스.
        """
        params: dict[str, Any] = {}
        if date:
            params["date"] = date
        data = await self._request_market("GET", "/api/v1/market-calendar/KR", params=params or None)
        result = data.get("result", {})
        return KrMarketCalendar(
            today=_parse_kr_market_day(result.get("today", {})),
            previous_business_day=_parse_kr_market_day(result.get("previousBusinessDay", {})),
            next_business_day=_parse_kr_market_day(result.get("nextBusinessDay", {})),
        )

    async def get_market_calendar_us(self, date: str | None = None) -> UsMarketCalendar:
        """미국 마켓 캘린더를 조회한다.

        GET /api/v1/market-calendar/US

        Args:
            date: 기준일 (YYYY-MM-DD). None이면 오늘 기준.

        Returns:
            UsMarketCalendar 인스턴스.
        """
        params: dict[str, Any] = {}
        if date:
            params["date"] = date
        data = await self._request_market("GET", "/api/v1/market-calendar/US", params=params or None)
        result = data.get("result", {})
        return UsMarketCalendar(
            today=_parse_us_market_day(result.get("today", {})),
            previous_business_day=_parse_us_market_day(result.get("previousBusinessDay", {})),
            next_business_day=_parse_us_market_day(result.get("nextBusinessDay", {})),
        )

    async def is_market_open(self, market: Literal["KR", "US"]) -> bool:
        """현재 시각 기준 시장 개장 여부를 반환한다.

        캘린더 API를 호출해 오늘 영업일 여부를 판단한다.

        Args:
            market: 시장 구분 (KR 또는 US).

        Returns:
            True이면 개장 중.
        """
        if market == "KR":
            cal = await self.get_market_calendar_kr()
            return cal.today.is_open
        else:
            cal = await self.get_market_calendar_us()
            return cal.today.is_open

    # ------------------------------------------------------------------
    # T053 — 종목 정보 & 유의사항
    # ------------------------------------------------------------------

    async def get_stocks(self, symbols: list[str]) -> list[StockInfo]:
        """종목 기본 정보를 조회한다.

        GET /api/v1/stocks?symbols=A,B,C

        Args:
            symbols: 종목 심볼 리스트.

        Returns:
            StockInfo 리스트.
        """
        data = await self._request_market(
            "GET", "/api/v1/stocks",
            params={"symbols": ",".join(symbols)},
        )
        results = data.get("result", [])
        return [
            StockInfo(
                symbol=item.get("symbol", ""),
                name=item.get("name", ""),
                english_name=item.get("englishName", ""),
                market=item.get("market", ""),
                status=item.get("status", "NORMAL"),
                currency=item.get("currency", "KRW"),
                isin_code=item.get("isinCode", ""),
                is_common_share=bool(item.get("isCommonShare", True)),
            )
            for item in results
        ]

    async def get_stock_warnings(self, symbol: str) -> list[StockWarning]:
        """종목 유의사항을 조회한다.

        GET /api/v1/stocks/{symbol}/warnings

        Args:
            symbol: 종목 심볼.

        Returns:
            StockWarning 리스트. 유의사항 없으면 빈 리스트.
        """
        data = await self._request_market("GET", f"/api/v1/stocks/{symbol}/warnings")
        results = data.get("result", [])
        return [
            StockWarning(
                warning_type=item.get("warningType", ""),
                start_date=item.get("startDate"),
                end_date=item.get("endDate"),
            )
            for item in results
        ]

    # ------------------------------------------------------------------
    # T054 — 환율 조회
    # ------------------------------------------------------------------

    async def get_exchange_rate(
        self,
        base_currency: str = "USD",
        quote_currency: str = "KRW",
    ) -> ExchangeRate:
        """환율을 조회한다. 60초 TTL 인메모리 캐시를 사용한다.

        GET /api/v1/exchange-rate

        Args:
            base_currency: 기준 통화 (기본 USD).
            quote_currency: 표시 통화 (기본 KRW).

        Returns:
            ExchangeRate 인스턴스.
        """
        import time
        cache_key = f"{base_currency}/{quote_currency}"

        async with self._exchange_rate_lock:
            cached = self._exchange_rate_cache.get(cache_key)
            if cached and (time.monotonic() - cached[1]) < 60.0:
                return cached[0]

            data = await self._request_market(
                "GET", "/api/v1/exchange-rate",
                params={"baseCurrency": base_currency, "quoteCurrency": quote_currency},
            )
            result = data.get("result", {})

            def _parse_dt(val: Any) -> datetime:
                try:
                    return datetime.fromisoformat(str(val).replace("Z", "+00:00"))
                except Exception:
                    return datetime.now(UTC)

            rate = ExchangeRate(
                base_currency=result.get("baseCurrency", base_currency),
                quote_currency=result.get("quoteCurrency", quote_currency),
                rate=Decimal(str(result.get("rate", "0"))),
                mid_rate=Decimal(str(result.get("midRate", "0"))),
                rate_change_type=result.get("rateChangeType", ""),
                valid_from=_parse_dt(result.get("validFrom", "")),
                valid_until=_parse_dt(result.get("validUntil", "")),
            )
            self._exchange_rate_cache[cache_key] = (rate, time.monotonic())
            return rate

    # ------------------------------------------------------------------
    # T055 — 과거 캔들 데이터
    # ------------------------------------------------------------------

    async def get_candles(
        self,
        symbol: str,
        interval: Literal["1m", "1d"],
        count: int = 100,
        before: str | None = None,
        adjusted: bool = True,
    ) -> list[TossCandle]:
        """과거 캔들 데이터를 조회한다.

        GET /api/v1/candles

        Args:
            symbol: 종목 심볼.
            interval: 봉 단위 ("1m" 또는 "1d").
            count: 최대 반환 건수 (기본 100).
            before: 이 시각 이전 데이터만 반환 (ISO 8601).
            adjusted: 수정주가 적용 여부 (기본 True).

        Returns:
            TossCandle 리스트 (오래된 순 → 최신 순).
        """
        params: dict[str, Any] = {
            "symbol": symbol,
            "interval": interval,
            "count": count,
            "adjusted": str(adjusted).lower(),
        }
        if before:
            params["before"] = before

        data = await self._request_market("GET", "/api/v1/candles", params=params)
        result = data.get("result", {})
        if isinstance(result, dict) and "candles" not in result:
            logger.warning("get_candles: 예상치 못한 응답 구조 (candles 키 없음): keys=%s", list(result.keys()))
        items = result.get("candles", result) if isinstance(result, dict) else result
        if not isinstance(items, list):
            raise RuntimeError(
                f"get_candles: Toss API 응답 구조 오류 — items가 list가 아닙니다 "
                f"(type={type(items).__name__}, symbol={symbol}). 응답 구조를 확인하세요."
            )

        candles = []
        for item in items:
            raw_ts = item.get("timestamp", "")
            try:
                ts = datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00"))
            except Exception:
                logger.warning("get_candles: 타임스탬프 파싱 실패 (raw=%r, symbol=%s) — 현재 시각으로 대체", raw_ts, symbol)
                ts = datetime.now(UTC)
            candles.append(
                TossCandle(
                    timestamp=ts,
                    open_price=Decimal(str(item.get("openPrice", "0"))),
                    high_price=Decimal(str(item.get("highPrice", "0"))),
                    low_price=Decimal(str(item.get("lowPrice", "0"))),
                    close_price=Decimal(str(item.get("closePrice", "0"))),
                    volume=_safe_int(item.get("volume", 0), "volume"),
                    currency=item.get("currency", "KRW"),
                )
            )
        return candles


# ---------------------------------------------------------------------------
# 모듈 수준 헬퍼 함수 (T051·T052)
# ---------------------------------------------------------------------------


def _normalize_toss_trade(item: dict[str, Any]) -> Fill:
    """Toss /api/v1/trades result 항목을 Fill로 변환한다."""
    raw_ts = item.get("timestamp", "")
    try:
        timestamp = datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00"))
    except Exception:
        timestamp = datetime.now(UTC)

    return Fill(
        symbol=item.get("symbol", ""),
        price=Decimal(str(item.get("price", "0"))),
        volume=int(Decimal(str(item.get("volume", "0")))),
        timestamp=timestamp,
        currency=item.get("currency", "KRW"),
        side=item.get("side"),
    )


def _parse_kr_market_day(raw: dict[str, Any]) -> KrMarketDay:
    """Toss KrMarketDay 원시 객체를 KrMarketDay로 변환한다."""
    integrated = raw.get("integrated") or {}
    is_open = bool(integrated)  # 빈 dict(휴장일)이면 False
    return KrMarketDay(
        date=raw.get("date", ""),
        is_open=is_open,
        open_time=integrated.get("open") if integrated else None,
        close_time=integrated.get("close") if integrated else None,
    )


def _parse_us_market_day(raw: dict[str, Any]) -> UsMarketDay:
    """Toss UsMarketDay 원시 객체를 UsMarketDay로 변환한다."""
    regular = raw.get("regular") or {}
    is_open = bool(regular)
    return UsMarketDay(
        date=raw.get("date", ""),
        is_open=is_open,
        regular_open=regular.get("open") if regular else None,
        regular_close=regular.get("close") if regular else None,
    )
