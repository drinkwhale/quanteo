"""Settings 모듈 단위 테스트."""

from pathlib import Path

import pytest
import yaml

from core.config.settings import Market, Settings, TossCredentials, load_settings


def _write_yaml(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        yaml.dump(data, f)


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


class TestLoadSettings:
    def test_loads_toss_credentials(self, tmp_path: Path) -> None:
        config_path = tmp_path / "quanteo.yaml"
        _write_yaml(config_path, TOSS_CONFIG)

        settings = load_settings(config_path=config_path)

        assert settings.credentials.client_id == "test-client-id"

    def test_default_market_is_domestic(self, tmp_path: Path) -> None:
        config_path = tmp_path / "quanteo.yaml"
        _write_yaml(config_path, TOSS_CONFIG)

        settings = load_settings(config_path=config_path)

        assert settings.market == Market.DOMESTIC

    def test_overseas_market(self, tmp_path: Path) -> None:
        config_path = tmp_path / "quanteo.yaml"
        _write_yaml(config_path, TOSS_CONFIG)

        settings = load_settings(market=Market.OVERSEAS, config_path=config_path)

        assert settings.market == Market.OVERSEAS

    def test_telegram_disabled_by_default(self, tmp_path: Path) -> None:
        config_path = tmp_path / "quanteo.yaml"
        _write_yaml(config_path, TOSS_CONFIG)

        settings = load_settings(config_path=config_path)

        assert not settings.telegram.enabled

    def test_telegram_config_loaded(self, tmp_path: Path) -> None:
        config_path = tmp_path / "quanteo.yaml"
        _write_yaml(config_path, TOSS_CONFIG)

        settings = load_settings(config_path=config_path)

        assert settings.telegram.chat_id == "-100"
        assert settings.telegram.level == "INFO"

    def test_secret_is_masked(self, tmp_path: Path) -> None:
        config_path = tmp_path / "quanteo.yaml"
        _write_yaml(config_path, TOSS_CONFIG)

        settings = load_settings(config_path=config_path)
        secret_repr = repr(settings.credentials.client_secret)

        assert "test-client-secret" not in secret_repr

    def test_file_not_found_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_settings(config_path=tmp_path / "missing.yaml")

    def test_missing_toss_section_raises(self, tmp_path: Path) -> None:
        config_path = tmp_path / "quanteo.yaml"
        _write_yaml(config_path, {"telegram": {}})

        with pytest.raises(ValueError, match="toss"):
            load_settings(config_path=config_path)

    def test_returns_settings_instance(self, tmp_path: Path) -> None:
        config_path = tmp_path / "quanteo.yaml"
        _write_yaml(config_path, TOSS_CONFIG)

        settings = load_settings(config_path=config_path)

        assert isinstance(settings, Settings)
        assert isinstance(settings.credentials, TossCredentials)

    def test_missing_client_secret_raises(self, tmp_path: Path) -> None:
        config_path = tmp_path / "quanteo.yaml"
        _write_yaml(config_path, {"toss": {"client_id": "only-id"}})

        with pytest.raises((KeyError, ValueError)):
            load_settings(config_path=config_path)

    def test_malformed_yaml_raises(self, tmp_path: Path) -> None:
        config_path = tmp_path / "quanteo.yaml"
        config_path.write_text("toss:\n  client_id: [\ninvalid yaml", encoding="utf-8")

        with pytest.raises(Exception):
            load_settings(config_path=config_path)

    def test_env_var_config_path(self, tmp_path: Path, monkeypatch) -> None:
        config_path = tmp_path / "custom.yaml"
        _write_yaml(config_path, TOSS_CONFIG)
        monkeypatch.setenv("QUANTEO_CONFIG_PATH", str(config_path))

        settings = load_settings()

        assert settings.credentials.client_id == "test-client-id"

    def test_kis_not_configured_by_default(self, tmp_path: Path) -> None:
        """kis: 섹션이 없으면 configured가 False여야 한다 (day_change 결측 처리 분기용)."""
        config_path = tmp_path / "quanteo.yaml"
        _write_yaml(config_path, TOSS_CONFIG)

        settings = load_settings(config_path=config_path)

        assert not settings.kis.configured

    def test_kis_section_loaded(self, tmp_path: Path) -> None:
        config_path = tmp_path / "quanteo.yaml"
        _write_yaml(
            config_path,
            {
                **TOSS_CONFIG,
                "kis": {
                    "app_key": "test-kis-app-key",
                    "app_secret": "test-kis-app-secret",
                    "prod_url": "https://example-kis.test:9443",
                },
            },
        )

        settings = load_settings(config_path=config_path)

        assert settings.kis.app_key == "test-kis-app-key"
        assert settings.kis.base_url == "https://example-kis.test:9443"
        assert settings.kis.configured

    def test_kis_secret_is_masked(self, tmp_path: Path) -> None:
        config_path = tmp_path / "quanteo.yaml"
        _write_yaml(
            config_path,
            {
                **TOSS_CONFIG,
                "kis": {"app_key": "k", "app_secret": "super-secret-value"},
            },
        )

        settings = load_settings(config_path=config_path)

        assert "super-secret-value" not in repr(settings.kis.app_secret)


class TestScreenerSettings:
    def test_disabled_by_default(self, tmp_path: Path) -> None:
        config_path = tmp_path / "quanteo.yaml"
        _write_yaml(config_path, TOSS_CONFIG)

        settings = load_settings(config_path=config_path)

        assert not settings.screener.enabled

    def test_own_keys_take_priority(self, tmp_path: Path) -> None:
        config_path = tmp_path / "quanteo.yaml"
        _write_yaml(
            config_path,
            {
                **TOSS_CONFIG,
                "info": {"dart": {"api_key": "info-dart-key"}, "anthropic": {"api_key": "info-anthropic-key"}},
                "screener": {
                    "enabled": True,
                    "dart": {"api_key": "screener-dart-key"},
                    "anthropic": {"api_key": "screener-anthropic-key"},
                    "telegram": {"chat_id": "screener-chat"},
                    "krx": {"id": "krx-user", "pw": "krx-pass"},
                },
            },
        )

        settings = load_settings(config_path=config_path)

        assert settings.screener.enabled
        assert settings.screener.dart_api_key == "screener-dart-key"
        assert settings.screener.anthropic_api_key == "screener-anthropic-key"
        assert settings.screener.telegram_chat_id == "screener-chat"
        assert settings.screener.krx_id == "krx-user"
        assert settings.screener.krx_pw == "krx-pass"

    def test_krx_credentials_default_empty(self, tmp_path: Path) -> None:
        # KRX 로그인은 info:/dart:와 무관한 별도 자격증명이라 폴백이 없다.
        config_path = tmp_path / "quanteo.yaml"
        _write_yaml(config_path, {**TOSS_CONFIG, "screener": {"enabled": True}})

        settings = load_settings(config_path=config_path)

        assert settings.screener.krx_id == ""
        assert settings.screener.krx_pw == ""

    def test_falls_back_to_info_and_telegram_keys(self, tmp_path: Path) -> None:
        config_path = tmp_path / "quanteo.yaml"
        _write_yaml(
            config_path,
            {
                **TOSS_CONFIG,
                "info": {"dart": {"api_key": "info-dart-key"}, "anthropic": {"api_key": "info-anthropic-key"}},
                "screener": {"enabled": True},
            },
        )

        settings = load_settings(config_path=config_path)

        assert settings.screener.dart_api_key == "info-dart-key"
        assert settings.screener.anthropic_api_key == "info-anthropic-key"
        assert settings.screener.telegram_chat_id == "-100"
