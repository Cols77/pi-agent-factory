from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

pytestmark = pytest.mark.unit

HOOKS = Path(__file__).parents[3] / ".claude" / "hooks"


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, HOOKS / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def guard() -> ModuleType:
    return _load("coherence_channel_guard")


@pytest.fixture(scope="module")
def gate() -> ModuleType:
    return _load("coherence_finalize_gate")


# --- channel guard -------------------------------------------------------


@pytest.mark.parametrize(
    "command",
    ["ls -la", "git status", "rtk proxy uv run pytest -q", "echo coherence is a word"],
)
def test_guard_allows_unrelated_commands(guard: ModuleType, command: str) -> None:
    assert guard.decide(command) is None


@pytest.mark.parametrize(
    "verb", ["start", "resume", "append", "resolve", "finalize", "bootstrap", "check", "handoff"]
)
def test_guard_denies_direct_backend_planning_calls(guard: ModuleType, verb: str) -> None:
    reason = guard.decide(f"uv run coherence plan {verb} --run-id r --project-root .")

    assert reason is not None
    assert "adapter" in reason


@pytest.mark.parametrize(
    "command",
    [
        "uv run python -m coherence.planning.guided_entrypoint start --run-id r --prompt p",
        "uv run python -m coherence.planning.guided_pipeline check --run-id r --intent i "
        "--spec s --plan p",
        "uv run python -m coherence.planning.legal_actions_adapter r",
        "uv run python -m coherence.planning.artifact_navigator FEAT-018",
    ],
)
def test_guard_allows_the_sanctioned_adapters(guard: ModuleType, command: str) -> None:
    assert guard.decide(command) is None


def test_guard_denies_planning_verbs_outside_the_implemented_set(guard: ModuleType) -> None:
    assert guard.decide("uv run coherence plan adopt --run-id r") is not None


# --- finalize gate -------------------------------------------------------


def _journal(root: Path, run_id: str, events: list[dict]) -> None:
    path = root / ".factory" / "planning" / run_id / "capture" / "events.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(event) + "\n" for event in events), encoding="utf-8")


def _answer(sequence: int, source: str) -> dict:
    return {
        "run_id": "FEAT-018",
        "sequence": sequence,
        "kind": "answer_captured",
        "payload": {"id": f"a{sequence}", "question": "q", "text": "t", "source": source},
    }


FINALIZE = (
    "uv run python -m coherence.planning.guided_entrypoint finalize "
    "--run-id FEAT-018 --project-root . --status provisional"
)


def test_gate_ignores_commands_that_are_not_finalize(gate: ModuleType, tmp_path: Path) -> None:
    assert (
        gate.decide(
            tmp_path,
            "uv run python -m coherence.planning.guided_entrypoint status --run-id FEAT-018",
        )
        is None
    )


def test_gate_denies_when_no_review_record_exists(gate: ModuleType, tmp_path: Path) -> None:
    _journal(
        tmp_path,
        "FEAT-018",
        [
            {
                "run_id": "FEAT-018",
                "sequence": 1,
                "kind": "capture_started",
                "payload": {"prompt": "p"},
            },
            _answer(2, "user"),
        ],
    )

    reason = gate.decide(tmp_path, FINALIZE)

    assert reason is not None
    assert "intent-review-agent" in reason


def test_gate_allows_once_the_review_verdict_is_recorded(
    gate: ModuleType, tmp_path: Path
) -> None:
    _journal(
        tmp_path,
        "FEAT-018",
        [
            {
                "run_id": "FEAT-018",
                "sequence": 1,
                "kind": "capture_started",
                "payload": {"prompt": "p"},
            },
            _answer(2, "user"),
            _answer(3, "intent-review-agent"),
        ],
    )

    assert gate.decide(tmp_path, FINALIZE) is None


