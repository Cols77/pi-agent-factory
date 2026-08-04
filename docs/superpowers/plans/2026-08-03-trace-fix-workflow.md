# `/trace-fix` Deterministic Gap-Closing Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close traceability gaps through a loop whose iteration, state, writes and completion check all live in code — the model contributes one bounded judgment per gap and never decides when the loop ends.

**Architecture:** `/trace-fix` drives a loop in TypeScript: `factory trace next --json` picks the gap and ranks candidates, `ctx.ui.select` collects the human's decision, `factory trace link|exempt|defer` performs the write, and `factory trace check` gates the end. A second mode, `/trace-fix --assist`, seeds an agent session with a deliberately narrow skill for cases where the human wants the model's reasoning on a hard gap.

**Tech Stack:** TypeScript (ES2022, NodeNext), vitest, and a Pi skill in `.pi/skills/`.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-03-review-plans-browser-and-trace-health-design.md` §6
- Prerequisites: plan `2026-08-03-trace-model-and-cli.md` (provides `next`, `link`, `exempt`, `defer`, `check`) and Task 1 of plan `2026-08-03-docs-browser-viewer.md` (provides `trace-cli.ts`).
- **The model never decides when the loop ends, never records its own progress, and never writes a file.** (Spec §6.1)
- The gate is `factory trace check`, which is **stateless** — it re-derives every gap and disposition from disk. Never add a session log it could consult instead.
- `pi-ext/factory-watch/package.json` has zero runtime dependencies. Do not add any.
- `tsconfig.json` sets `strict: true` and `noUncheckedIndexedAccess: true`.
- ESM/NodeNext: intra-package imports use the `.js` extension, including in tests.
- Run tests with `npm test --prefix pi-ext/factory-watch`.

## A constraint that shapes the design

`ctx.newSession()` **replaces the running session and makes `ctx` stale** — the
existing `/clear` handler documents this at `pi-ext/factory-watch/src/index.ts:446-452`
and returns immediately after calling it. A loop therefore cannot pause to consult
the model and then resume: seeding a session *ends* the command.

So the model cannot be called from inside the loop. Rather than pretend otherwise,
this plan splits the two modes:

- **`/trace-fix`** — the deterministic loop. Python ranks the candidates, the human
  picks, code writes, code gates. No model involved, and nothing to go off the rails.
- **`/trace-fix --assist`** — seeds an agent session for reasoning about hard gaps.
  Terminal by nature, because seeding replaces the session.

Both are gated by the same stateless `factory trace check`, which is also runnable
from CI. That is what makes the gate trustworthy: it does not care which mode
produced the dispositions, or whether anything produced them at all.

---

### Task 1: Extend the trace client with `next`, writes and `check`

**Files:**
- Modify: `pi-ext/factory-watch/src/trace-cli.ts` (append)
- Test: `pi-ext/factory-watch/test/trace-cli-actions.test.ts`

**Interfaces:**
- Consumes: `buildTraceCommand`, `TraceGap` from `trace-cli.ts` (plan 2, Task 1).
- Produces:
  - `TraceCandidate { id: string; title: string; evidence: string; score: number }`
  - `TraceProposal { gap: TraceGap; node_title: string; node_excerpt: string; candidates: TraceCandidate[] }`
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
  candidates: [{ id: "SR-001", title: "Preempt patrol", evidence: "shared terms: shark", score: 3 }],
};

describe("loadNextGap", () => {
  test("parses a proposal", () => {
    spawnSync.mockReturnValue({ status: 0, stdout: JSON.stringify(PROPOSAL), stderr: "" });
    const result = loadNextGap("/repo");
    expect(result.ok).toBe(true);
    if (result.ok) expect(result.proposal?.candidates[0]?.id).toBe("SR-001");
  });

  test("returns a null proposal when nothing is pending", () => {
    spawnSync.mockReturnValue({ status: 0, stdout: JSON.stringify({ gap: null }), stderr: "" });
    const result = loadNextGap("/repo");
    expect(result).toEqual({ ok: true, proposal: null });
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
    const result = runTraceCheck("/repo");
    expect(result).toMatchObject({ ok: true, pending: 0, deferred: 2, exempt: 1 });
  });

  test("fails when gaps are still undiscussed", () => {
    spawnSync.mockReturnValue({
      status: 1, stdout: "traceability health: 10%\n45 pending, 0 deferred, 0 exempt\n", stderr: "",
    });
    const result = runTraceCheck("/repo");
    expect(result.ok).toBe(false);
    expect(result.pending).toBe(45);
  });

  test("an unparsable report still reports failure from the exit code", () => {
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
  evidence: string;
  score: number;
}

export interface TraceProposal {
  gap: TraceGap;
  node_title: string;
  node_excerpt: string;
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
  const result = spawnSync(cmd.bin, cmd.args, { cwd, encoding: "utf-8" });
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

### Task 2: Pure action mapping

**Files:**
- Create: `pi-ext/factory-watch/src/trace-actions.ts`
- Test: `pi-ext/factory-watch/test/trace-actions.test.ts`

**Interfaces:**
- Consumes: `TraceProposal`, `TraceCandidate` (Task 1).
- Produces:
  - `DEFER_LABEL`, `EXEMPT_LABEL`, `SKIP_LABEL` — exported constants
  - `TraceAction` — `{ kind: "link"; taskId: string; srId: string } | { kind: "linkSpec"; planId: string; specFile: string } | { kind: "exempt"; nodeId: string; reason: string } | { kind: "defer"; nodeId: string; reason: string } | { kind: "skip" }`
  - `formatGapSummary(proposal: TraceProposal): string`
  - `buildActionOptions(proposal: TraceProposal): string[]`
  - `resolveAction(proposal: TraceProposal, label: string, reason: string): TraceAction | null`
  - `buildActionArgs(action: TraceAction): string[] | null`
- **Link direction matters.** `satisfies` always lives on the *task*. For a
  `task_no_sr` gap the node is the task and the candidate is the SR; for an
  `sr_unsatisfied` gap the node is the SR and the candidate is the task. Both
  produce `link <taskId> --satisfies <srId>`.

- [ ] **Step 1: Write the failing test**

Create `pi-ext/factory-watch/test/trace-actions.test.ts`:

```ts
import { describe, expect, test } from "vitest";
import {
  DEFER_LABEL,
  EXEMPT_LABEL,
  SKIP_LABEL,
  buildActionArgs,
  buildActionOptions,
  formatGapSummary,
  resolveAction,
} from "../src/trace-actions.js";
import type { TraceProposal } from "../src/trace-cli.js";

