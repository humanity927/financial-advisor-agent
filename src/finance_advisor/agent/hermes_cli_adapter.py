from __future__ import annotations

import logging
import os
import subprocess
import threading
from pathlib import Path

from dotenv import dotenv_values

from finance_advisor.agent.tool_audit import audit_path

MAX_PROMPT_CHARS = 12_000
SENSITIVE_ENV_VARS = ("RELAY_API_KEY", "DEEPSEEK_API_KEY", "RELAY_BASE_URL")
LOGGER = logging.getLogger(__name__)
_ACTIVE_PROCESSES: dict[str, subprocess.Popen[str]] = {}
_PROCESS_LOCK = threading.Lock()


class HermesCliError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


class HermesCliAdapter:
    """Call Hermes through the supported public CLI boundary only."""

    def __init__(
        self,
        *,
        project_root: Path,
        hermes_home: Path,
        executable: str = "hermes",
        timeout_seconds: float = 120.0,
        use_windows_taskkill: bool | None = None,
    ) -> None:
        self.project_root = project_root.resolve()
        self.hermes_home = hermes_home.resolve()
        self.executable = executable
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
        values = {**dotenv_values(env_path), **os.environ}
        base_url = str(values.get("RELAY_BASE_URL") or "")
        api_key = str(values.get("RELAY_API_KEY") or "")
        model_id = str(values.get("RELAY_MODEL_ID") or "")
        if not base_url or "example.invalid" in base_url or not api_key or not model_id:
            LOGGER.warning(
                "Hermes model configuration incomplete base_url=%s api_key=%s model_id=%s",
                bool(base_url and "example.invalid" not in base_url),
                bool(api_key),
                bool(model_id),
            )
            return HermesCliError(
                "model_configuration_missing",
                "模型服务配置不完整，请配置主模型地址、模型标识和凭据。",
            )
        return None

    def generate_report(self, prompt: str, *, audit_id: str | None = None) -> str:
        if not prompt.strip():
            raise HermesCliError("empty_prompt", "报告提示词不能为空")
        if len(prompt) > MAX_PROMPT_CHARS:
            raise HermesCliError("prompt_too_long", "报告提示词超过长度限制")

        self.hermes_home.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        env["HERMES_HOME"] = str(self.hermes_home)
        env["PYTHONUTF8"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        env["NO_COLOR"] = "1"
        env["FINANCE_TOOL_AUDIT_PATH"] = str(audit_path())
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
                _ACTIVE_PROCESSES[audit_id] = process
        try:
            stdout, stderr = process.communicate(timeout=self.timeout_seconds)
        except subprocess.TimeoutExpired as exc:
            self._terminate_process_tree(process)
            raise HermesCliError("hermes_timeout", "Hermes 生成报告超时", retryable=True) from exc
        finally:
            if audit_id:
                with _PROCESS_LOCK:
                    _ACTIVE_PROCESSES.pop(audit_id, None)

        if process.returncode != 0:
            LOGGER.warning(
                "Hermes CLI failed returncode=%s stderr_present=%s",
                process.returncode,
                bool(stderr.strip()),
            )
            raise self._classified_failure(stderr)

        report = stdout.strip()
        if not report:
            raise HermesCliError("hermes_empty_output", "Hermes 未返回可展示报告", retryable=True)
        sensitive_values = [env.get(name, "") for name in SENSITIVE_ENV_VARS]
        if any(len(value) >= 8 and value in report for value in sensitive_values):
            raise HermesCliError(
                "unsafe_output",
                "Hermes 返回内容触发敏感信息保护，报告已拦截。",
                retryable=True,
            )
        return report

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
