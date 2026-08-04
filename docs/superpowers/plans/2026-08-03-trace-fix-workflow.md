# `/trace-fix` Tool-Driven Gap-Closing Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close traceability gaps through registered tools whose implementations are deterministic code, so the model contributes semantic judgment over the full candidate set while enumeration, validation, writes and the completion gate stay in code.

**Architecture:** `pi.registerTool()` exposes five tools — `trace_next`, `trace_link`, `trace_exempt`, `trace_defer`, `trace_check` — each backed by the `factory trace` CLI from plan 1. `/trace-fix` seeds a session with a narrow skill; the agent calls `trace_next`, reasons over **every** candidate with its full requirement statement, proposes to the human, and applies the confirmed decision through a tool. The gate is stateless and re-derives everything from disk.

**Tech Stack:** TypeScript (ES2022, NodeNext), `typebox` for tool parameter schemas, vitest, and a Pi skill in `.pi/skills/`.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-03-review-plans-browser-and-trace-health-design.md` §6
- Prerequisites: plan `2026-08-03-trace-model-and-cli.md` (provides `next`, `link`, `exempt`, `defer`, `check`) and Task 1 of plan `2026-08-03-docs-browser-viewer.md` (provides `trace-cli.ts`).
- **Never truncate the candidate list.** Ranking orders it; truncating would let a lexical heuristic decide which links are reachable at all.
- **Every candidate carries its requirement statement.** A shared-term count cannot be reasoned about semantically.
- The gate is `factory trace check`, which is **stateless** — it re-derives every gap and disposition from disk. Never add a session log it could consult instead.
- `pi-ext/factory-watch/package.json` has zero runtime dependencies. `typebox` is already present as a transitive dependency of `@earendil-works/pi-coding-agent`, and is the package pi itself imports `TSchema`/`Static` from — import from `"typebox"`, not `"@sinclair/typebox"`. Add nothing else.
- `tsconfig.json` sets `strict: true` and `noUncheckedIndexedAccess: true`.
- ESM/NodeNext: intra-package imports use the `.js` extension, including in tests.
- Run tests with `npm test --prefix pi-ext/factory-watch`.

## Why tools, and where determinism actually lives

An earlier draft of this plan drove the loop from TypeScript with `ctx.ui.select`,
because `ctx.newSession()` replaces the session and makes `ctx` stale — so a loop
appeared unable to consult the model and resume. That reasoning was wrong: it
generalised one API's behaviour to the whole API. `pi.registerTool()` inverts the
control flow so the **model** drives and calls deterministic code.

It also had a worse flaw. It shortlisted five candidates by shared-term overlap
before the model ever saw them. Ranking that *orders* is harmless; ranking that
*truncates* means a lexical heuristic decides which links are reachable — and a task
and a requirement describing the same behaviour in different words become
impossible to link at all. Semantic matching is the one thing a model is genuinely
better at, and the old design filtered it out upstream.

| concern | owner | why |
|---|---|---|
| which gaps exist, in what order | `trace_next` | code — the model cannot skip one |
| the candidate set | `trace_next` — **all of them, each with its statement** | code retrieves and orders, never truncates |
| **which candidate is right** | **the model** | semantic matching over full statements |
| confirmation | the human | every write is proposed first |
| is the link target real | `trace_link` | code — refuses to create a dangling reference |
| what reaches disk | the tools | code — the model never edits frontmatter |
| is the work complete | `trace_check` | stateless code — unfakeable by assertion |

---

### Task 1: Extend the trace client with `next`, writes and `check`

**Files:**
- Modify: `pi-ext/factory-watch/src/trace-cli.ts` (append)
- Test: `pi-ext/factory-watch/test/trace-cli-actions.test.ts`

**Interfaces:**
- Consumes: `buildTraceCommand`, `TraceGap` from `trace-cli.ts` (plan 2, Task 1).
- Produces:
  - `TraceCandidate { id: string; title: string; summary: string; shared_terms: string[]; score: number }`
  - `TraceProposal { gap: TraceGap; node_title: string; node_excerpt: string; pending_total: number; candidates: TraceCandidate[] }`
  - `loadNextGap(cwd: string): { ok: true; proposal: TraceProposal | null } | { ok: false; error: string }`
  - `runTrace(cwd: string, sub: string[]): { ok: boolean; status: number; stdout: string; stderr: string }`
  - `TraceCheckResult { ok: boolean; pending: number; deferred: number; exempt: number; report: string }`
  - `runTraceCheck(cwd: string): TraceCheckResult`

- [ ] **Step 1: Write the failing test**

Create `pi-ext/factory-watch/test/trace-cli-actions.test.ts`:

```ts
import { describe, expect, test, vi } from "vitest";

const spawnSync = vi.hoisted(() => vi.fn());
vi.mock("node:child_process", () => ({ spawnSync }));

import { loadNextGap, runTrace, runTraceCheck } from "../src/trace-cli.js";

const PROPOSAL = {
  gap: { node_id: "T-001", kind: "task_no_sr", detail: "task declares no satisfies", disposition: "pending" },
  node_title: "Bug Capture",
  node_excerpt: "body",
  pending_total: 45,
  candidates: [
    {
      id: "SR-001",
      title: "Preempt patrol",
      summary: "navigation shall preempt patrol when a shark is detected",
      shared_terms: ["shark"],
      score: 1,
    },
  ],
};

