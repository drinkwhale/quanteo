"""prod 실전 게이트 안전 테스트.

아키텍처 설계서 7항 '안전 설계' 요구사항:
- prod 전환은 설정 파일 + 실행 시 명시 플래그(--i-understand-real-money) 이중 확인.
- 플래그 없이 prod 환경으로는 절대 진입되지 않아야 한다.
"""

from __future__ import annotations

import pytest

from core.app import ProdGateError, _check_prod_gate
from core.config.settings import Env


# ---------------------------------------------------------------------------
# 핵심 게이트 함수
# ---------------------------------------------------------------------------


def test_vps_without_flag_passes():
    """VPS 환경은 확인 플래그 없어도 통과."""
    _check_prod_gate(Env.VPS, prod_confirmed=False)  # 예외 없음


def test_vps_with_flag_passes():
    """VPS 환경은 플래그가 있어도 통과."""
    _check_prod_gate(Env.VPS, prod_confirmed=True)  # 예외 없음


def test_prod_without_flag_raises():
    """prod 환경에서 확인 플래그 없으면 ProdGateError 발생."""
    with pytest.raises(ProdGateError, match="실전.*prod.*환경 진입 차단"):
        _check_prod_gate(Env.PROD, prod_confirmed=False)


def test_prod_with_flag_passes():
    """prod 환경에서도 확인 플래그가 있으면 통과."""
    _check_prod_gate(Env.PROD, prod_confirmed=True)  # 예외 없음


def test_prod_gate_error_message_contains_instruction():
    """에러 메시지에 올바른 플래그 사용법이 포함되어야 한다."""
    with pytest.raises(ProdGateError) as exc_info:
        _check_prod_gate(Env.PROD, prod_confirmed=False)

    msg = str(exc_info.value)
    assert "--i-understand-real-money" in msg
    assert "--env prod" in msg


# ---------------------------------------------------------------------------
# run() 함수 레벨 게이트 검증
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_rejects_prod_without_flag():
    """run()에 prod + prod_confirmed=False 전달 시 ProdGateError 발생.

    settings 파일 없어도 게이트가 먼저 동작해야 한다.
    """
    from core.app import run
    from core.config.settings import Env

    with pytest.raises(ProdGateError):
        await run(env=Env.PROD, prod_confirmed=False)


@pytest.mark.asyncio
async def test_run_blocks_prod_before_settings_load():
    """prod 게이트는 설정 파일 로딩보다 먼저 실행된다.

    설정 파일(kis_devlp.yaml)이 없어도 ProdGateError가 먼저 발생해야 한다.
    (FileNotFoundError가 발생하면 게이트가 너무 늦게 동작하는 것.)
    """
    from core.app import run
    from pathlib import Path

    with pytest.raises(ProdGateError):
        await run(
            env=Env.PROD,
            prod_confirmed=False,
            config_path=Path("/nonexistent/path/kis_devlp.yaml"),
        )
