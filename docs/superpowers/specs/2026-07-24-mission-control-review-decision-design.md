# Mission Control — Review Decision (Increment 2 / E2) — Design

**Status:** design, pending user review
**Date:** 2026-07-24
**Repo:** pi-agent-factory (`pi-ext/factory-watch` + `src/factory/orchestrator`)

## Goal

Let a human complete the human-review approve/reject decision **from the mission-control dashboard**, not only from the interactive pi terminal. This is Increment 2 of the mission-control work (Increment 1, observation-only, already shipped: `pi --session`, per-row summaries, log tailing, human-review diff *browsing* via `mission-control-review.ts`).

## Why this needs new architecture, not just wiring

Increment 1's `mission-control-review.ts` is a standalone process (`node <file>.ts`) with no relationship to the orchestrator's process tree — it can browse the diff, but it structurally cannot "answer" a review the way the interactive terminal does today. Today's mechanism (`StdioHumanReviewGate`) blocks the orchestrator's own `stdin.readline()`; the interactive terminal supplies that decision because `index.ts`'s `launchInteractiveReview` is the process that *spawned* the orchestrator and privately holds its `child.stdin`. Mission control was spawned independently via `spawnTerminalWindow` and has no access to that pipe. A file-based channel both processes can reach is required.

## Scope

**In scope:**
1. Replace the stdin-pipe review handshake with a **decision file** the orchestrator polls for. Both the interactive-terminal flow and mission control write to the same file — one mechanism, either UI can complete a review.
2. Give `mission-control-review.ts` a real decision loop (comment / edit / approve / reject), built from primitives that exist in a bare `node` process (no pi extension `ui.*` API available there).
3. Simplify `index.ts`'s `launchInteractiveReview`: detect "time to review" by polling `.factory-status.json` (the same signal `mission-control-dashboard.ts` already polls), not a stdout event; spawn the orchestrator with fully closed stdio, removing the long-lived open-pipe pattern.

**Explicitly out of scope / deferred (Increment "F"):** pause/steer control at other pipeline stages, taking over a still-running agent's session. `pi --session` (Increment 1) already gives partial single-agent takeover; F is a separate, later design.

**Explicitly untouched:** `HumanReviewDecision` dataclass, `HumanReviewGate` protocol shape (`request_review(task_id, start_commit) -> HumanReviewDecision`), `ReviewOverlay`'s rendering/input-handling core, `runReviewLoop`'s decision logic (still used verbatim by the interactive-terminal path), `computeReviewFiles`/the working-tree diff fix, `format_review_feedback`, and the dev-retry feedback loop that consumes a rejection's comments. The orchestration pipeline's gate sequence (context→dev→validation→review→human-review) is not restructured.

## Design

### 1. Decision file transport

New `FileHumanReviewGate` (replaces `StdioHumanReviewGate` as what `__main__.py` constructs for non-`--auto` runs) implements the same `HumanReviewGate` protocol:

```python
class FileHumanReviewGate:
    def __init__(self, transcript_dir: Path, poll_interval: float = 1.0) -> None: ...
    def request_review(self, task_id: str, start_commit: str) -> HumanReviewDecision:
        # polls <transcript_dir>/review-decision.json until it exists,
        # reads + parses it, deletes it (or renames to .consumed), returns
        # HumanReviewDecision(decision=..., comments=...).
```

`transcript_dir` is already computed in `__main__.py` (`repo_root / "sessions" / ".factory-transcripts" / session_id`) before the gate is constructed — no new path convention, reuses the existing session-scoped directory both transcripts and the validation gate log already live in.

The decision file is written **atomically** (tmp file + `os.replace`/equivalent rename), matching `FileStatusReporter`'s existing convention, by whichever UI completes the review. Payload shape is unchanged from today's stdin payload: `{"decision": "approve"|"reject", "comments": {file: text}}`.

`StdioHumanReviewGate` and its stdin-blocking mechanism are removed once `FileHumanReviewGate` is wired in (no need to keep two implementations of the same protocol live).

### 2. `index.ts`'s `launchInteractiveReview` — simplified

