# factory-watch Pi Extension Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `factory-watch`, a Pi extension loaded in the user's own interactive `pi` session that launches the factory orchestrator (via `/factory`) using whatever provider/model is already active in that session, renders its live progress from the status file Plan A already produces, and can cancel a running task (`/factory-stop`) without orphaning the sub-agent process.

**Architecture:** A TypeScript Pi extension, same shape as the already-shipped `pi-ext/scope-guard/`: pure, unit-tested functions for everything that doesn't need a live subprocess or Pi's runtime (status/lock file parsing, display formatting, platform-specific kill-command construction), thin wiring in `index.ts` for the actual `pi.registerCommand()` / `ctx.ui.setWidget()` / `child_process.spawn()` calls. Unlike scope-guard's original approach (hand-roll minimal types, discover the drift risk later, fix it in a review round), this extension depends on the real `@earendil-works/pi-coding-agent` package's types from Task 1 and pins its own minimal structural subset against them immediately — applying the lesson from scope-guard's final review up front instead of repeating it.

**Tech Stack:** TypeScript (strict, NodeNext), `vitest` (tests), `@earendil-works/pi-coding-agent` (types only, devDependency — already proven to resolve locally in `pi-ext/scope-guard/`). No new Python code — Plan A's orchestrator is used unmodified.

## Global Constraints

- Runtime target: **Node ≥ 18**, TypeScript **strict** mode, `moduleResolution: "nodenext"`.
- Platform is **Windows 10** (primary dev/target); paths and process control must actually work there, not just assume POSIX semantics.
- **No new IPC mechanism.** Communication with the orchestrator is exclusively via the files Plan A already produces: `sessions/.factory-status.json`, `sessions/.factory-run.lock`. This extension only ever *reads* those files and *launches*/*terminates* the orchestrator process — it never talks to the orchestrator's own sub-agent `pi` processes.
- **`/factory` always uses the session's currently active model** (`ctx.model.provider`/`ctx.model.id`) — no separate configuration, no override flags (per spec §6, deliberately out of scope for v1).
- **No orphaned sub-agent process on cancellation, on either platform** — this is the hard requirement from the spec (§4); the exact mechanism differs by platform and is decided in Task 5 below.
- Every task ends green (`npm run typecheck`, `npm test`) and is committed.

Full design: `docs/superpowers/specs/2026-07-20-factory-live-visualization-design.md`. This plan implements §2, §3.4, §4, and the TypeScript half of §7; §3.1-§3.3 (the status file, streaming backend, PID lock file) are Plan A, already shipped and consumed here unmodified.

## Verified Real API Shapes (from `@earendil-works/pi-coding-agent`, confirmed against the installed package's `.d.ts` files, not assumed)

- `ExtensionContext.model: Model<any> | undefined`, where `Model.id: string` and `Model.provider: Provider` (a string).
- `ExtensionUIContext.notify(message: string, type?: "info" | "warning" | "error"): void` — note: `"warning"`, not `"warn"`.
- `ExtensionUIContext.setStatus(key: string, text: string | undefined): void`.
- `ExtensionUIContext.setWidget(key: string, content: string[] | undefined, options?): void`.
- `ExtensionAPI.registerCommand(name: string, options: Omit<RegisteredCommand, "name" | "sourceInfo">): void`, where `RegisteredCommand.handler: (args: string, ctx: ExtensionCommandContext) => Promise<void>`.
- `ExtensionCommandContext extends ExtensionContext` (adds session-control methods this extension doesn't need).
- Mode behavior (`docs/extensions.md`): in `-p` (print) mode, **extensions and registered commands run**, but `ctx.ui.*` methods are no-ops (they don't throw, they just don't render anything). This means `/factory`'s and `/factory-stop`'s actual *logic* (spawning, file I/O, process control) is verifiable via `pi -p "/factory"` without a real interactive TUI session — only the *visual* widget rendering itself requires an actual interactive session to see (Task 6).

---

## File Structure

```
pi-ext/factory-watch/
  package.json
  tsconfig.json
  vitest.config.ts
  src/
    pi-types.ts            # minimal structural types: PiApi, ExtCommandCtx, UiApi, ModelInfo, CommandDef
    type-compat-check.ts   # pins pi-types.ts against the real @earendil-works/pi-coding-agent types
    status-format.ts       # pure: parse status JSON, compute "Xs ago", format widget display lines
    lock-status.ts         # pure: parse lock JSON, cross-platform PID liveness check
    process-control.ts     # pure: build the orchestrator run command, the Windows kill args
    index.ts                # thin wiring: registerCommand("factory", ...), registerCommand("factory-stop", ...)
  test/
    status-format.test.ts
    lock-status.test.ts
    process-control.test.ts
    handler.test.ts
  README.md
scripts/gates/
  watch_ext.py             # factory gate: runs the extension's typecheck + tests (mirrors scripts/gates/ext.py)
tests/gates/
  test_watch_ext_gate.py   # mirrors tests/gates/test_ext_gate.py
```

---

### Task 1: TypeScript project scaffold

**Files:**
- Create: `pi-ext/factory-watch/package.json`, `pi-ext/factory-watch/tsconfig.json`, `pi-ext/factory-watch/vitest.config.ts`, `pi-ext/factory-watch/src/pi-types.ts`
- Test: `pi-ext/factory-watch/test/smoke.test.ts`

**Interfaces:**
- Consumes: nothing.
- Produces: a buildable/testable TS package; `ModelInfo`, `UiApi`, `ExtCommandCtx`, `CommandDef`, `PiApi` types importable from `src/pi-types.ts`.

- [ ] **Step 1: Write `package.json`**

```json
{
  "name": "@factory/factory-watch",
  "version": "0.0.1",
  "private": true,
  "type": "module",
  "scripts": {
    "typecheck": "tsc --noEmit",
    "test": "vitest run"
  },
  "devDependencies": {
    "@earendil-works/pi-coding-agent": "^0.74.2",
    "@types/node": "^18.19.130",
    "typescript": "^5.5.0",
    "vitest": "^2.0.0"
  }
}
```

- [ ] **Step 2: Write `tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "NodeNext",
    "moduleResolution": "nodenext",
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "types": ["node"]
  },
  "include": ["src", "test"]
}
```

- [ ] **Step 3: Write `vitest.config.ts`**

```typescript
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: { environment: "node", include: ["test/**/*.test.ts"] },
});
```

- [ ] **Step 4: Write `src/pi-types.ts`**

```typescript
// Minimal structural subset of Pi's real ExtensionAPI/ExtensionContext that
// this extension actually uses. Pinned against the real
// @earendil-works/pi-coding-agent package's types by type-compat-check.ts
// (Task 5) so drift is caught at typecheck time, not discovered later.

