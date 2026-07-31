# Mission Control — Observation Increment — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make mission control a useful observation surface: open any agent's real pi session natively (`pi --session`), show meaningful per-stage summaries, tail deterministic-step logs, and reach the existing human-review diff browser from the dashboard — all by reuse, with the orchestration pipeline untouched.

**Architecture:** Additive telemetry on the Python side (`AgentResult.session_id`, three new optional `status.report` fields, per-role summary strings, validation-gate log capture) feeds new fields into `sessions/.factory-status.json`. The standalone TypeScript dashboard reads those fields and, on Enter over a row, opens the right window: `pi --session <file>` for agent rows, a plain log tail for the validation row, and a reused `ReviewOverlay` browse window for the human-review row. The old dirty-log viewer is deleted.

**Tech Stack:** Python (pytest), TypeScript (`pi-ext/factory-watch`, vitest, `@earendil-works/pi-tui`).

## Global Constraints

- **The orchestration pipeline is untouched.** Every Python change is additive telemetry. None may alter `run_task`'s control flow, the validation/review/human-review gates, the review-findings→dev feedback loop, or how roles hand off manifest/kb-entries/feedback via `compose_prompt`. Existing pipeline/gate tests must stay green unchanged.
- Session files live at `~/.pi/agent/sessions/<project-slug>/<timestamp>_<uuid>.jsonl`; the `<uuid>` equals the `id` in each run's first `session` stdout event (verified). Resolve by globbing the uuid across `*/`, never by reconstructing the slug.
- Standalone TS entry points run via plain `node <file>.ts`: **no TypeScript constructor parameter properties**, and **relative imports between source files must use `.ts` extensions** (tsconfig has `allowImportingTsExtensions`). Both pitfalls are already fixed in existing files — match them.
- Terminal windows open via `spawnTerminalWindow`, which uses `cmd /c start "" <command> <args>` on win32 (do not reintroduce `powershell Start-Process`).
- `pi --session` shows a snapshot of an in-progress session (not a live mirror). Accepted; not gated.
- Deferred to Increment 2 (do NOT build here): deciding a review from the dashboard (E2), and pause/steer workflow control (F).
- Design reference: `docs/superpowers/specs/2026-07-23-mission-control-observation-design.md`.

---

## File Structure

**Python (`src/factory/`):**
- `orchestrator/types.py` (modify) — `AgentResult.session_id: str | None`.
- `orchestrator/pi_backend.py` (modify) — `parse_session_id`, populate `AgentResult.session_id`.
- `orchestrator/status.py` (modify) — `session_id`/`summary`/`start_commit` optional params on all four reporters + entry dict.
- `orchestrator/backends.py` (modify) — `SubprocessGateRunner` optionally tees gate output to a log file (for D).
- `orchestrator/nodes.py` (modify) — build per-role `summary`; pass `session_id`/`summary` into `status.report`; give validation a log path.
- `orchestrator/runner.py` (modify) — pass `start_commit` on the human-review "blocked" report; thread the validation log dir.
- `orchestrator/review_diff.py` or wherever the human-review diff is computed — only if Task 1's root cause lands here (Python side); otherwise the fix is TS-side in `review-diff.ts`.

**TypeScript (`pi-ext/factory-watch/src/`):**
- `status-format.ts` (modify) — carry `session_id`/`summary`/`start_commit`; render the summary line.
- `session-path.ts` (new) — resolve a session uuid to its on-disk `.jsonl` path.
- `mission-control-dashboard.ts` (modify) — Enter dispatch + summary rendering; drop the transcript wiring.
- `mission-control-review.ts` (new) — standalone browse window reusing `ReviewOverlay` + `computeReviewFiles` (E1).
- `mission-control-transcript.ts` (delete) + `test/mission-control-transcript.test.ts` (delete).

---

### Task 1: Debug & fix the human-review "0 changes / crashing" bug

**REQUIRED SUB-SKILL:** superpowers:systematic-debugging. This is an investigative task — the fix code is determined by root-cause analysis, not pre-written here. Do not guess-fix.

