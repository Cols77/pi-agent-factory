# Design: Mission Control Dashboard, KB/Review Wiring, and the Session-Review Agent

**Date:** 2026-07-22
**Status:** Draft for review
**Author:** Colin AUBE (with Claude)

---

## 1. Context & Framing

Three related gaps in the factory pipeline, discovered together while designing a way to observe a running factory task:

1. **No visibility into the pipeline.** `/factory-run` currently seeds a single interactive session where the current model does a task's work live (a recent, deliberate redesign) — there is no view of the underlying multi-role pipeline (context-gatherer → dev → validation → review → human-review) actually happening, no way to see which stage is running or blocked, and no way to inspect what a specific stage said.
2. **Review doesn't see the KB or the context manifest.** `run_dev` receives the context-gatherer's manifest and the selected KB entries; `run_review` receives neither — it reviews from the task text and its own skills alone.
3. **The session-review agent role is fully scaffolded but was never wired up.** `AgentRole.SESSION_WRITER` exists in `roles.py` with skills/scope/prompt already defined, deliberately left dead in a prior review ("a deterministic gate/pure-Python step is preferable... for now"). What's wanted now is richer than its original "summarize for resume" purpose: analyze what happened, write new KB entries for issues worth recording, and suggest skill/prompt improvements.

A fourth, unrelated but blocking bug (`parse_pi_json` targeting Pi's old v2 event format, so the context-gatherer step always failed) was found and fixed separately, already committed (`9bfa55c`) — mentioned here only because without it, none of this pipeline ever ran far enough to observe.

### 1.1 Goals

- `/factory-run` goes back to running the real pipeline (undoing the interactive-session redesign), targeting one specific task, same as it worked before that redesign.
- A "mission control" TUI dashboard, opened in its own terminal window alongside the main `pif` session, showing each pipeline stage's live state and the handoff between stages -- reusing status data the pipeline already produces, plus a small backend addition for the one real gap (no "blocked" state exists today for the human-review wait).
- Drilling into any one stage opens a third terminal window with that stage's full transcript, scrollable, live-following if still running -- this requires persisting each stage's complete output, which today is discarded in memory once a step finishes.
- `run_review` receives the same `manifest`/`kb_entries` that `run_dev` already does.
- `AgentRole.SESSION_WRITER` is renamed to `AgentRole.SESSION_REVIEW`, its scope widened to write KB entries, and it is actually invoked at the end of `run_next` -- analyzing the task's full pipeline run, writing new KB entries for genuinely reusable issues, and appending skill/prompt improvement suggestions to the session summary.

### 1.2 Non-Goals

- **Not multiple concurrent task runs.** The factory still runs one task at a time (`sessions/.factory-run.lock` still refuses a second run); mission control visualizes the sequential pipeline *within* one run, not parallel agents across many.
- **Not a web/GUI dashboard.** Everything here is terminal-window + TUI, using the same `pi-tui` primitives already used elsewhere in this extension. No browser, no `frontend-design` skill needed for this iteration.
- **Not auto-applying skill/prompt improvements.** The session-review agent's suggestions are written text for a human to read and act on later -- it does not edit `.pi/skills/**` or `prompts.py` directly. Only KB entries (already an append-first, human-curated store by convention) are written directly.
- **Not cross-platform terminal spawning, verified.** The window-spawning mechanism (PowerShell `Start-Process`) is confirmed working on this Windows machine; a POSIX fallback is included as best-effort but untested.

---

## 2. Restoring `/factory-run`'s pipeline

`buildRunCommand` (`process-control.ts`) already supports an optional task ID -- this is what `/factory-run` used before its redesign, and what `/factory --task <id>` still could use today. Restoring `/factory-run`:

- Keep the existing task-picker logic (list todo tasks, `ctx.ui.select` if no id given).
- Replace the `ctx.newSession(...)` seeding with the same `if (auto) { launchAndWatch(...) } else { await launchInteractiveReview(...) }` branch `/factory` already uses, just with `buildRunCommand(provider, model, taskId)` instead of the no-task-id form.
- Remove `buildFactoryRunPrompt`/the skill-loading-for-a-seed-prompt code path this replaces (dead code once nothing calls it) -- **flagged as a judgment call for whoever implements this**: confirm nothing else in the codebase still depends on `buildFactoryRunPrompt` before deleting it.

## 3. Mission control: architecture

```
/factory-run T-029
    |
    v
spawn orchestrator (same launchAndWatch/launchInteractiveReview path as /factory)
    |
    v
ALSO: spawn a second terminal window running a standalone mission-control
      viewer (no `pi --extension`, no LLM -- pure data visualization)
    |
    v
viewer polls sessions/.factory-status.json every ~500ms
  - reads session_id from the status record itself (no need to pass it in)
  - renders one row per pipeline stage from the `pipeline` array
  - highlights whichever stage is "running" or "blocked"
```

**The "blocked" gap**: right before `human_review.request_review(...)` blocks on `stdin.readline()` in `runner.py`, add:
```python
status.report(
    task_id=task.id, node="human-review", node_state="blocked",
    attempt=1, max_attempts=1, handoff="waiting for you to review the diff",
)
```
This is the only backend status-reporting change mission control needs for the "which agent is blocked" requirement -- every other stage already reports its own running/pass/fail/handoff state.

**Transcripts**: each pipeline step's full raw output (`AgentResult.raw`, already returned by `backend.run(...)` in `run_context_gatherer`/`run_dev`/`run_review`, currently discarded unless the step fails) gets persisted. New module `src/factory/orchestrator/transcripts.py`:
```python
def write_role_transcript(sessions_dir: Path, session_id: str, node: str, attempt: int, raw: str) -> Path:
    transcript_dir = sessions_dir / ".factory-transcripts" / session_id
    transcript_dir.mkdir(parents=True, exist_ok=True)
    path = transcript_dir / f"{node}-attempt{attempt}.log"
    path.write_text(raw, encoding="utf-8")
    return path
```
Keyed by attempt (not just node name) since dev/review can retry within one task run, and each attempt's transcript should survive independently. `run_context_gatherer`/`run_dev`/`run_review` each gain an optional `transcript_dir: Path | None = None` parameter (default `None` = today's behavior unchanged), threaded through `run_task`/`run_next`/`__main__.py`, calling `write_role_transcript(...)` right after each `backend.run(...)` call when the parameter is set.

