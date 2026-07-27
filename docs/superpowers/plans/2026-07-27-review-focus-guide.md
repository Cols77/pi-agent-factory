# Reviewer Focus Guide Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show the human reviewer a focus guide atop the diff — reviewer confidence + a verify checklist, the run's gate/test results, and the feedback already fixed this run — with digit-jump to a referenced file, non-gating.

**Architecture:** The review agent emits `confidence` + `verify` (carried in the review `NodeEvent.extra`). The orchestrator assembles a `review-guide.json` (adding `validation` parsed from the gate logs and `addressed` accumulated across this run's rounds) when it blocks on human-review. The extension reads it and passes it to `runReviewLoop`; `ReviewOverlay` renders a header and digit-jumps to a verify item's file. Everything degrades to today's plain diff when the guide is absent.

**Tech Stack:** Python 3 (orchestrator, `uv`/`pytest`), TypeScript (pi extension, `node`/`vitest`).

## Global Constraints

- Python tests: `uv run python -m pytest <path> -v`; mark unit tests `pytestmark = pytest.mark.unit`. Lint `uv run ruff check <files>`.
- TS tests: from `pi-ext/factory-watch/`, `npx vitest run <path>`; typecheck `npx tsc --noEmit`. Do NOT run the full `npx vitest run` while iterating (a known flaky `mission-control-review.ts` "usage:" smoke test fails only under full-suite concurrency; run it once before committing and re-run to confirm if only that test fails).
- `.ts` relative-import specifiers for files also loaded via `node <file>.ts` (review-overlay, review-diff, review-protocol, session-*); `index.ts` uses `.js` specifiers. Match the file you edit.
- TDD: failing test first → watch fail → minimal implementation → watch pass → commit.
- The guide is best-effort everywhere: a missing/garbage guide, a write failure, or absent gate logs must never crash a run or the overlay — degrade to the plain diff.
- The guide is **non-gating**: approve/reject/comment/edit/arrows behave exactly as today; the guide only adds a header and digit shortcuts.

---

### Task 1: Review agent emits `confidence` + `verify`

**Files:**
- Modify: `src/factory/orchestrator/roles.py` (REVIEW prompt)
- Modify: `src/factory/orchestrator/nodes.py` (`run_review` carries them in the event)
- Test: `tests/unit/orchestrator/test_nodes_val_review.py`

**Interfaces:**
- Produces: on both review outcomes, the returned `NodeEvent.extra` includes `"confidence": str | None` and `"verify": list` copied from the review agent's JSON output (`result.output`).

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/orchestrator/test_nodes_val_review.py` (reuse its existing imports/fixtures for `run_review`, `FakeAgentBackend`, `FakeGateRunner`, a `Task`, `write_skill_stubs`):

```python
def test_run_review_carries_confidence_and_verify_in_event(tmp_path):
    write_skill_stubs(tmp_path)
    review_out = {
        "dod_met": True, "findings": [],
        "confidence": "medium -- edges thin",
        "verify": [{"item": "advance past last waypoint", "file": "src/x.py", "line": 44}],
    }
    b = FakeAgentBackend({AgentRole.REVIEW: [AgentResult(True, review_out)]})
    _outcome, ev, _findings = run_review(b, FakeGateRunner(), _task(), [], tmp_path)
    assert ev.extra["confidence"] == "medium -- edges thin"
    assert ev.extra["verify"] == [{"item": "advance past last waypoint", "file": "src/x.py", "line": 44}]
```

(If this test file lacks a `_task()` helper, add `def _task(): return Task("T-001", "t", "todo", ["c"], "body", Path("t"))` and the imports it needs, mirroring `test_nodes_context_dev.py`.)

- [ ] **Step 2: Run to verify it fails**

Run: `uv run python -m pytest tests/unit/orchestrator/test_nodes_val_review.py::test_run_review_carries_confidence_and_verify_in_event -v`
Expected: FAIL — `KeyError: 'confidence'`.

- [ ] **Step 3: Carry them in `run_review`'s events**

In `nodes.py` `run_review`, after `dod_met = bool(out.get("dod_met"))` (~line 255), extract:

```python
    confidence = out.get("confidence") if isinstance(out.get("confidence"), str) else None
    verify = out.get("verify") if isinstance(out.get("verify"), list) else []
```

Then add both to the `extra` dict on BOTH the PASS and CHANGES paths. The two `extra = _note_backend_failure({...}, result)` lines become, respectively:

```python
        extra = _note_backend_failure({"confidence": confidence, "verify": verify}, result)   # PASS path
...
        extra = _note_backend_failure({"findings": len(findings), "gate": gate, "confidence": confidence, "verify": verify}, result)  # CHANGES path
```

- [ ] **Step 4: Update the REVIEW prompt**

In `roles.py`, replace `ROLE_PROMPTS[AgentRole.REVIEW]` with:

```python
    AgentRole.REVIEW: (
        "Review the change for YAGNI/DRY and against the Definition of Done. Emit ONLY a "
        "fenced ```json block: {\"dod_met\": bool, \"principles\": [..], \"findings\": [..], "
        "\"confidence\": \"<one line: how sure you are and why>\", "
        "\"verify\": [{\"item\": \"<a concrete behavior/edge case a human should check "
        "before approving>\", \"file\": \"<path, optional>\", \"line\": <n, optional>, "
        "\"why\": \"<one line, optional>\"}]}. "
        "ALWAYS include confidence and 3-6 verify items -- even when dod_met is true; that is "
        "exactly when the human needs to know where you are least sure. verify items are "
        "concrete behaviors to check, NOT file summaries."
    ),
```

- [ ] **Step 5: Run the review-node tests**

Run: `uv run python -m pytest tests/unit/orchestrator/test_nodes_val_review.py -v`
Expected: PASS (new + existing).

- [ ] **Step 6: Commit**

```bash
git add src/factory/orchestrator/roles.py src/factory/orchestrator/nodes.py tests/unit/orchestrator/test_nodes_val_review.py
git commit -m "feat: review agent emits confidence + verify checklist, carried in the review event"
```

---

### Task 2: `review_guide` module — gate-log parsing, assembly, write path

**Files:**
- Create: `src/factory/orchestrator/review_guide.py`
- Test: `tests/unit/orchestrator/test_review_guide.py`

**Interfaces:**
- Produces:
  - `parse_gate_summary(log_text: str) -> dict | None` → `{"ok": bool, "summary": str}` or `None` when the log has no pytest tally AND no failure marker.
  - `review_guide_path(repo_root: Path, session_id: str) -> Path` → `<repo_root>/sessions/.factory-transcripts/<session_id>/review-guide.json`.
  - `read_validation(transcript_dir: Path) -> list[dict]` → one `{"gate","ok","summary"}` per existing `<gate>-gate.log`, in unit→sim→full order.
  - `write_review_guide(path: Path, guide: dict) -> None` → atomic, best-effort (never raises).

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/orchestrator/test_review_guide.py`:

```python
import json
import pytest
from factory.orchestrator.review_guide import (
    parse_gate_summary, review_guide_path, read_validation, write_review_guide,
)

pytestmark = pytest.mark.unit


def test_parse_gate_summary_all_passed():
    assert parse_gate_summary("....\n27 passed in 3.20s\n") == {"ok": True, "summary": "27 passed"}


def test_parse_gate_summary_with_failures():
    out = parse_gate_summary("F..\n2 failed, 25 passed in 3.2s\n")
    assert out["ok"] is False and "2 failed" in out["summary"] and "25 passed" in out["summary"]


def test_parse_gate_summary_non_pytest_failure_marker():
    assert parse_gate_summary("ruff....\nsrc/x.py:1:1: E501\nFAILED\n") == {"ok": False, "summary": "ran"}


def test_parse_gate_summary_none_when_no_signal():
    assert parse_gate_summary("some neutral output\n") is None


def test_review_guide_path(tmp_path):
    p = review_guide_path(tmp_path, "s1")
    assert p == tmp_path / "sessions" / ".factory-transcripts" / "s1" / "review-guide.json"


def test_read_validation_reads_existing_gate_logs(tmp_path):
    (tmp_path / "unit-gate.log").write_text("27 passed in 1s\n", encoding="utf-8")
    (tmp_path / "sim-gate.log").write_text("1 failed, 5 passed in 1s\n", encoding="utf-8")
    # no full-gate.log
    v = read_validation(tmp_path)
    assert v == [
        {"gate": "unit", "ok": True, "summary": "27 passed"},
        {"gate": "sim", "ok": False, "summary": "1 failed, 5 passed"},
    ]


def test_write_review_guide_atomic_and_best_effort(tmp_path):
    p = tmp_path / "d" / "review-guide.json"
    write_review_guide(p, {"confidence": "high", "verify": []})
    assert json.loads(p.read_text(encoding="utf-8"))["confidence"] == "high"
    # a bad path must NOT raise
    write_review_guide(tmp_path / "does" / "not" / "exist" / "x.json", {})  # dirs created; no raise
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run python -m pytest tests/unit/orchestrator/test_review_guide.py -v`
Expected: FAIL — `ModuleNotFoundError: factory.orchestrator.review_guide`.

- [ ] **Step 3: Implement the module**

Create `src/factory/orchestrator/review_guide.py`:

```python
from __future__ import annotations

import json
import re
from pathlib import Path

_COUNT = {
    kind: re.compile(rf"(\d+) {kind}")
    for kind in ("passed", "failed", "error", "errors", "skipped", "xfailed")
}
_FAIL_MARKER = re.compile(r"\bFAILED\b|\berror:|Traceback \(most recent call last\)")
_GATES = ("unit", "sim", "full")


def parse_gate_summary(log_text: str) -> dict | None:
    """Turn a gate log into {"ok", "summary"} using its pytest tally; fall back
    to a failure-marker scan for non-pytest gates. None when there's no signal."""
    counts = {}
    for kind, pat in _COUNT.items():
        m = list(pat.finditer(log_text))
        if m:
            counts[kind.rstrip("s") if kind == "errors" else kind] = int(m[-1].group(1))
    if any(k in counts for k in ("passed", "failed", "error")):
        parts = []
        for kind in ("failed", "error", "passed", "skipped", "xfailed"):
            if counts.get(kind):
                parts.append(f"{counts[kind]} {kind}")
        ok = counts.get("passed", 0) > 0 and not counts.get("failed") and not counts.get("error")
        return {"ok": ok, "summary": ", ".join(parts)}
    if _FAIL_MARKER.search(log_text):
        return {"ok": False, "summary": "ran"}
    return None


def review_guide_path(repo_root: Path, session_id: str) -> Path:
    return repo_root / "sessions" / ".factory-transcripts" / session_id / "review-guide.json"


def read_validation(transcript_dir: Path) -> list[dict]:
    out: list[dict] = []
    for gate in _GATES:
        log = transcript_dir / f"{gate}-gate.log"
        if not log.exists():
            continue
        try:
            parsed = parse_gate_summary(log.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            parsed = None
        if parsed is not None:
            out.append({"gate": gate, **parsed})
    return out


def write_review_guide(path: Path, guide: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(guide, indent=2), encoding="utf-8")
        tmp.replace(path)
    except OSError:
        pass  # best-effort: the guide is a nicety, never block the run
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run python -m pytest tests/unit/orchestrator/test_review_guide.py -v && uv run ruff check src/factory/orchestrator/review_guide.py`
Expected: PASS, ruff clean.

- [ ] **Step 5: Commit**

```bash
git add src/factory/orchestrator/review_guide.py tests/unit/orchestrator/test_review_guide.py
git commit -m "feat: review_guide module (gate-log parsing, path, atomic write)"
```

---

### Task 3: `run_task` accumulates `addressed` and writes the guide

**Files:**
- Modify: `src/factory/orchestrator/runner.py`
- Test: `tests/unit/orchestrator/test_human_review_gate_in_runner.py`

**Interfaces:**
- Consumes: `review_guide` module (Task 2); `NodeEvent.extra["confidence"|"verify"]` (Task 1).
- Produces: when `run_task` blocks on human-review it writes `review-guide.json` under the run's transcript dir with keys `confidence`, `verify`, `validation`, `addressed`.

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/orchestrator/test_human_review_gate_in_runner.py` (it has `_repo`, `FakeHumanReviewGate`, real git; the guide is written under `transcript_dir`). Pass a `transcript_dir` and assert the written guide:

```python
def test_human_review_writes_a_focus_guide(tmp_path):
    repo = _repo(tmp_path)
    td = repo / "sessions" / ".factory-transcripts" / "s1"
    td.mkdir(parents=True)
    (td / "sim-gate.log").write_text("12 passed in 1s\n", encoding="utf-8")
    # review agent returns a guide
    scripts = _already_done_scripts()  # context-gather already_done -> review -> human-review
    scripts[AgentRole.REVIEW] = [AgentResult(True, {
        "dod_met": True, "findings": [],
        "confidence": "medium", "verify": [{"item": "check X"}],
    })]
    human_review = FakeHumanReviewGate([HumanReviewDecision("approve", {})])
    run_next(
        repo, FakeAgentBackend(scripts), FakeGateRunner(),
        session_id="s1", git_info={"branch": "main"}, task_id="T-001",
        human_review=human_review, status=FakeStatusReporter(), transcript_dir=td,
    )
    import json
    guide = json.loads((td / "review-guide.json").read_text(encoding="utf-8"))
    assert guide["confidence"] == "medium"
    assert guide["verify"] == [{"item": "check X"}]
    assert {"gate": "sim", "ok": True, "summary": "12 passed"} in guide["validation"]
```

(`run_next` passes `transcript_dir` through to `run_task`; if the existing `_already_done_scripts` helper isn't visible here, define the scripts inline as in the other tests. `T-001`'s deliverable `src/x.py` exists in `_repo`, so it's the already-done route — hence `task_id="T-001"` and `_already_done_scripts`.)

- [ ] **Step 2: Run to verify it fails**

Run: `uv run python -m pytest tests/unit/orchestrator/test_human_review_gate_in_runner.py::test_human_review_writes_a_focus_guide -v`
Expected: FAIL — `review-guide.json` doesn't exist.

- [ ] **Step 3: Implement in `run_task`**

In `runner.py`, add the import:

```python
from factory.orchestrator.review_guide import read_validation, review_guide_path, write_review_guide
```

Initialize the accumulator next to `feedback`/`iterations` (before the outer loop):

```python
    addressed: list[str] = []
```

At the two feedback points in the loop, append before handing feedback to dev:
- inner-loop review CHANGES (where `feedback = "\n".join(review_findings) ...`):

```python
            addressed.extend(f"review (round {_cycle + 1}): {f}" for f in review_findings)
```

- human reject (where `feedback = format_review_feedback(decision.comments)`):

```python
        addressed.extend(
            f"your comment (round {_human_round + 1}) on {file}: {text}"
            for file, text in decision.comments.items()
        )
```

At the human-review `blocked` report (both `already_done` and normal handoff cases go through the same `status.report(node="human-review", node_state="blocked", ...)`), immediately BEFORE that `status.report(...)`, assemble and write the guide:

```python
        if transcript_dir is not None:
            guide = {
                "confidence": r_ev.extra.get("confidence") if r_ev is not None else None,
                "verify": r_ev.extra.get("verify", []) if r_ev is not None else [],
                "validation": read_validation(transcript_dir),
                "addressed": list(dict.fromkeys(addressed)),  # dedup, keep order
            }
            write_review_guide(review_guide_path(repo_root, session_review_id_or_run_id), guide)
```

Note on the session id: the guide path must use the SAME id the extension will
read with. The extension uses `record.session_id` (the top-level status
`session_id`, i.e. the factory run id). `run_task` doesn't receive that id
directly today, but `transcript_dir` already ends in it
(`.../.factory-transcripts/<run_id>`), so write to `transcript_dir /
"review-guide.json"` directly rather than recomputing the path — replace the
`write_review_guide(review_guide_path(...), guide)` line with:

```python
            write_review_guide(transcript_dir / "review-guide.json", guide)
```

- [ ] **Step 4: Run the test + full orchestrator suite**

Run: `uv run python -m pytest tests/unit/orchestrator/ -q`
Expected: PASS (no regressions; the new test passes).

- [ ] **Step 5: Commit**

```bash
git add src/factory/orchestrator/runner.py tests/unit/orchestrator/test_human_review_gate_in_runner.py
git commit -m "feat: run_task writes review-guide.json (confidence/verify/validation/addressed) at human-review"
```

---

### Task 4: TS `review-guide.ts` — path + tolerant reader

**Files:**
- Create: `pi-ext/factory-watch/src/review-guide.ts`
- Test: `pi-ext/factory-watch/test/review-guide.test.ts`

**Interfaces:**
- Produces:
  - `interface ReviewGuide { confidence?: string; verify?: VerifyItem[]; validation?: GateResult[]; addressed?: string[] }` with `VerifyItem = { item: string; file?: string; line?: number; why?: string }` and `GateResult = { gate: string; ok?: boolean; summary?: string }`.
  - `reviewGuidePath(cwd: string, sessionId: string): string`.
  - `readReviewGuide(path: string): ReviewGuide | null` — reads+parses; returns `null` on missing file or any parse error (never throws).

- [ ] **Step 1: Write the failing test**

Create `pi-ext/factory-watch/test/review-guide.test.ts`:

```typescript
import { mkdtempSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, expect, test } from "vitest";
import { reviewGuidePath, readReviewGuide } from "../src/review-guide.js";

let dir: string;
beforeEach(() => { dir = mkdtempSync(join(tmpdir(), "rg-")); });
afterEach(() => { rmSync(dir, { recursive: true, force: true }); });

test("reviewGuidePath builds the transcript path", () => {
  expect(reviewGuidePath("/repo", "s1")).toBe(join("/repo", "sessions", ".factory-transcripts", "s1", "review-guide.json"));
});

test("readReviewGuide parses a valid guide", () => {
  const p = join(dir, "g.json");
  writeFileSync(p, JSON.stringify({ confidence: "high", verify: [{ item: "x", file: "a.ts", line: 3 }] }), "utf-8");
  const g = readReviewGuide(p)!;
  expect(g.confidence).toBe("high");
  expect(g.verify![0]).toEqual({ item: "x", file: "a.ts", line: 3 });
});

test("readReviewGuide returns null on missing file or garbage", () => {
  expect(readReviewGuide(join(dir, "nope.json"))).toBeNull();
  writeFileSync(join(dir, "bad.json"), "not json", "utf-8");
  expect(readReviewGuide(join(dir, "bad.json"))).toBeNull();
});
```

- [ ] **Step 2: Run to verify it fails**

Run (from `pi-ext/factory-watch/`): `npx vitest run test/review-guide.test.ts`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement**

Create `pi-ext/factory-watch/src/review-guide.ts`:

```typescript
import { readFileSync } from "node:fs";
import { join } from "node:path";

export interface VerifyItem { item: string; file?: string; line?: number; why?: string }
export interface GateResult { gate: string; ok?: boolean; summary?: string }
export interface ReviewGuide {
  confidence?: string;
  verify?: VerifyItem[];
  validation?: GateResult[];
  addressed?: string[];
}

export function reviewGuidePath(cwd: string, sessionId: string): string {
  return join(cwd, "sessions", ".factory-transcripts", sessionId, "review-guide.json");
}

export function readReviewGuide(path: string): ReviewGuide | null {
  try {
    return JSON.parse(readFileSync(path, "utf-8")) as ReviewGuide;
  } catch {
    return null; // missing or unparseable -> no guide, plain diff
  }
}
```

- [ ] **Step 4: Run + typecheck**

Run: `npx vitest run test/review-guide.test.ts && npx tsc --noEmit`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pi-ext/factory-watch/src/review-guide.ts pi-ext/factory-watch/test/review-guide.test.ts
git commit -m "feat: review-guide.ts (path + tolerant reader)"
```

---

### Task 5: `ReviewOverlay` renders the guide + digit-jump

**Files:**
- Modify: `pi-ext/factory-watch/src/review-overlay.ts`
- Test: `pi-ext/factory-watch/test/review-overlay.test.ts`

**Interfaces:**
- Consumes: `ReviewGuide` (Task 4).
- Produces: `runReviewLoop(ui, cwd, taskId, startCommit, files, opts)` and `new ReviewOverlay(...)` accept `opts.guide?: ReviewGuide`. The summary view renders a confidence/validation/addressed/verify header above the file list; a digit `1`–`9` opens the diff of that verify item's `file` (no-op if it has no `file` or the file isn't among `files`). Non-gating.

