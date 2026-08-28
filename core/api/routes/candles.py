"""GET /candles — 캔들 차트 데이터 조회."""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from core.api.deps import ContainerDep
from core.api.models import CandleItem, CandleList

logger = logging.getLogger(__name__)
router = APIRouter()

# 심볼 형식 검증: 영문+숫자+하이픈, 1-20자
SYMBOL_PATTERN = re.compile(r"^[A-Za-z0-9\-]{1,20}$")


def _validate_symbol(symbol: str) -> str:
    """심볼 검증 및 정규화.

    Args:
        symbol: 종목 심볼 (예: 005930, AAPL)

    Returns:
        정규화된 심볼 (공백 제거, 상한 유지)

    Raises:
        ValueError: 심볼 형식 불일치
    """
    symbol = symbol.strip()
    if not symbol:
        raise ValueError("심볼은 비어있을 수 없습니다.")
    if not SYMBOL_PATTERN.match(symbol):
        raise ValueError(
            f"심볼 형식이 유효하지 않습니다 (영문·숫자·하이픈만, 1-20자): {symbol!r}"
        )
    return symbol


def _validate_before(before: str | None) -> str | None:
    """before 날짜 형식 검증.

    ISO 8601 형식(예: 2024-01-15T14:30:00Z, 2024-01-15)을 검증한다.

    Args:
        before: ISO 8601 형식 날짜 문자열

    Returns:
        검증된 before 값

    Raises:
        ValueError: 날짜 형식 불일치
    """
    if before is None:
        return None

    before = before.strip()
    if not before:
        raise ValueError("before 값이 비어있을 수 없습니다.")

    # ISO 8601 형식 검증: YYYY-MM-DD 또는 YYYY-MM-DDTHH:MM:SS[.fff][Z/±HH:MM]
    # URL 인코딩에서 + 또는 공백이 올 수 있으므로 더 관대하게 패턴 작성
    iso_pattern = re.compile(
        r"^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}:\d{2}(\.\d{1,6})?(Z|[\+\-\s]\d{2}:\d{2})?)?$"
    )
    if not iso_pattern.match(before):
        raise ValueError(
            f"before 형식이 유효하지 않습니다 (ISO 8601 필수): {before!r}"
        )

    # 파싱 시도 — 형식은 맞지만 날짜값이 유효하지 않은 경우 감지
    # URL 인코딩된 공백을 + 로 복구
    before_normalized = before.replace(" ", "+")
    try:
        datetime.fromisoformat(before_normalized.replace("Z", "+00:00"))
    except ValueError as e:
        raise ValueError(f"before 날짜값이 유효하지 않습니다: {before!r} — {str(e)}")

    return before


