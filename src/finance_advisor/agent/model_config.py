from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dotenv import dotenv_values
from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, field_validator, model_validator

DEFAULT_HERMES_TOTAL_TIMEOUT_SECONDS = 300.0


class ModelRuntimeConfig(BaseModel):
    """Validated, non-secret settings shared by Hermes and model preflight."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    primary_base_url: AnyHttpUrl = Field(alias="RELAY_BASE_URL")
    primary_model: str = Field(alias="RELAY_MODEL_ID", min_length=1, max_length=200)
    deepseek_base_url: AnyHttpUrl = Field(
        default=AnyHttpUrl("https://api.deepseek.com/v1"),
        alias="DEEPSEEK_BASE_URL",
    )
    deepseek_model: str = Field(
        default="deepseek-chat",
        alias="DEEPSEEK_MODEL_ID",
        min_length=1,
        max_length=200,
    )
    request_timeout_seconds: float = Field(
        default=90.0,
        alias="MODEL_REQUEST_TIMEOUT_SECONDS",
        ge=5,
        le=600,
    )
    total_timeout_seconds: float = Field(
        default=DEFAULT_HERMES_TOTAL_TIMEOUT_SECONDS,
        alias="HERMES_TOTAL_TIMEOUT_SECONDS",
        ge=10,
        le=1_800,
    )
    max_retries: int = Field(default=1, alias="MODEL_MAX_RETRIES", ge=0, le=3)
    fallback_enabled: bool = Field(
        default=True,
        alias="DEEPSEEK_FALLBACK_ENABLED",
    )

    @field_validator("primary_model", "deepseek_model")
    @classmethod
    def normalize_model_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("model id cannot be empty")
        return normalized

    @model_validator(mode="after")
    def validate_timeout_budget(self) -> ModelRuntimeConfig:
        if self.total_timeout_seconds < self.request_timeout_seconds:
            raise ValueError("Hermes total timeout cannot be shorter than a model request timeout")
        return self

    @property
    def primary_base_url_text(self) -> str:
        return str(self.primary_base_url).rstrip("/")

    @property
    def deepseek_base_url_text(self) -> str:
        return str(self.deepseek_base_url).rstrip("/")


MODEL_CONFIG_ENV_KEYS = (
    "RELAY_BASE_URL",
    "RELAY_MODEL_ID",
    "DEEPSEEK_BASE_URL",
    "DEEPSEEK_MODEL_ID",
    "MODEL_REQUEST_TIMEOUT_SECONDS",
    "HERMES_TOTAL_TIMEOUT_SECONDS",
    "MODEL_MAX_RETRIES",
    "DEEPSEEK_FALLBACK_ENABLED",
)


def read_model_environment(env_file: Path | None = None) -> dict[str, Any]:
    file_values = dotenv_values(env_file) if env_file and env_file.is_file() else {}
    merged = {**file_values, **os.environ}
    return {key: merged[key] for key in MODEL_CONFIG_ENV_KEYS if merged.get(key) is not None}


def load_model_runtime_config(env_file: Path | None = None) -> ModelRuntimeConfig:
    return ModelRuntimeConfig.model_validate(read_model_environment(env_file))


def model_credentials_configured(env_file: Path | None = None) -> tuple[bool, bool]:
    file_values = dotenv_values(env_file) if env_file and env_file.is_file() else {}
    merged = {**file_values, **os.environ}
    return (
        bool(str(merged.get("RELAY_API_KEY") or "").strip()),
        bool(str(merged.get("DEEPSEEK_API_KEY") or "").strip()),
    )
