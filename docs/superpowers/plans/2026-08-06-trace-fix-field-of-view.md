# Trace-fix Field of View Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop the `\trace-fix` loop from letting constants decide what the agent may consider — show the whole pending gap set, give the candidate-less gap kinds honest guidance, and mark truncated text — without weakening the gate.

**Architecture:** Three independent changes across one Python module and three TypeScript ones. `Proposal` gains the full pending list and `next_gap` gains an optional focus id, so visibility is separated from commit granularity. `formatProposal` renders per-kind guidance instead of one message that only fits half the kinds. Truncation points gain a marker naming the file. `trace check` and the candidate ranking are untouched.

**Tech Stack:** Python 3.11–3.12 (`propose.py`, `cli.py`), TypeScript / vitest (`pi-ext/factory-watch`), pytest.

**Spec:** `docs/superpowers/specs/2026-08-06-trace-fix-field-of-view-design.md`

## Global Constraints

- Python `>=3.11,<3.13`; `ruff` line-length **100**; `pyright` standard mode clean.
- Python tests: `uv run pytest -m unit`. TypeScript: `npm test` and `npm run typecheck` in `pi-ext/factory-watch`.
- **No new dependencies** in either language.
- `pending_total` stays on `Proposal`. The existing test at `docs/superpowers/plans/2026-08-03-trace-model-and-cli.md` line 1675 asserts it, and removing it is not part of this work.
- **Do not touch** `trace check`, `_terms`, `_STOPWORDS`, the candidate score ordering, `_EXCERPT_CHARS`/`_SUMMARY_CHARS` values, or any gap kind. Gap kinds are owned by `2026-08-06-requirement-doctor-design.md` §8.
- The "lexical hint, not a verdict" warning appears at four surfaces (`propose.py`, `trace-tools.ts`, `trace-tool-format.ts`, `skill-prompt.ts`). All four stay.

---

### Task 1: `Proposal` carries every pending gap, and a gap can be chosen

**Files:**
- Modify: `src/factory/trace/propose.py`
- Modify: `src/factory/trace/cli.py`
- Test: `tests/unit/trace/test_propose.py`

**Interfaces:**
- Produces: `PendingGap(node_id: str, kind: str, detail: str)`, `Proposal.pending: list[PendingGap]`, `next_gap(root: Path, node_id: str | None = None) -> Proposal | None`, `UnknownGapError(ValueError)`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/trace/test_propose.py -- append
import pytest

from factory.trace.propose import UnknownGapError, next_gap


def _task(tmp_path, task_id: str) -> None:
    d = tmp_path / "tasks"
    d.mkdir(exist_ok=True)
    (d / f"{task_id}.md").write_text(
        f"---\nid: {task_id}\ntitle: {task_id}\nstatus: todo\ndod: []\n---\nbody\n",
        encoding="utf-8",
    )


def test_the_proposal_lists_every_pending_gap(tmp_path):
    for task_id in ("T-001", "T-002"):
        _task(tmp_path, task_id)
    proposal = next_gap(tmp_path)
    assert len(proposal.pending) == proposal.pending_total
    assert {p.node_id for p in proposal.pending} == {"T-001", "T-002"}
    assert {p.kind for p in proposal.pending} == {"task_no_sr", "task_no_plan"}


def test_the_default_focus_is_unchanged(tmp_path):
    _task(tmp_path, "T-002")
    _task(tmp_path, "T-001")
    assert next_gap(tmp_path).gap.node_id == "T-001"


def test_a_named_gap_is_focused_and_the_list_is_the_same(tmp_path):
    _task(tmp_path, "T-001")
    _task(tmp_path, "T-002")
    focused = next_gap(tmp_path, node_id="T-002")
    assert focused.gap.node_id == "T-002"
    assert len(focused.pending) == next_gap(tmp_path).pending_total


def test_an_unknown_gap_is_refused(tmp_path):
    _task(tmp_path, "T-001")
    with pytest.raises(UnknownGapError, match="T-404"):
        next_gap(tmp_path, node_id="T-404")