**Files:**
- Investigate: `src/factory/orchestrator/runner.py` (`start_commit` capture, human-review call), `pi-ext/factory-watch/src/review-diff.ts` (`computeReviewFiles`, `computeFileDiffText`), `src/factory/orchestrator/git_ops.py` (`changed_files`, `head_commit`).
- Test: wherever the failing reproduction naturally lands (Python `tests/unit/orchestrator/` or TS `test/review-diff.test.ts`).

**Two distinct symptoms — reproduce and root-cause each separately:**
1. Human-review reports **0 changed files** when changes exist.
2. Human-review **"crashes during execution."**

- [ ] **Step 1: Reproduce symptom (2) — the crash.** Run the interactive pipeline to the human-review gate (`/factory-run <task>` without `--auto`, or drive `run_task` with `human_review` set in a test). Capture the exact error/stack. Record it in the report before touching anything.

- [ ] **Step 2: Reproduce symptom (1) with a failing automated test.** Following `computeReviewFiles(cwd, startCommit)`: construct a repo where the dev stage produced real changes, drive the human-review path, and assert the reported file list is non-empty. Watch it fail (0 files). Leading hypothesis to check first (do not assume): `start_commit` is captured at `runner.py:67` via `git_ops.head_commit` **before** dev runs, but the diff at review time may compare `start_commit..HEAD` and miss **uncommitted** dev changes — the same family as the `changed_files` working-tree fix (`git diff <start_commit>` without `..HEAD`). Confirm what `computeReviewFiles` actually diffs and whether dev's work is committed by then.

- [ ] **Step 3: Root-cause both symptoms.** State the single root cause (or two) in the report with file:line evidence. Only proceed to a fix once the failing test in Step 2 pins symptom (1) and the crash in Step 1 is understood.

- [ ] **Step 4: Fix the root cause.** Smallest change that addresses the cause. If it is the diff-range issue, align it with `git_ops.changed_files`' working-tree semantics. Keep the fix additive to unrelated behavior.

- [ ] **Step 5: Verify.** The Step 2 test passes; the Step 1 crash no longer reproduces; full suites green (`uv run python scripts/gates/all.py` and `cd pi-ext/factory-watch && npm test`).

- [ ] **Step 6: Commit.**

```bash
git add -A
git commit -m "fix: human-review reports actual changed files and no longer crashes"
```

---

### Task 2: `status.py` — three additive report fields

**Files:**
- Modify: `src/factory/orchestrator/status.py`
- Test: `tests/unit/orchestrator/test_status.py` (create if absent; else extend)

**Interfaces:**
- Produces: `StatusReporter.report(..., session_id: str | None = None, summary: str | None = None, start_commit: str | None = None)` on the `Protocol`, `NullStatusReporter`, `FileStatusReporter`, `FakeStatusReporter`; `FileStatusReporter` writes `session_id`/`summary`/`start_commit` into each pipeline entry dict.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/orchestrator/test_status.py
import json
from pathlib import Path

import pytest
from factory.orchestrator.status import FileStatusReporter

pytestmark = pytest.mark.unit


def test_report_persists_session_id_summary_and_start_commit(tmp_path: Path):
    path = tmp_path / "status.json"
    r = FileStatusReporter(path=path, session_id="s1")
    r.report(
        task_id="T-1", node="dev", node_state="running", attempt=1, max_attempts=3,
        session_id="019f-uuid", summary="changed 3 files; unit tests pass",
    )
    r.report(
        task_id="T-1", node="human-review", node_state="blocked", attempt=1, max_attempts=1,
        start_commit="abc123",
    )
    record = json.loads(path.read_text(encoding="utf-8"))
    dev = next(e for e in record["pipeline"] if e["node"] == "dev")
    hr = next(e for e in record["pipeline"] if e["node"] == "human-review")
    assert dev["session_id"] == "019f-uuid"
    assert dev["summary"] == "changed 3 files; unit tests pass"
    assert hr["start_commit"] == "abc123"


