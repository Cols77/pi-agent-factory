# In-Session Mission Control Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Host mission control inside the pi session as a `ctx.ui.custom` overlay driven by an action-dispatch loop, deleting the standalone second-window machinery.

**Architecture:** `MissionControlDashboard` becomes a pure component that resolves with a typed `MissionControlAction` instead of spawning windows. `/factory-run` runs a loop: open the dashboard overlay (with a live status poll + auto-review in the factory closure) → dispatch the returned action (inspect transcript / gate log / review / quit) → reopen — until quit or run-finished. `pi --session` (an inspect pop-out) is the only surviving spawned window.

**Tech Stack:** TypeScript (pi extension, `node`/`vitest`), pi-tui components.

## Global Constraints

- TS tests: from `pi-ext/factory-watch/`, `npx vitest run <path>`. Typecheck: `npx tsc --noEmit`.
- TDD: failing test first, watch it fail, minimal implementation, watch it pass, commit.
- `.ts` relative-import specifiers for files also loaded via `node <file>.ts` (review-overlay, review-diff, session-path, status-format, mission-control-*); `.js` specifiers for files only under vitest/host (index.ts). Match the file you edit.
- `ctx.ui.custom<T>(factory, opts?)` signature: `factory: (tui, theme, keybindings, done: (result: T) => void) => Component`; resolves to `T` when `done` is called. Overlay is **modal** — one at a time, never nested.
- **ASSUMPTION to verify in manual E2E (§ final):** a `ctx.ui.custom` component can live-update while open by having the factory closure `setInterval`-poll and call `tui.requestRender()`. This is the same TUI API the standalone host uses; if the pi host does not re-render an open custom overlay on `requestRender()`, fall back to re-opening the overlay each poll tick (coarser, but functional). Unit tests mock `ctx.ui.custom`, so they do not exercise this.

---

### Task 1: `MissionControlAction` + dashboard resolves instead of spawning

**Files:**
- Modify: `pi-ext/factory-watch/src/mission-control-dashboard.ts`
- Test: `pi-ext/factory-watch/test/mission-control-dashboard.test.ts`

**Interfaces:**
- Produces:
  ```ts
  export type MissionControlAction =
    | { type: "inspect"; sessionId: string | null }
    | { type: "gate-log" }
    | { type: "review" }
    | { type: "quit" };
  ```
  `new MissionControlDashboard(record: StatusRecord | null, onAction: (a: MissionControlAction) => void)`. Enter on an agent row → `inspect`; on `validation` → `gate-log`; on `human-review` → `review`; `q`/Ctrl-C → `quit`.

- [ ] **Step 1: Rewrite the dashboard tests for action resolution**

Replace the spawn-based tests in `test/mission-control-dashboard.test.ts`. Drop the `spawnTerminalWindow`/`resolveSessionPath` mocks; construct with an `onAction` spy. Keep the render/selection tests (they only lose the `cwd` arg). Representative new tests:

```typescript
import { describe, expect, test, vi } from "vitest";
import { MissionControlDashboard } from "../src/mission-control-dashboard.js";
import type { PipelineEntry, StatusRecord } from "../src/status-format.js";

const RECORD: StatusRecord = {
  session_id: "s1", task_id: "T-029", current_node: "dev", current_state: "running",
  pipeline: [
    { node: "context-gather", node_state: "pass", attempt: 1, max_attempts: 1, snippet: "", outcome: null, handoff: "-> dev", updated_at: "t" },
    { node: "dev", node_state: "running", attempt: 2, max_attempts: 3, snippet: "", outcome: null, handoff: null, updated_at: "t", session_id: "dev-abc" },
  ],
  started_at: "t", updated_at: "t",
};

function withEntry(entry: Partial<PipelineEntry> & { node: string }): StatusRecord {
  const base: PipelineEntry = { node: entry.node, node_state: "pending", attempt: 0, max_attempts: 0, snippet: "", outcome: null, handoff: null, updated_at: "t" };
  return { ...RECORD, pipeline: [...RECORD.pipeline, { ...base, ...entry }] };
}
function down(d: MissionControlDashboard, n: number) { for (let i = 0; i < n; i++) d.handleInput("\x1b[B"); }

test("Enter on an agent row resolves inspect with its sessionId", () => {
  const onAction = vi.fn();
  const d = new MissionControlDashboard(RECORD, onAction);
  down(d, 1); // dev row
  d.handleInput("\r");
  expect(onAction).toHaveBeenCalledWith({ type: "inspect", sessionId: "dev-abc" });
});

test("Enter on validation resolves gate-log", () => {
  const onAction = vi.fn();
  const d = new MissionControlDashboard(RECORD, onAction);
  down(d, 2); // validation row
  d.handleInput("\r");
  expect(onAction).toHaveBeenCalledWith({ type: "gate-log" });
});

test("Enter on human-review resolves review", () => {
  const onAction = vi.fn();
  const d = new MissionControlDashboard(withEntry({ node: "human-review", node_state: "blocked", start_commit: "abc" }), onAction);
  down(d, 4); // human-review row
  d.handleInput("\r");
  expect(onAction).toHaveBeenCalledWith({ type: "review" });
});

test("q and Ctrl-C resolve quit", () => {
  const onAction = vi.fn();
  const d = new MissionControlDashboard(RECORD, onAction);
  d.handleInput("q");
  d.handleInput("\x03");
  expect(onAction).toHaveBeenNthCalledWith(1, { type: "quit" });
  expect(onAction).toHaveBeenNthCalledWith(2, { type: "quit" });
});

test("renders one row per stage with the task header", () => {
  const d = new MissionControlDashboard(RECORD, () => {});
  const lines = d.render(80).join("\n");
  expect(lines).toContain("T-029");
  expect(lines).toContain("context-gatherer");
  expect(lines).toContain("human-review");
});

test("shows a HUMAN REVIEW NEEDED alert when human-review is blocked", () => {
  const d = new MissionControlDashboard(withEntry({ node: "human-review", node_state: "blocked", start_commit: "abc" }), () => {});
  expect(d.render(80).join("\n")).toContain("HUMAN REVIEW NEEDED");
});

test("no alert when human-review is not blocked", () => {
  const d = new MissionControlDashboard(RECORD, () => {});
  expect(d.render(80).join("\n")).not.toContain("HUMAN REVIEW NEEDED");
});
```

- [ ] **Step 2: Run to verify they fail**

Run: `npx vitest run test/mission-control-dashboard.test.ts`
Expected: FAIL — constructor arity / `onAction` undefined / no such behavior.

- [ ] **Step 3: Refactor the component**

Rewrite `mission-control-dashboard.ts` above the standalone `main()` (leave `main()` for Task 4). Remove the `readFileSync`, `resolveSessionPath`, `spawnTerminalWindow` imports (from the component; `main()` still needs `readFileSync`/`parseStatus` until Task 4 — keep those imports for now). New component:

