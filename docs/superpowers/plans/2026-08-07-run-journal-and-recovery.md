# Run Journal and Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a factory run inspectable and safely resumable after process death, reboot, or agent context exhaustion without relying on conversation history.

**Architecture:** Add an append-only run journal plus atomic latest checkpoint under the ignored per-session runtime directory. The orchestrator checkpoints Git patches and completed node outputs at stable transitions. A deterministic recovery module classifies compatibility and exposes inspect/resume/abandon CLI operations; context exhaustion uses the same checkpoint to launch a fresh role session.

**Tech Stack:** Python 3.11+, JSONL, atomic pathlib writes, SHA-256, Git binary patches, pytest; existing PIF status/lock mechanisms.

## Global Constraints

- One factory run per working tree remains the concurrency model.
- A completed attempt is never replayed for side effects.
- Resume never silently adopts external edits.
- An incomplete final JSONL line is tolerated; `checkpoint.json` is atomically replaced.
- Context-limit continuation may be automatic only when repository fingerprints remain compatible.
- Reboot/process recovery requires human confirmation by default.
- Patch checkpoints are local recovery data, not durable project evidence.

---

## File Structure

**Create:**
- `src/factory/orchestrator/journal.py` — event/checkpoint persistence and replay.
- `src/factory/orchestrator/recovery.py` — compatibility classification and recovery actions.
- `src/factory/orchestrator/run_cli.py` — inspect/resume/abandon commands.
- `tests/unit/orchestrator/test_journal.py`
- `tests/unit/orchestrator/test_recovery.py`
- `tests/unit/orchestrator/test_run_cli.py`
- `tests/integration/orchestrator/test_resume_run.py`

**Modify:**
- `src/factory/orchestrator/types.py` — structured interruption reason.
- `src/factory/orchestrator/pi_backend.py` — classify context/token limits.
- `src/factory/orchestrator/git_ops.py` — tree/worktree fingerprint and patch checkpoint helpers.
- `src/factory/orchestrator/nodes.py` — node lifecycle callbacks and continuation prompt.
- `src/factory/orchestrator/runner.py` — stable checkpoints and resume input.
- `src/factory/orchestrator/__main__.py` — `run-state` command family.
- existing tests for backend, nodes, runner, and CLI.

### Task 1: Append-only journal and atomic checkpoint

**Interfaces:**

```python
@dataclass(frozen=True)
class RunEvent:
    sequence: int
    at: str
    run_id: str
    task_id: str
    node: str
    attempt_id: str
    state: str  # started|completed|failed|interrupted
    data: dict

@dataclass
class RunCheckpoint:
    schema_version: int
    run_id: str
    task_id: str
    node: str
    attempt: int
    remaining: dict[str, int]
    start_commit: str
    head_commit: str
    worktree_fingerprint: str
    patch_path: str | None
    completed: list[dict]
    agent_sessions: dict[str, str]
    pending_human_round: int | None
    artifacts: list[str]
    interruption: str | None

class RunJournal:
    def append(self, event: RunEvent) -> None: ...
    def checkpoint(self, checkpoint: RunCheckpoint) -> None: ...
    def events(self) -> list[RunEvent]: ...
    def latest(self) -> RunCheckpoint | None: ...
```

- [ ] Write tests proving sequential append, `flush`+`os.fsync`, atomic checkpoint replacement, and replay ignoring only an incomplete final JSON line while rejecting corruption in an earlier line.
- [ ] Implement `journal.py`; use `dataclasses.asdict`, one compact JSON object per line, and a `.tmp`+`replace` checkpoint write.
- [ ] Run `uv run pytest tests/unit/orchestrator/test_journal.py -v` and static checks.
- [ ] Commit with `feat(orchestrator): add durable run journal`.

The central test must include:

```python
def test_replay_ignores_only_partial_tail(tmp_path):
    journal = RunJournal(tmp_path)
    journal.append(event(1, "started"))
    with (tmp_path / "journal.jsonl").open("ab") as f:
        f.write(b'{"sequence": 2')
    assert [e.sequence for e in journal.events()] == [1]
```

### Task 2: Git patch checkpoints and compatibility fingerprints

**Interfaces:**

```python
class GitOps(Protocol):
    ...
    def worktree_fingerprint(self, repo_root: Path, start_commit: str) -> str: ...
    def write_patch(self, repo_root: Path, start_commit: str, path: Path) -> Path: ...
    def check_patch(self, repo_root: Path, base_commit: str, path: Path) -> bool: ...
```

Fingerprint is SHA-256 over `git diff --binary <start_commit>` bytes plus the
sorted `git ls-files --others --exclude-standard -z` names and bytes, so untracked
dev output participates. `write_patch` includes tracked binary diff and a tar-free
JSON sidecar for untracked files (`path.with_suffix(".untracked.json")`) with
base64 data and mode. Paths outside the repository are rejected.

- [ ] Add real-repository tests for tracked, binary, and untracked changes; equal worktrees must have equal fingerprints independent of mtime.
- [ ] Add patch applicability tests against matching and diverged bases.
- [ ] Implement methods in `git_ops.py` and scriptable equivalents in `FakeGitOps`.
- [ ] Run focused tests and commit `feat(orchestrator): checkpoint working-tree changes`.

### Task 3: Recovery classification

**Interfaces:**

