from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from coherence.planning.adapter_backend import BackendError, invoke_backend, require_safe_run_id
from tests.unit._legal_actions_json import completed_json

pytestmark = pytest.mark.unit


def test_require_safe_run_id_accepts_the_shared_grammar() -> None:
    require_safe_run_id("FEAT-018")
    require_safe_run_id("run-001")


@pytest.mark.parametrize("run_id", ["", "../escape", "run 001", "run;rm -rf", "-run", "run/001"])
def test_require_safe_run_id_rejects_unsafe_ids(run_id: str) -> None:
    with pytest.raises(BackendError, match="safe run-id grammar"):
        require_safe_run_id(run_id)


@pytest.mark.parametrize("exit_code", [0, 1])
def test_trusted_exit_codes_return_stdout(monkeypatch: pytest.MonkeyPatch, exit_code: int) -> None:
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **k: completed_json({"ok": True}, returncode=exit_code)
    )

    code, stdout = invoke_backend(["uv", "run", "coherence", "plan", "status"], Path("/p"))

    assert code == exit_code
    assert json.loads(stdout) == {"ok": True}


@pytest.mark.parametrize("exit_code", [2, 3, 127])
def test_untrusted_exit_codes_never_return_stdout(
    monkeypatch: pytest.MonkeyPatch, exit_code: int
) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: completed_json({"ok": True}, returncode=exit_code, stderr="segfault"),
    )

    with pytest.raises(BackendError, match="segfault"):
        invoke_backend(["uv", "run", "coherence", "plan", "status"], Path("/p"))


def test_untrusted_exit_with_no_stderr_still_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **k: completed_json({}, returncode=2, stderr="")
    )

    with pytest.raises(BackendError, match="backend exited unsuccessfully"):
        invoke_backend(["uv", "run", "coherence"], Path("/p"))


def test_launch_failure_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*a: Any, **k: Any) -> None:
        raise OSError("uv not found")

    monkeypatch.setattr(subprocess, "run", boom)

    with pytest.raises(BackendError, match="uv not found"):
        invoke_backend(["uv"], Path("/p"))


def test_invocation_never_uses_a_shell(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def capture(command: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        seen.update(command=command, kwargs=kwargs)
        return completed_json({}, returncode=0)

    monkeypatch.setattr(subprocess, "run", capture)
    invoke_backend(["uv", "run", "coherence"], Path("/p"))

    assert isinstance(seen["command"], list)
    assert seen["kwargs"]["shell"] is False