export interface ModelInfo {
  provider: string;
  id: string;
}

export interface UiApi {
  notify(message: string, type?: "info" | "warning" | "error"): void;
  setStatus(key: string, text: string | undefined): void;
  setWidget(key: string, content: string[] | undefined): void;
}

export interface ExtCommandCtx {
  cwd: string;
  ui: UiApi;
  model: ModelInfo | undefined;
}

export interface CommandDef {
  description?: string;
  handler: (args: string, ctx: ExtCommandCtx) => Promise<void>;
}

export interface PiApi {
  registerCommand(name: string, def: CommandDef): void;
}
```

- [ ] **Step 5: Write the smoke test**

```typescript
// test/smoke.test.ts
import { expect, test } from "vitest";
import type { PiApi } from "../src/pi-types.js";

test("types import and a fake PiApi can register a command", () => {
  const registered: string[] = [];
  const pi: PiApi = {
    registerCommand: (name) => registered.push(name),
  };
  pi.registerCommand("factory", { handler: async () => {} });
  expect(registered).toEqual(["factory"]);
});
```

- [ ] **Step 6: Install and run**

```bash
cd pi-ext/factory-watch
npm install
npm run typecheck
npm test
```
Expected: typecheck clean, `1 passed`.

- [ ] **Step 7: Commit**

```bash
git add pi-ext/factory-watch/package.json pi-ext/factory-watch/tsconfig.json pi-ext/factory-watch/vitest.config.ts pi-ext/factory-watch/src/pi-types.ts pi-ext/factory-watch/test/smoke.test.ts
git commit -m "chore: scaffold factory-watch pi extension (ts + vitest)"
```

---

### Task 2: Status file parsing and display formatting (pure)

**Files:**
- Create: `pi-ext/factory-watch/src/status-format.ts`
- Test: `pi-ext/factory-watch/test/status-format.test.ts`

**Interfaces:**
- Consumes: nothing.
- Produces (all pure, no I/O):
  - `StatusRecord` — the shape Plan A's `FileStatusReporter` writes: `{ session_id, task_id, node, node_state, attempt, max_attempts, snippet, outcome, started_at, updated_at }`.
  - `parseStatus(raw: string): StatusRecord | null` — `null` on malformed/non-object JSON.
  - `secondsAgo(isoTimestamp: string, now?: Date): number`.
  - `formatStatusLines(record: StatusRecord | null, now?: Date): string[]` — the lines to pass to `ctx.ui.setWidget`.

- [ ] **Step 1: Write the failing test**

```typescript
// test/status-format.test.ts
import { describe, expect, test } from "vitest";
import { formatStatusLines, parseStatus, secondsAgo } from "../src/status-format.js";
import type { StatusRecord } from "../src/status-format.js";

const RECORD: StatusRecord = {
  session_id: "2026-07-20T10-15-00Z",
  task_id: "T-001",
  node: "dev",
  node_state: "running",
  attempt: 2,
  max_attempts: 3,
  snippet: "implementing goto()",
  outcome: null,
  started_at: "2026-07-20T10:15:00Z",
  updated_at: "2026-07-20T10:16:42Z",
};