```python
class RecoveryState(str, Enum):
    RESUMABLE = "resumable"
    INSPECT_ONLY = "inspect-only"
    CONFLICT = "conflict"
    COMPLETE = "complete"

@dataclass(frozen=True)
class RecoveryAssessment:
    state: RecoveryState
    reasons: list[str]
    actions: list[str]


def assess_recovery(repo_root: Path, checkpoint: RunCheckpoint, git_ops: GitOps) -> RecoveryAssessment: ...
def abandon_run(run_dir: Path, reason: str) -> Path: ...
```

Classification rules are exact:

- `complete` when checkpoint node is `completed`/`closed`;
- `resumable` when start commit resolves, HEAD and fingerprint match;
- `resumable` with action `restore-patch` when HEAD matches expected and saved patch checks cleanly;
- `conflict` when HEAD diverged or external working-tree changes differ;
- `inspect-only` when a referenced patch/artifact is missing or corrupt.

- [ ] Write one test per rule, including no mutation during assessment.
- [ ] Implement recovery and an atomic `abandoned.json` marker retaining reason/time/checkpoint hash.
- [ ] Run tests and commit `feat(orchestrator): classify interrupted run recovery`.

### Task 4: Structured context-limit interruption

**Interfaces:**

```python
class InterruptionReason(str, Enum):
    CONTEXT_LIMIT = "context_limit"
    IDLE_TIMEOUT = "idle_timeout"
    TOTAL_TIMEOUT = "total_timeout"
    PROCESS_EXIT = "process_exit"

@dataclass
class AgentResult:
    ...
    interruption: InterruptionReason | None = None
```

`PiAgentBackend` classifies context exhaustion only from explicit provider/Pi
signals in parsed events or matched terminal errors (`context length`, `maximum
context`, `token limit`, `prompt is too long`). Timeouts retain their distinct
reasons. Unknown non-zero exits are `PROCESS_EXIT`; successful results remain
`None`.

- [ ] Add backend parser tests for each explicit signal and a negative test where ordinary prose mentions “token limit.”
- [ ] Implement classification in one pure `classify_interruption(returncode, output, timed_out_reason)` function.
- [ ] Add `build_continuation_context(task, checkpoint, prior_output, diff, gate_results) -> str` to `prompts.py`; include exact task/DoD, completed outputs, current diff, remaining work, and explicit instruction to inspect rather than repeat.
- [ ] Test that context-limit continuation gets a fresh backend call and remains within the same attempt budget; timeout/process exit follow existing retry behavior.
- [ ] Commit `feat(orchestrator): classify and continue context-limited agents`.

### Task 5: Instrument pipeline checkpoints

Add a `RunExecution` dependency:

```python
@dataclass
class RunExecution:
    journal: RunJournal
    run_dir: Path
    git_ops: GitOps

    def start_attempt(...): ...
    def finish_attempt(...): ...
    def interrupt_attempt(...): ...
    def save_checkpoint(...): ...
```

`run_task(..., execution: RunExecution | None = None, resume: RunCheckpoint | None = None)` remains backward compatible. Instrument stable boundaries:

- context gather complete;
- each dev attempt after transcript and unit gate;
- validation evidence complete;
- automated review complete;
- before/after each human decision;
- code commit complete;
- evidence manifest complete;
- session review complete.

Each checkpoint writes the current patch before its checkpoint JSON. A completed
node output is referenced by transcript/evidence hash, not copied into the journal.

- [ ] Write an integration-style unit test that raises a scripted exception after dev completion and asserts the checkpoint identifies validation as next.
- [ ] Write a resume test proving context gathering and completed dev are not rerun.
- [ ] Implement runner/node hooks without changing behavior when `execution=None`.
- [ ] Run the complete orchestrator suite and commit `feat(orchestrator): checkpoint pipeline transitions`.

### Task 6: Run-state CLI and stale-lock flow

Commands:

```text
python -m factory.orchestrator run-state current --repo . --json
python -m factory.orchestrator run-state inspect <run-id> --repo . --json
python -m factory.orchestrator run-state resume <run-id> --repo .
python -m factory.orchestrator run-state abandon <run-id> --repo . --reason "..."
```

- `current` finds the newest non-complete checkpoint.
- `inspect` returns checkpoint plus `RecoveryAssessment`.
- `resume` exits `3` for conflict, `4` for inspect-only, and otherwise invokes `run_next` with the checkpoint.
- `abandon` requires a non-empty reason and never deletes evidence or patches.

- [ ] Add CLI tests for JSON/stdout purity and every exit code.
- [ ] Change orchestrator startup: a dead PID lock with a resumable checkpoint does not silently overwrite state; ordinary `run` exits with a message directing the caller to `run-state resume`.
- [ ] Preserve current stale-lock self-healing when no checkpoint exists.
- [ ] Add real-repository kill/resume integration test.
- [ ] Run `uv run pytest -q`, pyright, and Ruff.
- [ ] Commit `feat(orchestrator): resume interrupted factory runs`.

## Plan Self-review

- Covers journal durability, patch checkpoints, stale-lock recovery, compatibility checks, context-limit continuation, and deterministic CLI.
- Resume is conservative: no auto-adoption or silent merge.
- Publication/freshness/browser controls remain in their dedicated plans.
- All interfaces consumed by later plans (`RunCheckpoint`, `RecoveryAssessment`, CLI JSON) are named explicitly.
