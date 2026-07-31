# Mission Control — Review Decision (Increment 2 / E2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a human complete the human-review approve/reject decision from the mission-control dashboard, not only from the interactive pi terminal, by unifying both UIs on a file-based decision channel.

**Architecture:** A new `FileHumanReviewGate` (Python) replaces the stdin-blocking `StdioHumanReviewGate`, polling for `<transcript_dir>/review-decision.json`. Both `index.ts`'s interactive-terminal review flow and the new `mission-control-review.ts` decision loop write to that same file via a shared `writeReviewDecision`/`reviewDecisionPath` helper. `mission-control-review.ts` gains a real decision loop: comment/edit via spawning `$EDITOR` (reusing `resolveEditorLaunch`), approve/reject via a new `ConfirmPrompt` pi-tui component.

**Tech Stack:** Python (pytest), TypeScript (`pi-ext/factory-watch`, vitest, `@earendil-works/pi-tui`).

## Global Constraints

- `HumanReviewDecision`, the `HumanReviewGate` protocol shape, `ReviewOverlay`'s rendering/input-handling core, `runReviewLoop`'s decision logic, `computeReviewFiles`, `format_review_feedback`, and the dev-retry feedback loop stay unchanged. Only the review's *transport* changes.
- The orchestration pipeline's gate sequence (context→dev→validation→review→human-review) is not restructured.
- Standalone TS entry points (`mission-control-review.ts` and anything it imports) run via plain `node <file>.ts`: **no TypeScript constructor parameter properties**, and **relative imports between node-executed source files use `.ts` extensions**.
- `StdioHumanReviewGate` is removed once `FileHumanReviewGate` is wired in — don't keep two live implementations of the same protocol.
- Design reference: `docs/superpowers/specs/2026-07-24-mission-control-review-decision-design.md`.

---

## File Structure

**Python (`src/factory/`):**
- `orchestrator/human_review.py` (modify) — remove `StdioHumanReviewGate`, add `FileHumanReviewGate`.
- `orchestrator/__main__.py` (modify) — construct `FileHumanReviewGate(transcript_dir)`.

**TypeScript (`pi-ext/factory-watch/src/`):**
- `review-protocol.ts` (modify) — `writeReviewDecision` becomes file-based; add `reviewDecisionPath`; remove `parseReviewPendingLine`/`ReviewPendingMessage`.
- `index.ts` (modify) — `launchInteractiveReview`: closed stdio, status-file polling, file-based decision write.
- `review-overlay.ts` (modify) — export `hasCodeOnPath` (was private) for reuse.
- `mission-control-review.ts` (modify) — comment/edit editor-spawn helpers, `ReviewBrowser` gains a persistent comments map and a confirm-prompt flow, `buildReviewArgs` gains `taskId`/`sessionId`.
- `confirm-prompt.ts` (new) — `ConfirmPrompt` component.
- `mission-control-dashboard.ts` (modify) — `openReviewBrowser` passes `--task-id`/`--session-id`.

---

### Task 1: `FileHumanReviewGate` (Python)

**Files:**
- Modify: `src/factory/orchestrator/human_review.py`
- Modify: `src/factory/orchestrator/__main__.py`
- Test: `tests/unit/orchestrator/test_human_review.py` (rewrite the `StdioHumanReviewGate` tests into `FileHumanReviewGate` tests)

**Interfaces:**
- Produces: `FileHumanReviewGate(transcript_dir: Path, poll_interval: float = 1.0)` implementing `HumanReviewGate.request_review(task_id, start_commit) -> HumanReviewDecision`. Polls for `<transcript_dir>/review-decision.json`, reads it once present, deletes it, returns the decision. `HumanReviewDecision`/`HumanReviewGate`/`FakeHumanReviewGate`/`format_review_feedback` unchanged.
- Consumed by: `__main__.py`, which already computes `transcript_dir` before constructing the gate.

- [ ] **Step 1: Write the failing tests**

Replace the three `StdioHumanReviewGate`-specific tests in `tests/unit/orchestrator/test_human_review.py` with:

```python
import threading
import time
from pathlib import Path

from factory.orchestrator.human_review import FileHumanReviewGate


def test_file_gate_returns_decision_when_file_already_exists(tmp_path: Path):
    decision_path = tmp_path / "review-decision.json"
    decision_path.write_text(
        json.dumps({"decision": "approve", "comments": {}}), encoding="utf-8"
    )
    gate = FileHumanReviewGate(tmp_path, poll_interval=0.01)

    result = gate.request_review("T-001", "abc123")

    assert result == HumanReviewDecision(decision="approve", comments={})


def test_file_gate_parses_reject_with_comments(tmp_path: Path):
    decision_path = tmp_path / "review-decision.json"
    decision_path.write_text(
        json.dumps({"decision": "reject", "comments": {"src/x.py": "fix this"}}), encoding="utf-8"
    )
    gate = FileHumanReviewGate(tmp_path, poll_interval=0.01)

    result = gate.request_review("T-001", "abc123")

    assert result.decision == "reject"
    assert result.comments == {"src/x.py": "fix this"}


def test_file_gate_deletes_the_decision_file_after_reading(tmp_path: Path):
    decision_path = tmp_path / "review-decision.json"
    decision_path.write_text(json.dumps({"decision": "approve", "comments": {}}), encoding="utf-8")
    gate = FileHumanReviewGate(tmp_path, poll_interval=0.01)

    gate.request_review("T-001", "abc123")

    assert not decision_path.exists()


def test_file_gate_waits_for_the_file_to_appear(tmp_path: Path):
    decision_path = tmp_path / "review-decision.json"
    gate = FileHumanReviewGate(tmp_path, poll_interval=0.01)

    def write_after_delay():
        time.sleep(0.05)
        decision_path.write_text(json.dumps({"decision": "approve", "comments": {}}), encoding="utf-8")

    threading.Thread(target=write_after_delay).start()
    result = gate.request_review("T-001", "abc123")

    assert result.decision == "approve"
```