describe("parseStatus", () => {
  test("parses a valid record", () => {
    expect(parseStatus(JSON.stringify(RECORD))).toEqual(RECORD);
  });
  test("returns null for malformed JSON", () => {
    expect(parseStatus("not json")).toBeNull();
  });
  test("returns null for a JSON value that isn't a status object", () => {
    expect(parseStatus("42")).toBeNull();
    expect(parseStatus("null")).toBeNull();
    expect(parseStatus('{"foo": "bar"}')).toBeNull();
  });
});

describe("secondsAgo", () => {
  test("computes elapsed seconds", () => {
    const now = new Date("2026-07-20T10:16:52Z");
    expect(secondsAgo("2026-07-20T10:16:42Z", now)).toBe(10);
  });
  test("never returns negative (clock skew safety)", () => {
    const now = new Date("2026-07-20T10:16:40Z"); // before updated_at
    expect(secondsAgo("2026-07-20T10:16:42Z", now)).toBe(0);
  });
});

describe("formatStatusLines", () => {
  const now = new Date("2026-07-20T10:16:52Z");

  test("shows a waiting message when there's no record yet", () => {
    expect(formatStatusLines(null, now)).toEqual(["factory: waiting for status..."]);
  });

  test("includes task, node, state, attempt, and time-since-update", () => {
    const lines = formatStatusLines(RECORD, now);
    expect(lines[0]).toContain("T-001");
    expect(lines[0]).toContain("dev");
    expect(lines[0]).toContain("running");
    expect(lines.some((l) => l.includes("2/3"))).toBe(true);
    expect(lines.some((l) => l.includes("10s ago"))).toBe(true);
  });

  test("includes the snippet when present", () => {
    const lines = formatStatusLines(RECORD, now);
    expect(lines.some((l) => l.includes("implementing goto()"))).toBe(true);
  });

  test("includes outcome when set, omits it when null", () => {
    const withOutcome = formatStatusLines({ ...RECORD, outcome: "completed" }, now);
    expect(withOutcome.some((l) => l.includes("outcome: completed"))).toBe(true);

    const withoutOutcome = formatStatusLines(RECORD, now);
    expect(withoutOutcome.some((l) => l.includes("outcome:"))).toBe(false);
  });
});
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd pi-ext/factory-watch && npm test
```
Expected: FAIL — `../src/status-format.js` not found.

- [ ] **Step 3: Implement `src/status-format.ts`**

```typescript
export interface StatusRecord {
  session_id: string;
  task_id: string;
  node: string;
  node_state: string;
  attempt: number;
  max_attempts: number;
  snippet: string;
  outcome: string | null;
  started_at: string;
  updated_at: string;
}

function isStatusRecord(value: unknown): value is StatusRecord {
  return (
    typeof value === "object" &&
    value !== null &&
    "node" in value &&
    "node_state" in value &&
    "updated_at" in value
  );
}

export function parseStatus(raw: string): StatusRecord | null {
  let data: unknown;
  try {
    data = JSON.parse(raw);
  } catch {
    return null;
  }
  return isStatusRecord(data) ? data : null;
}

export function secondsAgo(isoTimestamp: string, now: Date = new Date()): number {
  const then = new Date(isoTimestamp);
  return Math.max(0, Math.round((now.getTime() - then.getTime()) / 1000));
}

export function formatStatusLines(record: StatusRecord | null, now: Date = new Date()): string[] {
  if (record === null) {
    return ["factory: waiting for status..."];
  }
  const lines: string[] = [];
  lines.push(`factory: ${record.task_id || "(no task)"}  [${record.node} / ${record.node_state}]`);
  lines.push(
    `  attempt ${record.attempt}/${record.max_attempts}  (updated ${secondsAgo(record.updated_at, now)}s ago)`,
  );
  if (record.snippet) {
    lines.push(`  ${record.snippet.slice(-120)}`);
  }
  if (record.outcome) {
    lines.push(`  outcome: ${record.outcome}`);
  }
  return lines;
}
```

- [ ] **Step 4: Run to pass**

```bash
cd pi-ext/factory-watch && npm test && npm run typecheck
```
Expected: all status-format tests pass; typecheck clean.

- [ ] **Step 5: Commit**

```bash
git add pi-ext/factory-watch/src/status-format.ts pi-ext/factory-watch/test/status-format.test.ts
git commit -m "feat: pure status-file parsing and widget formatting"
```

---

### Task 3: Lock file parsing and cross-platform PID liveness (pure)

**Files:**
- Create: `pi-ext/factory-watch/src/lock-status.ts`
- Test: `pi-ext/factory-watch/test/lock-status.test.ts`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `LockRecord` — the shape Plan A's `lock.py` writes: `{ pid: number, started_at: string }`.
  - `parseLock(raw: string): LockRecord | null`.
  - `isPidAlive(pid: number): boolean` — uses Node's native `process.kill(pid, 0)`, which (unlike Python's `os.kill`) works as a liveness-only check on both POSIX and Windows without shelling out to anything.

- [ ] **Step 1: Write the failing test**

```typescript
// test/lock-status.test.ts
import { describe, expect, test } from "vitest";
import { isPidAlive, parseLock } from "../src/lock-status.js";

