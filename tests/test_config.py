import pytest
from pydantic import ValidationError

from core.config.manager import ConfigManager
from core.config.resolver import EnvVarResolver
from core.config.schemas import AppConfig


def test_production_cannot_enable_test_control():
    with pytest.raises(ValidationError):
        AppConfig(environment="production", test_control_enabled=True)


def test_file_backend_has_one_writer():
    with pytest.raises(ValidationError):
        AppConfig(environment="test", workers=2, storage_backend="file")


def test_offline_config_needs_no_external_credentials(monkeypatch):
    monkeypatch.delenv("TEST_ADMIN_TOKEN", raising=False)
    monkeypatch.delenv("SIMULATOR_TOKEN", raising=False)
    monkeypatch.setenv("BIGFISH_OTLP_ENABLED", "false")
    config = ConfigManager().load("configs/test.yaml")
    assert config.offline_mode and config.local_observation_enabled
    assert not config.otlp_enabled


def test_secrets_and_invalid_config_do_not_echo_credentials():
    config = AppConfig(test_admin_token="secret-admin", simulator_token="secret-sim")
    assert "secret-admin" not in repr(config)
    assert "secret-sim" not in config.model_dump_json()
    with pytest.raises(ValidationError) as error:
        AppConfig(test_admin_token="secret-admin", workers=0)
    assert "secret-admin" not in str(error.value)


def test_tokens_must_be_distinct():
    with pytest.raises(ValidationError):
        AppConfig(test_admin_token="same", simulator_token="same")


def test_environment_resolution(monkeypatch):
    monkeypatch.setenv("BIGFISH_TEST_VALUE", "resolved")
    assert EnvVarResolver.resolve({"a": ["${BIGFISH_TEST_VALUE}", "${ABSENT:-fallback}"]}) == {
        "a": ["resolved", "fallback"]
    }
    with pytest.raises(RuntimeError, match="UNSET_BIGFISH"):
        EnvVarResolver.resolve("${UNSET_BIGFISH}")


def test_unknown_config_rejected():
    with pytest.raises(ValidationError):
        AppConfig(typo=True)
