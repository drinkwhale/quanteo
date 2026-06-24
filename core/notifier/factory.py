"""
Notifier 팩토리.

Settings.telegram.enabled 값에 따라 TelegramNotifier 또는 MockNotifier를 반환한다.
"""

from __future__ import annotations

import logging

from core.config.settings import Settings
from core.notifier.base import Notifier, NotifyLevel
from core.notifier.mock import MockNotifier
from core.notifier.telegram import TelegramNotifier

logger = logging.getLogger(__name__)


def make_notifier(settings: Settings) -> Notifier:
    """설정에 따라 적절한 Notifier를 생성한다.

    telegram.enabled가 True이면 TelegramNotifier를 반환한다.
    그렇지 않으면 MockNotifier를 반환해 운영 중 불필요한 API 호출을 방지한다.

    Args:
        settings: load_settings()로 로드된 Settings 인스턴스.

    Returns:
        Notifier Protocol을 만족하는 구현체.
    """
    tg = settings.telegram

    if tg.enabled:
        bot_token = tg.bot_token.get_secret_value()
        if not bot_token or not tg.chat_id:
            logger.warning(
                "telegram.enabled=true이지만 bot_token/chat_id가 비어 있어 MockNotifier로 대체합니다."
            )
            return MockNotifier()

        # "WARN"은 설정 파일에서 흔히 쓰는 별칭 → "WARNING"으로 정규화
        _ALIASES: dict[str, str] = {"WARN": "WARNING"}
        raw_level = _ALIASES.get(tg.level.upper(), tg.level.upper())
        try:
            min_level = NotifyLevel(raw_level)
        except ValueError:
            logger.warning("알 수 없는 telegram.level=%r — INFO로 대체합니다.", tg.level)
            min_level = NotifyLevel.INFO

        logger.info("TelegramNotifier 생성 (chat_id=%s level=%s)", tg.chat_id, min_level)
        return TelegramNotifier(
            bot_token=bot_token,
            chat_id=tg.chat_id,
            min_level=min_level,
        )

    logger.info("Telegram 비활성화 — MockNotifier 사용")
    return MockNotifier()