```typescript
import { wrapTextWithAnsi } from "@earendil-works/pi-tui";
import type { Component } from "@earendil-works/pi-tui";
import { formatMissionControlRows } from "./status-format.ts";
import type { StatusRecord } from "./status-format.ts";

const STAGE_ORDER = ["context-gather", "dev", "validation", "review", "human-review"];
const AGENT_NODES = new Set(["context-gather", "dev", "review", "session-review"]);

export type MissionControlAction =
  | { type: "inspect"; sessionId: string | null }
  | { type: "gate-log" }
  | { type: "review" }
  | { type: "quit" };

export class MissionControlDashboard implements Component {
  private selectedIndex = 0;
  private record: StatusRecord | null;
  private readonly onAction: (action: MissionControlAction) => void;

  constructor(record: StatusRecord | null, onAction: (action: MissionControlAction) => void) {
    this.record = record;
    this.onAction = onAction;
  }

  updateRecord(record: StatusRecord | null): void {
    this.record = record;
  }

  invalidate(): void {}

  private handleEnter(): void {
    if (this.record === null) return;
    const row = formatMissionControlRows(this.record, STAGE_ORDER)[this.selectedIndex]!;
    if (AGENT_NODES.has(row.node)) {
      this.onAction({ type: "inspect", sessionId: row.sessionId });
    } else if (row.node === "validation") {
      this.onAction({ type: "gate-log" });
    } else if (row.node === "human-review") {
      this.onAction({ type: "review" });
    }
  }

  handleInput(data: string): void {
    const rows = formatMissionControlRows(this.record, STAGE_ORDER);
    if (data === "\x1b[B" || data === "j") {
      this.selectedIndex = Math.min(this.selectedIndex + 1, rows.length - 1);
    } else if (data === "\x1b[A" || data === "k") {
      this.selectedIndex = Math.max(this.selectedIndex - 1, 0);
    } else if (data === "\r" || data === "\n") {
      this.handleEnter();
    } else if (data === "q" || data === "\x03") {
      this.onAction({ type: "quit" });
    }
  }

  render(width: number): string[] {
    const taskId = this.record?.task_id ?? "(no task)";
    const lines = [`Factory Mission Control — ${taskId}`, ""];
    const hrBlocked = (this.record?.pipeline ?? []).some(
      (e) => e.node === "human-review" && e.node_state === "blocked",
    );
    if (hrBlocked) lines.push("⚠ HUMAN REVIEW NEEDED — select human-review and press Enter", "");
    formatMissionControlRows(this.record, STAGE_ORDER).forEach((row, i) => {
      const prefix = i === this.selectedIndex ? "> " : "  ";
      lines.push(`${prefix}${row.label.padEnd(16)} ${row.state}`);
      if (row.handoff) lines.push(`    ${row.handoff}`);
      if (row.summary) {
        for (const wrapped of wrapTextWithAnsi(row.summary, Math.max(1, width - 4))) lines.push(`    ${wrapped}`);
      }
    });
    lines.push("", "up/down select  Enter open  q close");
    return lines;
  }
}
```

Keep the existing `main()` and its imports below this (unchanged) for now.

- [ ] **Step 4: Run the dashboard tests + typecheck**

Run: `npx vitest run test/mission-control-dashboard.test.ts && npx tsc --noEmit`
Expected: PASS (main() still typechecks against the new constructor — it passes an `onAction`; if `main()` still constructs with the old `(record, cwd, onQuit)` shape, temporarily adapt its call to `new MissionControlDashboard(readRecord(), () => { tui.stop(); process.exit(0); })` so it compiles until Task 4 deletes it).

- [ ] **Step 5: Commit**

```bash
git add pi-ext/factory-watch/src/mission-control-dashboard.ts pi-ext/factory-watch/test/mission-control-dashboard.test.ts
git commit -m "refactor: MissionControlDashboard resolves with a typed action instead of spawning windows"
```

---

### Task 2: Session transcript parser

**Files:**
- Create: `pi-ext/factory-watch/src/session-transcript.ts`
- Test: `pi-ext/factory-watch/test/session-transcript.test.ts`

**Interfaces:**
- Produces: `parseSessionTranscript(jsonl: string): string` — turns a pi session `.jsonl` (one JSON event per line) into readable text: user/assistant text blocks prefixed by role; tool calls as a one-line `> [tool] <name>` summary; unparseable lines skipped.

- [ ] **Step 1: Write the failing test**

Create `test/session-transcript.test.ts`:

```typescript
import { describe, expect, test } from "vitest";
import { parseSessionTranscript } from "../src/session-transcript.js";

const JSONL = [
  JSON.stringify({ type: "session", id: "019f", cwd: "/repo" }),
  JSON.stringify({ type: "message_end", message: { role: "user", content: [{ type: "text", text: "implement T-030" }] } }),
  JSON.stringify({ type: "message_end", message: { role: "assistant", content: [{ type: "text", text: "writing the test first" }, { type: "tool_use", name: "write" }] } }),
  "not json, skip me",
].join("\n");

test("renders user/assistant text with a role prefix", () => {
  const out = parseSessionTranscript(JSONL);
  expect(out).toContain("implement T-030");
  expect(out).toContain("writing the test first");
});

test("summarizes tool calls on one line", () => {
  expect(parseSessionTranscript(JSONL)).toContain("[tool] write");
});

test("skips unparseable lines without throwing", () => {
  expect(() => parseSessionTranscript(JSONL)).not.toThrow();
});

test("empty input yields empty string", () => {
  expect(parseSessionTranscript("")).toBe("");
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `npx vitest run test/session-transcript.test.ts`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement the parser**

Create `src/session-transcript.ts`:

```typescript
interface Block { type?: string; text?: string; name?: string }
interface Message { role?: string; content?: Block[] }
interface Event { type?: string; message?: Message }