describe("parseLock", () => {
  test("parses a valid lock record", () => {
    const raw = JSON.stringify({ pid: 12345, started_at: "2026-07-20T10:00:00Z" });
    expect(parseLock(raw)).toEqual({ pid: 12345, started_at: "2026-07-20T10:00:00Z" });
  });
  test("returns null for malformed JSON", () => {
    expect(parseLock("not json")).toBeNull();
  });
  test("returns null when pid is missing or not a number", () => {
    expect(parseLock('{"started_at": "x"}')).toBeNull();
    expect(parseLock('{"pid": "12345", "started_at": "x"}')).toBeNull();
  });
});

describe("isPidAlive", () => {
  test("is true for the current process", () => {
    expect(isPidAlive(process.pid)).toBe(true);
  });
  test("is false for an implausible pid", () => {
    expect(isPidAlive(999_999_999)).toBe(false);
  });
});
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd pi-ext/factory-watch && npm test
```
Expected: FAIL — `../src/lock-status.js` not found.

- [ ] **Step 3: Implement `src/lock-status.ts`**

```typescript
export interface LockRecord {
  pid: number;
  started_at: string;
}

function isLockRecord(value: unknown): value is LockRecord {
  return (
    typeof value === "object" &&
    value !== null &&
    "pid" in value &&
    typeof (value as { pid: unknown }).pid === "number" &&
    "started_at" in value
  );
}

export function parseLock(raw: string): LockRecord | null {
  let data: unknown;
  try {
    data = JSON.parse(raw);
  } catch {
    return null;
  }
  return isLockRecord(data) ? data : null;
}

export function isPidAlive(pid: number): boolean {
  // process.kill with signal 0 is a Node-documented existence check: it
  // sends no actual signal and works this way on both POSIX and Windows
  // (unlike Python's os.kill, which doesn't support signal 0 on Windows --
  // see src/factory/orchestrator/lock.py's tasklist-based workaround there).
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}
```

- [ ] **Step 4: Run to pass**

```bash
cd pi-ext/factory-watch && npm test && npm run typecheck
```
Expected: all lock-status tests pass; typecheck clean.

- [ ] **Step 5: Commit**

```bash
git add pi-ext/factory-watch/src/lock-status.ts pi-ext/factory-watch/test/lock-status.test.ts
git commit -m "feat: pure lock-file parsing and cross-platform PID liveness check"
```

---

### Task 4: Process command builders (pure)

**Files:**
- Create: `pi-ext/factory-watch/src/process-control.ts`
- Test: `pi-ext/factory-watch/test/process-control.test.ts`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `Command { bin: string; args: string[] }`.
  - `buildRunCommand(provider: string, modelId: string): Command` — the orchestrator invocation, mirroring `src/factory/orchestrator/pi_backend.py`'s `_build_command` pattern (return the full invocation shape, nothing partial).
  - `buildWindowsKillArgs(pid: number): string[]` — `taskkill` arguments for a forceful process-tree kill.

**Design note carried into this task:** on Windows, a *non-forceful* `taskkill /PID <pid> /T` relies on sending a close request that plain console processes (this orchestrator is one) frequently don't respond to reliably — so this always goes straight to a forceful tree-kill (`/T /F`) rather than attempting a "graceful" phase that wouldn't actually work for this kind of process on Windows. On POSIX, real graceful-then-forceful (`SIGTERM` then `SIGKILL` to the process group) *is* reliable, and doesn't need shelling out — Node's native `process.kill(-pid, signal)` handles it directly, so there's no POSIX equivalent of `buildWindowsKillArgs` to write here; that timing/signal logic lives directly in Task 5's `index.ts`.

- [ ] **Step 1: Write the failing test**

```typescript
// test/process-control.test.ts
import { describe, expect, test } from "vitest";
import { buildRunCommand, buildWindowsKillArgs } from "../src/process-control.js";

describe("buildRunCommand", () => {
  test("builds the orchestrator invocation with the given provider/model", () => {
    const cmd = buildRunCommand("openrouter", "anthropic/claude-opus-4");
    expect(cmd.bin).toBe("uv");
    expect(cmd.args).toEqual([
      "run", "python", "-m", "factory.orchestrator", "run",
      "--provider", "openrouter",
      "--model", "anthropic/claude-opus-4",
    ]);
  });
});

