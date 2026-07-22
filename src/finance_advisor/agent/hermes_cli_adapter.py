from __future__ import annotations

import logging
import os
import re
import subprocess
import threading
from pathlib import Path

import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from finance_advisor.agent.model_config import (
    DEFAULT_HERMES_TOTAL_TIMEOUT_SECONDS,
    load_model_runtime_config,
    model_credentials_configured,
)
from finance_advisor.agent.tool_audit import audit_path

MAX_PROMPT_CHARS = 12_000
MAX_RESPONSE_CHARS = 50_000
SENSITIVE_ENV_VARS = (
    "RELAY_API_KEY",
    "DEEPSEEK_API_KEY",
    "TUSHARE_TOKEN",
    "RELAY_BASE_URL",
    "DEEPSEEK_BASE_URL",
)
LOGGER = logging.getLogger(__name__)
_ACTIVE_PROCESSES: dict[str, subprocess.Popen[str]] = {}
_CANCELLED_RUNS: set[str] = set()
_PROCESS_LOCK = threading.Lock()
_THINK_BLOCK = re.compile(r"<think\b[^>]*>.*?</think>", flags=re.IGNORECASE | re.DOTALL)


class HermesCliError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


class HermesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=MAX_RESPONSE_CHARS)

    @field_validator("content")
    @classmethod
    def sanitize_visible_content(cls, value: str) -> str:
        cleaned = _THINK_BLOCK.sub("", value).replace("\x00", "").strip()
        lowered = cleaned.lower()
        if "<think" in lowered or "</think>" in lowered:
            raise ValueError("unclosed hidden reasoning block")
        if not cleaned:
            raise ValueError("empty visible response")
        return cleaned