export function parseSessionTranscript(jsonl: string): string {
  const out: string[] = [];
  for (const line of jsonl.split("\n")) {
    const trimmed = line.trim();
    if (trimmed === "") continue;
    let ev: Event;
    try {
      ev = JSON.parse(trimmed) as Event;
    } catch {
      continue;
    }
    if (ev.type !== "message_end" || !ev.message) continue;
    const role = ev.message.role ?? "?";
    for (const block of ev.message.content ?? []) {
      if (block.type === "text" && typeof block.text === "string") {
        out.push(`## ${role}`, block.text, "");
      } else if (block.type === "tool_use" && typeof block.name === "string") {
        out.push(`> [tool] ${block.name}`, "");
      }
    }
  }
  return out.join("\n").trimEnd();
}
```

- [ ] **Step 4: Run to verify pass**

Run: `npx vitest run test/session-transcript.test.ts && npx tsc --noEmit`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pi-ext/factory-watch/src/session-transcript.ts pi-ext/factory-watch/test/session-transcript.test.ts
git commit -m "feat: parseSessionTranscript renders a pi session jsonl as readable text"
```

---

### Task 3: Transcript viewer component (scroll + pop-out)

**Files:**
- Create: `pi-ext/factory-watch/src/session-transcript-view.ts`
- Test: `pi-ext/factory-watch/test/session-transcript-view.test.ts`

**Interfaces:**
- Consumes: nothing from earlier tasks (self-contained pi-tui component).
- Produces: `new SessionTranscriptView(lines: string[], tui: { terminal: { rows: number } }, onClose: () => void, onPopOut: () => void)`. Scrolls with arrows/PgUp/PgDn/Home/End (like `ScrollableMarkdown`); `q`/Escape → `onClose`; `o` → `onPopOut`. `render(width)` truncates every line to `width` (per the crash we fixed).

- [ ] **Step 1: Write the failing test**

Create `test/session-transcript-view.test.ts`:

```typescript
import { visibleWidth } from "@earendil-works/pi-tui";
import { describe, expect, test, vi } from "vitest";
import { SessionTranscriptView } from "../src/session-transcript-view.js";

const tui = { terminal: { rows: 10 } };

test("q closes, o pops out", () => {
  const onClose = vi.fn(), onPopOut = vi.fn();
  const v = new SessionTranscriptView(["a", "b"], tui, onClose, onPopOut);
  v.handleInput("q");
  expect(onClose).toHaveBeenCalledTimes(1);
  v.handleInput("o");
  expect(onPopOut).toHaveBeenCalledTimes(1);
});

test("render truncates lines to width and shows a footer", () => {
  const v = new SessionTranscriptView(["x".repeat(200)], tui, () => {}, () => {});
  const lines = v.render(40);
  for (const line of lines) expect(visibleWidth(line)).toBeLessThanOrEqual(40);
  expect(lines[lines.length - 1]).toContain("o open in pi --session");
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `npx vitest run test/session-transcript-view.test.ts`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement the component**

Create `src/session-transcript-view.ts` (mirrors `ScrollableMarkdown`'s scroll math; adds `o`):

```typescript
import { Key, matchesKey, truncateToWidth } from "@earendil-works/pi-tui";
import type { Component } from "@earendil-works/pi-tui";

export interface TuiLike { terminal: { rows: number } }

export class SessionTranscriptView implements Component {
  private scrollOffset = 0;
  private readonly lines: string[];
  private readonly tui: TuiLike;
  private readonly onClose: () => void;
  private readonly onPopOut: () => void;

  constructor(lines: string[], tui: TuiLike, onClose: () => void, onPopOut: () => void) {
    this.lines = lines;
    this.tui = tui;
    this.onClose = onClose;
    this.onPopOut = onPopOut;
  }

  invalidate(): void {}

  private viewportHeight(): number {
    return Math.max(1, this.tui.terminal.rows - 2);
  }