## 4. Mission control: the dashboard screen

A standalone Node entry point (not a pi extension -- no LLM involvement), using `@earendil-works/pi-tui`'s `ProcessTerminal` and a custom `Component` directly:

```
Factory Mission Control — T-029: Core Data Types & FakeFlightController

  context-gather   done      -> dev: 3 files, coherence=yes
> dev              running   attempt 2/3, unit tests failed, retrying
  validation       pending
  review           pending
  human-review     pending

up/down select  Enter open transcript  q close
```

One row per pipeline stage in fixed order, populated from `.factory-status.json`'s `pipeline` array as it grows; stages not yet reached show `pending`. Re-renders on a poll interval (~500ms). Since the lock file already prevents a genuinely concurrent second run, a briefly-stale status file from a *previous* run (before the new run's first status update lands) is an acceptable, non-blocking race for v1.

## 5. Mission control: drill-down transcript window

`Enter` on a selected row spawns a third terminal window (same spawning mechanism as the dashboard itself) tailing `sessions/.factory-transcripts/<session_id>/<node>-attempt<N>.log` -- scrollable the same way as `/review-plans`'s `ScrollableMarkdown`, following the file as it grows if that stage is still running (if the file doesn't exist yet -- stage hasn't started -- show a simple "not started yet" message instead of an error).

## 6. Window spawning mechanism

Confirmed working on this machine via PowerShell:
```
Start-Process powershell -ArgumentList "-NoExit", "-Command", "<command to run>"
```
Wrapped as a small TS helper (e.g. `spawnTerminalWindow(command: string, args: string[]): void`) used by both the dashboard-launch and the drill-down-launch call sites. POSIX platforms get a best-effort fallback (e.g. `xterm -e`/`gnome-terminal --`/`open -a Terminal`) -- untested, since this environment is Windows-only; flagged for whoever eventually needs it on another platform to verify.

## 7. `run_review` gains `manifest`/`kb_entries`