@router.get("/candles", response_model=CandleList, summary="캔들 데이터 조회")
async def get_candles(
    container: ContainerDep,
    symbol: str = Query(..., description="종목 심볼 (예: 005930, AAPL)"),
    interval: Literal["1m", "1d"] = Query("1d", description="캔들 간격 (1분봉: 1m, 일봉: 1d)"),
    count: int = Query(100, ge=1, le=200, description="조회할 캔들 수 (1~200)"),
    before: str | None = Query(None, description="조회 기준 일시 (ISO 8601, 선택)"),
    adjusted: bool = Query(True, description="수정주가 여부"),
) -> CandleList:
    """캔들 차트 데이터를 조회한다.

    Toss API `GET /api/v1/candles`의 프록시 엔드포인트로, 지정된 종목의 OHLCV 데이터를 반환한다.
    현재 지원하는 interval은 1분봉(1m)과 일봉(1d)이다.

    입력값 검증:
    - symbol: 영문·숫자·하이픈만, 1-20자
    - interval: 1m 또는 1d (FastAPI 자동 검증)
    - count: 1-200 (FastAPI 자동 검증)
    - before: ISO 8601 형식 (수동 검증)
    - adjusted: boolean (자동 변환)

    Args:
        symbol: 종목 심볼 (예: 005930, AAPL)
        interval: 캔들 간격 (1m=1분봉, 1d=일봉)
        count: 조회할 캔들 수 (1~200, 기본 100)
        before: 조회 기준 일시 (ISO 8601 형식, 선택)
        adjusted: 수정주가 여부 (기본 True)

    Raises:
        HTTPException(400): 입력값 검증 실패
        HTTPException(503): 브로커 어댑터가 초기화되지 않았을 때
        HTTPException(502): 어댑터가 캔들 조회에 실패했을 때 또는 API 응답 구조 오류

    Returns:
        CandleList: 캔들 데이터 목록
    """
    # =========================================================================
    # 1. 입력값 검증 및 정규화
    # =========================================================================
    try:
        symbol = _validate_symbol(symbol)
        logger.debug(f"심볼 검증 완료: {symbol!r}")
    except ValueError as e:
        logger.warning(f"심볼 검증 실패: {str(e)}")
        raise HTTPException(
            status_code=400,
            detail=f"심볼 검증 실패: {str(e)}",
        ) from e

    try:
        before = _validate_before(before)
        if before:
            logger.debug(f"before 날짜 검증 완료: {before!r}")
    except ValueError as e:
        logger.warning(f"before 날짜 검증 실패: {str(e)}")
        raise HTTPException(
            status_code=400,
            detail=f"before 날짜 검증 실패: {str(e)}",
        ) from e

    logger.debug(
        f"캔들 조회 요청: symbol={symbol!r}, interval={interval!r}, "
        f"count={count}, before={before!r}, adjusted={adjusted}"
    )

    # =========================================================================
    # 2. 브로커 초기화 확인
    # =========================================================================
    broker = container.broker
    if broker is None:
        logger.error("브로커 어댑터가 초기화되지 않음")
        raise HTTPException(
            status_code=503,
            detail="브로커 어댑터가 초기화되지 않았습니다.",
        )

    # =========================================================================
    # 3. 캔들 데이터 조회 (세분화된 예외처리)
    # =========================================================================
    try:
        candles = await broker.get_candles(
            symbol=symbol,
            interval=interval,
            count=count,
            before=before,
            adjusted=adjusted,
        )

        # 응답 검증: 리스트여야 함
        if not isinstance(candles, list):
            logger.error(
                f"캔들 조회 응답 타입 오류: {type(candles).__name__} "
                f"(symbol={symbol!r}, 리스트여야 함)"
            )
            raise HTTPException(
                status_code=502,
                detail="캔들 조회 응답 형식이 유효하지 않습니다.",
            )

        # 캔들 객체 변환 (응답 구조 검증 포함)
        items = []
        for idx, c in enumerate(candles):
            try:
                item = CandleItem(
                    timestamp=c.timestamp,
                    open=float(c.open_price),
                    high=float(c.high_price),
                    low=float(c.low_price),
                    close=float(c.close_price),
                    volume=float(c.volume),
                )
                items.append(item)
            except (AttributeError, TypeError, ValueError) as e:
                logger.error(
                    f"캔들 변환 오류: idx={idx}, candle={c!r}, "
                    f"error={type(e).__name__}: {str(e)}"
                )
                raise HTTPException(
                    status_code=502,
                    detail=f"캔들 데이터 변환 중 오류 (index {idx}): {type(e).__name__}",
                ) from e

        logger.info(
            f"캔들 조회 성공: symbol={symbol!r}, interval={interval!r}, "
            f"count={len(items)}, before={before!r}"
        )
        return CandleList(items=items)

    except HTTPException:
        # HTTPException은 이미 처리됨 — 그대로 전파
        raise

    except (ValueError, RuntimeError) as e:
        # API 응답 구조 오류, 데이터 검증 실패
        logger.error(
            f"캔들 조회 API 오류: {type(e).__name__}: {str(e)} "
            f"(symbol={symbol!r}, interval={interval!r})"
        )
        raise HTTPException(
            status_code=502,
            detail=f"캔들 조회 중 오류: {type(e).__name__}",
        ) from e

    except (ConnectionError, TimeoutError) as e:
        # 네트워크 오류
        logger.error(
            f"캔들 조회 연결 오류: {type(e).__name__}: {str(e)} "
            f"(symbol={symbol!r})"
        )
        raise HTTPException(
            status_code=502,
            detail="시세 서버와의 연결이 실패했습니다. 잠시 후 다시 시도하세요.",
        ) from e

    except Exception as e:
        # 예기치 못한 예외
        logger.exception(
            f"캔들 조회 예상 오류: {type(e).__name__}: {str(e)} "
            f"(symbol={symbol!r}, interval={interval!r})"
        )
        raise HTTPException(
            status_code=502,
            detail="캔들 조회 중 예상 오류가 발생했습니다.",
        ) from e
