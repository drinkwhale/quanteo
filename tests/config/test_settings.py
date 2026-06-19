"""Settings 모듈 단위 테스트."""

import pytest
import yaml
from pathlib import Path

from core.config.settings import Env, KisCredentials, Market, Settings, TelegramConfig, load_settings


def _write_yaml(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        yaml.dump(data, f)


SAMPLE_CONFIG = {
    "user_agent": "TestAgent/1.0",
    "vps": {
        "app_key": "VPSKEY12345678901234",
        "app_secret": "VPSSECRET1234567890123456789012345678901234567890",
        "account_no": "12345678",
        "account_code": "01",
        "hts_id": "test_user",
    },
    "prod": {
        "app_key": "PRODKEY1234567890123",
        "app_secret": "PRODSECRET123456789012345678901234567890123456789",
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


class TestLoadSettings:
    def test_loads_vps_by_default(self, tmp_path: Path) -> None:
        config_file = tmp_path / "kis_devlp.yaml"
        _write_yaml(config_file, SAMPLE_CONFIG)

        settings = load_settings(config_path=config_file)

        assert settings.env == Env.VPS
        assert settings.credentials.app_key == "VPSKEY12345678901234"

    def test_loads_prod_when_explicit(self, tmp_path: Path) -> None:
        config_file = tmp_path / "kis_devlp.yaml"
        _write_yaml(config_file, SAMPLE_CONFIG)

        settings = load_settings(env=Env.PROD, config_path=config_file)

        assert settings.env == Env.PROD
        assert settings.credentials.app_key == "PRODKEY1234567890123"

    def test_default_market_is_domestic(self, tmp_path: Path) -> None:
        config_file = tmp_path / "kis_devlp.yaml"
        _write_yaml(config_file, SAMPLE_CONFIG)

        settings = load_settings(config_path=config_file)

        assert settings.market == Market.DOMESTIC

    def test_is_prod_flag(self, tmp_path: Path) -> None:
        config_file = tmp_path / "kis_devlp.yaml"
        _write_yaml(config_file, SAMPLE_CONFIG)

        vps = load_settings(env=Env.VPS, config_path=config_file)
        prod = load_settings(env=Env.PROD, config_path=config_file)

        assert not vps.is_prod
        assert prod.is_prod

    def test_account_full_concatenates_cano_and_product_code(self, tmp_path: Path) -> None:
        config_file = tmp_path / "kis_devlp.yaml"
        _write_yaml(config_file, SAMPLE_CONFIG)

        settings = load_settings(config_path=config_file)

        assert settings.account_full == "1234567801"

    def test_file_not_found_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="kis_devlp.yaml"):
            load_settings(config_path=tmp_path / "missing.yaml")

    def test_missing_env_section_raises(self, tmp_path: Path) -> None:
        config_file = tmp_path / "kis_devlp.yaml"
        _write_yaml(config_file, {"vps": SAMPLE_CONFIG["vps"]})  # prod 섹션 없음

        with pytest.raises(ValueError, match="'prod'"):
            load_settings(env=Env.PROD, config_path=config_file)

    def test_telegram_disabled_by_default(self, tmp_path: Path) -> None:
        config_file = tmp_path / "kis_devlp.yaml"
        _write_yaml(config_file, SAMPLE_CONFIG)

        settings = load_settings(config_path=config_file)

        assert not settings.telegram.enabled


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