def test_no_gaps_at_all_is_still_none(tmp_path):
    (tmp_path / "tasks").mkdir()
    assert next_gap(tmp_path) is None
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/unit/trace/test_propose.py -v`
Expected: FAIL — `AttributeError: 'Proposal' object has no attribute 'pending'`

- [ ] **Step 3: Implement**

```python
# src/factory/trace/propose.py -- changed regions only
@dataclass(frozen=True)
class PendingGap:
    node_id: str
    kind: str
    detail: str


@dataclass(frozen=True)
class Proposal:
    gap: Gap
    node_title: str
    node_excerpt: str
    pending_total: int
    candidates: list[Candidate]
    pending: list[PendingGap]


class UnknownGapError(ValueError):
    pass


def next_gap(root: Path, node_id: str | None = None) -> Proposal | None:
    graph = build_graph(root)
    by_id = {n.id: n for n in graph.nodes}
    pending = [g for g in graph.gaps if g.disposition == "pending"]
    if not pending:
        return None
    listing = [PendingGap(g.node_id, g.kind, g.detail) for g in pending]

    if node_id is not None:
        chosen = next((g for g in pending if g.node_id == node_id), None)
        if chosen is None:
            raise UnknownGapError(f"no pending gap for {node_id!r}")
        candidates = [chosen]
    else:
        # Default order stays _KIND_ORDER then node id. It is a default, not a
        # queue: the caller may name any pending gap instead.
        candidates = pending

    for gap in candidates:
        node = by_id.get(gap.node_id)
        if node is None:
            continue
        return Proposal(
            gap=gap,
            node_title=node.title,
            node_excerpt=_read(node.path)[:_EXCERPT_CHARS],
            pending_total=len(pending),
            candidates=_candidates_for(gap, node, graph.nodes),
            pending=listing,
        )
    return None
```

`proposal_to_dict` needs no change — `asdict` already walks the new field, and `PendingGap` is a dataclass.

- [ ] **Step 4: Add the CLI flag**

```python
# src/factory/trace/cli.py -- in main()
    p_next.add_argument("--node-id", dest="node_id", default=None)
```

```python
# src/factory/trace/cli.py -- in the "next" branch, replacing the first line
    elif args.cmd == "next":
        try:
            proposal = next_gap(args.project_root, args.node_id)
        except UnknownGapError as exc:
            print(str(exc))
            return 1
```

Import `UnknownGapError` alongside `next_gap` at the top of `cli.py`.

- [ ] **Step 5: Run to verify they pass**

Run: `uv run pytest tests/unit/trace/ -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
uv run ruff check . && uv run pyright
git add src/factory/trace/propose.py src/factory/trace/cli.py tests/unit/trace/test_propose.py
git commit -m "feat(trace): the proposal carries every pending gap, and a gap can be chosen"
```

---

### Task 2: Mark truncated excerpts and summaries

**Files:**
- Modify: `src/factory/trace/propose.py`
- Test: `tests/unit/trace/test_propose.py`

**Interfaces:**
- Produces: `_clip(text: str, limit: int, path: Path) -> str` (module-private).

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/trace/test_propose.py -- append
def test_a_long_excerpt_is_marked_and_names_its_file(tmp_path):
    d = tmp_path / "tasks"
    d.mkdir(exist_ok=True)
    body = "x" * 5000
    (d / "T-001.md").write_text(
        f"---\nid: T-001\ntitle: t\nstatus: todo\ndod: []\n---\n{body}\n", encoding="utf-8"
    )
    excerpt = next_gap(tmp_path).node_excerpt
    assert "[truncated at 1200 chars" in excerpt
    assert "T-001.md" in excerpt


def test_a_short_excerpt_is_untouched(tmp_path):
    d = tmp_path / "tasks"
    d.mkdir(exist_ok=True)
    (d / "T-001.md").write_text(
        "---\nid: T-001\ntitle: t\nstatus: todo\ndod: []\n---\nshort\n", encoding="utf-8"
    )
    excerpt = next_gap(tmp_path).node_excerpt
    assert "truncated" not in excerpt
    assert excerpt == (tmp_path / "tasks" / "T-001.md").read_text(encoding="utf-8")
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/unit/trace/test_propose.py -v`
Expected: FAIL — the excerpt is clipped with no marker.