def test_gate_denies_while_a_raised_challenge_has_no_disposition(
    gate: ModuleType, tmp_path: Path
) -> None:
    _journal(
        tmp_path,
        "FEAT-018",
        [
            {
                "run_id": "FEAT-018",
                "sequence": 1,
                "kind": "capture_started",
                "payload": {"prompt": "p"},
            },
            _answer(2, "intent-review-agent"),
            {
                "run_id": "FEAT-018",
                "sequence": 3,
                "kind": "challenge_raised",
                "payload": {"id": "challenge-a2-evidence"},
            },
        ],
    )

    reason = gate.decide(tmp_path, FINALIZE)

    assert reason is not None
    assert "challenge-a2-evidence" in reason


def test_gate_allows_once_every_challenge_is_dispositioned(
    gate: ModuleType, tmp_path: Path
) -> None:
    _journal(
        tmp_path,
        "FEAT-018",
        [
            {
                "run_id": "FEAT-018",
                "sequence": 1,
                "kind": "capture_started",
                "payload": {"prompt": "p"},
            },
            _answer(2, "intent-review-agent"),
            {
                "run_id": "FEAT-018",
                "sequence": 3,
                "kind": "challenge_raised",
                "payload": {"id": "challenge-a2-evidence"},
            },
            {
                "run_id": "FEAT-018",
                "sequence": 4,
                "kind": "challenge_resolved",
                "payload": {"id": "challenge-a2-evidence", "resolution": "defer"},
            },
        ],
    )

    assert gate.decide(tmp_path, FINALIZE) is None


def test_gate_denies_when_the_journal_is_missing_entirely(
    gate: ModuleType, tmp_path: Path
) -> None:
    assert gate.decide(tmp_path, FINALIZE) is not None


def test_gate_refuses_an_unsafe_run_id_rather_than_reading_a_path(
    gate: ModuleType, tmp_path: Path
) -> None:
    reason = gate.decide(
        tmp_path,
        "uv run python -m coherence.planning.guided_entrypoint finalize "
        "--run-id ../../etc --status provisional",
    )

    assert reason is not None


# --- challenge surface ---------------------------------------------------


@pytest.fixture(scope="module")
def surface() -> ModuleType:
    return _load("coherence_challenge_surface")


def test_surface_reports_nothing_when_no_challenge_is_unresolved(surface: ModuleType) -> None:
    payload = {"ok": True, "challenges": [{"id": "c1", "status": "deferred"}]}

    assert surface.summarize(payload) is None


def test_surface_lists_every_unresolved_challenge_verbatim(surface: ModuleType) -> None:
    payload = {
        "ok": True,
        "challenges": [
            {
                "id": "c1",
                "status": "unresolved",
                "kind": "unsupported_claim",
                "claim": "This always works",
                "rationale": "No evidence.",
                "evidence_needed": "a citation",
            },
            {
                "id": "c2",
                "status": "resolved",
                "kind": "tradeoff",
                "claim": "x",
                "rationale": "y",
                "evidence_needed": "z",
            },
        ],
    }

    text = surface.summarize(payload)

    assert "c1" in text
    assert "This always works" in text
    assert "a citation" in text
    assert "c2" not in text


def test_surface_ignores_payloads_that_are_not_ok(surface: ModuleType) -> None:
    assert surface.summarize({"ok": False, "error": "boom"}) is None


def test_surface_tolerates_a_malformed_payload(surface: ModuleType) -> None:
    assert surface.summarize({"ok": True, "challenges": "nope"}) is None


def test_settings_register_every_hook() -> None:
    settings = json.loads(
        (Path(__file__).parents[3] / ".claude" / "settings.json").read_text(encoding="utf-8")
    )
    serialized = json.dumps(settings)

    assert "coherence_channel_guard.py" in serialized
    assert "coherence_finalize_gate.py" in serialized
    assert "coherence_challenge_surface.py" in serialized
    assert '"PreToolUse"' in serialized
    assert '"PostToolUse"' in serialized
