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


class KisSettings(BaseModel):
    """KIS(한국투자증권) Open API 설정 — 당일 등락(전일 종가) 조회 전용.

    실전 매매 브로커가 아니다 (Phase 8-9에서 KIS 브로커는 완전 제거됨).
    Toss 캔들 API의 종가 데이터가 실제 시세와 어긋나는 사례가 확인돼,
    day_change 계산의 전일 종가만 KIS 실시간 시세 조회(stck_sdpr)로
    대체하기 위한 읽기 전용 용도.
    """

    app_key: str = ""
    app_secret: SecretStr = SecretStr("")
    base_url: str = "https://openapi.koreainvestment.com:9443"

    @property
    def configured(self) -> bool:
        return bool(self.app_key and self.app_secret.get_secret_value())


class InfoSettings(BaseModel):
    """정보 수집·알람 서브시스템 설정 (Phase 10)."""

    enabled: bool = False
    dart_api_key: str = ""
    finnhub_api_key: str = ""
    google_calendar_credentials_path: str = ""
    anthropic_api_key: str = ""
    fx_alert_threshold: float = 1.0  # USD/KRW 급변 알람 임계값 (%)
    telegram_chat_id: str = ""  # info 전용 chat_id (없으면 main telegram.chat_id 사용)


class ScreenerSettings(BaseModel):
    """일일 종목 추천 시스템(Stock Miner, Phase 16) 설정.

    스코어링 가중치·유니버스 필터 임계값 등은 여기 두지 않는다 — 그건
    `config_path`가 가리키는 screener/config/settings.yaml의 몫이다. 여기는
    quanteo.yaml에서 오는 자격증명·활성화 플래그만 담는다.
    """

    enabled: bool = False
    config_path: str = "screener/config/settings.yaml"
    dart_api_key: str = ""
    anthropic_api_key: str = ""
    telegram_chat_id: str = ""
    krx_id: str = ""
    krx_pw: str = ""


class Settings(BaseModel):
    """quanteo 전체 설정."""

    market: Market = Market.DOMESTIC
    credentials: TossCredentials
    telegram: TelegramConfig = TelegramConfig()
    info: InfoSettings = InfoSettings()
    kis: KisSettings = KisSettings()
    screener: ScreenerSettings = ScreenerSettings()


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

    info_raw = raw.get("info", {})
    info = InfoSettings(
        enabled=info_raw.get("enabled", False),
        dart_api_key=info_raw.get("dart", {}).get("api_key", ""),
        finnhub_api_key=info_raw.get("finnhub", {}).get("api_key", ""),
        google_calendar_credentials_path=info_raw.get("google_calendar", {}).get(
            "credentials_path", ""
        ),
        anthropic_api_key=info_raw.get("anthropic", {}).get("api_key", ""),
        fx_alert_threshold=info_raw.get("fx_alert_threshold", 1.0),
        telegram_chat_id=info_raw.get("telegram", {}).get("chat_id", ""),
    )

    kis_raw = raw.get("kis", {})
    kis = KisSettings(
        app_key=kis_raw.get("app_key", ""),
        app_secret=kis_raw.get("app_secret", ""),
        base_url=kis_raw.get("prod_url", "https://openapi.koreainvestment.com:9443"),
    )

    screener_raw = raw.get("screener", {})
    screener = ScreenerSettings(
        enabled=screener_raw.get("enabled", False),
        config_path=os.environ.get(
            "SCREENER_CONFIG_PATH", "screener/config/settings.yaml"
        ),
        # DART/Anthropic 키는 info: 섹션과 공유 재사용이 기본값 — screener: 섹션에
        # 값이 없으면 info.* 키를 그대로 물려받는다.
        dart_api_key=screener_raw.get("dart", {}).get("api_key", "") or info.dart_api_key,
        anthropic_api_key=(
            screener_raw.get("anthropic", {}).get("api_key", "") or info.anthropic_api_key
        ),
        telegram_chat_id=(
            screener_raw.get("telegram", {}).get("chat_id", "") or telegram.chat_id
        ),
        # KRX가 대량 조회 엔드포인트에 로그인 세션을 요구하므로(pykrx 내장
        # KRX_ID/KRX_PW 로그인 지원) 별도 자격증명 — info:/dart:와 공유하지
        # 않는다(KRX 개인 회원 계정, DART Open API 키와는 무관).
        krx_id=screener_raw.get("krx", {}).get("id", ""),
        krx_pw=screener_raw.get("krx", {}).get("pw", ""),
    )

    return Settings(
        market=market,
        credentials=credentials,
        telegram=telegram,
        info=info,
        kis=kis,
        screener=screener,
    )
