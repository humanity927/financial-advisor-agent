from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from finance_advisor.agent.model_config import (
    MODEL_CONFIG_ENV_KEYS,
    load_model_runtime_config,
    model_credentials_configured,
)


@pytest.fixture(autouse=True)
def clear_model_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (*MODEL_CONFIG_ENV_KEYS, "RELAY_API_KEY", "DEEPSEEK_API_KEY"):
        monkeypatch.delenv(key, raising=False)


def _write_env(path: Path, extra: str = "") -> None:
    path.write_text(
        "\n".join(
            (
                "RELAY_BASE_URL=https://relay.example/v1",
                "RELAY_MODEL_ID=test-model",
                "DEEPSEEK_BASE_URL=https://deepseek.example/v1",
                "DEEPSEEK_MODEL_ID=deepseek-test",
                "MODEL_REQUEST_TIMEOUT_SECONDS=60",
                "HERMES_TOTAL_TIMEOUT_SECONDS=240",
                "MODEL_MAX_RETRIES=1",
                "DEEPSEEK_FALLBACK_ENABLED=true",
                extra,
            )
        ),
        encoding="utf-8",
    )


def test_model_runtime_config_loads_all_non_secret_controls(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    _write_env(env_file)

    config = load_model_runtime_config(env_file)

    assert config.primary_base_url_text == "https://relay.example/v1"
    assert config.primary_model == "test-model"
    assert config.deepseek_model == "deepseek-test"
    assert config.request_timeout_seconds == 60
    assert config.total_timeout_seconds == 240
    assert config.max_retries == 1
    assert config.fallback_enabled is True


def test_model_runtime_config_rejects_total_timeout_below_request_timeout(
    tmp_path: Path,
) -> None:
    env_file = tmp_path / ".env"
    _write_env(env_file, "HERMES_TOTAL_TIMEOUT_SECONDS=30")

    with pytest.raises(ValidationError):
        load_model_runtime_config(env_file)


def test_credentials_are_read_as_presence_only(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    _write_env(env_file, "RELAY_API_KEY=primary-secret\nDEEPSEEK_API_KEY=fallback-secret")

    assert model_credentials_configured(env_file) == (True, True)