function proposal(kind: string, nodeId: string, candidateId: string): TraceProposal {
  return {
    gap: { node_id: nodeId, kind, detail: "detail here", disposition: "pending" },
    node_title: "Some Title",
    node_excerpt: "excerpt",
    candidates: [{ id: candidateId, title: "Candidate Title", evidence: "shared terms: shark", score: 3 }],
  };
}

describe("buildActionOptions", () => {
  test("lists candidates first, then defer, exempt and skip", () => {
    const options = buildActionOptions(proposal("task_no_sr", "T-001", "SR-001"));
    expect(options[0]).toContain("SR-001");
    expect(options).toContain(DEFER_LABEL);
    expect(options).toContain(EXEMPT_LABEL);
    expect(options).toContain(SKIP_LABEL);
  });

  test("never offers to exempt a requirement", () => {
    // The CLI refuses it (spec 4.4); offering it would produce a guaranteed error.
    const options = buildActionOptions(proposal("sr_unvalidated", "SR-001", ""));
    expect(options).not.toContain(EXEMPT_LABEL);
    expect(options).toContain(DEFER_LABEL);
  });

  test("a gap with no candidates still offers a way out", () => {
    const p = proposal("dangling_upstream", "SR-001", "");
    p.candidates = [];
    expect(buildActionOptions(p)).toEqual([DEFER_LABEL, SKIP_LABEL]);
  });
});

