# Polish Session Playground/Usecase Selection Menu — Implementation Plan

**Spec:** docs/superpowers/specs/2026-08-21-polish-menu-playground-usecase.md

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A factory **polish session** should spawn an interactive selection menu — exactly like `/factory-run`'s ticket selection (`ctx.ui.select("Run which task?", ...)`) — so an operator can pick *which playground* and *which usecase* to polish, instead of having to remember and type `<playground>:<usecase>` every time.

**Architecture:** Two independent, order-dependent halves sharing one JSON contract.

1. **Python CLI (R1 = this factory repo).** `factory polish list` already prints flat `playground:usecase` lines. Add a `--json` flag whose output is a structured list the TS side can consume:
   ```json
   [{"playground": "sim-live", "usecases": ["scn_001", "scn_002", ...]}, ...]
   ```
   Plain `list` keeps its existing text output and behaviour (pinned by an existing test).

2. **TS extension (R1 = `pi-ext/factory-watch`).** The `/polish` command handler currently errors with `usage: /polish <playground>:<usecase>` when no target is given. When the argument is **empty**, instead fetch the `polish list --json` output and present two sequential menus via `ctx.ui.select` — first the playground, then the usecase for that playground — exactly mirroring `/factory-run`. When an explicit `<playground>:<usecase>` argument IS given, keep the current direct-launch behaviour (backwards compatible).

**Tech stack / repos:** R1 = `C:/coding/pi-agent-factory`. Python CLI uses argparse + `factory.polish.config.load_config`; tests under `tests/unit/polish/` (`-m unit`). TS uses vitest (`pi-ext/factory-watch/test/`), tsc `--noEmit` typecheck. There are **pre-existing dirty files** in R1 (e.g. `src/factory-init-command.ts` has a pre-existing typecheck error about `./tool-catalog.js`) — do not touch them, and do not report them as your responsibility.

## Design decisions (ground truth)

1. **Keep `cmd_list` text behaviour; add a sibling `cmd_list_json`.** A new `--json` flag on the `list` subparser returns structured data, while `cmd_list` (text) is untouched so `test_cmd_list` stays green. `cmd_list_json(project_root) -> str` returns `json.dumps([{"playground": name, "usecases": pg.list_usecases()} for name, pg in ...])`.
2. **`list --json` runs with `cwd = ctx.cwd` in the TS spawn, so `--project-root` defaults to `.`.** No project-root flag needs to be passed from TS (matches how `orchestrator list --json` already works from `/factory-run`).
3. **`ctx.ui.select` returns the selected option string (or `undefined` when cancelled).** The playground menu's options are formatted labels like `sim-live (11 usecases)`; the selected label is parsed back to the playground id via a pure helper. The usecase menu's options are the bare usecase stems, returned verbatim.
4. **The JSON contract is the only thing the two halves share.** Parsing/validation of `list --json` output lives in a pure TS module (`polish-picker.ts`) so it is unit-testable without a subprocess; malformed/empty JSON degrades to a `ctx.ui.notify` + abort, never a crash.

---

### Task 1: `polish list --json` in the Python CLI (T-1, R1)

**Files:**
- Modify: `src/factory/polish/cli.py` (R1)
- Modify: `tests/unit/polish/test_cli.py` (R1)

**Interfaces:**
- Produces: `cmd_list_json(project_root: Path) -> str` (JSON string: list of `{"playground", "usecases"}`), and a `--json` flag recognised by the `list` subparser that routes to it in `main()`.

**Steps:**

- [ ] **Step 1: Write the failing tests** — append to `tests/unit/polish/test_cli.py`:

```python
def test_cmd_list_json_groups_usecases_by_playground(tmp_path):
    _project(tmp_path)  # single playground "ref" -> usecase shark_warning
    import json as _json
    assert _json.loads(cmd_list_json(tmp_path)) == [
        {"playground": "ref", "usecases": ["shark_warning"]}
    ]


def test_main_list_json_exit_code_and_shape(tmp_path, capsys):
    _project(tmp_path)
    import json as _json
    rc = main(["list", "--json", "--project-root", str(tmp_path)])
    assert rc == 0
    out = _json.loads(capsys.readouterr().out)
    assert out == [{"playground": "ref", "usecases": ["shark_warning"]}]
```

