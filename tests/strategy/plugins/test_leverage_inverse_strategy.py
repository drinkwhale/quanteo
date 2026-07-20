"""LeverageInverseStrategy 상태머신 테스트.

지표 계산(DEMA·CCI·Stochastic)은 core/strategy/indicators/*.py에서 이미 단위
테스트로 검증했으므로, 여기서는 상태 전이 로직(진입 3-of-3 → 보유 → 1차 경고
→ 2차 확정청산 → 관망 복귀)을 합성 지표값으로 직접 검증한다. 이는
tests/strategy/plugins/test_cci_bbc_strategy.py가 TimeframeState를 합성해
전략 로직을 검증하는 것과 동일한 방식이다.
"""

from __future__ import annotations

from datetime import UTC, datetime

from core.marketdata.models import Candle, Tick
from core.strategy.base import MarketContext, SignalSide
from core.strategy.plugins.leverage_inverse_strategy import LeverageInverseStrategy, Phase

_UNDERLYING = "000660"
_LONG = "LEVERAGE_ETF"
_SHORT = "INVERSE_ETF"


def _candle(close: float, high: float | None = None, low: float | None = None) -> Candle:
    return Candle(
        symbol=_UNDERLYING,
        open=close,
        high=high if high is not None else close + 1.0,
        low=low if low is not None else close - 1.0,
        close=close,
        volume=1000,
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        market="domestic",
    )


def _tick(price: float = 100.0, symbol: str = _UNDERLYING) -> Tick:
    return Tick(
        symbol=symbol,
        price=price,
        volume=1000,
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        market="domestic",
    )


def _make_strategy() -> LeverageInverseStrategy:
    return LeverageInverseStrategy(
        underlying_symbol=_UNDERLYING,
        long_symbol=_LONG,
        short_symbol=_SHORT,
        qty_per_unit=10,
    )


class TestOnTickGating:
    def test_대상_심볼이_아니면_None(self) -> None:
        strategy = _make_strategy()
        ctx = MarketContext(symbol="OTHER", recent_candles=())
        result = strategy.on_tick(_tick(symbol="OTHER"), ctx)
        assert result is None

    def test_캔들_부족시_None(self) -> None:
        strategy = _make_strategy()
        ctx = MarketContext(symbol=_UNDERLYING, recent_candles=(_candle(100.0),))
        result = strategy.on_tick(_tick(), ctx)
        assert result is None
        assert strategy.phase == Phase.WATCHING

    def test_지표_워밍업_부족시_None(self) -> None:
        strategy = _make_strategy()
        candles = tuple(_candle(100.0 + i * 0.1) for i in range(10))
        ctx = MarketContext(symbol=_UNDERLYING, recent_candles=candles)
        result = strategy.on_tick(_tick(), ctx)
        assert result is None


class TestWarmup:
    def test_기초자산_심볼만_필터링(self) -> None:
        strategy = _make_strategy()
        history = [
            _candle(100.0),
            Candle(
                symbol="OTHER",
                open=1,
                high=2,
                low=0,
                close=1,
                volume=1,
                timestamp=datetime(2026, 1, 1, tzinfo=UTC),
                market="domestic",
            ),
        ]
        strategy.warmup(history)
        assert len(strategy._candle_history) == 1
        assert strategy._candle_history[0].symbol == _UNDERLYING


class TestEntries:
    def test_레버리지_3of3_충족시_BUY_시그널(self) -> None:
        strategy = _make_strategy()
        dema = [100.0, 101.0, 103.0]
        cci = [-5.0, 5.0]
        cci_signal = [0.0, 0.0]
        candles = [_candle(90.0), _candle(95.0), _candle(104.0)]
        stoch_d = [50.0]

        signal = strategy._try_entries(_tick(), candles, dema, cci, cci_signal, stoch_d)

        assert signal is not None
        assert signal.side == SignalSide.BUY
        assert signal.symbol == _LONG
        assert signal.qty == 10
        assert strategy.phase == Phase.LEVERAGE_HOLDING
        assert strategy.position_qty == 10

    def test_인버스_3of3_충족시_BUY_시그널(self) -> None:
        strategy = _make_strategy()
        dema = [100.0, 99.0, 97.0]
        cci = [5.0, -5.0]
        cci_signal = [0.0, 0.0]
        candles = [_candle(110.0), _candle(105.0), _candle(96.0)]
        stoch_d = [50.0]

        signal = strategy._try_entries(_tick(), candles, dema, cci, cci_signal, stoch_d)

        assert signal is not None
        assert signal.side == SignalSide.BUY
        assert signal.symbol == _SHORT
        assert strategy.phase == Phase.INVERSE_HOLDING

    def test_조건_미충족시_None_watching_유지(self) -> None:
        strategy = _make_strategy()
        dema = [100.0, 100.0, 100.0]
        cci = [0.0, 0.0]
        cci_signal = [0.0, 0.0]
        candles = [_candle(100.0), _candle(100.0), _candle(100.0)]
        stoch_d = [50.0]

        signal = strategy._try_entries(_tick(), candles, dema, cci, cci_signal, stoch_d)

        assert signal is None
        assert strategy.phase == Phase.WATCHING