`run_review`'s signature changes from:
```python
def run_review(backend, gates, task, repo_root, status=...) -> tuple[NodeOutcome, NodeEvent, list[str]]:
```
to:
```python
def run_review(backend, gates, task, manifest, kb_entries, repo_root, status=...) -> tuple[NodeOutcome, NodeEvent, list[str]]:
```
matching `run_dev`'s existing parameter shape exactly, and its `compose_prompt` call gains the same two arguments `run_dev` already passes. `run_task`'s call site updates accordingly (it already holds both values in scope from earlier in the function, no new plumbing needed there). `compose_prompt`'s own signature/behavior for including manifest/kb_entries in a role's prompt already exists (that's how `run_dev` gets them today) -- review only needed to start passing them through.

## 8. The session-review agent

**Rename**: `AgentRole.SESSION_WRITER` -> `AgentRole.SESSION_REVIEW` in `types.py`. Safe -- confirmed zero call sites reference this role anywhere in the pipeline today, so there's no serialized data using the old string to migrate.

**Scope widened** (`roles.py`): from `Scope(allow=["sessions/**"], bash="deny")` to `Scope(allow=["sessions/**", "kb/**"], bash="deny")` -- KB entries and the session summary (including its suggestions section) are both plain file writes, no bash needed.

**Prompt rewritten** (`roles.py`), replacing "Summarize what happened this session for reliable resume" with something covering all three responsibilities: analyze the task's full pipeline run, write a new `kb/kb-NNNN-<slug>.md` entry (checking existing entries for the next free number) for any issue that's genuinely worth remembering for future tasks -- not every run needs one -- and append a short skill/prompt improvement suggestion section to the session summary for a human to read later. No new Python-side parsing needed for the KB/suggestions output: this agent has direct file-write scope for both destinations, so it does this work the same way dev writes code -- through its own file tools, not by returning structured JSON for the orchestrator to act on.

**A real gap this design caught in its own first draft**: `compose_prompt` has no parameter today for "what happened during the run" -- not for any role. `run_task`'s `TaskResult.events: list[NodeEvent]` (each carrying `node`/`result`/`attempts`/`extra`) is exactly the pipeline history the session-review agent needs to analyze, but nothing currently threads it into a prompt. `compose_prompt` needs a new optional parameter, e.g. `events: list[NodeEvent] | None = None`, formatted similarly to how `manifest`/`kb_entries`/`feedback` are conditionally appended today (e.g. `"- context-gather: pass (1 attempt)"`, `"- dev: pass (2 attempts)"`, `"- review: pass"` per event) -- used only by the `SESSION_REVIEW` call site; every other role keeps passing `None` for it, unaffected.

**Wiring**: invoked once at the end of `run_next`, after `write_session` persists the session record -- `backend.run(AgentRole.SESSION_REVIEW, compose_prompt(AgentRole.SESSION_REVIEW, task, events=result.events, ...))`, reporting a `session-review` status node the same way other stages do (also visible in mission control as a final row, if a task run is being watched live).

**Required prerequisite** (already flagged by the existing code comment this design confirms): vendor `.pi/skills/session-report/SKILL.md` under this repo's `.pi/skills/` -- `ROLE_SKILLS[AgentRole.SESSION_REVIEW]` already names `"session-report"`, and `compose_prompt`/`load_skill_block` hard-fail with `FileNotFoundError` if a named skill isn't vendored. This did not matter while the role was dead; it will crash immediately on first real use otherwise.

---

## 9. Self-Review

- **Placeholder scan**: no TBD/TODO. The two explicitly-flagged judgment calls (confirming nothing else depends on `buildFactoryRunPrompt` before deletion; verifying the POSIX terminal-spawning fallback on a non-Windows machine) are real open items for the implementer, not vague hand-waving -- each has a concrete, checkable action.
- **Internal consistency**: Section 3's transcript design and Section 5's drill-down both key off `session_id` read from the status file, not passed as a separate argument -- consistent. Section 7's `run_review` signature change and Section 8's `SESSION_REVIEW` invocation both slot into `run_task` without touching each other.
- **A real gap caught during this self-review, not just before it**: the first draft of Section 8 claimed the session-review agent could analyze "what happened" using data compose_prompt already assembles -- checking `prompts.py` directly showed that's false; no role's prompt today includes the pipeline's events/outcome history. Corrected by adding an explicit `events` parameter to `compose_prompt` in Section 8, used only by `SESSION_REVIEW`. This is exactly the kind of claim that needed verifying against the real file rather than assumed from the surrounding design's shape.
- **Scope check**: four fairly independent pieces (restore /factory-run, mission control, review context-wiring, session-review agent) bundled into one spec because they were discovered together and the user asked they be planned together -- but they decompose cleanly into separate implementation tasks (already reflected in how each section above is self-contained).