def test_report_defaults_new_fields_to_none(tmp_path: Path):
    path = tmp_path / "status.json"
    FileStatusReporter(path=path, session_id="s1").report(
        task_id="T-1", node="validation", node_state="pass", attempt=1, max_attempts=1,
    )
    entry = json.loads(path.read_text(encoding="utf-8"))["pipeline"][0]
    assert entry["session_id"] is None
    assert entry["summary"] is None
    assert entry["start_commit"] is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /c/coding/pi-agent-factory && uv run pytest tests/unit/orchestrator/test_status.py -v`
Expected: FAIL with `TypeError: report() got an unexpected keyword argument 'session_id'`.

- [ ] **Step 3: Implement.** Add the three keyword-only params (default `None`) to `report` on all four reporter types (`StatusReporter` Protocol, `NullStatusReporter`, `FileStatusReporter`, `FakeStatusReporter`). In `FileStatusReporter.report`, add to the `entry` dict:

```python
            "session_id": session_id,
            "summary": summary,
            "start_commit": start_commit,
```

In `FakeStatusReporter.report`, include them in the recorded call dict the same way.

- [ ] **Step 4: Run to verify it passes**

Run: `cd /c/coding/pi-agent-factory && uv run pytest tests/unit/orchestrator/test_status.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/factory/orchestrator/status.py tests/unit/orchestrator/test_status.py
git commit -m "feat: status reporter carries session_id, summary, and start_commit per stage"
```

---

### Task 3: `AgentResult.session_id` + `parse_session_id`

**Files:**
- Modify: `src/factory/orchestrator/types.py`, `src/factory/orchestrator/pi_backend.py`
- Test: `tests/unit/orchestrator/test_pi_parse.py` (extend)

**Interfaces:**
- Produces: `AgentResult.session_id: str | None = None`; `parse_session_id(stdout: str) -> str | None` in `pi_backend.py`; `PiAgentBackend.run` populates `AgentResult.session_id` from stdout.

- [ ] **Step 1: Write the failing tests** (append to `tests/unit/orchestrator/test_pi_parse.py`; it already imports from `pi_backend`)

```python
def test_parse_session_id_extracts_id_from_session_event():
    from factory.orchestrator.pi_backend import parse_session_id
    stream = "\n".join([
        '{"type":"session","version":3,"id":"019f8ef3-6103-725c-997a-a9159325ebf1"}',
        '{"type":"message_end","message":{"role":"assistant","content":[]}}',
    ])
    assert parse_session_id(stream) == "019f8ef3-6103-725c-997a-a9159325ebf1"


def test_parse_session_id_returns_none_when_absent():
    from factory.orchestrator.pi_backend import parse_session_id
    assert parse_session_id('{"type":"message_end","message":{}}') is None
    assert parse_session_id("") is None


def test_run_populates_session_id(monkeypatch, tmp_path):
    from factory.orchestrator.pi_backend import PiAgentBackend
    from factory.orchestrator.types import AgentRole

    class _FakeProc:
        def __init__(self, lines): self.stdout = iter(lines); self.returncode = 0
        def wait(self): pass

    lines = [
        '{"type":"session","id":"abc-123"}\n',
        '{"type":"message_end","message":{"role":"assistant","content":[{"type":"text","text":"```json\\n{}\\n```"}]}}\n',
    ]
    monkeypatch.setattr(subprocess, "Popen", lambda cmd, **kw: _FakeProc(lines))
    result = PiAgentBackend(tmp_path, tmp_path / "ext.ts").run(AgentRole.DEV, "hi")
    assert result.session_id == "abc-123"
```

- [ ] **Step 2: Run to verify failure**

Run: `cd /c/coding/pi-agent-factory && uv run pytest tests/unit/orchestrator/test_pi_parse.py -v`
Expected: FAIL (`ImportError: cannot import name 'parse_session_id'`).

- [ ] **Step 3: Implement.** In `types.py`, add to `AgentResult`:

```python
    session_id: str | None = None
```

In `pi_backend.py`, add:

```python
def parse_session_id(stdout: str) -> str | None:
    """Return the id from Pi's first `session` event, or None."""
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict) and event.get("type") == "session":
            sid = event.get("id")
            return sid if isinstance(sid, str) else None
    return None
