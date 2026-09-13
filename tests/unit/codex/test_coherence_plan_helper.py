from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

pytestmark = pytest.mark.unit

HELPER_PATH = (
    Path(__file__).parents[3]
    / ".agents"
    / "skills"
    / "coherence-plan"
    / "scripts"
    / "coherence_plan.py"
)


@pytest.fixture
def helper() -> ModuleType:
    spec = importlib.util.spec_from_file_location("coherence_plan_helper", HELPER_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def projection(*, run_id: str = "run-001", blocked: bool = False) -> dict[str, Any]:
    legal_ids = [
        "author-requirements",
        "record-sr-consent",
        "author-spec",
        "author-plan",
        "review-spec",
        "review-plan",
        "run-planning-gates",
        "create-handoff",
        "inspect-handoff",
    ]
    return {
        "schema": 2,
        "run_id": run_id,
        "blocked": blocked,
        "reason": "NEEDS_REVIEW" if blocked else None,
        "legal_next_actions": [] if blocked else ["author-spec"],
        "starts_automatically": False,
        "state": "intent_provisional",
        "run_identity": None if blocked else {
            "run_id": run_id,
            "next_sequence": 2,
            "journal_sha256": "a" * 64,
        },
        "action_registry": {
            "schema": 1,
            "legal_ids": legal_ids,
            "registry_hash": hashlib.sha256("\n".join(legal_ids).encode()).hexdigest(),
        },
    }


def test_query_uses_exact_argv_and_safe_subprocess_options(
    helper: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[list[str], dict[str, Any]]] = []
    expected = [
        "uv",
        "run",
        "coherence",
        "plan",
        "legal-actions",
        "--project-root",
        str(tmp_path),
        "--run-id",
        "run-001",
        "--json",
    ]

    def fake_run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, 0, json.dumps(projection()), "")

    monkeypatch.setattr(helper.subprocess, "run", fake_run)

    assert helper.build_legal_actions_command(tmp_path, "run-001") == expected
    assert helper.query_legal_actions(tmp_path, "run-001") == projection()
    assert calls == [
        (
            expected,
            {
                "cwd": tmp_path,
                "capture_output": True,
                "text": True,
                "check": False,
                "shell": False,
            },
        )
    ]
    assert all(isinstance(argument, str) for argument in calls[0][0])


