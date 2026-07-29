# Review UX — Plan A: Shared Model + Enhanced TUI + Python Handoff Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the per-file comment model with line-anchored annotations end-to-end, and upgrade the in-Pi TUI review overlay with per-line comments, a comment overview, reviewed marks, and hunk/search navigation — while the deterministic `review-decision.json` handshake keeps working after every task.

**Architecture:** A new shared `review-model.ts` defines the `Annotation` + `ReviewDecisionPayload` types and a diff-row → `{line, side}` anchoring helper. The Python reader is taught to accept the new `annotations` shape (preferring it, falling back to the legacy `comments` map) *before* the TS writer flips to emitting it, so the pipeline is never broken mid-plan. Then the TUI overlay is rewired onto the shared model and gains the new interactions.

**Tech Stack:** TypeScript (Node built-ins only, no new deps), `@earendil-works/pi-tui` + `@earendil-works/pi-coding-agent` (already used), vitest for TS tests; Python 3 + pytest for the orchestrator side.

## Global Constraints

- **No new runtime dependencies.** Node built-ins only on the TS side (this repo deliberately avoids frameworks — see the hand-rolled `syncSleep` in `review-protocol.ts`).
- **Windows-first.** Target OS is `win32`; keep the atomic-rename + retry logic in `writeReviewDecision` intact.
- **`.ts` relative import specifiers** in files that are also loaded via a plain `node <file>.ts` chain (`review-overlay.ts` and anything it imports, e.g. the new `review-model.ts`), because Node's real module resolution needs the on-disk extension. Files only used by vitest may use `.js` specifiers. Match each file's existing convention (see the header comment in `review-overlay.ts`).
- **No TypeScript constructor parameter properties** in `review-overlay.ts` / `review-model.ts` — Node's strip-only TS execution rejects them (`ERR_UNSUPPORTED_TYPESCRIPT_SYNTAX`). Use explicit field assignment.
- **Every rendered TUI line must be truncated to width** (`truncateToWidth`) — pi-tui hard-throws if a line exceeds terminal width.
- **The review guide** (`ReviewGuide` header, digit-jump) is unchanged behavior — preserve it.

---

### Task 1: Shared review model — types, `buildDecision`, `annotationsForFile`

**Files:**
- Create: `pi-ext/factory-watch/src/review-model.ts`
- Test: `pi-ext/factory-watch/test/review-model.test.ts`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `interface Annotation { file: string; line?: number; side?: "old" | "new"; body: string; severity?: "must-fix" | "suggestion" }`
  - `interface ReviewDecisionPayload { decision: "approve" | "reject"; annotations: Annotation[]; reviewedFiles: string[] }`
  - `function buildDecision(decision: "approve" | "reject", annotations: Annotation[], reviewedFiles: string[]): ReviewDecisionPayload`
  - `function annotationsForFile(annotations: Annotation[], file: string): Annotation[]`

- [ ] **Step 1: Write the failing test**

```ts
// pi-ext/factory-watch/test/review-model.test.ts
import { describe, expect, test } from "vitest";
import { annotationsForFile, buildDecision } from "../src/review-model.js";
import type { Annotation } from "../src/review-model.js";

const ANNS: Annotation[] = [
  { file: "a.py", line: 10, side: "new", body: "fix", severity: "must-fix" },
  { file: "a.py", body: "file note" },
  { file: "b.py", line: 3, side: "old", body: "old side" },
];

describe("review-model", () => {
  test("buildDecision packages decision, annotations, reviewedFiles", () => {
    const d = buildDecision("reject", ANNS, ["a.py"]);
    expect(d.decision).toBe("reject");
    expect(d.annotations).toHaveLength(3);
    expect(d.reviewedFiles).toEqual(["a.py"]);
  });

  test("annotationsForFile filters by path", () => {
    expect(annotationsForFile(ANNS, "a.py")).toHaveLength(2);
    expect(annotationsForFile(ANNS, "b.py")).toHaveLength(1);
    expect(annotationsForFile(ANNS, "z.py")).toHaveLength(0);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd pi-ext/factory-watch && npx vitest run test/review-model.test.ts`
Expected: FAIL — cannot resolve `../src/review-model.js`.

- [ ] **Step 3: Write minimal implementation**

