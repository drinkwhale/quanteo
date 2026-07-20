"""LeverageInverseStrategy 상태머신 테스트.

지표 계산(DEMA·CCI·Stochastic)은 core/strategy/indicators/*.py에서 이미 단위
테스트로 검증했으므로, 여기서는 상태 전이 로직(진입 3-of-3 → 보유 → 1차 경고
→ 2차 확정청산 → 관망 복귀)을 합성 지표값으로 직접 검증한다. 이는
tests/strategy/plugins/test_cci_bbc_strategy.py가 TimeframeState를 합성해
전략 로직을 검증하는 것과 동일한 방식이다.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

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


class TestConstructorValidation:
    def test_qty_per_unit_1미만이면_예외(self) -> None:
        with pytest.raises(ValueError):
            LeverageInverseStrategy(
                underlying_symbol=_UNDERLYING,
                long_symbol=_LONG,
                short_symbol=_SHORT,
                qty_per_unit=0,
            )

    def test_qty_per_unit_음수면_예외(self) -> None:
        with pytest.raises(ValueError):
            LeverageInverseStrategy(
                underlying_symbol=_UNDERLYING,
                long_symbol=_LONG,
                short_symbol=_SHORT,
                qty_per_unit=-5,
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

    def test_경고_없이_데드크로스만_발생하면_부분청산_안함(self) -> None:
        """CCI가 150 이상을 찍은 적 없는 상태에서 데드크로스만 발생하면 무시해야 한다."""
        strategy = _make_strategy()
        strategy._phase = Phase.LEVERAGE_HOLDING
        strategy._position_qty = 10

        candles = [_candle(200.0), _candle(200.0), _candle(200.0)]

        signal = strategy._manage_leverage_position(
            _tick(),
            candles,
            dema=[100.0, 101.0, 102.0],
            cci=[100.0, 80.0],  # 데드크로스는 발생하지만 150 도달 이력 없음
            cci_signal=[90.0, 90.0],
            stoch_d=[50.0],
        )

        assert signal is None
        assert strategy._leverage_overbought_seen is False
        assert strategy.phase == Phase.LEVERAGE_HOLDING
        assert strategy.position_qty == 10

    def test_PARTIAL_상태에서_확정조건_충족시_잔량_전량청산(self) -> None:
        strategy = _make_strategy()
        strategy._phase = Phase.LEVERAGE_PARTIAL
        strategy._position_qty = 6  # 1차 부분 익절 이후 남은 잔량

        dema = [102.0, 101.0, 99.0]
        cci = [10.0, -10.0]
        cci_signal = [0.0, 0.0]
        candles = [_candle(120.0), _candle(110.0), _candle(90.0)]

        signal = strategy._manage_leverage_position(
            _tick(), candles, dema, cci, cci_signal, stoch_d=[50.0]
        )

        assert signal is not None
        assert signal.side == SignalSide.SELL
        assert signal.symbol == _LONG
        assert signal.qty == 6
        assert strategy.phase == Phase.WATCHING
        assert strategy.position_qty == 0


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

    def test_경고_없이_골든크로스만_발생하면_부분청산_안함(self) -> None:
        """CCI가 -150 이하를 찍은 적 없는 상태에서 골든크로스만 발생하면 무시해야 한다."""
        strategy = _make_strategy()
        strategy._phase = Phase.INVERSE_HOLDING
        strategy._position_qty = 10

        candles = [_candle(50.0), _candle(50.0), _candle(50.0)]

        signal = strategy._manage_inverse_position(
            _tick(),
            candles,
            dema=[100.0, 99.0, 98.0],
            cci=[-100.0, -80.0],  # 골든크로스는 발생하지만 -150 도달 이력 없음
            cci_signal=[-90.0, -90.0],
            stoch_d=[50.0],
        )

        assert signal is None
        assert strategy._inverse_oversold_seen is False
        assert strategy.phase == Phase.INVERSE_HOLDING
        assert strategy.position_qty == 10

    def test_PARTIAL_상태에서_확정조건_충족시_잔량_전량청산(self) -> None:
        strategy = _make_strategy()
        strategy._phase = Phase.INVERSE_PARTIAL
        strategy._position_qty = 6

        dema = [98.0, 99.0, 101.0]
        cci = [-10.0, 10.0]
        cci_signal = [0.0, 0.0]
        candles = [_candle(80.0), _candle(90.0), _candle(110.0)]

        signal = strategy._manage_inverse_position(
            _tick(), candles, dema, cci, cci_signal, stoch_d=[50.0]
        )

        assert signal is not None
        assert signal.side == SignalSide.SELL
        assert signal.symbol == _SHORT
        assert signal.qty == 6
        assert strategy.phase == Phase.WATCHING
        assert strategy.position_qty == 0


class TestEndToEndOnTick:
    """실제 캔들 시퀀스로 on_tick() → _compute_indicators() → 상태머신 전체 경로를 검증한다.

    개별 조건 판정 로직은 test_leverage_inverse_conditions.py에서 이미 검증했으므로,
    여기서는 합성 지표 배열이 아니라 실제 DEMA/CCI/Stochastic 계산 결과가 상태머신과
    올바르게 맞물려 시그널까지 이어지는지 확인하는 데 집중한다.

    130봉 평탄 구간(지표 워밍업)에 이은 단일 급등/급락 봉으로 3-of-3 조건이 동시에
    충족되는 지점을 만든다 — uv run python으로 사전에 수치 시뮬레이션해 확정한 값이다.
    """

    _FLAT_N = 130

    def _flat_then_jump(self, jump: float) -> list[Candle]:
        candles = [_candle(100.0) for _ in range(self._FLAT_N)]
        candles.append(_candle(100.0 + jump))
        return candles

    def _run_until_signal(self, strategy: LeverageInverseStrategy, candles: list[Candle]):
        strategy.warmup(candles[: self._FLAT_N])
        signal = None
        for idx in range(self._FLAT_N, len(candles)):
            window = tuple(candles[: idx + 1])
            ctx = MarketContext(symbol=_UNDERLYING, recent_candles=window)
            signal = strategy.on_tick(_tick(price=candles[idx].close), ctx)
            if signal is not None:
                break
        return signal

    def test_레버리지_진입_실제_지표_계산_경로(self) -> None:
        strategy = _make_strategy()
        candles = self._flat_then_jump(jump=2.0)

        signal = self._run_until_signal(strategy, candles)

        assert signal is not None
        assert signal.side == SignalSide.BUY
        assert signal.symbol == _LONG
        assert strategy.phase == Phase.LEVERAGE_HOLDING
        assert strategy.position_qty == 10

    def test_인버스_진입_실제_지표_계산_경로(self) -> None:
        strategy = _make_strategy()
        candles = self._flat_then_jump(jump=-2.0)

        signal = self._run_until_signal(strategy, candles)

        assert signal is not None
        assert signal.side == SignalSide.BUY
        assert signal.symbol == _SHORT
        assert strategy.phase == Phase.INVERSE_HOLDING
        assert strategy.position_qty == 10
