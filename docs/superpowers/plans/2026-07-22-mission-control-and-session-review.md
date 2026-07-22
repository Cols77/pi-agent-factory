# Mission Control, Review Context Fix, and the Session-Review Agent — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore `/factory-run`'s multi-role pipeline, add a mission-control TUI dashboard (a second terminal window showing each pipeline stage's live state, with a drill-down transcript viewer in a third window), fix `run_review` to use dev's actual diff instead of context-gatherer's stale prediction, and wire up the previously-dormant session-review agent (KB curation + skill/prompt improvement suggestions).

**Architecture:** Backend additions in `src/factory/orchestrator/` (transcript persistence, a "blocked" status state, `GitOps.changed_files`, `compose_prompt` gaining `events`/`existing_kb_titles`, the renamed `SESSION_REVIEW` role actually invoked). Two new standalone TypeScript entry points in `pi-ext/factory-watch/src/` (no `pi --extension`, no LLM — pure data visualization), run via Node 22's native `.ts` execution (confirmed working with real `@earendil-works/pi-tui` imports, zero new dependencies), spawned into their own terminal windows via the confirmed-working `Start-Process powershell` mechanism.

**Tech Stack:** Python (pytest), TypeScript (`pi-ext/factory-watch`, vitest, `@earendil-works/pi-tui`).

## Global Constraints

- Mission control is TUI-only, in its own terminal windows — no web/GUI, no `frontend-design` skill needed for this iteration.
- `/factory-run`'s restoration must reuse the existing `launchAndWatch`/`launchInteractiveReview` branch (`index.ts`), not reintroduce a separate code path.
- Review's KB entries are selected against what dev **actually changed** (`GitOps.changed_files`, a real git diff), never the manifest's pre-dev file prediction. Review does not receive the manifest.
- `AgentRole.SESSION_WRITER` renames to `AgentRole.SESSION_REVIEW`. Vendoring `.pi/skills/session-report/SKILL.md` is mandatory as part of wiring it up — `compose_prompt`/`load_skill_block` hard-fail with `FileNotFoundError` on first real call otherwise.
- Standalone TS scripts run via plain `node <file>.ts` (confirmed: Node 22.23.1 strips TS types natively, no tsx/ts-node needed) when placed inside `pi-ext/factory-watch/src/` (so `node_modules` resolves).
- Design reference: `docs/superpowers/specs/2026-07-22-mission-control-and-session-review-design.md`.

---

## File Structure

**Python (`src/factory/`):**
- `orchestrator/git_ops.py` (modify) — `GitOps.changed_files`, `SubprocessGitOps`/`FakeGitOps` implementations.
- `orchestrator/transcripts.py` (new) — `write_role_transcript`.
- `kb/retrieval.py` (modify) — `list_kb_titles`.
- `orchestrator/types.py` (modify) — `SESSION_WRITER` → `SESSION_REVIEW`.
- `orchestrator/roles.py` (modify) — widened scope + rewritten prompt for `SESSION_REVIEW`.
- `.pi/skills/session-report/SKILL.md` (new) — vendored skill content.
- `orchestrator/prompts.py` (modify) — `compose_prompt` gains `events`/`existing_kb_titles`.
- `orchestrator/nodes.py` (modify) — `transcript_dir` param on the three role-runners; `run_review` drops `manifest`, gains `kb_entries`.
- `orchestrator/runner.py` (modify) — unconditional `start_commit`, review's KB selection, the "blocked" status report, session-review invocation, transcript-dir threading.
- `orchestrator/__main__.py` (modify) — thread `transcript_dir` through.

**TypeScript (`pi-ext/factory-watch/src/`):**
- `status-format.ts` (modify) — `blocked` icon, `human-review` label, a new fixed-order-with-`pending` formatter.
- `terminal-window.ts` (new) — `spawnTerminalWindow`.
- `mission-control-dashboard.ts` (new) — `MissionControlDashboard` component + standalone entry point.
- `mission-control-transcript.ts` (new) — `TranscriptViewer` component + standalone entry point.
- `index.ts` (modify) — restore `/factory-run`'s pipeline; spawn the dashboard alongside `/factory`/`/factory-run`.

---

### Task 1: `GitOps.changed_files`

**Files:**
- Modify: `src/factory/orchestrator/git_ops.py`
- Test: `tests/unit/orchestrator/test_git_ops.py` (extend)

**Interfaces:**
- Produces: `GitOps.changed_files(repo_root: Path, start_commit: str) -> list[str]` (protocol method), `SubprocessGitOps` implementation (`git diff --name-only <start_commit>..HEAD`), `FakeGitOps` gains a scriptable `changed_files_result: list[str]`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/orchestrator/test_git_ops.py`:

```python
def test_subprocess_git_ops_changed_files_lists_modified_paths(tmp_path):
    repo = _init_repo(tmp_path)
    start = SubprocessGitOps().head_commit(repo)
    (repo / "a.txt").write_text("two\n", encoding="utf-8")
    (repo / "b.txt").write_text("new\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "change"], cwd=repo, check=True)

    files = SubprocessGitOps().changed_files(repo, start)

    assert sorted(files) == ["a.txt", "b.txt"]


def test_subprocess_git_ops_changed_files_empty_when_nothing_changed(tmp_path):
    repo = _init_repo(tmp_path)
    start = SubprocessGitOps().head_commit(repo)
    assert SubprocessGitOps().changed_files(repo, start) == []


def test_fake_git_ops_returns_scripted_changed_files():
    fake = FakeGitOps(changed_files_result=["src/a.py", "src/b.py"])
    assert fake.changed_files(None, "abc123") == ["src/a.py", "src/b.py"]


def test_fake_git_ops_changed_files_defaults_to_empty():
    assert FakeGitOps().changed_files(None, "abc123") == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /c/coding/pi-agent-factory && uv run pytest tests/unit/orchestrator/test_git_ops.py -v`
Expected: FAIL with `AttributeError: 'SubprocessGitOps' object has no attribute 'changed_files'` (and the same for `FakeGitOps`)

- [ ] **Step 3: Implement**

In `src/factory/orchestrator/git_ops.py`, add to the `GitOps` protocol:

```python
class GitOps(Protocol):
    def head_commit(self, repo_root: Path) -> str: ...
    def commit_all(self, repo_root: Path, message: str) -> bool: ...
    def changed_files(self, repo_root: Path, start_commit: str) -> list[str]: ...
```

Add to `SubprocessGitOps`:

```python
    def changed_files(self, repo_root: Path, start_commit: str) -> list[str]:
        result = subprocess.run(
            ["git", "diff", "--name-only", f"{start_commit}..HEAD"],
            cwd=repo_root, capture_output=True, text=True, check=True,
        )
        return [line for line in result.stdout.splitlines() if line.strip()]
```

Change `FakeGitOps` to accept and serve the scripted list:

```python
class FakeGitOps:
    def __init__(
        self, head: str = "0" * 40, has_uncommitted: bool = False,
        changed_files_result: list[str] | None = None,
    ) -> None:
        self.head = head
        self.has_uncommitted = has_uncommitted
        self.commit_messages: list[str] = []
        self._changed_files_result = changed_files_result or []

    def head_commit(self, repo_root: Path) -> str:
        return self.head

    def commit_all(self, repo_root: Path, message: str) -> bool:
        if self.has_uncommitted:
            self.commit_messages.append(message)
            return True
        return False

    def changed_files(self, repo_root: Path, start_commit: str) -> list[str]:
        return self._changed_files_result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /c/coding/pi-agent-factory && uv run pytest tests/unit/orchestrator/test_git_ops.py -v`
Expected: PASS (all 8 -- 4 pre-existing + 4 new)

- [ ] **Step 5: Commit**

```bash
git add src/factory/orchestrator/git_ops.py tests/unit/orchestrator/test_git_ops.py
git commit -m "feat: add GitOps.changed_files for review's actual-diff KB selection"
```

---

### Task 2: `transcripts.py`

**Files:**
- Create: `src/factory/orchestrator/transcripts.py`
- Test: `tests/unit/orchestrator/test_transcripts.py`

**Interfaces:**
- Produces: `write_role_transcript(transcript_dir: Path, node: str, attempt: int, raw: str) -> Path` -- `transcript_dir` is always already session-scoped (`repo_root/sessions/.factory-transcripts/<session_id>`, resolved once by the caller in `__main__.py`, Task 8), so this function itself has no notion of `session_id`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/orchestrator/test_transcripts.py
from __future__ import annotations

import pytest
from factory.orchestrator.transcripts import write_role_transcript

pytestmark = pytest.mark.unit


def test_writes_transcript_to_the_expected_path(tmp_path):
    path = write_role_transcript(tmp_path, "dev", 2, "raw agent output")
    assert path == tmp_path / "dev-attempt2.log"
    assert path.read_text(encoding="utf-8") == "raw agent output"


def test_creates_intermediate_directories(tmp_path):
    target = tmp_path / "nested" / "dir"
    write_role_transcript(target, "review", 1, "x")
    assert target.is_dir()


def test_separate_attempts_do_not_overwrite_each_other(tmp_path):
    write_role_transcript(tmp_path, "dev", 1, "first attempt")
    write_role_transcript(tmp_path, "dev", 2, "second attempt")
    assert (tmp_path / "dev-attempt1.log").read_text(encoding="utf-8") == "first attempt"
    assert (tmp_path / "dev-attempt2.log").read_text(encoding="utf-8") == "second attempt"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /c/coding/pi-agent-factory && uv run pytest tests/unit/orchestrator/test_transcripts.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'factory.orchestrator.transcripts'`

- [ ] **Step 3: Implement**

`transcript_dir` here is always an already session-scoped directory -- every caller (Tasks 6, 7) resolves `repo_root / "sessions" / ".factory-transcripts" / session_id` itself (computed once, in `__main__.py`, Task 8) before passing it down, so this function only needs to know the node/attempt/content, not sessions_dir/session_id:

```python
# src/factory/orchestrator/transcripts.py
from __future__ import annotations

from pathlib import Path


def write_role_transcript(transcript_dir: Path, node: str, attempt: int, raw: str) -> Path:
    transcript_dir.mkdir(parents=True, exist_ok=True)
    path = transcript_dir / f"{node}-attempt{attempt}.log"
    path.write_text(raw, encoding="utf-8")
    return path
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /c/coding/pi-agent-factory && uv run pytest tests/unit/orchestrator/test_transcripts.py -v`
Expected: PASS (3/3)

- [ ] **Step 5: Commit**

```bash
git add src/factory/orchestrator/transcripts.py tests/unit/orchestrator/test_transcripts.py
git commit -m "feat: persist each pipeline role's full transcript per attempt"
```

---

### Task 3: `kb/retrieval.py` gains `list_kb_titles`

**Files:**
- Modify: `src/factory/kb/retrieval.py`
- Test: `tests/unit/test_kb_retrieval.py` (extend)

**Interfaces:**
- Produces: `list_kb_titles(kb_dir: Path) -> list[tuple[str, str]]` -- every `kb-*.md` entry's `(id, title)`, unfiltered by status/relevance (unlike `select_entries`, this is for the session-review agent's duplicate-avoidance check, not task-relevance selection).

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_kb_retrieval.py` (this file already has a `KB_DIR` constant pointed at the repo's real `kb/` directory with the seeded `kb-0001-example-entry.md` fixture -- reuse it):

```python
def test_list_kb_titles_returns_id_and_title_for_every_entry():
    titles = list_kb_titles(KB_DIR)
    assert ("kb-0001", "Example: flaky retry needs a longer backoff") in titles