- [ ] **Step 1: Write the failing tests**

Add to `test/review-overlay.test.ts` (import `ReviewGuide` type as needed):

```typescript
describe("ReviewOverlay focus guide", () => {
  const guide = {
    confidence: "medium -- edges thin",
    validation: [{ gate: "sim", ok: true, summary: "12 passed" }],
    addressed: ["review (round 1): docstring"],
    verify: [{ item: "advance past last waypoint", file: "src/rtb.py", line: 44 }],
  };

  test("renders the guide header in the summary", () => {
    const overlay = new ReviewOverlay(FILES, new Map(), fakeTui(), "/repo", "abc", () => {}, { guide });
    const out = overlay.render(120).join("\n");
    expect(out).toContain("medium -- edges thin");
    expect(out).toContain("12 passed");
    expect(out).toContain("advance past last waypoint");
    expect(out).toContain("[1]");
  });

  test("digit jumps to the referenced file's diff", () => {
    const overlay = new ReviewOverlay(FILES, new Map(), fakeTui(), "/repo", "abc", () => {}, { guide });
    overlay.handleInput("1"); // verify item 1 -> src/rtb.py (index 0 in FILES)
    // now in file view for src/rtb.py -> its diff (mocked computeFileDiffText) shows
    expect(overlay.render(80).join("\n")).toContain("@@");
  });

  test("digit for an item without a matching file is a no-op", () => {
    const g2 = { verify: [{ item: "no file here" }] };
    const overlay = new ReviewOverlay(FILES, new Map(), fakeTui(), "/repo", "abc", () => {}, { guide: g2 });
    expect(() => overlay.handleInput("1")).not.toThrow();
    expect(overlay.render(80).join("\n")).toContain("files changed"); // still on summary
  });
});
```