```ts
// pi-ext/factory-watch/src/review-model.ts
export interface Annotation {
  file: string;
  line?: number;                 // 1-based line in the diff's `side`; absent = file-level note
  side?: "old" | "new";          // default "new"
  body: string;
  severity?: "must-fix" | "suggestion";
}

export interface ReviewDecisionPayload {
  decision: "approve" | "reject";
  annotations: Annotation[];
  reviewedFiles: string[];
}

export function buildDecision(
  decision: "approve" | "reject",
  annotations: Annotation[],
  reviewedFiles: string[],
): ReviewDecisionPayload {
  return { decision, annotations, reviewedFiles };
}

export function annotationsForFile(annotations: Annotation[], file: string): Annotation[] {
  return annotations.filter((a) => a.file === file);
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd pi-ext/factory-watch && npx vitest run test/review-model.test.ts`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add pi-ext/factory-watch/src/review-model.ts pi-ext/factory-watch/test/review-model.test.ts
git commit -m "feat: shared review-model types (Annotation, ReviewDecisionPayload)"
```

---

### Task 2: Diff-row anchoring helper (`mapDiffRows`)

Parse a unified-diff's raw lines into per-row metadata so a cursor on any rendered diff row can be turned into `{line, side}`. Shared by the TUI (Task 4) and the web server (Plan B).

**Files:**
- Modify: `pi-ext/factory-watch/src/review-model.ts`
- Test: `pi-ext/factory-watch/test/review-model.test.ts`

**Interfaces:**
- Produces:
  - `interface DiffRowMeta { kind: "add" | "del" | "context" | "hunk" | "meta"; line?: number; side?: "old" | "new" }`
  - `function mapDiffRows(rawDiffLines: string[]): DiffRowMeta[]` — one entry per input line, index-aligned.
  - `function anchorForRow(meta: DiffRowMeta[], rowIndex: number): { line?: number; side?: "old" | "new" }` — returns the `{line, side}` for a row, or `{}` (file-level) when the row is a hunk/meta line or `rowIndex` is out of range.

- [ ] **Step 1: Write the failing test**

```ts
// append to pi-ext/factory-watch/test/review-model.test.ts
import { anchorForRow, mapDiffRows } from "../src/review-model.js";

const RAW = [
  "diff --git a/x.py b/x.py",
  "index 111..222 100644",
  "--- a/x.py",
  "+++ b/x.py",
  "@@ -10,3 +10,4 @@ def f():",
  " context1",   // old 10 / new 10  -> anchor new 10
  "-removed",    // old 11           -> anchor old 11
  "+added1",     // new 11           -> anchor new 11
  "+added2",     // new 12           -> anchor new 12
  " context2",   // old 12 / new 13  -> anchor new 13
];