- [ ] **Step 3: Implement**

```python
# src/factory/trace/propose.py -- add near _read
def _clip(text: str, limit: int, path: Path) -> str:
    """Clip, and say so. A clipped excerpt that looks complete is how a task's dod
    block silently stops being part of the judgement."""
    if len(text) <= limit:
        return text
    return f"{text[:limit]}…[truncated at {limit} chars — read {path.as_posix()} for the full text]"
```

Apply it at all three truncation points:

```python
# in _summary_of -- the statement branch
            return _clip(str(statement), _SUMMARY_CHARS, node.path)
# in _summary_of -- the first-prose-line branch
            return _clip(stripped, _SUMMARY_CHARS, node.path)
# in next_gap
            node_excerpt=_clip(_read(node.path), _EXCERPT_CHARS, node.path),
```

`_summary_of` already takes `node`, so `node.path` is in scope at both call sites.

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/unit/trace/ -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
uv run ruff check . && uv run pyright
git add src/factory/trace/propose.py tests/unit/trace/test_propose.py
git commit -m "feat(trace): mark truncated excerpts and name the file to read"
```

---

### Task 3: Carry the pending list and the focus id across the TS bridge

**Files:**
- Modify: `pi-ext/factory-watch/src/trace-cli.ts`
- Modify: `pi-ext/factory-watch/src/trace-tools.ts`
- Test: `pi-ext/factory-watch/test/trace-tools.test.ts`

**Interfaces:**
- Consumes: `Proposal.pending` and the `--node-id` flag from Task 1.
- Produces: `TracePendingGap`, `TraceProposal.pending`, `loadNextGap(cwd: string, nodeId?: string)`.

- [ ] **Step 1: Write the failing tests**

Append to `pi-ext/factory-watch/test/trace-tools.test.ts`. That file already hoists the `spawnSync` mock and defines `CTX`, `run`, `PROPOSAL` and `traceArgs` — reuse them rather than re-declaring.

```typescript
// pi-ext/factory-watch/test/trace-tools.test.ts -- append
const PROPOSAL_WITH_PENDING = {
  ...PROPOSAL,
  pending: [
    { node_id: "T-047", kind: "task_no_sr", detail: "task declares no satisfies" },
    { node_id: "T-048", kind: "task_no_plan", detail: "task declares no source_plan" },
  ],
};

describe("trace_next gap selection", () => {
  test("omits --node-id when none is given", async () => {
    spawnSync.mockReturnValue({
      status: 0,
      stdout: JSON.stringify(PROPOSAL_WITH_PENDING),
      stderr: "",
    });
    await run(traceNextTool, {});
    expect(spawnSync).toHaveBeenCalledWith("uv", traceArgs("next", "--json"), expect.anything());
  });

  test("forwards --node-id when given", async () => {
    spawnSync.mockReturnValue({
      status: 0,
      stdout: JSON.stringify(PROPOSAL_WITH_PENDING),
      stderr: "",
    });
    await run(traceNextTool, { node_id: "T-048" });
    expect(spawnSync).toHaveBeenCalledWith(
      "uv",
      traceArgs("next", "--json", "--node-id", "T-048"),
      expect.anything(),
    );
  });

  test("renders every pending gap, not only the focused one", async () => {
    spawnSync.mockReturnValue({
      status: 0,
      stdout: JSON.stringify(PROPOSAL_WITH_PENDING),
      stderr: "",
    });
    const result = await run(traceNextTool, {});
    expect(result.content).toContain("T-047");
    expect(result.content).toContain("T-048");
  });
});
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd pi-ext/factory-watch && npm test`
Expected: FAIL — `Property 'pending' does not exist on type 'TraceProposal'`.

- [ ] **Step 3: Implement**

```typescript
// pi-ext/factory-watch/src/trace-cli.ts -- changed regions only
export interface TracePendingGap {
  node_id: string;
  kind: string;
  detail: string;
}

