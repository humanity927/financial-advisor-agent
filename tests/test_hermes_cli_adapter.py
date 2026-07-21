from __future__ import annotations

import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest

from finance_advisor.agent.hermes_cli_adapter import (
    MAX_PROMPT_CHARS,
    HermesCliAdapter,
    HermesCliError,
)


class FakeProcess:
    def __init__(
        self,
        *,
        stdout: str = "",
        stderr: str = "",
        returncode: int = 0,
        timeout_once: bool = False,
    ) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode
        self.timeout_once = timeout_once
        self.pid = 4321
        self.killed = False
        self.communicate_calls = 0

    def communicate(self, timeout: float | None = None) -> tuple[str, str]:
        self.communicate_calls += 1
        if self.timeout_once:
            self.timeout_once = False
            raise subprocess.TimeoutExpired(cmd="hermes", timeout=timeout)
        return self.stdout, self.stderr

    def kill(self) -> None:
        self.killed = True


def _adapter(tmp_path: Path, *, use_windows_taskkill: bool = False) -> HermesCliAdapter:
    return HermesCliAdapter(
        project_root=tmp_path,
        hermes_home=tmp_path / ".runtime" / "hermes-test",
        executable="hermes",
        timeout_seconds=0.1,
        use_windows_taskkill=use_windows_taskkill,
    )


def test_success_uses_fixed_cli_args_and_isolated_home(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    process = FakeProcess(stdout=" 报告内容 \n")
    captured: dict[str, Any] = {}

    def fake_popen(args: Sequence[str], **kwargs: Any) -> FakeProcess:
        captured["args"] = list(args)
        captured["kwargs"] = kwargs
        return process

    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    report = _adapter(tmp_path).generate_report("生成教学报告")

    assert report == "报告内容"
    assert captured["args"] == ["hermes", "--toolsets", "finance", "--oneshot", "生成教学报告"]
    assert captured["kwargs"]["shell"] is False
    assert captured["kwargs"]["cwd"] == str(tmp_path.resolve())
    env = captured["kwargs"]["env"]
    assert isinstance(env, Mapping)
    assert env["HERMES_HOME"] == str((tmp_path / ".runtime" / "hermes-test").resolve())


def test_timeout_cleans_full_windows_process_tree(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    process = FakeProcess(stdout="late", timeout_once=True)
    run_calls: list[list[str]] = []

    monkeypatch.setattr(subprocess, "Popen", lambda *_args, **_kwargs: process)

    def fake_run(args: Sequence[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        run_calls.append(list(args))
        return subprocess.CompletedProcess(args=list(args), returncode=0)

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(HermesCliError) as exc_info:
        _adapter(tmp_path, use_windows_taskkill=True).generate_report("生成教学报告")

    assert exc_info.value.code == "hermes_timeout"
    assert exc_info.value.retryable is True
    assert run_calls == [["taskkill", "/PID", "4321", "/T", "/F"]]
    assert process.communicate_calls == 2


def test_nonzero_exit_returns_stable_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    process = FakeProcess(stderr="secret-key-and-provider-url", returncode=2)
    monkeypatch.setattr(subprocess, "Popen", lambda *_args, **_kwargs: process)

    with pytest.raises(HermesCliError) as exc_info:
        _adapter(tmp_path).generate_report("生成教学报告")

    assert exc_info.value.code == "hermes_failed"
    assert exc_info.value.message == "Hermes 顾问服务暂不可用，请检查模型与运行配置。"
    assert "secret-key" not in exc_info.value.message
    assert exc_info.value.retryable is True


def test_empty_output_is_retryable_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    process = FakeProcess(stdout="  \n", returncode=0)
    monkeypatch.setattr(subprocess, "Popen", lambda *_args, **_kwargs: process)

    with pytest.raises(HermesCliError) as exc_info:
        _adapter(tmp_path).generate_report("生成教学报告")

    assert exc_info.value.code == "hermes_empty_output"
    assert exc_info.value.retryable is True


def test_sensitive_environment_value_in_output_is_blocked(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    secret = "relay-secret-value"
    process = FakeProcess(stdout=f"不应展示 {secret}", returncode=0)
    monkeypatch.setenv("RELAY_API_KEY", secret)
    monkeypatch.setattr(subprocess, "Popen", lambda *_args, **_kwargs: process)

    with pytest.raises(HermesCliError) as exc_info:
        _adapter(tmp_path).generate_report("生成教学报告")

    assert exc_info.value.code == "unsafe_output"
    assert secret not in exc_info.value.message


def test_prompt_length_is_checked_before_process_start(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    started = False

    def fake_popen(*_args: object, **_kwargs: object) -> FakeProcess:
        nonlocal started
        started = True
        return FakeProcess(stdout="never")

    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    with pytest.raises(HermesCliError) as exc_info:
        _adapter(tmp_path).generate_report("x" * (MAX_PROMPT_CHARS + 1))

    assert exc_info.value.code == "prompt_too_long"
    assert started is False


def test_non_windows_timeout_kills_process(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    process = FakeProcess(stdout="late", timeout_once=True)
    monkeypatch.setattr(subprocess, "Popen", lambda *_args, **_kwargs: process)

    with pytest.raises(HermesCliError):
        _adapter(tmp_path, use_windows_taskkill=False).generate_report("生成教学报告")

    assert process.killed is True
