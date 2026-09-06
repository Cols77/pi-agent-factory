from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

pytestmark = pytest.mark.unit

HOOKS = Path(__file__).parents[3] / ".claude" / "hooks"

# coherence_channel_guard.py and coherence_finalize_gate.py both import the
# shared `_shell_segments` helper module from this directory by its bare
# name; when Claude Code runs a hook as `uv run python <path>`, the
# interpreter puts the script's own directory on `sys.path` automatically, but
# `_load` below (spec_from_file_location + exec_module) does not, so it must
# be added here for that same bare import to resolve under pytest.
if str(HOOKS) not in sys.path:
    sys.path.insert(0, str(HOOKS))


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


def test_guard_denies_a_raw_call_disguised_by_a_trailing_comment(guard: ModuleType) -> None:
    reason = guard.decide(
        "uv run coherence plan finalize --run-id FEAT-018 --project-root . "
        "--status provisional  # coherence.planning.guided_entrypoint"
    )

    assert reason is not None


def test_guard_denies_a_raw_call_chained_before_a_sanctioned_one(guard: ModuleType) -> None:
    reason = guard.decide(
        "uv run coherence plan finalize --run-id FEAT-018 --project-root . --status provisional "
        "&& uv run python -m coherence.planning.guided_entrypoint status --run-id FEAT-018 "
        "--project-root ."
    )

    assert reason is not None


def test_guard_denies_a_raw_call_that_merely_mentions_an_adapter_in_an_argument(
    guard: ModuleType,
) -> None:
    reason = guard.decide(
        'uv run coherence plan start --run-id r --prompt '
        '"see coherence.planning.guided_entrypoint for context"'
    )

    assert reason is not None


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


def test_gate_denies_the_same_finalize_call_by_script_path_instead_of_dash_m(
    gate: ModuleType, tmp_path: Path
) -> None:
    """No journal exists in `tmp_path`; the path-form spelling must be
    recognized and denied exactly as the `-m` form is."""
    reason = gate.decide(
        tmp_path,
        "uv run python src/coherence/planning/guided_entrypoint.py finalize "
        "--run-id FEAT-018 --project-root . --status provisional",
    )

    assert reason is not None


def test_gate_uses_the_last_run_id_like_argparse_does(gate: ModuleType, tmp_path: Path) -> None:
    """`argparse`'s `store` action keeps the LAST `--run-id`; a duplicated
    flag must not let the gate check a clean run while the real CLI finalizes
    a different, unreviewed one."""
    _journal(
        tmp_path,
        "reviewed-run",
        [
            {
                "run_id": "reviewed-run",
                "sequence": 1,
                "kind": "capture_started",
                "payload": {"prompt": "p"},
            },
            _answer(2, "intent-review-agent"),
        ],
    )

    reason = gate.decide(
        tmp_path,
        "uv run python -m coherence.planning.guided_entrypoint finalize "
        "--run-id reviewed-run --run-id X --project-root . --status provisional",
    )

    assert reason is not None
    assert "X" in reason


def test_gate_ignores_the_adapter_and_finalize_words_in_an_unrelated_commit_message(
    gate: ModuleType, tmp_path: Path
) -> None:
    reason = gate.decide(
        tmp_path,
        'git commit -m "docs: mention coherence.planning.guided_entrypoint finalize flow"',
    )

    assert reason is None


def test_gate_denies_finalize_reached_through_a_preceding_cd(
    gate: ModuleType, tmp_path: Path
) -> None:
    """A `cd` before the adapter call makes the project root the backend will
    actually run against different from the one this gate can check."""
    _journal(
        tmp_path,
        "reviewed-run",
        [
            {
                "run_id": "reviewed-run",
                "sequence": 1,
                "kind": "capture_started",
                "payload": {"prompt": "p"},
            },
            _answer(2, "intent-review-agent"),
        ],
    )

    reason = gate.decide(
        tmp_path,
        "cd /tmp/other-project && uv run python -m coherence.planning.guided_entrypoint "
        "finalize --run-id reviewed-run --project-root . --status provisional",
    )

    assert reason is not None


def test_gate_denies_finalize_reached_through_inline_python_exec(
    gate: ModuleType, tmp_path: Path
) -> None:
    reason = gate.decide(
        tmp_path,
        "uv run python -c \"from coherence.planning.guided_entrypoint import main; "
        "main(['finalize','--run-id','FEAT-018'])\"",
    )

    assert reason is not None


def test_gate_imports_the_shared_run_id_grammar_rather_than_restating_it(
    gate: ModuleType,
) -> None:
    from coherence.planning.legal_actions_adapter import SAFE_RUN_ID

    assert gate.SAFE_RUN_ID is SAFE_RUN_ID


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


def _finalize_review_agent_hook() -> dict:
    settings = json.loads(
        (Path(__file__).parents[3] / ".claude" / "settings.json").read_text(encoding="utf-8")
    )
    for entry in settings["hooks"]["PreToolUse"]:
        for hook in entry.get("hooks", []):
            if hook.get("type") == "agent":
                return hook
    raise AssertionError("no PreToolUse agent hook found in settings.json")


def test_finalize_review_agent_is_advisory_not_a_content_veto() -> None:
    """A hook may only enforce procedural facts, never judge whether content
    is good (that judgment already belongs to `coherence_finalize_gate.py`'s
    deterministic review-record check). The review agent must record its
    findings and always allow -- it must never withhold the tool call on its
    own opinion of whether the captured intent is adequate."""
    prompt = _finalize_review_agent_hook()["prompt"].lower()

    assert '"ok": false' not in prompt
    assert '"ok": true' in prompt
    assert "never" in prompt and ("veto" in prompt or "withhold" in prompt or "delay" in prompt)