describe("buildWindowsKillArgs", () => {
  test("builds a forceful tree-kill for the given pid", () => {
    expect(buildWindowsKillArgs(12345)).toEqual(["/PID", "12345", "/T", "/F"]);
  });
});
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd pi-ext/factory-watch && npm test
```
Expected: FAIL — `../src/process-control.js` not found.

- [ ] **Step 3: Implement `src/process-control.ts`**

```typescript
export interface Command {
  bin: string;
  args: string[];
}

export function buildRunCommand(provider: string, modelId: string): Command {
  return {
    bin: "uv",
    args: [
      "run", "python", "-m", "factory.orchestrator", "run",
      "--provider", provider,
      "--model", modelId,
    ],
  };
}

export function buildWindowsKillArgs(pid: number): string[] {
  return ["/PID", String(pid), "/T", "/F"];
}
```

- [ ] **Step 4: Run to pass**

```bash
cd pi-ext/factory-watch && npm test && npm run typecheck
```
Expected: all process-control tests pass; typecheck clean.

- [ ] **Step 5: Commit**

```bash
git add pi-ext/factory-watch/src/process-control.ts pi-ext/factory-watch/test/process-control.test.ts
git commit -m "feat: pure command builders for launching and killing the orchestrator"
```

---

### Task 5: Extension entry wiring (`/factory`, `/factory-stop`) + real-type compat check

**Files:**
- Create: `pi-ext/factory-watch/src/index.ts`, `pi-ext/factory-watch/src/type-compat-check.ts`
- Test: `pi-ext/factory-watch/test/handler.test.ts`

**Interfaces:**
- Consumes: `PiApi`, `ExtCommandCtx` (Task 1); `parseStatus`, `formatStatusLines` (Task 2); `parseLock`, `isPidAlive` (Task 3); `buildRunCommand`, `buildWindowsKillArgs` (Task 4).
- Produces: default-exported `(pi: PiApi) => void` registering two commands, `factory` and `factory-stop`.

- [ ] **Step 1: Write the failing test**

```typescript
// test/handler.test.ts
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import factoryWatch from "../src/index.js";
import type { CommandDef, ExtCommandCtx, PiApi, UiApi } from "../src/pi-types.js";

function capture(): { commands: Map<string, CommandDef>; pi: PiApi } {
  const commands = new Map<string, CommandDef>();
  const pi: PiApi = {
    registerCommand: (name, def) => commands.set(name, def),
  };
  factoryWatch(pi);
  return { commands, pi };
}

function fakeCtx(overrides: Partial<ExtCommandCtx> = {}): ExtCommandCtx {
  const ui: UiApi = {
    notify: vi.fn(),
    setStatus: vi.fn(),
    setWidget: vi.fn(),
  };
  return {
    cwd: overrides.cwd ?? process.cwd(),
    ui: overrides.ui ?? ui,
    model: overrides.model ?? { provider: "openrouter", id: "anthropic/claude-opus-4" },
  };
}

describe("factory-watch commands", () => {
  test("registers both factory and factory-stop", () => {
    const { commands } = capture();
    expect(commands.has("factory")).toBe(true);
    expect(commands.has("factory-stop")).toBe(true);
  });

  test("/factory notifies an error and does nothing else when no model is active", async () => {
    const { commands } = capture();
    const ctx = fakeCtx({ model: undefined });
    await commands.get("factory")!.handler("", ctx);
    expect(ctx.ui.notify).toHaveBeenCalledWith(expect.stringContaining("no model"), "error");
  });

  test("/factory-stop notifies when nothing is running (no lock file)", async () => {
    const { commands } = capture();
    const ctx = fakeCtx({ cwd: "/nonexistent/path/for/this/test/only" });
    await commands.get("factory-stop")!.handler("", ctx);
    expect(ctx.ui.notify).toHaveBeenCalledWith(expect.stringContaining("not running"), "info");
  });
});
```

Note: this test intentionally does NOT exercise the real `child_process.spawn`/`taskkill` paths — those require a real filesystem lock file and a real live process to interact with correctly, and are covered instead by Task 6's manual verification. This test covers exactly the two logic branches that are safely exercisable without spawning anything: the no-model guard and the no-lock-file guard.

- [ ] **Step 2: Run to verify it fails**

```bash
cd pi-ext/factory-watch && npm test
```
Expected: FAIL — `../src/index.js` not found.

- [ ] **Step 3: Implement `src/index.ts`**

```typescript
// Pi loads this via: pi --extension pi-ext/factory-watch/src/index.ts
// (project-local auto-discovery via .pi/extensions/ also works once installed there)