describe("loadNextGap", () => {
  test("parses a proposal including the statement and pending total", () => {
    spawnSync.mockReturnValue({ status: 0, stdout: JSON.stringify(PROPOSAL), stderr: "" });
    const result = loadNextGap("/repo");
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.proposal?.pending_total).toBe(45);
      expect(result.proposal?.candidates[0]?.summary).toContain("preempt patrol");
    }
  });

  test("returns a null proposal when nothing is pending", () => {
    spawnSync.mockReturnValue({ status: 0, stdout: JSON.stringify({ gap: null }), stderr: "" });
    expect(loadNextGap("/repo")).toEqual({ ok: true, proposal: null });
  });

  test("reports a failure instead of throwing", () => {
    spawnSync.mockReturnValue({ status: 2, stdout: "", stderr: "boom" });
    expect(loadNextGap("/repo").ok).toBe(false);
  });
});

describe("runTrace", () => {
  test("reports success", () => {
    spawnSync.mockReturnValue({ status: 0, stdout: "tasks/T-001.md", stderr: "" });
    expect(runTrace("/repo", ["link", "T-001", "--satisfies", "SR-001"])).toEqual({
      ok: true, status: 0, stdout: "tasks/T-001.md", stderr: "",
    });
  });

  test("reports a refusal from the CLI", () => {
    spawnSync.mockReturnValue({ status: 2, stdout: "error: no such requirement: SR-999", stderr: "" });
    const result = runTrace("/repo", ["link", "T-001", "--satisfies", "SR-999"]);
    expect(result.ok).toBe(false);
    expect(result.stdout).toContain("no such requirement");
  });

  test("reports a missing binary instead of throwing", () => {
    spawnSync.mockReturnValue({ error: new Error("ENOENT"), status: null, stdout: "", stderr: "" });
    expect(runTrace("/repo", ["check"]).ok).toBe(false);
  });
});

