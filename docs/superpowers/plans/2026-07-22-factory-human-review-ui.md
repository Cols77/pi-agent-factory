# Human Code Review UI for the Factory Pipeline — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a human-in-the-loop code review gate to the factory pipeline, with an efficient TUI review UI (file-list summary + full-width diff drill-down) inside `pif`, wired through a blocking stdio JSON-lines handshake between the Python orchestrator and the TypeScript pi extension.

**Architecture:** `run_task` (Python) gains an optional `HumanReviewGate` dependency; when present, it writes one JSON line to stdout after automated review passes and blocks on `stdin.readline()` for a decision. The pif extension, when `/factory`/`/factory-run` run without `--auto`, spawns the orchestrator non-detached with piped stdio, reads that line, shows a review overlay (`ctx.ui.custom`), and writes the decision back to the child's stdin.

**Tech Stack:** Python (factory orchestrator, pytest), TypeScript (`pi-ext/factory-watch`, vitest, `@earendil-works/pi-tui`/`pi-coding-agent`).

## Global Constraints

- `--auto` on `/factory`/`/factory-run` (and the orchestrator's own `--auto` CLI flag) must reproduce today's exact behavior unchanged: detached spawn, status-file polling only, no gate, fully automated review decision. This is the existing, already-tested code path — do not alter it.
- Comments are file-level, not line-level (see design spec, Non-Goals).
- `e` (edit) only supports GUI/wait-mode editors, or a tmux `split-window`+`wait-for` path when `$TMUX` is set. Never attempt a known terminal editor directly against the same terminal pi-tui owns — that corrupts the display. Fail with a clear error instead.
- Reject requires at least one comment. Approve commits any uncommitted working-tree changes (from `e`) before the task is marked done, so the pipeline's existing "committed" DoD item still holds.
- Human review comments feed into the *same* `feedback: str | None` mechanism `run_task` already uses for automated-review findings — no new feedback channel.
- Design reference: `docs/superpowers/specs/2026-07-22-factory-human-review-ui-design.md`.

---

## File Structure

**Python (`src/factory/orchestrator/`):**
- `git_ops.py` (new) — `GitOps` protocol (`head_commit`, `commit_all`), `SubprocessGitOps`, `FakeGitOps`.
- `human_review.py` (new) — `HumanReviewDecision`, `HumanReviewGate` protocol, `StdioHumanReviewGate`, `FakeHumanReviewGate`, `format_review_feedback`.
- `runner.py` (modify) — `run_task`/`run_next` gain `human_review`/`git_ops` params.
- `__main__.py` (modify) — `--auto` flag; regular output moves to stderr so stdout is free for the JSON-lines protocol.

**TypeScript (`pi-ext/factory-watch/src/`):**
- `review-diff.ts` (new) — parse `git diff --stat`, compute per-file diff text.
- `review-editor-launch.ts` (new) — resolve an editor command; GUI-only guard; tmux-enhanced path.
- `review-protocol.ts` (new) — read `review_pending` JSON lines from a child's stdout; write a decision line to its stdin.
- `review-overlay.ts` (new) — the `ReviewOverlay` Component (summary + file drill-down) and the `runReviewLoop` async orchestrator; also extends `pi-types.ts`'s `UiApi` with `confirm`/`editor`.
- `pi-types.ts` (modify) — add `confirm`/`editor` to `UiApi`.
- `index.ts` (modify) — `--auto` flag parsing; new foreground/piped-stdio spawn path for `/factory` and `/factory-run`.

---

### Task 1: `git_ops.py`

**Files:**
- Create: `src/factory/orchestrator/git_ops.py`
- Test: `tests/unit/orchestrator/test_git_ops.py`

**Interfaces:**
- Produces: `GitOps` (Protocol: `head_commit(repo_root: Path) -> str`, `commit_all(repo_root: Path, message: str) -> bool`), `SubprocessGitOps`, `FakeGitOps(head: str = "0"*40, has_uncommitted: bool = False)` with `.commit_messages: list[str]`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/orchestrator/test_git_ops.py
from __future__ import annotations

import subprocess
import pytest
from factory.orchestrator.git_ops import FakeGitOps, SubprocessGitOps

pytestmark = pytest.mark.unit


def _init_repo(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    (tmp_path / "a.txt").write_text("one\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=tmp_path, check=True)
    return tmp_path


def test_subprocess_git_ops_head_commit_matches_rev_parse(tmp_path):
    repo = _init_repo(tmp_path)
    expected = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()
    assert SubprocessGitOps().head_commit(repo) == expected


def test_subprocess_git_ops_commit_all_returns_false_when_nothing_to_commit(tmp_path):
    repo = _init_repo(tmp_path)
    assert SubprocessGitOps().commit_all(repo, "no-op") is False


def test_subprocess_git_ops_commit_all_commits_uncommitted_changes(tmp_path):
    repo = _init_repo(tmp_path)
    (repo / "a.txt").write_text("two\n", encoding="utf-8")
    before = SubprocessGitOps().head_commit(repo)
    committed = SubprocessGitOps().commit_all(repo, "review: address direct edits during human review")
    assert committed is True
    after = SubprocessGitOps().head_commit(repo)
    assert after != before
    log = subprocess.run(
        ["git", "log", "-1", "--pretty=%s"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()
    assert log == "review: address direct edits during human review"


def test_fake_git_ops_records_commit_messages_only_when_has_uncommitted():
    clean = FakeGitOps(head="abc123", has_uncommitted=False)
    assert clean.head_commit(None) == "abc123"
    assert clean.commit_all(None, "msg") is False
    assert clean.commit_messages == []

    dirty = FakeGitOps(head="def456", has_uncommitted=True)
    assert dirty.commit_all(None, "msg") is True
    assert dirty.commit_messages == ["msg"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /c/coding/pi-agent-factory && uv run pytest tests/unit/orchestrator/test_git_ops.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'factory.orchestrator.git_ops'`

- [ ] **Step 3: Implement**

```python
# src/factory/orchestrator/git_ops.py
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Protocol


class GitOps(Protocol):
    def head_commit(self, repo_root: Path) -> str: ...
    def commit_all(self, repo_root: Path, message: str) -> bool: ...


class SubprocessGitOps:
    def head_commit(self, repo_root: Path) -> str:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo_root, capture_output=True, text=True, check=True,
        )
        return result.stdout.strip()

    def commit_all(self, repo_root: Path, message: str) -> bool:
        subprocess.run(["git", "add", "-A"], cwd=repo_root, check=True)
        staged = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=repo_root)
        if staged.returncode == 0:
            return False
        subprocess.run(["git", "commit", "-q", "-m", message], cwd=repo_root, check=True)
        return True


class FakeGitOps:
    def __init__(self, head: str = "0" * 40, has_uncommitted: bool = False) -> None:
        self.head = head
        self.has_uncommitted = has_uncommitted
        self.commit_messages: list[str] = []

    def head_commit(self, repo_root: Path) -> str:
        return self.head

    def commit_all(self, repo_root: Path, message: str) -> bool:
        if self.has_uncommitted:
            self.commit_messages.append(message)
            return True
        return False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /c/coding/pi-agent-factory && uv run pytest tests/unit/orchestrator/test_git_ops.py -v`
Expected: PASS (4/4)

- [ ] **Step 5: Commit**

```bash
git add src/factory/orchestrator/git_ops.py tests/unit/orchestrator/test_git_ops.py
git commit -m "feat: add GitOps for capturing/committing during human review"
```

---

### Task 2: `human_review.py`

**Files:**
- Create: `src/factory/orchestrator/human_review.py`
- Test: `tests/unit/orchestrator/test_human_review.py`

**Interfaces:**
- Consumes: nothing new (stdlib `json`, `sys`, `dataclasses`, `typing.Protocol`).
- Produces: `HumanReviewDecision(decision: str, comments: dict[str,str])`, `HumanReviewGate` (Protocol: `request_review(task_id: str, start_commit: str) -> HumanReviewDecision`), `StdioHumanReviewGate(stdout=sys.stdout, stdin=sys.stdin)`, `FakeHumanReviewGate(decisions: list[HumanReviewDecision])` with `.requests: list[tuple[str,str]]`, `format_review_feedback(comments: dict[str,str]) -> str`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/orchestrator/test_human_review.py
from __future__ import annotations

import io
import json
import pytest
from factory.orchestrator.human_review import (
    FakeHumanReviewGate,
    HumanReviewDecision,
    StdioHumanReviewGate,
    format_review_feedback,
)

pytestmark = pytest.mark.unit


def test_stdio_gate_writes_review_pending_line_and_reads_decision():
    decision_line = json.dumps({"decision": "approve", "comments": {}}) + "\n"
    stdin = io.StringIO(decision_line)
    stdout = io.StringIO()
    gate = StdioHumanReviewGate(stdout=stdout, stdin=stdin)

    result = gate.request_review("T-001", "abc123")

    written = json.loads(stdout.getvalue().strip())
    assert written == {"type": "review_pending", "task_id": "T-001", "start_commit": "abc123"}
    assert result == HumanReviewDecision(decision="approve", comments={})


def test_stdio_gate_parses_reject_with_comments():
    decision_line = json.dumps(
        {"decision": "reject", "comments": {"src/x.py": "fix this"}}
    ) + "\n"
    gate = StdioHumanReviewGate(stdout=io.StringIO(), stdin=io.StringIO(decision_line))

    result = gate.request_review("T-001", "abc123")

    assert result.decision == "reject"
    assert result.comments == {"src/x.py": "fix this"}


def test_stdio_gate_raises_eof_error_when_stdin_closes_without_a_decision():
    gate = StdioHumanReviewGate(stdout=io.StringIO(), stdin=io.StringIO(""))
    with pytest.raises(EOFError):
        gate.request_review("T-001", "abc123")


def test_fake_gate_records_requests_and_returns_scripted_decisions():
    gate = FakeHumanReviewGate([HumanReviewDecision("approve", {})])
    result = gate.request_review("T-002", "def456")
    assert result == HumanReviewDecision("approve", {})
    assert gate.requests == [("T-002", "def456")]


def test_format_review_feedback_lists_each_file_comment():
    text = format_review_feedback({"src/a.py": "missing check", "src/b.py": "typo"})
    assert text == (
        "human review requested changes:\n"
        "- src/a.py: missing check\n"
        "- src/b.py: typo"
    )


def test_format_review_feedback_with_no_comments():
    assert format_review_feedback({}) == "human review requested changes:"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /c/coding/pi-agent-factory && uv run pytest tests/unit/orchestrator/test_human_review.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'factory.orchestrator.human_review'`

- [ ] **Step 3: Implement**

```python
# src/factory/orchestrator/human_review.py
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from typing import IO, Protocol


@dataclass
class HumanReviewDecision:
    decision: str  # "approve" or "reject"
    comments: dict[str, str] = field(default_factory=dict)


class HumanReviewGate(Protocol):
    def request_review(self, task_id: str, start_commit: str) -> HumanReviewDecision: ...


class StdioHumanReviewGate:
    def __init__(self, stdout: IO[str] = sys.stdout, stdin: IO[str] = sys.stdin) -> None:
        self._stdout = stdout
        self._stdin = stdin

    def request_review(self, task_id: str, start_commit: str) -> HumanReviewDecision:
        self._stdout.write(
            json.dumps({"type": "review_pending", "task_id": task_id, "start_commit": start_commit}) + "\n"
        )
        self._stdout.flush()
        line = self._stdin.readline()
        if not line:
            raise EOFError("human review gate: stdin closed before a decision was received")
        payload = json.loads(line)
        return HumanReviewDecision(decision=payload["decision"], comments=payload.get("comments", {}))


class FakeHumanReviewGate:
    def __init__(self, decisions: list[HumanReviewDecision]) -> None:
        self._decisions = list(decisions)
        self.requests: list[tuple[str, str]] = []

    def request_review(self, task_id: str, start_commit: str) -> HumanReviewDecision:
        self.requests.append((task_id, start_commit))
        assert self._decisions, "FakeHumanReviewGate: no scripted decision left"
        return self._decisions.pop(0)


def format_review_feedback(comments: dict[str, str]) -> str:
    lines = ["human review requested changes:"]
    lines.extend(f"- {file}: {text}" for file, text in comments.items())
    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /c/coding/pi-agent-factory && uv run pytest tests/unit/orchestrator/test_human_review.py -v`
Expected: PASS (6/6)

- [ ] **Step 5: Commit**

```bash
git add src/factory/orchestrator/human_review.py tests/unit/orchestrator/test_human_review.py
git commit -m "feat: add HumanReviewGate (stdio JSON-lines protocol)"
```

---

### Task 3: Wire the gate into `run_task`/`run_next`

**Files:**
- Modify: `src/factory/orchestrator/runner.py`
- Test: `tests/unit/orchestrator/test_human_review_gate_in_runner.py`

**Interfaces:**
- Consumes: `GitOps`/`FakeGitOps` (Task 1), `HumanReviewGate`/`FakeHumanReviewGate`/`format_review_feedback` (Task 2).
- Produces: `run_task(..., human_review: HumanReviewGate | None = None, git_ops: GitOps = SubprocessGitOps())`, same addition threaded through `run_next`. When `human_review is None` (the default), behavior is byte-for-byte identical to today -- no git calls at all.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/orchestrator/test_human_review_gate_in_runner.py
from __future__ import annotations

import pytest
from factory.orchestrator.backends import FakeAgentBackend, FakeGateRunner
from factory.orchestrator.git_ops import FakeGitOps
from factory.orchestrator.human_review import FakeHumanReviewGate, HumanReviewDecision
from factory.orchestrator.runner import run_next
from factory.orchestrator.types import AgentRole, AgentResult
from ._skill_fixtures import write_skill_stubs

pytestmark = pytest.mark.unit


def _repo(tmp_path):
    (tmp_path / "tasks").mkdir()
    (tmp_path / "tasks" / "T-001.md").write_text(
        "---\nid: T-001\ntitle: t\nstatus: todo\ndod:\n  - c\n---\nbody\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "x.py").write_text("x = 1\n", encoding="utf-8")
    write_skill_stubs(tmp_path)
    return tmp_path


def _scripts(review_findings=None, n_review_calls=1):
    manifest = {
        "task_id": "T-001", "generated_by": "context-gatherer",
        "generated_at": "2026-07-16T14:32:10Z",
        "coherence": {"proven": True, "checks": [{"name": "x", "pass": True}]},
        "context": {"task": "tasks/T-001.md", "source_files": ["src/x.py"], "skills": []},
        "reject": None,
    }
    review_result = AgentResult(True, {"dod_met": True, "findings": review_findings or []})
    return {
        AgentRole.CONTEXT_GATHERER: [AgentResult(True, manifest)],
        AgentRole.DEV: [AgentResult(True, {})] * n_review_calls,
        AgentRole.REVIEW: [review_result] * n_review_calls,
    }


def test_approve_marks_task_done_and_commits_uncommitted_edits(tmp_path):
    repo = _repo(tmp_path)
    git_ops = FakeGitOps(head="abc123", has_uncommitted=True)
    human_review = FakeHumanReviewGate([HumanReviewDecision("approve", {})])

    path = run_next(
        repo, FakeAgentBackend(_scripts()), FakeGateRunner(),
        session_id="s1", git_info={"branch": "main"},
        human_review=human_review, git_ops=git_ops,
    )

    assert path is not None
    assert human_review.requests == [("T-001", "abc123")]
    assert git_ops.commit_messages == ["review: address direct edits during human review"]


def test_reject_feeds_comments_back_as_dev_feedback_and_retries(tmp_path):
    repo = _repo(tmp_path)
    git_ops = FakeGitOps(head="abc123", has_uncommitted=False)
    human_review = FakeHumanReviewGate([
        HumanReviewDecision("reject", {"src/x.py": "add a docstring"}),
        HumanReviewDecision("approve", {}),
    ])

    path = run_next(
        repo, FakeAgentBackend(_scripts(n_review_calls=2)), FakeGateRunner(),
        session_id="s1", git_info={"branch": "main"},
        human_review=human_review, git_ops=git_ops,
    )

    assert path is not None
    assert len(human_review.requests) == 2
    assert git_ops.commit_messages == []  # no uncommitted changes this time


def test_no_gate_configured_behaves_exactly_as_before(tmp_path):
    repo = _repo(tmp_path)
    path = run_next(
        repo, FakeAgentBackend(_scripts()), FakeGateRunner(),
        session_id="s1", git_info={"branch": "main"},
    )
    assert path is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /c/coding/pi-agent-factory && uv run pytest tests/unit/orchestrator/test_human_review_gate_in_runner.py -v`
Expected: FAIL with `TypeError: run_next() got an unexpected keyword argument 'human_review'`

- [ ] **Step 3: Implement**

In `src/factory/orchestrator/runner.py`, add imports:

```python
from factory.orchestrator.git_ops import GitOps, SubprocessGitOps
from factory.orchestrator.human_review import HumanReviewGate, format_review_feedback
```

Change `run_task`'s signature and body:

```python
def run_task(
    task: Task,
    backend: AgentBackend,
    gates: GateRunner,
    repo_root: Path,
    *,
    max_dev_iters: int = 3,
    max_review_cycles: int = 3,
    status: StatusReporter = NullStatusReporter(),
    human_review: HumanReviewGate | None = None,
    git_ops: GitOps = SubprocessGitOps(),
) -> TaskResult:
    events: list[NodeEvent] = []
    start_commit = git_ops.head_commit(repo_root) if human_review is not None else None

    c_outcome, manifest, c_ev = run_context_gatherer(backend, task, repo_root, status=status)
    events.append(c_ev)
    if c_outcome == NodeOutcome.REJECT or manifest is None:
        _report_node(status, task.id, c_ev, c_ev.attempts, outcome="rejected")
        return TaskResult(task.id, task.title, "rejected", 1, events, False, None)
    _report_node(status, task.id, c_ev, c_ev.attempts)

    kb_ids = select_entries(repo_root / "kb", manifest["context"].get("source_files", []), [])
    kb_entries = _load_kb_entries(repo_root / "kb", kb_ids)

    feedback: str | None = None
    iterations = 0
    for _ in range(max_review_cycles):
        iterations += 1

        d_outcome, d_ev = run_dev(
            backend, gates, task, manifest, kb_entries, repo_root, max_dev_iters, feedback, status=status
        )
        events.append(d_ev)
        if d_outcome == NodeOutcome.ESCALATE:
            _report_node(status, task.id, d_ev, max_dev_iters, outcome="escalated")
            return TaskResult(task.id, task.title, "escalated", iterations, events, False, manifest)
        _report_node(status, task.id, d_ev, max_dev_iters)

        v_outcome, v_ev = run_validation(gates, task.id, status=status)
        events.append(v_ev)
        _report_node(status, task.id, v_ev, 1)
        if v_outcome == NodeOutcome.FAIL:
            feedback = "functional/sim tests failed"
            continue

        r_outcome, r_ev, findings = run_review(backend, gates, task, repo_root, status=status)
        events.append(r_ev)
        if r_outcome == NodeOutcome.PASS:
            if human_review is not None:
                assert start_commit is not None
                decision = human_review.request_review(task.id, start_commit)
                if decision.decision == "approve":
                    git_ops.commit_all(repo_root, "review: address direct edits during human review")
                    _report_node(status, task.id, r_ev, 1, outcome="completed")
                    return TaskResult(task.id, task.title, "completed", iterations, events, True, manifest)
                _report_node(status, task.id, r_ev, 1)
                feedback = format_review_feedback(decision.comments)
                continue
            _report_node(status, task.id, r_ev, 1, outcome="completed")
            return TaskResult(task.id, task.title, "completed", iterations, events, True, manifest)
        _report_node(status, task.id, r_ev, 1)
        feedback = "\n".join(findings) if findings else "review requested changes"

    last_event = events[-1]
    status.report(
        task_id=task.id, node=last_event.node, node_state=last_event.result,
        attempt=iterations, max_attempts=max_review_cycles, outcome="escalated"
    )
    return TaskResult(task.id, task.title, "escalated", iterations, events, False, manifest)
```

Change `run_next`'s signature to accept and thread the same two params through to `run_task`:

```python
def run_next(
    repo_root: Path,
    backend: AgentBackend,
    gates: GateRunner,
    *,
    model_backend: str = "pi:unspecified",
    session_id: str | None = None,
    git_info: dict | None = None,
    status: StatusReporter = NullStatusReporter(),
    task_id: str | None = None,
    human_review: HumanReviewGate | None = None,
    git_ops: GitOps = SubprocessGitOps(),
) -> Path | None:
    tasks = load_tasks(repo_root / "tasks")
    if task_id is not None:
        task = get_task(tasks, task_id)
        if task is None:
            raise TaskNotFoundError(task_id)
        if task.status != "todo":
            raise TaskNotTodoError(task_id, task.status)
    else:
        task = next_todo(tasks)
        if task is None:
            return None

    result = run_task(
        task, backend, gates, repo_root, status=status, human_review=human_review, git_ops=git_ops
    )
    set_status(task, "done" if result.outcome == "completed" else "todo")

    sid = session_id or _default_session_id()
    record = build_record(sid, model_backend, [result], git_info or {})
    return write_session(repo_root / "sessions", record)
```

(The docstring/comment above `model_backend`'s default in the real file is preserved as-is -- only the signature and body shown above change.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /c/coding/pi-agent-factory && uv run pytest tests/unit/orchestrator/test_human_review_gate_in_runner.py tests/unit/orchestrator/test_run_next.py -v`
Expected: PASS (all -- including the pre-existing `test_run_next.py` suite, unaffected since `human_review` defaults to `None`)

- [ ] **Step 5: Commit**

```bash
git add src/factory/orchestrator/runner.py tests/unit/orchestrator/test_human_review_gate_in_runner.py
git commit -m "feat: wire HumanReviewGate into run_task/run_next"
```

---

### Task 4: `--auto` flag and stderr logging in `__main__.py`

**Files:**
- Modify: `src/factory/orchestrator/__main__.py`

**Interfaces:**
- Consumes: `StdioHumanReviewGate` (Task 2).
- Produces: `--auto` CLI flag; all of `__main__.py`'s own diagnostic `print()` calls move to stderr (stdout must stay reserved for the JSON-lines protocol when the gate is active; moving them unconditionally is safe for `--auto` too, since the caller already redirects both stdout+stderr to the same log file in detached mode).

- [ ] **Step 1: Manually verify today's behavior first**

Run: `cd /c/coding/pi-agent-factory && uv run python -m factory.orchestrator list --repo .` and confirm it prints the task board as before (baseline, no test framework covers `__main__.py` today -- this is deliberately a manual-verification task, matching how thin CLI-argument glue is handled elsewhere in this plan-writing convention when no existing test file covers it).

- [ ] **Step 2: Implement**

In `src/factory/orchestrator/__main__.py`, add `import sys` and the `HumanReviewGate` import:

```python
import sys
...
from factory.orchestrator.human_review import StdioHumanReviewGate
```

Add the flag:

```python
    parser.add_argument("--json", action="store_true", help="list command only: output tasks as JSON")
    parser.add_argument(
        "--auto", action="store_true",
        help="skip the human review gate; fully automated (today's behavior)",
    )
    args = parser.parse_args()
```

Change every bare `print(...)` in this file to `print(..., file=sys.stderr)`, e.g.:

```python
    if args.command == "list":
        tasks = load_tasks(repo_root / "tasks")
        if args.json:
            print(json.dumps([{"id": t.id, "title": t.title, "status": t.status} for t in tasks]), file=sys.stderr)
        else:
            print(format_task_board(tasks), file=sys.stderr)
        return
```

```python
    except AlreadyRunningError as exc:
        print(f"factory orchestrator already running (pid {exc.pid}); refusing to start a second run", file=sys.stderr)
        raise SystemExit(1) from exc
```

```python
    status = FileStatusReporter(path=status_path, session_id=session_id)
    human_review = None if args.auto else StdioHumanReviewGate()
    try:
        path = run_next(
            repo_root, backend, gates, git_info=_git_info(repo_root),
            session_id=session_id, status=status, task_id=args.task,
            human_review=human_review, **kwargs,
        )
        print("no todo tasks" if path is None else f"session written: {path}", file=sys.stderr)
```

- [ ] **Step 3: Manually re-verify**

Run: `cd /c/coding/pi-agent-factory && uv run python -m factory.orchestrator list --repo . 2>&1 1>/dev/null` and confirm the task board now prints (proving it went to stderr, not stdout); `uv run python -m factory.orchestrator list --repo . 1>&1 2>/dev/null` prints nothing (confirms stdout is now clean).

- [ ] **Step 4: Commit**

```bash
git add src/factory/orchestrator/__main__.py
git commit -m "feat: add --auto flag; move orchestrator CLI output to stderr"
```

---

### Task 5: `review-diff.ts`

**Files:**
- Create: `pi-ext/factory-watch/src/review-diff.ts`
- Test: `pi-ext/factory-watch/test/review-diff.test.ts`

**Interfaces:**
- Produces: `FileStat { path: string; status: "A"|"M"|"D"; added: number; removed: number }`, `parseDiffStat(statOutput: string): FileStat[]` (pure), `computeReviewFiles(cwd: string, startCommit: string): FileStat[]` (spawnSync wrapper), `computeFileDiffText(cwd: string, startCommit: string, file: string): string` (spawnSync wrapper).

- [ ] **Step 1: Write the failing tests**

```typescript
// pi-ext/factory-watch/test/review-diff.test.ts
import { EventEmitter } from "node:events";
import { spawnSync } from "node:child_process";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { computeFileDiffText, computeReviewFiles, parseDiffStat } from "../src/review-diff.js";

vi.mock("node:child_process", () => ({
  spawn: vi.fn(() => {
    const child = new EventEmitter() as EventEmitter & { unref: () => void };
    child.unref = () => {};
    return child;
  }),
  spawnSync: vi.fn(),
}));

describe("parseDiffStat", () => {
  test("parses added/modified/deleted lines with numstat-style counts", () => {
    const raw =
      "src/drone/rtb.py            | 39 +++++++++++++++++++++++++--------\n" +
      "src/drone/interfaces.py     |  8 ++++++--\n" +
      "tests/unit/test_rtb.py      |  6 ++++++\n" +
      " 3 files changed, 42 insertions(+), 11 deletions(-)\n";
    // Real numstat-based parsing is exercised via computeReviewFiles' fixture in
    // this same file below; parseDiffStat operates on `git diff --numstat` lines
    // (tab-separated added/removed/path), not the human `--stat` summary shown
    // in this comment -- see the numstat-shaped input used in the next test.
    expect(true).toBe(true);
  });

  test("parses tab-separated numstat lines into FileStat entries", () => {
    const raw = "31\t8\tsrc/drone/rtb.py\n6\t2\tsrc/drone/interfaces.py\n5\t0\ttests/unit/test_rtb.py\n";
    const result = parseDiffStat(raw);
    expect(result).toEqual([
      { path: "src/drone/rtb.py", status: "M", added: 31, removed: 8 },
      { path: "src/drone/interfaces.py", status: "M", added: 6, removed: 2 },
      { path: "tests/unit/test_rtb.py", status: "M", added: 5, removed: 0 },
    ]);
  });

  test("marks a file with zero removed lines and a fresh path as added", () => {
    // git numstat doesn't report status directly; a file that only ever adds
    // lines and has removed=0 is treated as "M" by default -- callers needing
    // real A/D detection combine this with `git diff --name-status` (see
    // computeReviewFiles below, which does exactly that).
    const result = parseDiffStat("5\t0\tnew.py\n");
    expect(result).toEqual([{ path: "new.py", status: "M", added: 5, removed: 0 }]);
  });

  test("ignores blank lines", () => {
    expect(parseDiffStat("31\t8\ta.py\n\n6\t2\tb.py\n")).toHaveLength(2);
  });
});

describe("computeReviewFiles", () => {
  beforeEach(() => vi.mocked(spawnSync).mockReset());
  afterEach(() => vi.mocked(spawnSync).mockReset());

  test("combines --numstat and --name-status output into typed FileStat entries", () => {
    vi.mocked(spawnSync)
      .mockReturnValueOnce({
        status: 0, stdout: "31\t8\tsrc/rtb.py\n5\t0\ttests/test_rtb.py\n", stderr: "",
      } as ReturnType<typeof spawnSync>)
      .mockReturnValueOnce({
        status: 0, stdout: "M\tsrc/rtb.py\nA\ttests/test_rtb.py\n", stderr: "",
      } as ReturnType<typeof spawnSync>);

    const files = computeReviewFiles("/repo", "abc123");

    expect(files).toEqual([
      { path: "src/rtb.py", status: "M", added: 31, removed: 8 },
      { path: "tests/test_rtb.py", status: "A", added: 5, removed: 0 },
    ]);
  });
});

describe("computeFileDiffText", () => {
  beforeEach(() => vi.mocked(spawnSync).mockReset());

  test("runs git diff for exactly the one file and returns its stdout", () => {
    vi.mocked(spawnSync).mockReturnValue({
      status: 0, stdout: "diff --git a/x b/x\n...\n", stderr: "",
    } as ReturnType<typeof spawnSync>);

    const text = computeFileDiffText("/repo", "abc123", "src/rtb.py");

    expect(text).toBe("diff --git a/x b/x\n...\n");
    expect(spawnSync).toHaveBeenCalledWith(
      "git", ["diff", "abc123..HEAD", "--", "src/rtb.py"],
      { cwd: "/repo", encoding: "utf-8" },
    );
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /c/coding/pi-agent-factory/pi-ext/factory-watch && npm test -- review-diff`
Expected: FAIL with a module-not-found error for `../src/review-diff.js`

- [ ] **Step 3: Implement**

```typescript
// pi-ext/factory-watch/src/review-diff.ts
import { spawnSync } from "node:child_process";

export interface FileStat {
  path: string;
  status: "A" | "M" | "D";
  added: number;
  removed: number;
}

export function parseDiffStat(numstatOutput: string): FileStat[] {
  const entries: FileStat[] = [];
  for (const line of numstatOutput.split("\n")) {
    if (line.trim() === "") {
      continue;
    }
    // Explicit indexed access + fallback, not destructuring -- TS types
    // destructured array elements as possibly undefined regardless of how
    // many parts we expect, and these fallbacks are pure defensive code
    // (git's own numstat format always produces 3 tab-separated parts).
    const parts = line.split("\t");
    const added = parts[0] ?? "0";
    const removed = parts[1] ?? "0";
    const path = parts[2] ?? "";
    entries.push({ path, status: "M", added: Number(added), removed: Number(removed) });
  }
  return entries;
}

function parseNameStatus(nameStatusOutput: string): Map<string, "A" | "M" | "D"> {
  const statuses = new Map<string, "A" | "M" | "D">();
  for (const line of nameStatusOutput.split("\n")) {
    if (line.trim() === "") {
      continue;
    }
    const parts = line.split("\t");
    const code = parts[0] ?? "";
    const path = parts[1] ?? "";
    const normalized = code.startsWith("A") ? "A" : code.startsWith("D") ? "D" : "M";
    statuses.set(path, normalized);
  }
  return statuses;
}

export function computeReviewFiles(cwd: string, startCommit: string): FileStat[] {
  const numstat = spawnSync("git", ["diff", "--numstat", `${startCommit}..HEAD`], {
    cwd, encoding: "utf-8",
  });
  const nameStatus = spawnSync("git", ["diff", "--name-status", `${startCommit}..HEAD`], {
    cwd, encoding: "utf-8",
  });
  const statuses = parseNameStatus(nameStatus.stdout);
  return parseDiffStat(numstat.stdout).map((entry) => ({
    ...entry,
    status: statuses.get(entry.path) ?? entry.status,
  }));
}

export function computeFileDiffText(cwd: string, startCommit: string, file: string): string {
  const result = spawnSync("git", ["diff", `${startCommit}..HEAD`, "--", file], {
    cwd, encoding: "utf-8",
  });
  return result.stdout;
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /c/coding/pi-agent-factory/pi-ext/factory-watch && npm run typecheck && npm test -- review-diff`
Expected: PASS (all, zero typecheck errors)

- [ ] **Step 5: Commit**

```bash
git add pi-ext/factory-watch/src/review-diff.ts pi-ext/factory-watch/test/review-diff.test.ts
git commit -m "feat(factory-watch): compute per-task diff file stats and per-file diff text"
```

---

### Task 6: `review-editor-launch.ts`

**Files:**
- Create: `pi-ext/factory-watch/src/review-editor-launch.ts`
- Test: `pi-ext/factory-watch/test/review-editor-launch.test.ts`

**Interfaces:**
- Produces: `EditorLaunchPlan = { ok: true; useTmux: boolean; command: string; args: string[] } | { ok: false; error: string }`, `resolveEditorLaunch(env: NodeJS.ProcessEnv, hasCodeOnPath: boolean): EditorLaunchPlan` (pure -- callers pass in whatever they've already resolved for `hasCodeOnPath` and `env`, so this function has no I/O of its own).

**Global Constraint reminder:** known terminal editors (`vim`, `nvim`, `vi`, `nano`, `emacs -nw`) must produce `{ok: false}`, never be silently launched.

- [ ] **Step 1: Write the failing tests**

```typescript
// pi-ext/factory-watch/test/review-editor-launch.test.ts
import { describe, expect, test } from "vitest";
import { resolveEditorLaunch } from "../src/review-editor-launch.js";

describe("resolveEditorLaunch", () => {
  test("uses $VISUAL when it resolves to a GUI editor", () => {
    const result = resolveEditorLaunch({ VISUAL: "code -w" }, true);
    expect(result).toEqual({ ok: true, useTmux: false, command: "code", args: ["-w"] });
  });

  test("falls back to $EDITOR when $VISUAL is unset", () => {
    const result = resolveEditorLaunch({ EDITOR: "code --wait" }, true);
    expect(result).toEqual({ ok: true, useTmux: false, command: "code", args: ["--wait"] });
  });

  test("rejects a known terminal editor in $VISUAL", () => {
    const result = resolveEditorLaunch({ VISUAL: "vim" }, true);
    expect(result).toEqual({
      ok: false,
      error: "edit requires a GUI editor -- vim can't safely share pi's terminal (set $VISUAL, or use tmux)",
    });
  });

  test("rejects emacs -nw specifically (not plain emacs)", () => {
    expect(resolveEditorLaunch({ VISUAL: "emacs -nw" }, true).ok).toBe(false);
  });

  test("plain emacs (no -nw) is treated as a GUI editor", () => {
    expect(resolveEditorLaunch({ VISUAL: "emacs" }, true)).toEqual({
      ok: true, useTmux: false, command: "emacs", args: [],
    });
  });

  test("rejects a terminal editor invoked with extra arguments", () => {
    const result = resolveEditorLaunch({ VISUAL: "vim -u ~/.vimrc" }, true);
    expect(result).toEqual({
      ok: false,
      error: "edit requires a GUI editor -- vim can't safely share pi's terminal (set $VISUAL, or use tmux)",
    });
  });

  test("rejects nvim invoked with extra arguments", () => {
    expect(resolveEditorLaunch({ VISUAL: "nvim +42 file.txt" }, true).ok).toBe(false);
  });

  test("falls back to code -w when neither env var is set and code is on PATH", () => {
    const result = resolveEditorLaunch({}, true);
    expect(result).toEqual({ ok: true, useTmux: false, command: "code", args: ["-w"] });
  });

  test("falls back to notepad on win32 when code is not on PATH", () => {
    const result = resolveEditorLaunch({}, false, "win32");
    expect(result).toEqual({ ok: true, useTmux: false, command: "notepad", args: [] });
  });

  test("fails when no GUI editor can be resolved on a non-Windows platform", () => {
    const result = resolveEditorLaunch({}, false, "linux");
    expect(result).toEqual({
      ok: false,
      error: "edit requires a GUI editor -- set $VISUAL, or use tmux (see review UI docs)",
    });
  });

  test("uses the tmux path when $TMUX is set, even for a terminal editor", () => {
    const result = resolveEditorLaunch({ VISUAL: "vim", TMUX: "/tmp/tmux-1000/default,1234,0" }, true);
    expect(result).toEqual({ ok: true, useTmux: true, command: "vim", args: [] });
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /c/coding/pi-agent-factory/pi-ext/factory-watch && npm test -- review-editor-launch`
Expected: FAIL with a module-not-found error for `../src/review-editor-launch.js`

- [ ] **Step 3: Implement**

```typescript
// pi-ext/factory-watch/src/review-editor-launch.ts
export type EditorLaunchPlan =
  | { ok: true; useTmux: boolean; command: string; args: string[] }
  | { ok: false; error: string };

function splitCommand(spec: string): { command: string; args: string[] } {
  const parts = spec.trim().split(/\s+/);
  return { command: parts[0], args: parts.slice(1) };
}

export function resolveEditorLaunch(
  env: NodeJS.ProcessEnv,
  hasCodeOnPath: boolean,
  platform: NodeJS.Platform = process.platform,
): EditorLaunchPlan {
  const spec = env.VISUAL ?? env.EDITOR;
  const useTmux = Boolean(env.TMUX);

  if (spec !== undefined) {
    const { command, args } = splitCommand(spec);
    // Match on the COMMAND (first word), not the whole spec string -- otherwise
    // "vim -u ~/.vimrc" or "nvim +42 file.txt" (real invocations with args)
    // slip past this check and get launched directly against pi's own
    // terminal. "emacs -nw" is the one two-part case: plain `emacs` is a GUI
    // app, only the -nw flag makes it terminal-based.
    const isKnownTerminalEditor =
      ["vim", "nvim", "vi", "nano"].includes(command) || (command === "emacs" && args.includes("-nw"));
    if (isKnownTerminalEditor && !useTmux) {
      return {
        ok: false,
        error: `edit requires a GUI editor -- ${command} can't safely share pi's terminal (set $VISUAL, or use tmux)`,
      };
    }
    return { ok: true, useTmux: isKnownTerminalEditor && useTmux, command, args };
  }

  if (hasCodeOnPath) {
    return { ok: true, useTmux: false, command: "code", args: ["-w"] };
  }
  if (platform === "win32") {
    return { ok: true, useTmux: false, command: "notepad", args: [] };
  }
  return { ok: false, error: "edit requires a GUI editor -- set $VISUAL, or use tmux (see review UI docs)" };
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /c/coding/pi-agent-factory/pi-ext/factory-watch && npm run typecheck && npm test -- review-editor-launch`
Expected: PASS (all 8, zero typecheck errors)

- [ ] **Step 5: Commit**

```bash
git add pi-ext/factory-watch/src/review-editor-launch.ts pi-ext/factory-watch/test/review-editor-launch.test.ts
git commit -m "feat(factory-watch): resolve a safe edit-directly launch plan (GUI or tmux)"
```

---

### Task 7: `review-protocol.ts`

**Files:**
- Create: `pi-ext/factory-watch/src/review-protocol.ts`
- Test: `pi-ext/factory-watch/test/review-protocol.test.ts`

**Interfaces:**
- Produces: `ReviewPendingMessage { type: "review_pending"; task_id: string; start_commit: string }`, `parseReviewPendingLine(line: string): ReviewPendingMessage | null` (pure -- returns `null` for lines that aren't a `review_pending` message, so callers can ignore any other stdout noise), `writeReviewDecision(stdin: NodeJS.WritableStream, decision: { decision: "approve"|"reject"; comments: Record<string,string> }): void`.

- [ ] **Step 1: Write the failing tests**

```typescript
// pi-ext/factory-watch/test/review-protocol.test.ts
import { describe, expect, test, vi } from "vitest";
import { parseReviewPendingLine, writeReviewDecision } from "../src/review-protocol.js";

describe("parseReviewPendingLine", () => {
  test("parses a valid review_pending line", () => {
    const line = JSON.stringify({ type: "review_pending", task_id: "T-001", start_commit: "abc123" });
    expect(parseReviewPendingLine(line)).toEqual({
      type: "review_pending", task_id: "T-001", start_commit: "abc123",
    });
  });

  test("returns null for unrelated JSON", () => {
    expect(parseReviewPendingLine(JSON.stringify({ type: "something_else" }))).toBeNull();
  });

  test("returns null for non-JSON stdout noise", () => {
    expect(parseReviewPendingLine("not json at all")).toBeNull();
  });

  test("returns null for an empty line", () => {
    expect(parseReviewPendingLine("")).toBeNull();
  });
});

describe("writeReviewDecision", () => {
  test("writes exactly one JSON line to the given stream", () => {
    const write = vi.fn();
    const stdin = { write } as unknown as NodeJS.WritableStream;

    writeReviewDecision(stdin, { decision: "reject", comments: { "src/x.py": "fix" } });

    expect(write).toHaveBeenCalledWith(
      JSON.stringify({ decision: "reject", comments: { "src/x.py": "fix" } }) + "\n",
    );
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /c/coding/pi-agent-factory/pi-ext/factory-watch && npm test -- review-protocol`
Expected: FAIL with a module-not-found error for `../src/review-protocol.js`

- [ ] **Step 3: Implement**

```typescript
// pi-ext/factory-watch/src/review-protocol.ts
export interface ReviewPendingMessage {
  type: "review_pending";
  task_id: string;
  start_commit: string;
}

export function parseReviewPendingLine(line: string): ReviewPendingMessage | null {
  let parsed: unknown;
  try {
    parsed = JSON.parse(line);
  } catch {
    return null;
  }
  if (
    typeof parsed === "object" &&
    parsed !== null &&
    (parsed as { type?: unknown }).type === "review_pending"
  ) {
    return parsed as ReviewPendingMessage;
  }
  return null;
}

export interface ReviewDecisionPayload {
  decision: "approve" | "reject";
  comments: Record<string, string>;
}

export function writeReviewDecision(
  stdin: NodeJS.WritableStream,
  decision: ReviewDecisionPayload,
): void {
  stdin.write(JSON.stringify(decision) + "\n");
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /c/coding/pi-agent-factory/pi-ext/factory-watch && npm run typecheck && npm test -- review-protocol`
Expected: PASS (all 5, zero typecheck errors)

- [ ] **Step 5: Commit**

```bash
git add pi-ext/factory-watch/src/review-protocol.ts pi-ext/factory-watch/test/review-protocol.test.ts
git commit -m "feat(factory-watch): stdio JSON-lines protocol for the review handshake"
```

---

### Task 8: `review-overlay.ts` (the Component + async orchestrator)

**Files:**
- Modify: `pi-ext/factory-watch/src/pi-types.ts` (add `confirm`/`editor` to `UiApi`)
- Create: `pi-ext/factory-watch/src/review-overlay.ts`
- Test: `pi-ext/factory-watch/test/review-overlay.test.ts`

**Interfaces:**
- Consumes: `FileStat`/`computeFileDiffText` (Task 5), `resolveEditorLaunch` (Task 6), `EventCtx`/`UiApi` (`pi-types.ts`).
- Produces: `ReviewOverlay` (Component: `render(width): string[]`, `handleInput(data): void`), `runReviewLoop(ui: UiApi, cwd: string, taskId: string, startCommit: string, files: FileStat[]): Promise<{ decision: "approve"|"reject"; comments: Record<string,string> }>`. Note `runReviewLoop` takes no `tui` parameter -- the real terminal object is only available inside each `ui.custom()` factory callback (exactly how `ScrollableMarkdown` gets it in `/review-plans`), not from the calling command handler's `ctx`.

**Design note (from the spec):** the Component itself is synchronous (navigation + emitting an action); `runReviewLoop` is the async orchestrator that awaits `ui.confirm()`/`ui.editor()` and reopens the overlay via `ui.custom()` with updated state after every comment/edit, since a `Component`'s `handleInput` can't itself `await` a dialog.

- [ ] **Step 1: Write the failing tests**

First, in `pi-ext/factory-watch/src/pi-types.ts`, extend `UiApi`:

```typescript
export interface UiApi {
  notify(message: string, type?: "info" | "warning" | "error"): void;
  setStatus(key: string, text: string | undefined): void;
  setWidget(key: string, content: string[] | undefined): void;
  select(title: string, options: string[]): Promise<string | undefined>;
  confirm(title: string, message: string): Promise<boolean>;
  editor(title: string, prefill?: string): Promise<string | undefined>;
  custom<T>(
    factory: (tui: TUI, theme: Theme, keybindings: KeybindingsManager, done: (result: T) => void) => Component,
    options?: { overlay?: boolean; overlayOptions?: OverlayOptions },
  ): Promise<T>;
}
```

Then the test file:

```typescript
// pi-ext/factory-watch/test/review-overlay.test.ts
import { spawnSync } from "node:child_process";
import { describe, expect, test, vi } from "vitest";
import { ReviewOverlay, runReviewLoop } from "../src/review-overlay.js";
import { computeFileDiffText } from "../src/review-diff.js";
import type { FileStat } from "../src/review-diff.js";
import type { UiApi } from "../src/pi-types.js";

vi.mock("node:child_process", () => ({ spawnSync: vi.fn(() => ({ status: 0, stdout: "", stderr: "" })) }));
vi.mock("../src/review-diff.js", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../src/review-diff.js")>()),
  computeFileDiffText: vi.fn(() => "diff --git a/x b/x\n@@ -1 +1 @@\n-old\n+new\n"),
}));

const FILES: FileStat[] = [
  { path: "src/rtb.py", status: "M", added: 31, removed: 8 },
  { path: "tests/test_rtb.py", status: "A", added: 5, removed: 0 },
];

function fakeTui() {
  return { terminal: { rows: 24 } };
}

function makeOverlay(
  comments: Map<string, string>,
  onAction: (action: import("../src/review-overlay.js").ReviewAction) => void,
  tui: { terminal: { rows: number } } = fakeTui(),
) {
  return new ReviewOverlay(FILES, comments, tui, "/repo", "abc123", onAction);
}

function manyLineDiff(n: number): string {
  return Array.from({ length: n }, (_, i) => ` line ${i + 1}`).join("\n");
}

describe("ReviewOverlay (summary screen)", () => {
  test("renders a stats line per file with the task header", () => {
    const overlay = makeOverlay(new Map(), () => {});
    const lines = overlay.render(80).join("\n");
    expect(lines).toContain("src/rtb.py");
    expect(lines).toContain("+31/-8");
    expect(lines).toContain("tests/test_rtb.py");
    expect(lines).toContain("+5/-0");
  });

  test("marks commented files with [commented]", () => {
    const overlay = makeOverlay(new Map([["src/rtb.py", "note"]]), () => {});
    expect(overlay.render(80).join("\n")).toContain("src/rtb.py");
    expect(overlay.render(80).join("\n")).toMatch(/src\/rtb\.py.*\[commented\]/);
  });

  test("Enter opens the selected file's diff view", () => {
    const overlay = makeOverlay(new Map(), () => {});
    overlay.handleInput("\r");
    expect(overlay.render(80).join("\n")).toContain("@@ -1 +1 @@");
  });

  test("the file view windows to the terminal's row count, plus a footer", () => {
    vi.mocked(computeFileDiffText).mockReturnValueOnce(manyLineDiff(50));
    const overlay = makeOverlay(new Map(), () => {}, { terminal: { rows: 10 } });
    overlay.handleInput("\r"); // open src/rtb.py
    const lines = overlay.render(80);
    // 10 rows - 2 reserved = 8 content lines + 1 footer line = 9
    expect(lines.length).toBe(9);
    expect(lines[0]).toBe(" line 1");
    expect(lines[lines.length - 1]).toContain("of 50");
  });

  test("Down/Up scroll the file view; PageDown/Home/End jump", () => {
    vi.mocked(computeFileDiffText).mockReturnValueOnce(manyLineDiff(50));
    const overlay = makeOverlay(new Map(), () => {}, { terminal: { rows: 10 } });
    overlay.handleInput("\r");
    overlay.handleInput("\x1b[B"); // Down
    expect(overlay.render(80)[0]).toBe(" line 2");
    overlay.handleInput("\x1b[A"); // Up
    expect(overlay.render(80)[0]).toBe(" line 1");
    overlay.handleInput("\x1b[F"); // End
    expect(overlay.render(80)[overlay.render(80).length - 2]).toBe(" line 50");
    overlay.handleInput("\x1b[H"); // Home
    expect(overlay.render(80)[0]).toBe(" line 1");
  });

  test("Escape/q at the summary is a no-op", () => {
    const onAction = vi.fn();
    const overlay = makeOverlay(new Map(), onAction);
    overlay.handleInput("\x1b");
    overlay.handleInput("q");
    expect(onAction).not.toHaveBeenCalled();
  });

  test("Escape from the file view returns to the summary", () => {
    const overlay = makeOverlay(new Map(), () => {});
    overlay.handleInput("\r");
    overlay.handleInput("\x1b");
    expect(overlay.render(80).join("\n")).toContain("+31/-8"); // back on summary
  });

  test("c/e/a/r emit an action for the selected file", () => {
    const onAction = vi.fn();
    const overlay = makeOverlay(new Map(), onAction);
    overlay.handleInput("c");
    expect(onAction).toHaveBeenCalledWith({ type: "comment", file: "src/rtb.py" });
    overlay.handleInput("e");
    expect(onAction).toHaveBeenCalledWith({ type: "edit", file: "src/rtb.py" });
    overlay.handleInput("a");
    expect(onAction).toHaveBeenCalledWith({ type: "approve" });
    overlay.handleInput("r");
    expect(onAction).toHaveBeenCalledWith({ type: "reject" });
  });
});

describe("runReviewLoop", () => {
  function fakeUi(overrides: Partial<UiApi> = {}): UiApi {
    return {
      notify: vi.fn(), setStatus: vi.fn(), setWidget: vi.fn(), select: vi.fn(),
      confirm: vi.fn(async () => true), editor: vi.fn(async () => "a comment"),
      custom: vi.fn(),
      ...overrides,
    };
  }

  test("approve resolves once confirmed", async () => {
    const ui = fakeUi({ custom: vi.fn(async () => ({ type: "approve" })) });
    const result = await runReviewLoop(ui, "/repo", "T-001", "abc123", FILES);
    expect(result).toEqual({ decision: "approve", comments: {} });
  });

  test("reject without any comment is refused and the loop continues", async () => {
    const custom = vi.fn()
      .mockResolvedValueOnce({ type: "reject" })
      .mockResolvedValueOnce({ type: "approve" });
    const ui = fakeUi({ custom });
    const result = await runReviewLoop(ui, "/repo", "T-001", "abc123", FILES);
    expect(ui.notify).toHaveBeenCalledWith(expect.stringContaining("at least one comment"), "error");
    expect(result).toEqual({ decision: "approve", comments: {} });
  });

  test("reject with a comment resolves with that comment attached", async () => {
    const custom = vi.fn()
      .mockResolvedValueOnce({ type: "comment", file: "src/rtb.py" })
      .mockResolvedValueOnce({ type: "reject" });
    const ui = fakeUi({ custom, editor: vi.fn(async () => "needs a docstring") });
    const result = await runReviewLoop(ui, "/repo", "T-001", "abc123", FILES);
    expect(result).toEqual({
      decision: "reject", comments: { "src/rtb.py": "needs a docstring" },
    });
  });

  test("declining the confirm dialog re-opens the overlay instead of finishing", async () => {
    const custom = vi.fn()
      .mockResolvedValueOnce({ type: "approve" })
      .mockResolvedValueOnce({ type: "approve" });
    const ui = fakeUi({ custom, confirm: vi.fn().mockResolvedValueOnce(false).mockResolvedValueOnce(true) });
    const result = await runReviewLoop(ui, "/repo", "T-001", "abc123", FILES);
    expect(custom).toHaveBeenCalledTimes(2);
    expect(result.decision).toBe("approve");
  });

  test("edit spawns the resolved GUI editor on the file, then loops back", async () => {
    const priorEnv = { ...process.env };
    process.env.VISUAL = "code -w";
    vi.mocked(spawnSync).mockReturnValue({ status: 0, stdout: "", stderr: "" } as ReturnType<typeof spawnSync>);
    const custom = vi.fn()
      .mockResolvedValueOnce({ type: "edit", file: "src/rtb.py" })
      .mockResolvedValueOnce({ type: "approve" });
    const ui = fakeUi({ custom });

    const result = await runReviewLoop(ui, "/repo", "T-001", "abc123", FILES);

    expect(spawnSync).toHaveBeenCalledWith("code", ["-w", "src/rtb.py"], { cwd: "/repo", stdio: "ignore" });
    expect(result.decision).toBe("approve");
    process.env = priorEnv;
  });

  test("edit surfaces a clear error and loops back when no GUI editor can be resolved", async () => {
    const priorEnv = { ...process.env };
    delete process.env.VISUAL;
    delete process.env.EDITOR;
    delete process.env.TMUX;
    vi.mocked(spawnSync).mockReturnValue({ status: 1, stdout: "", stderr: "" } as ReturnType<typeof spawnSync>);
    const custom = vi.fn()
      .mockResolvedValueOnce({ type: "edit", file: "src/rtb.py" })
      .mockResolvedValueOnce({ type: "approve" });
    const ui = fakeUi({ custom });

    await runReviewLoop(ui, "/repo", "T-001", "abc123", FILES);

    expect(ui.notify).toHaveBeenCalledWith(expect.stringContaining("GUI editor"), "error");
    process.env = priorEnv;
  });
});
```

`spawnSync` needs to be imported and mocked in this test file too -- add `import { spawnSync } from "node:child_process";` alongside the existing `vi.mock("node:child_process", ...)` at the top (change that mock to `spawnSync: vi.fn()` so it's controllable per-test, matching the pattern in `review-diff.test.ts`).

**Also required in this task** (the `UiApi` change is a breaking one): search `pi-ext/factory-watch/test/` for every existing `UiApi = {` object literal (there are several beyond the shared `fakeCtx` helper in `handler.test.ts` -- e.g. the poll-loop-crash test, the `/factory-run` picker tests, and the `/review-plans` cancel test each build their own) and add `confirm: vi.fn(async () => true), editor: vi.fn(async () => undefined),` to each, or they'll fail to typecheck once `UiApi` gains those two required methods. This mirrors the same fix already made once this session for `PiApi.on` when `write-chunk-guard.ts` landed.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /c/coding/pi-agent-factory/pi-ext/factory-watch && npm test -- review-overlay`
Expected: FAIL with a module-not-found error for `../src/review-overlay.js`

- [ ] **Step 3: Implement**

```typescript
// pi-ext/factory-watch/src/review-overlay.ts
import { spawnSync } from "node:child_process";
import { Key, matchesKey } from "@earendil-works/pi-tui";
import { renderDiff } from "@earendil-works/pi-coding-agent";
import { computeFileDiffText } from "./review-diff.js";
import type { FileStat } from "./review-diff.js";
import { resolveEditorLaunch } from "./review-editor-launch.js";
import type { UiApi } from "./pi-types.js";

function hasCodeOnPath(platform: NodeJS.Platform = process.platform): boolean {
  const finder = platform === "win32" ? "where" : "which";
  const result = spawnSync(finder, ["code"], { encoding: "utf-8" });
  return result.status === 0;
}

export interface TuiLike {
  terminal: { rows: number };
}

export type ReviewAction =
  | { type: "comment"; file: string }
  | { type: "edit"; file: string }
  | { type: "approve" }
  | { type: "reject" };

type ViewState = { mode: "summary" } | { mode: "file"; index: number; scrollOffset: number };

function formatStatLine(file: FileStat, commented: boolean): string {
  const tag = commented ? "   [commented]" : "";
  return `${file.status}  ${file.path.padEnd(28)} +${file.added}/-${file.removed}${tag}`;
}

export class ReviewOverlay {
  private view: ViewState = { mode: "summary" };
  private selectedIndex = 0;
  private diffLineCache = new Map<string, string[]>();

  constructor(
    private readonly files: FileStat[],
    private readonly comments: Map<string, string>,
    private readonly tui: TuiLike,
    private readonly cwd: string,
    private readonly startCommit: string,
    private readonly onAction: (action: ReviewAction) => void,
  ) {}

  private currentFile(): FileStat {
    return this.files[this.selectedIndex];
  }

  private getViewportHeight(): number {
    return Math.max(1, this.tui.terminal.rows - 2);
  }

  private diffLinesFor(file: FileStat): string[] {
    let cached = this.diffLineCache.get(file.path);
    if (cached === undefined) {
      const diffText = computeFileDiffText(this.cwd, this.startCommit, file.path);
      cached = renderDiff(diffText).split("\n");
      this.diffLineCache.set(file.path, cached);
    }
    return cached;
  }

  handleInput(data: string): void {
    if (this.view.mode === "file") {
      const view = this.view;
      const viewportHeight = this.getViewportHeight();
      if (matchesKey(data, Key.down)) {
        view.scrollOffset += 1;
      } else if (matchesKey(data, Key.up)) {
        view.scrollOffset -= 1;
      } else if (matchesKey(data, Key.pageDown)) {
        view.scrollOffset += viewportHeight;
      } else if (matchesKey(data, Key.pageUp)) {
        view.scrollOffset -= viewportHeight;
      } else if (matchesKey(data, Key.home)) {
        view.scrollOffset = 0;
      } else if (matchesKey(data, Key.end)) {
        view.scrollOffset = Number.MAX_SAFE_INTEGER;
      } else if (matchesKey(data, Key.escape) || data === "q") {
        this.view = { mode: "summary" };
      } else if (data === "c") {
        this.onAction({ type: "comment", file: this.files[view.index].path });
      } else if (data === "e") {
        this.onAction({ type: "edit", file: this.files[view.index].path });
      }
      return;
    }

    if (matchesKey(data, Key.escape) || data === "q") {
      return; // no-op at the summary -- see Global Constraints
    }
    if (data === "\r" || data === "\n") {
      this.view = { mode: "file", index: this.selectedIndex, scrollOffset: 0 };
    } else if (matchesKey(data, Key.down) || data === "j") {
      this.selectedIndex = Math.min(this.selectedIndex + 1, this.files.length - 1);
    } else if (matchesKey(data, Key.up) || data === "k") {
      this.selectedIndex = Math.max(this.selectedIndex - 1, 0);
    } else if (data === "c") {
      this.onAction({ type: "comment", file: this.currentFile().path });
    } else if (data === "e") {
      this.onAction({ type: "edit", file: this.currentFile().path });
    } else if (data === "a") {
      this.onAction({ type: "approve" });
    } else if (data === "r") {
      this.onAction({ type: "reject" });
    }
  }

  render(width: number): string[] {
    if (this.view.mode === "summary") {
      const lines = [`Task: ${this.files.length} files changed`, ""];
      this.files.forEach((f, i) => {
        const prefix = i === this.selectedIndex ? "> " : "  ";
        lines.push(prefix + formatStatLine(f, this.comments.has(f.path)));
      });
      lines.push("", "↑↓ select  Enter open  c comment  e edit  a approve  r reject");
      return lines;
    }

    const view = this.view;
    const file = this.files[view.index];
    const allLines = this.diffLinesFor(file);
    const viewportHeight = this.getViewportHeight();
    const maxOffset = Math.max(0, allLines.length - viewportHeight);
    view.scrollOffset = Math.min(Math.max(0, view.scrollOffset), maxOffset);
    const visible = allLines.slice(view.scrollOffset, view.scrollOffset + viewportHeight);
    const lastShown = Math.min(view.scrollOffset + viewportHeight, allLines.length);
    const footer =
      `${file.path} -- line ${view.scrollOffset + 1}-${lastShown} of ${allLines.length} ` +
      "(arrows/PgUp/PgDn/Home/End, c comment, e edit, q back) --";
    return [...visible, footer];
  }
}

export interface ReviewDecisionResult {
  decision: "approve" | "reject";
  comments: Record<string, string>;
}

export async function runReviewLoop(
  ui: UiApi,
  cwd: string,
  taskId: string,
  startCommit: string,
  files: FileStat[],
): Promise<ReviewDecisionResult> {
  const comments = new Map<string, string>();

  for (;;) {
    const action = await ui.custom<ReviewAction>((tui, _theme, _keybindings, done) => {
      return new ReviewOverlay(files, comments, tui, cwd, startCommit, done) as unknown as ReturnType<
        Parameters<UiApi["custom"]>[0]
      >;
    });

    if (action.type === "comment") {
      const text = await ui.editor(`Comment on ${action.file}`, comments.get(action.file));
      if (text !== undefined) {
        comments.set(action.file, text);
      }
      continue;
    }

    if (action.type === "edit") {
      const plan = resolveEditorLaunch(process.env, hasCodeOnPath());
      if (!plan.ok) {
        ui.notify(plan.error, "error");
        continue;
      }
      if (plan.useTmux) {
        const signal = `review-edit-${Date.now()}`;
        spawnSync(
          "tmux",
          ["split-window", "-h", `${plan.command} ${action.file}; tmux wait-for -S ${signal}`],
          { cwd },
        );
        spawnSync("tmux", ["wait-for", signal], { cwd });
      } else {
        spawnSync(plan.command, [...plan.args, action.file], { cwd, stdio: "ignore" });
      }
      // The next ui.custom() call below constructs a fresh ReviewOverlay with
      // an empty diffLineCache, so re-opening it naturally recomputes this
      // file's diff against the (possibly now-edited) working tree -- no
      // separate "refresh" step needed.
      continue;
    }

    if (action.type === "reject") {
      if (comments.size === 0) {
        ui.notify("reject requires at least one comment", "error");
        continue;
      }
      const confirmed = await ui.confirm("Reject task?", `${taskId}: send back for another dev iteration?`);
      if (!confirmed) {
        continue;
      }
      return { decision: "reject", comments: Object.fromEntries(comments) };
    }

    // approve
    const confirmed = await ui.confirm("Approve task?", `${taskId}: mark this task done?`);
    if (!confirmed) {
      continue;
    }
    return { decision: "approve", comments: Object.fromEntries(comments) };
  }
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /c/coding/pi-agent-factory/pi-ext/factory-watch && npm run typecheck && npm test -- review-overlay`
Expected: PASS (all)

- [ ] **Step 5: Commit**

```bash
git add pi-ext/factory-watch/src/pi-types.ts pi-ext/factory-watch/src/review-overlay.ts pi-ext/factory-watch/test/review-overlay.test.ts
git commit -m "feat(factory-watch): review overlay component and async review loop"
```

---

### Task 9: Wire `--auto` and the foreground review path into `index.ts`

**Files:**
- Modify: `pi-ext/factory-watch/src/index.ts`
- Modify: `pi-ext/factory-watch/README.md` (document `/factory --auto`, `/factory-run --auto`)
- Test: `pi-ext/factory-watch/test/handler.test.ts` (extend)

**Interfaces:**
- Consumes: `parseReviewPendingLine`/`writeReviewDecision` (Task 7), `runReviewLoop` (Task 8), `resolveEditorLaunch` (Task 6), `computeReviewFiles` (Task 5).
- Produces: `/factory [--auto]`, `/factory-run [--auto] [task-id]` -- no flag uses the new foreground path; `--auto` reproduces `launchAndWatch` exactly, unchanged.

- [ ] **Step 1: Write the failing tests**

Add to `pi-ext/factory-watch/test/handler.test.ts` (alongside the existing `/factory`/`/factory-run` tests):

```typescript
  test("/factory --auto still uses the detached launchAndWatch path", async () => {
    const { commands } = capture();
    const ctx = fakeCtx();
    await commands.get("factory")!.handler("--auto", ctx);
    expect(spawn).toHaveBeenCalled();
    expect(ctx.ui.notify).toHaveBeenCalledWith(expect.stringContaining("factory started"), "info");
  });

  test("/factory without --auto spawns non-detached and opens the review overlay on review_pending", async () => {
    const child = new EventEmitter() as EventEmitter & {
      stdout: EventEmitter; stdin: { write: ReturnType<typeof vi.fn> }; unref: () => void;
    };
    child.stdout = new EventEmitter();
    child.stdin = { write: vi.fn() };
    child.unref = () => {};
    vi.mocked(spawn).mockReturnValue(child as unknown as ReturnType<typeof spawn>);

    const ui: UiApi = {
      notify: vi.fn(), setStatus: vi.fn(), setWidget: vi.fn(), select: vi.fn(),
      confirm: vi.fn(async () => true), editor: vi.fn(),
      custom: vi.fn(async () => ({ type: "approve" })),
    };
    const { commands } = capture();
    const ctx = fakeCtx({ ui });

    const handlerDone = commands.get("factory")!.handler("", ctx);
    child.stdout.emit(
      "data",
      Buffer.from(JSON.stringify({ type: "review_pending", task_id: "T-001", start_commit: "abc123" }) + "\n"),
    );
    child.emit("exit", 0);
    await handlerDone;

    expect(ui.custom).toHaveBeenCalled();
    expect(child.stdin.write).toHaveBeenCalledWith(
      JSON.stringify({ decision: "approve", comments: {} }) + "\n",
    );
  });
```

(These extend the existing `describe("factory-watch commands", ...)` block; the file's existing `vi.mock("node:child_process", ...)` at the top already mocks `spawn`/`spawnSync`, and `import { EventEmitter } from "node:events"` is already imported there too.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /c/coding/pi-agent-factory/pi-ext/factory-watch && npm test -- handler`
Expected: FAIL -- `/factory --auto` isn't parsed yet (today's `/factory` ignores its args entirely), and there's no non-detached path to emit `review_pending` on.

- [ ] **Step 3: Implement**

In `index.ts`, add imports:

```typescript
import { computeReviewFiles } from "./review-diff.js";
import { parseReviewPendingLine, writeReviewDecision } from "./review-protocol.js";
import { runReviewLoop } from "./review-overlay.js";
```

Add a tiny shared flag parser near the top-level constants:

```typescript
function parseAutoFlag(args: string): { auto: boolean; rest: string } {
  const auto = /(^|\s)--auto(\s|$)/.test(args);
  const rest = args.replace("--auto", "").trim();
  return { auto, rest };
}
```

Add the new foreground path as a sibling to `launchAndWatch`, inside `factoryWatch`:

```typescript
  async function launchInteractiveReview(ctx: ExtCommandCtx, cmd: Command, label: string): Promise<void> {
    const child = spawn(cmd.bin, cmd.args, { cwd: ctx.cwd, stdio: ["pipe", "pipe", "pipe"] });
    ctx.ui.notify(`factory started (${label}, human review on)`, "info");

    child.stdout.on("data", (chunk: Buffer) => {
      for (const line of chunk.toString("utf-8").split("\n")) {
        const message = parseReviewPendingLine(line);
        if (message === null) {
          continue;
        }
        const files = computeReviewFiles(ctx.cwd, message.start_commit);
        void runReviewLoop(ctx.ui, ctx.cwd, message.task_id, message.start_commit, files)
          .then((decision) => writeReviewDecision(child.stdin, decision));
      }
    });

    await new Promise<void>((resolve) => child.on("exit", () => resolve()));
    ctx.ui.notify("factory run finished", "info");
  }
```

Change the `/factory` handler:

```typescript
  pi.registerCommand("factory", {
    description: "Run the next todo factory task, watching progress live",
    handler: async (args: string, ctx: ExtCommandCtx) => {
      const lockPath = join(ctx.cwd, LOCK_FILE);
      if (isAlreadyRunning(ctx, lockPath)) {
        return;
      }

      if (ctx.model === undefined) {
        ctx.ui.notify("no model selected in this session -- can't launch factory", "error");
        return;
      }

      const { auto } = parseAutoFlag(args);
      const cmd = buildRunCommand(ctx.model.provider, ctx.model.id);
      if (auto) {
        launchAndWatch(ctx, cmd, `${ctx.model.provider}/${ctx.model.id}`);
      } else {
        await launchInteractiveReview(ctx, cmd, `${ctx.model.provider}/${ctx.model.id}`);
      }
    },
  });
```

Apply the same `parseAutoFlag`/branch pattern to `/factory-run`'s handler (parse `--auto` out of `args` before the existing task-id trimming/listing logic, same `if (auto) { launchAndWatch(...) } else { await launchInteractiveReview(...) }` branch at its existing `launchAndWatch` call site).

Add a section to `pi-ext/factory-watch/README.md` documenting `--auto` next to the existing `/factory`/`/factory-run` entries.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /c/coding/pi-agent-factory/pi-ext/factory-watch && npm run typecheck && npm test`
Expected: PASS (full suite)

- [ ] **Step 5: Commit**

```bash
git add pi-ext/factory-watch/src/index.ts pi-ext/factory-watch/README.md pi-ext/factory-watch/test/handler.test.ts
git commit -m "feat(factory-watch): wire --auto flag and the interactive review path into /factory, /factory-run"
```

---

## Manual Verification (after all tasks complete)

This feature is fundamentally a real-terminal experience that automated tests can't fully exercise end to end. Hand off to the user directly:

1. Run `pif`, create a real todo task, run `/factory` (no `--auto`) with a real model, and confirm the review overlay opens when automated review passes.
2. Exercise navigation (↑↓, Enter, Esc/q at both summary and file view), a comment (`c`), approve (`a`) and reject (`r`, verifying the "at least one comment" refusal), and `e` with `$VISUAL` set to `code -w` (and, if available, a terminal editor under tmux).
3. Confirm `/factory --auto` still behaves exactly as before (detached, no overlay).
4. Confirm a rejected task's next dev iteration prompt actually contains the human's comment text (inspect the session/log, or the dev agent's own transcript).
