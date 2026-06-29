"""
설정 로딩 모듈.

quanteo.yaml을 읽어 Toss 자격증명 및 Telegram 설정을 제공한다.
기본 경로: ~/quanteo/config/quanteo.yaml
환경 변수 QUANTEO_CONFIG_PATH 로 재지정 가능.
"""

from __future__ import annotations

import os
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, SecretStr


class Market(StrEnum):
    """대상 시장."""

    DOMESTIC = "domestic"
    OVERSEAS = "overseas"


class TossCredentials(BaseModel):
    """Toss증권 OAuth2 자격증명."""

    client_id: str
    client_secret: SecretStr


class TelegramConfig(BaseModel):
    """Telegram 알림 설정."""

    bot_token: SecretStr = SecretStr("")
    chat_id: str = ""
    level: str = "INFO"
    enabled: bool = False


class Settings(BaseModel):
    """quanteo 전체 설정."""

    market: Market = Market.DOMESTIC
    credentials: TossCredentials
    telegram: TelegramConfig = TelegramConfig()


_DEFAULT_CONFIG_PATH = Path.home() / "quanteo" / "config" / "quanteo.yaml"


def load_settings(
    market: Market = Market.DOMESTIC,
    config_path: Path | None = None,
) -> Settings:
    """quanteo.yaml을 읽어 Settings를 반환한다.

    Args:
        market: 대상 시장. 기본값 DOMESTIC.
        config_path: 설정 파일 경로.
            기본값: ~/quanteo/config/quanteo.yaml.
            환경 변수 QUANTEO_CONFIG_PATH 로 재지정 가능.

    Raises:
        FileNotFoundError: 설정 파일을 찾을 수 없을 때.
        ValueError: 필수 자격증명 필드가 누락되었을 때.
    """
    path = config_path or Path(
        os.environ.get("QUANTEO_CONFIG_PATH", str(_DEFAULT_CONFIG_PATH))
    )

    if not path.exists():
        raise FileNotFoundError(
            f"설정 파일을 찾을 수 없습니다: {path}\n"
            "quanteo.yaml 경로를 QUANTEO_CONFIG_PATH 환경 변수로 지정하거나 "
            f"기본 위치({_DEFAULT_CONFIG_PATH})에 파일을 두세요.\n"
            "quanteo.yaml.example 을 참고해 설정 파일을 작성하세요."
        )

    with path.open("r", encoding="utf-8") as f:
        raw: dict[str, Any] = yaml.safe_load(f)

    toss_raw = raw.get("toss", {})
    if not toss_raw or not toss_raw.get("client_id"):
        raise ValueError(
            f"설정 파일에서 'toss' 섹션을 찾을 수 없습니다: {path}\n"
            "quanteo.yaml.example의 toss: 섹션을 참고하세요."
        )

    credentials = TossCredentials(
        client_id=toss_raw["client_id"],
        client_secret=toss_raw["client_secret"],
    )

    telegram_raw = raw.get("telegram", {})
    telegram = TelegramConfig(
        bot_token=telegram_raw.get("bot_token", ""),
        chat_id=telegram_raw.get("chat_id", ""),
        level=telegram_raw.get("level", "INFO"),
        enabled=telegram_raw.get("enabled", False),
    )

    return Settings(
        market=market,
        credentials=credentials,
        telegram=telegram,
    )
