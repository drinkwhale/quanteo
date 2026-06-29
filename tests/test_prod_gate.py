"""트레이딩 게이트 안전 테스트.

Toss증권은 항상 실제 자금을 사용하므로 --with-trading 시 반드시
--i-understand-real-money 플래그가 필요하다.
"""

from __future__ import annotations

import pytest

from core.app import TradingGateError, _check_trading_gate


def test_no_trading_without_flag_passes():
    """트레이딩 없이 Control API만 시작할 때는 플래그 불필요."""
    _check_trading_gate(with_trading=False, confirmed=False)  # 예외 없음


def test_no_trading_with_flag_passes():
    """트레이딩 없이 Control API만 시작할 때 플래그가 있어도 무방."""
    _check_trading_gate(with_trading=False, confirmed=True)  # 예외 없음


def test_trading_without_flag_raises():
    """--with-trading 에 --i-understand-real-money 없으면 TradingGateError."""
    with pytest.raises(TradingGateError, match="트레이딩 시작 차단"):
        _check_trading_gate(with_trading=True, confirmed=False)


def test_trading_with_flag_passes():
    """--with-trading + --i-understand-real-money 이면 통과."""
    _check_trading_gate(with_trading=True, confirmed=True)  # 예외 없음


def test_gate_error_message_contains_instruction():
    """에러 메시지에 올바른 플래그 사용법이 포함되어야 한다."""
    with pytest.raises(TradingGateError) as exc_info:
        _check_trading_gate(with_trading=True, confirmed=False)

    msg = str(exc_info.value)
    assert "--i-understand-real-money" in msg
    assert "--with-trading" in msg


@pytest.mark.asyncio
async def test_run_rejects_trading_without_flag():
    """run(with_trading=True, confirmed=False) 시 TradingGateError 발생."""
    from core.app import run

    with pytest.raises(TradingGateError):
        await run(with_trading=True, confirmed=False)


@pytest.mark.asyncio
async def test_run_with_confirmed_passes_gate():
    """run(with_trading=True, confirmed=True) 이면 게이트 통과 후 다음 단계 진입."""
    from pathlib import Path

    from core.app import run

    with pytest.raises(Exception) as exc_info:
        await run(
            with_trading=True,
            confirmed=True,
            config_path=Path("/nonexistent/quanteo.yaml"),
        )

    assert not isinstance(exc_info.value, TradingGateError)