(Remove `test_stdio_gate_writes_review_pending_line_and_reads_decision`, `test_stdio_gate_parses_reject_with_comments`, `test_stdio_gate_raises_eof_error_when_stdin_closes_without_a_decision`, and the now-unused `StdioHumanReviewGate`/`io` imports. Keep `test_fake_gate_records_requests_and_returns_scripted_decisions` and the two `format_review_feedback` tests unchanged.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /c/coding/pi-agent-factory && uv run pytest tests/unit/orchestrator/test_human_review.py -v`
Expected: FAIL with `ImportError: cannot import name 'FileHumanReviewGate'`.

- [ ] **Step 3: Implement**

In `src/factory/orchestrator/human_review.py`, remove `StdioHumanReviewGate` (and the now-unused `sys`/`IO` imports if nothing else in the file needs them) and add:

```python
import time


class FileHumanReviewGate:
    def __init__(self, transcript_dir: Path, poll_interval: float = 1.0) -> None:
        self._decision_path = transcript_dir / "review-decision.json"
        self._poll_interval = poll_interval

    def request_review(self, task_id: str, start_commit: str) -> HumanReviewDecision:
        while not self._decision_path.exists():
            time.sleep(self._poll_interval)
        payload = json.loads(self._decision_path.read_text(encoding="utf-8"))
        self._decision_path.unlink()
        return HumanReviewDecision(decision=payload["decision"], comments=payload.get("comments", {}))
```

Add the `from pathlib import Path` import if not already present in the file.

In `src/factory/orchestrator/__main__.py`, change:

```python
from factory.orchestrator.human_review import StdioHumanReviewGate
```

to:

```python
from factory.orchestrator.human_review import FileHumanReviewGate
```

and change:

```python
    human_review = None if args.auto else StdioHumanReviewGate()
```

to:

```python
    human_review = None if args.auto else FileHumanReviewGate(transcript_dir)
```

(`transcript_dir` is already computed above this line in `main()` — no new variable needed.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /c/coding/pi-agent-factory && uv run pytest tests/unit/orchestrator/test_human_review.py -v`
Expected: PASS (6 tests: 4 new `FileHumanReviewGate` tests + `test_fake_gate_records_requests_and_returns_scripted_decisions` + the 2 `format_review_feedback` tests — 7 total).

Also run the full orchestrator suite, since this changes what `__main__.py` constructs:
Run: `cd /c/coding/pi-agent-factory && uv run pytest tests/unit/orchestrator/ -v`
Expected: PASS (no other test references `StdioHumanReviewGate`).

- [ ] **Step 5: Commit**

```bash
git add src/factory/orchestrator/human_review.py src/factory/orchestrator/__main__.py tests/unit/orchestrator/test_human_review.py
git commit -m "feat: replace StdioHumanReviewGate with a file-polling FileHumanReviewGate"
```

---

### Task 2: `review-protocol.ts` — file-based decision write

**Files:**
- Modify: `pi-ext/factory-watch/src/review-protocol.ts`
- Test: `pi-ext/factory-watch/test/review-protocol.test.ts` (extend or create — read it first if it exists)

**Interfaces:**
- Produces: `writeReviewDecision(path: string, decision: ReviewDecisionPayload): void` (writes atomically: temp file + rename). `reviewDecisionPath(cwd: string, sessionId: string): string` — returns `<cwd>/sessions/.factory-transcripts/<sessionId>/review-decision.json`.
- Removes: `parseReviewPendingLine`, `ReviewPendingMessage` (no longer used anywhere once Task 3 lands).

- [ ] **Step 1: Write the failing tests**

Read the existing `pi-ext/factory-watch/test/review-protocol.test.ts` first (if present) for its conventions, then write/replace with:

```typescript
import { mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, test } from "vitest";
import { reviewDecisionPath, writeReviewDecision } from "../src/review-protocol.ts";

describe("reviewDecisionPath", () => {
  test("joins cwd, sessions, .factory-transcripts, sessionId, review-decision.json", () => {
    expect(reviewDecisionPath("/repo", "s1")).toBe(
      join("/repo", "sessions", ".factory-transcripts", "s1", "review-decision.json"),
    );
  });
});

describe("writeReviewDecision", () => {
  test("writes the decision as JSON at the given path, creating parent dirs", () => {
    const dir = mkdtempSync(join(tmpdir(), "review-decision-"));
    const path = join(dir, "nested", "review-decision.json");

    writeReviewDecision(path, { decision: "approve", comments: {} });

    const written = JSON.parse(readFileSync(path, "utf-8"));
    expect(written).toEqual({ decision: "approve", comments: {} });
  });

  test("writes reject decisions with comments", () => {
    const dir = mkdtempSync(join(tmpdir(), "review-decision-"));
    const path = join(dir, "review-decision.json");

    writeReviewDecision(path, { decision: "reject", comments: { "src/a.ts": "fix this" } });

    const written = JSON.parse(readFileSync(path, "utf-8"));
    expect(written).toEqual({ decision: "reject", comments: { "src/a.ts": "fix this" } });
  });

  test("does not leave a .tmp file behind", () => {
    const dir = mkdtempSync(join(tmpdir(), "review-decision-"));
    const path = join(dir, "review-decision.json");

    writeReviewDecision(path, { decision: "approve", comments: {} });

    expect(() => readFileSync(`${path}.tmp`, "utf-8")).toThrow();
  });
});
```

(Remove any existing tests for `parseReviewPendingLine`/`ReviewPendingMessage` from this file.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /c/coding/pi-agent-factory/pi-ext/factory-watch && npm test -- review-protocol`
Expected: FAIL (`reviewDecisionPath` doesn't exist; `writeReviewDecision`'s old signature takes a stream, not a path).

- [ ] **Step 3: Implement**

Replace `pi-ext/factory-watch/src/review-protocol.ts`'s contents entirely with:

```typescript
import { mkdirSync, renameSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";

export interface ReviewDecisionPayload {
  decision: "approve" | "reject";
  comments: Record<string, string>;
}

export function reviewDecisionPath(cwd: string, sessionId: string): string {
  return join(cwd, "sessions", ".factory-transcripts", sessionId, "review-decision.json");
}

export function writeReviewDecision(path: string, decision: ReviewDecisionPayload): void {
  mkdirSync(dirname(path), { recursive: true });
  const tmpPath = `${path}.tmp`;
  writeFileSync(tmpPath, JSON.stringify(decision), "utf-8");
  renameSync(tmpPath, path);
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /c/coding/pi-agent-factory/pi-ext/factory-watch && npm run typecheck && npm test -- review-protocol`
Expected: PASS. `npm run typecheck` will show errors in `index.ts` (it still imports `parseReviewPendingLine` and calls the old `writeReviewDecision(child.stdin, ...)` signature) — that's expected and fixed in Task 3; do not touch `index.ts` in this task.

- [ ] **Step 5: Commit**

```bash
git add pi-ext/factory-watch/src/review-protocol.ts pi-ext/factory-watch/test/review-protocol.test.ts
git commit -m "feat(factory-watch): writeReviewDecision targets a file, not a stream"
```

---

### Task 3: `index.ts`'s `launchInteractiveReview` — closed stdio + status polling

**Files:**
- Modify: `pi-ext/factory-watch/src/index.ts`
- Test: `pi-ext/factory-watch/test/handler.test.ts` (extend — read it first, especially the fake-timers test at `"/factory's poll loop stops instead of crashing once ctx goes stale"` for the `vi.useFakeTimers()`/`vi.advanceTimersByTime()` convention this task's tests should follow)

**Interfaces:**
- Consumes: `reviewDecisionPath`/`writeReviewDecision` (Task 2), `parseStatus`/`StatusRecord`/`PipelineEntry` (existing, `status-format.ts` — note `PipelineEntry.start_commit?: string | null` and `StatusRecord.session_id: string`, `StatusRecord.pipeline: PipelineEntry[]`, `StatusRecord.task_id: string` already exist from Increment 1; read `status-format.ts` to confirm exact field names before writing this task's code).
- Produces: `launchInteractiveReview` spawns the orchestrator with fully closed stdio, detects the human-review block via status-file polling (not stdout), and writes the resulting decision to `reviewDecisionPath(...)`.

- [ ] **Step 1: Write the failing tests**

Read `pi-ext/factory-watch/src/index.ts`'s current `launchInteractiveReview` in full first (it hasn't changed since it was last read for this plan, but confirm). Read `test/handler.test.ts`'s existing conventions (`capture()`, `fakeCtx()`, the `spawn` mock returning an `EventEmitter`, and the fake-timers test referenced above).

Add to `test/handler.test.ts` (adapt to the file's real fixture helpers — this is the required behavior, not literal copy-paste):

```typescript
test("/factory-run (interactive) spawns the orchestrator with fully closed stdio", async () => {
  vi.mocked(spawnSync).mockReturnValue({
    status: 0, stdout: JSON.stringify([{ id: "T-001", title: "t", status: "todo" }]), stderr: "",
  } as ReturnType<typeof spawnSync>);
  const child = new EventEmitter() as EventEmitter & { unref: () => void };
  child.unref = () => {};
  vi.mocked(spawn).mockReturnValue(child as unknown as ReturnType<typeof spawn>);
  const { commands } = capture();
  const ctx = fakeCtx();

  const handlerPromise = commands.get("factory-run")!.handler("T-001", ctx);
  await Promise.resolve();
  child.emit("exit");
  await handlerPromise;

  expect(vi.mocked(spawn)).toHaveBeenCalledWith(
    expect.any(String), expect.any(Array),
    expect.objectContaining({ stdio: ["ignore", "ignore", "ignore"] }),
  );
});

test("/factory-run (interactive) detects a blocked human-review via the status file and writes the decision to a file, not the child's stdin", async () => {
  // Read the file's real conventions for stubbing readFileSync/fs (e.g. an
  // existing mock or a real tmp status file via ctx.cwd pointed at a tmpdir)
  // and follow that pattern rather than inventing a new one. Required
  // behavior: with a status file whose pipeline contains
  // { node: "human-review", node_state: "blocked", start_commit: "abc123" }
  // and top-level task_id/session_id set, advancing the poll timer causes
  // runReviewLoop (mocked) to be called with (ctx.ui, ctx.cwd, task_id,
  // "abc123", <computeReviewFiles's mocked return>), and its resolved
  // decision to be passed to writeReviewDecision(reviewDecisionPath(ctx.cwd,
  // session_id), decision) -- NOT written to child.stdin (there is no
  // child.stdin to write to; stdio is fully "ignore").
  // Use vi.useFakeTimers()/vi.advanceTimersByTime() as the existing
  // "/factory's poll loop stops instead of crashing" test does, wrapped in
  // try/finally with vi.useRealTimers().
});

test("/factory-run (interactive) does not launch a second review loop for the same task while one is already in flight", async () => {
  // Required behavior: two consecutive poll ticks that both see the same
  // blocked human-review task_id must result in exactly ONE runReviewLoop
  // call, not two.
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /c/coding/pi-agent-factory/pi-ext/factory-watch && npm test -- handler`
Expected: FAIL (`spawn` still called with piped stdio; no status-polling logic exists yet).

- [ ] **Step 3: Implement**

In `pi-ext/factory-watch/src/index.ts`, replace the import line:

```typescript
import { parseReviewPendingLine, writeReviewDecision } from "./review-protocol.js";
```

with:

```typescript
import { reviewDecisionPath, writeReviewDecision } from "./review-protocol.js";
```

Replace `launchInteractiveReview`'s body:

```typescript
  async function launchInteractiveReview(ctx: ExtCommandCtx, cmd: Command, label: string): Promise<void> {
    const child = spawn(cmd.bin, cmd.args, { cwd: ctx.cwd, detached: true, stdio: ["ignore", "ignore", "ignore"] });
    ctx.ui.notify(`factory started (${label}, human review on)`, "info");

    const statusPath = join(ctx.cwd, STATUS_FILE);
    let reviewInFlightForTask: string | null = null;

    const reviewPoll = setInterval(() => {
      // Same staleness guard as launchAndWatch's poll loop -- ctx.ui can
      // throw after a session replacement/reload; stop polling rather than
      // crashing the whole host process on the next tick.
      try {
        const raw = readFileIfExists(statusPath);
        const record = raw === null ? null : parseStatus(raw);
        if (record === null) {
          return;
        }
        const hrEntry = record.pipeline.find((e) => e.node === "human-review");
        if (
          hrEntry !== undefined &&
          hrEntry.node_state === "blocked" &&
          typeof hrEntry.start_commit === "string" &&
          reviewInFlightForTask !== record.task_id
        ) {
          const startCommit = hrEntry.start_commit;
          const taskId = record.task_id;
          const sessionId = record.session_id;
          reviewInFlightForTask = taskId;
          const files = computeReviewFiles(ctx.cwd, startCommit);
          void runReviewLoop(ctx.ui, ctx.cwd, taskId, startCommit, files).then((decision) => {
            writeReviewDecision(reviewDecisionPath(ctx.cwd, sessionId), decision);
          });
        }
      } catch {
        clearInterval(reviewPoll);
      }
    }, POLL_INTERVAL_MS);

    await new Promise<void>((resolve) => child.on("exit", () => resolve()));
    clearInterval(reviewPoll);
    ctx.ui.notify("factory run finished", "info");
  }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /c/coding/pi-agent-factory/pi-ext/factory-watch && npm run typecheck && npm test`
Expected: PASS (full suite — this changes shared code and removes `parseReviewPendingLine`, so a narrow target risks missing a stale reference elsewhere).

- [ ] **Step 5: Commit**

```bash
git add pi-ext/factory-watch/src/index.ts pi-ext/factory-watch/test/handler.test.ts
git commit -m "feat(factory-watch): launchInteractiveReview detects review via status polling, writes decision to a file"
```

---

### Task 4: Editor-spawn helpers in `mission-control-review.ts`

**Files:**
- Modify: `pi-ext/factory-watch/src/review-overlay.ts` (export `hasCodeOnPath`)
- Modify: `pi-ext/factory-watch/src/mission-control-review.ts`
- Test: `pi-ext/factory-watch/test/mission-control-review.test.ts` (extend)

**Interfaces:**
- Produces: `launchFileEditor(cwd: string, filePath: string): { ok: true } | { ok: false; error: string }` and `promptComment(cwd: string, currentText: string | undefined): { ok: true; text: string | undefined } | { ok: false; error: string }`, both exported from `mission-control-review.ts`. Both reuse `resolveEditorLaunch` (already exists in `review-editor-launch.ts`) and the exported `hasCodeOnPath` from `review-overlay.ts`.
- `promptComment` writes `currentText` (or `""`) to a temp file, blocks on the same editor-spawn mechanism `runReviewLoop`'s "edit" action already uses (including the tmux-split-and-wait dance when `plan.useTmux`), reads the file back afterward, deletes the temp file, and returns `{ ok: true, text: undefined }` if the result is empty/whitespace-only (matching "no comment" semantics) or `{ ok: true, text: <trimmed content> }` otherwise.

- [ ] **Step 1: Write the failing tests**

In `pi-ext/factory-watch/src/review-overlay.ts`, first change:

```typescript
function hasCodeOnPath(platform: NodeJS.Platform = process.platform): boolean {
```

to:

```typescript
export function hasCodeOnPath(platform: NodeJS.Platform = process.platform): boolean {
```

(Purely an export addition — no behavior change. Run `cd /c/coding/pi-agent-factory/pi-ext/factory-watch && npm test -- review-overlay` afterward to confirm its existing 18 tests are unaffected before continuing.)

Then, read `pi-ext/factory-watch/test/review-overlay.test.ts` for how it mocks `spawnSync`/`resolveEditorLaunch` for the "edit" action (if it does), and mirror that convention. Add to `pi-ext/factory-watch/test/mission-control-review.test.ts`:

```typescript
import { spawnSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";

vi.mock("node:child_process", async (importOriginal) => {
  const actual = await importOriginal<typeof import("node:child_process")>();
  return { ...actual, spawnSync: vi.fn() };
});

describe("launchFileEditor", () => {
  test("spawns the resolved editor on the given file and reports success", () => {
    vi.mocked(spawnSync).mockReturnValue({ status: 0 } as ReturnType<typeof spawnSync>);
    // Force a deterministic editor resolution for this test: set $VISUAL to
    // a non-terminal command so resolveEditorLaunch's fast path is used
    // without depending on the real machine having `code` on PATH.
    const prevVisual = process.env.VISUAL;
    process.env.VISUAL = "myeditor";
    try {
      const result = launchFileEditor("/repo", "/repo/src/a.ts");
      expect(result).toEqual({ ok: true });
      expect(spawnSync).toHaveBeenCalledWith(
        "myeditor", ["/repo/src/a.ts"], { cwd: "/repo", stdio: "ignore" },
      );
    } finally {
      if (prevVisual === undefined) delete process.env.VISUAL; else process.env.VISUAL = prevVisual;
    }
  });

  test("returns an error result when no editor can be resolved", () => {
    const prevVisual = process.env.VISUAL;
    const prevEditor = process.env.EDITOR;
    delete process.env.VISUAL;
    delete process.env.EDITOR;
    try {
      // On a machine with `code` on PATH this test's premise (no resolvable
      // editor) may not hold -- read resolveEditorLaunch's real fallback
      // order (VISUAL/EDITOR -> code -> win32 notepad -> error) and adapt
      // this test's env/platform stubbing so the "no editor" branch is
      // actually reached deterministically, following whatever pattern
      // review-overlay.test.ts already uses to test this same "no editor"
      // case for the "edit" action, if it does.
    } finally {
      if (prevVisual === undefined) delete process.env.VISUAL; else process.env.VISUAL = prevVisual;
      if (prevEditor === undefined) delete process.env.EDITOR; else process.env.EDITOR = prevEditor;
    }
  });
});

describe("promptComment", () => {
  test("writes currentText to a temp file, spawns the editor, and returns the edited content", () => {
    const prevVisual = process.env.VISUAL;
    process.env.VISUAL = "myeditor";
    vi.mocked(spawnSync).mockImplementation((_cmd, args) => {
      // Simulate the user editing the temp file: args[0] is the temp path.
      writeFileSync((args as string[])[0]!, "new comment text\n", "utf-8");
      return { status: 0 } as ReturnType<typeof spawnSync>;
    });
    try {
      const result = promptComment("/repo", "old text");
      expect(result).toEqual({ ok: true, text: "new comment text" });
    } finally {
      if (prevVisual === undefined) delete process.env.VISUAL; else process.env.VISUAL = prevVisual;
    }
  });

  test("returns text: undefined when the edited content is empty or whitespace-only", () => {
    const prevVisual = process.env.VISUAL;
    process.env.VISUAL = "myeditor";
    vi.mocked(spawnSync).mockImplementation((_cmd, args) => {
      writeFileSync((args as string[])[0]!, "   \n", "utf-8");
      return { status: 0 } as ReturnType<typeof spawnSync>;
    });
    try {
      const result = promptComment("/repo", undefined);
      expect(result).toEqual({ ok: true, text: undefined });
    } finally {
      if (prevVisual === undefined) delete process.env.VISUAL; else process.env.VISUAL = prevVisual;
    }
  });
});
```

(These are required behaviors and a reasonable literal shape, but adapt the env-stubbing/mocking specifics to whatever convention `review-overlay.test.ts` already established for testing the "edit" action, if it tests it directly, rather than inventing a divergent style.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /c/coding/pi-agent-factory/pi-ext/factory-watch && npm test -- mission-control-review`
Expected: FAIL (`launchFileEditor`/`promptComment` don't exist yet).

- [ ] **Step 3: Implement**

In `pi-ext/factory-watch/src/mission-control-review.ts`, add imports:

```typescript
import { randomUUID } from "node:crypto";
import { spawnSync } from "node:child_process";
import { readFileSync, unlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { resolveEditorLaunch } from "./review-editor-launch.ts";
import { hasCodeOnPath } from "./review-overlay.ts";
```

Add the helpers (place above `ReviewBrowser`):

```typescript
function spawnEditorBlocking(cwd: string, filePath: string): { ok: true } | { ok: false; error: string } {
  const plan = resolveEditorLaunch(process.env, hasCodeOnPath());
  if (!plan.ok) {
    return { ok: false, error: plan.error };
  }
  if (plan.useTmux) {
    const signal = `review-edit-${Date.now()}`;
    spawnSync(
      "tmux",
      ["split-window", "-h", `${plan.command} ${filePath}; tmux wait-for -S ${signal}`],
      { cwd },
    );
    spawnSync("tmux", ["wait-for", signal], { cwd });
  } else {
    spawnSync(plan.command, [...plan.args, filePath], { cwd, stdio: "ignore" });
  }
  return { ok: true };
}

export function launchFileEditor(cwd: string, filePath: string): { ok: true } | { ok: false; error: string } {
  return spawnEditorBlocking(cwd, filePath);
}

export function promptComment(
  cwd: string,
  currentText: string | undefined,
): { ok: true; text: string | undefined } | { ok: false; error: string } {
  const tmpPath = join(tmpdir(), `review-comment-${randomUUID()}.md`);
  writeFileSync(tmpPath, currentText ?? "", "utf-8");
  const result = spawnEditorBlocking(cwd, tmpPath);
  if (!result.ok) {
    unlinkSync(tmpPath);
    return result;
  }
  const text = readFileSync(tmpPath, "utf-8");
  unlinkSync(tmpPath);
  return { ok: true, text: text.trim() === "" ? undefined : text.trim() };
}
```

(`join` from `node:path` is already imported in this file for other purposes — check the current import list and add it if it isn't.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /c/coding/pi-agent-factory/pi-ext/factory-watch && npm run typecheck && npm test -- mission-control-review review-overlay`
Expected: PASS (review-overlay's existing 18 tests unaffected; new tests pass).

- [ ] **Step 5: Commit**

```bash
git add pi-ext/factory-watch/src/review-overlay.ts pi-ext/factory-watch/src/mission-control-review.ts pi-ext/factory-watch/test/mission-control-review.test.ts
git commit -m "feat(factory-watch): editor-spawn helpers for mission control's comment/edit actions"
```

---

### Task 5: `ConfirmPrompt` component

**Files:**
- Create: `pi-ext/factory-watch/src/confirm-prompt.ts`
- Test: `pi-ext/factory-watch/test/confirm-prompt.test.ts`

**Interfaces:**
- Produces: `ConfirmPrompt` (implements pi-tui's `Component`): `constructor(title: string, message: string, onDecide: (confirmed: boolean) => void)`; `render(width): string[]` shows title, message, and a "y confirm  n/Esc cancel" footer; `handleInput(data)` calls `onDecide(true)` on `y`/Enter, `onDecide(false)` on `n`/Escape, ignores everything else; `invalidate(): void` is a no-op (required, non-optional, by pi-tui's `Component` interface — matches the established pattern in `mission-control-dashboard.ts`/`mission-control-review.ts`'s `ReviewBrowser`).

- [ ] **Step 1: Write the failing tests**

```typescript
// pi-ext/factory-watch/test/confirm-prompt.test.ts
import { describe, expect, test, vi } from "vitest";
import { ConfirmPrompt } from "../src/confirm-prompt.ts";

describe("ConfirmPrompt", () => {
  test("renders the title and message", () => {
    const prompt = new ConfirmPrompt("Approve task?", "T-001: mark this task done?", () => {});
    const lines = prompt.render(80).join("\n");
    expect(lines).toContain("Approve task?");
    expect(lines).toContain("T-001: mark this task done?");
  });

  test("'y' confirms", () => {
    const onDecide = vi.fn();
    new ConfirmPrompt("t", "m", onDecide).handleInput("y");
    expect(onDecide).toHaveBeenCalledWith(true);
  });

  test("Enter confirms", () => {
    const onDecide = vi.fn();
    new ConfirmPrompt("t", "m", onDecide).handleInput("\r");
    expect(onDecide).toHaveBeenCalledWith(true);
  });

  test("'n' cancels", () => {
    const onDecide = vi.fn();
    new ConfirmPrompt("t", "m", onDecide).handleInput("n");
    expect(onDecide).toHaveBeenCalledWith(false);
  });

  test("Escape cancels", () => {
    const onDecide = vi.fn();
    new ConfirmPrompt("t", "m", onDecide).handleInput("\x1b");
    expect(onDecide).toHaveBeenCalledWith(false);
  });

  test("other keys are ignored", () => {
    const onDecide = vi.fn();
    new ConfirmPrompt("t", "m", onDecide).handleInput("x");
    expect(onDecide).not.toHaveBeenCalled();
  });

  test("invalidate is a safe no-op", () => {
    const prompt = new ConfirmPrompt("t", "m", () => {});
    expect(() => prompt.invalidate()).not.toThrow();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /c/coding/pi-agent-factory/pi-ext/factory-watch && npm test -- confirm-prompt`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement**

```typescript
// pi-ext/factory-watch/src/confirm-prompt.ts
import type { Component } from "@earendil-works/pi-tui";

export class ConfirmPrompt implements Component {
  private readonly title: string;
  private readonly message: string;
  private readonly onDecide: (confirmed: boolean) => void;

  constructor(title: string, message: string, onDecide: (confirmed: boolean) => void) {
    this.title = title;
    this.message = message;
    this.onDecide = onDecide;
  }

  // No cached render state -- required (non-optional) by pi-tui's Component
  // interface so this can be passed to tui.addChild()/tui.setFocus().
  invalidate(): void {}

  handleInput(data: string): void {
    if (data === "y" || data === "\r" || data === "\n") {
      this.onDecide(true);
    } else if (data === "n" || data === "\x1b") {
      this.onDecide(false);
    }
  }

  render(_width: number): string[] {
    return [this.title, "", this.message, "", "y confirm  n/Esc cancel"];
  }
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /c/coding/pi-agent-factory/pi-ext/factory-watch && npm run typecheck && npm test -- confirm-prompt`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pi-ext/factory-watch/src/confirm-prompt.ts pi-ext/factory-watch/test/confirm-prompt.test.ts
git commit -m "feat(factory-watch): ConfirmPrompt component for approve/reject confirmation"
```

---

### Task 6: `ReviewBrowser` gains a real decision loop

**Files:**
- Modify: `pi-ext/factory-watch/src/mission-control-review.ts`
- Test: `pi-ext/factory-watch/test/mission-control-review.test.ts` (extend — several existing tests construct `ReviewBrowser`/call `buildReviewArgs` with the OLD shapes; update them to the new required args rather than leaving them stale)

**Interfaces:**
- Consumes: `promptComment`/`launchFileEditor` (Task 4), `ConfirmPrompt` (Task 5), `writeReviewDecision`/`reviewDecisionPath` (Task 2), `ReviewAction`/`ReviewDecisionResult`-shaped payload (`review-overlay.ts`'s existing `ReviewAction` type; the payload written matches `ReviewDecisionPayload` from `review-protocol.ts`).
- Produces: `ReviewBrowser`'s constructor becomes `(files: FileStat[], tui: TuiLike, cwd: string, startCommit: string, taskId: string, onDecision: (decision: ReviewDecisionPayload) => void)`. `buildReviewArgs` gains required `taskId`/`sessionId` fields on `ReviewArgs`. `main()` wires the new constructor args and calls `writeReviewDecision(reviewDecisionPath(cwd, sessionId), decision)` then `process.exit(0)` on a confirmed decision.

- [ ] **Step 1: Write the failing tests**

Read the current `pi-ext/factory-watch/test/mission-control-review.test.ts` in full (Tasks 4 already extended it) and update the EXISTING `ReviewBrowser`/`buildReviewArgs` tests to the new required shape, then add new ones:

```typescript
// buildReviewArgs: update existing "both flags present" test and the two
// "missing" tests to also supply/omit --task-id and --session-id, e.g.:
test("all four flags present returns parsed args", () => {
  expect(
    buildReviewArgs([
      "node", "mission-control-review.ts",
      "--cwd", "/repo", "--start-commit", "abc123",
      "--task-id", "T-001", "--session-id", "s1",
    ]),
  ).toEqual({ cwd: "/repo", startCommit: "abc123", taskId: "T-001", sessionId: "s1" });
});

test("missing --task-id returns undefined", () => {
  expect(
    buildReviewArgs(["node", "mission-control-review.ts", "--cwd", "/repo", "--start-commit", "abc123", "--session-id", "s1"]),
  ).toBeUndefined();
});

test("missing --session-id returns undefined", () => {
  expect(
    buildReviewArgs(["node", "mission-control-review.ts", "--cwd", "/repo", "--start-commit", "abc123", "--task-id", "T-001"]),
  ).toBeUndefined();
});

// ReviewBrowser: update every existing `new ReviewBrowser(FILES, {...}, "/repo", "abc123")`
// call site to the new 6-arg constructor, e.g.
// `new ReviewBrowser(FILES, { terminal: { rows: 24 } }, "/repo", "abc123", "T-001", () => {})`.

describe("ReviewBrowser decision flow", () => {
  test("approve shows a ConfirmPrompt, and confirming it calls onDecision with the approve payload", () => {
    const onDecision = vi.fn();
    const browser = new ReviewBrowser(FILES, { terminal: { rows: 24 } }, "/repo", "abc123", "T-001", onDecision);
    browser.handleInput("a");
    expect(browser.render(80).join("\n")).toContain("Approve task?");
    browser.handleInput("y");
    expect(onDecision).toHaveBeenCalledWith({ decision: "approve", comments: {} });
  });

  test("reject without any comments shows an inline error instead of a confirm prompt", () => {
    const onDecision = vi.fn();
    const browser = new ReviewBrowser(FILES, { terminal: { rows: 24 } }, "/repo", "abc123", "T-001", onDecision);
    browser.handleInput("r");
    expect(browser.render(80).join("\n")).toContain("reject requires at least one comment");
    expect(onDecision).not.toHaveBeenCalled();
  });

  test("cancelling a confirm prompt (n) returns to browsing without calling onDecision", () => {
    const onDecision = vi.fn();
    const browser = new ReviewBrowser(FILES, { terminal: { rows: 24 } }, "/repo", "abc123", "T-001", onDecision);
    browser.handleInput("a");
    browser.handleInput("n");
    expect(onDecision).not.toHaveBeenCalled();
    expect(browser.render(80).join("\n")).toContain("2 files changed");
  });
});
```

(Note: the "reject with a comment" happy-path and the "comment"/"edit" action tests need `promptComment`/`launchFileEditor` mocked — read how Task 4's tests mock `spawnSync`/env vars and reuse that convention, or mock `promptComment`/`launchFileEditor` directly via `vi.mock` at the module boundary if `ReviewBrowser` calls them as free functions in the same module. Write at least one test confirming that after a successful `promptComment` result, `comments.size > 0` and a subsequent `reject` reaches the `ConfirmPrompt` instead of the inline error.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /c/coding/pi-agent-factory/pi-ext/factory-watch && npm test -- mission-control-review`
Expected: FAIL (old constructor arity, `buildReviewArgs` missing fields, no confirm-prompt behavior).

- [ ] **Step 3: Implement**

In `pi-ext/factory-watch/src/mission-control-review.ts`, update imports to add:

```typescript
import { ConfirmPrompt } from "./confirm-prompt.ts";
import { reviewDecisionPath, writeReviewDecision } from "./review-protocol.ts";
import type { ReviewDecisionPayload } from "./review-protocol.ts";
import type { ReviewAction } from "./review-overlay.ts";
```

Update `ReviewArgs` and `buildReviewArgs`:

```typescript
export interface ReviewArgs {
  cwd: string;
  startCommit: string;
  taskId: string;
  sessionId: string;
}

export function buildReviewArgs(argv: string[]): ReviewArgs | undefined {
  const cwdArgIndex = argv.indexOf("--cwd");
  const cwd = cwdArgIndex === -1 ? undefined : argv[cwdArgIndex + 1];
  const startCommitArgIndex = argv.indexOf("--start-commit");
  const startCommit = startCommitArgIndex === -1 ? undefined : argv[startCommitArgIndex + 1];
  const taskIdArgIndex = argv.indexOf("--task-id");
  const taskId = taskIdArgIndex === -1 ? undefined : argv[taskIdArgIndex + 1];
  const sessionIdArgIndex = argv.indexOf("--session-id");
  const sessionId = sessionIdArgIndex === -1 ? undefined : argv[sessionIdArgIndex + 1];
  if (cwd === undefined || startCommit === undefined || taskId === undefined || sessionId === undefined) {
    return undefined;
  }
  return { cwd, startCommit, taskId, sessionId };
}
```

Replace the `ReviewBrowser` class:

```typescript
export class ReviewBrowser implements Component {
  private readonly overlay: ReviewOverlay;
  private readonly comments = new Map<string, string>();
  private readonly cwd: string;
  private readonly taskId: string;
  private readonly onDecision: (decision: ReviewDecisionPayload) => void;
  private activePrompt: ConfirmPrompt | null = null;
  private statusMessage: string | null = null;

  constructor(
    files: FileStat[],
    tui: TuiLike,
    cwd: string,
    startCommit: string,
    taskId: string,
    onDecision: (decision: ReviewDecisionPayload) => void,
  ) {
    this.cwd = cwd;
    this.taskId = taskId;
    this.onDecision = onDecision;
    this.overlay = new ReviewOverlay(files, this.comments, tui, cwd, startCommit, (action) =>
      this.handleAction(action),
    );
  }

  invalidate(): void {}

  private handleAction(action: ReviewAction): void {
    this.statusMessage = null;

    if (action.type === "comment") {
      const result = promptComment(this.cwd, this.comments.get(action.file));
      if (!result.ok) {
        this.statusMessage = result.error;
        return;
      }
      if (result.text === undefined) {
        this.comments.delete(action.file);
      } else {
        this.comments.set(action.file, result.text);
      }
      return;
    }

    if (action.type === "edit") {
      const result = launchFileEditor(this.cwd, action.file);
      if (!result.ok) {
        this.statusMessage = result.error;
      }
      return;
    }

    if (action.type === "reject" && this.comments.size === 0) {
      this.statusMessage = "reject requires at least one comment";
      return;
    }

    const title = action.type === "approve" ? "Approve task?" : "Reject task?";
    const message =
      action.type === "approve"
        ? `${this.taskId}: mark this task done?`
        : `${this.taskId}: send back for another dev iteration?`;
    this.activePrompt = new ConfirmPrompt(title, message, (confirmed) => {
      this.activePrompt = null;
      if (!confirmed) {
        return;
      }
      this.onDecision({ decision: action.type, comments: Object.fromEntries(this.comments) });
    });
  }

  handleInput(data: string): void {
    if (this.activePrompt !== null) {
      this.activePrompt.handleInput(data);
      return;
    }
    this.overlay.handleInput(data);
  }

  render(width: number): string[] {
    if (this.activePrompt !== null) {
      return this.activePrompt.render(width);
    }
    const lines = this.overlay.render(width);
    return this.statusMessage === null ? lines : [...lines, "", this.statusMessage];
  }
}
```

Update `main()`:

```typescript
async function main(): Promise<void> {
  const { ProcessTerminal, TUI } = await import("@earendil-works/pi-tui");
  const args = buildReviewArgs(process.argv);
  if (args === undefined) {
    console.error(
      "usage: node mission-control-review.js --cwd <repo-root> --start-commit <sha> --task-id <id> --session-id <id>",
    );
    process.exit(1);
  }
  const { cwd, startCommit, taskId, sessionId } = args;

  const terminal = new ProcessTerminal();
  const tui = new TUI(terminal);
  const files = computeReviewFiles(cwd, startCommit);
  const browser = new ReviewBrowser(files, { terminal: { rows: terminal.rows } }, cwd, startCommit, taskId, (decision) => {
    writeReviewDecision(reviewDecisionPath(cwd, sessionId), decision);
    process.exit(0);
  });
  tui.addChild(browser);
  tui.setFocus(browser);
  tui.start();
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /c/coding/pi-agent-factory/pi-ext/factory-watch && npm run typecheck && npm test`
Expected: PASS (full suite — the `ReviewBrowser`/`buildReviewArgs` signature changes could affect other call sites; a narrow target risks missing one).

- [ ] **Step 5: Commit**

```bash
git add pi-ext/factory-watch/src/mission-control-review.ts pi-ext/factory-watch/test/mission-control-review.test.ts
git commit -m "feat(factory-watch): ReviewBrowser gains a real approve/reject decision flow"
```

---

### Task 7: Wire the dashboard's `openReviewBrowser` to the new required args

**Files:**
- Modify: `pi-ext/factory-watch/src/mission-control-dashboard.ts`
- Test: `pi-ext/factory-watch/test/mission-control-dashboard.test.ts` (extend)

**Interfaces:**
- Consumes: `ReviewArgs`'s new required `--task-id`/`--session-id` flags (Task 6).
- Produces: `openReviewBrowser` passes `"--task-id", this.record.task_id, "--session-id", this.record.session_id` alongside the existing `--cwd`/`--start-commit` args when spawning `mission-control-review.ts`.

- [ ] **Step 1: Write the failing test**

Read the current `mission-control-dashboard.ts`'s `openReviewBrowser` and its existing test(s) for the human-review dispatch (from Increment 1) first. Extend `mission-control-dashboard.test.ts`:

```typescript
test("Enter on human-review passes --task-id and --session-id to mission-control-review.ts", () => {
  const record: StatusRecord = {
    session_id: "s1", task_id: "T-029", current_node: "human-review", current_state: "blocked",
    pipeline: [
      { node: "human-review", node_state: "blocked", attempt: 1, max_attempts: 1, snippet: "", outcome: null, handoff: null, start_commit: "abc123", updated_at: "2026-07-24T00:00:00Z" },
    ],
    started_at: "2026-07-24T00:00:00Z", updated_at: "2026-07-24T00:00:00Z",
  };
  const dashboard = new MissionControlDashboard(record, "/repo");
  // Navigate to the human-review row and press Enter -- adapt to however
  // the existing Increment-1 human-review dispatch test in this file
  // selects that row and asserts on spawnTerminalWindow's call, and add the
  // --task-id/--session-id assertion to (or alongside) that same pattern.
  expect(vi.mocked(spawnTerminalWindow)).toHaveBeenCalledWith(
    "node",
    expect.arrayContaining(["--task-id", "T-029", "--session-id", "s1"]),
    { cwd: "/repo" },
  );
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /c/coding/pi-agent-factory/pi-ext/factory-watch && npm test -- mission-control-dashboard`
Expected: FAIL (the two new flags aren't passed yet).

- [ ] **Step 3: Implement**

In `pi-ext/factory-watch/src/mission-control-dashboard.ts`, find `openReviewBrowser` and add the two new arguments to the `spawnTerminalWindow` args array (alongside the existing `--cwd`/`--start-commit`), sourcing `taskId` from `this.record.task_id` and `sessionId` from `this.record.session_id` (both already available on `StatusRecord`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /c/coding/pi-agent-factory/pi-ext/factory-watch && npm run typecheck && npm test`
Expected: PASS (full suite — final integration task for this plan).

- [ ] **Step 5: Commit**

```bash
git add pi-ext/factory-watch/src/mission-control-dashboard.ts pi-ext/factory-watch/test/mission-control-dashboard.test.ts
git commit -m "feat(factory-watch): dashboard passes task-id/session-id when opening the review browser"
```

---

## Manual Verification (after all tasks complete)

1. Run a task to the human-review gate via `/factory-run <task>` (no `--auto`). Confirm the mission-control window's human-review row shows `blocked`.
2. Open the human-review row from mission control; comment on a file (confirm your `$EDITOR` opens on a temp file, and the comment persists after closing it); press `r` (reject) — confirm the `ConfirmPrompt` appears, confirm with `y`, and confirm the dev stage picks up the feedback and retries.
3. Repeat step 1 on a fresh task; this time approve (`a` then `y`) from mission control and confirm the task completes.
4. Repeat step 1 on a fresh task, but this time complete the review from the **interactive pi terminal** instead of mission control (the original flow) — confirm it still works exactly as before, now going through the same decision-file mechanism.
5. Confirm `/factory --auto`/`/factory-run --auto` (no human review) are unaffected.
