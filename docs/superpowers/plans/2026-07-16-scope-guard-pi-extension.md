# Scope-Guard Pi Extension Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `scope-guard`, a TypeScript Pi extension that deterministically blocks any file write/edit outside a per-agent path allowlist and blocks bash unless explicitly permitted — the sole write-scope enforcement for the dev factory.

**Architecture:** A Pi extension (default-exported `(pi) => void`) that registers a single `tool_call` interceptor. All decision logic lives in **pure, unit-tested functions** (`allow.ts`, `policy.ts`); the interceptor (`index.ts`) is a thin adapter reading `PI_SCOPE_ALLOW` / `PI_SCOPE_BASH` from the environment (set per-node by the orchestrator). Enforcement is unconditional in headless mode — no UI prompts, no inference. Because this is the only guard (no orchestrator backstop, by design decision), the pure logic is tested exhaustively and wired to its own gate.

**Tech Stack:** TypeScript (strict, NodeNext), `vitest` (tests), `minimatch` (glob matching). Types come from `@earendil-works/pi-coding-agent` at runtime; for self-contained typechecking/testing we declare a minimal structural interface and note the swap.

## Global Constraints

- Runtime target: **Node ≥ 18**, TypeScript **strict** mode, `moduleResolution: "nodenext"`.
- Platform is **Windows 10**; paths arriving in `event.input.path` may be absolute (`C:\...`) or use `\` separators. **All path logic normalizes to repo-relative POSIX (`/`) before glob matching.**
- Enforcement is **deterministic and headless-first**: decisions depend only on `event.toolName`, `event.input`, and the two env vars — never on UI, model calls, or randomness.
- **Env contract (set by the orchestrator per agent node):**
  - `PI_SCOPE_ALLOW` — comma-separated repo-relative globs of writable paths. Unset/empty ⇒ **no writes allowed** (read-only role).
  - `PI_SCOPE_BASH` — `"allow"` or `"deny"`. Unset ⇒ **`"deny"`** (fail-closed).
- **Fail closed:** any parse ambiguity, missing path, or unknown write-tool target ⇒ block.
- Every task ends green (`npm run typecheck`, `npm test`) and is committed.

---

## File Structure

```
pi-ext/scope-guard/
  package.json
  tsconfig.json
  vitest.config.ts
  src/
    pi-types.ts        # minimal structural types for the Pi extension API
    allow.ts           # parseAllow(), toRepoRelative(), isPathAllowed()  (pure)
    policy.ts          # parseBashPolicy(), decide()  (pure decision core)
    index.ts           # default export: registers the tool_call interceptor
  test/
    allow.test.ts
    policy.test.ts
    handler.test.ts
  README.md
scripts/gates/
  ext.py               # factory gate: runs the extension's typecheck + tests