  handleInput(data: string): void {
    const h = this.viewportHeight();
    if (matchesKey(data, Key.down)) this.scrollOffset += 1;
    else if (matchesKey(data, Key.up)) this.scrollOffset -= 1;
    else if (matchesKey(data, Key.pageDown)) this.scrollOffset += h;
    else if (matchesKey(data, Key.pageUp)) this.scrollOffset -= h;
    else if (matchesKey(data, Key.home)) this.scrollOffset = 0;
    else if (matchesKey(data, Key.end)) this.scrollOffset = Number.MAX_SAFE_INTEGER;
    else if (matchesKey(data, Key.escape) || data === "q") this.onClose();
    else if (data === "o") this.onPopOut();
  }

  render(width: number): string[] {
    const h = this.viewportHeight();
    const maxOffset = Math.max(0, this.lines.length - h);
    this.scrollOffset = Math.min(Math.max(0, this.scrollOffset), maxOffset);
    const visible = this.lines.slice(this.scrollOffset, this.scrollOffset + h);
    const last = Math.min(this.scrollOffset + h, this.lines.length);
    const footer = `-- line ${this.scrollOffset + 1}-${last} of ${this.lines.length}  (arrows/PgUp/PgDn/Home/End, q back, o open in pi --session) --`;
    return [...visible, footer].map((line) => truncateToWidth(line, width));
  }
}
```

- [ ] **Step 4: Run to verify pass**

Run: `npx vitest run test/session-transcript-view.test.ts && npx tsc --noEmit`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pi-ext/factory-watch/src/session-transcript-view.ts pi-ext/factory-watch/test/session-transcript-view.test.ts
git commit -m "feat: SessionTranscriptView scroll overlay with a pi --session pop-out"
```

---

### Task 4: `/factory-run` action loop; delete the second-window machinery

**Files:**
- Modify: `pi-ext/factory-watch/src/index.ts` (action loop; delete `launchMissionControl` + the review-poll `setInterval`)
- Modify: `pi-ext/factory-watch/src/mission-control-dashboard.ts` (delete standalone `main()` + bootstrap)
- Test: `pi-ext/factory-watch/test/handler.test.ts`

**Interfaces:**
- Consumes: `MissionControlDashboard` + `MissionControlAction` (Task 1); `parseSessionTranscript` (Task 2); `SessionTranscriptView` (Task 3); existing `resolveSessionPath`, `runReviewLoop`, `computeReviewFiles`, `computeImplementingFiles`, `writeReviewDecision`, `reviewDecisionPath`, `spawnTerminalWindow`, `ScrollableMarkdown`, `getMarkdownTheme`.

- [ ] **Step 1: Write the failing handler tests**

Add to `test/handler.test.ts`. Mock `mission-control-dashboard.js` so the overlay resolves with a scripted action, and assert dispatch. The existing `vi.mock("../src/review-overlay.js")` / `review-diff.js` mocks stay. Representative:

```typescript
// The custom overlay is driven by fakeCtx's ui.custom mock; make it resolve
// with a scripted MissionControlAction, then a quit to end the loop.
test("/factory-run opens the dashboard overlay and dispatches quit without spawning a window", async () => {
  // ui.custom resolves { type: "quit" } on the first dashboard open.
  const ctx = fakeCtx();
  vi.mocked(ctx.ui.custom).mockResolvedValueOnce({ type: "quit" });
  // ... standard spawnSync/spawn child setup as in the other factory-run tests ...
  await commands.get("factory-run")!.handler("T-001", ctx);
  expect(spawnTerminalWindow).not.toHaveBeenCalled();      // no dashboard window
  expect(ctx.ui.custom).toHaveBeenCalled();                // in-session overlay used
});

test("/factory-run dispatches an inspect action to the transcript overlay then reopens", async () => {
  const ctx = fakeCtx();
  vi.mocked(ctx.ui.custom)
    .mockResolvedValueOnce({ type: "inspect", sessionId: "dev-abc" }) // dashboard
    .mockResolvedValueOnce(undefined)                                  // transcript view closes
    .mockResolvedValueOnce({ type: "quit" });                          // dashboard again
  vi.mocked(resolveSessionPath).mockReturnValue("/home/x_dev-abc.jsonl");
  // ... child setup ...
  await commands.get("factory-run")!.handler("T-001", ctx);
  expect(resolveSessionPath).toHaveBeenCalledWith("dev-abc");
  // custom called at least 3x: dashboard, transcript, dashboard
  expect(vi.mocked(ctx.ui.custom).mock.calls.length).toBeGreaterThanOrEqual(3);
});
```

