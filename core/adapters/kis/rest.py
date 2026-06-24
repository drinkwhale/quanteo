"""
KIS REST API 어댑터 — 현재가·잔고 조회 + 매수/매도 주문.

참조: open-trading-api/examples_llm/domestic_stock/inquire_price.py
     open-trading-api/examples_llm/domestic_stock/inquire_balance.py
     open-trading-api/examples_llm/domestic_stock/order_cash.py
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

import httpx

from core.adapters.kis.auth import KisAuth
from core.adapters.kis.throttler import FixedIntervalThrottler, with_retry
from core.adapters.kis.tr_ids import get_rest_domain, get_tr_ids
from core.config.settings import Env, Market

if TYPE_CHECKING:
    from core.execution.executor import OrderAck
    from core.risk.models import Order

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 응답 모델
# ---------------------------------------------------------------------------


@dataclass
class PriceInfo:
    """현재가 조회 결과."""

    symbol: str
    current_price: float
    open_price: float
    high_price: float
    low_price: float
    volume: int
    market: Market
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class BalanceItem:
    """잔고 항목 (보유 종목 1개)."""

    symbol: str
    symbol_name: str
    qty: int
    avg_price: float
    current_price: float
    eval_amount: float
    profit_loss: float
    profit_loss_rate: float


@dataclass
class BalanceInfo:
    """잔고 조회 결과."""

    items: list[BalanceItem]
    total_eval_amount: float
    total_profit_loss: float
    deposit: float


# ---------------------------------------------------------------------------
# REST 클라이언트
# ---------------------------------------------------------------------------


class KisRestClient:
    """KIS REST API 클라이언트.

    Args:
        auth: KisAuth 인스턴스 (토큰 관리).
        env: 투자 환경 (PROD/VPS).
        market: 대상 시장.
        http_client: 테스트 인젝션용 httpx.AsyncClient.
        throttler: FixedIntervalThrottler. None이면 기본값 생성.
    """

    def __init__(
        self,
        auth: KisAuth,
        env: Env = Env.VPS,
        market: Market = Market.DOMESTIC,
        http_client: httpx.AsyncClient | None = None,
        throttler: FixedIntervalThrottler | None = None,
    ) -> None:
        self.auth = auth
        self.env = env
        self.market = market
        self._base_url = get_rest_domain(env)
        self._tr_ids = get_tr_ids(env, market)
        self._http_client = http_client
        self._throttler = throttler or FixedIntervalThrottler()

    # ------------------------------------------------------------------
    # 내부 공통 요청 헬퍼
    # ------------------------------------------------------------------

    async def _request(
        self,
        method: Literal["GET", "POST"],
        path: str,
        tr_id: str,
        *,
        params: dict[str, str] | None = None,
        body: dict[str, str] | None = None,
        idempotent: bool = True,
    ) -> dict[str, Any]:
        """공통 HTTP 요청 헬퍼 (throttler + retry 포함).

        Args:
            method: "GET" 또는 "POST".
            path: API 경로.
            tr_id: KIS TR_ID 헤더값.
            params: GET 쿼리 파라미터.
            body: POST JSON 바디.
            idempotent: False이면 429 시 재시도 없이 즉시 예외 (주문 중복 방지).
        """

        async def _do() -> dict[str, Any]:
            token = await self.auth.get_access_token()
            headers = {
                "authorization": f"Bearer {token.token}",
                "appkey": self.auth.credentials.app_key,
                "appsecret": self.auth.credentials.app_secret.get_secret_value(),
                "tr_id": tr_id,
                "content-type": "application/json; charset=utf-8",
                "User-Agent": self.auth.credentials.user_agent,
            }
            url = f"{self._base_url}{path}"

            if self._http_client:
                if method == "GET":
                    resp = await self._http_client.get(url, headers=headers, params=params, timeout=10.0)
                else:
                    resp = await self._http_client.post(url, headers=headers, json=body, timeout=10.0)
            else:
                async with httpx.AsyncClient() as client:
                    if method == "GET":
                        resp = await client.get(url, headers=headers, params=params, timeout=10.0)
                    else:
                        resp = await client.post(url, headers=headers, json=body, timeout=10.0)

            resp.raise_for_status()
            data: dict[str, Any] = resp.json()

            rt_cd = data.get("rt_cd", "")
            if rt_cd != "0":
                msg = data.get("msg1", "알 수 없는 KIS API 오류")
                raise RuntimeError(f"KIS API 오류 (tr_id={tr_id}, rt_cd={rt_cd}): {msg}")

            return data

        return await with_retry(_do, self._throttler, idempotent=idempotent)

    async def _get(self, path: str, params: dict[str, str], tr_id: str) -> dict[str, Any]:
        """GET 요청 헬퍼 (멱등)."""
        return await self._request("GET", path, tr_id, params=params)

    async def _post(self, path: str, body: dict[str, str], tr_id: str) -> dict[str, Any]:
        """POST 요청 헬퍼 (비멱등 — 429 시 재시도 없음, 중복 주문 방지)."""
        return await self._request("POST", path, tr_id, body=body, idempotent=False)

    # ------------------------------------------------------------------
    # 현재가 조회
    # ------------------------------------------------------------------

    async def get_price(self, symbol: str) -> PriceInfo:
        """현재가를 조회한다.

        국내: FHKST01010100 / 해외: HHDFS76200200

        Args:
            symbol: 종목코드 (국내 6자리, 해외 티커).

        Returns:
            PriceInfo 인스턴스.
        """
        if self.market == Market.DOMESTIC:
            return await self._get_domestic_price(symbol)
        return await self._get_overseas_price(symbol)

    async def _get_domestic_price(self, symbol: str) -> PriceInfo:
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": symbol,
        }
        data = await self._get(
            "/uapi/domestic-stock/v1/quotations/inquire-price",
            params,
            self._tr_ids.price,
        )
        out = data.get("output", {})
        return PriceInfo(
            symbol=symbol,
            current_price=float(out.get("stck_prpr", 0)),
            open_price=float(out.get("stck_oprc", 0)),
            high_price=float(out.get("stck_hgpr", 0)),
            low_price=float(out.get("stck_lwpr", 0)),
            volume=int(out.get("acml_vol", 0)),
            market=self.market,
            raw=out,
        )

    async def _get_overseas_price(self, symbol: str) -> PriceInfo:
        params = {
            "AUTH": "",
            "EXCD": "NAS",  # 기본값 NASDAQ — 추후 파라미터화
            "SYMB": symbol,
        }
        data = await self._get(
            "/uapi/overseas-price/v1/quotations/price",
            params,
            self._tr_ids.price,
        )
        out = data.get("output", {})
        return PriceInfo(
            symbol=symbol,
            current_price=float(out.get("last", 0)),
            open_price=float(out.get("open", 0)),
            high_price=float(out.get("high", 0)),
            low_price=float(out.get("low", 0)),
            volume=int(out.get("tvol", 0)),
            market=self.market,
            raw=out,
        )

    # ------------------------------------------------------------------
    # 잔고 조회
    # ------------------------------------------------------------------

    async def get_balance(self) -> BalanceInfo:
        """계좌 잔고를 조회한다.

        국내: TTTC8434R (prod) / VTTC8434R (vps)
        """
        if self.market == Market.DOMESTIC:
            return await self._get_domestic_balance()
        return await self._get_overseas_balance()

    async def _get_domestic_balance(self) -> BalanceInfo:
        creds = self.auth.credentials
        params = {
            "CANO": creds.account_no,
            "ACNT_PRDT_CD": creds.account_code,
            "AFHR_FLPR_YN": "N",
            "OFL_YN": "",
            "INQR_DVSN": "02",
            "UNPR_DVSN": "01",
            "FUND_STTL_ICLD_YN": "N",
            "FNCG_AMT_AUTO_RDPT_YN": "N",
            "PRCS_DVSN": "01",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": "",
        }
        data = await self._get(
            "/uapi/domestic-stock/v1/trading/inquire-balance",
            params,
            self._tr_ids.balance,
        )

        items: list[BalanceItem] = []
        for row in data.get("output1", []):
            qty = int(row.get("hldg_qty", 0))
            if qty == 0:
                continue
            items.append(
                BalanceItem(
                    symbol=row.get("pdno", ""),
                    symbol_name=row.get("prdt_name", ""),
                    qty=qty,
                    avg_price=float(row.get("pchs_avg_pric", 0)),
                    current_price=float(row.get("prpr", 0)),
                    eval_amount=float(row.get("evlu_amt", 0)),
                    profit_loss=float(row.get("evlu_pfls_amt", 0)),
                    profit_loss_rate=float(row.get("evlu_pfls_rt", 0)),
                )
            )

        out2 = data.get("output2", [{}])
        summary = out2[0] if out2 else {}
        return BalanceInfo(
            items=items,
            total_eval_amount=float(summary.get("tot_evlu_amt", 0)),
            total_profit_loss=float(summary.get("evlu_pfls_smtl_amt", 0)),
            deposit=float(summary.get("dnca_tot_amt", 0)),
        )

    async def _get_overseas_balance(self) -> BalanceInfo:
        creds = self.auth.credentials
        params = {
            "CANO": creds.account_no,
            "ACNT_PRDT_CD": creds.account_code,
            "OVRS_EXCG_CD": "NASD",
            "TR_CRCY_CD": "USD",
            "CTX_AREA_FK200": "",
            "CTX_AREA_NK200": "",
        }
        data = await self._get(
            "/uapi/overseas-stock/v1/trading/inquire-balance",
            params,
            self._tr_ids.balance,
        )

        items: list[BalanceItem] = []
        for row in data.get("output1", []):
            qty = int(row.get("ovrs_cblc_qty", 0))
            if qty == 0:
                continue
            items.append(
                BalanceItem(
                    symbol=row.get("ovrs_pdno", ""),
                    symbol_name=row.get("ovrs_item_name", ""),
                    qty=qty,
                    avg_price=float(row.get("pchs_avg_pric", 0)),
                    current_price=float(row.get("now_pric2", 0)),
                    eval_amount=float(row.get("ovrs_stck_evlu_amt", 0)),
                    profit_loss=float(row.get("frcr_evlu_pfls_amt", 0)),
                    profit_loss_rate=float(row.get("evlu_pfls_rt", 0)),
                )
            )

        out2 = data.get("output2", {})
        return BalanceInfo(
            items=items,
            total_eval_amount=float(out2.get("tot_evlu_amt", 0)),
            total_profit_loss=float(out2.get("ovrs_tot_pfls", 0)),
            deposit=float(out2.get("frcr_dncl_amt_2", 0)),
        )

    # ------------------------------------------------------------------
    # 주문
    # ------------------------------------------------------------------

    async def place_order(self, order: Order) -> OrderAck:
        """매수/매도 주문을 KIS에 전송한다.

        환경별 TR_ID를 자동 선택하며 모의투자(vps)와 실전(prod) 모두 지원한다.
        국내 주식 시장가/지정가 주문을 처리한다.

        참조: open-trading-api/examples_llm/domestic_stock/order_cash.py

        Args:
            order: Risk Manager가 승인한 주문.

        Returns:
            OrderAck: KIS 주문 응답 (ODNO 포함).

        Raises:
            RateLimitExceeded: 주문 중 429 발생 (중복 방지를 위해 재시도 안 함).
            RuntimeError: KIS API 오류 발생 시.
        """
        if self.market == Market.DOMESTIC:
            return await self._place_domestic_order(order)
        return await self._place_overseas_order(order)

    async def _place_domestic_order(self, order: Order) -> OrderAck:
        from core.execution.executor import OrderAck
        from core.risk.models import OrderSide, OrderType

        tr_id = self._tr_ids.buy if order.side == OrderSide.BUY else self._tr_ids.sell

        # 주문 유형 코드: 00=지정가, 01=시장가 (KIS 국내주식 코드표)
        ord_dvsn = "00" if order.order_type == OrderType.LIMIT else "01"
        # 시장가 주문 시 가격은 "0"
        ord_unpr = str(int(order.price)) if order.order_type == OrderType.LIMIT else "0"

        creds = self.auth.credentials
        body = {
            "CANO": creds.account_no,
            "ACNT_PRDT_CD": creds.account_code,
            "PDNO": order.symbol,
            "ORD_DVSN": ord_dvsn,
            "ORD_QTY": str(order.qty),
            "ORD_UNPR": ord_unpr,
        }

        data = await self._post(
            "/uapi/domestic-stock/v1/trading/order-cash",
            body=body,
            tr_id=tr_id,
        )

        out = data.get("output", {})
        kis_order_id = out.get("ODNO", "")

        return OrderAck(
            client_order_id=order.client_order_id,
            kis_order_id=kis_order_id,
            symbol=order.symbol,
            status="submitted",
            raw=out,
        )

    async def _place_overseas_order(self, order: Order) -> OrderAck:
        from core.execution.executor import OrderAck
        from core.risk.models import OrderSide

        tr_id = self._tr_ids.buy if order.side == OrderSide.BUY else self._tr_ids.sell

        creds = self.auth.credentials
        body = {
            "CANO": creds.account_no,
            "ACNT_PRDT_CD": creds.account_code,
            "OVRS_EXCG_CD": "NASD",  # 기본값 NASDAQ — 추후 파라미터화
            "PDNO": order.symbol,
            "ORD_QTY": str(order.qty),
            "OVRS_ORD_UNPR": str(order.price) if order.price > 0 else "0",
            "ORD_SVR_DVSN_CD": "0",
            "ORD_DVSN": "00",
        }

        data = await self._post(
            "/uapi/overseas-stock/v1/trading/order",
            body=body,
            tr_id=tr_id,
        )

        out = data.get("output", {})
        return OrderAck(
            client_order_id=order.client_order_id,
            kis_order_id=out.get("ODNO", ""),
            symbol=order.symbol,
            status="submitted",
            raw=out,
        )