```

In `PiAgentBackend.run`, where `AgentResult` is currently returned, populate the field:

```python
        return AgentResult(ok=ok, output=output, raw=raw, session_id=parse_session_id(stdout))
```

(Apply to the normal return **and** the field-mismatch early path if it constructs its own `AgentResult`.)

- [ ] **Step 4: Run to verify pass**

Run: `cd /c/coding/pi-agent-factory && uv run pytest tests/unit/orchestrator/test_pi_parse.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/factory/orchestrator/types.py src/factory/orchestrator/pi_backend.py tests/unit/orchestrator/test_pi_parse.py
git commit -m "feat: capture each role's pi session id from its output"
```

---

### Task 4: `nodes.py` — per-role summaries + thread session_id/summary

**Files:**
- Modify: `src/factory/orchestrator/nodes.py`
- Test: `tests/unit/orchestrator/test_nodes_context_dev.py`, `test_nodes_val_review.py` (extend — read them first for fixture conventions)

**Interfaces:**
- Consumes: `AgentResult.session_id` (Task 3), `status.report`'s `session_id`/`summary` (Task 2).
- Produces: each role-runner passes `session_id=result.session_id` and a short `summary=...` into its terminal (pass/completed) `status.report` call. A helper `_summarize_review(findings: list) -> str` and `_summarize_dev(...)`/reuse of `_summarize_manifest`.

- [ ] **Step 1: Write the failing tests.** Read both test files' conventions first. Add tests asserting that after a scripted run, the `FakeStatusReporter` recorded a `summary` and `session_id` for the stage. Shapes (adapt to real fixtures — no comment-only bodies):
  - context-gather pass → recorded `summary` equals `_summarize_manifest(manifest)` and `session_id` equals the scripted result's session id.
  - dev pass → recorded `summary` contains the unit-test outcome; `session_id` threaded.
  - review: `_summarize_review(["fix error handling", "extract magic number"])` returns a string containing both finding texts (e.g. `"requested: fix error handling; extract magic number"`), and a changes-requested run records it as `summary`.

- [ ] **Step 2: Run to verify failure.**

Run: `cd /c/coding/pi-agent-factory && uv run pytest tests/unit/orchestrator/test_nodes_context_dev.py tests/unit/orchestrator/test_nodes_val_review.py -v`
Expected: FAIL (summaries/session_id not recorded yet).

- [ ] **Step 3: Implement.**
  - Add `_summarize_review(findings: list) -> str`: if empty, `"DoD not met"` else `"requested: " + "; ".join(str(f)[:60] for f in findings[:3])`.
  - In `run_context_gatherer`'s PASS `status.report` (the `→ dev:` one), add `session_id=result.session_id, summary=_summarize_manifest(manifest)`.
  - In `run_dev`'s PASS `status.report` (the `→ validation: unit tests green` one), add `session_id=result.session_id, summary="changed files; unit tests pass"` (keep it derived from what's available — do not invent a git call here).
  - In `run_review`'s two terminal `status.report` calls (PASS and changes-requested), add `session_id=result.session_id` and `summary=_summarize_review(findings)` (for PASS use `"DoD met; gates pass"`).
  - `run_validation` has no agent/session; leave its `session_id`/`summary` as default `None` (its log tail is Task 6/D).

- [ ] **Step 4: Run to verify pass.**

Run: `cd /c/coding/pi-agent-factory && uv run pytest tests/unit/orchestrator/ -v`
Expected: PASS (full orchestrator suite — this touches shared code).

- [ ] **Step 5: Commit**

```bash
git add src/factory/orchestrator/nodes.py tests/unit/orchestrator/test_nodes_context_dev.py tests/unit/orchestrator/test_nodes_val_review.py
git commit -m "feat: per-role summaries and session ids threaded into status"
```

---

### Task 5: `runner.py` — record human-review start_commit

**Files:**
- Modify: `src/factory/orchestrator/runner.py`
- Test: `tests/unit/orchestrator/test_human_review_gate_in_runner.py` (extend)

**Interfaces:**
- Consumes: `status.report`'s `start_commit` (Task 2).
- Produces: the human-review "blocked" `status.report` call carries `start_commit=start_commit`.

- [ ] **Step 1: Write the failing test.** Read the file's conventions. Drive `run_task` with a `human_review` gate to the blocked state and a `FakeStatusReporter`; assert the recorded `human-review`/`blocked` call has `start_commit` equal to the repo's start commit (the `_repo` fixture git-inits, so `head_commit` is real).

- [ ] **Step 2: Run to verify failure.**

Run: `cd /c/coding/pi-agent-factory && uv run pytest tests/unit/orchestrator/test_human_review_gate_in_runner.py -v`
Expected: FAIL (`start_commit` not recorded).

- [ ] **Step 3: Implement.** In `runner.py`, the existing "blocked" `status.report(... node="human-review", node_state="blocked" ...)` call (just before `human_review.request_review`) gains `start_commit=start_commit`.

- [ ] **Step 4: Run to verify pass.**

Run: `cd /c/coding/pi-agent-factory && uv run pytest tests/unit/orchestrator/ -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/factory/orchestrator/runner.py tests/unit/orchestrator/test_human_review_gate_in_runner.py
git commit -m "feat: record human-review start_commit in status for the dashboard diff browser"
```

---

### Task 6: Validation-gate log capture (for D)

**Files:**
- Modify: `src/factory/orchestrator/backends.py` (`SubprocessGateRunner`), and the composition root where the gate runner is constructed (`__main__.py`).
- Test: `tests/unit/orchestrator/test_backends.py` (create/extend)

**Interfaces:**
- Produces: `SubprocessGateRunner(repo_root, log_dir: Path | None = None)`; when `log_dir` is set, `run(name)` writes the gate's combined stdout+stderr to `log_dir / f"{name}-gate.log"` and still returns the exit code. `run_validation` and the `GateRunner` protocol are **unchanged** — the runner already holds `log_dir`, so no orchestration signature changes. Only `backends.py` and the construction site change.

- [ ] **Step 1: Write the failing test.**

```python
# tests/unit/orchestrator/test_backends.py
import pytest
from pathlib import Path
from factory.orchestrator.backends import SubprocessGateRunner