(Add `cmd_list_json` to the existing `from factory.polish.cli import (...)` in the test file.)

- [ ] **Step 2: Run the test file to verify it fails** — `uv run python -m pytest tests/unit/polish/test_cli.py -q`. Expected: `ImportError: cannot import name 'cmd_list_json' from 'factory.polish.cli'`.

- [ ] **Step 3: Write minimal implementation** — in `src/factory/polish/cli.py`:

(a) Add `cmd_list_json` next to `cmd_list`:

```python
def cmd_list_json(project_root: Path) -> str:
    """Return playgrounds and their usecases as a JSON string.

    Purpose: give the interactive polish picker (and anything else) structured
    playground -> usecases data to render selection menus from. The TS
    extension consumes this to offer a playground then a usecase menu when a
    polish session is started without an explicit <playground>:<usecase>.

    Args:
        project_root: the product repo root whose .factory config declares the
            playgrounds.

    Returns:
        A JSON array of objects, one per playground: ``[{"playground":
        "name", "usecases": ["a", "b"]}, ...]``.

    Raises:
        None.
    """
    groups = [
        {"playground": name, "usecases": pg.list_usecases()}
        for name, pg in load_config(project_root).playgrounds.items()
    ]
    return json.dumps(groups)
```

(b) In `main()`, give the `list` subparser the flag and route on it:

```python
    p_list = sub.add_parser("list", parents=[common])
    p_list.add_argument("--json", action="store_true")
```

```python
    if args.cmd == "list":
        print(cmd_list_json(args.project_root) if args.json else cmd_list(args.project_root))
```

- [ ] **Step 4: Run the test file to verify it passes** — `uv run python -m pytest tests/unit/polish/test_cli.py -q`. Expected: all pass (existing + 2 new).

- [ ] **Step 5: Commit** (R1, only the intended paths):

```
git add src/factory/polish/cli.py tests/unit/polish/test_cli.py
git commit -m "feat(polish): list --json playground/usecase groups (T-1)"
```

**Done when:** `uv run python -m pytest -m unit -q` green in R1; `polish list --json` returns the grouped shape; plain `polish list` unchanged.

---

### Task 2: `/polish` menu for playground and usecase (T-2, R1)

**Files:**
- Create: `pi-ext/factory-watch/src/polish-picker.ts` (R1)
- Create: `pi-ext/factory-watch/test/polish-picker.test.ts` (R1)
- Modify: `pi-ext/factory-watch/src/process-control.ts` (R1)
- Modify: `pi-ext/factory-watch/test/process-control.test.ts` (R1)
- Modify: `pi-ext/factory-watch/src/index.ts` (R1)

**Interfaces:**
- Consumes: `cmd_list_json` output contract (Task 1); `ctx.ui.select(prompt, options: string[])`; `spawnSync`; `Command` from `process-control`.
- Produces: `parsePolishGroupList(raw: string): PolishPlayground[] | null`, `polishPlaygroundLabel(pg: PolishPlayground): string`, `parsePlaygroundIdFromLabel(label: string): string | null` in `polish-picker.ts`; `buildPolishListCommand(): Command` in `process-control.ts`; a `pickPolishTarget(ctx)` helper + updated `/polish` handler in `index.ts`.

**Steps:**

- [ ] **Step 1: Write the failing TS tests** — create `test/polish-picker.test.ts`:

```ts
import { describe, expect, test } from "vitest";
import {
  parsePolishGroupList,
  polishPlaygroundLabel,
  parsePlaygroundIdFromLabel,
} from "../src/polish-picker.js";

describe("parsePolishGroupList", () => {
  test("parses the polish list --json contract", () => {
    const raw = JSON.stringify([
      { playground: "sim-live", usecases: ["scn_001", "scn_002"] },
      { playground: "ref", usecases: ["shark_warning"] },
    ]);
    expect(parsePolishGroupList(raw)).toEqual([
      { playground: "sim-live", usecases: ["scn_001", "scn_002"] },
      { playground: "ref", usecases: ["shark_warning"] },
    ]);
  });

  test("returns null on malformed JSON or bad shape", () => {
    expect(parsePolishGroupList("not json")).toBeNull();
    expect(parsePolishGroupList("{}")).toBeNull();
    expect(parsePolishGroupList('[{"playground":"x"}]')).toBeNull(); // missing usecases
  });

  test("returns an empty list for an empty array", () => {
    expect(parsePolishGroupList("[]")).toEqual([]);
  });
});

describe("polishPlaygroundLabel / parsePlaygroundIdFromLabel", () => {
  test("labels a playground with its usecase count", () => {
    expect(polishPlaygroundLabel({ playground: "sim-live", usecases: ["a", "b", "c"] }))
      .toBe("sim-live (3 usecases)");
  });

  test("round-trips playground id from its label", () => {
    expect(parsePlaygroundIdFromLabel("sim-live (3 usecases)")).toBe("sim-live");
  });
});
```

- [ ] **Step 2: Add `buildPolishListCommand` test** — append to `test/process-control.test.ts` (mirror `buildListJsonCommand`):

```ts
import { buildPolishListCommand } from "../src/process-control.js";

describe("buildPolishListCommand", () => {
  test("builds the polish list --json invocation", () => {
    const cmd = buildPolishListCommand();
    expect(cmd.bin).toBe("uv");
    expect(cmd.args).toEqual(["run", "python", "-m", "factory.polish", "list", "--json"]);
  });
});
```

- [ ] **Step 3: Run the new tests to verify they fail** — `npx vitest run test/polish-picker.test.ts test/process-control.test.ts`. Expected: fails (missing module/buildPolishListCommand).

- [ ] **Step 4: Implement `polish-picker.ts`**:

```ts
// Pure parsing + formatting for the polish playground/usecase selection menu.
// The JSON contract is produced by `factory polish list --json`; nothing here
// shells out or touches ctx -- callers (index.ts /polish) own the subprocess
// and the ctx.ui.select calls.

export interface PolishPlayground {
  playground: string;
  usecases: string[];
}

function isPlainArray(v: unknown): v is unknown[] {
  return Array.isArray(v);
}

export function parsePolishGroupList(raw: string): PolishPlayground[] | null {
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return null;
  }
  if (!isPlainArray(parsed)) return null;
  const out: PolishPlayground[] = [];
  for (const item of parsed) {
    if (typeof item !== "object" || item === null) return null;
    const pg = item as Record<string, unknown>;
    if (typeof pg.playground !== "string" || !Array.isArray(pg.usecases)) return null;
    if (!pg.usecases.every((u) => typeof u === "string")) return null;
    out.push({ playground: pg.playground, usecases: pg.usecases as string[] });
  }
  return out;
}

/** Menu label for a playground, e.g. `sim-live (11 usecases)`. */
export function polishPlaygroundLabel(pg: PolishPlayground): string {
  const n = pg.usecases.length;
  return `${pg.playground} (${n} usecase${n === 1 ? "" : "s"})`;
}

/** Recover the playground id from a label produced by polishPlaygroundLabel. */
export function parsePlaygroundIdFromLabel(label: string): string | null {
  const match = /^(\S+)/.exec(label.trim());
  return match ? match[1]! : null;
}
```

- [ ] **Step 5: Add `buildPolishListCommand` to `process-control.ts`** (next to `buildListJsonCommand`):

```ts
export function buildPolishListCommand(): Command {
  return {
    bin: "uv",
    args: ["run", "python", "-m", "factory.polish", "list", "--json"],
  };
}
```

- [ ] **Step 6: Add imports in `index.ts`** (extend the existing process-control import list with `buildPolishListCommand`, and add the polish-picker helpers):

```ts
import {
  buildListCommand,
  buildListJsonCommand,
  buildPolishListCommand,
  buildRunCommand,
  buildSystemNavigatorUrl,
  buildWindowsKillArgs,
} from "./process-control.js";
import {
  parsePolishGroupList,
  polishPlaygroundLabel,
  parsePlaygroundIdFromLabel,
} from "./polish-picker.js";
```

