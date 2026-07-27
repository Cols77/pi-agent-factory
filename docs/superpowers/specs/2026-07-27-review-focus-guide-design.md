# Design: Reviewer Focus Guide in Human Review

**Date:** 2026-07-27
**Status:** Draft for review
**Author:** Colin AUBE (with Claude)

---

## 1. Problem

The human-review overlay (`runReviewLoop`/`ReviewOverlay`) shows only a raw
diff — changed files with `+/-` stats and each file's diff. It does NOT surface
the task's acceptance criteria, what the LLM reviewer checked or flagged, the
validation results, or where the human should focus. So a human approves/rejects
blind to the criteria and to what the pipeline already verified, and can't tell
where the risk is or what's already been addressed.

## 2. Goal (settled during brainstorming)

Help the human **focus attention where it matters**, driven by a
reviewer-produced guide plus pipeline facts:
- a **confidence** line and a **verify** checklist of concrete behaviors/edge
  cases (from the review agent — it's task-aware and already runs);
- the **validation results** (gate/test outcomes) so the human sees what's
  green;
- the **already-addressed** feedback (LLM findings and the human's prior reject
  comments that dev fixed this run) so the human doesn't re-flag fixed issues.

The checklist is **displayed, jump-to, non-gating** — informational, never
blocks approve/reject.

## 3. The guide artifact

The orchestrator assembles a single guide and persists it for the extension:

```jsonc
{
  // from the review agent (see §4)
  "confidence": "medium -- core logic sound, edge cases thinly tested",
  "verify": [
    {"item": "advance past the last waypoint", "file": "src/drone/mission/state.py", "line": 44, "why": "boundary not obviously handled"},
    {"item": "summary() reflects mark_objective()"},
    {"item": "nav_plan swapped mid-mission", "file": "src/drone/mission/state.py"}
  ],
  // added by the orchestrator from pipeline data (§5)
  "validation": [
    {"gate": "unit", "ok": true, "summary": "27 passed"},
    {"gate": "sim", "ok": true, "summary": "12 passed"},
    {"gate": "full", "ok": true, "summary": "passed"}
  ],
  "addressed": [
    "review (round 1): missing docstring on advance() -- fixed",
    "your comment (round 1): guard empty waypoint list -- fixed"
  ]
}
```

All fields are optional; a consumer renders whatever is present and degrades to
the plain diff when the guide is absent.

## 4. Review agent contributes `confidence` + `verify`

The `review` role's prompt (roles.py `ROLE_PROMPTS[REVIEW]`) gains a requirement:
alongside the existing `{dod_met, principles, findings}` JSON, ALWAYS emit
- `confidence`: a one-line "how sure I am and why";
- `verify`: 3–6 items, each `{item, file?, line?, why?}` — concrete behaviors or
  edge cases a human should check before approving (NOT file summaries), emitted
  even when `dod_met` is true (that's exactly when the human needs to know where
  the reviewer is least sure).

`run_review` (nodes.py) reads `confidence`/`verify` from `result.output` (best
effort — tolerate missing/malformed) and returns them so `run_task` can assemble
the guide. No schema file change (review output isn't schema-validated).

## 5. Orchestrator adds `validation` + `addressed`

Both are assembled in `run_task` at the point it blocks on human-review, from
data the pipeline already produced this run — no new agent calls, no new
plumbing through the node functions.

### 5.1 `validation` — test results from the gate logs

The factory runs three deterministic gates, each via
`SubprocessGateRunner(log_dir=transcript_dir)`, which writes the gate script's
full stdout to `<transcript_dir>/<name>-gate.log`:

| guide entry | gate | run by | script |
|---|---|---|---|
| `unit` | `unit` | dev node (`run_dev`) | `scripts/gates/unit.py` |
| `sim`  | `sim`  | validation node (`run_validation`) | `scripts/gates/sim_smoke.py` |
| `full` | `full` | review node (`run_review`) | `scripts/gates/all.py` |

Note "validation" in the user's request maps to the **sim** gate specifically
(the validation node), but the guide surfaces all three so the human sees the
whole picture.

A new helper `parse_gate_summary(log_text) -> {ok, summary} | None` reads a gate
log and extracts the pytest tally. It scans for the standard pytest summary
tokens with a regex over the log (last match wins, since the summary is the last
line): counts of `passed`, `failed`, `error`, `skipped`, `xfailed`. Then:
- `summary` = a compact reconstruction of the non-zero counts, e.g. `"27 passed"`
  or `"2 failed, 25 passed"` or `"1 error, 26 passed"`.
- `ok` = at least one `passed` and zero `failed`/`error`.
- If the log has **no** pytest tally (e.g. `all.py` shells out to lint/types and
  those failed before pytest ran, or a non-pytest gate): fall back to a
  best-effort signal from the log tail — `ok = false` if the tail contains an
  obvious failure marker (`FAILED`, `error:`, `Traceback`), else report
  `summary: "ran"` with `ok` omitted rather than guessing green.

The assembler reads whichever of the three logs **exist** under the transcript
dir (a gate whose node didn't run this round has no log → that entry is omitted)
and builds the `validation` array in unit→sim→full order. Because the log is the
authority for the *counts* and the fail-marker heuristic covers non-pytest
failures, the guide never needs the raw exit code threaded up from inside
`run_dev`/`run_validation`/`run_review`.

Rendering (§7) is compact: `unit 27✓   sim 12✓   full ✗ 2 failed`.

### 5.2 `addressed` — what was requested and then fixed this run

`run_task`'s loop is nested (human rounds × inner dev→validation→review cycles),
and two kinds of "please change X" already flow through it:
- an **inner-loop review CHANGES** verdict, whose `review_findings` become dev
  feedback for the next inner cycle;
- a **human reject**, whose `decision.comments` become dev feedback for the next
  human round.

Neither is recorded once consumed. This design adds a single `addressed:
list[str]` accumulator in `run_task`, appended to at exactly those two points
**before** the feedback is handed to the next dev run:
- on review CHANGES: extend with `f"review (round {i+1}): {finding}"` for each
  finding;
- on human reject: extend with `f"your comment (round {h+1}) on {file}: {text}"`
  for each `(file, text)` in `decision.comments`.

By the time execution reaches a *later* human-review block, `addressed` holds
every item that was raised and then re-run through dev — i.e. the churn that is
already handled, so the human can skip re-flagging it. On the very first
human-review of a clean run `addressed` is empty (nothing was rejected yet).
Round numbers are 1-based and included so the human can see the sequence. The
list is deduplicated (identical strings collapsed) to avoid repeats when the same
finding recurs across rounds. Scope is **this run only** — the orchestrator has
no clean cross-run history, and per-run churn is exactly what the human needs to
contextualize the diff in front of them.

## 6. Data flow (mirrors the decision-file handshake)

- New `reviewGuidePath(cwd, sessionId)` =
  `sessions/.factory-transcripts/<sessionId>/review-guide.json` on both sides
  (a Python writer + a TS reader), analogous to `review-decision.json`.
- When `run_task` reports the human-review row `blocked`, it writes the assembled
  guide to that path (best-effort; a write failure never blocks the run — same
  resilience as the status writer).
- The extension's review dispatch (`runMissionControl`'s `review` action /
  `launchInteractiveReview`) reads the guide, parses it, and passes it to
  `runReviewLoop` as an optional argument. Missing/unparseable → no guide.

## 7. UI

`runReviewLoop`/`ReviewOverlay` accept an optional `guide`. The summary view
renders a header above the file list (every line truncated to width, per the
existing crash fix):

```
Confidence: medium -- core logic sound, edge cases thinly tested
Validation: unit 27✓   sim 12✓   full ✓
Already addressed this run (2): docstring on advance(); guard empty waypoints

Verify before approving:
  [1] advance past the last waypoint            state.py:44
  [2] summary() reflects mark_objective()
  [3] nav_plan swapped mid-mission              state.py

—— 3 files changed ——
  M  state.py   +40/-2
  ...
```

- **Digit 1–9 jumps** to that verify item's `file` (and `line`, scrolled into the
  file view) by reusing the existing file-view mode. If the item has no `file`,
  or the file isn't among the changed files, the digit is a no-op.
- The guide is **non-gating**: `a`/`r`/`c`/`e`/arrows behave exactly as today; the
  guide only adds the header and the digit shortcuts.
- Failed validation gates render with a clear marker (e.g. `sim ✗ 2 failed`) —
  useful on the "reviewer couldn't confirm" path where the human is asked to
  decide despite an unhappy gate.

## 8. Edge cases

- **Absent guide** (older runs, review agent skipped the fields, write failed):
  the overlay shows the plain diff exactly as today.
- **`--auto` mode**: no human-review step, so no guide is shown. (The assembled
  guide could be logged for the record — out of scope here.)
- **Already-done route**: review still runs and emits `confidence`/`verify`; the
  guide shows with `addressed` empty and validation from that run.
- **"Reviewer couldn't confirm" route** (human-review-loop fix): the guide is
  most valuable here — low `confidence`, the outstanding items in `verify`, and a
  failing gate in `validation`.
- **Verify item references a file not in the diff**: shown, but its digit
  shortcut is a no-op.

## 9. Testing

- **Python**: `run_review` extracts `confidence`/`verify` (and tolerates their
  absence); the gate-log parser yields `N passed`/`N failed`/exit-code fallback;
  `run_task` accumulates `addressed` across CHANGES rounds and human rejects, and
  writes a well-formed `review-guide.json` on the human-review block; a write
  failure doesn't crash the run.
- **TS**: `reviewGuidePath` round-trips; the review dispatch reads + passes the
  guide (and tolerates a missing/garbage file); `ReviewOverlay` renders the
  confidence/validation/addressed/verify header, truncates to width, jumps to a
  referenced `file:line` on a digit and no-ops on an unmatched one, and renders
  the plain diff when no guide is given.

## 10. Files touched (anticipated)

- `src/factory/orchestrator/roles.py` — REVIEW prompt gains confidence/verify.
- `src/factory/orchestrator/nodes.py` — `run_review` returns confidence/verify.
- `src/factory/orchestrator/review_guide.py` (new) — assemble the guide, parse
  gate-log summaries, `review_guide_path`, atomic write.
- `src/factory/orchestrator/runner.py` — accumulate `addressed`, write the guide
  at the human-review block.
- `pi-ext/factory-watch/src/review-guide.ts` (new) — `reviewGuidePath`, read/parse.
- `pi-ext/factory-watch/src/review-overlay.ts` — render the guide header + digit
  jump; `runReviewLoop` gains the optional guide arg.
- `pi-ext/factory-watch/src/index.ts` — read the guide in the review dispatch.
- Tests under both test trees.
