"""Settings 모듈 단위 테스트."""

from pathlib import Path

import pytest
import yaml

from core.config.settings import (
    Env,
    KisCredentials,
    Market,
    TossCredentials,
    load_settings,
)


def _write_yaml(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        yaml.dump(data, f)


# KIS 공식 포맷 (open-trading-api 원본 변수명 기준)
KIS_OFFICIAL_CONFIG = {
    "my_agent": "TestAgent/1.0",
    "my_app": "PRODKEY1234567890123",
    "my_sec": "PRODSECRET12345678901234567890123456789012345678",
    "my_acct_stock": "87654321",    # 실전 증권계좌 8자리
    "my_prod": "01",                # 계좌번호 뒤 2자리
    "my_htsid": "prod_user",
    "paper_app": "VPSKEY12345678901234",
    "paper_sec": "VPSSECRET1234567890123456789012345678901234567",
    "my_paper_stock": "12345678",   # 모의투자 증권계좌 8자리
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
        # VPS 자격증명만 있고 PROD(my_app) 없음
        _write_yaml(config_file, {
            "paper_app": "VPS_KEY",
            "paper_sec": "VPS_SEC",
            "my_paper_stock": "12345678",
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


class TestLoadSettingsToss:
    """Toss 브로커 설정 로딩 테스트."""

    TOSS_CONFIG = {
        "toss": {
            "client_id": "test-client-id",
            "client_secret": "test-client-secret",
        },
        "telegram": {
            "bot_token": "0:AAAAA",
            "chat_id": "-100",
            "level": "INFO",
            "enabled": False,
        },
    }

    def test_loads_toss_credentials(self, tmp_path: Path) -> None:
        """broker='toss' 시 TossCredentials가 올바르게 로드된다."""
        config_path = tmp_path / "config.yaml"
        with config_path.open("w") as f:
            import yaml
            yaml.dump(self.TOSS_CONFIG, f)

        settings = load_settings(config_path=config_path, broker="toss")

        assert settings.broker == "toss"
        assert settings.toss_credentials is not None
        assert settings.toss_credentials.client_id == "test-client-id"
        assert settings.credentials is None  # KIS 자격증명 없음

    def test_toss_missing_section_raises(self, tmp_path: Path) -> None:
        """설정 파일에 toss 섹션이 없으면 ValueError를 발생시킨다."""
        config_path = tmp_path / "config.yaml"
        with config_path.open("w") as f:
            import yaml
            yaml.dump({"telegram": {}}, f)

        with pytest.raises(ValueError, match="toss"):
            load_settings(config_path=config_path, broker="toss")

    def test_toss_secret_is_secret_str(self, tmp_path: Path) -> None:
        """TossCredentials.client_secret은 SecretStr으로 마스킹된다."""
        config_path = tmp_path / "config.yaml"
        with config_path.open("w") as f:
            import yaml
            yaml.dump(self.TOSS_CONFIG, f)

        settings = load_settings(config_path=config_path, broker="toss")
        secret_repr = repr(settings.toss_credentials.client_secret)
        assert "test-client-secret" not in secret_repr  # SecretStr 마스킹 확인
