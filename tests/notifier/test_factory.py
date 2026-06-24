"""T038 — make_notifier() 팩토리 테스트."""

from __future__ import annotations

from unittest.mock import MagicMock

from core.config.settings import TelegramConfig
from core.notifier.factory import make_notifier
from core.notifier.mock import MockNotifier
from core.notifier.telegram import TelegramNotifier

# aiogram은 "{숫자}:{문자열}" 형식의 토큰만 허용한다.
_FAKE_TOKEN = "123456789:AABBCCDDaabbccdd11223344"


def _settings(enabled: bool, bot_token: str = _FAKE_TOKEN, chat_id: str = "-100123", level: str = "INFO") -> MagicMock:
    """Settings 모의 객체를 만든다."""
    tg = TelegramConfig(bot_token=bot_token, chat_id=chat_id, level=level, enabled=enabled)
    settings = MagicMock()
    settings.telegram = tg
    return settings


def test_disabled_returns_mock():
    notifier = make_notifier(_settings(enabled=False))
    assert isinstance(notifier, MockNotifier)


def test_enabled_returns_telegram():
    notifier = make_notifier(_settings(enabled=True, chat_id="-100123"))
    assert isinstance(notifier, TelegramNotifier)


def test_enabled_but_empty_token_falls_back_to_mock():
    notifier = make_notifier(_settings(enabled=True, bot_token="", chat_id="-100123"))
    assert isinstance(notifier, MockNotifier)


def test_enabled_but_empty_chat_id_falls_back_to_mock():
    notifier = make_notifier(_settings(enabled=True, bot_token="tok", chat_id=""))
    assert isinstance(notifier, MockNotifier)


def test_invalid_level_defaults_to_info():
    from core.notifier.base import NotifyLevel
    notifier = make_notifier(_settings(enabled=True, chat_id="-100", level="INVALID"))
    assert isinstance(notifier, TelegramNotifier)
    assert notifier._min_level == NotifyLevel.INFO


def test_level_propagated_to_telegram():
    from core.notifier.base import NotifyLevel
    notifier = make_notifier(_settings(enabled=True, chat_id="-100", level="ERROR"))
    assert isinstance(notifier, TelegramNotifier)
    assert notifier._min_level == NotifyLevel.ERROR


def test_warn_alias_resolves_to_warning():
    """'WARN'은 설정 파일에서 흔히 쓰는 별칭 — WARNING으로 해석되어야 한다."""
    from core.notifier.base import NotifyLevel
    notifier = make_notifier(_settings(enabled=True, chat_id="-100", level="WARN"))
    assert isinstance(notifier, TelegramNotifier)
    assert notifier._min_level == NotifyLevel.WARNING
