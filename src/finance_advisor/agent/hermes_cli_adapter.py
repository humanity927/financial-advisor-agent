from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path

MAX_PROMPT_CHARS = 8_000
SENSITIVE_ENV_VARS = ("RELAY_API_KEY", "DEEPSEEK_API_KEY", "RELAY_BASE_URL")
LOGGER = logging.getLogger(__name__)


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
        timeout_seconds: float = 60.0,
        use_windows_taskkill: bool | None = None,
    ) -> None:
        self.project_root = project_root.resolve()
        self.hermes_home = hermes_home.resolve()
        self.executable = executable
        self.timeout_seconds = timeout_seconds
        self.use_windows_taskkill = (
            os.name == "nt" if use_windows_taskkill is None else use_windows_taskkill
        )

    def generate_report(self, prompt: str) -> str:
        if not prompt.strip():
            raise HermesCliError("empty_prompt", "报告提示词不能为空")
        if len(prompt) > MAX_PROMPT_CHARS:
            raise HermesCliError("prompt_too_long", "报告提示词超过长度限制")

        self.hermes_home.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        env["HERMES_HOME"] = str(self.hermes_home)
        command = [
            self.executable,
            "--toolsets",
            "finance",
            "--oneshot",
            prompt,
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
        try:
            stdout, stderr = process.communicate(timeout=self.timeout_seconds)
        except subprocess.TimeoutExpired as exc:
            self._terminate_process_tree(process)
            raise HermesCliError("hermes_timeout", "Hermes 生成报告超时", retryable=True) from exc

        if process.returncode != 0:
            LOGGER.warning(
                "Hermes CLI failed returncode=%s stderr_present=%s",
                process.returncode,
                bool(stderr.strip()),
            )
            raise HermesCliError(
                "hermes_failed",
                "Hermes 顾问服务暂不可用，请检查模型与运行配置。",
                retryable=True,
            )

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