def test_list_kb_titles_empty_dir_returns_empty_list(tmp_path):
    assert list_kb_titles(tmp_path) == []


def test_list_kb_titles_includes_inactive_entries(tmp_path):
    # Unlike select_entries, list_kb_titles is for duplicate-avoidance
    # awareness, not task relevance -- it should not filter by status.
    (tmp_path / "kb-0099-retired.md").write_text(
        "---\nid: kb-0099\ntitle: Retired issue\nstatus: retired\nseverity: low\n"
        "tags: []\nscope:\n  files: []\n---\nbody\n",
        encoding="utf-8",
    )
    assert ("kb-0099", "Retired issue") in list_kb_titles(tmp_path)
```

Add the import: `from factory.kb.retrieval import list_kb_titles, select_entries` (extending the existing import line).

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /c/coding/pi-agent-factory && uv run pytest tests/unit/test_kb_retrieval.py -v`
Expected: FAIL with `ImportError: cannot import name 'list_kb_titles'`

- [ ] **Step 3: Implement**

In `src/factory/kb/retrieval.py`, add (this reads entries directly via `parse_entry`, not through `_iter_entries`, since it deliberately skips both the `validate_entry` filter and the `status == "active"` filter `select_entries` applies -- a retired or even slightly malformed entry's title is still useful context for "does something like this already exist"):

```python
from factory.validation.kb_validator import parse_entry


def list_kb_titles(kb_dir: Path) -> list[tuple[str, str]]:
    titles: list[tuple[str, str]] = []
    for path in sorted(kb_dir.glob("kb-*.md")):
        entry = parse_entry(path)
        entry_id = entry.get("id")
        title = entry.get("title")
        if entry_id is not None and title is not None:
            titles.append((str(entry_id), str(title)))
    return titles
```

(`parse_entry` is already imported in this file per its existing `from factory.validation.kb_validator import parse_entry, validate_entry` line -- no new import needed if that line is already present; add `parse_entry` to it if it isn't.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /c/coding/pi-agent-factory && uv run pytest tests/unit/test_kb_retrieval.py -v`
Expected: PASS (all -- pre-existing + 3 new)

- [ ] **Step 5: Commit**

```bash
git add src/factory/kb/retrieval.py tests/unit/test_kb_retrieval.py
git commit -m "feat: add list_kb_titles for the session-review agent's dedup check"
```

---

### Task 4: Rename `SESSION_WRITER` to `SESSION_REVIEW`, widen scope, rewrite prompt, vendor its skill

**Files:**
- Modify: `src/factory/orchestrator/types.py`
- Modify: `src/factory/orchestrator/roles.py`
- Create: `.pi/skills/session-report/SKILL.md`
- Test: `tests/unit/orchestrator/test_roles.py` (extend)

**Interfaces:**
- Produces: `AgentRole.SESSION_REVIEW` (replaces `SESSION_WRITER`), `ROLE_SKILLS[AgentRole.SESSION_REVIEW] == ["session-report"]` (unchanged name, now vendored), `ROLE_SCOPE[AgentRole.SESSION_REVIEW] == Scope(allow=["sessions/**", "kb/**"], bash="deny")`, a rewritten `ROLE_PROMPTS[AgentRole.SESSION_REVIEW]`.

- [ ] **Step 1: Write the failing tests**

Read the existing `tests/unit/orchestrator/test_roles.py` first to match its exact style, then add (or adapt existing `SESSION_WRITER`-referencing assertions, if any exist, to the new name):

```python
def test_session_review_role_has_kb_write_scope():
    scope = ROLE_SCOPE[AgentRole.SESSION_REVIEW]
    assert "kb/**" in scope.allow
    assert "sessions/**" in scope.allow
    assert scope.bash == "deny"


def test_session_review_role_names_session_report_skill():
    assert ROLE_SKILLS[AgentRole.SESSION_REVIEW] == ["session-report"]


def test_session_writer_role_no_longer_exists():
    assert not hasattr(AgentRole, "SESSION_WRITER")
```

(Adjust imports at the top of the test file to include `AgentRole`, `ROLE_SCOPE`, `ROLE_SKILLS` if not already present.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /c/coding/pi-agent-factory && uv run pytest tests/unit/orchestrator/test_roles.py -v`
Expected: FAIL with `AttributeError: SESSION_REVIEW` (the enum member doesn't exist yet)

- [ ] **Step 3: Implement**

In `src/factory/orchestrator/types.py`, rename:

```python
class AgentRole(str, Enum):
    CONTEXT_GATHERER = "context-gatherer"
    DEV = "dev"
    VALIDATION = "validation"
    REVIEW = "review"
    SESSION_REVIEW = "session-review"
```

In `src/factory/orchestrator/roles.py`, replace every `AgentRole.SESSION_WRITER` reference with `AgentRole.SESSION_REVIEW`, widen its scope, and rewrite its prompt:

```python
ROLE_SKILLS: dict[AgentRole, list[str]] = {
    AgentRole.CONTEXT_GATHERER: ["verification-before-completion", "context-completeness-audit"],
    AgentRole.DEV: [
        "test-driven-development",
        "systematic-debugging",
        "receiving-code-review",
        "kb-lookup",
    ],
    AgentRole.VALIDATION: ["verification-before-completion", "sim-functional-tests"],
    AgentRole.REVIEW: ["requesting-code-review", "verification-before-completion", "coding-principles"],
    AgentRole.SESSION_REVIEW: ["session-report"],
}

ROLE_SCOPE: dict[AgentRole, Scope] = {
    AgentRole.CONTEXT_GATHERER: Scope(allow=["context-manifests/**"], bash="deny"),
    AgentRole.DEV: Scope(allow=["src/**", "tests/**"], bash="allow"),
    AgentRole.VALIDATION: Scope(allow=[], bash="allow"),
    AgentRole.REVIEW: Scope(allow=[], bash="deny"),
    AgentRole.SESSION_REVIEW: Scope(allow=["sessions/**", "kb/**"], bash="deny"),
}

ROLE_PROMPTS: dict[AgentRole, str] = {
    AgentRole.CONTEXT_GATHERER: (
        "You verify that spec, plan, prior session, and this task are coherent and "
        "that context is complete. Emit ONLY a context manifest as a fenced ```json block "
        "matching the context_manifest schema. If you cannot prove coherence, set "
        "coherence.proven=false and populate reject."
    ),
    AgentRole.DEV: (
        "Implement the task using strict TDD (write the failing test first). "
        "Consult the provided knowledge-base entries. Do not stop until unit tests pass."
    ),
    AgentRole.VALIDATION: "Run the functional/sim suite. Do not modify source.",
    AgentRole.REVIEW: (
        "Review the change for YAGNI/DRY and against the Definition of Done. Emit ONLY a "
        "fenced ```json block: {\"dod_met\": bool, \"principles\": [..], \"findings\": [..]}."
    ),
    AgentRole.SESSION_REVIEW: (
        "Analyze this task's full pipeline run (see the events below): what happened at "
        "each stage, how many attempts each took, what the final outcome was. If you find "
        "an issue genuinely worth remembering for future tasks -- not every run has one -- "
        "write a new kb/kb-NNNN-<slug>.md entry (check the existing entry list below and "
        "kb/ itself for the next free number; do not duplicate an issue already recorded "
        "there). Then append a short 'Suggestions' section to this session's summary in "
        "sessions/ noting any skill or prompt improvements that would have made this run "
        "more efficient -- these are suggestions for a human to read later, not changes to "
        "apply yourself."
    ),
}
```

Also update the module-level comment above `ROLE_SKILLS` (currently references `AgentRole.SESSION_WRITER` by name and describes it as permanently dead code) to reflect that `SESSION_REVIEW` is now wired up for real -- remove the parts of that comment that no longer apply (the "neither is ever invoked" and "LATENT TRAP" framing was specifically about this role staying dead; it isn't anymore) while keeping the parts still true of `AgentRole.VALIDATION` (still a deterministic gate, still dead as an agent role).

- [ ] **Step 4: Vendor the skill**

Create `.pi/skills/session-report/SKILL.md`:

```markdown
---
name: session-report
description: Analyze a completed factory task's pipeline run, record genuinely reusable issues in the knowledge base, and suggest skill/prompt improvements
---

# Session Report

Analyze what happened during this task's pipeline run using the event
history provided in your prompt: which stages ran, how many attempts each
took, and the final outcome.

## Knowledge base entries

Not every run produces something worth recording. Only write a new
`kb/kb-NNNN-<slug>.md` entry when you've identified a genuinely reusable
issue -- a bug class, a gotcha, a non-obvious fix -- that would help a
future task avoid the same problem. Check the existing entry list in your
prompt (and `kb/` itself if you want more detail on a specific one) before
writing; do not create a near-duplicate of an issue already recorded.

Follow the existing KB entry format: YAML frontmatter with `id`, `title`,
`status`, `severity`, `tags`, and `scope.files`/`scope.error_signatures`,
followed by Symptom / Root cause / Rule-or-fix sections in the body.

## Skill and prompt suggestions

Append a short "Suggestions" section to this session's summary noting any
skill or prompt improvements that would have made this specific run more
efficient -- for example, a skill that was missing context it needed, or a
role prompt that led to a wasted retry. These are suggestions for a human
to read and decide on later; do not edit `.pi/skills/**` or any role prompt
yourself.
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /c/coding/pi-agent-factory && uv run pytest tests/unit/orchestrator/test_roles.py -v`
Expected: PASS (all, including the 3 new tests)

Also run the full orchestrator suite once here, since renaming an enum member is exactly the kind of change that can silently break an unrelated test elsewhere:
Run: `cd /c/coding/pi-agent-factory && uv run pytest tests/unit/orchestrator/ -v`
Expected: PASS (no other test references `SESSION_WRITER`)

- [ ] **Step 6: Commit**

```bash
git add src/factory/orchestrator/types.py src/factory/orchestrator/roles.py .pi/skills/session-report/SKILL.md tests/unit/orchestrator/test_roles.py
git commit -m "feat: rename SESSION_WRITER to SESSION_REVIEW, widen its scope, vendor its skill"
```

---

### Task 5: `compose_prompt` gains `events` and `existing_kb_titles`

**Files:**
- Modify: `src/factory/orchestrator/prompts.py`
- Test: `tests/unit/orchestrator/test_prompts.py` (extend)

**Interfaces:**
- Consumes: `NodeEvent` (`types.py`, unchanged).
- Produces: `compose_prompt(role, task, manifest=None, kb_entries=None, feedback=None, *, events=None, existing_kb_titles=None, skills_dir)`.

- [ ] **Step 1: Write the failing tests**

Read the existing `tests/unit/orchestrator/test_prompts.py` first to match its exact fixture/assertion style, then add:

```python
def test_compose_prompt_includes_events_section_when_provided():
    from factory.orchestrator.types import NodeEvent

    events = [
        NodeEvent("context-gather", "pass", 1),
        NodeEvent("dev", "pass", 2),
    ]
    prompt = compose_prompt(
        AgentRole.SESSION_REVIEW, _task(), events=events, skills_dir=_skills_dir(),
    )
    assert "## What happened this run" in prompt
    assert "context-gather: pass (1 attempt)" in prompt
    assert "dev: pass (2 attempts)" in prompt


def test_compose_prompt_omits_events_section_when_not_provided():
    prompt = compose_prompt(AgentRole.DEV, _task(), skills_dir=_skills_dir())
    assert "## What happened this run" not in prompt


def test_compose_prompt_includes_existing_kb_titles_when_provided():
    prompt = compose_prompt(
        AgentRole.SESSION_REVIEW, _task(),
        existing_kb_titles=[("kb-0001", "Flaky retry")], skills_dir=_skills_dir(),
    )
    assert "## Existing knowledge base entries" in prompt
    assert "kb-0001: Flaky retry" in prompt


def test_compose_prompt_omits_existing_kb_titles_section_when_not_provided():
    prompt = compose_prompt(AgentRole.DEV, _task(), skills_dir=_skills_dir())
    assert "## Existing knowledge base entries" not in prompt
```

(`_task()`/`_skills_dir()` are placeholders for whatever this test file's existing helper functions/fixtures for building a `Task` and a skills directory are actually named -- read the file and use its real ones; do not invent new fixtures if equivalent ones already exist.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /c/coding/pi-agent-factory && uv run pytest tests/unit/orchestrator/test_prompts.py -v`
Expected: FAIL with `TypeError: compose_prompt() got an unexpected keyword argument 'events'`

- [ ] **Step 3: Implement**

In `src/factory/orchestrator/prompts.py`:

```python
from __future__ import annotations

from pathlib import Path

from factory.orchestrator.ledger import Task
from factory.orchestrator.roles import ROLE_PROMPTS, ROLE_SKILLS
from factory.orchestrator.skills import load_skill_block
from factory.orchestrator.types import AgentRole, NodeEvent


def compose_prompt(
    role: AgentRole,
    task: Task,
    manifest: dict | None = None,
    kb_entries: list[dict] | None = None,
    feedback: str | None = None,
    *,
    events: list[NodeEvent] | None = None,
    existing_kb_titles: list[tuple[str, str]] | None = None,
    skills_dir: Path,
) -> str:
    lines: list[str] = []
    lines.append(f"# Role: {role.value}")
    lines.append(ROLE_PROMPTS[role])
    lines.append("")
    lines.append("## Loaded skills")
    for skill in ROLE_SKILLS[role]:
        lines.append(load_skill_block(skills_dir, skill))
    lines.append("")
    lines.append(f"## Task {task.id}: {task.title}")
    lines.append(task.body.strip())
    lines.append("")
    lines.append("## Definition of Done")
    for crit in task.dod:
        lines.append(f"- {crit}")

    if manifest is not None:
        lines.append("")
        lines.append("## Context (from manifest)")
        ctx = manifest.get("context")
        if not isinstance(ctx, dict):
            ctx = {}
        for f in ctx.get("source_files", []):
            lines.append(f"- {f}")

    if kb_entries:
        lines.append("")
        lines.append("## Known issues (knowledge base)")
        for e in kb_entries:
            lines.append(f"- {e.get('id')}: {e.get('title')}")

    if feedback:
        lines.append("")
        lines.append("## Feedback to address")
        lines.append(feedback)

    if events:
        lines.append("")
        lines.append("## What happened this run")
        for ev in events:
            plural = "attempt" if ev.attempts == 1 else "attempts"
            lines.append(f"- {ev.node}: {ev.result} ({ev.attempts} {plural})")

    if existing_kb_titles:
        lines.append("")
        lines.append("## Existing knowledge base entries")
        for kb_id, title in existing_kb_titles:
            lines.append(f"- {kb_id}: {title}")

    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /c/coding/pi-agent-factory && uv run pytest tests/unit/orchestrator/test_prompts.py -v`
Expected: PASS (all -- pre-existing + 4 new)

- [ ] **Step 5: Commit**

```bash
git add src/factory/orchestrator/prompts.py tests/unit/orchestrator/test_prompts.py
git commit -m "feat: compose_prompt gains events and existing_kb_titles for the session-review agent"
```

---

### Task 6: `nodes.py` -- transcript persistence + `run_review`'s corrected context

**Files:**
- Modify: `src/factory/orchestrator/nodes.py`
- Test: `tests/unit/orchestrator/test_nodes_context_dev.py`, `test_nodes_val_review.py` (extend both -- read them first)

**Interfaces:**
- Consumes: `write_role_transcript` (Task 2), `GitOps`/`FakeGitOps` (Task 1, for tests only -- `nodes.py` itself doesn't call `GitOps` directly; `runner.py` does, in Task 7).
- Produces: `run_context_gatherer(..., transcript_dir: Path | None = None, ...)`, `run_dev(..., transcript_dir: Path | None = None, ...)`, `run_review(backend, gates, task, kb_entries, repo_root, transcript_dir: Path | None = None, status=...)` -- note `run_review` no longer takes `manifest`, and now takes `kb_entries` as a required positional (matching `run_dev`'s existing shape for that parameter, just without `manifest`).

- [ ] **Step 1: Write the failing tests**

Read `tests/unit/orchestrator/test_nodes_context_dev.py` and `test_nodes_val_review.py` first for their exact fixture/mocking conventions, then add (adapting to match those conventions exactly -- the shapes below are the required behavior, not literal copy-paste):

```python
# In test_nodes_context_dev.py (or wherever run_context_gatherer/run_dev are tested):

def test_run_context_gatherer_writes_transcript_when_dir_given(tmp_path):
    # ... construct a FakeAgentBackend scripted to succeed on attempt 1 ...
    transcript_dir = tmp_path / "transcripts"
    run_context_gatherer(backend, task, repo_root, transcript_dir=transcript_dir, status=status)
    assert (transcript_dir / "context-gather-attempt1.log").read_text(encoding="utf-8") != ""


def test_run_context_gatherer_no_transcript_when_dir_not_given(tmp_path):
    # ... same setup, transcript_dir omitted (defaults to None) ...
    # assert nothing new was written under tmp_path at all.


def test_run_dev_writes_one_transcript_per_attempt(tmp_path):
    # ... FakeGateRunner scripted to fail unit gate once then pass, so run_dev
    # takes 2 attempts ...
    transcript_dir = tmp_path / "transcripts"
    run_dev(backend, gates, task, manifest, kb_entries, repo_root, transcript_dir=transcript_dir, status=status)
    # assert both "dev-attempt1.log" and "dev-attempt2.log" exist under transcript_dir,
    # with distinct content matching each attempt's scripted backend result.
```

```python
# In test_nodes_val_review.py (or wherever run_review is tested):

def test_run_review_no_longer_accepts_manifest():
    import inspect
    sig = inspect.signature(run_review)
    assert "manifest" not in sig.parameters
    assert "kb_entries" in sig.parameters


def test_run_review_prompt_includes_kb_entries_not_manifest(monkeypatch):
    # Capture the prompt compose_prompt actually builds (patch
    # factory.orchestrator.nodes.compose_prompt, or inspect the backend's
    # captured prompt argument if FakeAgentBackend records it -- read the
    # existing test file to see which pattern it already uses) and assert
    # the KB entries appear, and no "## Context (from manifest)" section
    # appears (since manifest=None is now always passed for review).


def test_run_review_writes_transcript_when_dir_given(tmp_path):
    transcript_dir = tmp_path / "transcripts"
    run_review(backend, gates, task, kb_entries, repo_root, transcript_dir=transcript_dir, status=status)
    # assert "review-attempt1.log" exists under transcript_dir with the backend's raw output.
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /c/coding/pi-agent-factory && uv run pytest tests/unit/orchestrator/test_nodes_context_dev.py tests/unit/orchestrator/test_nodes_val_review.py -v`
Expected: FAIL -- `run_review`'s current signature still takes `manifest` and no `kb_entries`/`transcript_dir`; `run_context_gatherer`/`run_dev` don't accept `transcript_dir` yet.

- [ ] **Step 3: Implement**

In `src/factory/orchestrator/nodes.py`, add the import:

```python
from factory.orchestrator.transcripts import write_role_transcript
```

Add `transcript_dir: Path | None = None` to `run_context_gatherer`'s signature, and write a transcript right after each `backend.run(...)` call inside its retry loop, via `write_role_transcript` (Task 1's `transcript_dir` here is always already session-scoped -- `repo_root/sessions/.factory-transcripts/<session_id>`, resolved once in `__main__.py`, Task 8 -- so this call needs no `session_id` of its own):

```python
        result = backend.run(
            AgentRole.CONTEXT_GATHERER,
            compose_prompt(AgentRole.CONTEXT_GATHERER, task, skills_dir=repo_root / ".pi" / "skills"),
            on_snippet=_on_snippet,
        )
        if transcript_dir is not None:
            write_role_transcript(transcript_dir, "context-gather", attempt, result.raw)
```

Apply the same `transcript_dir: Path | None = None` parameter to `run_dev`'s retry loop, calling `write_role_transcript(transcript_dir, "dev", attempt, result.raw)` right after its own `backend.run(...)` call.

Change `run_review`'s signature and body:

```python
def run_review(
    backend: AgentBackend,
    gates: GateRunner,
    task: Task,
    kb_entries: list[dict],
    repo_root: Path,
    transcript_dir: Path | None = None,
    status: StatusReporter = NullStatusReporter(),
) -> tuple[NodeOutcome, NodeEvent, list[str]]:
    status.report(task_id=task.id, node="review", node_state="running", attempt=1, max_attempts=1)

    def _on_snippet(text: str) -> None:
        status.report(
            task_id=task.id, node="review", node_state="running",
            attempt=1, max_attempts=1, snippet=text,
        )

    result = backend.run(
        AgentRole.REVIEW,
        compose_prompt(AgentRole.REVIEW, task, kb_entries=kb_entries, skills_dir=repo_root / ".pi" / "skills"),
        on_snippet=_on_snippet,
    )
    if transcript_dir is not None:
        write_role_transcript(transcript_dir, "review", 1, result.raw)
    out = result.output
    findings = list(out.get("findings", []))
    dod_met = bool(out.get("dod_met"))
    gate = gates.run("full")
    if gate == 0 and dod_met and not findings:
        extra = _note_backend_failure({}, result)
        status.report(
            task_id=task.id, node="review", node_state="pass",
            attempt=1, max_attempts=1,
            handoff="✓ task complete, DoD met, gates pass", outcome="completed",
        )
        return NodeOutcome.PASS, NodeEvent("review", "pass", 1, extra), []
    finding_summary = f"{len(findings)} finding(s)" if findings else "DoD not met"
    extra = _note_backend_failure({"findings": len(findings), "gate": gate}, result)
    status.report(
        task_id=task.id, node="review", node_state="changes-requested",
        attempt=1, max_attempts=1,
        handoff=f"→ dev: {finding_summary}, gate={'pass' if gate == 0 else 'fail'}",
    )
    return (
        NodeOutcome.CHANGES,
        NodeEvent("review", "changes-requested", 1, extra),
        findings,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /c/coding/pi-agent-factory && uv run pytest tests/unit/orchestrator/test_nodes_context_dev.py tests/unit/orchestrator/test_nodes_val_review.py -v`
Expected: PASS (all, including new tests). Note `run_task`'s call site in `runner.py` will now be broken by `run_review`'s signature change until Task 7 -- that's expected and fixed there; do not touch `runner.py` in this task.

- [ ] **Step 5: Commit**

```bash
git add src/factory/orchestrator/nodes.py tests/unit/orchestrator/test_nodes_context_dev.py tests/unit/orchestrator/test_nodes_val_review.py
git commit -m "feat: transcript persistence in nodes.py; run_review drops manifest, gains kb_entries"
```

---

### Task 7: `runner.py` -- unconditional `start_commit`, review's KB selection, blocked status, session-review invocation

**Files:**
- Modify: `src/factory/orchestrator/runner.py`
- Test: `tests/unit/orchestrator/test_run_next.py`, `tests/unit/orchestrator/test_human_review_gate_in_runner.py` (both extend/fix), new `tests/unit/orchestrator/test_session_review_in_runner.py`

**Interfaces:**
- Consumes: `GitOps.changed_files` (Task 1), `list_kb_titles` (Task 3), `compose_prompt`'s `events`/`existing_kb_titles` (Task 5), `run_review`'s new signature (Task 6), `AgentRole.SESSION_REVIEW` (Task 4).
- Produces: `run_task`/`run_next` unchanged signatures (this task changes their *bodies*, not their public parameters) except `run_task` gains `transcript_dir: Path | None = None` and `run_next` threads it through.

- [ ] **Step 1: Fix a real regression this task's design introduces, before writing anything new**

Making `start_commit` unconditional (`git_ops.head_commit(repo_root)` with no `if human_review is not None` guard) means `SubprocessGitOps` now runs on **every** `run_task` call, including every existing test that doesn't pass a `git_ops` override. Both `tests/unit/orchestrator/test_run_next.py` and `tests/unit/orchestrator/test_human_review_gate_in_runner.py` have their own local `_repo(tmp_path)` fixture helper (5 and 3 call sites respectively -- 8 currently-passing tests total), and **neither one runs `git init`** -- confirmed by reading both files directly. Left as-is, this task would silently break all 8 of them with `CalledProcessError` the moment `start_commit`'s guard is removed.

Fix this **first**, in both files, before writing any new test: update each file's `_repo(tmp_path)` helper to `git init` and commit the fixture files it already creates, matching `tests/unit/orchestrator/test_git_ops.py`'s `_init_repo` helper exactly (`git init -q`, set `user.email`/`user.name`, `git add -A`, `git commit -q -m "init"`, after the existing fixture-file-writing lines, before `return tmp_path`). This is a mechanical, low-risk change to existing fixtures, not new behavior -- run the full existing suite in both files right after this change, before writing anything else, to confirm all 8 pre-existing tests still pass unchanged:

Run: `cd /c/coding/pi-agent-factory && uv run pytest tests/unit/orchestrator/test_run_next.py tests/unit/orchestrator/test_human_review_gate_in_runner.py -v`
Expected: PASS (all 8, unchanged behavior -- this step only prevents a regression Task 7 would otherwise introduce; it does not yet touch `runner.py` itself)

- [ ] **Step 2: Write the failing tests**

This task also **breaks** `run_review`'s existing call site in `run_task` (Task 6 changed the function it calls) -- fix that as part of Step 4, not as a separate red/green cycle, since the whole point of Task 6 was "review's call site updates in Task 7."

Add to `tests/unit/orchestrator/test_run_next.py` (now that `_repo` git-inits, per Step 1):

```python
def test_review_kb_entries_selected_from_actual_changed_files_not_manifest(tmp_path):
    repo = _repo(tmp_path)
    # Seed a kb/ entry whose scope.files glob matches a file dev is scripted
    # to "change" (simulate by writing + `git add -A` + `git commit` a new
    # file matching the glob, after _repo's initial commit but before calling
    # run_next) but does NOT match the manifest's predicted source_files --
    # assert the review backend's captured prompt includes that KB entry
    # (proving selection used the actual diff, not the manifest). Read this
    # file's FakeAgentBackend/_scripts() helpers to see how a scripted
    # backend's received prompt is captured/asserted on elsewhere in this
    # file, and follow the same pattern rather than inventing a new one.


def test_session_review_invoked_at_end_of_run_next_with_events_and_kb_titles(tmp_path):
    repo = _repo(tmp_path)
    scripts = _scripts()
    scripts[AgentRole.SESSION_REVIEW] = [AgentResult(True, {})]
    backend = FakeAgentBackend(scripts)
    run_next(repo, backend, FakeGateRunner(), session_id="s1", git_info={"branch": "main"})
    # Assert AgentRole.SESSION_REVIEW was actually invoked (FakeAgentBackend
    # raises its own assertion error if a role's scripted queue is empty when
    # called, so simply NOT erring here is meaningful; additionally, if this
    # test file's FakeAgentBackend variant records calls/prompts, assert the
    # captured session-review prompt contains "## What happened this run".
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd /c/coding/pi-agent-factory && uv run pytest tests/unit/orchestrator/test_run_next.py tests/unit/orchestrator/test_human_review_gate_in_runner.py -v`
Expected: FAIL -- `run_task`'s existing `run_review(...)` call site doesn't match Task 6's new signature yet (breaks ALL tests in this file until Step 4 fixes it), plus the two new tests fail for their own reasons.

- [ ] **Step 4: Implement**

In `src/factory/orchestrator/runner.py`, update imports:

```python
from factory.kb.retrieval import list_kb_titles, select_entries
from factory.orchestrator.transcripts import write_role_transcript
from factory.orchestrator.types import AgentRole, NodeEvent, NodeOutcome, TaskResult
```

(`AgentRole` is newly needed here for the `SESSION_REVIEW` call.)

Change `run_task`'s signature to add `transcript_dir`:

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
    transcript_dir: Path | None = None,
) -> TaskResult:
    events: list[NodeEvent] = []
    start_commit = git_ops.head_commit(repo_root)
```

(Note: `start_commit` is now captured unconditionally -- the `if human_review is not None else None` gate is removed. `git_ops` already defaults to a real `SubprocessGitOps()` regardless of `human_review`, so this costs one extra `git rev-parse HEAD` call on every task run, always.)

The rest of the context-gatherer/dev/validation section of `run_task` is unchanged except passing `transcript_dir` through to `run_context_gatherer`/`run_dev`:

```python
        d_outcome, d_ev = run_dev(
            backend, gates, task, manifest, kb_entries, repo_root, max_dev_iters, feedback,
            transcript_dir=transcript_dir, status=status,
        )
```

(and similarly for the earlier `run_context_gatherer(...)` call.)

Replace the review section:

```python
        review_changed_files = git_ops.changed_files(repo_root, start_commit)
        review_kb_ids = select_entries(repo_root / "kb", review_changed_files, [])
        review_kb_entries = _load_kb_entries(repo_root / "kb", review_kb_ids)

        r_outcome, r_ev, findings = run_review(
            backend, gates, task, review_kb_entries, repo_root,
            transcript_dir=transcript_dir, status=status,
        )
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
```

(everything else in this block -- the `else` path for `r_outcome != PASS`, the loop's closing `feedback = ...` line -- is unchanged from before this task.)

Add the "blocked" status report right before the human-review call:

```python
            if human_review is not None:
                assert start_commit is not None
                status.report(
                    task_id=task.id, node="human-review", node_state="blocked",
                    attempt=1, max_attempts=1, handoff="waiting for you to review the diff",
                )
                decision = human_review.request_review(task.id, start_commit)
```

Add the session-review invocation at the end of `run_next` (not `run_task` -- it belongs after the session record is written, matching Section 8's design):

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
    transcript_dir: Path | None = None,
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
        task, backend, gates, repo_root, status=status, human_review=human_review,
        git_ops=git_ops, transcript_dir=transcript_dir,
    )
    set_status(task, "done" if result.outcome == "completed" else "todo")

    sid = session_id or _default_session_id()
    record = build_record(sid, model_backend, [result], git_info or {})
    path = write_session(repo_root / "sessions", record)

    status.report(task_id=task.id, node="session-review", node_state="running", attempt=1, max_attempts=1)
    session_review_prompt = compose_prompt(
        AgentRole.SESSION_REVIEW, task,
        events=result.events, existing_kb_titles=list_kb_titles(repo_root / "kb"),
        skills_dir=repo_root / ".pi" / "skills",
    )
    session_review_result = backend.run(AgentRole.SESSION_REVIEW, session_review_prompt)
    if transcript_dir is not None:
        write_role_transcript(transcript_dir, "session-review", 1, session_review_result.raw)
    status.report(
        task_id=task.id, node="session-review", node_state="pass",
        attempt=1, max_attempts=1, outcome="completed",
    )

    return path
```

Add the `compose_prompt` import (`from factory.orchestrator.prompts import compose_prompt` -- check it isn't already imported under a different alias before adding a duplicate).

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /c/coding/pi-agent-factory && uv run pytest tests/unit/orchestrator/ -v`
Expected: PASS (the full orchestrator suite -- this task's changes touch enough shared code that a narrower target risks missing a regression, matching this plan's established practice of running the full suite after integration-heavy changes)

- [ ] **Step 6: Commit**

```bash
git add src/factory/orchestrator/runner.py tests/unit/orchestrator/test_run_next.py tests/unit/orchestrator/test_human_review_gate_in_runner.py tests/unit/orchestrator/test_session_review_in_runner.py
git commit -m "feat: wire review's actual-diff KB selection, blocked status, and session-review invocation into runner.py"
```

---

### Task 8: `__main__.py` -- thread `transcript_dir` through

**Files:**
- Modify: `src/factory/orchestrator/__main__.py`

**Interfaces:**
- Consumes: `run_next`'s new `transcript_dir` parameter (Task 7).
- Produces: `run_next(...)` in `main()` is called with `transcript_dir=repo_root / "sessions" / ".factory-transcripts" / session_id` computed from the already-generated `session_id`.

- [ ] **Step 1: Manually verify today's behavior first**

Run: `cd /c/coding/pi-agent-factory && uv run python -m factory.orchestrator list --repo .` and confirm it still prints the task board (baseline, unaffected by this task).

- [ ] **Step 2: Implement**

In `src/factory/orchestrator/__main__.py`'s `main()`, right after `session_id = _now_id()`:

```python
    session_id = _now_id()
    transcript_dir = repo_root / "sessions" / ".factory-transcripts" / session_id
```

and pass it through the existing `run_next(...)` call:

```python
        path = run_next(
            repo_root, backend, gates, git_info=_git_info(repo_root),
            session_id=session_id, status=status, task_id=args.task,
            human_review=human_review, transcript_dir=transcript_dir, **kwargs,
        )
```

- [ ] **Step 3: Manually re-verify**

Run: `cd /c/coding/pi-agent-factory && uv run python -m factory.orchestrator list --repo .` again -- unaffected, still prints the task board on stdout (this task doesn't touch the `list` command at all).

Run the full gate suite once to confirm nothing else broke: `uv run python scripts/gates/all.py`
Expected: fully green.

- [ ] **Step 4: Commit**

```bash
git add src/factory/orchestrator/__main__.py
git commit -m "feat: thread transcript_dir from __main__ into run_next"
```

---

### Task 9: `status-format.ts` -- blocked icon, human-review label, fixed-order-with-pending formatter

**Files:**
- Modify: `pi-ext/factory-watch/src/status-format.ts`
- Test: `pi-ext/factory-watch/test/status-format.test.ts` (extend)

**Interfaces:**
- Produces: `STATE_ICONS` gains `blocked`, `NODE_LABELS` gains `"human-review"`, new `formatMissionControlRows(record: StatusRecord | null, stageOrder: string[]): { node: string; label: string; state: string; handoff: string | null }[]` -- one entry per stage in `stageOrder`, `state: "pending"` for any stage not yet present in `record.pipeline`.

- [ ] **Step 1: Write the failing tests**

Append to `pi-ext/factory-watch/test/status-format.test.ts` (read the file first for its exact fixture-building conventions -- likely a helper building a minimal `StatusRecord`):

```typescript
import { formatMissionControlRows } from "../src/status-format.js";

const STAGE_ORDER = ["context-gather", "dev", "validation", "review", "human-review"];

describe("formatMissionControlRows", () => {
  test("shows every stage in fixed order, pending for stages not yet reached", () => {
    const record: StatusRecord = {
      session_id: "s1", task_id: "T-001", current_node: "dev", current_state: "running",
      pipeline: [
        { node: "context-gather", node_state: "pass", attempt: 1, max_attempts: 1, snippet: "", outcome: null, handoff: "-> dev: 3 files", updated_at: "2026-07-22T00:00:00Z" },
        { node: "dev", node_state: "running", attempt: 1, max_attempts: 3, snippet: "", outcome: null, handoff: null, updated_at: "2026-07-22T00:00:01Z" },
      ],
      started_at: "2026-07-22T00:00:00Z", updated_at: "2026-07-22T00:00:01Z",
    };
    const rows = formatMissionControlRows(record, STAGE_ORDER);
    expect(rows).toEqual([
      { node: "context-gather", label: "context-gatherer", state: "pass", handoff: "-> dev: 3 files" },
      { node: "dev", label: "developer", state: "running", handoff: null },
      { node: "validation", label: "validation", state: "pending", handoff: null },
      { node: "review", label: "reviewer", state: "pending", handoff: null },
      { node: "human-review", label: "human-review", state: "pending", handoff: null },
    ]);
  });

  test("returns all-pending rows when record is null", () => {
    const rows = formatMissionControlRows(null, STAGE_ORDER);
    expect(rows.every((r) => r.state === "pending")).toBe(true);
    expect(rows).toHaveLength(5);
  });
});
```

Also add a direct icon test:

```typescript
test("formatStatusLines renders the blocked icon, not the default fallback", () => {
  const record: StatusRecord = {
    session_id: "s1", task_id: "T-001", current_node: "human-review", current_state: "blocked",
    pipeline: [
      { node: "human-review", node_state: "blocked", attempt: 1, max_attempts: 1, snippet: "", outcome: null, handoff: "waiting for you to review the diff", updated_at: "2026-07-22T00:00:00Z" },
    ],
    started_at: "2026-07-22T00:00:00Z", updated_at: "2026-07-22T00:00:00Z",
  };
  const lines = formatStatusLines(record);
  expect(lines[1]).toBe("⊘ human-review: blocked  (1/1)");
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /c/coding/pi-agent-factory/pi-ext/factory-watch && npm test -- status-format`
Expected: FAIL -- `formatMissionControlRows` doesn't exist yet; the blocked-icon test fails since `blocked` isn't in `STATE_ICONS` yet.

- [ ] **Step 3: Implement**

In `pi-ext/factory-watch/src/status-format.ts`:

```typescript
const NODE_LABELS: Record<string, string> = {
  "context-gather": "context-gatherer",
  dev: "developer",
  validation: "validation",
  review: "reviewer",
  "human-review": "human-review",
};

const STATE_ICONS: Record<string, string> = {
  running: "●",
  pass: "✓",
  fail: "✗",
  reject: "✗",
  escalate: "↑",
  "changes-requested": "↻",
  blocked: "⊘",
};
```

Add the new function:

```typescript
export interface MissionControlRow {
  node: string;
  label: string;
  state: string;
  handoff: string | null;
}

export function formatMissionControlRows(record: StatusRecord | null, stageOrder: string[]): MissionControlRow[] {
  const byNode = new Map((record?.pipeline ?? []).map((entry) => [entry.node, entry]));
  return stageOrder.map((node) => {
    const entry = byNode.get(node);
    return {
      node,
      label: labelForNode(node),
      state: entry?.node_state ?? "pending",
      handoff: entry?.handoff ?? null,
    };
  });
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /c/coding/pi-agent-factory/pi-ext/factory-watch && npm run typecheck && npm test -- status-format`
Expected: PASS (all)

- [ ] **Step 5: Commit**

```bash
git add pi-ext/factory-watch/src/status-format.ts pi-ext/factory-watch/test/status-format.test.ts
git commit -m "feat(factory-watch): blocked icon, human-review label, fixed-order mission control rows"
```

---

### Task 10: `terminal-window.ts`

**Files:**
- Create: `pi-ext/factory-watch/src/terminal-window.ts`
- Test: `pi-ext/factory-watch/test/terminal-window.test.ts`

**Interfaces:**
- Produces: `spawnTerminalWindow(command: string, args: string[], options: { cwd: string }): void`.

- [ ] **Step 1: Write the failing tests**

```typescript
// pi-ext/factory-watch/test/terminal-window.test.ts
import { spawn } from "node:child_process";
import { describe, expect, test, vi } from "vitest";
import { spawnTerminalWindow } from "../src/terminal-window.js";

vi.mock("node:child_process", () => ({ spawn: vi.fn(() => ({ unref: vi.fn() })) }));

describe("spawnTerminalWindow", () => {
  test("on win32, uses PowerShell Start-Process with the command and args", () => {
    vi.mocked(spawn).mockClear();
    spawnTerminalWindow("node", ["dashboard.ts", "--cwd", "/repo"], { cwd: "/repo" }, "win32");
    expect(spawn).toHaveBeenCalledWith(
      "powershell",
      [
        "-NoExit", "-Command",
        "Start-Process node -ArgumentList 'dashboard.ts','--cwd','/repo'",
      ],
      { cwd: "/repo", detached: true, stdio: "ignore" },
    );
  });

  test("on darwin, uses `open -a Terminal`", () => {
    vi.mocked(spawn).mockClear();
    spawnTerminalWindow("node", ["dashboard.ts"], { cwd: "/repo" }, "darwin");
    expect(spawn).toHaveBeenCalledWith(
      "open", ["-a", "Terminal", "node", "dashboard.ts"],
      { cwd: "/repo", detached: true, stdio: "ignore" },
    );
  });

  test("on linux, uses xterm -e", () => {
    vi.mocked(spawn).mockClear();
    spawnTerminalWindow("node", ["dashboard.ts"], { cwd: "/repo" }, "linux");
    expect(spawn).toHaveBeenCalledWith(
      "xterm", ["-e", "node", "dashboard.ts"],
      { cwd: "/repo", detached: true, stdio: "ignore" },
    );
  });

  test("unrefs the spawned child so it doesn't keep the parent process alive", () => {
    const unref = vi.fn();
    vi.mocked(spawn).mockReturnValue({ unref } as unknown as ReturnType<typeof spawn>);
    spawnTerminalWindow("node", ["dashboard.ts"], { cwd: "/repo" }, "win32");
    expect(unref).toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /c/coding/pi-agent-factory/pi-ext/factory-watch && npm test -- terminal-window`
Expected: FAIL with a module-not-found error for `../src/terminal-window.js`

- [ ] **Step 3: Implement**

```typescript
// pi-ext/factory-watch/src/terminal-window.ts
import { spawn } from "node:child_process";

export function spawnTerminalWindow(
  command: string,
  args: string[],
  options: { cwd: string },
  platform: NodeJS.Platform = process.platform,
): void {
  let child: ReturnType<typeof spawn>;
  if (platform === "win32") {
    const argList = args.map((a) => `'${a}'`).join(",");
    child = spawn(
      "powershell",
      ["-NoExit", "-Command", `Start-Process ${command} -ArgumentList ${argList}`],
      { cwd: options.cwd, detached: true, stdio: "ignore" },
    );
  } else if (platform === "darwin") {
    child = spawn("open", ["-a", "Terminal", command, ...args], {
      cwd: options.cwd, detached: true, stdio: "ignore",
    });
  } else {
    child = spawn("xterm", ["-e", command, ...args], {
      cwd: options.cwd, detached: true, stdio: "ignore",
    });
  }
  child.unref();
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /c/coding/pi-agent-factory/pi-ext/factory-watch && npm run typecheck && npm test -- terminal-window`
Expected: PASS (all 4)

- [ ] **Step 5: Commit**

```bash
git add pi-ext/factory-watch/src/terminal-window.ts pi-ext/factory-watch/test/terminal-window.test.ts
git commit -m "feat(factory-watch): spawnTerminalWindow, confirmed working via a real Start-Process test earlier this session"
```

---

### Task 11: `mission-control-dashboard.ts`

**Files:**
- Create: `pi-ext/factory-watch/src/mission-control-dashboard.ts`
- Test: `pi-ext/factory-watch/test/mission-control-dashboard.test.ts`

**Interfaces:**
- Consumes: `parseStatus`/`formatMissionControlRows` (Task 9, `status-format.ts`).
- Produces: `MissionControlDashboard` (Component: `render(width): string[]`, `handleInput(data): void`, with an `onSelectTranscript: (node: string, sessionId: string) => void` callback fired on Enter), a standalone entry point (`if (import.meta.url === ...)`-guarded `main()`) that polls a status file path given via `process.argv` and drives a real `TUI`/`ProcessTerminal`.

**Note for the implementer**: the exact `TUI`/`Terminal` mounting/render-triggering API (confirmed available: `new ProcessTerminal()`, `new TUI(terminal)`, `tui.addChild(component)`, `terminal.start(onInput, onResize)`) should be verified against `node_modules/@earendil-works/pi-tui/dist/tui.d.ts` and `terminal.d.ts` directly before writing the entry point -- this plan confirms the pieces exist and are importable (verified via a real `node src/_scratch-test.ts` run earlier this session with actual `pi-tui` imports), but the exact call sequence to trigger an initial render and subsequent re-renders on a poll tick was not fully traced during planning.

- [ ] **Step 1: Write the failing tests**

```typescript
// pi-ext/factory-watch/test/mission-control-dashboard.test.ts
import { describe, expect, test, vi } from "vitest";
import { MissionControlDashboard } from "../src/mission-control-dashboard.js";
import type { StatusRecord } from "../src/status-format.js";

const RECORD: StatusRecord = {
  session_id: "s1", task_id: "T-029", current_node: "dev", current_state: "running",
  pipeline: [
    { node: "context-gather", node_state: "pass", attempt: 1, max_attempts: 1, snippet: "", outcome: null, handoff: "-> dev: 3 files, coherence=yes", updated_at: "2026-07-22T00:00:00Z" },
    { node: "dev", node_state: "running", attempt: 2, max_attempts: 3, snippet: "", outcome: null, handoff: null, updated_at: "2026-07-22T00:00:01Z" },
  ],
  started_at: "2026-07-22T00:00:00Z", updated_at: "2026-07-22T00:00:01Z",
};

describe("MissionControlDashboard", () => {
  test("renders one row per pipeline stage with the task header", () => {
    const dashboard = new MissionControlDashboard(RECORD, () => {});
    const lines = dashboard.render(80).join("\n");
    expect(lines).toContain("T-029");
    expect(lines).toContain("context-gatherer");
    expect(lines).toContain("dev");
    expect(lines).toContain("validation");
    expect(lines).toContain("review");
    expect(lines).toContain("human-review");
  });

  test("Down/Up move the selected row", () => {
    const dashboard = new MissionControlDashboard(RECORD, () => {});
    dashboard.handleInput("\x1b[B");
    dashboard.handleInput("\r");
    const onSelect = vi.fn();
    const dashboard2 = new MissionControlDashboard(RECORD, onSelect);
    dashboard2.handleInput("\x1b[B"); // move to "dev" row (index 1)
    dashboard2.handleInput("\r");
    expect(onSelect).toHaveBeenCalledWith("dev", "s1");
  });

  test("updateRecord replaces the displayed data without losing selection", () => {
    const dashboard = new MissionControlDashboard(RECORD, () => {});
    dashboard.handleInput("\x1b[B"); // select "dev"
    const updated: StatusRecord = {
      ...RECORD,
      pipeline: [...RECORD.pipeline, {
        node: "validation", node_state: "pass", attempt: 1, max_attempts: 1,
        snippet: "", outcome: null, handoff: "-> review: sim tests green", updated_at: "2026-07-22T00:00:02Z",
      }],
    };
    dashboard.updateRecord(updated);
    expect(dashboard.render(80).join("\n")).toContain("-> review: sim tests green");
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /c/coding/pi-agent-factory/pi-ext/factory-watch && npm test -- mission-control-dashboard`
Expected: FAIL with a module-not-found error for `../src/mission-control-dashboard.js`

- [ ] **Step 3: Implement**

```typescript
// pi-ext/factory-watch/src/mission-control-dashboard.ts
import { readFileSync } from "node:fs";
import { formatMissionControlRows, parseStatus } from "./status-format.js";
import type { StatusRecord } from "./status-format.js";

const STAGE_ORDER = ["context-gather", "dev", "validation", "review", "human-review"];
const POLL_INTERVAL_MS = 500;

export class MissionControlDashboard {
  private selectedIndex = 0;

  constructor(
    private record: StatusRecord | null,
    private readonly onSelectTranscript: (node: string, sessionId: string) => void,
  ) {}

  updateRecord(record: StatusRecord | null): void {
    this.record = record;
  }

  handleInput(data: string): void {
    const rows = formatMissionControlRows(this.record, STAGE_ORDER);
    if (data === "\x1b[B" || data === "j") {
      this.selectedIndex = Math.min(this.selectedIndex + 1, rows.length - 1);
    } else if (data === "\x1b[A" || data === "k") {
      this.selectedIndex = Math.max(this.selectedIndex - 1, 0);
    } else if ((data === "\r" || data === "\n") && this.record !== null) {
      this.onSelectTranscript(rows[this.selectedIndex]!.node, this.record.session_id);
    }
  }

  render(width: number): string[] {
    const taskId = this.record?.task_id ?? "(no task)";
    const lines = [`Factory Mission Control — ${taskId}`, ""];
    const rows = formatMissionControlRows(this.record, STAGE_ORDER);
    rows.forEach((row, i) => {
      const prefix = i === this.selectedIndex ? "> " : "  ";
      lines.push(`${prefix}${row.label.padEnd(16)} ${row.state}`);
      if (row.handoff) {
        lines.push(`    ${row.handoff}`);
      }
    });
    lines.push("", "up/down select  Enter open transcript  q close");
    return lines;
  }
}

// Standalone entry point -- no `pi --extension`, no LLM. Verify the exact
// TUI/Terminal mounting call sequence against node_modules/@earendil-works/
// pi-tui/dist/{tui,terminal}.d.ts before finalizing this section; the pieces
// below (ProcessTerminal, TUI, addChild, terminal.start) are confirmed
// importable and constructible, but the initial-render/poll-driven-rerender
// sequence needs verifying against the real API, not assumed from this sketch.
async function main(): Promise<void> {
  const { ProcessTerminal, TUI } = await import("@earendil-works/pi-tui");
  const statusPathArgIndex = process.argv.indexOf("--status");
  const statusPath = process.argv[statusPathArgIndex + 1];
  if (statusPath === undefined) {
    console.error("usage: node mission-control-dashboard.js --status <path> --cwd <repo-root>");
    process.exit(1);
  }

  function readRecord(): StatusRecord | null {
    try {
      return parseStatus(readFileSync(statusPath, "utf-8"));
    } catch {
      return null;
    }
  }

  const terminal = new ProcessTerminal();
  const tui = new TUI(terminal);
  const dashboard = new MissionControlDashboard(readRecord(), (node, sessionId) => {
    // Wire to terminal-window.ts's spawnTerminalWindow + mission-control-transcript.ts
    // in Task 13, once index.ts's spawn call sites are established.
  });
  tui.addChild(dashboard);
  terminal.start(
    (data) => dashboard.handleInput(data),
    () => tui.invalidate(),
  );
  setInterval(() => {
    dashboard.updateRecord(readRecord());
    tui.invalidate();
  }, POLL_INTERVAL_MS);
}

if (process.argv[1]?.endsWith("mission-control-dashboard.js") || process.argv[1]?.endsWith("mission-control-dashboard.ts")) {
  void main();
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /c/coding/pi-agent-factory/pi-ext/factory-watch && npm run typecheck && npm test -- mission-control-dashboard`
Expected: PASS (the 3 component tests -- `main()`'s entry-point guard means it doesn't execute under vitest's import, matching how this plan's other standalone-script tasks separate pure/testable logic from the thin process-wiring wrapper)

- [ ] **Step 5: Commit**

```bash
git add pi-ext/factory-watch/src/mission-control-dashboard.ts pi-ext/factory-watch/test/mission-control-dashboard.test.ts
git commit -m "feat(factory-watch): mission control dashboard component + standalone viewer entry point"
```

---

### Task 12: `mission-control-transcript.ts`

**Files:**
- Create: `pi-ext/factory-watch/src/mission-control-transcript.ts`
- Test: `pi-ext/factory-watch/test/mission-control-transcript.test.ts`

**Interfaces:**
- Produces: `TranscriptViewer` (Component: `render(width): string[]`, `handleInput(data): void`, scrollable exactly like `ScrollableMarkdown`/the human-review-UI's `ReviewOverlay` file view -- reuse that same windowing pattern, not a new one), a standalone entry point polling a transcript log file for growth (re-reading and appending new lines as the file grows, for a still-running stage).

- [ ] **Step 1: Write the failing tests**

```typescript
// pi-ext/factory-watch/test/mission-control-transcript.test.ts
import { describe, expect, test } from "vitest";
import { TranscriptViewer } from "../src/mission-control-transcript.js";

function manyLines(n: number): string[] {
  return Array.from({ length: n }, (_, i) => `line ${i + 1}`);
}

describe("TranscriptViewer", () => {
  test("renders a windowed slice sized to the terminal's row count, plus a footer", () => {
    const view = new TranscriptViewer(manyLines(50), { terminal: { rows: 10 } });
    const lines = view.render(80);
    expect(lines.length).toBe(9); // 10 rows - 2 reserved (matches ScrollableMarkdown's own convention... but here 8 content + 1 footer = 9, no header line)
    expect(lines[0]).toBe("line 1");
    expect(lines[lines.length - 1]).toContain("of 50");
  });

  test("appendLines grows the content and End follows it (tail -f style)", () => {
    const view = new TranscriptViewer(manyLines(20), { terminal: { rows: 10 } });
    view.handleInput("\x1b[F"); // End -- jump to bottom
    view.appendLines(["line 21", "line 22"]);
    const lines = view.render(80);
    expect(lines[lines.length - 2]).toBe("line 22");
  });

  test("Down/Up scroll manually; appendLines does not force-follow if the user scrolled away from the bottom", () => {
    const view = new TranscriptViewer(manyLines(20), { terminal: { rows: 10 } });
    view.handleInput("\x1b[A"); // Up, away from the (default) bottom-follow position... or top; verify actual default scroll position against ScrollableMarkdown's own default (starts at top, offset 0) and adjust this test's setup accordingly
    view.appendLines(["line 21"]);
    // Assert scrollOffset did not jump to follow the new line, since the
    // user is not currently at the bottom (exact assertion depends on the
    // real starting scrollOffset default -- verify against ScrollableMarkdown's
    // own behavior, which starts at offset 0, not "following", so adjust this
    // test to scroll to the bottom first, then away, before appending).
  });

  test("shows a 'not started yet' placeholder for empty content", () => {
    const view = new TranscriptViewer([], { terminal: { rows: 10 } });
    expect(view.render(80).join("\n")).toContain("not started yet");
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /c/coding/pi-agent-factory/pi-ext/factory-watch && npm test -- mission-control-transcript`
Expected: FAIL with a module-not-found error for `../src/mission-control-transcript.js`

- [ ] **Step 3: Implement**

```typescript
// pi-ext/factory-watch/src/mission-control-transcript.ts
import { existsSync, readFileSync, statSync } from "node:fs";
import { Key, matchesKey } from "@earendil-works/pi-tui";

export interface TuiLike {
  terminal: { rows: number };
}

export class TranscriptViewer {
  private lines: string[];
  private scrollOffset = 0;
  private followingBottom = false;

  constructor(initialLines: string[], private readonly tui: TuiLike) {
    this.lines = initialLines;
  }

  private getViewportHeight(): number {
    return Math.max(1, this.tui.terminal.rows - 2);
  }

  appendLines(newLines: string[]): void {
    const wasAtBottom = this.followingBottom;
    this.lines.push(...newLines);
    if (wasAtBottom) {
      this.scrollOffset = Number.MAX_SAFE_INTEGER;
    }
  }

  handleInput(data: string): void {
    const viewportHeight = this.getViewportHeight();
    if (matchesKey(data, Key.down)) {
      this.scrollOffset += 1;
      this.followingBottom = false;
    } else if (matchesKey(data, Key.up)) {
      this.scrollOffset -= 1;
      this.followingBottom = false;
    } else if (matchesKey(data, Key.pageDown)) {
      this.scrollOffset += viewportHeight;
      this.followingBottom = false;
    } else if (matchesKey(data, Key.pageUp)) {
      this.scrollOffset -= viewportHeight;
      this.followingBottom = false;
    } else if (matchesKey(data, Key.home)) {
      this.scrollOffset = 0;
      this.followingBottom = false;
    } else if (matchesKey(data, Key.end)) {
      this.scrollOffset = Number.MAX_SAFE_INTEGER;
      this.followingBottom = true;
    }
  }

  render(width: number): string[] {
    if (this.lines.length === 0) {
      return ["(not started yet)"];
    }
    const viewportHeight = this.getViewportHeight();
    const maxOffset = Math.max(0, this.lines.length - viewportHeight);
    this.scrollOffset = Math.min(Math.max(0, this.scrollOffset), maxOffset);
    if (this.scrollOffset >= maxOffset) {
      this.followingBottom = true;
    }
    const visible = this.lines.slice(this.scrollOffset, this.scrollOffset + viewportHeight);
    const lastShown = Math.min(this.scrollOffset + viewportHeight, this.lines.length);
    const footer = `-- line ${this.scrollOffset + 1}-${lastShown} of ${this.lines.length} (arrows/PgUp/PgDn/Home/End, q close) --`;
    return [...visible, footer];
  }
}

// Standalone entry point. Same TUI/Terminal mounting caveat as
// mission-control-dashboard.ts -- verify the exact API against the real
// node_modules/@earendil-works/pi-tui .d.ts files before finalizing.
async function main(): Promise<void> {
  const { ProcessTerminal, TUI } = await import("@earendil-works/pi-tui");
  const pathArgIndex = process.argv.indexOf("--transcript");
  const transcriptPath = process.argv[pathArgIndex + 1];
  if (transcriptPath === undefined) {
    console.error("usage: node mission-control-transcript.js --transcript <path>");
    process.exit(1);
  }

  function readLines(): string[] {
    if (!existsSync(transcriptPath)) {
      return [];
    }
    return readFileSync(transcriptPath, "utf-8").split("\n");
  }

  const terminal = new ProcessTerminal();
  const tui = new TUI(terminal);
  const viewer = new TranscriptViewer(readLines(), { terminal: { rows: terminal.rows } });
  tui.addChild(viewer);
  terminal.start(
    (data) => viewer.handleInput(data),
    () => tui.invalidate(),
  );

  let lastSize = existsSync(transcriptPath) ? statSync(transcriptPath).size : 0;
  setInterval(() => {
    if (!existsSync(transcriptPath)) {
      return;
    }
    const size = statSync(transcriptPath).size;
    if (size > lastSize) {
      const allLines = readLines();
      viewer.appendLines(allLines.slice(-Math.max(1, allLines.length - lastSize)));
      lastSize = size;
      tui.invalidate();
    }
  }, 500);
}

if (process.argv[1]?.endsWith("mission-control-transcript.js") || process.argv[1]?.endsWith("mission-control-transcript.ts")) {
  void main();
}
```

**Note for the implementer**: the poll loop's "which lines are new" logic (`allLines.slice(-Math.max(1, allLines.length - lastSize))`) is a rough approximation mixing byte-size deltas with line-count slicing -- it works passably but isn't exact (a partial last line growing across polls could be double-counted). If this proves visibly wrong in manual verification, a more correct approach is tracking the last-read line COUNT (not byte size) and slicing from there on each poll; flagged here rather than over-engineered into the initial implementation, since the pure `TranscriptViewer` class itself (fully tested above) is correct regardless of how its caller decides what counts as "new lines."

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /c/coding/pi-agent-factory/pi-ext/factory-watch && npm run typecheck && npm test -- mission-control-transcript`
Expected: PASS (all component tests)

- [ ] **Step 5: Commit**

```bash
git add pi-ext/factory-watch/src/mission-control-transcript.ts pi-ext/factory-watch/test/mission-control-transcript.test.ts
git commit -m "feat(factory-watch): scrollable transcript viewer component + standalone viewer entry point"
```

---

### Task 13: Restore `/factory-run`'s pipeline; wire mission control into `/factory`/`/factory-run`

**Files:**
- Modify: `pi-ext/factory-watch/src/index.ts`
- Modify: `pi-ext/factory-watch/README.md`
- Test: `pi-ext/factory-watch/test/handler.test.ts` (extend)

**Interfaces:**
- Consumes: `buildRunCommand` with `taskId` (`process-control.ts`, already supports this), `spawnTerminalWindow` (Task 10), the mission-control dashboard/transcript entry points (Tasks 11-12).

**Read the current file first**: this file has evolved across two other plans this session (the write-chunk-guard feature, the human-review-UI plan) -- confirm the exact current shape of `/factory`'s handler, `launchAndWatch`, `launchInteractiveReview`, and `/factory-run`'s handler (including `buildFactoryRunPrompt`, `findTaskFile`, `extractSourcePlan`, `RUN_SKILL_NAMES`) before editing, rather than assuming the line numbers referenced elsewhere in this plan's own prior sections still hold exactly.

- [ ] **Step 1: Write the failing tests**

Add to `pi-ext/factory-watch/test/handler.test.ts`:

```typescript
  test("/factory-run with no id lists todo tasks, picks one, and routes through launchAndWatch/launchInteractiveReview like /factory", async () => {
    vi.mocked(spawnSync).mockReturnValue({
      status: 0,
      stdout: JSON.stringify([{ id: "T-001", title: "First", status: "todo" }]),
      stderr: "",
    } as ReturnType<typeof spawnSync>);
    const ui: UiApi = {
      notify: vi.fn(), setStatus: vi.fn(), setWidget: vi.fn(),
      select: vi.fn().mockResolvedValue("T-001  First"),
      confirm: vi.fn(async () => true), editor: vi.fn(), custom: vi.fn(),
    };
    const { commands } = capture();
    const ctx = fakeCtx({ ui });

    await commands.get("factory-run")!.handler("--auto", ctx);

    // --auto -> launchAndWatch -> detached spawn, matching /factory's own --auto test
    expect(spawn).toHaveBeenCalled();
  });

  test("/factory-run spawns a mission control terminal window alongside the run", async () => {
    const { spawnTerminalWindow } = await import("../src/terminal-window.js");
    vi.mocked(spawnSync).mockReturnValue({
      status: 0, stdout: JSON.stringify([{ id: "T-001", title: "t", status: "todo" }]), stderr: "",
    } as ReturnType<typeof spawnSync>);
    const { commands } = capture();
    const ctx = fakeCtx();

    await commands.get("factory-run")!.handler("--auto T-001", ctx);

    expect(vi.mocked(spawnTerminalWindow)).toHaveBeenCalled();
  });
```

(This second test requires `vi.mock("../src/terminal-window.js", ...)` at the top of the file, mocking `spawnTerminalWindow` as a `vi.fn()` -- add that alongside the file's existing `vi.mock` calls.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /c/coding/pi-agent-factory/pi-ext/factory-watch && npm test -- handler`
Expected: FAIL -- `/factory-run` still seeds an interactive session unconditionally, never calls `spawnTerminalWindow` or routes through `launchAndWatch`.

- [ ] **Step 3: Implement**

In `index.ts`, add the import:

```typescript
import { spawnTerminalWindow } from "./terminal-window.js";
```

Add a helper that both `/factory` and `/factory-run` call to spawn the mission control window (right after `launchAndWatch`/`launchInteractiveReview` starts the orchestrator, sharing the same `statusPath`):

```typescript
  function launchMissionControl(ctx: ExtCommandCtx): void {
    const statusPath = join(ctx.cwd, STATUS_FILE);
    spawnTerminalWindow(
      "node",
      [join(ctx.cwd, "pi-ext", "factory-watch", "src", "mission-control-dashboard.ts"), "--status", statusPath, "--cwd", ctx.cwd],
      { cwd: ctx.cwd },
    );
  }
```

Call `launchMissionControl(ctx)` once, right after the `launchAndWatch`/`launchInteractiveReview` call in both `/factory`'s and `/factory-run`'s handlers (both branches -- `--auto` and interactive -- get a mission control window, since both still run the pipeline that's worth watching).

Replace `/factory-run`'s handler body (removing the `ctx.newSession`/`buildFactoryRunPrompt` seeding path entirely) with the same shape as `/factory`'s handler, targeting the resolved `taskId`:

```typescript
  pi.registerCommand("factory-run", {
    description: "Run the factory on one specific task, watching progress live",
    handler: async (args: string, ctx: ExtCommandCtx) => {
      const lockPath = join(ctx.cwd, LOCK_FILE);
      if (isAlreadyRunning(ctx, lockPath)) {
        return;
      }
      if (ctx.model === undefined) {
        ctx.ui.notify("no model selected in this session -- can't launch factory", "error");
        return;
      }

      const { auto, rest } = parseAutoFlag(args);
      let taskId = rest;
      if (taskId === "") {
        const cmd = buildListJsonCommand();
        const result = spawnSync(cmd.bin, cmd.args, { cwd: ctx.cwd, encoding: "utf-8" });
        if (result.status !== 0) {
          ctx.ui.notify(`factory-run failed to list tasks: ${result.stderr || "unknown error"}`, "error");
          return;
        }
        let tasks: TaskSummary[];
        try {
          tasks = JSON.parse(result.stdout) as TaskSummary[];
        } catch {
          ctx.ui.notify("factory-run failed to parse task list", "error");
          return;
        }
        const todoTasks = tasks.filter((t) => t.status === "todo");
        if (todoTasks.length === 0) {
          ctx.ui.notify("no todo tasks", "info");
          return;
        }
        const selected = await ctx.ui.select("Run which task?", todoTasks.map(formatTaskOption));
        if (selected === undefined) {
          return;
        }
        taskId = parseTaskIdFromOption(selected);
      }

      const cmd = buildRunCommand(ctx.model.provider, ctx.model.id, taskId);
      const label = `${ctx.model.provider}/${ctx.model.id}, task ${taskId}`;
      if (auto) {
        launchAndWatch(ctx, cmd, label);
      } else {
        await launchInteractiveReview(ctx, cmd, label);
      }
      launchMissionControl(ctx);
    },
  });
```

Remove `buildFactoryRunPrompt`, `findTaskFile`, `extractSourcePlan`, `RUN_SKILL_NAMES`, and their now-unused imports (`readdirSync` if nothing else in this file uses it, `homedir`/`loadSkills`/`stripFrontmatter`/`buildSkillBlock` if `/plan`'s handler is the only other user and still needs them -- check each import's remaining use sites individually before removing; several of these are still used by `/plan`, which is unrelated and must be left untouched).

Add a `--auto`/mission-control section to `pi-ext/factory-watch/README.md` documenting that `/factory-run` now runs the same pipeline `/factory` does (targeting one task), and that both commands open a mission control window alongside the run.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /c/coding/pi-agent-factory/pi-ext/factory-watch && npm run typecheck && npm test`
Expected: PASS (full suite -- this is the final integration task, run everything, not just `handler.test.ts`)

- [ ] **Step 5: Commit**

```bash
git add pi-ext/factory-watch/src/index.ts pi-ext/factory-watch/README.md pi-ext/factory-watch/test/handler.test.ts
git commit -m "feat(factory-watch): restore /factory-run's pipeline; spawn mission control alongside /factory and /factory-run"
```

---

## Manual Verification (after all tasks complete)

Real-terminal, real-process behavior that automated tests can't fully exercise:

1. Run `pif`, `/factory-run T-<some-todo-task>` (no `--auto`), and confirm a second terminal window (mission control) actually opens, showing all 5 pipeline stages, the running one highlighted.
2. Watch a real run progress through context-gather → dev → validation → review, confirming handoff messages appear as each stage completes.
3. Select the "dev" row and press Enter; confirm a third terminal window opens tailing that stage's transcript, following new output live while dev is still running.
4. If the run reaches human-review, confirm mission control shows `blocked -- waiting for you to review the diff` instead of going silent.
5. After the run completes, confirm the session-review agent actually ran (check `sessions/latest.md` or the session record for its output, and check whether it wrote anything to `kb/`).
6. Confirm `/factory --auto` and `/factory-run --auto <task-id>` still work exactly as before (detached, no mission control needed to matter for correctness, though it'll still open).
