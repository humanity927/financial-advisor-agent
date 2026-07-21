from __future__ import annotations

import os
import subprocess
from pathlib import Path

MAX_PROMPT_CHARS = 8_000


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
            "--oneshot",
            "--toolsets",
            "finance",
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
            detail = stderr.strip() or "Hermes CLI 返回非零退出码"
            raise HermesCliError("hermes_failed", detail, retryable=True)

        report = stdout.strip()
        if not report:
            raise HermesCliError("hermes_empty_output", "Hermes 未返回可展示报告", retryable=True)
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