describe("resolveAction", () => {
  test("task_no_sr links the task to the chosen requirement", () => {
    const p = proposal("task_no_sr", "T-001", "SR-001");
    const action = resolveAction(p, buildActionOptions(p)[0]!, "");
    expect(action).toEqual({ kind: "link", taskId: "T-001", srId: "SR-001" });
  });

  test("sr_unsatisfied flips the direction: satisfies is written on the task", () => {
    const p = proposal("sr_unsatisfied", "SR-001", "T-042");
    const action = resolveAction(p, buildActionOptions(p)[0]!, "");
    expect(action).toEqual({ kind: "link", taskId: "T-042", srId: "SR-001" });
  });

  test("plan_no_spec links the plan to the chosen spec file", () => {
    const p = proposal("plan_no_spec", "plan:p1.md", "spec:s1.md");
    const action = resolveAction(p, buildActionOptions(p)[0]!, "");
    expect(action).toEqual({ kind: "linkSpec", planId: "plan:p1.md", specFile: "s1.md" });
  });

  test("defer and exempt carry the reason", () => {
    const p = proposal("task_no_sr", "T-001", "SR-001");
    expect(resolveAction(p, DEFER_LABEL, "needs a split")).toEqual({
      kind: "defer", nodeId: "T-001", reason: "needs a split",
    });
    expect(resolveAction(p, EXEMPT_LABEL, "tooling")).toEqual({
      kind: "exempt", nodeId: "T-001", reason: "tooling",
    });
  });

  test("defer without a reason is refused rather than written blank", () => {
    const p = proposal("task_no_sr", "T-001", "SR-001");
    expect(resolveAction(p, DEFER_LABEL, "   ")).toBeNull();
  });

  test("skip resolves to skip", () => {
    const p = proposal("task_no_sr", "T-001", "SR-001");
    expect(resolveAction(p, SKIP_LABEL, "")).toEqual({ kind: "skip" });
  });

  test("an unrecognised label resolves to nothing", () => {
    const p = proposal("task_no_sr", "T-001", "SR-001");
    expect(resolveAction(p, "something else", "")).toBeNull();
  });
});

describe("buildActionArgs", () => {
  test("link", () => {
    expect(buildActionArgs({ kind: "link", taskId: "T-001", srId: "SR-001" }))
      .toEqual(["link", "T-001", "--satisfies", "SR-001"]);
  });

  test("linkSpec", () => {
    expect(buildActionArgs({ kind: "linkSpec", planId: "plan:p1.md", specFile: "s1.md" }))
      .toEqual(["link", "plan:p1.md", "--spec", "s1.md"]);
  });

  test("exempt and defer", () => {
    expect(buildActionArgs({ kind: "exempt", nodeId: "T-001", reason: "tooling" }))
      .toEqual(["exempt", "T-001", "--reason", "tooling"]);
    expect(buildActionArgs({ kind: "defer", nodeId: "T-001", reason: "later" }))
      .toEqual(["defer", "T-001", "--reason", "later"]);
  });

  test("skip runs nothing", () => {
    expect(buildActionArgs({ kind: "skip" })).toBeNull();
  });
});