(`FILES` here must include a file whose path is `src/rtb.py` so item 1 matches — the file's existing `FILES` fixture already uses `src/rtb.py`. `computeFileDiffText` is mocked in this file to return a diff containing `@@`.)

- [ ] **Step 2: Run to verify it fails**

Run: `npx vitest run test/review-overlay.test.ts -t "focus guide"`
Expected: FAIL — `opts.guide` unused / header absent / digit does nothing.

- [ ] **Step 3: Implement**

In `review-overlay.ts`:

Add the import and a field:

```typescript
import type { ReviewGuide } from "./review-guide.ts";
```
```typescript
  private readonly guide: ReviewGuide | null;
```

Extend the `opts` type and assignment in BOTH the constructor and `runReviewLoop`:

```typescript
    opts: { implementing?: boolean; banner?: string; guide?: ReviewGuide } = {},
```
```typescript
    this.guide = opts.guide ?? null;
```

Add a private renderer for the header:

```typescript
  private guideLines(width: number): string[] {
    const g = this.guide;
    if (g === null) return [];
    const lines: string[] = [];
    if (g.confidence) lines.push(`Confidence: ${g.confidence}`);
    if (g.validation && g.validation.length > 0) {
      lines.push("Validation: " + g.validation.map((v) => `${v.gate} ${v.summary ?? ""}${v.ok === false ? " ✗" : v.ok ? " ✓" : ""}`.trim()).join("   "));
    }
    if (g.addressed && g.addressed.length > 0) {
      lines.push(`Already addressed this run (${g.addressed.length}): ${g.addressed.join("; ")}`);
    }
    if (g.verify && g.verify.length > 0) {
      lines.push("", "Verify before approving:");
      g.verify.slice(0, 9).forEach((v, i) => {
        const loc = v.file ? `  ${v.file}${v.line ? `:${v.line}` : ""}` : "";
        lines.push(`  [${i + 1}] ${v.item}${loc}`);
      });
    }
    if (lines.length > 0) lines.push("");
    return lines.map((l) => truncateToWidth(l, width));
  }
```

In `render`, in the `summary` branch, prepend the guide lines before the existing `Task: …` / banner content:

```typescript
    if (this.view.mode === "summary") {
      const lines: string[] = [...this.guideLines(width)];
      if (this.banner) { lines.push(this.banner, ""); }
      lines.push(`Task: ${this.files.length} files changed`, "");
      // ...existing file list + footer...
```

In `handleInput`, in the summary branch, handle digit keys (before the other summary keys):

```typescript
      if (/^[1-9]$/.test(data)) {
        const v = this.guide?.verify?.[Number(data) - 1];
        const idx = v?.file ? this.files.findIndex((f) => f.path === v.file) : -1;
        if (idx >= 0) { this.view = { mode: "file", index: idx, scrollOffset: 0 }; }
        return;
      }
```

- [ ] **Step 4: Run the overlay tests + typecheck**

Run: `npx vitest run test/review-overlay.test.ts && npx tsc --noEmit`
Expected: PASS (new + existing).

- [ ] **Step 5: Commit**

```bash
git add pi-ext/factory-watch/src/review-overlay.ts pi-ext/factory-watch/test/review-overlay.test.ts
git commit -m "feat: ReviewOverlay renders the focus guide with digit-jump to a file"
```

---

### Task 6: Extension reads the guide in the review dispatch

**Files:**
- Modify: `pi-ext/factory-watch/src/index.ts`
- Test: `pi-ext/factory-watch/test/handler.test.ts`

**Interfaces:**
- Consumes: `reviewGuidePath`/`readReviewGuide` (Task 4); `runReviewLoop` guide opt (Task 5).
- Produces: the interactive review dispatch reads `review-guide.json` for the current run and passes it to `runReviewLoop` via `opts.guide`.

- [ ] **Step 1: Write the failing test**

Add to `test/handler.test.ts`, modeled on the existing blocked-human-review test. Mock `readReviewGuide` (add to a `vi.mock("../src/review-guide.js", …)`), write a status file with a blocked human-review, and assert the guide flows into `runReviewLoop`:

```typescript
test("/factory-run passes the review guide into the review loop", async () => {
  // ...standard blocked-human-review status setup (see the existing detection test)...
  vi.mocked(readReviewGuide).mockReturnValue({ confidence: "high", verify: [{ item: "x" }] });
  // ...advance timers so the poll opens the review...
  expect(vi.mocked(runReviewLoop)).toHaveBeenCalledWith(
    ctx.ui, cwd, "T-001", "abc123", files,
    expect.objectContaining({ guide: { confidence: "high", verify: [{ item: "x" }] } }),
  );
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `npx vitest run test/handler.test.ts -t "review guide"`
Expected: FAIL — `runReviewLoop` called without a `guide` opt.

- [ ] **Step 3: Implement in the review dispatch**

In `index.ts`, add the import:

```typescript
import { readReviewGuide, reviewGuidePath } from "./review-guide.js";
```

In the review dispatch (the `case "review"` in `runMissionControl`, and any other place that calls `runReviewLoop` for a blocked human-review), read the guide and merge it into `opts`:

```typescript
          const guide = readReviewGuide(reviewGuidePath(ctx.cwd, rec.session_id)) ?? undefined;
          const files = alreadyDone
            ? computeImplementingFiles(ctx.cwd, hr.deliverables ?? [])
            : computeReviewFiles(ctx.cwd, hr.start_commit);
          const opts = alreadyDone
            ? { implementing: true, banner: "This task appears already complete -- approve to mark it done, reject to re-run it.", guide }
            : { guide };
          const decision = await runReviewLoop(ctx.ui, ctx.cwd, rec.task_id, hr.start_commit, files, opts);
          writeReviewDecision(reviewDecisionPath(ctx.cwd, rec.session_id), decision);
```

- [ ] **Step 4: Run handler tests + full suite + typecheck**

Run: `npx vitest run && npx tsc --noEmit`
Expected: PASS (ignore the known flaky `mission-control-review.ts` "usage:" test if it's the only failure under concurrency — re-run to confirm green).

- [ ] **Step 5: Commit**

```bash
git add pi-ext/factory-watch/src/index.ts pi-ext/factory-watch/test/handler.test.ts
git commit -m "feat: pass the review focus guide into the human-review overlay"
```

---

## Final verification

- [ ] **Python:** `uv run python -m pytest tests/unit/orchestrator/ -q` → all pass; `uv run ruff check src/factory/orchestrator/` clean.
- [ ] **TS:** from `pi-ext/factory-watch/`, `npx vitest run && npx tsc --noEmit` → all pass (bar the known flake).
- [ ] **Manual E2E (optional, live):** run a task that triggers human-review (or the `deepseek-v4-flash:low` e2e setup); confirm the overlay shows Confidence / Validation / Verify above the diff, a digit jumps to the referenced file, and a reject→re-run shows the prior finding under "Already addressed".