- [ ] **Step 7: Add the `pickPolishTarget` helper** near `parsePolishTarget`:

```ts
// Offer the same two-step selection menu `/factory-run` provides for tickets,
// but for a polish session: first the playground, then one of its usecases.
// Returns null when the operator cancels, the list is empty, or the CLI fails.
async function pickPolishTarget(
  ctx: ExtCommandCtx,
): Promise<{ playground: string; usecase: string } | null> {
  const cmd = buildPolishListCommand();
  const result = spawnSync(cmd.bin, cmd.args, { cwd: ctx.cwd, encoding: "utf-8" });
  if (result.status !== 0) {
    ctx.ui.notify(`polish list failed: ${result.stderr || "unknown error"}`, "error");
    return null;
  }
  const playgrounds = parsePolishGroupList(result.stdout);
  if (playgrounds === null) {
    ctx.ui.notify("polish list returned malformed data", "error");
    return null;
  }
  if (playgrounds.length === 0) {
    ctx.ui.notify("no polish playgrounds/usecases", "info");
    return null;
  }
  const pgLabel = await ctx.ui.select(
    "Polish which playground?",
    playgrounds.map(polishPlaygroundLabel),
  );
  if (pgLabel === undefined) return null;
  const pgId = parsePlaygroundIdFromLabel(pgLabel);
  const pg = pgId === null ? undefined : playgrounds.find((p) => p.playground === pgId);
  if (pg === undefined || pg.usecases.length === 0) {
    ctx.ui.notify("that playground has no usecases", "info");
    return null;
  }
  const usecase = await ctx.ui.select(`Which usecase on ${pg.playground}?`, pg.usecases);
  if (usecase === undefined) return null;
  return { playground: pg.playground, usecase };
}
```

- [ ] **Step 8: Update the `/polish` handler** to spawn the menu when the argument is empty (keep direct-launch + strict usage error otherwise):

```ts
pi.registerCommand("polish", {
  description: "Run a factory polish session (deterministic orchestrator + control panel)",
  handler: async (args: string, ctx: ExtCommandCtx) => {
    const trimmed = args.trim();
    const target = trimmed ? parsePolishTarget(trimmed) : null;
    if (trimmed && !target) {
      ctx.ui.notify("usage: /polish <playground>:<usecase> (or /polish to pick from a menu)", "error");
      return;
    }
    const resolved = target ?? (await pickPolishTarget(ctx));
    if (!resolved) return;
    await runPolishSession(ctx, resolved);
  },
});
```

- [ ] **Step 9: Run TS tests + typecheck** — `npx vitest run` in `pi-ext/factory-watch`; then `npm run typecheck`. Note: there is a **pre-existing** typecheck error in `src/factory-init-command.ts` (`./tool-catalog.js`) and other pre-existing dirty files — your new files (polish-picker.ts, process-control.ts, index.ts) must not add NEW type errors; that pre-existing error is out of scope to fix.

- [ ] **Step 10: Commit** (R1, only the intended paths):

```
git add pi-ext/factory-watch/src/polish-picker.ts
git add pi-ext/factory-watch/test/polish-picker.test.ts
git add pi-ext/factory-watch/src/process-control.ts
git add pi-ext/factory-watch/test/process-control.test.ts
git add pi-ext/factory-watch/src/index.ts
git commit -m "feat(polish): /polish menu to pick playground + usecase (T-2)"
```

**Done when:** the new TS tests pass, `buildPolishListCommand` is covered, and `/polish` with no argument opens the two-step menu (manual smoke: run `/polish` in a pi session in R2); `/polish <pg>:<uc>` still launches directly.

---

## Traceability

This factory CLI/extension change is pure UI + plumbing for the polish session's launch: it adds a structured listing flag and a selection menu. No product requirement genuinely measures an interactive selection menu or a `list --json` endpoint — these are interaction conveniences with no behavioural claim (same disposition as the scenario-replay / sim-live playground work). Exempt dispositions are recorded in the plan/task store, not deferred.