import { spawn, spawnSync } from "node:child_process";
import { openSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { isPidAlive, parseLock } from "./lock-status.js";
import { buildRunCommand, buildWindowsKillArgs } from "./process-control.js";
import type { ExtCommandCtx, PiApi } from "./pi-types.js";
import { formatStatusLines, parseStatus } from "./status-format.js";

const STATUS_FILE = "sessions/.factory-status.json";
const LOCK_FILE = "sessions/.factory-run.lock";
const LOG_FILE = "sessions/.factory-run.log";
const POLL_INTERVAL_MS = 1000;
const POSIX_GRACEFUL_TIMEOUT_MS = 3000;

function readFileIfExists(path: string): string | null {
  try {
    return readFileSync(path, "utf-8");
  } catch {
    return null;
  }
}

export default function factoryWatch(pi: PiApi): void {
  let pollHandle: ReturnType<typeof setInterval> | undefined;

  function stopPolling(): void {
    if (pollHandle !== undefined) {
      clearInterval(pollHandle);
      pollHandle = undefined;
    }
  }

  pi.registerCommand("factory", {
    description: "Run the next todo factory task, watching progress live",
    handler: async (_args: string, ctx: ExtCommandCtx) => {
      const lockPath = join(ctx.cwd, LOCK_FILE);
      const statusPath = join(ctx.cwd, STATUS_FILE);

      const existingLockRaw = readFileIfExists(lockPath);
      if (existingLockRaw !== null) {
        const existingLock = parseLock(existingLockRaw);
        if (existingLock !== null && isPidAlive(existingLock.pid)) {
          ctx.ui.notify(
            `factory already running (pid ${existingLock.pid}) -- use /factory-stop first`,
            "warning",
          );
          return;
        }
      }

      if (ctx.model === undefined) {
        ctx.ui.notify("no model selected in this session -- can't launch factory", "error");
        return;
      }

      const cmd = buildRunCommand(ctx.model.provider, ctx.model.id);
      const logFd = openSync(join(ctx.cwd, LOG_FILE), "a");
      const child = spawn(cmd.bin, cmd.args, {
        cwd: ctx.cwd,
        detached: true,
        stdio: ["ignore", logFd, logFd],
      });
      child.unref();

      stopPolling();
      pollHandle = setInterval(() => {
        const raw = readFileIfExists(statusPath);
        const record = raw === null ? null : parseStatus(raw);
        ctx.ui.setWidget("factory", formatStatusLines(record));

        const stillLocked = readFileIfExists(lockPath) !== null;
        if (!stillLocked) {
          stopPolling();
          ctx.ui.notify("factory run finished", "info");
        }
      }, POLL_INTERVAL_MS);

      ctx.ui.notify(`factory started (${ctx.model.provider}/${ctx.model.id})`, "info");
    },
  });

  pi.registerCommand("factory-stop", {
    description: "Stop the currently running factory task",
    handler: async (_args: string, ctx: ExtCommandCtx) => {
      const lockPath = join(ctx.cwd, LOCK_FILE);
      const raw = readFileIfExists(lockPath);
      if (raw === null) {
        ctx.ui.notify("factory is not running", "info");
        return;
      }
      const lock = parseLock(raw);
      if (lock === null || !isPidAlive(lock.pid)) {
        ctx.ui.notify("factory lock is stale (process already gone)", "info");
        return;
      }

      if (process.platform === "win32") {
        spawnSync("taskkill", buildWindowsKillArgs(lock.pid));
      } else {
        try {
          process.kill(-lock.pid, "SIGTERM");
        } catch {
          // process group may already be gone; the liveness check below handles it
        }
        await new Promise((resolve) => setTimeout(resolve, POSIX_GRACEFUL_TIMEOUT_MS));
        if (isPidAlive(lock.pid)) {
          try {
            process.kill(-lock.pid, "SIGKILL");
          } catch {
            // already gone
          }
        }
      }

      stopPolling();
      ctx.ui.setWidget("factory", undefined);
      ctx.ui.notify("factory stopped", "info");
    },
  });
}
```

- [ ] **Step 4: Write `src/type-compat-check.ts`**

```typescript
// Type-only compile-time guard: never imported, never executed, only
// typechecked by `tsc --noEmit`.
//
// pi-types.ts hand-declares a minimal structural subset of Pi's real
// ExtensionAPI so this extension can be typechecked/tested without
// exercising the full real interface in every fake. That hand-rolled
// surface can silently drift from the real @earendil-works/pi-coding-agent
// package as Pi evolves. This file pins the one load-bearing assumption
// against the real package's published types:
//
//   factory-watch's default export (`(pi: PiApi) => void`) must remain
//   structurally usable as a real Pi `ExtensionFactory` -- this is literally
//   how Pi loads the extension at runtime
//   (`pi --extension pi-ext/factory-watch/src/index.ts`). Because function
//   parameter assignability is checked contravariantly, this single
//   assignment recursively validates every field this extension reads off
//   `pi` and off each command handler's `ctx` (registerCommand,
//   ctx.ui.notify/setStatus/setWidget, ctx.model, ctx.cwd) against the real
//   types.
//
// If this assignment stops compiling, pi-types.ts has drifted from the real
// ExtensionAPI and must be reconciled before merging.

import type { ExtensionFactory } from "@earendil-works/pi-coding-agent";
import factoryWatch from "./index.js";

const _factoryCompat: ExtensionFactory = factoryWatch;
void _factoryCompat;
```

- [ ] **Step 5: Run to pass**

```bash
cd pi-ext/factory-watch && npm test && npm run typecheck
```
Expected: handler tests pass; typecheck clean (this is the step that proves `type-compat-check.ts` actually compiles against the real installed package).

- [ ] **Step 6: Commit**

```bash
git add pi-ext/factory-watch/src/index.ts pi-ext/factory-watch/src/type-compat-check.ts pi-ext/factory-watch/test/handler.test.ts
git commit -m "feat: factory-watch /factory and /factory-stop command wiring"
```

---

### Task 6: Factory gate + README + real verification

**Files:**
- Create: `scripts/gates/watch_ext.py`, `pi-ext/factory-watch/README.md`
- Test: `tests/gates/test_watch_ext_gate.py`

**Interfaces:**
- Consumes: `run_and_propagate` from `scripts/gates/_proc.py` (already exists, used identically by `scripts/gates/ext.py`).
- Produces: `scripts/gates/watch_ext.py` runs the extension's typecheck + tests via npm, propagating the exit code, so the factory's gate set covers this extension too — mirrors `scripts/gates/ext.py` exactly, pointed at the new extension's directory.

- [ ] **Step 1: Write the failing test**

```python
# tests/gates/test_watch_ext_gate.py
import subprocess
import sys
import pytest

pytestmark = pytest.mark.unit


def test_watch_ext_gate_passes():
    rc = subprocess.run([sys.executable, "scripts/gates/watch_ext.py"]).returncode
    assert rc == 0
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/gates/test_watch_ext_gate.py -v`
Expected: FAIL — `scripts/gates/watch_ext.py` missing.

- [ ] **Step 3: Implement `scripts/gates/watch_ext.py`**

```python
# scripts/gates/watch_ext.py
import sys
from pathlib import Path
from _proc import run_and_propagate

EXT_DIR = Path(__file__).resolve().parents[2] / "pi-ext" / "factory-watch"

if __name__ == "__main__":
    # npm on Windows is npm.cmd; shell=False needs the resolved name.
    npm = "npm.cmd" if sys.platform == "win32" else "npm"
    code = run_and_propagate([npm, "--prefix", str(EXT_DIR), "run", "typecheck"])
    if code != 0:
        sys.exit(code)
    sys.exit(run_and_propagate([npm, "--prefix", str(EXT_DIR), "test"]))
```

- [ ] **Step 4: Write `README.md`**

```markdown
# factory-watch — Pi extension

Launches and observes the factory orchestrator from inside an interactive
`pi` session. Loads in *your own* session (not the orchestrator's spawned
sub-agent sessions, which load `scope-guard` instead).

## Commands

- `/factory` — reads the session's currently active model (`ctx.model`), runs
  `uv run python -m factory.orchestrator run --provider <provider> --model <id>`
  detached, and polls `sessions/.factory-status.json` (written by the
  orchestrator, see Plan A) once a second, rendering it via a widget. Refuses
  to start a second run while `sessions/.factory-run.lock` shows a live PID.
- `/factory-stop` — reads the lock file's PID and terminates it: a forceful
  process-tree kill on Windows (`taskkill /PID <pid> /T /F` — a non-forceful
  `/T` alone is unreliable for plain console processes on Windows, so this
  skips straight to force), or `SIGTERM` to the process group followed by
  `SIGKILL` after a few seconds if still alive on POSIX.

## No new IPC

Everything here reads files Plan A's orchestrator already writes
(`sessions/.factory-status.json`, `sessions/.factory-run.lock`) — no sockets,
no named pipes.

## Load into Pi

```
pi --extension pi-ext/factory-watch/src/index.ts
```
Then type `/factory` in the session.

## Test

```
npm --prefix pi-ext/factory-watch run typecheck
npm --prefix pi-ext/factory-watch test
```

## Verification limits

`ctx.ui.*` calls are no-ops in `-p`/print mode (per Pi's own docs), so the
*logic* here (spawning, file reads, process control) is verifiable
headlessly, but the actual *rendered widget* can only be seen in a real
interactive session. See this plan's Task 6 for what was and wasn't
automated.
```

- [ ] **Step 5: Run the gate to pass**

Run: `uv run pytest tests/gates/test_watch_ext_gate.py -v` → 1 passed.
Run: `uv run python scripts/gates/watch_ext.py; echo "exit=$?"` → exit=0.

- [ ] **Step 6: Automated real-process verification (headless, via `pi -p`)**

> Pi's own docs confirm registered commands run in `-p` (print) mode — only
> `ctx.ui.*` calls become no-ops, the actual command logic still executes.
> This lets most of `/factory`/`/factory-stop` be verified for real without
> a full interactive TUI session.

In a scratch directory with its own `tasks/T-001-scratch.md` (`status: todo`,
same frontmatter shape as `tasks/T-001-example.md`) so a real run has
something to pick up — or, to avoid triggering a real (billed) LLM call,
temporarily set every task's `status` to something other than `todo` first
and only verify the **refuse-to-double-start** and **stop-with-no-run**
paths, which don't require a task to actually execute. Prefer the
credential-free path unless you have already confirmed working LLM
credentials you're fine spending on this repo:

```bash
# From the repo root, with the extension loadable via --extension:
pi -p "/factory" --mode json --extension pi-ext/factory-watch/src/index.ts
```
Expected (no active `todo` task): the orchestrator prints `no todo tasks`
(same as Task 6 of Plan A's own smoke check) and exits almost immediately;
no lock file is left behind afterward.

```bash
pi -p "/factory-stop" --mode json --extension pi-ext/factory-watch/src/index.ts
```
Expected: exits cleanly; since no run was started, this exercises the
"factory is not running" branch.

If you *do* want to verify a real run + real cancellation end to end (costs
a real LLM call and takes longer): put one task back to `status: todo`, run
`/factory`, then within a few seconds (before the task finishes) run
`/factory-stop` from a second `pi -p` invocation in the same directory.
Confirm via the OS process list (e.g. PowerShell `Get-Process` /
`Get-CimInstance Win32_Process`) that no `python`/`pi` process tied to this
repo survives after `/factory-stop` returns — this is the one property unit
tests structurally cannot prove, since it depends on real OS process-tree
behavior.

Record what you actually ran and observed (not what you expect to have
happened) in this step's commit or report.

- [ ] **Step 7: One remaining manual step (not automatable by this plan)**

The rendered widget itself — does `ctx.ui.setWidget("factory", [...])`
actually look right in a live interactive `pi` session, updating once a
second — can only be seen by a human running `pi` interactively and typing
`/factory`. This is explicitly out of scope for automated verification here;
flag it to whoever owns this repo as a one-time manual check before relying
on this extension day-to-day.

- [ ] **Step 8: Commit**

```bash
git add scripts/gates/watch_ext.py pi-ext/factory-watch/README.md tests/gates/test_watch_ext_gate.py
git commit -m "feat: factory gate and docs for factory-watch extension"
```

---

## Self-Review

**Spec coverage** (against `docs/superpowers/specs/2026-07-20-factory-live-visualization-design.md`):
- §2 architecture (two independent pi process contexts, factory-watch only ever launches/observes, never talks to sub-agents directly) → the whole extension; nothing here imports or touches `pi-ext/scope-guard/`.
- §3.4 `/factory`/`/factory-stop` → Task 5.
- §4 cancellation, no orphaned sub-agent process → Task 4 (Windows kill-arg construction) + Task 5 (POSIX process-group signal timing) + Task 6 (the one thing that must be verified against a real OS, not just unit tests).
- §5 error handling (stale lock, concurrent `/factory` refusal) → Task 5's `/factory`/`/factory-stop` guards.
- §6 no override of provider/model → honored throughout; `/factory` takes no arguments beyond what `ctx.model` already provides.
- §7 testing strategy (pure functions vitest-tested, thin wiring, required manual verification) → Tasks 2-4 (pure), Task 5 (thin wiring + the two logic branches that are safely testable without a real subprocess), Task 6 (the manual/headless-automated verification explicitly called out as required, not assumed).

**Placeholder scan:** none. Every step ships exact, complete code and exact commands with expected output. Task 6's verification step is deliberately honest about what it can and can't automate, rather than claiming full automated coverage of something that structurally requires a real interactive TUI.

**Type consistency:** `ModelInfo`/`UiApi`/`ExtCommandCtx`/`CommandDef`/`PiApi` (Task 1) used unchanged in Tasks 2-5. `StatusRecord` (Task 2) and `LockRecord` (Task 3) match exactly what Plan A's `FileStatusReporter`/`lock.py` actually write (verified against the shipped Plan A code, not assumed). `Command`/`buildRunCommand`/`buildWindowsKillArgs` (Task 4) match their call sites in Task 5's `index.ts` exactly (`cmd.bin`, `cmd.args`, `buildWindowsKillArgs(lock.pid)`).

**Cross-plan dependency note:** consumes Plan A (`src/factory/orchestrator/status.py`'s `FileStatusReporter` output shape, `lock.py`'s lock file shape, `__main__.py`'s CLI flags) unchanged — this plan makes zero changes to any Python file. If Plan A's status/lock file shapes ever change, `StatusRecord`/`LockRecord` here (Tasks 2-3) need to be updated to match, but nothing in this plan enforces that at compile time (per spec §6, deliberately not schema-validated) — a human or a future gate would need to catch drift here.