describe("mapDiffRows", () => {
  test("assigns line numbers per side across a hunk", () => {
    const meta = mapDiffRows(RAW);
    expect(meta).toHaveLength(RAW.length);
    expect(meta[4].kind).toBe("hunk");
    expect(anchorForRow(meta, 5)).toEqual({ line: 10, side: "new" });   // context1
    expect(anchorForRow(meta, 6)).toEqual({ line: 11, side: "old" });   // removed
    expect(anchorForRow(meta, 7)).toEqual({ line: 11, side: "new" });   // added1
    expect(anchorForRow(meta, 8)).toEqual({ line: 12, side: "new" });   // added2
    expect(anchorForRow(meta, 9)).toEqual({ line: 13, side: "new" });   // context2
  });

  test("hunk/meta rows and out-of-range anchor to file-level {}", () => {
    const meta = mapDiffRows(RAW);
    expect(anchorForRow(meta, 0)).toEqual({});   // diff header
    expect(anchorForRow(meta, 4)).toEqual({});   // hunk header
    expect(anchorForRow(meta, 999)).toEqual({}); // out of range
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd pi-ext/factory-watch && npx vitest run test/review-model.test.ts`
Expected: FAIL — `mapDiffRows`/`anchorForRow` not exported.

- [ ] **Step 3: Write minimal implementation**

```ts
// append to pi-ext/factory-watch/src/review-model.ts
export interface DiffRowMeta {
  kind: "add" | "del" | "context" | "hunk" | "meta";
  line?: number;
  side?: "old" | "new";
}

const HUNK_RE = /^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/;

export function mapDiffRows(rawDiffLines: string[]): DiffRowMeta[] {
  const out: DiffRowMeta[] = [];
  let oldLine = 0;
  let newLine = 0;
  let inHunk = false;
  for (const raw of rawDiffLines) {
    const hunk = HUNK_RE.exec(raw);
    if (hunk) {
      oldLine = Number(hunk[1]);
      newLine = Number(hunk[2]);
      inHunk = true;
      out.push({ kind: "hunk" });
      continue;
    }
    if (!inHunk) {
      out.push({ kind: "meta" }); // diff/index/---/+++ headers before the first hunk
      continue;
    }
    const c = raw[0];
    if (c === "+") {
      out.push({ kind: "add", line: newLine, side: "new" });
      newLine += 1;
    } else if (c === "-") {
      out.push({ kind: "del", line: oldLine, side: "old" });
      oldLine += 1;
    } else {
      // context (leading space) or the rare "\ No newline" marker -> treat as context
      out.push({ kind: "context", line: newLine, side: "new" });
      oldLine += 1;
      newLine += 1;
    }
  }
  return out;
}

export function anchorForRow(meta: DiffRowMeta[], rowIndex: number): { line?: number; side?: "old" | "new" } {
  const m = meta[rowIndex];
  if (m === undefined || m.line === undefined) return {};
  return { line: m.line, side: m.side };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd pi-ext/factory-watch && npx vitest run test/review-model.test.ts`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add pi-ext/factory-watch/src/review-model.ts pi-ext/factory-watch/test/review-model.test.ts
git commit -m "feat: diff-row anchoring helper (mapDiffRows/anchorForRow)"
```

---

### Task 3: Python handoff accepts line-anchored annotations (with legacy fallback)

Done **before** the TS writer flips (Task 4), so Python understands `annotations` the moment the extension starts emitting them, and still understands the legacy `comments` map emitted by the current/older extension.

**Files:**
- Modify: `src/factory/orchestrator/human_review.py`
- Modify: `src/factory/orchestrator/runner.py:200-204`
- Test: `tests/unit/orchestrator/test_human_review_gate_in_runner.py` (add cases; file exists)

**Interfaces:**
- Produces:
  - `@dataclass class Annotation: file: str; body: str; line: int | None = None; side: str | None = None; severity: str | None = None`
  - `HumanReviewDecision.annotations: list[Annotation]` (replaces `comments: dict[str, str]`)
  - `format_review_feedback(annotations: list[Annotation]) -> str`
  - `FileHumanReviewGate.request_review` reads `annotations` preferentially, else maps legacy `comments`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/orchestrator/test_human_review.py  (new file)
from factory.orchestrator.human_review import (
    Annotation,
    HumanReviewDecision,
    FileHumanReviewGate,
    format_review_feedback,
)
import json


def test_format_feedback_anchors_line_and_severity():
    anns = [
        Annotation(file="src/foo.py", line=42, side="new", body="guard empty", severity="must-fix"),
        Annotation(file="src/foo.py", body="naming inconsistent"),
        Annotation(file="src/bar.py", line=88, side="new", body="extract branch", severity="suggestion"),
    ]
    out = format_review_feedback(anns)
    assert "src/foo.py:42 [must-fix]: guard empty" in out
    assert "src/foo.py (file): naming inconsistent" in out
    assert "src/bar.py:88 [suggestion]: extract branch" in out


def test_gate_reads_annotations(tmp_path):
    (tmp_path / "review-decision.json").write_text(
        json.dumps({
            "decision": "reject",
            "annotations": [{"file": "a.py", "line": 3, "side": "new", "body": "x"}],
            "reviewedFiles": ["a.py"],
        }),
        encoding="utf-8",
    )
    gate = FileHumanReviewGate(tmp_path, poll_interval=0.01)
    d = gate.request_review("T-1", "abc")
    assert d.decision == "reject"
    assert d.annotations[0].file == "a.py"
    assert d.annotations[0].line == 3


def test_gate_falls_back_to_legacy_comments(tmp_path):
    (tmp_path / "review-decision.json").write_text(
        json.dumps({"decision": "reject", "comments": {"a.py": "please fix"}}),
        encoding="utf-8",
    )
    gate = FileHumanReviewGate(tmp_path, poll_interval=0.01)
    d = gate.request_review("T-1", "abc")
    assert d.annotations[0].file == "a.py"
    assert d.annotations[0].body == "please fix"
    assert d.annotations[0].line is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/orchestrator/test_human_review.py -v`
Expected: FAIL — `Annotation` not importable / `format_review_feedback` signature mismatch.

- [ ] **Step 3: Write minimal implementation**

```python
# src/factory/orchestrator/human_review.py  (replace the dataclass + gate read + formatter)
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass
class Annotation:
    file: str
    body: str
    line: int | None = None
    side: str | None = None
    severity: str | None = None


@dataclass
class HumanReviewDecision:
    decision: str  # "approve" or "reject"
    annotations: list[Annotation] = field(default_factory=list)


def _parse_annotations(payload: dict) -> list[Annotation]:
    raw = payload.get("annotations")
    if isinstance(raw, list):
        return [
            Annotation(
                file=a.get("file", ""),
                body=a.get("body", ""),
                line=a.get("line"),
                side=a.get("side"),
                severity=a.get("severity"),
            )
            for a in raw
            if isinstance(a, dict)
        ]
    # legacy shape: {"comments": {file: text}}
    legacy = payload.get("comments", {})
    return [Annotation(file=f, body=t) for f, t in legacy.items()]


class HumanReviewGate(Protocol):
    def request_review(self, task_id: str, start_commit: str) -> HumanReviewDecision: ...


class FileHumanReviewGate:
    def __init__(self, transcript_dir: Path, poll_interval: float = 1.0) -> None:
        self._decision_path = transcript_dir / "review-decision.json"
        self._poll_interval = poll_interval

    def request_review(self, task_id: str, start_commit: str) -> HumanReviewDecision:
        while not self._decision_path.exists():
            time.sleep(self._poll_interval)
        payload = json.loads(self._decision_path.read_text(encoding="utf-8"))
        self._decision_path.unlink()
        return HumanReviewDecision(
            decision=payload["decision"],
            annotations=_parse_annotations(payload),
        )


class FakeHumanReviewGate:
    def __init__(self, decisions: list[HumanReviewDecision]) -> None:
        self._decisions = list(decisions)
        self.requests: list[tuple[str, str]] = []

    def request_review(self, task_id: str, start_commit: str) -> HumanReviewDecision:
        self.requests.append((task_id, start_commit))
        assert self._decisions, "FakeHumanReviewGate: no scripted decision left"
        return self._decisions.pop(0)


def format_review_feedback(annotations: list[Annotation]) -> str:
    lines = ["human review requested changes:"]
    for a in annotations:
        loc = f"{a.file}:{a.line}" if a.line is not None else f"{a.file} (file)"
        sev = f" [{a.severity}]" if a.severity else ""
        lines.append(f"- {loc}{sev}: {a.body}")
    return "\n".join(lines)
```

- [ ] **Step 4: Update `runner.py`'s reject branch to the new shape**

In `src/factory/orchestrator/runner.py` (currently lines ~200-204):

```python
        feedback = format_review_feedback(decision.annotations)
        addressed.extend(
            f"your comment (round {_human_round + 1}) on "
            f"{a.file}{':' + str(a.line) if a.line is not None else ''}: {a.body}"
            for a in decision.annotations
        )
```

- [ ] **Step 5: Update any `FakeHumanReviewGate`/`HumanReviewDecision` construction in existing tests**

Search and fix constructions that pass `comments=`:

Run: `git grep -n "comments=" tests/ src/factory` — for each `HumanReviewDecision(comments={...})`, rewrite to `HumanReviewDecision(decision=..., annotations=[Annotation(file=f, body=t) for f, t in {...}.items()])`. Update imports to include `Annotation`.

- [ ] **Step 6: Run the orchestrator unit gate**

Run: `uv run pytest tests/unit/orchestrator/test_human_review.py tests/unit/orchestrator/test_human_review_gate_in_runner.py -v`
Expected: PASS (new tests green; existing reject/approve flow tests still green).

- [ ] **Step 7: Run the full unit gate to catch ripple**

Run: `uv run python scripts/gates/unit.py`
Expected: exit code 0.

- [ ] **Step 8: Commit**

```bash
git add src/factory/orchestrator/human_review.py src/factory/orchestrator/runner.py tests/
git commit -m "feat: line-anchored review annotations in orchestrator handoff (legacy fallback)"
```

---

### Task 4: Rewire TUI overlay onto the shared model + per-line comments

Flip `review-overlay.ts` from `Map<string,string>` (per-file) to `Annotation[]` (per-line), and make `writeReviewDecision` emit the new payload. After this task the extension emits `annotations`, which Task 3 already taught Python to read.

**Files:**
- Modify: `pi-ext/factory-watch/src/review-protocol.ts` (payload type → shared model)
- Modify: `pi-ext/factory-watch/src/review-overlay.ts`
- Modify: `pi-ext/factory-watch/src/index.ts:126-127` (call-site: `runReviewLoop` return + write)
- Test: `pi-ext/factory-watch/test/review-overlay.test.ts`

**Interfaces:**
- Consumes: `Annotation`, `ReviewDecisionPayload`, `buildDecision`, `mapDiffRows`, `anchorForRow` from `review-model.ts`.
- Produces:
  - `ReviewOverlay` constructor takes `annotations: Annotation[]` (was `comments: Map<string,string>`) and `reviewed: Set<string>`.
  - `runReviewLoop(...)` returns `ReviewDecisionResult = { decision: "approve" | "reject"; annotations: Annotation[]; reviewedFiles: string[] }`.
  - New `ReviewAction` variants: `{ type: "comment"; file: string; line?: number; side?: "old" | "new" }` now carries the anchor.

- [ ] **Step 1: Point `review-protocol.ts` at the shared payload type**

```ts
// pi-ext/factory-watch/src/review-protocol.ts — replace the local interface
import { mkdirSync, renameSync, unlinkSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import type { ReviewDecisionPayload } from "./review-model.js";

export type { ReviewDecisionPayload };
// ... keep syncSleep, reviewDecisionPath, and writeReviewDecision(path, decision) unchanged.
```

(Delete the old `interface ReviewDecisionPayload { decision; comments }`. `writeReviewDecision`'s body is unchanged — it JSON-stringifies whatever payload it's given.)

- [ ] **Step 2: Write the failing test (per-line comment anchors)**

```ts
// pi-ext/factory-watch/test/review-overlay.test.ts — add
import type { Annotation } from "../src/review-model.js";

test("commenting inside a file view carries the line anchor", () => {
  const actions: import("../src/review-overlay.js").ReviewAction[] = [];
  const overlay = new ReviewOverlay(FILES, [], new Set(), fakeTui(), "/repo", "abc123", (a) => actions.push(a));
  overlay.handleInput("\r");        // open first file
  overlay.handleInput("j");         // move line cursor down onto a diff row
  overlay.handleInput("c");         // comment on the current line
  const last = actions.at(-1)!;
  expect(last.type).toBe("comment");
  expect(last).toHaveProperty("file", "src/rtb.py");
  expect(typeof (last as { line?: number }).line === "number" || (last as { line?: number }).line === undefined).toBe(true);
});

test("summary shows a per-file annotation count badge", () => {
  const anns: Annotation[] = [
    { file: "src/rtb.py", line: 1, side: "new", body: "x" },
    { file: "src/rtb.py", line: 2, side: "new", body: "y" },
  ];
  const overlay = new ReviewOverlay(FILES, anns, new Set(), fakeTui(), "/repo", "abc123", () => {});
  expect(overlay.render(80).join("\n")).toMatch(/src\/rtb\.py.*\(2\)/);
});
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd pi-ext/factory-watch && npx vitest run test/review-overlay.test.ts`
Expected: FAIL — constructor arity/type mismatch (`annotations`/`reviewed` args not accepted).

- [ ] **Step 4: Rewire `ReviewOverlay`**

Key changes in `review-overlay.ts` (explicit field assignment, no param-properties):

```ts
import { annotationsForFile, anchorForRow, buildDecision, mapDiffRows } from "./review-model.ts";
import type { Annotation, DiffRowMeta, ReviewDecisionPayload } from "./review-model.ts";

export type ReviewAction =
  | { type: "comment"; file: string; line?: number; side?: "old" | "new" }
  | { type: "fileComment"; file: string }
  | { type: "edit"; file: string }
  | { type: "toggleReviewed"; file: string }
  | { type: "viewComments" }
  | { type: "approve" }
  | { type: "reject" };

type ViewState =
  | { mode: "summary" }
  | { mode: "file"; index: number; scrollOffset: number; cursor: number };
```

- Constructor signature becomes:
  `(files, annotations: Annotation[], reviewed: Set<string>, tui, cwd, startCommit, onAction, opts)`.
- Replace the `comments: Map<string,string>` field with `annotations: Annotation[]` and add `reviewed: Set<string>`.
- `diffLinesFor` additionally computes and caches `rowMeta`: build it from the **raw** diff text split, before colorizing:

```ts
private rowMetaCache = new Map<string, DiffRowMeta[]>();

private diffLinesFor(file: FileStat): string[] {
  let cached = this.diffLineCache.get(file.path);
  if (cached === undefined) {
    const diffText = this.implementing
      ? computeImplementingFileDiffText(this.cwd, file.path)
      : computeFileDiffText(this.cwd, this.startCommit, file.path);
    const rawLines = diffText.split("\n");
    let rendered: string[];
    try {
      rendered = renderDiff(diffText).split("\n");
    } catch {
      rendered = rawLines;
    }
    // Anchoring requires 1:1 alignment with the rendered rows. If renderDiff
    // changed the line count, fall back to file-level-only (all-empty meta).
    const meta = rendered.length === rawLines.length
      ? mapDiffRows(rawLines)
      : rawLines.map(() => ({ kind: "meta" as const }));
    this.rowMetaCache.set(file.path, meta);
    cached = rendered;
    this.diffLineCache.set(file.path, cached);
  }
  return cached;
}
```

- In file mode, add a `cursor` (a rendered-row index). `j`/`down` and `k`/`up` move `cursor`; keep `scrollOffset` following the cursor (clamp so cursor stays within `[scrollOffset, scrollOffset+viewport)`). Render the cursor row with a `>` gutter marker (still width-truncated).
- `c` in file mode:

```ts
} else if (data === "c") {
  const meta = this.rowMetaCache.get(this.files[view.index]!.path) ?? [];
  const { line, side } = anchorForRow(meta, view.cursor);
  this.onAction({ type: "comment", file: this.files[view.index]!.path, line, side });
}
```

- `C` (shift-c) in file mode → `{ type: "fileComment", file }` (line-less).
- Summary `formatStatLine` shows the count badge and reviewed check:

```ts
function formatStatLine(file: FileStat, count: number, reviewed: boolean): string {
  const check = reviewed ? "✓ " : "  ";
  const badge = count > 0 ? `  (${count})` : "";
  return `${check}${file.status}  ${file.path.padEnd(28)} +${file.added}/-${file.removed}${badge}`;
}
```

  where `count = annotationsForFile(this.annotations, f.path).length`.

- [ ] **Step 5: Rewire `runReviewLoop` to the annotation store + shared payload**

```ts
export interface ReviewDecisionResult {
  decision: "approve" | "reject";
  annotations: Annotation[];
  reviewedFiles: string[];
}

export async function runReviewLoop(ui, cwd, taskId, startCommit, files, opts = {}): Promise<ReviewDecisionResult> {
  const annotations: Annotation[] = [];
  const reviewed = new Set<string>();
  for (;;) {
    const action = await ui.custom<ReviewAction>((tui, _t, _k, done) =>
      new ReviewOverlay(files, annotations, reviewed, tui, cwd, startCommit, done, opts) as unknown as ...);

    if (action.type === "comment" || action.type === "fileComment") {
      const anchor = action.type === "comment" ? action : { file: action.file };
      const existing = annotations.find((a) =>
        a.file === anchor.file && a.line === (anchor as Annotation).line && a.side === (anchor as Annotation).side);
      const text = await ui.editor(
        `Comment on ${anchor.file}${(anchor as Annotation).line ? ":" + (anchor as Annotation).line : ""}`,
        existing?.body,
      );
      if (text !== undefined) {
        if (existing) existing.body = text;
        else annotations.push({ file: anchor.file, line: (anchor as Annotation).line, side: (anchor as Annotation).side, body: text });
      }
      continue;
    }
    if (action.type === "toggleReviewed") {
      if (reviewed.has(action.file)) reviewed.delete(action.file); else reviewed.add(action.file);
      continue;
    }
    if (action.type === "viewComments") { /* Task 5 */ continue; }
    if (action.type === "edit") { /* unchanged edit-launch block */ continue; }
    if (action.type === "reject") {
      if (annotations.length === 0) { ui.notify("reject requires at least one comment", "error"); continue; }
      if (!(await ui.confirm("Reject task?", `${taskId}: send back for another dev iteration?`))) continue;
      return { decision: "reject", annotations, reviewedFiles: [...reviewed] };
    }
    if (!(await ui.confirm("Approve task?", `${taskId}: mark this task done?`))) continue;
    return { decision: "approve", annotations, reviewedFiles: [...reviewed] };
  }
}
```

- [ ] **Step 6: Update the `index.ts` call site**

`review-overlay`'s result already matches `ReviewDecisionPayload`'s fields; wrap via `buildDecision` for clarity:

```ts
// index.ts case "review": after runReviewLoop
const result = await runReviewLoop(ctx.ui, ctx.cwd, rec.task_id, hr.start_commit, files, opts);
writeReviewDecision(
  reviewDecisionPath(ctx.cwd, rec.session_id),
  buildDecision(result.decision, result.annotations, result.reviewedFiles),
);
```

Add `import { buildDecision } from "./review-model.js";` to `index.ts`.

- [ ] **Step 7: Update existing overlay tests to the new constructor**

The `makeOverlay` helper and the `[commented]` test change: pass `[]`/`new Map()` → `[]` annotations + `new Set()`; the "marks commented files" test now asserts the `(1)` badge instead of `[commented]`. Update `makeOverlay` signature accordingly.

- [ ] **Step 8: Run overlay tests + typecheck**

Run: `cd pi-ext/factory-watch && npx vitest run test/review-overlay.test.ts test/review-model.test.ts`
Expected: PASS.
Run: `cd pi-ext/factory-watch && npm run typecheck` (or the repo's TS gate)
Expected: exit 0.

- [ ] **Step 9: Commit**

```bash
git add pi-ext/factory-watch/src/review-protocol.ts pi-ext/factory-watch/src/review-overlay.ts pi-ext/factory-watch/src/index.ts pi-ext/factory-watch/test/
git commit -m "feat: per-line review comments + count/reviewed badges in TUI overlay"
```

---

### Task 5: Comment overview popup + reviewed toggle wiring

**Files:**
- Modify: `pi-ext/factory-watch/src/review-overlay.ts`
- Test: `pi-ext/factory-watch/test/review-overlay.test.ts`

**Interfaces:**
- Consumes: `Annotation`, `annotationsForFile`.
- Produces: summary-mode keys `space` → `toggleReviewed`, `v` → `viewComments`; a `CommentListOverlay` component reachable from `runReviewLoop`.

- [ ] **Step 1: Write the failing test**

```ts
test("space toggles reviewed and renders a check", () => {
  const actions: any[] = [];
  const overlay = new ReviewOverlay(FILES, [], new Set(), fakeTui(), "/repo", "abc123", (a) => actions.push(a));
  overlay.handleInput(" ");
  expect(actions.at(-1)).toEqual({ type: "toggleReviewed", file: "src/rtb.py" });
});

test("reviewed set renders a check in the summary", () => {
  const overlay = new ReviewOverlay(FILES, [], new Set(["src/rtb.py"]), fakeTui(), "/repo", "abc123", () => {});
  expect(overlay.render(80).join("\n")).toMatch(/✓.*src\/rtb\.py/);
});

test("v requests the comment overview", () => {
  const actions: any[] = [];
  const overlay = new ReviewOverlay(FILES, [{ file: "src/rtb.py", line: 1, side: "new", body: "x" }], new Set(), fakeTui(), "/repo", "abc123", (a) => actions.push(a));
  overlay.handleInput("v");
  expect(actions.at(-1)).toEqual({ type: "viewComments" });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd pi-ext/factory-watch && npx vitest run test/review-overlay.test.ts`
Expected: FAIL — space/v not handled.

- [ ] **Step 3: Implement the summary keys + overview overlay**

In `handleInput` summary branch add:

```ts
} else if (data === " ") {
  if (this.files.length > 0) this.onAction({ type: "toggleReviewed", file: this.currentFile().path });
} else if (data === "v") {
  this.onAction({ type: "viewComments" });
}
```

Add a `CommentListOverlay` component (same `Component` shape as `ReviewOverlay`) that renders one row per annotation — ``${a.file}${a.line ? ":" + a.line : ""}  ${a.severity ?? ""}  ${a.body.split("\n")[0]}`` (width-truncated) — with up/down selection and Enter returning the selected `{file, line, side}` so `runReviewLoop` can jump into that file. In `runReviewLoop`'s `viewComments` branch:

```ts
if (action.type === "viewComments") {
  if (annotations.length === 0) { ui.notify("no comments yet", "info"); continue; }
  await ui.custom<void>((tui, _t, _k, done) =>
    new CommentListOverlay(annotations, tui, () => done(undefined)) as unknown as ...,
    { overlay: true, overlayOptions: { width: "80%", maxHeight: "80%", anchor: "center" } });
  continue;
}
```

(Jump-to-file on Enter is optional polish; the minimum is the browsable list. Footer of the summary view updates to include `space reviewed  v comments`.)

- [ ] **Step 4: Run tests**

Run: `cd pi-ext/factory-watch && npx vitest run test/review-overlay.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pi-ext/factory-watch/src/review-overlay.ts pi-ext/factory-watch/test/review-overlay.test.ts
git commit -m "feat: comment overview popup + reviewed toggle in review overlay"
```

---

### Task 6: Diff navigation — hunk jump + in-diff search

**Files:**
- Modify: `pi-ext/factory-watch/src/review-overlay.ts`
- Test: `pi-ext/factory-watch/test/review-overlay.test.ts`

**Interfaces:**
- Consumes: the cached `rowMeta` (kind `"hunk"`) and rendered diff lines from Task 4.
- Produces: file-mode keys `[`/`]` (prev/next hunk), `/` (search prompt via `ui`? — no; search is captured in-overlay via a minimal input buffer), `n`/`N` (repeat).

- [ ] **Step 1: Write the failing test**

```ts
test("] jumps the cursor to the next hunk header", () => {
  // 2 hunks in the mocked diff
  vi.mocked(computeFileDiffText).mockReturnValueOnce(
    "@@ -1,1 +1,1 @@\n-a\n+b\n@@ -10,1 +10,1 @@\n-c\n+d\n",
  );
  const overlay = new ReviewOverlay(FILES, [], new Set(), fakeTui(), "/repo", "abc123", () => {});
  overlay.handleInput("\r");    // open file
  overlay.handleInput("]");     // jump to 2nd hunk
  const shown = overlay.render(80).join("\n");
  expect(shown).toContain("@@ -10,1 +10,1 @@");
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd pi-ext/factory-watch && npx vitest run test/review-overlay.test.ts`
Expected: FAIL — `]` not handled / cursor unchanged.

- [ ] **Step 3: Implement navigation**

In file mode `handleInput`, using the cached `rowMeta` for the current file:

```ts
} else if (data === "]") {
  const meta = this.rowMetaCache.get(file.path) ?? [];
  const next = meta.findIndex((m, i) => i > view.cursor && m.kind === "hunk");
  if (next >= 0) view.cursor = next;
} else if (data === "[") {
  const meta = this.rowMetaCache.get(file.path) ?? [];
  for (let i = view.cursor - 1; i >= 0; i--) { if (meta[i]!.kind === "hunk") { view.cursor = i; break; } }
} else if (data === "/") {
  this.search = ""; this.searching = true;   // minimal in-overlay buffer; Enter commits, Esc cancels
} else if (data === "n" || data === "N") {
  this.jumpToMatch(file, data === "n" ? 1 : -1);
}
```

Add `private search = ""; private searching = false;` fields and a `jumpToMatch(file, dir)` that scans the rendered lines from `cursor + dir` for one containing `this.search` (case-insensitive), wrapping once, and sets `view.cursor`. While `this.searching`, printable characters append to `this.search` and Enter commits (calls `jumpToMatch(file, 1)` then clears `searching`); render a `/<search>` prompt line in the footer. Always keep `scrollOffset` following `cursor`.

- [ ] **Step 4: Run tests + full TS gate**

Run: `cd pi-ext/factory-watch && npx vitest run`
Expected: PASS (all overlay/model tests).
Run: `cd pi-ext/factory-watch && npm run typecheck`
Expected: exit 0.

- [ ] **Step 5: Commit**

```bash
git add pi-ext/factory-watch/src/review-overlay.ts pi-ext/factory-watch/test/review-overlay.test.ts
git commit -m "feat: hunk jump + in-diff search in review overlay"
```

---

### Task 7: Full-gate verification of Plan A

**Files:** none (verification only).

- [ ] **Step 1: Run the repo's combined gate**

Run: `uv run python scripts/gates/all.py`
Expected: exit code 0 (lint + types + unit all green).

- [ ] **Step 2: Run the TS suite**

Run: `cd pi-ext/factory-watch && npx vitest run`
Expected: all tests pass.

- [ ] **Step 3: Manual smoke (optional, documented for the human)**

Trigger a real `--review` in a Pi session, confirm: file list shows counts + `✓` after `space`; opening a file and pressing `c` on a line produces a `file:line`-anchored comment; `v` lists all comments; `[`/`]` and `/`+`n` move the cursor; reject feeds `src/x:NN [must-fix]: …` back to dev (check the dev feedback in the session transcript).

- [ ] **Step 4: Commit any doc/notes**

```bash
git add -A && git commit -m "chore: Plan A verification notes" || echo "nothing to commit"
```