describe("runTraceCheck", () => {
  test("passes when nothing is pending", () => {
    spawnSync.mockReturnValue({
      status: 0, stdout: "traceability health: 80%\n0 pending, 2 deferred, 1 exempt\n", stderr: "",
    });
    expect(runTraceCheck("/repo")).toMatchObject({ ok: true, pending: 0, deferred: 2, exempt: 1 });
  });

  test("fails when gaps are still undiscussed", () => {
    spawnSync.mockReturnValue({
      status: 1, stdout: "traceability health: 10%\n45 pending, 0 deferred, 0 exempt\n", stderr: "",
    });
    const result = runTraceCheck("/repo");
    expect(result.ok).toBe(false);
    expect(result.pending).toBe(45);
  });

  test("the exit code decides, not the parsed text", () => {
    spawnSync.mockReturnValue({ status: 1, stdout: "surprise", stderr: "" });
    const result = runTraceCheck("/repo");
    expect(result.ok).toBe(false);
    expect(result.pending).toBe(0);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test --prefix pi-ext/factory-watch -- trace-cli-actions`
Expected: FAIL — `loadNextGap` is not exported from `../src/trace-cli.js`

- [ ] **Step 3: Write minimal implementation**

Append to `pi-ext/factory-watch/src/trace-cli.ts`:

```ts
export interface TraceCandidate {
  id: string;
  title: string;
  summary: string;
  shared_terms: string[];
  score: number;
}

export interface TraceProposal {
  gap: TraceGap;
  node_title: string;
  node_excerpt: string;
  pending_total: number;
  candidates: TraceCandidate[];
}

export interface TraceRunResult {
  ok: boolean;
  status: number;
  stdout: string;
  stderr: string;
}

export interface TraceCheckResult {
  ok: boolean;
  pending: number;
  deferred: number;
  exempt: number;
  report: string;
}

export function runTrace(cwd: string, sub: string[]): TraceRunResult {
  const cmd = buildTraceCommand(sub);
  const result = spawnSync(cmd.bin, cmd.args, { cwd, encoding: "utf-8", maxBuffer: 64 * 1024 * 1024 });
  if (result.error) {
    return { ok: false, status: -1, stdout: "", stderr: String(result.error.message ?? result.error) };
  }
  const status = result.status ?? -1;
  return { ok: status === 0, status, stdout: result.stdout ?? "", stderr: result.stderr ?? "" };
}

export function loadNextGap(
  cwd: string,
): { ok: true; proposal: TraceProposal | null } | { ok: false; error: string } {
  const result = runTrace(cwd, ["next", "--json"]);
  if (!result.ok) {
    return { ok: false, error: result.stderr || result.stdout || `exited ${result.status}` };
  }
  try {
    const parsed = JSON.parse(result.stdout) as { gap: unknown };
    if (parsed.gap === null) return { ok: true, proposal: null };
    return { ok: true, proposal: parsed as unknown as TraceProposal };
  } catch (err) {
    return { ok: false, error: `could not parse factory trace next: ${String(err)}` };
  }
}

const COUNTS_RE = /(\d+) pending, (\d+) deferred, (\d+) exempt/;

export function runTraceCheck(cwd: string): TraceCheckResult {
  const result = runTrace(cwd, ["check"]);
  const report = result.stdout || result.stderr;
  const match = COUNTS_RE.exec(report);
  return {
    // The exit code is authoritative; the parsed counts are for display only, so
    // a formatting change can never turn a failing gate into a passing one.
    ok: result.status === 0,
    pending: match ? Number(match[1]) : 0,
    deferred: match ? Number(match[2]) : 0,
    exempt: match ? Number(match[3]) : 0,
    report,
  };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test --prefix pi-ext/factory-watch -- trace-cli-actions`
Expected: PASS — 9 passed

- [ ] **Step 5: Commit**

```bash
git add pi-ext/factory-watch/src/trace-cli.ts pi-ext/factory-watch/test/trace-cli-actions.test.ts
git commit -m "feat(factory-watch): trace client for next, writes and the check gate

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: Tool result formatting

**Files:**
- Create: `pi-ext/factory-watch/src/trace-tool-format.ts`
- Test: `pi-ext/factory-watch/test/trace-tool-format.test.ts`

**Interfaces:**
- Consumes: `TraceProposal`, `TraceCheckResult` (Task 1).
- Produces:
  - `formatProposal(proposal: TraceProposal): string` — what `trace_next` returns to the model
  - `formatNoGaps(): string`
  - `formatCheck(result: TraceCheckResult): string`
  - `formatWriteResult(label: string, result: { ok: boolean; stdout: string; stderr: string }): string`
- Kept separate from the tool registrations so the exact text the model reads is
  unit-testable without constructing an `ExtensionContext`.

- [ ] **Step 1: Write the failing test**

Create `pi-ext/factory-watch/test/trace-tool-format.test.ts`:

```ts
import { describe, expect, test } from "vitest";
import {
  formatCheck,
  formatNoGaps,
  formatProposal,
  formatWriteResult,
} from "../src/trace-tool-format.js";
import type { TraceProposal } from "../src/trace-cli.js";

function proposal(candidateCount: number): TraceProposal {
  return {
    gap: { node_id: "T-047", kind: "task_no_sr", detail: "task declares no satisfies", disposition: "pending" },
    node_title: "Bug Capture",
    node_excerpt: "Create src/sim/bug_capture.py",
    pending_total: 45,
    candidates: Array.from({ length: candidateCount }, (_, i) => ({
      id: `SR-${String(i + 1).padStart(3, "0")}`,
      title: `Requirement ${i + 1}`,
      summary: `the system shall do thing number ${i + 1}`,
      shared_terms: i === 0 ? ["capture"] : [],
      score: i === 0 ? 1 : 0,
    })),
  };
}

describe("formatProposal", () => {
  test("names the gap, the node and how many remain", () => {
    const text = formatProposal(proposal(2));
    expect(text).toContain("T-047");
    expect(text).toContain("task_no_sr");
    expect(text).toContain("Bug Capture");
    expect(text).toContain("45");
  });

  test("includes every candidate's statement, not just its id", () => {
    // Semantic matching is impossible without the statements. Spec section 6.1.
    const text = formatProposal(proposal(3));
    expect(text).toContain("the system shall do thing number 3");
  });

  test("lists all candidates even when there are many", () => {
    const text = formatProposal(proposal(30));
    expect(text).toContain("SR-030");
  });

  test("states that ranking is lexical and not authoritative", () => {
    const text = formatProposal(proposal(2));
    expect(text.toLowerCase()).toContain("shared-term");
  });

  test("handles a gap with no candidates", () => {
    const text = formatProposal(proposal(0));
    expect(text).toContain("no candidates");
  });
});

describe("formatCheck", () => {
  test("reports a pass", () => {
    const text = formatCheck({ ok: true, pending: 0, deferred: 2, exempt: 1, report: "raw" });
    expect(text).toContain("PASSED");
    expect(text).toContain("raw");
  });

  test("reports a failure with the pending count", () => {
    const text = formatCheck({ ok: false, pending: 7, deferred: 0, exempt: 0, report: "raw" });
    expect(text).toContain("FAILED");
    expect(text).toContain("7");
  });
});

describe("formatWriteResult", () => {
  test("reports success with the path written", () => {
    expect(formatWriteResult("link", { ok: true, stdout: "tasks/T-047.md", stderr: "" }))
      .toContain("tasks/T-047.md");
  });

  test("surfaces a refusal verbatim so the model cannot mistake it for success", () => {
    const text = formatWriteResult("link", { ok: false, stdout: "error: no such requirement: SR-999", stderr: "" });
    expect(text).toContain("FAILED");
    expect(text).toContain("no such requirement: SR-999");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test --prefix pi-ext/factory-watch -- trace-tool-format`
Expected: FAIL — cannot resolve `../src/trace-tool-format.js`

- [ ] **Step 3: Write minimal implementation**

Create `pi-ext/factory-watch/src/trace-tool-format.ts`:

```ts
import type { TraceCheckResult, TraceProposal } from "./trace-cli.js";

export function formatNoGaps(): string {
  return "No pending gaps. Every gap is linked, exempted, or deferred. Run trace_check to confirm.";
}

export function formatProposal(proposal: TraceProposal): string {
  const lines = [
    `Gap: ${proposal.gap.node_id}  [${proposal.gap.kind}]`,
    `Node: ${proposal.node_title}`,
    `Detail: ${proposal.gap.detail}`,
    `Pending gaps remaining: ${proposal.pending_total}`,
    "",
    "Excerpt:",
    proposal.node_excerpt,
    "",
  ];

  if (proposal.candidates.length === 0) {
    lines.push("Candidates: no candidates exist for this gap kind. Defer it, or exempt it if it is not a task or plan that should be linked.");
    return lines.join("\n");
  }

  lines.push(
    `Candidates (${proposal.candidates.length}, ordered by shared-term overlap — ` +
      "that ordering is a lexical hint, NOT a judgement. Read the statements and " +
      "decide on meaning; the right answer is often not first, and may share no vocabulary at all.",
  );
  lines.push("");
  for (const candidate of proposal.candidates) {
    const terms = candidate.shared_terms.length > 0 ? candidate.shared_terms.join(", ") : "none";
    lines.push(`- ${candidate.id}  ${candidate.title}`);
    lines.push(`    ${candidate.summary}`);
    lines.push(`    (shared terms: ${terms})`);
  }
  return lines.join("\n");
}

export function formatCheck(result: TraceCheckResult): string {
  const headline = result.ok
    ? "GATE PASSED — every gap is linked, exempted, or deferred."
    : `GATE FAILED — ${result.pending} gap(s) still undiscussed.`;
  return `${headline}\n\n${result.report}`;
}

export function formatWriteResult(
  label: string,
  result: { ok: boolean; stdout: string; stderr: string },
): string {
  const detail = (result.stdout || result.stderr).trim();
  return result.ok ? `${label} written: ${detail}` : `${label} FAILED: ${detail}`;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test --prefix pi-ext/factory-watch -- trace-tool-format`
Expected: PASS — 9 passed

- [ ] **Step 5: Commit**

```bash
git add pi-ext/factory-watch/src/trace-tool-format.ts pi-ext/factory-watch/test/trace-tool-format.test.ts
git commit -m "feat(factory-watch): tool result formatting carrying full statements

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: Register the five trace tools

**Files:**
- Create: `pi-ext/factory-watch/src/trace-tools.ts`
- Test: `pi-ext/factory-watch/test/trace-tools.test.ts`

**Interfaces:**
- Consumes: `loadNextGap`, `runTrace`, `runTraceCheck` (Task 1); the formatters (Task 2).
- Produces: `registerTraceTools(pi: { registerTool(tool: unknown): void })`, plus the
  five tool definitions exported individually for testing:
  `traceNextTool`, `traceLinkTool`, `traceExemptTool`, `traceDeferTool`, `traceCheckTool`.
- Each tool's `execute(toolCallId, params, signal, onUpdate, ctx)` reads `ctx.cwd`
  and returns `{ content: string }`.

- [ ] **Step 1: Write the failing test**

Create `pi-ext/factory-watch/test/trace-tools.test.ts`:

```ts
import { describe, expect, test, vi } from "vitest";

const spawnSync = vi.hoisted(() => vi.fn());
vi.mock("node:child_process", () => ({ spawnSync }));

import {
  registerTraceTools,
  traceCheckTool,
  traceDeferTool,
  traceExemptTool,
  traceLinkTool,
  traceNextTool,
} from "../src/trace-tools.js";

const CTX = { cwd: "/repo" } as never;

function run(tool: { execute: Function }, params: unknown) {
  return tool.execute("call-1", params, undefined, undefined, CTX);
}

const PROPOSAL = {
  gap: { node_id: "T-047", kind: "task_no_sr", detail: "d", disposition: "pending" },
  node_title: "Bug Capture",
  node_excerpt: "excerpt",
  pending_total: 45,
  candidates: [
    { id: "SR-001", title: "Preempt", summary: "shall preempt patrol", shared_terms: [], score: 0 },
  ],
};

describe("registerTraceTools", () => {
  test("registers all five tools", () => {
    const names: string[] = [];
    registerTraceTools({ registerTool: (t: { name: string }) => names.push(t.name) } as never);
    expect(names.sort()).toEqual(["trace_check", "trace_defer", "trace_exempt", "trace_link", "trace_next"]);
  });
});

describe("trace_next", () => {
  test("returns the proposal with candidate statements", async () => {
    spawnSync.mockReturnValue({ status: 0, stdout: JSON.stringify(PROPOSAL), stderr: "" });
    const result = await run(traceNextTool, {});
    expect(result.content).toContain("shall preempt patrol");
    expect(result.content).toContain("45");
  });

  test("reports when nothing is pending", async () => {
    spawnSync.mockReturnValue({ status: 0, stdout: JSON.stringify({ gap: null }), stderr: "" });
    const result = await run(traceNextTool, {});
    expect(result.content).toContain("No pending gaps");
  });

  test("surfaces a CLI failure rather than pretending there is nothing to do", async () => {
    spawnSync.mockReturnValue({ status: 2, stdout: "", stderr: "boom" });
    const result = await run(traceNextTool, {});
    expect(result.content).toContain("boom");
  });
});

describe("trace_link", () => {
  test("links a task to a requirement", async () => {
    spawnSync.mockReturnValue({ status: 0, stdout: "tasks/T-047.md", stderr: "" });
    await run(traceLinkTool, { node_id: "T-047", satisfies: "SR-001" });
    expect(spawnSync).toHaveBeenCalledWith(
      "uv",
      ["run", "python", "-m", "factory.trace", "link", "T-047", "--satisfies", "SR-001"],
      expect.objectContaining({ cwd: "/repo" }),
    );
  });

  test("links a plan to a spec", async () => {
    spawnSync.mockReturnValue({ status: 0, stdout: "plans/p1.md", stderr: "" });
    await run(traceLinkTool, { node_id: "plan:p1.md", spec: "s1.md" });
    expect(spawnSync).toHaveBeenCalledWith(
      "uv",
      ["run", "python", "-m", "factory.trace", "link", "plan:p1.md", "--spec", "s1.md"],
      expect.objectContaining({ cwd: "/repo" }),
    );
  });

  test("requires one of satisfies or spec", async () => {
    const result = await run(traceLinkTool, { node_id: "T-047" });
    expect(result.content).toContain("exactly one");
    expect(spawnSync).not.toHaveBeenCalled();
  });

  test("rejects both at once", async () => {
    const result = await run(traceLinkTool, { node_id: "T-047", satisfies: "SR-001", spec: "s1.md" });
    expect(result.content).toContain("exactly one");
    expect(spawnSync).not.toHaveBeenCalled();
  });

  test("reports a refusal from the CLI as a failure", async () => {
    spawnSync.mockReturnValue({ status: 2, stdout: "error: no such requirement: SR-999", stderr: "" });
    const result = await run(traceLinkTool, { node_id: "T-047", satisfies: "SR-999" });
    expect(result.content).toContain("FAILED");
  });
});

describe("trace_exempt and trace_defer", () => {
  test("exempt passes the reason through", async () => {
    spawnSync.mockReturnValue({ status: 0, stdout: "tasks/T-047.md", stderr: "" });
    await run(traceExemptTool, { node_id: "T-047", reason: "tooling task" });
    expect(spawnSync).toHaveBeenCalledWith(
      "uv",
      ["run", "python", "-m", "factory.trace", "exempt", "T-047", "--reason", "tooling task"],
      expect.objectContaining({ cwd: "/repo" }),
    );
  });

  test("defer passes the reason through", async () => {
    spawnSync.mockReturnValue({ status: 0, stdout: "tasks/T-047.md", stderr: "" });
    await run(traceDeferTool, { node_id: "T-047", reason: "needs an SR split" });
    expect(spawnSync).toHaveBeenCalledWith(
      "uv",
      ["run", "python", "-m", "factory.trace", "defer", "T-047", "--reason", "needs an SR split"],
      expect.objectContaining({ cwd: "/repo" }),
    );
  });

  test("a blank reason is refused before anything is written", async () => {
    const result = await run(traceDeferTool, { node_id: "T-047", reason: "   " });
    expect(result.content).toContain("reason");
    expect(spawnSync).not.toHaveBeenCalled();
  });
});

describe("trace_check", () => {
  test("reports the gate passing", async () => {
    spawnSync.mockReturnValue({ status: 0, stdout: "0 pending, 0 deferred, 0 exempt", stderr: "" });
    expect((await run(traceCheckTool, {})).content).toContain("GATE PASSED");
  });

  test("reports the gate failing", async () => {
    spawnSync.mockReturnValue({ status: 1, stdout: "45 pending, 0 deferred, 0 exempt", stderr: "" });
    const result = await run(traceCheckTool, {});
    expect(result.content).toContain("GATE FAILED");
    expect(result.content).toContain("45");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test --prefix pi-ext/factory-watch -- trace-tools`
Expected: FAIL — cannot resolve `../src/trace-tools.js`

- [ ] **Step 3: Write minimal implementation**

Create `pi-ext/factory-watch/src/trace-tools.ts`:

```ts
import { Type } from "typebox";
import { loadNextGap, runTrace, runTraceCheck } from "./trace-cli.js";
import {
  formatCheck,
  formatNoGaps,
  formatProposal,
  formatWriteResult,
} from "./trace-tool-format.js";

// Structural subset of the ExtensionContext fields these tools read, kept local
// so the tools stay unit-testable without constructing a real context.
interface ToolCtx {
  cwd: string;
}

function result(content: string): { content: string } {
  return { content };
}

export const traceNextTool = {
  name: "trace_next",
  label: "Trace: next gap",
  description:
    "Return the next pending traceability gap, with the node's excerpt and EVERY candidate target " +
    "including its full requirement statement. Candidates are ordered by shared-term overlap, which " +
    "is a lexical hint only — judge matches by meaning, not by position in the list.",
  parameters: Type.Object({}),
  async execute(
    _id: string,
    _params: Record<string, never>,
    _signal: AbortSignal | undefined,
    _onUpdate: unknown,
    ctx: ToolCtx,
  ) {
    const next = loadNextGap(ctx.cwd);
    if (!next.ok) return result(`trace_next failed: ${next.error}`);
    if (next.proposal === null) return result(formatNoGaps());
    return result(formatProposal(next.proposal));
  },
};

export const traceLinkTool = {
  name: "trace_link",
  label: "Trace: link",
  description:
    "Declare a traceability link. Use `satisfies` to record that a task satisfies a requirement " +
    "(node_id must be the TASK id, even when the gap was reported against the requirement), or " +
    "`spec` to record that a plan implements a spec file. The link target is validated: a " +
    "non-existent target is refused rather than written.",
  parameters: Type.Object({
    node_id: Type.String({ description: "Task id (for satisfies) or plan id (for spec)" }),
    satisfies: Type.Optional(Type.String({ description: "Requirement id, e.g. SR-001" })),
    spec: Type.Optional(Type.String({ description: "Spec filename, e.g. 2026-07-30-design.md" })),
  }),
  async execute(
    _id: string,
    params: { node_id: string; satisfies?: string; spec?: string },
    _signal: AbortSignal | undefined,
    _onUpdate: unknown,
    ctx: ToolCtx,
  ) {
    const hasSatisfies = typeof params.satisfies === "string" && params.satisfies.trim() !== "";
    const hasSpec = typeof params.spec === "string" && params.spec.trim() !== "";
    if (hasSatisfies === hasSpec) {
      return result("trace_link needs exactly one of `satisfies` or `spec`; nothing was written.");
    }
    const args = hasSatisfies
      ? ["link", params.node_id, "--satisfies", params.satisfies!]
      : ["link", params.node_id, "--spec", params.spec!];
    return result(formatWriteResult("link", runTrace(ctx.cwd, args)));
  },
};

function dispositionTool(name: "exempt" | "defer", label: string, description: string) {
  return {
    name: `trace_${name}`,
    label,
    description,
    parameters: Type.Object({
      node_id: Type.String({ description: "Node id, e.g. T-047 or plan:2026-07-30-sim.md" }),
      reason: Type.String({ description: "Why — recorded on disk and read by humans later" }),
    }),
    async execute(
      _id: string,
      params: { node_id: string; reason: string },
      _signal: AbortSignal | undefined,
      _onUpdate: unknown,
      ctx: ToolCtx,
    ) {
      // A blank reason would record that we looked without recording what we saw.
      if (params.reason.trim() === "") {
        return result(`trace_${name} needs a non-empty reason; nothing was written.`);
      }
      const args = [name, params.node_id, "--reason", params.reason];
      return result(formatWriteResult(name, runTrace(ctx.cwd, args)));
    },
  };
}

export const traceExemptTool = dispositionTool(
  "exempt",
  "Trace: exempt",
  "Record that no requirement applies to this task or plan. Requirements themselves cannot be " +
    "exempted — defer them instead.",
);

export const traceDeferTool = dispositionTool(
  "defer",
  "Trace: defer",
  "Record that this gap was discussed but needs more time, with what must happen before it can be " +
    "resolved. Deferring passes the gate but does not improve the health score.",
);

export const traceCheckTool = {
  name: "trace_check",
  label: "Trace: check",
  description:
    "Run the completion gate. It re-derives every gap and disposition from disk, so it reflects what " +
    "is actually written, not what was claimed. Fails while any gap is still undiscussed.",
  parameters: Type.Object({}),
  async execute(
    _id: string,
    _params: Record<string, never>,
    _signal: AbortSignal | undefined,
    _onUpdate: unknown,
    ctx: ToolCtx,
  ) {
    return result(formatCheck(runTraceCheck(ctx.cwd)));
  },
};

export function registerTraceTools(pi: { registerTool(tool: unknown): void }): void {
  for (const tool of [traceNextTool, traceLinkTool, traceExemptTool, traceDeferTool, traceCheckTool]) {
    pi.registerTool(tool);
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test --prefix pi-ext/factory-watch -- trace-tools`
Expected: PASS — 14 passed

- [ ] **Step 5: Typecheck**

Run: `npm run typecheck --prefix pi-ext/factory-watch`
Expected: no errors. If `typebox` cannot be resolved, confirm it is present with
`ls pi-ext/factory-watch/node_modules/typebox/package.json` — it ships as a
transitive dependency of `@earendil-works/pi-coding-agent`, which imports
`TSchema`/`Static` from it.

- [ ] **Step 6: Commit**

```bash
git add pi-ext/factory-watch/src/trace-tools.ts pi-ext/factory-watch/test/trace-tools.test.ts
git commit -m "feat(factory-watch): five trace tools backed by deterministic code

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 4: The `trace-fix` skill and its seed prompt

**Files:**
- Create: `.pi/skills/trace-fix/SKILL.md`
- Modify: `pi-ext/factory-watch/src/skill-prompt.ts` (append)
- Test: `pi-ext/factory-watch/test/skill-prompt.test.ts` (extend)

**Interfaces:**
- Consumes: `buildSkillBlock` (existing, `skill-prompt.ts:7`).
- Produces: `buildTraceFixSeedPrompt(skillBlocks: string[], gapReport: string): string`.

- [ ] **Step 1: Write the failing test**

Append to `pi-ext/factory-watch/test/skill-prompt.test.ts`:

```ts
import { buildTraceFixSeedPrompt } from "../src/skill-prompt.js";

describe("buildTraceFixSeedPrompt", () => {
  const prompt = buildTraceFixSeedPrompt(['<skill name="trace-fix">body</skill>'], "45 pending");

  test("includes the skill block and the current gap report", () => {
    expect(prompt).toContain('<skill name="trace-fix">');
    expect(prompt).toContain("45 pending");
  });

  test("directs the agent at the tools, not at raw commands", () => {
    expect(prompt).toContain("trace_next");
    expect(prompt).toContain("trace_check");
  });

  test("tells the agent to judge by meaning rather than by rank", () => {
    expect(prompt.toLowerCase()).toContain("ordering is a lexical hint");
  });

  test("forbids editing frontmatter directly", () => {
    expect(prompt.toLowerCase()).toContain("never edit");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test --prefix pi-ext/factory-watch -- skill-prompt`
Expected: FAIL — `buildTraceFixSeedPrompt` is not exported

- [ ] **Step 3: Write the seed prompt builder**

Append to `pi-ext/factory-watch/src/skill-prompt.ts`:

```ts
export function buildTraceFixSeedPrompt(skillBlocks: string[], gapReport: string): string {
  const instructions = [
    "You are closing traceability gaps for this repo. Use the loaded `trace-fix` skill.",
    "Work through the gaps with the trace tools: `trace_next` for the next gap and its candidates, `trace_link` / `trace_exempt` / `trace_defer` to record a decision, and `trace_check` for the gate. The tools own enumeration, validation and every write.",
    "You own exactly one thing: judging which candidate genuinely matches, and saying why. `trace_next` returns EVERY candidate with its full requirement statement, ordered by shared-term overlap — that ordering is a lexical hint, not a judgement. The right answer is often not first, and may share no vocabulary with the task at all. Read the statements.",
    "Propose one candidate to the human with your reasoning and wait for their answer before calling any write tool.",
    "Never edit `satisfies:`, `trace_exempt:` or `trace_deferred:` in a file directly. `trace_link` verifies the target exists; a hand-edited link can create a dangling reference it would have refused.",
    "Never claim a gap was handled without having called the tool. `trace_check` re-reads the files and will contradict you.",
    "Finish by calling `trace_check` and reporting its output verbatim.",
  ].join("\n\n");
  return [...skillBlocks, instructions, `Current gap report:\n${gapReport}`].join("\n\n");
}
```

- [ ] **Step 4: Write the skill**

Create `.pi/skills/trace-fix/SKILL.md`:

```markdown
---
name: trace-fix
description: Close traceability gaps one at a time — judge which requirement a task actually satisfies by reading statements, propose it with your reasoning, and let the trace tools perform every write.
---

# Trace fix

Use this when the human wants to improve traceability health: linking tasks to the
system requirements they satisfy, plans to the specs they implement, or recording
an honest exemption or deferral where no link belongs.

## What you own, and what you do not

You own **one judgment per gap**: which candidate genuinely matches, and why.

You do **not** own enumeration, validation, writing, or deciding when the work is
finished. Those belong to the `trace_*` tools. This split is deliberate — a gate
that trusted your account of your own progress would be worthless.

## Steps

1. **Get the next gap.** Call `trace_next`. It returns the gap, the node's excerpt,
   how many gaps remain, and **every** candidate with its full statement.
2. **Judge by meaning.** Candidates are ordered by shared-term overlap. That is a
   lexical hint, not a verdict — a task titled "Bug Capture" and a requirement about
   preempting patrol may share no vocabulary and still be the right pair, while two
   documents that both say "system" and "detection" may be unrelated. Read the
   statements. Consider every candidate, not just the top few.
3. **Propose, then wait.** Tell the human the gap, your recommended candidate, and
   the reasoning — what the task actually does, and why that satisfies that
   requirement's statement. If nothing fits, say so; a wrong link is worse than an
   honest deferral. Do not call a write tool before they answer.
4. **Record their decision**, then return to step 1:
   - `trace_link` with `satisfies` — note `node_id` is always the **task** id, even
     when the gap was reported against the requirement
   - `trace_link` with `spec` — for a plan implementing a spec
   - `trace_exempt` — no requirement applies (tasks and plans only)
   - `trace_defer` — discussed, needs more time
5. **Run the gate.** Call `trace_check` and report its output verbatim, including
   any gaps still pending.

## Rules

- **Never edit `satisfies:`, `trace_exempt:` or `trace_deferred:` by hand.** The
  tools verify that a link target exists; a hand-written link can create the
  dangling reference they would have refused.
- **Never assert a gap is handled without having called the tool.** `trace_check`
  re-derives everything from disk and will contradict you.
- **A deferral needs a real reason.** "Needs more time" alone is not one — record
  what has to happen before it can be resolved.
- **Requirements cannot be exempted.** An SR that no task satisfies and no run
  validates is a real gap. Defer it instead.
- **Do not batch.** One gap, one proposal, one confirmation.
```

- [ ] **Step 5: Run test to verify it passes**

Run: `npm test --prefix pi-ext/factory-watch -- skill-prompt`
Expected: PASS — 4 new tests pass alongside the existing ones

- [ ] **Step 6: Commit**

```bash
git add .pi/skills/trace-fix/SKILL.md pi-ext/factory-watch/src/skill-prompt.ts pi-ext/factory-watch/test/skill-prompt.test.ts
git commit -m "feat(trace-fix): skill owning semantic judgment over full statements

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 5: Register the tools and the `/trace-fix` command

**Files:**
- Modify: `pi-ext/factory-watch/src/index.ts` (imports, tool registration, command)
- Test: manual — see Step 4

**Interfaces:**
- Consumes: `registerTraceTools` (Task 3), `runTraceCheck` (Task 1),
  `buildTraceFixSeedPrompt` (Task 4), and `loadSkills` / `stripFrontmatter` /
  `buildSkillBlock` (already imported at `index.ts:13-14`).
- Produces: the five tools registered on activation, and the `/trace-fix` command.

- [ ] **Step 1: Add the imports and constant**

In `pi-ext/factory-watch/src/index.ts`, add beside the existing imports:

```ts
import { registerTraceTools } from "./trace-tools.js";
import { runTraceCheck } from "./trace-cli.js";
import { buildTraceFixSeedPrompt } from "./skill-prompt.js";
```

Add beside `PLAN_SKILL_NAMES` at `index.ts:43`:

```ts
const TRACE_FIX_SKILL_NAMES = ["trace-fix"];
```

- [ ] **Step 2: Register the tools**

Add near the top of the same activation function that calls `pi.registerCommand`,
before the command registrations:

```ts
  // The deterministic half of /trace-fix: the model reasons, these tools do the
  // enumerating, validating and writing.
  registerTraceTools(pi);
```

- [ ] **Step 3: Register the command**

Add after the `review-plans` registration:

```ts
  pi.registerCommand("trace-fix", {
    description: "Work through traceability gaps with the trace tools",
    handler: async (_args: string, ctx: ExtCommandCtx) => {
      const check = runTraceCheck(ctx.cwd);
      if (check.ok) {
        ctx.ui.notify(`trace-fix: nothing pending (${check.deferred} deferred, ${check.exempt} exempt)`, "info");
        return;
      }

      const { skills } = loadSkills({
        cwd: ctx.cwd,
        agentDir: join(homedir(), ".pi", "agent"),
        skillPaths: [],
        includeDefaults: true,
      });

      const skillBlocks: string[] = [];
      for (const name of TRACE_FIX_SKILL_NAMES) {
        const skill = skills.find((s) => s.name === name);
        if (skill === undefined) {
          ctx.ui.notify(`/trace-fix: skill not found: ${name}`, "error");
          return;
        }
        const body = stripFrontmatter(readFileSync(skill.filePath, "utf-8")).trim();
        skillBlocks.push(buildSkillBlock({ name: skill.name, location: skill.filePath, body }));
      }

      const seed = buildTraceFixSeedPrompt(skillBlocks, check.report);
      // newSession() replaces the session and makes ctx stale (see /clear at
      // index.ts:446-452), so nothing may touch ctx after this call.
      await ctx.newSession({
        withSession: async (session: ReplacedSessionCtx) => {
          await session.sendUserMessage(seed, { deliverAs: "followUp" });
        },
      });
    },
  });
```

- [ ] **Step 4: Verify the suite and typecheck**

Run: `npm test --prefix pi-ext/factory-watch`
Expected: PASS — the full suite, no regressions in `handler.test.ts` or `smoke.test.ts`

Run: `npm run typecheck --prefix pi-ext/factory-watch`
Expected: no errors

- [ ] **Step 5: Manual verification — required, not inferable from unit tests**

Start pi with the extension in this repo, which has 45 known pending `task_no_sr`
gaps, and confirm each of these by hand:

1. `uv run python -m factory.trace check; echo $?` prints a non-zero exit **before**
   you start. A `0` means the gate is not detecting the known gaps — stop.
2. The five `trace_*` tools appear in the session's tool list.
3. `/trace-fix` seeds a session; the agent calls `trace_next` and the result shows
   **every** requirement with its statement, not a shortlist of five.
4. Ask the agent to link a task to a requirement it did *not* rank first, and
   confirm it can — the correct answer must be reachable regardless of rank.
5. Confirm with `git diff` that `satisfies:` was written to that task and nothing else.
6. Have the agent call `trace_link` with a non-existent `SR-999` and confirm the
   tool reports a refusal rather than writing a dangling reference.
7. Defer a gap with a reason; confirm `trace_deferred:` carries that exact text.
8. Confirm `trace_check` fails while gaps remain pending, and that the agent
   reports the failure rather than claiming completion.

- [ ] **Step 6: Commit**

```bash
git add pi-ext/factory-watch/src/index.ts
git commit -m "feat(factory-watch): /trace-fix seeding a tool-driven gap session

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Known limitations, stated rather than hidden

- **The gate is advisory *within* the session, authoritative outside it.** The
  extension cannot run `trace_check` after the agent finishes, so the skill
  instructs the agent to call it and report verbatim. What makes this safe is that
  `factory trace check` is stateless and runnable by a human or by CI at any time:
  an agent that skipped work cannot make it pass by saying otherwise. Treat the CLI,
  not the transcript, as the source of truth.
- **Ranking is still lexical.** Ordering candidates by shared-term overlap is
  deterministic and explainable but not semantic. It no longer limits what can be
  linked — nothing is truncated, and every statement is included — but a badly
  ordered list makes the model work harder. Improving the ranker is optional; it can
  never again make a correct link unreachable.
- **`trace_next` grows with the requirement register.** Every candidate is returned,
  so a register of several hundred requirements would make each call large. At that
  point the right fix is a retrieval step that is still recall-oriented (for example
  filtering by `domain`), never a top-N cut.
- **This plan does not prevent new gaps.** Gating `factory-run` on a task closing
  with no `satisfies:`, and teaching `writing-plans` to emit a spec key, remain
  deferred to their own spec (spec §9). Without them `/trace-fix` is bailing out a
  boat that is still taking on water.
