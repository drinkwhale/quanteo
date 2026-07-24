"""
마켓 데이터 수집 — 거래대금/거래량 기준 종목 모니터링.

Phase 17: 실시간 시장 데이터를 주기적으로 폴링하고 DB에 저장.
방식: 4+2 하이브리드 (거래 기록 + Stock Miner 추천 종목 통합)
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

from core.adapters.base import BrokerAdapter
from core.store.db import StateStore

logger = logging.getLogger(__name__)


class MarketDataCollector:
    """거래 중인 종목 동적 발견 및 실시간 시장 데이터 수집."""

    def __init__(
        self,
        broker: BrokerAdapter,
        db: StateStore,
        poll_interval_minutes: int = 5,
    ):
        self.broker = broker
        self.db = db
        self.poll_interval_minutes = poll_interval_minutes
        self.active_symbols: set[str] = set()
        self._collecting = False

    async def discover_symbols(self) -> set[str]:
        """동적으로 모니터링할 종목 발견 (하이브리드 방식)."""
        symbols = set()

        # 1. Stock Miner 추천 종목 (우선순위 최고)
        try:
            screened = await self._get_screened_symbols()
            symbols.update(screened)
            logger.info(f"Stock Miner: {len(screened)} 종목 추가")
        except Exception as e:
            logger.warning(f"Stock Miner 조회 실패: {e}")

        # 2. 최근 주문 종목
        try:
            orders = await self.broker.get_orders()
            order_symbols = {o.symbol for o in orders}
            symbols.update(order_symbols)
            logger.info(f"최근 주문: {len(order_symbols)} 종목 추가")
        except Exception as e:
            logger.warning(f"주문 조회 실패: {e}")

        # 3. 현재 보유 종목
        try:
            holdings = await self.broker.get_holdings()
            holding_symbols = {h.symbol for h in holdings}
            symbols.update(holding_symbols)
            logger.info(f"보유 종목: {len(holding_symbols)} 종목 추가")
        except Exception as e:
            logger.warning(f"보유 조회 실패: {e}")

        # 4. DB에 캐시된 활성 종목 (빠른 부팅)
        try:
            cached = await self._get_cached_active_symbols()
            symbols.update(cached)
            logger.info(f"캐시된 종목: {len(cached)} 종목 추가")
        except Exception as e:
            logger.warning(f"캐시 조회 실패: {e}")

        # 5. 최근 거래 기록에서 추출
        try:
            recent = await self._get_recent_trade_symbols(hours=24)
            symbols.update(recent)
            logger.info(f"최근 거래: {len(recent)} 종목 추가")
        except Exception as e:
            logger.warning(f"거래 기록 조회 실패: {e}")

        return symbols

    async def collect_market_data(self) -> None:
        """주기적으로 마켓 데이터 수집."""
        if not self.active_symbols:
            logger.warning("모니터링할 종목이 없습니다")
            return

        logger.info(f"마켓 데이터 수집 시작: {len(self.active_symbols)} 종목")
        timestamp = datetime.utcnow().isoformat()

        # 병렬 폴링
        tasks = [
            self.broker.get_price(symbol) for symbol in self.active_symbols
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        stored_count = 0
        for symbol, result in zip(self.active_symbols, results):
            if isinstance(result, Exception):
                logger.debug(f"[{symbol}] 폴링 실패: {result}")
                continue

            try:
                await self.db.conn.execute(
                    """
                    INSERT OR REPLACE INTO market_data
                    (symbol, price, change_rate, trading_volume, trading_value, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        symbol,
                        float(result.get("price", 0)),
                        float(result.get("change_rate", 0)),
                        int(result.get("trading_volume", 0)),
                        int(result.get("trading_value", 0)),
                        timestamp,
                    ),
                )
                await self.db.conn.commit()
                stored_count += 1
            except Exception as e:
                logger.error(f"[{symbol}] DB 저장 실패: {e}")

        logger.info(f"마켓 데이터 저장: {stored_count}/{len(self.active_symbols)}")

    async def start(self) -> None:
        """백그라운드 수집 시작."""
        if self._collecting:
            logger.warning("이미 수집 중입니다")
            return

        self._collecting = True
        self.active_symbols = await self.discover_symbols()
        logger.info(f"모니터링 종목: {len(self.active_symbols)}")

        # 주기적 폴링 루프
        try:
            while self._collecting:
                await self.collect_market_data()
                await asyncio.sleep(self.poll_interval_minutes * 60)
        except asyncio.CancelledError:
            logger.info("수집 중단됨")
        except Exception as e:
            logger.error(f"수집 중 오류: {e}", exc_info=True)
        finally:
            self._collecting = False

    def stop(self) -> None:
        """수집 중지."""
        self._collecting = False
        logger.info("수집 중지 요청됨")

    # -------- 헬퍼 메서드 --------

    async def _get_screened_symbols(self) -> list[str]:
        """Stock Miner 추천 종목 조회."""
        try:
            async with self.db.conn.execute(
                "SELECT symbol FROM watchlist WHERE source = 'screener' LIMIT 100"
            ) as cursor:
                result = await cursor.fetchall()
            return [row[0] for row in result]
        except Exception:
            return []

    async def _get_cached_active_symbols(self) -> list[str]:
        """이전 세션의 활성 종목 캐시."""
        try:
            async with self.db.conn.execute(
                """
                SELECT symbol FROM active_symbols
                WHERE last_seen > datetime('now', '-3 days')
                LIMIT 200
                """
            ) as cursor:
                result = await cursor.fetchall()
            return [row[0] for row in result]
        except Exception:
            return []

    async def _get_recent_trade_symbols(self, hours: int = 24) -> list[str]:
        """최근 거래 기록에서 활성 종목 추출."""
        try:
            async with self.db.conn.execute(
                f"""
                SELECT DISTINCT symbol FROM fills
                WHERE filled_at > datetime('now', '-{hours} hours')
                LIMIT 200
                """
            ) as cursor:
                result = await cursor.fetchall()
            return [row[0] for row in result]
        except Exception:
            return []

    async def refresh_active_symbols(self) -> None:
        """활성 종목 목록 갱신."""
        self.active_symbols = await self.discover_symbols()
        logger.info(f"활성 종목 갱신: {len(self.active_symbols)}")

        # DB 캐시 업데이트
        timestamp = datetime.utcnow().isoformat()
        for symbol in self.active_symbols:
            try:
                await self.db.conn.execute(
                    """
                    INSERT OR REPLACE INTO active_symbols (symbol, last_seen)
                    VALUES (?, ?)
                    """,
                    (symbol, timestamp),
                )
                await self.db.conn.commit()
            except Exception as e:
                logger.debug(f"캐시 저장 실패 [{symbol}]: {e}")
