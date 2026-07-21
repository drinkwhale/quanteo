"""박병창 매수 3원칙 기반 매수 타이밍 판정 — Stock Miner 리포트용.

Screener/Scorer와 동일하게 결정론적 계산이다(LLM 미사용). 라이브 트레이딩 엔진의
core.strategy.plugins.bbc_buy.evaluate_buy()를 그대로 재사용해 배치(일봉) 분석에서도
같은 판정 로직을 쓴다 — 라이브/배치 두 시스템 간 시그널 불일치를 피하기 위함
(core.strategy.* 는 core.execution/core.adapters를 import하지 않는 순수 지표
모듈이라 screener/의 "매매 코어 미연동" 경계를 넘지 않는다).

일봉 기준 평가라 evaluate_buy()의 오전(10시 이전)/오후(14시 이후) 분기 중 항상
"오후"로 고정한다(current_time=18:30, 장 마감 후 실행). 제1원칙 오후 조건
(price>ma5 & 거래량 급증)과 제2/3원칙은 일봉 지표만으로 판정 가능해 문제없지만,
제1원칙 오전 전용 조건("시가 아래 하락 후 재돌파")은 장중 가격 경로가 필요해
일봉 데이터로는 재현 불가 — 이 배치 평가에서는 자연히 오후 분기로만 판정된다.
"""

from __future__ import annotations

from datetime import datetime as dt
from datetime import time

import pandas as pd

from core.marketdata.models import Candle
from core.strategy.indicators.ma import calculate_sma
from core.strategy.plugins.bbc_buy import BbcBuySignal, evaluate_buy

_EOD_TIME = time(18, 30)
# ma20 계산 + 제2원칙의 최근 20봉 peak_volume 참조에 필요한 최소 캔들 수
_MIN_CANDLES = 21


def candles_from_history(df: pd.DataFrame, ticker: str) -> list[Candle]:
    """pykrx 일봉 히스토리(오래된→최신 정렬)를 Candle 리스트로 변환한다.

    Args:
        df: columns 시가/고가/저가/종가/거래량, index는 날짜(datetime64 또는
            YYYYMMDD 문자열) — PykrxClient.fetch_ohlcv_history() 출력.
        ticker: 종목코드.

    Returns:
        Candle 리스트 (오래된 것부터 최신 순). df가 비어있으면 빈 리스트.
    """
    candles: list[Candle] = []
    for idx, row in df.iterrows():
        timestamp = idx.to_pydatetime() if hasattr(idx, "to_pydatetime") else dt.strptime(str(idx), "%Y%m%d")
        candles.append(
            Candle(
                symbol=ticker,
                open=float(row["시가"]),
                high=float(row["고가"]),
                low=float(row["저가"]),
                close=float(row["종가"]),
                volume=int(row["거래량"]),
                timestamp=timestamp,
                market="domestic",
                interval="1d",
            )
        )
    return candles


def assess_buy_principle(candles: list[Candle]) -> BbcBuySignal | None:
    """최근 일봉 히스토리로 매수 3원칙을 평가한다.

    Args:
        candles: 오래된 것부터 최신 순 Candle 리스트.

    Returns:
        가장 먼저 충족된 BbcBuySignal, 없으면 None. 캔들 수가 부족(< 21)하면
        None(판정 불가).
    """
    if len(candles) < _MIN_CANDLES:
        return None

    closes = [c.close for c in candles]
    volumes = [float(c.volume) for c in candles]
    ma5_series = calculate_sma(closes, 5)
    ma20_series = calculate_sma(closes, 20)
    volume_ma20_series = calculate_sma(volumes, 20)
    if not ma5_series or not ma20_series or not volume_ma20_series:
        return None

    latest = candles[-1]
    return evaluate_buy(
        current_price=latest.close,
        ma5=ma5_series[-1],
        ma20=ma20_series[-1],
        current_volume=latest.volume,
        volume_ma20=volume_ma20_series[-1],
        candles=candles,
        current_time=_EOD_TIME,
        current_open=latest.open,
    )
