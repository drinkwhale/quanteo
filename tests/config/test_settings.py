"""Settings 모듈 단위 테스트."""

import pytest
import yaml
from pathlib import Path

from core.config.settings import Env, KisCredentials, Market, Settings, TelegramConfig, load_settings


def _write_yaml(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        yaml.dump(data, f)


# KIS 공식 포맷 (open-trading-api 샘플 기준, flat top-level keys)
KIS_OFFICIAL_CONFIG = {
    "user_agent": "TestAgent/1.0",
    "my_app": "PRODKEY1234567890123",
    "my_sec": "PRODSECRET12345678901234567890123456789012345678",
    "my_acct": "87654321",
    "my_acct_stock": "01",
    "my_id": "prod_user",
    "paper_app": "VPSKEY12345678901234",
    "paper_sec": "VPSSECRET1234567890123456789012345678901234567",
    "paper_acct": "12345678",
    "paper_acct_stock": "01",
    "paper_id": "test_user",
    "telegram": {
        "bot_token": "0000000000:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        "chat_id": "-100123456789",
        "level": "INFO",
        "enabled": False,
    },
}

# 커스텀 포맷 (중첩 섹션 방식, fallback)
CUSTOM_NESTED_CONFIG = {
    "user_agent": "TestAgent/1.0",
    "vps": {
        "app_key": "VPSKEY12345678901234",
        "app_secret": "VPSSECRET1234567890123456789012345678901234567",
        "account_no": "12345678",
        "account_code": "01",
        "hts_id": "test_user",
    },
    "prod": {
        "app_key": "PRODKEY1234567890123",
        "app_secret": "PRODSECRET12345678901234567890123456789012345678",
        "account_no": "87654321",
        "account_code": "01",
        "hts_id": "prod_user",
    },
    "telegram": {
        "bot_token": "0000000000:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        "chat_id": "-100123456789",
        "level": "INFO",
        "enabled": False,
    },
}


class TestLoadSettingsOfficialFormat:
    """KIS 공식 포맷(flat keys: my_app / paper_app) 테스트."""

    def test_loads_vps_by_default(self, tmp_path: Path) -> None:
        config_file = tmp_path / "kis_devlp.yaml"
        _write_yaml(config_file, KIS_OFFICIAL_CONFIG)

        settings = load_settings(config_path=config_file)

        assert settings.env == Env.VPS
        assert settings.credentials.app_key == "VPSKEY12345678901234"

    def test_loads_prod_when_explicit(self, tmp_path: Path) -> None:
        config_file = tmp_path / "kis_devlp.yaml"
        _write_yaml(config_file, KIS_OFFICIAL_CONFIG)

        settings = load_settings(env=Env.PROD, config_path=config_file)

        assert settings.env == Env.PROD
        assert settings.credentials.app_key == "PRODKEY1234567890123"

    def test_default_market_is_domestic(self, tmp_path: Path) -> None:
        config_file = tmp_path / "kis_devlp.yaml"
        _write_yaml(config_file, KIS_OFFICIAL_CONFIG)

        settings = load_settings(config_path=config_file)

        assert settings.market == Market.DOMESTIC

    def test_is_prod_flag(self, tmp_path: Path) -> None:
        config_file = tmp_path / "kis_devlp.yaml"
        _write_yaml(config_file, KIS_OFFICIAL_CONFIG)

        vps = load_settings(env=Env.VPS, config_path=config_file)
        prod = load_settings(env=Env.PROD, config_path=config_file)

        assert not vps.is_prod
        assert prod.is_prod

    def test_account_full_vps(self, tmp_path: Path) -> None:
        config_file = tmp_path / "kis_devlp.yaml"
        _write_yaml(config_file, KIS_OFFICIAL_CONFIG)

        settings = load_settings(config_path=config_file)

        assert settings.account_full == "1234567801"

    def test_telegram_disabled_by_default(self, tmp_path: Path) -> None:
        config_file = tmp_path / "kis_devlp.yaml"
        _write_yaml(config_file, KIS_OFFICIAL_CONFIG)

        settings = load_settings(config_path=config_file)

        assert not settings.telegram.enabled

    def test_user_agent_loaded(self, tmp_path: Path) -> None:
        config_file = tmp_path / "kis_devlp.yaml"
        _write_yaml(config_file, KIS_OFFICIAL_CONFIG)

        settings = load_settings(config_path=config_file)

        assert settings.credentials.user_agent == "TestAgent/1.0"


class TestLoadSettingsCustomFormat:
    """커스텀 중첩 포맷(prod: / vps: 섹션) fallback 테스트."""

    def test_loads_vps_from_nested_section(self, tmp_path: Path) -> None:
        config_file = tmp_path / "kis_devlp.yaml"
        _write_yaml(config_file, CUSTOM_NESTED_CONFIG)

        settings = load_settings(config_path=config_file)

        assert settings.env == Env.VPS
        assert settings.credentials.app_key == "VPSKEY12345678901234"

    def test_loads_prod_from_nested_section(self, tmp_path: Path) -> None:
        config_file = tmp_path / "kis_devlp.yaml"
        _write_yaml(config_file, CUSTOM_NESTED_CONFIG)

        settings = load_settings(env=Env.PROD, config_path=config_file)

        assert settings.credentials.app_key == "PRODKEY1234567890123"


class TestLoadSettingsErrors:
    def test_file_not_found_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="kis_devlp.yaml"):
            load_settings(config_path=tmp_path / "missing.yaml")

    def test_missing_credentials_raises(self, tmp_path: Path) -> None:
        config_file = tmp_path / "kis_devlp.yaml"
        # VPS 자격증명만 있고 PROD 없음
        _write_yaml(config_file, {
            "paper_app": "VPS_KEY",
            "paper_sec": "VPS_SEC",
            "paper_acct": "12345678",
        })

        with pytest.raises(ValueError, match="prod"):
            load_settings(env=Env.PROD, config_path=config_file)


class TestKisCredentials:
    def test_invalid_account_no_length_raises(self) -> None:
        with pytest.raises(ValueError, match="account_no"):
            KisCredentials(
                app_key="KEY",
                app_secret="SECRET",
                account_no="123",  # 8자리 아님
                account_code="01",
                hts_id="user",
            )

    def test_invalid_account_code_raises(self) -> None:
        with pytest.raises(ValueError, match="account_code"):
            KisCredentials(
                app_key="KEY",
                app_secret="SECRET",
                account_no="12345678",
                account_code="X1",  # 숫자 아님
                hts_id="user",
            )
