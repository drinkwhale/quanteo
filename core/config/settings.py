"""
설정 로딩 모듈.

kis_devlp.yaml을 읽어 환경(prod/vps)·시장(domestic/overseas) 설정을 제공.
기본 환경은 항상 vps(모의투자).
"""

from __future__ import annotations

import os
from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, SecretStr, field_validator


# ---------------------------------------------------------------------------
# 열거형
# ---------------------------------------------------------------------------


class Env(str, Enum):
    """KIS 투자 환경."""

    PROD = "prod"  # 실전투자 (실제 돈)
    VPS = "vps"    # 모의투자 (paper trading) — 기본값


class Market(str, Enum):
    """대상 시장."""

    DOMESTIC = "domestic"
    OVERSEAS = "overseas"


# ---------------------------------------------------------------------------
# KIS 자격증명 모델
# ---------------------------------------------------------------------------


class KisCredentials(BaseModel):
    """환경별 KIS API 자격증명."""

    app_key: str
    app_secret: SecretStr
    account_no: str   # CANO 8자리
    account_code: str  # ACNT_PRDT_CD 2자리 (예: "01")
    hts_id: str
    user_agent: str = "Mozilla/5.0"

    @field_validator("account_no")
    @classmethod
    def validate_account_no(cls, v: str) -> str:
        if len(v) != 8 or not v.isdigit():
            raise ValueError(f"account_no는 8자리 숫자여야 합니다: {v!r}")
        return v

    @field_validator("account_code")
    @classmethod
    def validate_account_code(cls, v: str) -> str:
        if len(v) != 2 or not v.isdigit():
            raise ValueError(f"account_code는 2자리 숫자여야 합니다: {v!r}")
        return v


# ---------------------------------------------------------------------------
# Telegram 설정
# ---------------------------------------------------------------------------


class TelegramConfig(BaseModel):
    """Telegram 알림 설정."""

    bot_token: SecretStr = SecretStr("")
    chat_id: str = ""
    level: str = "INFO"
    enabled: bool = False


# ---------------------------------------------------------------------------
# 전체 앱 설정
# ---------------------------------------------------------------------------


class Settings(BaseModel):
    """quanteo 전체 설정."""

    env: Env = Env.VPS
    market: Market = Market.DOMESTIC
    credentials: KisCredentials
    telegram: TelegramConfig = TelegramConfig()

    @property
    def is_prod(self) -> bool:
        return self.env == Env.PROD

    @property
    def account_full(self) -> str:
        """CANO+ACNT_PRDT_CD 합산 문자열."""
        return self.credentials.account_no + self.credentials.account_code


# ---------------------------------------------------------------------------
# YAML 로딩
# ---------------------------------------------------------------------------


_DEFAULT_CONFIG_PATH = Path.home() / "KIS" / "config" / "kis_devlp.yaml"


def load_settings(
    env: Env = Env.VPS,
    market: Market = Market.DOMESTIC,
    config_path: Path | None = None,
) -> Settings:
    """kis_devlp.yaml을 읽어 Settings를 반환한다.

    Args:
        env: 투자 환경. 기본값 VPS(모의투자). PROD는 명시적으로만 지정.
        market: 대상 시장. 기본값 DOMESTIC.
        config_path: 설정 파일 경로. 기본값: ~/KIS/config/kis_devlp.yaml.
            환경 변수 QUANTEO_CONFIG_PATH 로 재지정 가능.

    Returns:
        Settings 인스턴스.

    Raises:
        FileNotFoundError: 설정 파일을 찾을 수 없을 때.
        ValueError: 필수 자격증명 필드가 누락되었을 때.
    """
    path = config_path or Path(os.environ.get("QUANTEO_CONFIG_PATH", str(_DEFAULT_CONFIG_PATH)))

    if not path.exists():
        raise FileNotFoundError(
            f"KIS 설정 파일을 찾을 수 없습니다: {path}\n"
            "kis_devlp.yaml 경로를 QUANTEO_CONFIG_PATH 환경 변수로 지정하거나 "
            f"기본 위치({_DEFAULT_CONFIG_PATH})에 파일을 두세요."
        )

    with path.open("r", encoding="utf-8") as f:
        raw: dict[str, Any] = yaml.safe_load(f)

    env_key = env.value  # "prod" or "vps"
    if env_key not in raw:
        raise ValueError(f"설정 파일에 '{env_key}' 섹션이 없습니다: {path}")

    creds_raw = raw[env_key]
    credentials = KisCredentials(
        app_key=creds_raw["app_key"],
        app_secret=creds_raw["app_secret"],
        account_no=creds_raw["account_no"],
        account_code=creds_raw.get("account_code", "01"),
        hts_id=creds_raw.get("hts_id", ""),
        user_agent=raw.get("user_agent", "Mozilla/5.0"),
    )

    telegram_raw = raw.get("telegram", {})
    telegram = TelegramConfig(
        bot_token=telegram_raw.get("bot_token", ""),
        chat_id=telegram_raw.get("chat_id", ""),
        level=telegram_raw.get("level", "INFO"),
        enabled=telegram_raw.get("enabled", False),
    )

    return Settings(
        env=env,
        market=market,
        credentials=credentials,
        telegram=telegram,
    )