class HermesCliAdapter:
    """Call Hermes through the supported public CLI boundary only."""

    def __init__(
        self,
        *,
        project_root: Path,
        hermes_home: Path,
        executable: str = "hermes",
        timeout_seconds: float = DEFAULT_HERMES_TOTAL_TIMEOUT_SECONDS,
        use_windows_taskkill: bool | None = None,
    ) -> None:
        self.project_root = project_root.resolve()
        self.hermes_home = hermes_home.resolve()
        self.executable = executable
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.timeout_seconds = timeout_seconds
        self.use_windows_taskkill = (
            os.name == "nt" if use_windows_taskkill is None else use_windows_taskkill
        )

    def configuration_error(self) -> HermesCliError | None:
        config_path = self.hermes_home / "config.yaml"
        env_path = self.hermes_home / ".env"
        if not config_path.is_file():
            return HermesCliError(
                "model_configuration_missing",
                "Hermes 运行配置缺失，请先执行项目初始化与配置同步。",
            )
        try:
            runtime = load_model_runtime_config(env_path)
            raw_config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            if not isinstance(raw_config, dict):
                raise ValueError("Hermes config root must be a mapping")
        except (OSError, ValueError, ValidationError, yaml.YAMLError) as exc:
            LOGGER.warning(
                "Hermes model configuration invalid error_type=%s",
                type(exc).__name__,
            )
            return HermesCliError(
                "model_configuration_invalid",
                "模型运行配置无效，请检查本地环境变量并重新同步 Hermes 配置。",
            )

        primary_key, deepseek_key = model_credentials_configured(env_path)
        primary_ready = "example.invalid" not in runtime.primary_base_url_text and primary_key
        fallback_ready = not runtime.fallback_enabled or deepseek_key
        model_config = raw_config.get("model")
        configured_model = (
            str(model_config.get("default") or "").strip() if isinstance(model_config, dict) else ""
        )
        fallbacks = raw_config.get("fallback_providers")
        fallback_matches = bool(
            isinstance(fallbacks, list)
            and any(
                isinstance(item, dict)
                and str(item.get("provider") or "").strip().lower() == "deepseek"
                and str(item.get("model") or "").strip() == runtime.deepseek_model
                for item in fallbacks
            )
        )
        config_synced = configured_model == runtime.primary_model and (
            not runtime.fallback_enabled or fallback_matches
        )
        if not primary_ready or not fallback_ready or not config_synced:
            LOGGER.warning(
                "Hermes model configuration incomplete primary=%s fallback=%s synced=%s",
                primary_ready,
                fallback_ready,
                config_synced,
            )
            return HermesCliError(
                "model_configuration_missing",
                "模型服务配置不完整或尚未同步，请检查主模型与备用模型的本地配置。",
            )
        return None

    def generate_response(self, prompt: str, *, audit_id: str | None = None) -> str:
        if not prompt.strip():
            raise HermesCliError("empty_prompt", "咨询内容不能为空")
        if len(prompt) > MAX_PROMPT_CHARS:
            raise HermesCliError("prompt_too_long", "咨询上下文超过长度限制")

        self.hermes_home.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        env["HERMES_HOME"] = str(self.hermes_home)
        env["PYTHONUTF8"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        env["NO_COLOR"] = "1"
        env["FINANCE_TOOL_AUDIT_PATH"] = str(audit_path())
        try:
            runtime = load_model_runtime_config(self.hermes_home / ".env")
        except ValidationError:
            runtime = None
        if runtime is not None:
            request_timeout = f"{runtime.request_timeout_seconds:g}"
            env["HERMES_API_TIMEOUT"] = request_timeout
            env["HERMES_STREAM_READ_TIMEOUT"] = request_timeout
        if audit_id:
            env["FINANCE_AUDIT_ID"] = audit_id
        command = [
            self.executable,
            "chat",
            "--query",
            prompt,
            "--toolsets",
            "finance",
            "--quiet",
            "--yolo",
            "--source",
            "tool",
        ]
        process = subprocess.Popen(
            command,
            cwd=str(self.project_root),
            env=env,
            shell=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if audit_id:
            with _PROCESS_LOCK:
                _CANCELLED_RUNS.discard(audit_id)
                _ACTIVE_PROCESSES[audit_id] = process
        was_cancelled = False
        try:
            stdout, stderr = process.communicate(timeout=self.timeout_seconds)
        except subprocess.TimeoutExpired as exc:
            self._terminate_process_tree(process)
            raise HermesCliError("hermes_timeout", "Agent 生成响应超时", retryable=True) from exc
        finally:
            if audit_id:
                with _PROCESS_LOCK:
                    _ACTIVE_PROCESSES.pop(audit_id, None)
                    was_cancelled = audit_id in _CANCELLED_RUNS
                    _CANCELLED_RUNS.discard(audit_id)

        if was_cancelled:
            raise HermesCliError(
                "generation_cancelled",
                "本次生成已终止。",
                retryable=True,
            )

        if process.returncode != 0:
            LOGGER.warning(
                "Hermes CLI failed returncode=%s stderr_present=%s",
                process.returncode,
                bool(stderr.strip()),
            )
            raise self._classified_failure(stderr)

        try:
            response = HermesResponse(content=stdout)
        except ValidationError as exc:
            LOGGER.warning("Hermes response validation failed error_count=%s", exc.error_count())
            raise HermesCliError(
                "model_invalid_response",
                "模型返回内容无效，请重试本次咨询。",
                retryable=True,
            ) from exc

        sensitive_values = self._sensitive_values(env)
        if any(value in response.content for value in sensitive_values):
            raise HermesCliError(
                "unsafe_output",
                "模型返回内容触发敏感信息保护，响应已拦截。",
                retryable=True,
            )
        return response.content

    def generate_report(self, prompt: str, *, audit_id: str | None = None) -> str:
        return self.generate_response(prompt, audit_id=audit_id)

    @staticmethod
    def _sensitive_values(env: dict[str, str]) -> list[str]:
        names = set(SENSITIVE_ENV_VARS)
        names.update(name for name in env if name.endswith(("_API_KEY", "_TOKEN")))
        return [value for name in names if len(value := str(env.get(name) or "").strip()) >= 8]

    @staticmethod
    def _classified_failure(stderr: str) -> HermesCliError:
        lowered = stderr.lower()
        if "usage: hermes" in lowered and "invalid choice" in lowered:
            return HermesCliError(
                "hermes_cli_argument_error",
                "Hermes CLI 无法接收本次咨询上下文，请缩短输入后重试。",
            )
        if any(term in lowered for term in ("401", "unauthorized", "invalid api key")):
            return HermesCliError(
                "model_auth_failed",
                "模型服务鉴权失败，请检查本地凭据配置。",
            )
        if any(term in lowered for term in ("429", "rate limit", "too many requests")):
            return HermesCliError(
                "model_rate_limited",
                "模型服务当前请求过多，请稍后重试。",
                retryable=True,
            )
        if "mcp" in lowered and any(
            term in lowered for term in ("failed", "timeout", "connect", "unavailable")
        ):
            return HermesCliError(
                "mcp_unavailable",
                "金融 MCP 工具连接失败，请检查本地服务配置。",
                retryable=True,
            )
        if any(term in lowered for term in ("timed out", "timeout", "readtimeout")):
            return HermesCliError(
                "model_timeout",
                "模型服务响应超时，请稍后重试。",
                retryable=True,
            )
        if any(
            term in lowered
            for term in (
                "500",
                "502",
                "503",
                "504",
                "service unavailable",
                "connection error",
                "connection refused",
                "name resolution",
            )
        ):
            return HermesCliError(
                "model_service_unavailable",
                "主模型与可用备用模型暂时无法连接，请稍后重试。",
                retryable=True,
            )
        if any(
            term in lowered
            for term in ("malformed response", "invalid response", "jsondecode", "no choices")
        ):
            return HermesCliError(
                "model_invalid_response",
                "模型返回内容无效，请重试本次咨询。",
                retryable=True,
            )
        return HermesCliError(
            "hermes_failed",
            "Hermes 顾问服务暂不可用，请检查模型与运行配置。",
            retryable=True,
        )

    def _terminate_process_tree(self, process: subprocess.Popen[str]) -> None:
        if self.use_windows_taskkill and process.pid:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            process.kill()

        try:
            process.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()


def cancel_run(audit_id: str) -> bool:
    with _PROCESS_LOCK:
        process = _ACTIVE_PROCESSES.get(audit_id)
        if process is None or process.poll() is not None:
            return False
        _CANCELLED_RUNS.add(audit_id)
    if os.name == "nt" and process.pid:
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
        process.kill()
    return True


def is_run_active(audit_id: str) -> bool:
    with _PROCESS_LOCK:
        process = _ACTIVE_PROCESSES.get(audit_id)
        return process is not None and process.poll() is None