describe("formatGapSummary", () => {
  test("names the gap, the node and the evidence", () => {
    const summary = formatGapSummary(proposal("task_no_sr", "T-001", "SR-001"));
    expect(summary).toContain("T-001");
    expect(summary).toContain("task_no_sr");
    expect(summary).toContain("Some Title");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test --prefix pi-ext/factory-watch -- trace-actions`
Expected: FAIL — cannot resolve `../src/trace-actions.js`

- [ ] **Step 3: Write minimal implementation**

Create `pi-ext/factory-watch/src/trace-actions.ts`:

```ts
import type { TraceProposal } from "./trace-cli.js";

export const DEFER_LABEL = "Defer — discussed, needs more time";
export const EXEMPT_LABEL = "Exempt — no requirement applies here";
export const SKIP_LABEL = "Skip — leave pending (the gate will fail)";

export type TraceAction =
  | { kind: "link"; taskId: string; srId: string }
  | { kind: "linkSpec"; planId: string; specFile: string }
  | { kind: "exempt"; nodeId: string; reason: string }
  | { kind: "defer"; nodeId: string; reason: string }
  | { kind: "skip" };

const LINKABLE = new Set(["task_no_sr", "sr_unsatisfied", "plan_no_spec"]);

function isRequirementGap(kind: string): boolean {
  return kind.startsWith("sr_") || kind === "dangling_upstream";
}

function candidateLabel(index: number, id: string, title: string, evidence: string): string {
  return `${index + 1}. ${id} — ${title}  (${evidence})`;
}

export function buildActionOptions(proposal: TraceProposal): string[] {
  const options: string[] = [];
  if (LINKABLE.has(proposal.gap.kind)) {
    proposal.candidates.forEach((c, i) => {
      options.push(candidateLabel(i, c.id, c.title, c.evidence));
    });
  }
  options.push(DEFER_LABEL);
  // Requirements are deliberately not exemptable (spec 4.4) -- the CLI refuses,
  // so offering the option here would only produce a guaranteed error.
  if (!isRequirementGap(proposal.gap.kind)) options.push(EXEMPT_LABEL);
  options.push(SKIP_LABEL);
  return options;
}

export function resolveAction(
  proposal: TraceProposal,
  label: string,
  reason: string,
): TraceAction | null {
  const nodeId = proposal.gap.node_id;

  if (label === SKIP_LABEL) return { kind: "skip" };

  if (label === DEFER_LABEL || label === EXEMPT_LABEL) {
    const trimmed = reason.trim();
    // A blank reason would record that we looked without recording what we saw.
    if (trimmed === "") return null;
    return label === DEFER_LABEL
      ? { kind: "defer", nodeId, reason: trimmed }
      : { kind: "exempt", nodeId, reason: trimmed };
  }

  const index = proposal.candidates.findIndex(
    (c, i) => candidateLabel(i, c.id, c.title, c.evidence) === label,
  );
  const candidate = proposal.candidates[index];
  if (candidate === undefined) return null;

  if (proposal.gap.kind === "task_no_sr") {
    return { kind: "link", taskId: nodeId, srId: candidate.id };
  }
  if (proposal.gap.kind === "sr_unsatisfied") {
    // satisfies always lives on the task, so the direction flips here.
    return { kind: "link", taskId: candidate.id, srId: nodeId };
  }
  if (proposal.gap.kind === "plan_no_spec") {
    return { kind: "linkSpec", planId: nodeId, specFile: candidate.id.replace(/^spec:/, "") };
  }
  return null;
}

export function buildActionArgs(action: TraceAction): string[] | null {
  switch (action.kind) {
    case "link":
      return ["link", action.taskId, "--satisfies", action.srId];
    case "linkSpec":
      return ["link", action.planId, "--spec", action.specFile];
    case "exempt":
      return ["exempt", action.nodeId, "--reason", action.reason];
    case "defer":
      return ["defer", action.nodeId, "--reason", action.reason];
    case "skip":
      return null;
  }
}

export function formatGapSummary(proposal: TraceProposal): string {
  return `${proposal.gap.node_id}  [${proposal.gap.kind}]  ${proposal.node_title}\n${proposal.gap.detail}`;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test --prefix pi-ext/factory-watch -- trace-actions`
Expected: PASS — 15 passed

- [ ] **Step 5: Commit**

```bash
git add pi-ext/factory-watch/src/trace-actions.ts pi-ext/factory-watch/test/trace-actions.test.ts
git commit -m "feat(factory-watch): pure action mapping for the trace-fix loop

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: The `trace-fix` skill and its seed prompt

**Files:**
- Create: `.pi/skills/trace-fix/SKILL.md`
- Modify: `pi-ext/factory-watch/src/skill-prompt.ts` (append a builder)
- Test: `pi-ext/factory-watch/test/skill-prompt.test.ts` (extend)

**Interfaces:**
- Consumes: `buildSkillBlock` (existing, `skill-prompt.ts:7`).
- Produces: `buildTraceFixSeedPrompt(skillBlocks: string[], gapReport: string): string`.

- [ ] **Step 1: Write the failing test**

Append to `pi-ext/factory-watch/test/skill-prompt.test.ts`:

```ts
import { buildTraceFixSeedPrompt } from "../src/skill-prompt.js";

describe("buildTraceFixSeedPrompt", () => {
  const prompt = buildTraceFixSeedPrompt(["<skill name=\"trace-fix\">body</skill>"], "45 pending");

  test("includes the skill block and the current gap report", () => {
    expect(prompt).toContain("<skill name=\"trace-fix\">");
    expect(prompt).toContain("45 pending");
  });

  test("instructs the agent to use the CLI for both enumeration and writes", () => {
    expect(prompt).toContain("factory.trace next");
    expect(prompt).toContain("factory.trace check");
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
    "The CLI owns enumeration, ordering, candidate ranking, and every write. You own exactly one thing: judging which candidate is right for the gap in front of you, and saying why.",
    "Loop: run `uv run python -m factory.trace next --json` to get the next gap. Reason about its candidates. Propose one to the human with the evidence you based it on, and wait for their answer. Apply their decision with `uv run python -m factory.trace link|exempt|defer`. Repeat until `next` reports no pending gaps.",
    "Never edit `satisfies:`, `trace_exempt:` or `trace_deferred:` in a file directly — the CLI validates link targets, and a hand-edited link can create a dangling reference it would have refused.",
    "Never claim a gap was handled without having run the write command; the gate re-reads the files and will contradict you.",
    "Finish by running `uv run python -m factory.trace check` and reporting its output and exit code verbatim.",
  ].join("\n\n");
  return [...skillBlocks, instructions, `Current gap report:\n${gapReport}`].join("\n\n");
}
```

- [ ] **Step 4: Write the skill**

Create `.pi/skills/trace-fix/SKILL.md`:

```markdown
---
name: trace-fix
description: Close traceability gaps one at a time — reason about the single gap the CLI hands you, propose a link with its evidence, and let the CLI perform every write.
---

# Trace fix

Use this when the human wants to improve traceability health: linking tasks to the
system requirements they satisfy, plans to the specs they implement, or recording
an honest exemption or deferral where no link belongs.

## What you own, and what you do not

You own **one judgment per gap**: which candidate is right, and why.

You do **not** own iteration, ordering, candidate selection, writing, or deciding
when the work is finished. All of those live in `factory trace`. This is deliberate
— a gate that trusted your account of your own progress would be worthless.

## Steps

1. **Get the next gap.** Run `uv run python -m factory.trace next --json`. It
   returns the gap, the node's title and excerpt, and up to five candidates ranked
   by shared terminology. If it returns `{"gap": null}`, go to step 5.
2. **Judge.** Read the node excerpt and the candidates' evidence. Decide which
   candidate genuinely fits — shared vocabulary is a hint, not a verdict. If none
   fits, say so; a wrong link is worse than an honest deferral.
3. **Propose, then wait.** Tell the human the gap, your recommendation, and the
   evidence behind it. Ask them to confirm, choose another candidate, exempt, or
   defer. Do not proceed without their answer.
4. **Apply their decision**, then return to step 1:
   - `uv run python -m factory.trace link <task-id> --satisfies <SR-###>`
   - `uv run python -m factory.trace link <plan-id> --spec <filename.md>`
   - `uv run python -m factory.trace exempt <node-id> --reason "<why>"`
   - `uv run python -m factory.trace defer <node-id> --reason "<why>"`
5. **Run the gate.** `uv run python -m factory.trace check`. Report its output and
   exit code verbatim, including any gaps still pending.

## Rules

- **Never edit `satisfies:`, `trace_exempt:` or `trace_deferred:` by hand.** The CLI
  verifies that a link target exists; a hand-written link can create the dangling
  reference the CLI would have refused.
- **Never assert a gap is handled without having run the command.** The gate
  re-derives everything from disk and will contradict you.
- **A deferral needs a real reason.** "Needs more time" alone is not one — record
  what has to happen before it can be resolved.
- **Requirements cannot be exempted.** An SR that no task satisfies and no run
  validates is a real gap. Defer it instead.
- **Do not batch.** One gap, one proposal, one confirmation.
```

- [ ] **Step 5: Run test to verify it passes**

Run: `npm test --prefix pi-ext/factory-watch -- skill-prompt`
Expected: PASS — 3 new tests pass alongside the existing ones

- [ ] **Step 6: Commit**

```bash
git add .pi/skills/trace-fix/SKILL.md pi-ext/factory-watch/src/skill-prompt.ts pi-ext/factory-watch/test/skill-prompt.test.ts
git commit -m "feat(trace-fix): narrow skill owning one judgment per gap

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 4: The `/trace-fix` command

**Files:**
- Modify: `pi-ext/factory-watch/src/index.ts` (register the command; imports)
- Test: manual — see Step 4

**Interfaces:**
- Consumes: `loadNextGap`, `runTrace`, `runTraceCheck` (Task 1); `buildActionOptions`,
  `resolveAction`, `buildActionArgs`, `formatGapSummary`, `DEFER_LABEL`, `EXEMPT_LABEL`
  (Task 2); `buildTraceFixSeedPrompt`, `buildSkillBlock` (Task 3); `loadSkills`,
  `stripFrontmatter` (already imported at `index.ts:13`).
- Produces: the `/trace-fix` command.

- [ ] **Step 1: Add the imports**

In `pi-ext/factory-watch/src/index.ts`, add beside the existing imports:

```ts
import { loadNextGap, runTrace, runTraceCheck } from "./trace-cli.js";
import {
  DEFER_LABEL,
  EXEMPT_LABEL,
  buildActionArgs,
  buildActionOptions,
  formatGapSummary,
  resolveAction,
} from "./trace-actions.js";
import { buildTraceFixSeedPrompt } from "./skill-prompt.js";
```

Add beside the other constants near `PLAN_SKILL_NAMES` at `index.ts:43`:

```ts
const TRACE_FIX_SKILL_NAMES = ["trace-fix"];
const TRACE_FIX_MAX_ITERATIONS = 200;
```

- [ ] **Step 2: Register the command**

Add at the end of the registration block in `pi-ext/factory-watch/src/index.ts`,
after the `review-plans` registration:

```ts
  pi.registerCommand("trace-fix", {
    description: "Close traceability gaps one at a time (--assist for agent reasoning)",
    handler: async (args: string, ctx: ExtCommandCtx) => {
      const assist = /(^|\s)--assist(\s|$)/.test(args);

      if (assist) {
        // Seeding replaces the session and makes ctx stale (see /clear at
        // index.ts:446-452), so this mode necessarily ends the command.
        const check = runTraceCheck(ctx.cwd);
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
        await ctx.newSession({
          withSession: async (session: ReplacedSessionCtx) => {
            await session.sendUserMessage(seed, { deliverAs: "followUp" });
          },
        });
        return;
      }

      // The deterministic loop: the CLI picks the gap and ranks candidates, the
      // human decides, the CLI writes, the CLI gates. No model in the loop.
      let handled = 0;
      let skipped = 0;
      for (let i = 0; i < TRACE_FIX_MAX_ITERATIONS; i += 1) {
        const next = loadNextGap(ctx.cwd);
        if (!next.ok) {
          ctx.ui.notify(`trace-fix: ${next.error}`, "error");
          return;
        }
        if (next.proposal === null) break;

        const proposal = next.proposal;
        const options = buildActionOptions(proposal);
        const choice = await ctx.ui.select(formatGapSummary(proposal), options);
        if (choice === undefined) {
          ctx.ui.notify("trace-fix: cancelled", "info");
          break;
        }

        let reason = "";
        if (choice === DEFER_LABEL || choice === EXEMPT_LABEL) {
          const entered = await ctx.ui.editor(
            choice === DEFER_LABEL
              ? `Why is ${proposal.gap.node_id} deferred? (what must happen first)`
              : `Why does no requirement apply to ${proposal.gap.node_id}?`,
          );
          if (entered === undefined) continue;
          reason = entered;
        }

        const action = resolveAction(proposal, choice, reason);
        if (action === null) {
          ctx.ui.notify("trace-fix: a reason is required — nothing written", "warning");
          continue;
        }
        if (action.kind === "skip") {
          skipped += 1;
          // Skipping leaves the gap pending, so `next` would hand it back forever.
          // Stop rather than spin; the gate below will report it.
          ctx.ui.notify("trace-fix: skipped — stopping so the gate can report it", "info");
          break;
        }

        const cliArgs = buildActionArgs(action);
        if (cliArgs === null) continue;
        const result = runTrace(ctx.cwd, cliArgs);
        if (!result.ok) {
          ctx.ui.notify(`trace-fix: ${result.stdout || result.stderr}`.trim(), "error");
          break;
        }
        handled += 1;
      }

      const check = runTraceCheck(ctx.cwd);
      ctx.ui.notify(
        check.ok
          ? `trace-fix: ${handled} handled, ${check.deferred} deferred, ${check.exempt} exempt — gate passed`
          : `trace-fix: ${handled} handled, ${skipped} skipped, ${check.pending} still pending — gate FAILED`,
        check.ok ? "info" : "warning",
      );
    },
  });
```

- [ ] **Step 3: Verify the suite and typecheck**

Run: `npm test --prefix pi-ext/factory-watch`
Expected: PASS — the full suite, no regressions

Run: `npm run typecheck --prefix pi-ext/factory-watch`
Expected: no errors

- [ ] **Step 4: Manual verification — required, not inferable from unit tests**

Start pi with the extension in this repo, which has 45 known pending `task_no_sr`
gaps, and confirm each of these by hand:

1. `uv run python -m factory.trace check; echo $?` prints a non-zero exit **before**
   you start. If it prints `0`, stop — the gate is not detecting the known gaps.
2. `/trace-fix` presents one gap with ranked candidates. Choose a candidate, then
   confirm with `git diff` that `satisfies:` was written to that task and nothing else.
3. Choose **Defer** on the next gap, enter a reason, and confirm `trace_deferred:`
   carries that exact reason.
4. Press escape at the reason editor and confirm **nothing** is written.
5. Choose **Skip** and confirm the loop stops and the closing notification reports
   the gate failing with a pending count.
6. Run `/trace-fix` again and confirm the deferred gap is **not** offered again,
   and that the previously linked task no longer appears.
7. Exempt every remaining gap, then confirm `factory trace check` exits `0` and
   `/trace-fix` reports "gate passed".
8. `/trace-fix --assist` seeds a fresh session containing the skill and the current
   gap report.

- [ ] **Step 5: Commit**

```bash
git add pi-ext/factory-watch/src/index.ts
git commit -m "feat(factory-watch): /trace-fix deterministic loop with a stateless gate

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Known limitations, stated rather than hidden

- **`--assist` mode's gate is advisory.** Because seeding replaces the session, the
  extension cannot run `check` after the agent finishes; the skill instructs the
  agent to run it and report verbatim. The authoritative gate remains
  `factory trace check`, runnable by the human or by CI at any time, and it is
  stateless — so an agent that skipped work cannot make it pass by saying otherwise.
- **Skipping stops the loop.** A skipped gap stays pending, and `next` returns gaps
  in a fixed order, so continuing would hand back the same gap forever. Stopping and
  reporting is the honest behaviour; resuming past a skip would need per-session
  skip state, which is exactly the drift-prone side ledger spec §6.2 rejects.
- **Candidate ranking is shared-term overlap.** It is deterministic and explainable,
  but it is not semantic — it will miss a task and an SR that describe the same
  behaviour in different vocabulary. That is what `--assist` is for, and why every
  proposal requires human confirmation.
- **This plan does not prevent new gaps.** Gating `factory-run` on a task closing
  with no `satisfies:`, and teaching `writing-plans` to emit a spec key, remain
  deferred to their own spec (spec §9). Without them `/trace-fix` is bailing out a
  boat that is still taking on water.
