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
