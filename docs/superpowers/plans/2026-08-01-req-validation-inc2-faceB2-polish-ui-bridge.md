# Increment 2 — Face B2: Polish Control Panel + File Bridge — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the deterministic `PolishOrchestrator` (Plan B core) a human surface: a factory-watch TUI control panel (feedback input + live queue + Gate 1 accept/edit/discard + Gate 2 tick/comment), connected to the Python orchestrator through an atomic-JSON file bridge — the same cross-process pattern factory-watch already uses for review.

**Architecture:** The orchestrator is Python; the UI is the factory-watch pi extension (TypeScript). They bridge via files under `sessions/.factory-transcripts/<sessionId>/`, exactly as review does (`review-guide.json` in, `review-decision.json` out). A `PolishBridge` (Python) **publishes** `orchestrator.state()` to `polish-state.json` (atomic write, monotonic `seq`) on every change, and **consumes** command files the UI drops into `polish-commands/` (atomic rename in, sorted, applied, deleted), dispatching each to the matching orchestrator method. The TUI `PolishOverlay` (TS) is a pi-tui `Component` mirroring `ReviewOverlay`: it polls `polish-state.json`, renders the panel, and on keypress writes a command file via a `polish-protocol.ts` that reuses `review-protocol.ts`'s atomic-rename-with-Windows-retry. The CareerOS *app* browser is opened by the orchestrator's `open_navigator` (Plan B core), so this panel is the *control* surface only — no web panel is built (YAGNI).

**Tech Stack:** Python 3.12 (`pytest`, `ruff`, `pyright`); TypeScript / Node (pi extension, `@earendil-works/pi-tui`), `vitest` (the factory-watch test runner — confirm with `pi-ext/factory-watch/package.json`).

## Global Constraints

- Reuse verbatim: `PolishOrchestrator` + its `state()` dict and transition methods `submit_feedback/accept_finding/edit_finding/discard_finding/tick/comment` (Plan B core, `factory.polish.orchestrator`); the atomic-rename primitive and Windows-EPERM retry loop from `pi-ext/factory-watch/src/review-protocol.ts`; the `ui.custom<T>((tui, theme, keybindings, done) => Component)` panel API and the `ReviewOverlay` Component conformance in `review-overlay.ts` (the `PolishOverlay` MUST implement the same pi-tui `Component` interface the same way).
- The bridge is the ONLY coupling between Python and TS. Neither side imports the other; they agree only on the JSON shapes in Task 1 / Task 3 (keep them identical — a `polish-model.ts` type per `state()` key).
- All cross-process file writes use atomic temp-write + rename with the 5×50ms retry (Windows holds files open without delete-share). Never write the live file in place.
- Command files are consumed **exactly once**: Python processes the sorted `polish-commands/*.json`, applies, then deletes each. The UI never overwrites a pending command — it always writes a new uniquely-named file.
- Repos/paths: Python in `C:/coding/pi-agent-factory` (`src/factory/polish/`, tests `tests/unit/polish/`); TS in `pi-ext/factory-watch/src/` (tests `pi-ext/factory-watch/test/`).

---

### Task 1: `PolishBridge` — publish state + consume commands (Python)

**Files:**
- Create: `src/factory/polish/bridge.py`
- Test: `tests/unit/polish/test_bridge.py`

**Interfaces:**
- Consumes: `PolishOrchestrator` (Plan B core).
- Produces: `PolishBridge(orchestrator, state_path: Path, commands_dir: Path)` with `.publish() -> None` (atomic-write `state()` + incrementing `seq`), `.poll_commands() -> int` (apply + delete each sorted command file, return count applied), and `.dispatch(cmd: dict) -> None`. Command JSON shape: `{"kind": str, "args": {...}}` where `kind ∈ {feedback,accept,edit,discard,tick,comment}` and `args` are the matching method kwargs. Consumed by Task 2 (driver) and mirrored by Task 3 (TS types).