pytestmark = pytest.mark.unit


def test_gate_runner_writes_log_when_log_dir_set(tmp_path: Path):
    # A trivial gate script that prints and exits 0.
    (tmp_path / "scripts" / "gates").mkdir(parents=True)
    # Point the runner at a real script via monkeypatch-free approach: use "unit"
    # mapping but a stub script. Simplest: assert the log file is created and
    # contains the child's stdout for a known script. Adapt to the real _SCRIPTS
    # mapping — run a gate that exists in this repo and just assert the log file
    # appears and is non-empty.
    runner = SubprocessGateRunner(tmp_path, log_dir=tmp_path / "logs")
    # (Use the real repo_root + an existing gate in the actual test; the point is
    # the log file exists afterward.)
```

(Read `test_backends.py`/existing gate tests for the real convention; the assertion that matters: with `log_dir` set, `run("unit")` produces `log_dir/"unit-gate.log"` containing the child output, and the return code is unchanged. Without `log_dir`, behavior is exactly as today.)

- [ ] **Step 2: Run to verify failure.**

Run: `cd /c/coding/pi-agent-factory && uv run pytest tests/unit/orchestrator/test_backends.py -v`
Expected: FAIL (`SubprocessGateRunner` takes no `log_dir`).

- [ ] **Step 3: Implement.**

```python
    def __init__(self, repo_root: Path, log_dir: Path | None = None) -> None:
        self._repo_root = repo_root
        self._log_dir = log_dir

    def run(self, name: str) -> int:
        script = self._SCRIPTS[name]
        if self._log_dir is None:
            return subprocess.run([sys.executable, script], cwd=self._repo_root).returncode
        self._log_dir.mkdir(parents=True, exist_ok=True)
        log_path = self._log_dir / f"{name}-gate.log"
        proc = subprocess.run(
            [sys.executable, script], cwd=self._repo_root,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        log_path.write_text((proc.stdout or "") + (proc.stderr or ""), encoding="utf-8")
        return proc.returncode
```

In `__main__.py`, construct the gate runner with `log_dir=transcript_dir` (the same session-scoped dir threaded elsewhere). No signature change to `run_validation` needed — it already calls `gates.run("sim")`.

- [ ] **Step 4: Run to verify pass.**

Run: `cd /c/coding/pi-agent-factory && uv run pytest tests/unit/orchestrator/ -v` then `uv run python scripts/gates/all.py`
Expected: PASS / green.

- [ ] **Step 5: Commit**

```bash
git add src/factory/orchestrator/backends.py src/factory/orchestrator/__main__.py tests/unit/orchestrator/test_backends.py
git commit -m "feat: capture deterministic gate output to a per-session log for tailing"
```

---

### Task 7: `status-format.ts` — carry & render the new fields

**Files:**
- Modify: `pi-ext/factory-watch/src/status-format.ts`
- Test: `pi-ext/factory-watch/test/status-format.test.ts` (extend)

**Interfaces:**
- Produces: `PipelineEntry` gains `session_id?: string | null; summary?: string | null; start_commit?: string | null`. `MissionControlRow` gains `sessionId: string | null; summary: string | null; startCommit: string | null`. `formatMissionControlRows` populates them from the entry.

- [ ] **Step 1: Write the failing tests.** Read the file's fixture style. Assert `formatMissionControlRows` copies `session_id`→`sessionId`, `summary`→`summary`, `start_commit`→`startCommit` (null when absent), for a record whose `dev` entry has a `session_id`+`summary` and whose `human-review` entry has a `start_commit`.

- [ ] **Step 2: Run to verify failure.**

Run: `cd /c/coding/pi-agent-factory/pi-ext/factory-watch && npm test -- status-format`
Expected: FAIL.

- [ ] **Step 3: Implement.** Extend the two interfaces and map the fields in `formatMissionControlRows` (`sessionId: entry?.session_id ?? null`, etc.).

- [ ] **Step 4: Run to verify pass.**

Run: `cd /c/coding/pi-agent-factory/pi-ext/factory-watch && npm run typecheck && npm test -- status-format`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pi-ext/factory-watch/src/status-format.ts pi-ext/factory-watch/test/status-format.test.ts
git commit -m "feat(factory-watch): mission control rows carry sessionId, summary, startCommit"
```

---

### Task 8: `session-path.ts` — resolve a session uuid to its file

**Files:**
- Create: `pi-ext/factory-watch/src/session-path.ts`
- Test: `pi-ext/factory-watch/test/session-path.test.ts`

**Interfaces:**
- Produces: `resolveSessionPath(sessionId: string, sessionsRoot?: string): string | null` — globs `<sessionsRoot>/*/*_<sessionId>.jsonl` and returns the first match, or null. Default `sessionsRoot` = `join(homedir(), ".pi", "agent", "sessions")`.

- [ ] **Step 1: Write the failing tests.**

```typescript
// pi-ext/factory-watch/test/session-path.test.ts
import { mkdirSync, writeFileSync } from "node:fs";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, test } from "vitest";
import { resolveSessionPath } from "../src/session-path.ts";

describe("resolveSessionPath", () => {
  test("finds the session file by uuid under any project subdir", () => {
    const root = mkdtempSync(join(tmpdir(), "sess-"));
    const proj = join(root, "--C--somewhere--");
    mkdirSync(proj, { recursive: true });
    const file = join(proj, "2026-07-23T00-00-00-000Z_abc-uuid-123.jsonl");
    writeFileSync(file, "{}\n");
    expect(resolveSessionPath("abc-uuid-123", root)).toBe(file);
  });

  test("returns null when no file matches", () => {
    const root = mkdtempSync(join(tmpdir(), "sess-"));
    expect(resolveSessionPath("nope", root)).toBeNull();
  });
});
```

- [ ] **Step 2: Run to verify failure.**

Run: `cd /c/coding/pi-agent-factory/pi-ext/factory-watch && npm test -- session-path`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement** (no constructor params; `.ts` imports). Use `node:fs` `readdirSync` to walk one level of subdirs and match `*_<sessionId>.jsonl` (avoid pulling a glob dependency):

```typescript
import { readdirSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

export function resolveSessionPath(
  sessionId: string,
  sessionsRoot: string = join(homedir(), ".pi", "agent", "sessions"),
): string | null {
  let projectDirs: string[];
  try {
    projectDirs = readdirSync(sessionsRoot, { withFileTypes: true })
      .filter((d) => d.isDirectory())
      .map((d) => d.name);
  } catch {
    return null;
  }
  const suffix = `_${sessionId}.jsonl`;
  for (const dir of projectDirs) {
    let files: string[];
    try {
      files = readdirSync(join(sessionsRoot, dir));
    } catch {
      continue;
    }
    const match = files.find((f) => f.endsWith(suffix));
    if (match) {
      return join(sessionsRoot, dir, match);
    }
  }
  return null;
}
```

- [ ] **Step 4: Run to verify pass.**

Run: `cd /c/coding/pi-agent-factory/pi-ext/factory-watch && npm run typecheck && npm test -- session-path`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pi-ext/factory-watch/src/session-path.ts pi-ext/factory-watch/test/session-path.test.ts
git commit -m "feat(factory-watch): resolve a pi session uuid to its on-disk jsonl path"
```

---

### Task 9: `mission-control-review.ts` — human-review browse window (E1)

**Files:**
- Create: `pi-ext/factory-watch/src/mission-control-review.ts`
- Test: `pi-ext/factory-watch/test/mission-control-review.test.ts`

**Interfaces:**
- Consumes: `computeReviewFiles(cwd, startCommit)` (`review-diff.ts`), `ReviewOverlay` (`review-overlay.ts`).
- Produces: a standalone entry point that, given `--cwd <path> --start-commit <sha>`, mounts `ReviewOverlay` over `computeReviewFiles(cwd, startCommit)` in **browse mode** (no decision sent — E2 deferred). Same TUI mounting pattern as `mission-control-dashboard.ts` (`ProcessTerminal`, `TUI`, `tui.start()`, `tui.setFocus`, `tui.requestRender`).

**Read first:** `review-overlay.ts` (the `ReviewOverlay` constructor + `TuiLike` + `runReviewLoop`) to see how the overlay is built and driven, and `mission-control-dashboard.ts`'s `main()` for the exact TUI mounting sequence. If `ReviewOverlay` is coupled to producing a decision, mount it read-only (ignore/short-circuit the decision path); do not wire a decision channel.

- [ ] **Step 1: Write the failing test.** Unit-test the pure part: a `buildReviewArgs`/arg-parse helper, and that with a mocked `computeReviewFiles` the component renders the file list. Follow the dashboard test's seam (test the pure logic; the argv-guarded `main()` isn't unit-run). At minimum assert the module exports the entry helper and that missing `--start-commit` triggers the usage path (mirror the dashboard's arg handling, including the `indexOf === -1` guard so a missing flag doesn't read `argv[0]`).

- [ ] **Step 2: Run to verify failure.**

Run: `cd /c/coding/pi-agent-factory/pi-ext/factory-watch && npm test -- mission-control-review`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement** the component + `main()`. No constructor parameter properties; `.ts` relative imports. Arg parsing uses the `indexOf === -1 ? undefined : argv[i+1]` guard. Include the `main()` entry guard (`process.argv[1]?.endsWith("mission-control-review.ts")`).

- [ ] **Step 4: Run to verify pass** + smoke.

Run: `cd /c/coding/pi-agent-factory/pi-ext/factory-watch && npm run typecheck && npm test -- mission-control-review`
Then add a `smoke.test.ts` case (mirroring the existing two) that spawns `node mission-control-review.ts` with no args and asserts a fast usage exit, no `ERR_UNSUPPORTED_TYPESCRIPT_SYNTAX`/`ERR_MODULE_NOT_FOUND`.
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pi-ext/factory-watch/src/mission-control-review.ts pi-ext/factory-watch/test/mission-control-review.test.ts pi-ext/factory-watch/test/smoke.test.ts
git commit -m "feat(factory-watch): standalone human-review diff browser reusing ReviewOverlay"
```

---

### Task 10: `mission-control-dashboard.ts` — Enter dispatch, summaries, remove transcript viewer

**Files:**
- Modify: `pi-ext/factory-watch/src/mission-control-dashboard.ts`
- Delete: `pi-ext/factory-watch/src/mission-control-transcript.ts`, `pi-ext/factory-watch/test/mission-control-transcript.test.ts`
- Test: `pi-ext/factory-watch/test/mission-control-dashboard.test.ts` (extend), `test/smoke.test.ts` (drop the transcript case)

**Interfaces:**
- Consumes: `resolveSessionPath` (Task 8), `spawnTerminalWindow` (existing), `MissionControlRow.{sessionId,summary,startCommit}` (Task 7).
- Produces: on Enter over the selected row, dispatch by node:
  - agent rows (`context-gather`, `dev`, `review`, `session-review`) with a `sessionId` → resolve path; if found, `spawnTerminalWindow("pi", ["--session", path], { cwd })`; if not found, notify inline "session not ready".
  - `validation` → `spawnTerminalWindow` a plain tail of the gate log. Build the path from the **top-level `record.session_id`** (the factory run id used for the transcript dir — NOT the row's pi `sessionId`): `<cwd>/sessions/.factory-transcripts/<record.session_id>/sim-gate.log`. win32: `spawnTerminalWindow("powershell", ["-NoExit","-Command",\`Get-Content '<log>' -Wait -Tail 40\`], {cwd})`; on unix, `spawnTerminalWindow("tail", ["-f", "<log>"], {cwd})`. (Pass the tail command straight through `spawnTerminalWindow`, whose win32 branch wraps it in `cmd /c start`.)
  - `human-review` with a `startCommit` → `spawnTerminalWindow("node", [<mission-control-review.ts path>, "--cwd", cwd, "--start-commit", startCommit], { cwd })`.
  - `render()` prints each row's `summary` (width-wrapped) under the existing handoff line.

**Read first:** the current `mission-control-dashboard.ts` (`onSelectTranscript`, `handleInput` Enter path, `render`) and remove the `buildTranscriptPath`/transcript wiring.

- [ ] **Step 1: Write the failing tests.** Extend `mission-control-dashboard.test.ts` (mock `spawnTerminalWindow` and `resolveSessionPath`): pressing Enter on a `dev` row with a `sessionId` calls `spawnTerminalWindow("pi", ["--session", <resolved>], ...)`; on a `human-review` row with a `startCommit` calls `spawnTerminalWindow("node", [..."mission-control-review.ts", "--start-commit", <sha>...], ...)`; on `validation` calls the tail command; and `render()` output contains a row's `summary` text. Follow the existing dashboard test seam.

- [ ] **Step 2: Run to verify failure.**

Run: `cd /c/coding/pi-agent-factory/pi-ext/factory-watch && npm test -- mission-control-dashboard`
Expected: FAIL.

- [ ] **Step 3: Implement** the dispatch + summary render; delete `mission-control-transcript.ts` + its test; drop the transcript case from `smoke.test.ts`; remove now-dead `buildTranscriptPath`/`onSelectTranscript`-transcript code.

- [ ] **Step 4: Run to verify pass** (full TS suite — final integration).

Run: `cd /c/coding/pi-agent-factory/pi-ext/factory-watch && npm run typecheck && npm test`
Expected: PASS (all files; transcript files gone).

- [ ] **Step 5: Commit**

```bash
git add -A pi-ext/factory-watch
git commit -m "feat(factory-watch): dashboard opens pi --session / gate-log tail / review browser; drop dirty-log viewer"
```

---

## Manual Verification (after all tasks)

1. `/factory-run <task>` (no `--auto`); confirm mission control opens and rows show meaningful summaries (review findings, dev result).
2. Enter on `dev`/`review`/`context-gather` → a new window opens the real pi session (native rendering); typing continues that agent.
3. Enter on `validation` → a window tails `sim-gate.log`, updating as the gate runs.
4. Enter on `human-review` (once the run blocks) → the diff browser opens and shows the **actual** changed files (Task 1 fix), navigable as before.
5. Confirm `/factory --auto` and the pipeline itself behave exactly as before (gates + handoffs unchanged).