export interface TraceProposal {
  gap: TraceGap;
  node_title: string;
  node_excerpt: string;
  pending_total: number;
  candidates: TraceCandidate[];
  pending: TracePendingGap[];
}

export function loadNextGap(
  cwd: string,
  nodeId?: string,
): { ok: true; proposal: TraceProposal | null } | { ok: false; error: string } {
  const sub = nodeId ? ["next", "--json", "--node-id", nodeId] : ["next", "--json"];
  const result = runTrace(cwd, sub);
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
```

```typescript
// pi-ext/factory-watch/src/trace-tools.ts -- traceNextTool
export const traceNextTool = {
  name: "trace_next",
  label: "Trace: next gap",
  description:
    "Return a pending traceability gap with the node's excerpt, EVERY candidate target " +
    "including its full requirement statement, and the full list of pending gaps. Candidates " +
    "are ordered by shared-term overlap, which is a lexical hint only — judge matches by " +
    "meaning, not by position. Pass `node_id` to work a specific gap; the default order is a " +
    "default, not a queue.",
  parameters: Type.Object({
    node_id: Type.Optional(
      Type.String({ description: "Pending gap to focus, e.g. T-047. Omit for the first." }),
    ),
  }),
  async execute(
    _id: string,
    params: { node_id?: string },
    _signal: AbortSignal | undefined,
    _onUpdate: unknown,
    ctx: ToolCtx,
  ) {
    const next = loadNextGap(ctx.cwd, params.node_id);
    if (!next.ok) return result(`trace_next failed: ${next.error}`);
    if (next.proposal === null) return result(formatNoGaps());
    return result(formatProposal(next.proposal));
  },
};
```

- [ ] **Step 4: Run to verify they pass**

Run: `cd pi-ext/factory-watch && npm test && npm run typecheck`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pi-ext/factory-watch/src/trace-cli.ts pi-ext/factory-watch/src/trace-tools.ts pi-ext/factory-watch/test/trace-tools.test.ts
git commit -m "feat(trace-tools): trace_next carries the pending list and accepts a focus id"
```

---

### Task 4: Render the pending list and per-kind guidance

**Files:**
- Modify: `pi-ext/factory-watch/src/trace-tool-format.ts`
- Test: `pi-ext/factory-watch/test/trace-tool-format.test.ts`

**Interfaces:**
- Consumes: `TraceProposal.pending` from Task 3.

- [ ] **Step 1: Write the failing tests**

```typescript
// pi-ext/factory-watch/test/trace-tool-format.test.ts
import { describe, expect, test } from "vitest";
import { formatProposal } from "../src/trace-tool-format.js";
import type { TraceProposal } from "../src/trace-cli.js";

function proposal(kind: string): TraceProposal {
  return {
    gap: { node_id: "SR-001", kind, detail: "no harness declared", disposition: "pending" },
    node_title: "t",
    node_excerpt: "e",
    pending_total: 2,
    candidates: [],
    pending: [
      { node_id: "SR-001", kind, detail: "no harness declared" },
      { node_id: "T-002", kind: "task_no_plan", detail: "task declares no source_plan" },
    ],
  };
}

describe("formatProposal", () => {
  test("renders every pending gap and labels the order as a default", () => {
    const out = formatProposal(proposal("task_no_sr"));
    expect(out).toContain("SR-001");
    expect(out).toContain("T-002");
    expect(out.toLowerCase()).toContain("a default, not a queue");
  });

  test("an unvalidated requirement is not told to exempt or link", () => {
    const out = formatProposal(proposal("sr_unvalidated"));
    expect(out).toContain("running validation");
    expect(out).not.toContain("trace_exempt");
    expect(out).not.toContain("trace_link");
  });

  test("a stale requirement gets the same validation guidance", () => {
    expect(formatProposal(proposal("sr_stale"))).toContain("running validation");
  });

  test("a dangling upstream is told the target does not exist", () => {
    const out = formatProposal(proposal("dangling_upstream"));
    expect(out).toContain("does not exist");
    expect(out).not.toContain("trace_exempt");
  });

  test("a missing source_plan keeps its link and exempt route", () => {
    const out = formatProposal(proposal("task_plan_missing"));
    expect(out).toContain("--source-plan");
    expect(out).toContain("trace_exempt");
  });
});
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd pi-ext/factory-watch && npm test`
Expected: FAIL — the single candidate-less message is rendered for every kind.

- [ ] **Step 3: Implement**

```typescript
// pi-ext/factory-watch/src/trace-tool-format.ts -- changed regions only
const NO_CANDIDATE_GUIDANCE: Record<string, string> = {
  sr_unvalidated:
    "This gap closes by running validation, not by linking. Neither trace_link nor a " +
    "waiver applies — a requirement can never be exempted. Defer it only if validation " +
    "genuinely cannot be run yet, and record what has to happen first.",
  sr_stale:
    "The recorded result predates a change to the statement or binding. It closes by " +
    "running validation again, not by linking. Defer it only if that cannot happen yet.",
  dangling_upstream:
    "The upstream target does not exist. Fix the reference or create the missing " +
    "requirement; deferring records the dangle, it does not resolve it.",
  task_plan_missing:
    "source_plan points at a file that is not there. Correct it with trace_link " +
    "--source-plan, or use trace_exempt if this task legitimately has no plan.",
};

const DEFAULT_NO_CANDIDATE_GUIDANCE =
  "Candidates: no candidates exist for this gap kind. Defer it, or exempt it if it is a " +
  "task or plan that legitimately has nothing to link to.";

function formatPending(proposal: TraceProposal): string[] {
  return [
    "",
    `All ${proposal.pending.length} pending gap(s) — the focused one above is a default, ` +
      "not a queue. Pass node_id to trace_next to work any of these instead:",
    ...proposal.pending.map((p) => `  ${p.node_id.padEnd(24)} ${p.kind.padEnd(18)} ${p.detail}`),
  ];
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
    lines.push(NO_CANDIDATE_GUIDANCE[proposal.gap.kind] ?? DEFAULT_NO_CANDIDATE_GUIDANCE);
    lines.push(...formatPending(proposal));
    return lines.join("\n");
  }

  lines.push(
    `Candidates (${proposal.candidates.length}, ordered by shared-term overlap — that ordering ` +
      "is a lexical hint, NOT a judgement. Read the statements and decide on meaning; the right " +
      "answer is often not first, and may share no vocabulary at all):",
  );
  lines.push("");
  for (const candidate of proposal.candidates) {
    const terms = candidate.shared_terms.length > 0 ? candidate.shared_terms.join(", ") : "none";
    lines.push(`- ${candidate.id}  ${candidate.title}`);
    lines.push(`    ${candidate.summary}`);
    lines.push(`    (shared terms: ${terms})`);
  }
  lines.push(...formatPending(proposal));
  return lines.join("\n");
}
```

The `sr_proposed` and `sr_unvalidatable` kinds from the doctor plan fall through to `DEFAULT_NO_CANDIDATE_GUIDANCE`. `sr_proposed` never reaches here (it is dispositioned `deferred`, and `next_gap` only returns pending gaps); add an `sr_unvalidatable` entry when that plan lands.

- [ ] **Step 4: Run to verify they pass**

Run: `cd pi-ext/factory-watch && npm test && npm run typecheck`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pi-ext/factory-watch/src/trace-tool-format.ts pi-ext/factory-watch/test/trace-tool-format.test.ts
git commit -m "feat(trace-tools): render the pending list and per-kind guidance for candidate-less gaps"
```

---

### Task 5: Correct the two prompt surfaces

`skill-prompt.ts:23` tells the agent "The tools own enumeration". After Task 1 that is no longer true, and it is the claim that made the loop feel like a queue.

**Files:**
- Modify: `pi-ext/factory-watch/src/skill-prompt.ts`
- Modify: `.pi/skills/trace-fix/SKILL.md`
- Test: `pi-ext/factory-watch/test/skill-prompt.test.ts`

**Interfaces:**
- Consumes: the `node_id` parameter from Task 3.

- [ ] **Step 1: Write the failing tests**

```typescript
// pi-ext/factory-watch/test/skill-prompt.test.ts -- append
test("the prompt no longer claims the tools own enumeration", () => {
  expect(prompt).not.toContain("own enumeration");
});

test("the prompt tells the agent it may choose a gap", () => {
  expect(prompt).toContain("node_id");
});

test("the prompt still forbids batching and still points at the gate", () => {
  expect(prompt).toContain("trace_check");
  expect(prompt.toLowerCase()).toContain("one gap, one proposal, one confirmation");
});
```

```python
# tests/unit/trace/test_skill_contract.py
from pathlib import Path

_SKILL = Path(__file__).resolve().parents[3] / ".pi" / "skills" / "trace-fix" / "SKILL.md"


def test_the_skill_no_longer_claims_the_tools_own_enumeration():
    assert "do not own enumeration" not in _SKILL.read_text(encoding="utf-8").lower()


def test_the_skill_says_excerpts_may_be_clipped():
    text = _SKILL.read_text(encoding="utf-8").lower()
    assert "truncated" in text
    assert "read the file" in text


def test_the_skill_still_forbids_batching():
    assert "Do not batch" in _SKILL.read_text(encoding="utf-8")
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd pi-ext/factory-watch && npm test` and `uv run pytest tests/unit/trace/test_skill_contract.py -v`
Expected: FAIL on both — the old claims are still present.

- [ ] **Step 3: Update `skill-prompt.ts`**

Replace lines 23–24's first string with:

```typescript
    "Work through the gaps with the trace tools: `trace_next` for a gap, its candidates and the full list of pending gaps, `trace_link` / `trace_exempt` / `trace_defer` to record a decision, and `trace_check` for the gate. The default focus is a default, not a queue — pass `node_id` to trace_next to work any pending gap. The tools own validation and every write; you decide which gap to take and what it means.",
```

Leave the second string (the "lexical hint" paragraph) exactly as it is.

- [ ] **Step 4: Update `SKILL.md`**

In "What you own, and what you do not", replace the second paragraph:

```markdown
You do **not** own validation, writing, or deciding when the work is finished.
Those belong to the `trace_*` tools. That split is deliberate — a gate that
trusted your account of your own progress would be worthless.

You **do** own which gap to work. `trace_next` returns every pending gap; the
focused one is a default ordering, not a queue.
```

In "Steps", replace step 1:

```markdown
1. **Get a gap.** Call `trace_next`. It returns the gap, the node's excerpt, every
   pending gap, and **every** candidate with its full statement. Pass `node_id` to
   focus a specific gap — related gaps are often easier to judge together, even
   though you still confirm them one at a time.
```

In "Rules", add:

```markdown
- **Excerpts and summaries may be clipped.** When one ends with a `[truncated …]`
  marker, read the file it names before judging. A task's `dod` block is often the
  part that falls off the end.
```

- [ ] **Step 5: Run both suites**

Run: `cd pi-ext/factory-watch && npm test && npm run typecheck`
Run: `uv run pytest -m unit`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
uv run ruff check .
git add pi-ext/factory-watch/src/skill-prompt.ts pi-ext/factory-watch/test/skill-prompt.test.ts .pi/skills/trace-fix/SKILL.md tests/unit/trace/test_skill_contract.py
git commit -m "docs(trace-fix): the agent chooses the gap, and clipped excerpts say so"
```

---

## Verification

The plan is done when, from a clean tree:

- `uv run pytest -m unit`, `uv run ruff check .` and `uv run pyright` pass
- `npm test` and `npm run typecheck` pass in `pi-ext/factory-watch`
- `python -m factory.trace next` against a repo with several gaps prints the focused gap and the full pending list
- `python -m factory.trace next --node-id <some other pending gap>` focuses that gap and exits 0
- `python -m factory.trace next --node-id T-404` prints the reason and exits 1
- `python -m factory.trace check` behaves exactly as before — no gap kind, disposition or exit code changed