- [ ] **Step 1: Write the failing test** (real orchestrator with fakes from Plan B core's test helpers; drive it entirely through bridge files)

```python
# tests/unit/polish/test_bridge.py
import json
from pathlib import Path

from factory.orchestrator.backends import FakeAgentBackend
from factory.orchestrator.types import AgentResult, AgentRole
from factory.polish.playground import PlaygroundSession
from factory.polish.worker import FixWorker, LandedChange
from factory.polish.orchestrator import PolishOrchestrator
from factory.polish.bridge import PolishBridge

class _Pg:
    def list_usecases(self): return ["sign-in"]
    def setup(self, uc): return PlaygroundSession(entrypoints=["http://x"], describe="up")

class _FakeExecutor:  # stands in for WorktreeIsolatedExecutor
    def __init__(self): self.n = 0
    def execute(self, finding):
        self.n += 1
        return LandedChange(finding=finding, task_path=Path(f"tasks/T-{self.n:03d}.md"),
                            task_id=f"T-{self.n:03d}", status="landed")

def _orch(tmp_path, findings):
    backend = FakeAgentBackend({AgentRole.SYNTHESIS: [AgentResult(ok=True, output={"findings": findings})]})
    worker = FixWorker(_FakeExecutor())
    return PolishOrchestrator(_Pg(), backend, worker, open_nav=lambda e: None)

def test_publish_writes_state_with_incrementing_seq(tmp_path):
    orch = _orch(tmp_path, [{"description": "x"}]); orch.setup("sign-in")
    b = PolishBridge(orch, tmp_path / "polish-state.json", tmp_path / "cmds")
    b.publish(); b.publish()
    data = json.loads((tmp_path / "polish-state.json").read_text("utf-8"))
    assert data["seq"] == 2
    assert data["state"]["usecase"] == "sign-in"
    orch.teardown()

def test_poll_commands_dispatches_feedback_then_accept(tmp_path):
    orch = _orch(tmp_path, [{"description": "sign-in broken", "sr": "SR-010"}]); orch.setup("sign-in")
    cmds = tmp_path / "cmds"; cmds.mkdir()
    b = PolishBridge(orch, tmp_path / "polish-state.json", cmds)
    (cmds / "001.json").write_text(json.dumps({"kind": "feedback", "args": {"text": "broken"}}), "utf-8")
    assert b.poll_commands() == 1
    assert not (cmds / "001.json").exists()  # consumed
    gid = orch.state()["gate1_ids"][0]
    (cmds / "002.json").write_text(json.dumps({"kind": "accept", "args": {"gid": gid}}), "utf-8")
    assert b.poll_commands() == 1
    assert orch.state()["gate1"] == []
    orch.teardown()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/polish/test_bridge.py -v`
Expected: FAIL — `ModuleNotFoundError: factory.polish.bridge`.

- [ ] **Step 3: Implement**

```python
# src/factory/polish/bridge.py
from __future__ import annotations

import json
import os
from pathlib import Path

from factory.polish.orchestrator import PolishOrchestrator


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)  # atomic on same filesystem


class PolishBridge:
    """File bridge between the Python PolishOrchestrator and the TS UI."""

    def __init__(self, orchestrator: PolishOrchestrator, state_path: Path, commands_dir: Path) -> None:
        self._orch = orchestrator
        self._state_path = state_path
        self._commands_dir = commands_dir
        self._seq = 0

    def publish(self) -> None:
        self._seq += 1
        _atomic_write(self._state_path, json.dumps({"seq": self._seq, "state": self._orch.state()}))

    def dispatch(self, cmd: dict) -> None:
        kind = cmd.get("kind")
        args = cmd.get("args") or {}
        if kind == "feedback":
            self._orch.submit_feedback(str(args["text"]))
        elif kind == "accept":
            self._orch.accept_finding(str(args["gid"]))
        elif kind == "edit":
            self._orch.edit_finding(str(args["gid"]), **(args.get("changes") or {}))
        elif kind == "discard":
            self._orch.discard_finding(str(args["gid"]))
        elif kind == "tick":
            self._orch.tick(str(args["gid"]))
        elif kind == "comment":
            self._orch.comment(str(args["gid"]), str(args["text"]))
        # unknown kinds are ignored (forward-compat with a newer UI)

    def poll_commands(self) -> int:
        if not self._commands_dir.exists():
            return 0
        applied = 0
        for path in sorted(self._commands_dir.glob("*.json")):
            try:
                cmd = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue  # a half-written file; try again next poll
            self.dispatch(cmd)
            path.unlink(missing_ok=True)
            applied += 1
        if applied:
            self.publish()
        return applied
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/polish/test_bridge.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/factory/polish/bridge.py tests/unit/polish/test_bridge.py
git commit -m "feat(polish): PolishBridge — publish state json + consume command files"
```

---

### Task 2: Bridge-driven `factory polish` session loop (Python)

**Files:**
- Modify: `src/factory/polish/cli.py` (add a `serve` path that runs orchestrator + bridge)
- Test: `tests/unit/polish/test_cli.py`

**Interfaces:**
- Consumes: `PolishOrchestrator` + `build_orchestrator` (Plan B Task 7), `PolishBridge` (Task 1).
- Produces: `run_polish_serve(orchestrator, bridge, *, should_stop: Callable[[], bool], poll_interval: float = 0.2) -> None` — publishes once, then loops `poll_commands()` at `poll_interval` until `should_stop()`, publishing on change; tears down on exit. Consumed by the `/polish` command (Task 6) which spawns `python -m factory.polish serve ...`.

- [ ] **Step 1: Write the failing test** (inject `should_stop` to stop after the commands drain, so the loop is deterministic)

```python
# add to tests/unit/polish/test_cli.py
import json
from factory.polish.bridge import PolishBridge
from factory.polish.cli import run_polish_serve

def test_serve_applies_a_command_then_stops(tmp_path, monkeypatch):
    # reuse the orchestrator fake-builder from test_bridge
    from tests.unit.polish.test_bridge import _orch
    orch = _orch(tmp_path, [{"description": "x"}]); orch.setup("sign-in")
    cmds = tmp_path / "cmds"; cmds.mkdir()
    (cmds / "001.json").write_text(json.dumps({"kind": "feedback", "args": {"text": "broken"}}), "utf-8")
    bridge = PolishBridge(orch, tmp_path / "state.json", cmds)
    calls = {"n": 0}
    def should_stop():
        calls["n"] += 1
        return calls["n"] > 2  # let a couple of polls run
    run_polish_serve(orch, bridge, should_stop=should_stop, poll_interval=0.0)
    assert orch.state()["gate1_ids"]  # feedback was applied
    assert not (cmds / "001.json").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/polish/test_cli.py -k serve -v`
Expected: FAIL — `cannot import name 'run_polish_serve'`.

- [ ] **Step 3: Implement**

```python
# add to src/factory/polish/cli.py
import time
from collections.abc import Callable

from factory.polish.bridge import PolishBridge
from factory.polish.orchestrator import PolishOrchestrator


def run_polish_serve(orchestrator: PolishOrchestrator, bridge: PolishBridge, *,
                     should_stop: Callable[[], bool], poll_interval: float = 0.2) -> None:
    bridge.publish()
    try:
        while not should_stop():
            bridge.poll_commands()
            bridge.publish()  # worker may have landed a fix between polls -> Gate 2 grows
            if poll_interval:
                time.sleep(poll_interval)
    finally:
        orchestrator.teardown()
```

Also add a `serve` subcommand to the argparse in `cli.py` that: builds the orchestrator (`build_orchestrator`), calls `orchestrator.setup(usecase)`, constructs `PolishBridge` with the session paths (Task 4 defines the exact filenames), and runs `run_polish_serve` with `should_stop` reading a sentinel file the UI deletes on quit (or a signal handler). Mirror the argparse style already in `cli.py`.

- [ ] **Step 4: Run tests + lint/type**

Run: `python -m pytest tests/unit/polish -v && ruff check src/factory/polish && pyright src/factory/polish`
Expected: PASS; clean.

- [ ] **Step 5: Commit**

```bash
git add src/factory/polish/cli.py tests/unit/polish/test_cli.py
git commit -m "feat(polish): run_polish_serve — orchestrator+bridge session loop + serve CLI"
```

---

### Task 3: `polish-model.ts` — shared JSON shapes (TS)

**Files:**
- Create: `pi-ext/factory-watch/src/polish-model.ts`
- Test: `pi-ext/factory-watch/test/polish-model.test.ts`

**Interfaces:**
- Consumes: nothing (mirrors Task 1's JSON).
- Produces: `PolishState` (mirrors `state()`), `PolishStateFile = { seq: number; state: PolishState }`, `PolishCommand` (discriminated union of the Task-1 command kinds), and `parsePolishStateFile(raw: string): PolishStateFile | null` (defensive; returns null on malformed JSON — never throws, per the no-throw discipline in review-guide.ts). Consumed by Tasks 4–5.

- [ ] **Step 1: Write the failing test**

```typescript
// pi-ext/factory-watch/test/polish-model.test.ts
import { describe, it, expect } from "vitest";
import { parsePolishStateFile } from "../src/polish-model.js";

describe("parsePolishStateFile", () => {
  it("parses a well-formed state file", () => {
    const raw = JSON.stringify({ seq: 3, state: {
      usecase: "sign-in", entrypoints: ["http://x"], queue_size: 1,
      gate1_ids: ["g1-1"], gate1: [{ gid: "g1-1", description: "broken", sr: "SR-010" }],
      gate2: [{ gid: "g2-1", task_id: "T-007", description: "fix", sr: null, status: "landed", verdict: "pending" }],
    }});
    const parsed = parsePolishStateFile(raw);
    expect(parsed?.seq).toBe(3);
    expect(parsed?.state.gate1[0]?.description).toBe("broken");
    expect(parsed?.state.gate2[0]?.status).toBe("landed");
  });

  it("returns null on malformed json (never throws)", () => {
    expect(parsePolishStateFile("{not json")).toBeNull();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd pi-ext/factory-watch && npx vitest run test/polish-model.test.ts`
Expected: FAIL — cannot find module `../src/polish-model.js`.

- [ ] **Step 3: Implement**

```typescript
// pi-ext/factory-watch/src/polish-model.ts
export interface Gate1Item { gid: string; description: string; sr: string | null }
export interface Gate2Row {
  gid: string; task_id: string; description: string;
  sr: string | null; status: "landed" | "failed"; verdict: "pending" | "accepted" | "wrong";
}
export interface PolishState {
  usecase: string;
  entrypoints: string[];
  queue_size: number;
  gate1_ids: string[];
  gate1: Gate1Item[];
  gate2: Gate2Row[];
}
export interface PolishStateFile { seq: number; state: PolishState }

export type PolishCommand =
  | { kind: "feedback"; args: { text: string } }
  | { kind: "accept"; args: { gid: string } }
  | { kind: "edit"; args: { gid: string; changes: Record<string, unknown> } }
  | { kind: "discard"; args: { gid: string } }
  | { kind: "tick"; args: { gid: string } }
  | { kind: "comment"; args: { gid: string; text: string } };

export function parsePolishStateFile(raw: string): PolishStateFile | null {
  try {
    const obj = JSON.parse(raw) as PolishStateFile;
    if (typeof obj?.seq !== "number" || typeof obj?.state !== "object") return null;
    return obj;
  } catch {
    return null; // half-written file or garbage; caller keeps the last good state
  }
}
```

- [ ] **Step 4: Run test + typecheck**

Run: `cd pi-ext/factory-watch && npx vitest run test/polish-model.test.ts && npx tsc --noEmit`
Expected: PASS; no TS errors.

- [ ] **Step 5: Commit**

```bash
git add pi-ext/factory-watch/src/polish-model.ts pi-ext/factory-watch/test/polish-model.test.ts
git commit -m "feat(factory-watch): polish-model shared bridge JSON shapes"
```

---

### Task 4: `polish-protocol.ts` — read state / write command (TS)

**Files:**
- Create: `pi-ext/factory-watch/src/polish-protocol.ts`
- Test: `pi-ext/factory-watch/test/polish-protocol.test.ts`

**Interfaces:**
- Consumes: `PolishStateFile`, `PolishCommand` (Task 3); the atomic-write helper pattern from `review-protocol.ts`.
- Produces: `polishStatePath(cwd, sessionId): string`, `polishCommandsDir(cwd, sessionId): string`, `readPolishState(path): PolishStateFile | null`, `writePolishCommand(commandsDir, cmd: PolishCommand): void` (writes `<zero-padded-monotonic>.json` via atomic temp+rename with the same retry loop as `writeReviewDecision`). Consumed by Tasks 5–6.

- [ ] **Step 1: Write the failing test**

```typescript
// pi-ext/factory-watch/test/polish-protocol.test.ts
import { describe, it, expect, beforeEach } from "vitest";
import { mkdtempSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { readPolishState, writePolishCommand } from "../src/polish-protocol.js";

let dir: string;
beforeEach(() => { dir = mkdtempSync(join(tmpdir(), "polish-")); });

describe("polish-protocol", () => {
  it("readPolishState returns null when the file is absent", () => {
    expect(readPolishState(join(dir, "nope.json"))).toBeNull();
  });
  it("readPolishState round-trips a written state", () => {
    const p = join(dir, "polish-state.json");
    writeFileSync(p, JSON.stringify({ seq: 1, state: { usecase: "x", entrypoints: [], queue_size: 0, gate1_ids: [], gate1: [], gate2: [] } }));
    expect(readPolishState(p)?.seq).toBe(1);
  });
  it("writePolishCommand drops a uniquely-named json file each call", () => {
    writePolishCommand(dir, { kind: "feedback", args: { text: "a" } });
    writePolishCommand(dir, { kind: "accept", args: { gid: "g1-1" } });
    const files = readdirSync(dir).filter((f) => f.endsWith(".json")).sort();
    expect(files.length).toBe(2);
    expect(JSON.parse(readFileSync(join(dir, files[0]!), "utf-8")).kind).toBe("feedback");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd pi-ext/factory-watch && npx vitest run test/polish-protocol.test.ts`
Expected: FAIL — cannot find `../src/polish-protocol.js`.

- [ ] **Step 3: Implement** (reuse the atomic-rename-with-retry from `review-protocol.ts` — import its helper if exported, else replicate the 5×50ms `syncSleep` loop)

```typescript
// pi-ext/factory-watch/src/polish-protocol.ts
import { mkdirSync, readFileSync, renameSync, unlinkSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { parsePolishStateFile, type PolishCommand, type PolishStateFile } from "./polish-model.js";

function syncSleep(ms: number): void {
  Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms);
}

function atomicWrite(path: string, text: string): void {
  const tmp = `${path}.tmp`;
  writeFileSync(tmp, text, "utf-8");
  let lastErr: unknown;
  for (let i = 0; i < 5; i++) {
    try { renameSync(tmp, path); return; } catch (e) { lastErr = e; syncSleep(50); }
  }
  try { unlinkSync(tmp); } catch { /* ignore */ }
  throw lastErr;
}

export function polishStatePath(cwd: string, sessionId: string): string {
  return join(cwd, "sessions", ".factory-transcripts", sessionId, "polish-state.json");
}
export function polishCommandsDir(cwd: string, sessionId: string): string {
  return join(cwd, "sessions", ".factory-transcripts", sessionId, "polish-commands");
}

export function readPolishState(path: string): PolishStateFile | null {
  try { return parsePolishStateFile(readFileSync(path, "utf-8")); } catch { return null; }
}

let _seq = 0;
export function writePolishCommand(commandsDir: string, cmd: PolishCommand): void {
  mkdirSync(commandsDir, { recursive: true });
  const name = `${Date.now()}-${String(_seq++).padStart(4, "0")}.json`;
  atomicWrite(join(commandsDir, name), JSON.stringify(cmd));
}
```

- [ ] **Step 4: Run test + typecheck**

Run: `cd pi-ext/factory-watch && npx vitest run test/polish-protocol.test.ts && npx tsc --noEmit`
Expected: PASS; no TS errors.

- [ ] **Step 5: Commit**

```bash
git add pi-ext/factory-watch/src/polish-protocol.ts pi-ext/factory-watch/test/polish-protocol.test.ts
git commit -m "feat(factory-watch): polish-protocol read-state/write-command file bridge"
```

---

### Task 5: `polish-overlay.ts` — the TUI control panel (TS)

**Files:**
- Create: `pi-ext/factory-watch/src/polish-overlay.ts`
- Test: `pi-ext/factory-watch/test/polish-overlay.test.ts`

**Interfaces:**
- Consumes: `PolishState` (Task 3), `writePolishCommand`/`polishCommandsDir` (Task 4); the pi-tui `Component` interface and `ui.custom` pattern EXACTLY as `ReviewOverlay` uses them (`review-overlay.ts` — follow its class shape, render→lines, and input handling for pi-tui conformance).
- Produces: `renderPolishPanel(state, mode): string[]` and `keyToCommand(key, state, mode): PolishCommand | null` (pure; unit-tested); `class PolishOverlay implements Component` (injected command-writer for direct accept/discard/tick; returns `PolishAction` via `done()` for feedback/edit/comment/quit so the outer loop can call `ui.editor`); `PanelMode = { typing: boolean; cursor: number; focus?: "gate1"|"gate2" }` (cursor/focus drive row selection). Consumed by Task 6.

- [ ] **Step 1: Write the failing test** (test the PURE renderer + the key→command mapping; the pi-tui Component wrapper is exercised by Task 6's integration, mirroring how `review-html.test.ts` tests the pure render and leaves the live server to integration)

```typescript
// pi-ext/factory-watch/test/polish-overlay.test.ts
import { describe, it, expect } from "vitest";
import { renderPolishPanel, keyToCommand, PolishOverlay } from "../src/polish-overlay.js";

const state = {
  usecase: "sign-in", entrypoints: ["http://localhost:3000"], queue_size: 2,
  gate1_ids: ["g1-1"], gate1: [{ gid: "g1-1", description: "sign-in broken", sr: "SR-010" }],
  gate2: [{ gid: "g2-1", task_id: "T-007", description: "fix login", sr: "SR-010", status: "landed" as const, verdict: "pending" as const }],
};

describe("renderPolishPanel", () => {
  it("shows usecase, queue depth, and both gates", () => {
    const lines = renderPolishPanel(state, { typing: false, cursor: 0 }).join("\n");
    expect(lines).toContain("sign-in");
    expect(lines).toContain("queue: 2");
    expect(lines).toContain("sign-in broken");   // gate 1
    expect(lines).toContain("T-007");             // gate 2 landed change
  });
});

describe("keyToCommand", () => {
  it("maps 'a' on a Gate-1 row to an accept command", () => {
    const cmd = keyToCommand("a", state, { typing: false, cursor: 0, focus: "gate1" });
    expect(cmd).toEqual({ kind: "accept", args: { gid: "g1-1" } });
  });
  it("maps 't' on a Gate-2 row to a tick command", () => {
    const cmd = keyToCommand("t", state, { typing: false, cursor: 0, focus: "gate2" });
    expect(cmd).toEqual({ kind: "tick", args: { gid: "g2-1" } });
  });
  it("returns null for an unmapped key", () => {
    expect(keyToCommand("z", state, { typing: false, cursor: 0, focus: "gate1" })).toBeNull();
  });
});

describe("PolishOverlay", () => {
  const fakeTui = { terminal: { rows: 24 } };
  it("writes an accept command when 'a' is pressed on a Gate-1 row", () => {
    const written: unknown[] = [];
    const o = new PolishOverlay(fakeTui, (c) => written.push(c), () => {});
    o.update(state); // focus defaults to gate1, cursor 0
    o.handleInput("a");
    expect(written).toEqual([{ kind: "accept", args: { gid: "g1-1" } }]);
  });
  it("returns a feedback action via done() when 'f' is pressed", () => {
    let action: unknown = null;
    const o = new PolishOverlay(fakeTui, () => {}, (a) => { action = a; });
    o.update(state);
    o.handleInput("f");
    expect(action).toEqual({ type: "feedback" });
  });
  it("returns quit on 'q'", () => {
    let action: unknown = null;
    const o = new PolishOverlay(fakeTui, () => {}, (a) => { action = a; });
    o.update(state);
    o.handleInput("q");
    expect(action).toEqual({ type: "quit" });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd pi-ext/factory-watch && npx vitest run test/polish-overlay.test.ts`
Expected: FAIL — cannot find `../src/polish-overlay.js`.

- [ ] **Step 3: Implement the pure renderer + key mapping, then the Component wrapper**

```typescript
// pi-ext/factory-watch/src/polish-overlay.ts
import type { PolishCommand, PolishState } from "./polish-model.js";

export interface PanelMode { typing: boolean; cursor: number; focus?: "gate1" | "gate2" }

export function renderPolishPanel(state: PolishState, mode: PanelMode): string[] {
  const lines: string[] = [];
  lines.push(`Polish — ${state.usecase}    queue: ${state.queue_size}`);
  lines.push(`app: ${state.entrypoints.join("  ")}`);
  lines.push("");
  const g1active = mode.focus === "gate1";
  lines.push(`${g1active ? "▶ " : "  "}Gate 1 — review before fixing  [a]ccept [e]dit [d]iscard`);
  if (state.gate1.length === 0) lines.push("    (none)");
  state.gate1.forEach((g, i) => {
    const cur = g1active && i === mode.cursor ? "› " : "  ";
    lines.push(`  ${cur}${g.description}${g.sr ? `  (${g.sr})` : ""}`);
  });
  lines.push("");
  const g2active = mode.focus === "gate2";
  lines.push(`${g2active ? "▶ " : "  "}Gate 2 — landed changes  [t]ick done  [c]omment wrong`);
  if (state.gate2.length === 0) lines.push("    (none)");
  state.gate2.forEach((r, i) => {
    const mark = r.verdict === "accepted" ? "✓" : r.verdict === "wrong" ? "✗" : r.status === "failed" ? "!" : " ";
    const cur = g2active && i === mode.cursor ? "› " : "  ";
    lines.push(`  ${cur}${mark} ${r.task_id}  ${r.description}${r.sr ? `  (${r.sr})` : ""}`);
  });
  lines.push("");
  lines.push("↑↓ move  Tab switch gate  [f] feedback  [q] quit");
  return lines;
}

export function keyToCommand(key: string, state: PolishState, mode: PanelMode): PolishCommand | null {
  const row1 = state.gate1[mode.cursor];
  const row2 = state.gate2[mode.cursor];
  if (mode.focus === "gate1" && row1) {
    if (key === "a") return { kind: "accept", args: { gid: row1.gid } };
    if (key === "d") return { kind: "discard", args: { gid: row1.gid } };
  }
  if (mode.focus === "gate2" && row2) {
    if (key === "t") return { kind: "tick", args: { gid: row2.gid } };
  }
  return null;
}
```

Then add the `PolishOverlay` Component. It implements the real pi-tui `Component`
(`render(width): string[]`, `handleInput(data)`, `invalidate()` — confirmed in
`node_modules/@earendil-works/pi-tui/dist/tui.d.ts`). Key insight from
`review-overlay.ts`: **free-text is NOT buffered in the overlay** — the overlay
returns an *action* via `done()` and the outer loop (Task 6) calls `ui.editor()`.
Direct commands (accept/discard/tick) are written from inside the overlay via an
injected writer so the panel stays open and live. Import `Key`, `matchesKey`,
`truncateToWidth` from the same module `review-overlay.ts` imports them from
(copy its import line verbatim).

```typescript
// append to pi-ext/factory-watch/src/polish-overlay.ts
import { Key, matchesKey, truncateToWidth } from "@earendil-works/pi-tui"; // match review-overlay.ts's import source
import type { Component } from "@earendil-works/pi-tui";

export type PolishAction =
  | { type: "feedback" }
  | { type: "edit"; gid: string; description: string }
  | { type: "comment"; gid: string }
  | { type: "quit" };

interface TuiLike { terminal: { rows: number } }

export class PolishOverlay implements Component {
  private state: PolishState = { usecase: "", entrypoints: [], queue_size: 0, gate1_ids: [], gate1: [], gate2: [] };
  private cursor = 0;
  private focus: "gate1" | "gate2" = "gate1";

  // Explicit field assignment (not TS parameter properties) — same reason as
  // ReviewOverlay: this module is also reachable via a plain `node <file>.ts`
  // import chain.
  private readonly tui: TuiLike;
  private readonly write: (cmd: PolishCommand) => void;
  private readonly done: (a: PolishAction) => void;
  constructor(tui: TuiLike, write: (cmd: PolishCommand) => void, done: (a: PolishAction) => void) {
    this.tui = tui;
    this.write = write;
    this.done = done;
  }

  update(state: PolishState): void {
    this.state = state;
    const rows = this.focus === "gate1" ? state.gate1.length : state.gate2.length;
    if (this.cursor >= rows) this.cursor = Math.max(0, rows - 1);
  }

  invalidate(): void {}

  private rowsFor(focus: "gate1" | "gate2"): number {
    return focus === "gate1" ? this.state.gate1.length : this.state.gate2.length;
  }

  handleInput(data: string): void {
    if (matchesKey(data, Key.escape) || data === "q") { this.done({ type: "quit" }); return; }
    if (data === "\t") { this.focus = this.focus === "gate1" ? "gate2" : "gate1"; this.cursor = 0; return; }
    if (matchesKey(data, Key.down) || data === "j") {
      this.cursor = Math.min(this.cursor + 1, Math.max(0, this.rowsFor(this.focus) - 1)); return;
    }
    if (matchesKey(data, Key.up) || data === "k") { this.cursor = Math.max(this.cursor - 1, 0); return; }
    if (data === "f") { this.done({ type: "feedback" }); return; }
    if (data === "e" && this.focus === "gate1") {
      const row = this.state.gate1[this.cursor];
      if (row) this.done({ type: "edit", gid: row.gid, description: row.description });
      return;
    }
    if (data === "c" && this.focus === "gate2") {
      const row = this.state.gate2[this.cursor];
      if (row) this.done({ type: "comment", gid: row.gid });
      return;
    }
    const cmd = keyToCommand(data, this.state, { typing: false, cursor: this.cursor, focus: this.focus });
    if (cmd) this.write(cmd); // accept / discard / tick — stays open; the poll reflects the new state
  }

  render(width: number): string[] {
    const lines = renderPolishPanel(this.state, { typing: false, cursor: this.cursor, focus: this.focus });
    // pi-tui hard-throws on any over-width line — truncate, exactly like ReviewOverlay.render.
    return lines.map((l) => truncateToWidth(l, width));
  }
}
```

- [ ] **Step 4: Run test + typecheck**

Run: `cd pi-ext/factory-watch && npx vitest run test/polish-overlay.test.ts && npx tsc --noEmit`
Expected: PASS (renderer + key-map tests); no TS errors.

- [ ] **Step 5: Commit**

```bash
git add pi-ext/factory-watch/src/polish-overlay.ts pi-ext/factory-watch/test/polish-overlay.test.ts
git commit -m "feat(factory-watch): polish-overlay TUI panel (render + key->command)"
```

---

### Task 6: `/polish` command — spawn orchestrator, poll state, drive the panel (TS)

**Files:**
- Modify: `pi-ext/factory-watch/src/index.ts` (register `polish` command)
- Test: `pi-ext/factory-watch/test/polish-command.test.ts` (unit-test the state-poll → overlay-update glue with a fake state file; the live spawn is manual)

**Interfaces:**
- Consumes: `readPolishState`/`polishStatePath`/`polishCommandsDir` (Task 4), `PolishOverlay` (Task 5), the `pi.registerCommand` + `ctx.ui.custom` + polling patterns already in `index.ts` (`runMissionControl`, `startBackgroundWidgetPoll`).
- Produces: a `/polish [<playground>:<usecase>]` command that (1) spawns `python -m factory.polish serve --project-root <cwd> --playground <p> --usecase <uc> --session <id>` (the Task-2 serve loop), (2) opens the panel via `ui.custom` with a `PolishOverlay`, (3) polls `polish-state.json` on an interval and pushes new state into the overlay when `seq` increases, (4) on quit, stops the poll and signals the Python `serve` to teardown (delete the session dir sentinel / terminate the child).

- [ ] **Step 1: Write the failing test** (pure glue: a `pollOnce` helper that reads the state file and returns the parsed state only if `seq` advanced)

```typescript
// pi-ext/factory-watch/test/polish-command.test.ts
import { describe, it, expect } from "vitest";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pollPolishState } from "../src/index.js";

describe("pollPolishState", () => {
  it("returns state only when seq advances past lastSeq", () => {
    const dir = mkdtempSync(join(tmpdir(), "pc-"));
    const p = join(dir, "s.json");
    writeFileSync(p, JSON.stringify({ seq: 2, state: { usecase: "x", entrypoints: [], queue_size: 0, gate1_ids: [], gate1: [], gate2: [] } }));
    expect(pollPolishState(p, 1)?.seq).toBe(2);
    expect(pollPolishState(p, 2)).toBeNull(); // no advance
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd pi-ext/factory-watch && npx vitest run test/polish-command.test.ts`
Expected: FAIL — `pollPolishState` is not exported.

- [ ] **Step 3: Implement `pollPolishState` + register the command**

```typescript
// add near the other helpers in index.ts, and export it for the test
export function pollPolishState(statePath: string, lastSeq: number) {
  const parsed = readPolishState(statePath);
  if (parsed && parsed.seq > lastSeq) return parsed;
  return null;
}
```

Add the imports and register the command inside the default `factoryWatch(pi)`
export. The live-refresh pattern (`setInterval` → `tui.requestRender()`, cleared
on `done`) mirrors `runMissionControl`'s dashboard poll (`index.ts:74-80`); the
child-process spawn mirrors `launchAndWatch`/`spawnInteractive`.

```typescript
// imports at the top of index.ts
import { spawn } from "node:child_process";
import { PolishOverlay, type PolishAction } from "./polish-overlay.js";
import {
  polishCommandsDir, polishStatePath, readPolishState, writePolishCommand,
} from "./polish-protocol.js";

function parsePolishTarget(args: string): { playground: string; usecase: string } | null {
  const m = /^(\S+):(\S+)$/.exec(args.trim());
  return m ? { playground: m[1]!, usecase: m[2]! } : null;
}

// inside factoryWatch(pi):
pi.registerCommand("polish", {
  description: "Run a factory polish session (deterministic orchestrator + control panel)",
  handler: async (args, ctx) => {
    const target = parsePolishTarget(args);
    if (!target) { ctx.ui.notify("usage: /polish <playground>:<usecase>", "error"); return; }
    const sessionId = `polish-${Date.now()}`;
    const statePath = polishStatePath(ctx.cwd, sessionId);
    const cmdsDir = polishCommandsDir(ctx.cwd, sessionId);
    // The Python serve loop starts the app (front+back), opens the browser,
    // publishes polish-state.json, and consumes polish-commands/*.json.
    const child = spawn(
      "python",
      ["-m", "factory.polish", "serve", "--project-root", ctx.cwd,
       "--playground", target.playground, "--usecase", target.usecase, "--session", sessionId],
      { cwd: ctx.cwd, stdio: "ignore" },
    );
    let lastSeq = 0;
    try {
      for (;;) {
        const action = await ctx.ui.custom<PolishAction>((tui, _theme, _kb, done) => {
          let poll: ReturnType<typeof setInterval> | undefined;
          const overlay = new PolishOverlay(
            tui,
            (cmd) => writePolishCommand(cmdsDir, cmd),
            (a) => { if (poll) clearInterval(poll); done(a); },
          );
          const first = pollPolishState(statePath, 0);
          if (first) { lastSeq = first.seq; overlay.update(first.state); }
          poll = setInterval(() => {
            try {
              const s = pollPolishState(statePath, lastSeq);
              if (s) { lastSeq = s.seq; overlay.update(s.state); tui.requestRender(); }
            } catch { if (poll) clearInterval(poll); } // ctx.ui can throw after a session reload
          }, 200);
          return overlay as unknown as ReturnType<Parameters<typeof ctx.ui.custom>[0]>;
        });
        if (action.type === "quit") break;
        if (action.type === "feedback") {
          const text = await ctx.ui.editor(`Feedback — ${target.usecase}`, "");
          if (text) writePolishCommand(cmdsDir, { kind: "feedback", args: { text } });
        } else if (action.type === "edit") {
          const text = await ctx.ui.editor("Edit finding description", action.description);
          if (text) writePolishCommand(cmdsDir, { kind: "edit", args: { gid: action.gid, changes: { description: text } } });
        } else if (action.type === "comment") {
          const text = await ctx.ui.editor("What's wrong with this change?", "");
          if (text) writePolishCommand(cmdsDir, { kind: "comment", args: { gid: action.gid, text } });
        }
      }
    } finally {
      child.kill(); // SIGTERM → the serve loop's handler tears down both dev-servers + the worker
    }
  },
});
```

The Python `serve` subcommand (Plan B2 Task 2) must install a SIGTERM handler that
sets its `should_stop` flag, so `child.kill()` cleanly stops the loop and runs
`orchestrator.teardown()`.

- [ ] **Step 4: Run tests + typecheck + full factory-watch suite**

Run: `cd pi-ext/factory-watch && npx vitest run && npx tsc --noEmit`
Expected: PASS (all existing + new polish tests); no TS errors.

- [ ] **Step 5: Manual live check (not automated).** From CareerOS, run `/polish web:sign-in`: the CareerOS app opens in the browser, the panel shows the running app; type feedback → a Gate-1 row appears → `a` accept → the worker runs factory-run in the background → a Gate-2 row appears on hot-reload → `t` tick or `c` comment. Confirm teardown stops both dev-servers.

- [ ] **Step 6: Commit**

```bash
git add pi-ext/factory-watch/src/index.ts pi-ext/factory-watch/test/polish-command.test.ts
git commit -m "feat(factory-watch): /polish command — spawn orchestrator, poll state, drive panel"
```

---

## Self-Review

**Spec coverage (Inc 2 design §4.1 nodes surfaced + §7 UI):**
- §7 feedback input — Task 5 (`f` typing mode → `feedback` command) + Task 6 spawn/poll. ✅
- §7 live queue / fix-progress — `queue_size` + Gate 2 rows with `status` (landed/failed), Task 5 renderer. ✅
- §6.1 Gate 1 accept/edit/discard — Task 5 key-map + Task 1 dispatch. ✅
- §6.2 Gate 2 tick/comment (comment→rework) — Task 5 key-map + Task 1 dispatch → orchestrator (Plan B). ✅
- §4.1 browser opens — handled by the orchestrator's `open_navigator` (Plan B core); this plan renders the *control* panel, correctly NOT a second web surface. ✅
- Cross-process bridge (the whole point) — Tasks 1–4, atomic files, exactly-once command consumption. ✅

**Placeholder scan:** All six tasks have complete code, including the `PolishOverlay` Component (Task 5, against the real `render`/`handleInput`/`invalidate` interface confirmed in `tui.d.ts`, with unit tests for the key→command and key→action mappings) and the full `/polish` handler (Task 6, with the `setInterval`→`requestRender` live-refresh cleared on `done`, mirroring `index.ts:74-80`). The only "match the existing source" note is the one import line for `Key`/`matchesKey`/`truncateToWidth` (copy `review-overlay.ts`'s import), which is a verified in-repo fact, not unwritten logic. No `TODO`/`TBD`. ✅

**Type consistency:** the `PolishState`/`Gate1Item`/`Gate2Row` fields (Task 3) match `PolishOrchestrator.state()` keys (Plan B Task 6) one-for-one; the `PolishCommand` kinds (Task 3) match `PolishBridge.dispatch` branches (Task 1) and the orchestrator method names; `polishCommandsDir`/`polishStatePath` are used identically in Tasks 4/6 and mirror the Python `PolishBridge` paths (agree the session-relative path with Task 2's `serve` wiring — both must resolve `sessions/.factory-transcripts/<sessionId>/`). ✅

**Cross-plan note:** Tasks 2 and 6 must agree on the exact CLI: `python -m factory.polish serve --project-root <cwd> --playground <p> --usecase <uc> --session <sessionId>`, and on the session-relative bridge paths. Verify against Plan B Task 7's `build_orchestrator` signature when executing.
