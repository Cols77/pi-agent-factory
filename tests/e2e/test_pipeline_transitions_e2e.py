"""Real-LLM end-to-end pipeline transition tests.

These run the REAL orchestrator (`run_next`) with a REAL `PiAgentBackend`
(a cheap OpenRouter model), REAL git (`SubprocessGitOps`) and REAL gate
subprocesses against a throwaway factory workspace seeded with a dumb task.
They exist to catch integration bugs the fake-backed unit tests cannot -- e.g.
`commit_all` crashing on a real `git add -A`, or the JSON/handshake wiring only
exercised end to end.

They are marked `e2e` (excluded from the default `-m unit` run) and SKIP unless
BOTH `OPENROUTER_API_KEY` and `OPENROUTER_MODEL` are set. Validated config:

    OPENROUTER_API_KEY=... OPENROUTER_MODEL=deepseek/deepseek-v4-flash:low \
        uv run python -m pytest tests/e2e -m e2e -v

NOTE on the model: use the plain slug (`deepseek/deepseek-v4-flash`), NOT an
`openrouter/`-prefixed one (double-prefix makes pi fall back to plain text with
no `--mode json` events). Thinking level matters: at a HIGH thinking level the
model tool-calls/thinks without concluding with the manifest, so context-gather
rejects -- the `:low` thinking shorthand (as above) or a non-thinking model lets
it emit the manifest. The happy path was verified green with the config above.
If a cheaper model stalls a stage, tune `_write_task`/`_write_gates`.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from factory.orchestrator.backends import SubprocessGateRunner
from factory.orchestrator.git_ops import SubprocessGitOps
from factory.orchestrator.human_review import Annotation, HumanReviewDecision
from factory.orchestrator.pi_backend import PiAgentBackend
from factory.orchestrator.runner import run_next
from factory.orchestrator.status import FakeStatusReporter

pytestmark = pytest.mark.e2e

REAL_REPO = Path(__file__).resolve().parents[2]
SCOPE_GUARD_EXT = REAL_REPO / "pi-ext" / "scope-guard" / "src" / "index.ts"

# Every skill any invoked role loads via compose_prompt -> load_skill_block
# (hard-required). Stubbed so the real prompts compose without shipping content.
_SKILL_NAMES = [
    "verification-before-completion", "context-completeness-audit",
    "test-driven-development", "systematic-debugging", "receiving-code-review",
    "kb-lookup", "requesting-code-review", "coding-principles", "session-report",
]


def _requires_creds() -> None:
    if not os.environ.get("OPENROUTER_API_KEY") or not os.environ.get("OPENROUTER_MODEL"):
        pytest.skip("set OPENROUTER_API_KEY and OPENROUTER_MODEL to run the e2e pipeline tests")


class ScriptedGate:
    """In-process human-review gate that returns pre-scripted decisions, so a
    test can drive approve/reject without an interactive UI. Exercises the real
    run_task loop + real git commit-on-approve (where the recent crash lived)."""

    def __init__(self, decisions: list[HumanReviewDecision]) -> None:
        self._decisions = list(decisions)
        self.requests: list[tuple[str, str]] = []

    def request_review(self, task_id: str, start_commit: str) -> HumanReviewDecision:
        self.requests.append((task_id, start_commit))
        assert self._decisions, "ScriptedGate: ran out of scripted decisions"
        return self._decisions.pop(0)


def _write_skills(ws: Path) -> None:
    # Copy the REAL vendored skills (not stubs). The full content is what the
    # role prompts actually load, and it pushes the prompt past pi_backend's
    # inline-arg limit so the prompt is delivered via `@file` -- matching the
    # real factory, whose runs produce the `--mode json` event stream a minimal
    # stub workspace (short, inline `-p` prompt) did not.
    src = REAL_REPO / ".pi" / "skills"
    if src.exists():
        shutil.copytree(src, ws / ".pi" / "skills")
        return
    for name in _SKILL_NAMES:  # fallback: stubs (won't match the real prompt)
        d = ws / ".pi" / "skills" / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: stub for e2e tests\n---\n\nStub content for {name}.\n",
            encoding="utf-8",
        )


def _write_gates(ws: Path) -> None:
    # Trivial gates that always pass, so the pipeline flows through every stage
    # and we assert on TRANSITIONS, not dev correctness. Make them stricter
    # (e.g. assert the deliverable exists) to also gate on real work.
    gdir = ws / "scripts" / "gates"
    gdir.mkdir(parents=True, exist_ok=True)
    for name in ("unit.py", "sim_smoke.py", "all.py"):
        (gdir / name).write_text("import sys\nprint('gate ok')\nsys.exit(0)\n", encoding="utf-8")


def _write_plan(ws: Path) -> None:
    # context-gather must prove the task is coherent with a plan/spec, so give
    # it a plan the task references. Without one it rejects (can't prove
    # coherence) and dev never runs.
    (ws / "docs").mkdir(parents=True, exist_ok=True)
    (ws / "docs" / "plan.md").write_text(
        "# Plan: answer module\n\n"
        "## Task 1: Answer constant\n\n"
        "Create `src/answer.py` defining the module-level constant `ANSWER = 42`, "
        "and `tests/test_answer.py` asserting `ANSWER == 42`.\n\n"
        "Definition of Done: `src/answer.py` defines `ANSWER = 42`; "
        "`tests/test_answer.py` imports it and passes.\n",
        encoding="utf-8",
    )


def _write_task(ws: Path) -> None:
    (ws / "tasks").mkdir(parents=True, exist_ok=True)
    (ws / "tasks" / "T-900-answer.md").write_text(
        "---\n"
        "id: T-900\n"
        "title: Answer constant\n"
        "status: todo\n"
        "source_plan: docs/plan.md\n"
        "source_task: 1\n"
        "dod:\n"
        "  - '`ANSWER` constant equal to 42 in `src/answer.py`; `tests/test_answer.py` passes'\n"
        "---\n"
        "- Create: `src/answer.py`\n"
        "- Test: `tests/test_answer.py`\n\n"
        "Implements Task 1 of `docs/plan.md`: define `ANSWER = 42` in "
        "`src/answer.py` and a test asserting it.\n",
        encoding="utf-8",
    )


def _git(ws: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=ws, check=True, capture_output=True, text=True)


def _build_workspace(tmp_path: Path, *, deliverables_already_exist: bool = False) -> Path:
    ws = tmp_path / "ws"
    ws.mkdir()
    _write_skills(ws)
    _write_gates(ws)
    _write_plan(ws)
    _write_task(ws)
    for sub in ("sessions", "kb", "context-manifests", "src", "tests"):
        (ws / sub).mkdir(parents=True, exist_ok=True)
    if deliverables_already_exist:
        # Pre-create + commit the task's deliverables so context-gather can emit
        # already_done (the routing that crashed on approve before 8bc1bfd).
        (ws / "src" / "answer.py").write_text("ANSWER = 42\n", encoding="utf-8")
        (ws / "tests" / "test_answer.py").write_text(
            "from src.answer import ANSWER\n\n\ndef test_answer():\n    assert ANSWER == 42\n",
            encoding="utf-8",
        )
    _git(ws, "init", "-q")
    _git(ws, "config", "user.email", "e2e@example.com")
    _git(ws, "config", "user.name", "e2e")
    _git(ws, "add", "-A")
    _git(ws, "commit", "-q", "-m", "init e2e workspace")
    return ws


def _run(ws: Path, gate: ScriptedGate) -> tuple[Path | None, FakeStatusReporter]:
    backend = PiAgentBackend(
        repo_root=ws, extension_path=SCOPE_GUARD_EXT,
        provider="openrouter", model=os.environ["OPENROUTER_MODEL"],
    )
    transcript_dir = ws / "sessions" / ".factory-transcripts" / "e2e"
    gates = SubprocessGateRunner(ws, log_dir=transcript_dir)
    status = FakeStatusReporter()
    path = run_next(
        ws, backend, gates,
        session_id="e2e", task_id="T-900", status=status,
        human_review=gate, git_ops=SubprocessGitOps(), transcript_dir=transcript_dir,
    )
    return path, status


def _nodes(status: FakeStatusReporter) -> list[str]:
    return [c["node"] for c in status.calls]


def test_happy_path_runs_every_stage_through_session_review(tmp_path: Path) -> None:
    _requires_creds()
    ws = _build_workspace(tmp_path)
    path, status = _run(ws, ScriptedGate([HumanReviewDecision("approve", [])]))

    nodes = _nodes(status)
    for stage in ("context-gather", "dev", "validation", "review", "human-review", "session-review"):
        assert stage in nodes, f"stage {stage!r} never ran; saw {sorted(set(nodes))}"
    assert path is not None  # session record written
    assert any(c["node"] == "human-review" and c["node_state"] == "approved" for c in status.calls)


def test_reject_then_approve_returns_to_human_and_completes(tmp_path: Path) -> None:
    _requires_creds()
    ws = _build_workspace(tmp_path)
    gate = ScriptedGate([
        HumanReviewDecision("reject", [Annotation(file="src/answer.py", body="add a module docstring")]),
        HumanReviewDecision("approve", []),
    ])
    path, status = _run(ws, gate)

    hr_states = [c["node_state"] for c in status.calls if c["node"] == "human-review"]
    assert hr_states[:1] == ["blocked"]
    assert "changes-requested" in hr_states     # the reject was recorded
    assert hr_states[-1] == "approved"          # we came back and approved
    assert len(gate.requests) == 2              # human was consulted twice
    assert "session-review" in _nodes(status)
    assert path is not None


def test_already_done_approve_completes_without_crashing(tmp_path: Path) -> None:
    # Regression for the commit_all crash: an already-done task's approve runs
    # `git add -A` with nothing to commit -- must complete and reach session-review.
    _requires_creds()
    ws = _build_workspace(tmp_path, deliverables_already_exist=True)
    path, status = _run(ws, ScriptedGate([HumanReviewDecision("approve", [])]))

    nodes = _nodes(status)
    assert "human-review" in nodes
    assert any(c["node"] == "human-review" and c["node_state"] == "approved" for c in status.calls)
    assert "session-review" in nodes            # the pipeline was NOT stranded
    assert not any(c["node"] == "orchestrator" and c["node_state"] == "error" for c in status.calls)
    assert path is not None