class TestLeverageExit:
    def test_2개_이상_조건_충족시_전량_청산(self) -> None:
        strategy = _make_strategy()
        strategy._phase = Phase.LEVERAGE_HOLDING
        strategy._position_qty = 10

        dema = [102.0, 101.0, 99.0]  # 기울기 하향 전환
        cci = [10.0, -10.0]  # 0선 이탈
        cci_signal = [0.0, 0.0]
        candles = [_candle(120.0), _candle(110.0), _candle(90.0)]  # 저점 이탈 + DEMA 하회

        signal = strategy._manage_leverage_position(
            _tick(), candles, dema, cci, cci_signal, stoch_d=[50.0]
        )

        assert signal is not None
        assert signal.side == SignalSide.SELL
        assert signal.symbol == _LONG
        assert signal.qty == 10
        assert strategy.phase == Phase.WATCHING
        assert strategy.position_qty == 0

    def test_1차_경고_후_부분_익절(self) -> None:
        strategy = _make_strategy()
        strategy._phase = Phase.LEVERAGE_HOLDING
        strategy._position_qty = 10

        candles = [_candle(200.0), _candle(200.0), _candle(200.0)]

        # 1콜: CCI 과열(>=150) 관측, 아직 데드크로스 없음 → 상태만 세팅
        first = strategy._manage_leverage_position(
            _tick(),
            candles,
            dema=[100.0, 101.0, 102.0],
            cci=[160.0, 158.0],
            cci_signal=[140.0, 145.0],
            stoch_d=[50.0],
        )
        assert first is None
        assert strategy._leverage_overbought_seen is True
        assert strategy.phase == Phase.LEVERAGE_HOLDING

        # 2콜: Signal 데드크로스 발생 → 1차 경고(부분 익절)
        second = strategy._manage_leverage_position(
            _tick(),
            candles,
            dema=[101.0, 102.0, 103.0],
            cci=[158.0, 140.0],
            cci_signal=[140.0, 150.0],
            stoch_d=[50.0],
        )

        assert second is not None
        assert second.side == SignalSide.SELL
        assert second.symbol == _LONG
        assert second.qty == 4  # round(10 * 0.4)
        assert strategy.phase == Phase.LEVERAGE_PARTIAL
        assert strategy.position_qty == 6


class TestInverseExit:
    def test_2개_이상_조건_충족시_전량_청산(self) -> None:
        strategy = _make_strategy()
        strategy._phase = Phase.INVERSE_HOLDING
        strategy._position_qty = 10

        dema = [98.0, 99.0, 101.0]  # 기울기 우상향 전환
        cci = [-10.0, 10.0]  # 0선 상향 돌파
        cci_signal = [0.0, 0.0]
        candles = [_candle(80.0), _candle(90.0), _candle(110.0)]  # 고점 갱신 + DEMA 상회

        signal = strategy._manage_inverse_position(
            _tick(), candles, dema, cci, cci_signal, stoch_d=[50.0]
        )

        assert signal is not None
        assert signal.side == SignalSide.SELL
        assert signal.symbol == _SHORT
        assert signal.qty == 10
        assert strategy.phase == Phase.WATCHING
        assert "저점신뢰도" in signal.reason

    def test_1차_경고_후_부분_익절(self) -> None:
        strategy = _make_strategy()
        strategy._phase = Phase.INVERSE_HOLDING
        strategy._position_qty = 10

        candles = [_candle(50.0), _candle(50.0), _candle(50.0)]

        first = strategy._manage_inverse_position(
            _tick(),
            candles,
            dema=[100.0, 99.0, 98.0],
            cci=[-160.0, -158.0],
            cci_signal=[-140.0, -145.0],
            stoch_d=[50.0],
        )
        assert first is None
        assert strategy._inverse_oversold_seen is True

        second = strategy._manage_inverse_position(
            _tick(),
            candles,
            dema=[99.0, 98.0, 97.0],
            cci=[-158.0, -140.0],
            cci_signal=[-140.0, -150.0],
            stoch_d=[50.0],
        )

        assert second is not None
        assert second.side == SignalSide.SELL
        assert second.symbol == _SHORT
        assert second.qty == 4
        assert strategy.phase == Phase.INVERSE_PARTIAL
        assert strategy.position_qty == 6