(Model the `spawnSync`/`spawn`/child-exit scaffolding on the existing factory-run tests; add `resolveSessionPath` to the `vi.mock("../src/session-path.js")` list and `custom` to `fakeCtx().ui`.)

- [ ] **Step 2: Run to verify they fail**

Run: `npx vitest run test/handler.test.ts -t "dashboard overlay"`
Expected: FAIL — `launchMissionControl` still spawns a window / no action loop exists.

- [ ] **Step 3: Implement the action loop**

In `index.ts`, replace `launchMissionControl` and the body of `launchInteractiveReview` with a single `runMissionControl` used by the interactive `/factory-run` path. Delete the old `launchMissionControl` function and `launchInteractiveReview`'s separate `reviewPoll` `setInterval`. New helper:

```typescript
import { MissionControlDashboard } from "./mission-control-dashboard.js";
import type { MissionControlAction } from "./mission-control-dashboard.js";
import { parseSessionTranscript } from "./session-transcript.js";
import { SessionTranscriptView } from "./session-transcript-view.js";
import { resolveSessionPath } from "./session-path.js";
import { ScrollableMarkdown } from "./scrollable-markdown.js";
import { getMarkdownTheme } from "@earendil-works/pi-coding-agent";
import { computeImplementingFiles, computeReviewFiles } from "./review-diff.js";

async function runMissionControl(ctx: ExtCommandCtx): Promise<void> {
  const statusPath = join(ctx.cwd, STATUS_FILE);
  const readRecord = () => {
    const raw = readFileIfExists(statusPath);
    return raw === null ? null : parseStatus(raw);
  };

  loop: for (;;) {
    const action = await ctx.ui.custom<MissionControlAction>((tui, _t, _k, done) => {
      const dash = new MissionControlDashboard(readRecord(), (a) => { clearInterval(poll); done(a); });
      // Live update only -- review is Enter-driven, never auto-opened.
      const poll = setInterval(() => {
        dash.updateRecord(readRecord());
        tui.requestRender();
      }, POLL_INTERVAL_MS);
      return dash;
    });

    switch (action.type) {
      case "quit":
        break loop;
      case "inspect": {
        const path = action.sessionId === null ? null : resolveSessionPath(action.sessionId);
        if (path === null) { ctx.ui.notify("session not ready", "info"); break; }
        const text = parseSessionTranscript(readFileIfExists(path) ?? "");
        const lines = text.split("\n");
        await ctx.ui.custom<void>((tui, _t, _k, done) =>
          new SessionTranscriptView(lines, tui, () => done(undefined), () => {
            spawnTerminalWindow("pi", ["--session", path], { cwd: ctx.cwd });
          }), { overlay: true, overlayOptions: { width: "90%", maxHeight: "90%", anchor: "center" } });
        break;
      }
      case "gate-log": {
        const rec = readRecord();
        const logPath = join(ctx.cwd, "sessions", ".factory-transcripts", rec?.session_id ?? "", "sim-gate.log");
        const text = readFileIfExists(logPath) ?? "(no gate log yet)";
        await ctx.ui.custom<void>((tui, _t, _k, done) =>
          new ScrollableMarkdown(text, getMarkdownTheme(), tui, () => done(undefined)),
          { overlay: true, overlayOptions: { width: "90%", maxHeight: "90%", anchor: "center" } });
        break;
      }
      case "review": {
        const rec = readRecord();
        const hr = rec?.pipeline.find((e) => e.node === "human-review");
        if (rec && hr && hr.node_state === "blocked" && typeof hr.start_commit === "string") {
          const alreadyDone = hr.already_done === true;
          const files = alreadyDone ? computeImplementingFiles(ctx.cwd, hr.deliverables ?? []) : computeReviewFiles(ctx.cwd, hr.start_commit);
          const opts = alreadyDone ? { implementing: true, banner: "This task appears already complete -- approve to mark it done, reject to re-run it." } : {};
          const decision = await runReviewLoop(ctx.ui, ctx.cwd, rec.task_id, hr.start_commit, files, opts);
          writeReviewDecision(reviewDecisionPath(ctx.cwd, rec.session_id), decision);
        }
        break;
      }
    }
  }
}
```