```

---

### Task 1: TypeScript project scaffold

**Files:**
- Create: `pi-ext/scope-guard/package.json`, `pi-ext/scope-guard/tsconfig.json`, `pi-ext/scope-guard/vitest.config.ts`, `pi-ext/scope-guard/src/pi-types.ts`
- Test: `pi-ext/scope-guard/test/smoke.test.ts`

**Interfaces:**
- Consumes: nothing.
- Produces: a buildable/testable TS package; `ToolCallEvent`, `ExtCtx`, `ToolCallResult`, `PiApi` types importable from `src/pi-types.ts`.

- [ ] **Step 1: Write `package.json`**

```json
{
  "name": "@factory/scope-guard",
  "version": "0.0.1",
  "private": true,
  "type": "module",
  "scripts": {
    "typecheck": "tsc --noEmit",
    "test": "vitest run"
  },
  "devDependencies": {
    "typescript": "^5.5.0",
    "vitest": "^2.0.0",
    "minimatch": "^10.0.0"
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
// Minimal structural subset of Pi's ExtensionAPI we depend on.
// At runtime Pi passes its real ExtensionAPI (a superset); this keeps the
// extension typecheckable/testable without installing the Pi package.
// Swap `PiApi` for `import type { ExtensionAPI }` once the dep is present.

export interface ToolCallEvent {
  toolName: string;
  input: { path?: string; command?: string };
}

export interface ExtCtx {
  cwd: string;
  hasUI?: boolean;
  mode?: "tui" | "rpc" | "json" | "print";
}

export type ToolCallResult = { block: true; reason: string } | undefined;

export type ToolCallHandler = (
  event: ToolCallEvent,
  ctx: ExtCtx,
) => Promise<ToolCallResult> | ToolCallResult;

export interface PiApi {
  on(event: "tool_call", handler: ToolCallHandler): void;
}
```

- [ ] **Step 5: Write the smoke test**

```typescript
// test/smoke.test.ts
import { expect, test } from "vitest";
import type { PiApi } from "../src/pi-types.js";

test("types import and a fake PiApi can register a handler", () => {
  const registered: string[] = [];
  const pi: PiApi = { on: (name) => registered.push(name) };
  pi.on("tool_call", () => undefined);
  expect(registered).toEqual(["tool_call"]);
});
```

- [ ] **Step 6: Install and run**

```bash
cd pi-ext/scope-guard
npm install
npm run typecheck
npm test
```
Expected: typecheck clean, `1 passed`.

- [ ] **Step 7: Commit**

```bash
git add pi-ext/scope-guard/package.json pi-ext/scope-guard/tsconfig.json pi-ext/scope-guard/vitest.config.ts pi-ext/scope-guard/src/pi-types.ts pi-ext/scope-guard/test/smoke.test.ts
git commit -m "chore: scaffold scope-guard pi extension (ts + vitest)"
```

---

### Task 2: Path allowlist logic (pure)

**Files:**
- Create: `pi-ext/scope-guard/src/allow.ts`
- Test: `pi-ext/scope-guard/test/allow.test.ts`

**Interfaces:**
- Consumes: `minimatch`.
- Produces (all pure, no I/O):
  - `parseAllow(raw: string | undefined): string[]` — split on commas, trim, drop empties.
  - `toRepoRelative(p: string, cwd: string): string` — normalize `\`→`/`, strip a leading `cwd` prefix (also normalized) to yield a repo-relative POSIX path with no leading `/`.
  - `isPathAllowed(p: string, cwd: string, globs: string[]): boolean` — true iff the repo-relative path matches at least one glob. Empty globs ⇒ always false.

- [ ] **Step 1: Write the failing test**

```typescript
// test/allow.test.ts
import { describe, expect, test } from "vitest";
import { parseAllow, toRepoRelative, isPathAllowed } from "../src/allow.js";

describe("parseAllow", () => {
  test("splits, trims, drops empties", () => {
    expect(parseAllow(" src/**, tests/** ,")).toEqual(["src/**", "tests/**"]);
  });
  test("undefined yields empty", () => {
    expect(parseAllow(undefined)).toEqual([]);
  });
});

describe("toRepoRelative", () => {
  test("normalizes backslashes", () => {
    expect(toRepoRelative("src\\drone\\x.py", "C:/repo")).toBe("src/drone/x.py");
  });
  test("strips absolute cwd prefix (windows)", () => {
    expect(toRepoRelative("C:\\repo\\src\\x.py", "C:\\repo")).toBe("src/x.py");
  });
});

describe("isPathAllowed", () => {
  const cwd = "C:/repo";
  test("matches a glob", () => {
    expect(isPathAllowed("src/x.py", cwd, ["src/**"])).toBe(true);
  });
  test("absolute path under cwd matches", () => {
    expect(isPathAllowed("C:\\repo\\src\\x.py", cwd, ["src/**"])).toBe(true);
  });
  test("outside allowlist is denied", () => {
    expect(isPathAllowed("secrets/.env", cwd, ["src/**"])).toBe(false);
  });
  test("empty globs deny everything", () => {
    expect(isPathAllowed("src/x.py", cwd, [])).toBe(false);
  });
});
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd pi-ext/scope-guard && npm test
```
Expected: FAIL — `../src/allow.js` not found.

- [ ] **Step 3: Implement `src/allow.ts`**

```typescript
import { minimatch } from "minimatch";

export function parseAllow(raw: string | undefined): string[] {
  if (!raw) return [];
  return raw
    .split(",")
    .map((s) => s.trim())
    .filter((s) => s.length > 0);
}

function normalize(p: string): string {
  return p.replace(/\\/g, "/");
}

export function toRepoRelative(p: string, cwd: string): string {
  const np = normalize(p);
  const nc = normalize(cwd).replace(/\/+$/, "");
  let rel = np;
  if (np.toLowerCase().startsWith(nc.toLowerCase() + "/")) {
    rel = np.slice(nc.length + 1);
  }
  return rel.replace(/^\/+/, "");
}

export function isPathAllowed(p: string, cwd: string, globs: string[]): boolean {
  if (globs.length === 0) return false;
  const rel = toRepoRelative(p, cwd);
  return globs.some((g) => minimatch(rel, g, { dot: true }));
}
```

- [ ] **Step 4: Run to pass**

```bash
cd pi-ext/scope-guard && npm test && npm run typecheck
```
Expected: all allow tests pass; typecheck clean.

- [ ] **Step 5: Commit**

```bash
git add pi-ext/scope-guard/src/allow.ts pi-ext/scope-guard/test/allow.test.ts
git commit -m "feat: pure path allowlist logic for scope-guard"
```

---

### Task 3: Decision core (write + bash policy, fail-closed)

**Files:**
- Create: `pi-ext/scope-guard/src/policy.ts`
- Test: `pi-ext/scope-guard/test/policy.test.ts`

**Interfaces:**
- Consumes: `isPathAllowed` (Task 2), `ToolCallEvent`, `ExtCtx`, `ToolCallResult` (Task 1).
- Produces:
  - `parseBashPolicy(raw: string | undefined): "allow" | "deny"` — `"allow"` only for the exact string `"allow"`; everything else ⇒ `"deny"` (fail-closed).
  - `WRITE_TOOLS: readonly string[]` = `["write", "edit"]`.
  - `decide(event: ToolCallEvent, ctx: ExtCtx, allowGlobs: string[], bash: "allow" | "deny"): ToolCallResult` — the pure enforcement decision (returns a block object or `undefined`).

- [ ] **Step 1: Write the failing test**

```typescript
// test/policy.test.ts
import { describe, expect, test } from "vitest";
import { parseBashPolicy, decide } from "../src/policy.js";
import type { ToolCallEvent, ExtCtx } from "../src/pi-types.js";

const ctx: ExtCtx = { cwd: "C:/repo", hasUI: false, mode: "print" };
const ev = (toolName: string, input: ToolCallEvent["input"]): ToolCallEvent => ({ toolName, input });

describe("parseBashPolicy", () => {
  test("only 'allow' allows; else deny (fail-closed)", () => {
    expect(parseBashPolicy("allow")).toBe("allow");
    expect(parseBashPolicy("Allow")).toBe("deny");
    expect(parseBashPolicy(undefined)).toBe("deny");
  });
});

describe("decide", () => {
  test("allows in-scope write", () => {
    expect(decide(ev("write", { path: "src/x.py" }), ctx, ["src/**"], "deny")).toBeUndefined();
  });
  test("blocks out-of-scope write", () => {
    const r = decide(ev("edit", { path: "secrets/.env" }), ctx, ["src/**"], "deny");
    expect(r?.block).toBe(true);
  });
  test("blocks write with missing path (fail-closed)", () => {
    const r = decide(ev("write", {}), ctx, ["src/**"], "deny");
    expect(r?.block).toBe(true);
  });
  test("blocks bash when policy deny", () => {
    expect(decide(ev("bash", { command: "ls" }), ctx, [], "deny")?.block).toBe(true);
  });
  test("allows bash when policy allow", () => {
    expect(decide(ev("bash", { command: "pytest" }), ctx, [], "allow")).toBeUndefined();
  });
  test("ignores unrelated read tools", () => {
    expect(decide(ev("read", { path: "anything" }), ctx, [], "deny")).toBeUndefined();
  });
});
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd pi-ext/scope-guard && npm test
```
Expected: FAIL — `../src/policy.js` not found.

- [ ] **Step 3: Implement `src/policy.ts`**

```typescript
import { isPathAllowed } from "./allow.js";
import type { ToolCallEvent, ExtCtx, ToolCallResult } from "./pi-types.js";

export const WRITE_TOOLS: readonly string[] = ["write", "edit"];

export function parseBashPolicy(raw: string | undefined): "allow" | "deny" {
  return raw === "allow" ? "allow" : "deny";
}

export function decide(
  event: ToolCallEvent,
  ctx: ExtCtx,
  allowGlobs: string[],
  bash: "allow" | "deny",
): ToolCallResult {
  if (event.toolName === "bash") {
    if (bash === "deny") {
      return { block: true, reason: "scope-guard: bash is disabled for this agent role" };
    }
    return undefined;
  }

  if (WRITE_TOOLS.includes(event.toolName)) {
    const path = event.input.path;
    if (!path) {
      return { block: true, reason: "scope-guard: write tool called without a path" };
    }
    if (!isPathAllowed(path, ctx.cwd, allowGlobs)) {
      return { block: true, reason: `scope-guard: '${path}' is outside this agent's write scope` };
    }
  }

  return undefined;
}
```

- [ ] **Step 4: Run to pass**

```bash
cd pi-ext/scope-guard && npm test && npm run typecheck
```
Expected: policy tests pass; typecheck clean.

- [ ] **Step 5: Commit**

```bash
git add pi-ext/scope-guard/src/policy.ts pi-ext/scope-guard/test/policy.test.ts
git commit -m "feat: fail-closed write/bash decision core for scope-guard"
```

---

### Task 4: Extension entry point (interceptor wiring)

**Files:**
- Create: `pi-ext/scope-guard/src/index.ts`
- Test: `pi-ext/scope-guard/test/handler.test.ts`

**Interfaces:**
- Consumes: `parseAllow` (Task 2), `parseBashPolicy`, `decide` (Task 3), `PiApi` (Task 1).
- Produces: default-exported `(pi: PiApi) => void` that registers a `tool_call` handler reading `PI_SCOPE_ALLOW` / `PI_SCOPE_BASH` from `process.env` at call time and delegating to `decide`.

- [ ] **Step 1: Write the failing test**

```typescript
// test/handler.test.ts
import { afterEach, describe, expect, test } from "vitest";
import scopeGuard from "../src/index.js";
import type { PiApi, ToolCallHandler, ToolCallEvent, ExtCtx } from "../src/pi-types.js";

function capture(): { handler: ToolCallHandler; pi: PiApi } {
  let handler: ToolCallHandler | undefined;
  const pi: PiApi = { on: (_e, h) => (handler = h) };
  scopeGuard(pi);
  if (!handler) throw new Error("no handler registered");
  return { handler, pi };
}

const ctx: ExtCtx = { cwd: "C:/repo", hasUI: false, mode: "print" };
const ev = (toolName: string, input: ToolCallEvent["input"]): ToolCallEvent => ({ toolName, input });

afterEach(() => {
  delete process.env.PI_SCOPE_ALLOW;
  delete process.env.PI_SCOPE_BASH;
});

describe("scope-guard handler", () => {
  test("blocks write outside PI_SCOPE_ALLOW", async () => {
    process.env.PI_SCOPE_ALLOW = "src/**";
    const { handler } = capture();
    const r = await handler(ev("write", { path: "kb/secret.md" }), ctx);
    expect(r?.block).toBe(true);
  });

  test("allows write inside PI_SCOPE_ALLOW", async () => {
    process.env.PI_SCOPE_ALLOW = "src/**,tests/**";
    const { handler } = capture();
    expect(await handler(ev("write", { path: "tests/x.test.py" }), ctx)).toBeUndefined();
  });

  test("no allow env means all writes blocked (read-only role)", async () => {
    const { handler } = capture();
    expect((await handler(ev("edit", { path: "src/x.py" }), ctx))?.block).toBe(true);
  });

  test("bash blocked by default, allowed when PI_SCOPE_BASH=allow", async () => {
    const { handler } = capture();
    expect((await handler(ev("bash", { command: "ls" }), ctx))?.block).toBe(true);
    process.env.PI_SCOPE_BASH = "allow";
    expect(await handler(ev("bash", { command: "ls" }), ctx)).toBeUndefined();
  });
});
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd pi-ext/scope-guard && npm test
```
Expected: FAIL — `../src/index.js` not found.

- [ ] **Step 3: Implement `src/index.ts`**

```typescript
import { parseAllow } from "./allow.js";
import { parseBashPolicy, decide } from "./policy.js";
import type { PiApi } from "./pi-types.js";

// Pi loads this via: pi --extension pi-ext/scope-guard/src/index.ts
// The orchestrator sets PI_SCOPE_ALLOW / PI_SCOPE_BASH per agent node.
export default function scopeGuard(pi: PiApi): void {
  pi.on("tool_call", (event, ctx) => {
    const allowGlobs = parseAllow(process.env.PI_SCOPE_ALLOW);
    const bash = parseBashPolicy(process.env.PI_SCOPE_BASH);
    return decide(event, ctx, allowGlobs, bash);
  });
}
```

- [ ] **Step 4: Run to pass**

```bash
cd pi-ext/scope-guard && npm test && npm run typecheck
```
Expected: handler tests pass; typecheck clean.

- [ ] **Step 5: Commit**

```bash
git add pi-ext/scope-guard/src/index.ts pi-ext/scope-guard/test/handler.test.ts
git commit -m "feat: scope-guard extension entry wiring env to decision core"
```

---

### Task 5: Factory gate + README + live Pi load verification

**Files:**
- Create: `scripts/gates/ext.py`, `pi-ext/scope-guard/README.md`
- Test: `tests/gates/test_ext_gate.py`

**Interfaces:**
- Consumes: `run_and_propagate` from `scripts/gates/_proc.py` (Plan 1, Task 9).
- Produces: `scripts/gates/ext.py` runs the extension's typecheck + tests via npm, propagating the exit code, so the factory's gate set covers the extension.

- [ ] **Step 1: Write the failing test**

```python
# tests/gates/test_ext_gate.py
import subprocess
import sys
import pytest

pytestmark = pytest.mark.unit


def test_ext_gate_passes():
    rc = subprocess.run([sys.executable, "scripts/gates/ext.py"]).returncode
    assert rc == 0
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/gates/test_ext_gate.py -v`
Expected: FAIL — `scripts/gates/ext.py` missing.

- [ ] **Step 3: Implement `scripts/gates/ext.py`**

```python
# scripts/gates/ext.py
import sys
from pathlib import Path
from _proc import run_and_propagate

EXT_DIR = Path(__file__).resolve().parents[2] / "pi-ext" / "scope-guard"

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
# scope-guard — Pi extension

Deterministic write-scope enforcement for factory agents. Blocks `write`/`edit`
outside an allowlist and blocks `bash` unless permitted. This is the *sole*
scope guard (no orchestrator backstop, by design) — treat its tests as
safety-critical.

## Env contract (set per agent node by the orchestrator)
- `PI_SCOPE_ALLOW` — comma-separated repo-relative globs of writable paths.
  Unset/empty ⇒ no writes allowed (read-only role).
- `PI_SCOPE_BASH` — `allow` | `deny`. Unset ⇒ `deny` (fail-closed).

## Load into Pi
```
pi --extension pi-ext/scope-guard/src/index.ts -p "<prompt>" --mode json
```

## Test
```
npm --prefix pi-ext/scope-guard run typecheck
npm --prefix pi-ext/scope-guard test
```
```

- [ ] **Step 5: Run the gate to pass**

Run: `uv run pytest tests/gates/test_ext_gate.py -v` → 1 passed.
Run: `uv run python scripts/gates/ext.py; echo "exit=$?"` → exit=0.

- [ ] **Step 6: Live Pi load spike (manual verification, once)**

> This confirms the real Pi runtime accepts the extension and enforces headlessly.
> If Pi is not yet installed, install per its docs (`npm i -g @earendil-works/pi-coding-agent` or the one-line installer), then:

```bash
# In an empty scratch dir, with a fake write target:
PI_SCOPE_ALLOW="src/**" PI_SCOPE_BASH="deny" \
  pi --extension "$(pwd)/pi-ext/scope-guard/src/index.ts" \
  -p "create a file kb/hack.md with the text 'x'" --mode json
```
Expected: the write is blocked with reason `scope-guard: 'kb/hack.md' is outside this agent's write scope` (the agent cannot create the file). Record the observed JSON event shape in the commit message — Plan 3's `PiAgentBackend` parses this stream.

- [ ] **Step 7: Commit**

```bash
git add scripts/gates/ext.py pi-ext/scope-guard/README.md tests/gates/test_ext_gate.py
git commit -m "feat: factory gate and docs for scope-guard extension"
```

---

## Self-Review

**Spec coverage (against `2026-07-16-deterministic-agent-dev-factory-design.md`):**
- §2 principle 2 (deterministic boundaries) and §6 per-agent permission profiles → the whole extension: writes constrained to a per-role allowlist, bash fail-closed, no inference.
- §10 "permission gates + path protection" → implemented as a Pi extension per the confirmed API (`pi.on("tool_call")` → `{ block, reason }`).
- Design decision (this session): **extensions-only enforcement, no orchestrator backstop** → no git-diff check anywhere here; the extension is the single guard, hence exhaustive pure-function tests (Tasks 2–3) and a dedicated gate (Task 5).
- **Deferred to Plan 3 (orchestrator):** setting `PI_SCOPE_ALLOW`/`PI_SCOPE_BASH` per node, spawning `pi --extension ... --mode json`, and parsing the event stream. This plan delivers only the guard and proves it loads.

**Placeholder scan:** none. The only non-code step (Task 5, Step 6) is a live-runtime verification with an exact command and expected output; it is explicitly a one-time manual spike, not hidden logic.

**Type consistency:** `ToolCallEvent`/`ExtCtx`/`ToolCallResult`/`PiApi`/`ToolCallHandler` defined in Task 1 and consumed unchanged in Tasks 2–4; `parseAllow`/`toRepoRelative`/`isPathAllowed` (Task 2) used by `decide` (Task 3); `parseBashPolicy`/`decide` (Task 3) used by `index.ts` (Task 4); `run_and_propagate` (Plan 1 Task 9) used by Task 5.

**Risk flagged inline:** the published `@earendil-works/pi-coding-agent` `ExtensionAPI` type may differ from our minimal `PiApi`; Task 1 notes the swap, and the runtime is structurally compatible (we only use `pi.on`). The live JSON event shape is confirmed by the Task 5 spike before Plan 3 depends on it.
```