- Spawns the orchestrator with `stdio: ["ignore", "ignore", "ignore"]` (matching `launchAndWatch`'s pattern) instead of piped stdio. This removes the long-lived open-stdin-pipe pattern entirely — the same pattern whose side effect (every per-role `pi` subprocess inheriting that open pipe) caused the indefinite-hang bug fixed earlier this session. Removing it at the source is a net robustness win, not just a refactor.
- Detects "time to review" by polling `.factory-status.json` for the `human-review` pipeline entry reaching `node_state === "blocked"` (using the existing `parseStatus`) — the identical signal `mission-control-dashboard.ts` already polls for. One detection mechanism for both UIs, not two.
- On decision, `runReviewLoop` (unchanged) still drives the interactive-terminal UX; its result is now written via the new file-based `writeReviewDecision(path, decision)` instead of `writeReviewDecision(child.stdin, decision)`.
- `review-protocol.ts`'s `parseReviewPendingLine`/`ReviewPendingMessage` are removed (no longer needed — nothing reads a `review_pending` stdout event anymore). `writeReviewDecision`'s signature changes from `(stdin: WritableStream, decision)` to `(path: string, decision)`, writing atomically (temp file + rename).

### 3. `mission-control-review.ts` — real decision loop

`ReviewBrowser.onAction` (a no-op in Increment 1) becomes a real loop mirroring `runReviewLoop`'s decision logic, using primitives available in a bare `node` process:

- **comment** → reuse `resolveEditorLaunch` + `spawnSync` (the exact mechanism the pre-existing "edit" action already uses): write the current comment text to a temp file, spawn the resolved editor on it, read the result back on close.
- **edit** → identical to Increment 1 — already works standalone, unchanged.
- **approve / reject** → one new, small pi-tui component: a plain yes/no confirm prompt (mirrors `ui.confirm`'s two-question shape: "Reject/Approve task? `<task_id>`: ..."). Reject still enforces "at least one comment," matching today's rule.
- On confirmation, write the decision file atomically at the same path the orchestrator is polling, then report success (e.g. a final "decision sent" render) and let the process exit or the user close the window.

`mission-control-review.ts` needs the decision-file path. The dashboard already knows `record.session_id` (the top-level factory-run id) when it spawns `mission-control-review.ts`; pass it an additional flag (e.g. `--session-id <id>`) so it can compute `repo_root/sessions/.factory-transcripts/<id>/review-decision.json` itself — the identical computation `__main__.py` and the dashboard's own gate-log tailing already do.

## Race handling

First-write-wins: whichever UI's decision file appears first is what `FileHumanReviewGate` reads, and it deletes/consumes the file immediately after reading. A second, slightly-later write from the other UI becomes an orphaned file for a review that has already advanced — harmless, since the file is scoped to one task's one human-review gate and never reused. No locking protocol is introduced; this is a single-human-operator scenario and over-engineering a lock here is not warranted.

## Components touched

**Python:** `orchestrator/human_review.py` (new `FileHumanReviewGate`, remove `StdioHumanReviewGate`), `orchestrator/__main__.py` (construct `FileHumanReviewGate(transcript_dir)` instead of `StdioHumanReviewGate()`).

**TypeScript (`pi-ext/factory-watch/src`):** `review-protocol.ts` (`writeReviewDecision` becomes file-based; remove `parseReviewPendingLine`/`ReviewPendingMessage`), `index.ts` (`launchInteractiveReview`: closed stdio, status-file polling instead of stdout parsing, file-based decision write), `mission-control-review.ts` (real `onAction` decision loop: comment via editor spawn, approve/reject via a new confirm component, decision-file write; accept `--session-id`), a new small confirm-prompt component (file TBD at plan time — likely alongside `mission-control-review.ts` or as a tiny standalone component file).

## Testing

- Python: `FileHumanReviewGate` — polls until the file appears, parses correctly, deletes it after reading, and a fresh call after that doesn't re-read the stale (deleted) file. Existing `test_human_review_gate_in_runner.py` fixtures updated to use `FileHumanReviewGate` instead of `StdioHumanReviewGate` where they exercise the real gate (the `FakeHumanReviewGate` used by most tests is unaffected — it never touches the transport).
- TypeScript: `writeReviewDecision`'s new file-based behavior (atomic write, correct payload). `launchInteractiveReview`'s status-polling detection (mock `parseStatus`/the status file). `mission-control-review.ts`'s new decision loop: comment editor-spawn (reuse the existing edit-action test pattern), the new confirm component's render/input behavior, reject-requires-comment enforcement, and the decision-file write on confirmation — all under the same "runs correctly via real `node <file>.ts`" constraints already established (no constructor parameter properties, `.ts` relative imports, a smoke-test case).
- Manual verification: run a task to the human-review gate; confirm the decision can be completed from mission control alone (interactive terminal never touched) and, separately, from the interactive terminal alone (mission control never opened) — both must work.

## Open risks

- **Poll latency:** `FileHumanReviewGate`'s poll interval trades responsiveness for orchestrator idle-CPU cost; a 1s interval (matching the plan default) is a reasonable starting point, not something to over-tune before real usage data exists.
- **New confirm component's UX fidelity:** it will not be pixel-identical to `ui.confirm`'s pi-native dialog; visually simpler is acceptable as long as the yes/no semantics and the "reject needs a comment" rule match.
- **Removing `StdioHumanReviewGate` is a real behavior change** to an already-shipped, tested mechanism — the implementer must re-verify the full existing human-review test suite passes under the new gate, not just add new tests alongside it.