Add a **background widget poll** helper (the existing `pollHandle`/`stopPolling`
pattern this file already has for `launchAndWatch`), started by `/factory-run`,
that updates the widget and flags review + finish, independent of whether the
overlay is open:

```typescript
function startBackgroundWidgetPoll(ctx: ExtCommandCtx): void {
  const statusPath = join(ctx.cwd, STATUS_FILE);
  const lockPath = join(ctx.cwd, LOCK_FILE);
  stopPolling();
  pollHandle = setInterval(() => {
    try {
      const raw = readFileIfExists(statusPath);
      const record = raw === null ? null : parseStatus(raw);
      const lines = formatStatusLines(record);
      const hrBlocked = (record?.pipeline ?? []).some((e) => e.node === "human-review" && e.node_state === "blocked");
      if (hrBlocked) lines.push("⚠ human review needed — /factory-watch");
      ctx.ui.setWidget("factory", lines);
      if (readFileIfExists(lockPath) === null) {
        stopPolling();
        ctx.ui.notify("factory run finished", "info");
      }
    } catch {
      stopPolling();
    }
  }, POLL_INTERVAL_MS);
}
```

Wire the interactive `/factory-run` branch: spawn the orchestrator detached with
stdout/stderr to the log (as `launchInteractiveReview` does today) and
`child.unref()`; `startBackgroundWidgetPoll(ctx)`; `await runMissionControl(ctx)`.
Do **not** await child exit — `q` returns you to chat while the run and the
background poll continue. Keep `launchAndWatch` (the `--auto` path) exactly as-is.
Delete the old `launchInteractiveReview` and `launchMissionControl`.

- [ ] **Step 3b: Add the `/factory-watch` command**

Register a new command that re-enters the loop against the current status (no
orchestrator spawn):

```typescript
pi.registerCommand("factory-watch", {
  description: "Open mission control for the current factory run",
  handler: async (_args: string, ctx: ExtCommandCtx) => {
    const statusPath = join(ctx.cwd, STATUS_FILE);
    if (readFileIfExists(statusPath) === null) {
      ctx.ui.notify("no factory run to watch", "info");
      return;
    }
    await runMissionControl(ctx);
  },
});
```

- [ ] **Step 4: Delete the standalone `main()`**

In `mission-control-dashboard.ts`, delete `main()` and the `if (process.argv[1]?.endsWith(...)) void main();` bootstrap, and the now-unused `readFileSync`/`parseStatus`/`ProcessTerminal` imports.

- [ ] **Step 5: Run the handler tests + full suite + typecheck**

Run: `npx vitest run && npx tsc --noEmit`
Expected: PASS. Update any remaining handler tests that asserted `launchMissionControl`/the old review-poll (replace with the action-loop assertions).

- [ ] **Step 6: Commit**

```bash
git add pi-ext/factory-watch/src/index.ts pi-ext/factory-watch/src/mission-control-dashboard.ts pi-ext/factory-watch/test/handler.test.ts
git commit -m "feat: in-session mission control via a ctx.ui.custom action loop; delete the second-window machinery"
```

---

## Final verification

- [ ] **Full TS suite + typecheck:** from `pi-ext/factory-watch/`, `npx vitest run && npx tsc --noEmit` → all pass.
- [ ] **Manual E2E (live — verifies the §Global-Constraints live-update assumption):** in a fresh `pif` session, `/factory-run <task>`:
  - the dashboard appears **in-session** (no new window) and updates live as stages progress;
  - Enter on an agent row shows the read-only transcript; `o` pops out a `pi --session` window; `q` returns;
  - Enter on validation shows the gate log; `q` returns;
  - when human-review blocks, the dashboard shows "HUMAN REVIEW NEEDED"; Enter on that row opens the review (implementing diff + banner for an already-done task); approve/reject works and control returns to the dashboard;
  - `q` closes mission control back to the chat; the status widget still shows progress and flags "human review needed"; `/factory-watch` reopens mission control and Enter services the review.
  - If the dashboard does NOT update live while open, apply the reopen-per-tick fallback noted in Global Constraints.