def test_unsafe_run_id_is_rejected_without_spawning(
    helper: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spawned = False

    def fail_if_spawned(*args: Any, **kwargs: Any) -> None:
        nonlocal spawned
        spawned = True

    monkeypatch.setattr(helper.subprocess, "run", fail_if_spawned)

    with pytest.raises(ValueError):
        helper.query_legal_actions(tmp_path, "run 001")

    assert spawned is False


def test_project_root_must_be_a_directory(helper: ModuleType, tmp_path: Path) -> None:
    project_file = tmp_path / "project.txt"
    project_file.write_text("not a directory", encoding="utf-8")

    with pytest.raises(ValueError):
        helper.build_legal_actions_command(project_file, "run-001")


def test_ready_projection_is_returned_for_backend_exit_zero(
    helper: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = projection()
    monkeypatch.setattr(
        helper.subprocess,
        "run",
        lambda argv, **kwargs: subprocess.CompletedProcess(
            argv, 0, json.dumps(payload), ""
        ),
    )

    assert helper.query_legal_actions(tmp_path, "run-001") == payload


def test_blocked_projection_is_returned_for_backend_exit_one(
    helper: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = projection(blocked=True)
    monkeypatch.setattr(
        helper.subprocess,
        "run",
        lambda argv, **kwargs: subprocess.CompletedProcess(
            argv, 1, json.dumps(payload), ""
        ),
    )

    assert helper.query_legal_actions(tmp_path, "run-001") == payload


def test_exit_zero_rejects_blocked_projection(
    helper: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = projection(blocked=True)
    monkeypatch.setattr(
        helper.subprocess,
        "run",
        lambda argv, **kwargs: subprocess.CompletedProcess(
            argv, 0, json.dumps(payload), ""
        ),
    )

    with pytest.raises(ValueError, match="contradicts blocked projection"):
        helper.query_legal_actions(tmp_path, "run-001")


def test_exit_one_rejects_ready_projection(
    helper: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = projection()
    monkeypatch.setattr(
        helper.subprocess,
        "run",
        lambda argv, **kwargs: subprocess.CompletedProcess(
            argv, 1, json.dumps(payload), ""
        ),
    )

    with pytest.raises(ValueError, match="contradicts ready projection"):
        helper.query_legal_actions(tmp_path, "run-001")


def test_relative_project_root_is_resolved_once_for_command_and_cwd(
    helper: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    relative_root = Path("relative-project")
    (tmp_path / relative_root).mkdir()
    monkeypatch.chdir(tmp_path)

    original_resolve = Path.resolve
    resolve_calls: list[Path] = []
    calls: dict[str, Any] = {}

    def track_resolve(path: Path, *args: Any, **kwargs: Any) -> Path:
        resolve_calls.append(path)
        return original_resolve(path, *args, **kwargs)

    def fake_run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls["argv"] = argv
        calls["kwargs"] = kwargs
        return subprocess.CompletedProcess(argv, 0, json.dumps(projection()), "")

    monkeypatch.setattr(Path, "resolve", track_resolve)
    monkeypatch.setattr(helper.subprocess, "run", fake_run)

    assert helper.query_legal_actions(relative_root, "run-001") == projection()

    resolved_root = tmp_path / relative_root
    assert resolve_calls == [relative_root]
    assert calls["argv"][6] == str(resolved_root)
    assert calls["kwargs"]["cwd"] == resolved_root


@pytest.mark.parametrize(
    "raw",
    [
        "not json",
        json.dumps({"schema": "1"}),
        json.dumps({**projection(), "schema": 1}),
        json.dumps({**projection(), "schema": True}),
        json.dumps({**projection(), "run_id": "run-002"}),
        json.dumps({**projection(), "blocked": "false"}),
        json.dumps({**projection(), "reason": 7}),
        json.dumps({**projection(), "legal_next_actions": ["author-spec", 7]}),
        json.dumps({**projection(), "starts_automatically": True}),
    ],
)
def test_invalid_projection_is_rejected(helper: ModuleType, raw: str) -> None:
    with pytest.raises(ValueError):
        helper.parse_projection(raw, "run-001")


def test_unexpected_backend_exit_is_rejected_even_with_valid_stdout(
    helper: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = projection()
    monkeypatch.setattr(
        helper.subprocess,
        "run",
        lambda argv, **kwargs: subprocess.CompletedProcess(
            argv, 2, json.dumps(payload), "unexpected backend failure"
        ),
    )

    with pytest.raises(ValueError, match="unexpected status 2"):
        helper.query_legal_actions(tmp_path, "run-001")


def test_main_prints_ready_projection_and_returns_zero(
    helper: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    payload = projection()
    monkeypatch.setattr(helper, "query_legal_actions", lambda root, run_id: payload)

    result = helper.main(
        ["legal-actions", "--project-root", str(tmp_path), "--run-id", "run-001"]
    )

    assert result == 0
    assert json.loads(capsys.readouterr().out) == payload


def test_main_prints_blocked_projection_and_returns_one(
    helper: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    payload = projection(blocked=True)
    monkeypatch.setattr(helper, "query_legal_actions", lambda root, run_id: payload)

    result = helper.main(
        ["legal-actions", "--project-root", str(tmp_path), "--run-id", "run-001"]
    )

    assert result == 1
    assert json.loads(capsys.readouterr().out) == payload


def test_main_emits_backend_invalid_projection_for_missing_run_id(
    helper: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = helper.main(["legal-actions", "--project-root", str(tmp_path)])
    output = json.loads(capsys.readouterr().out)

    assert result == 1
    assert output == {
        "schema": 2,
        "run_id": "",
        "blocked": True,
        "reason": "BACKEND_INVALID",
        "legal_next_actions": [],
        "starts_automatically": False,
        "error": "invalid command-line arguments",
    }


@pytest.mark.parametrize(
    "error", [OSError("spawn failed"), RuntimeError("boom"), ValueError("bad JSON")]
)
def test_main_emits_backend_invalid_projection_for_helper_errors(
    helper: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    error: Exception,
) -> None:
    def fail(root: Path, run_id: str) -> dict[str, Any]:
        raise error

    monkeypatch.setattr(helper, "query_legal_actions", fail)

    result = helper.main(
        ["legal-actions", "--project-root", str(tmp_path), "--run-id", "run-001"]
    )
    output = json.loads(capsys.readouterr().out)

    assert result == 1
    assert output == {
        "schema": 2,
        "run_id": "run-001",
        "blocked": True,
        "reason": "BACKEND_INVALID",
        "legal_next_actions": [],
        "starts_automatically": False,
        "error": str(error),
    }
