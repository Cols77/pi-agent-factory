# Design: Route Already-Done Tasks to Review for Clean Closure

**Date:** 2026-07-24
**Status:** Draft for review
**Author:** Colin AUBE (with Claude)

---

## 1. Context & Problem

`factory-run` picks a `todo` task and drives it through the pipeline
`context-gather → dev → validation → review → (human-review) → session-review`.
A task's status becomes `done` only when the factory itself completes it
(`runner.run_next` calls `set_status(task, "done")` on `outcome == "completed"`).

This leaves a gap: a task implemented **outside** the factory — committed
directly, or done before the mark-done bookkeeping existed — stays `todo`
forever. When `factory-run` is then pointed at such a task, context-gather
cannot "prove coherence" for work that already exists and **rejects**, so the
run dies at stage 1 (~30s) having accomplished nothing.

Observed case: **T-029** (`Core Data Types & FakeFlightController`) is marked
`status: todo`, but its deliverables (`src/drone/interfaces.py`,
`src/drone/fake_flight_controller.py`, `tests/unit/drone/test_interfaces.py`)
already exist, are committed (`0d4634b`), and its tests pass (27/27). Running
it produced a context-gather `reject`.

**Goal:** when `factory-run` is given a task whose work already looks done, it
should recognize that and route to a clean closure (mark the task `done` after
verification) instead of rejecting — with the human kept in the loop to confirm.

## 2. Decisions (settled during brainstorming)

- **Interaction model:** *detect, then ask* — the human confirms; the factory
  does not autonomously mark done. The confirmation reuses the existing
  **human-review approval** (approve = mark done; reject = fall through and do
  the work properly). No separate up-front prompt.
- **Detection:** an **LLM judgment made by context-gather** (not a new node), so
  it reuses the existing agent machinery and handles fuzzy DoD / `Modify:` cases
  that a pure file-existence check cannot.
- **Routing:** context-gather emits a new `ALREADY_DONE` outcome; `run_task`
  skips only the **dev** node on the first pass and still runs
  **validation (the sim gate)** before review, so the validation status of an
  already-done task is always surfaced. Review's deterministic
  `gates.run("full")` is the additional backstop: nothing is marked done unless
  both the sim gate and the review gates actually pass.
- **Minimal change:** no new pipeline node, agent role, scope entry, or
  decision-file handshake. Reuse review → human-review → `set_status(done)`.

This was chosen over a dedicated pre-check node + control-channel handshake
(more surface area, weaker guarantee) because routing through review gives a
**deterministic gate on a fuzzy signal** and reuses the completion path wholesale.

## 3. Detection — context-gather emits `already_done`

### 3.1 Prompt / behavior
The context-gatherer prompt gains a first responsibility: **before** attempting
to prove spec/plan/task coherence, check whether the task's declared
deliverables already exist and satisfy the DoD.

- It reads deliverable files via **pi's read tool, never bash**. (In the T-029
  run the agent tried a `cat` and hit `bash="deny"`, concluding "inaccessible."
  The prompt must direct it to the read tool so inspection is reliable under the
  role's `bash="deny"` scope. This is the "hole #3" reliability fix and is a
  prompt change only — no scope change.)
- If the deliverables exist and match the DoD, it sets `already_done: true` in
  its manifest JSON (with a short `already_done_reason` string for the status
  line / human-review banner).

### 3.2 Output contract
The context manifest gains an optional field:

```jsonc
{
  "already_done": true,                // optional, default false
  "already_done_reason": "deliverables src/drone/interfaces.py … exist and match the DoD",
  // … existing manifest fields (coherence, context, reject) …
}
```

The already-done branch in `run_context_gatherer` (§3.3) is checked **before**
`validate_manifest` and returns early, so a done task is **not** required to
pass manifest validation or prove coherence. `validate_manifest` itself is
extended only to *tolerate* an unknown `already_done` field (so it is never
rejected as a schema violation on the normal path); it does not gate the
already-done route.

### 3.3 `run_context_gatherer`
After parsing the manifest, before the existing reject/coherence logic:

```
if manifest.get("already_done"):
    status.report(node="context-gather", node_state="already-done",
                  handoff="→ review: task appears already complete",
                  session_id=result.session_id, summary=already_done_reason)
    return NodeOutcome.ALREADY_DONE, manifest, NodeEvent("context-gather", "already-done", attempt)
```

`session_id` continues to flow (now sticky in the status layer), so the
already-done context-gather row remains inspectable.

## 4. Routing — one branch in `run_task`

`NodeOutcome` gains `ALREADY_DONE`. `run_task` currently:

```
c_outcome, manifest, c_ev = run_context_gatherer(...)
if c_outcome == REJECT or manifest is None: return "rejected"
… for _ in range(max_review_cycles): run_dev → run_validation → run_review …
```

Change: carry an `already_done` flag into the loop and skip **only the dev
node** on the **first** pass; validation always runs:

```
already_done = (c_outcome == NodeOutcome.ALREADY_DONE)
if c_outcome == REJECT or manifest is None: return "rejected"

for i in range(max_review_cycles):
    if not (already_done and i == 0):
        run_dev(...)            # escalate handling unchanged
    run_validation(...)         # ALWAYS runs — surfaces the sim-gate status
    if v_outcome == FAIL:       # fail → feedback; next iteration runs dev
        feedback = "…"; continue
    run_review(...)  # existing review → human-review → completion path, unchanged
    # PASS  → (human-review approve) → set_status(done), return "completed"
    # CHANGES → feedback → next iteration runs dev normally (self-correct)
```

Consequences:
- **Validation always reported.** Even on the already-done first pass the sim
  gate runs, so the dashboard/status shows the task's real validation state.
- **PASS on the first pass** (sim gate green, review gates green, DoD met):
  interactive mode blocks on human-review (the "ask"); approve → completed →
  `set_status(done)`. `--auto` mode has no human gate, so it closes
  automatically once the gates pass — consistent with existing auto behavior.
- **Sim gate FAIL on the first pass** (task not actually done): validation
  returns FAIL → feedback → next iteration runs dev. Self-corrects before any
  review or completion.
- **Review CHANGES on the first pass** (sim passed but DoD/review gates not
  met): feedback → next iteration runs dev. `already_done` only suppresses the
  first dev pass, so a wrong "done" costs one cycle, never a bad close.

## 5. The "ask" + meaningful diff (hole #2)

An already-done task's work predates `start_commit`, so the normal human-review
diff (`start_commit..HEAD`) is **empty** — approving a blank diff is confusing
and overlaps the known "human-review reports 0 changes" bug.

For the already-done route:
- The human-review status row is flagged (e.g. `handoff`/a dedicated field the
  extension recognizes) so the review UI renders an **"already complete"
  banner**: *"This task appears already complete — approve to mark it done,
  reject to re-run it properly."*
- The diff shown is the **implementing diff**: the change(s) from the commit(s)
  that last added/modified the task's deliverable files, not `start_commit..HEAD`.
  Mechanically: for each deliverable path, resolve the last commit touching it
  (`git log -1 --format=%H -- <path>`) and show that commit's diff for the
  deliverables (union, de-duplicated). Exact plumbing is left to the plan; the
  requirement is *show the real implementing changes, never a blank range*.

If the implementing diff cannot be resolved (e.g. untracked files), fall back to
showing the current deliverable file contents with the same banner.

## 6. Edge cases

- **False positive** (looks done, isn't): the sim gate (validation) and/or
  review's `gates.run("full")` + DoD check fail → dev runs. Two deterministic
  backstops before any close.
- **Deliverables exist but sim gate fails:** validation FAIL → dev, before
  review is even reached. Correct.
- **Deliverables exist, sim passes, but review gates/DoD fail:** review CHANGES
  → dev. Correct.
- **`Modify:`-only tasks:** file existence proves nothing, so context-gather is
  unlikely to flag them; they take the normal path. Acceptable.
- **`--auto` mode:** no human gate; a verified already-done task is marked done
  automatically. Consistent with auto semantics.
- **Reject path unchanged:** a genuinely-incoherent, not-done task still rejects
  exactly as today.

## 7. Testing

Unit tests (`FakeAgentBackend` / `FakeGateRunner`, following existing
`tests/unit/orchestrator/` patterns):

1. `run_context_gatherer` returns `NodeOutcome.ALREADY_DONE` (carrying the
   manifest) when the manifest has `already_done: true`; unchanged otherwise.
2. `validate_manifest` accepts `already_done: true` without a proven-coherence
   manifest, and still validates the normal path.
3. `run_task` on `ALREADY_DONE` skips **dev** on the first pass but **still runs
   validation** (assert the sim gate is invoked), then calls `run_review`.
4. Review PASS on the already-done first pass (sim + review gates green) →
   `TaskResult "completed"` and (via `run_next`) `set_status(done)`.
5. Sim gate FAIL on the already-done first pass → dev runs on iteration 1
   (self-correct), review not reached, no premature completion.
6. Review CHANGES on the already-done first pass (sim passed) → dev runs on
   iteration 1 (self-correct), no premature completion.
7. The already-done human-review computes the implementing diff (last commit(s)
   touching the deliverables), not the empty `start_commit..HEAD` range, and
   carries the "already complete" flag/banner.
8. Status row for the already-done context-gather carries `session_id`
   (regression guard on the sticky-field fix).

## 8. Out of scope

- The broader `bash="deny"` / read-tool-reliability investigation for agents
  beyond the context-gather prompt instruction in §3.1.
- Auto-marking tasks done that were completed entirely outside the factory with
  no `factory-run` invocation (that is T-028's "post-session auto-export
  mark-done loop").
- Bulk auditing / fixing the status of the other currently-`todo`-but-possibly-
  done tasks (T-020, T-025–T-028): a one-off bookkeeping task, not this feature.

## 9. Files touched (anticipated)

- `src/factory/orchestrator/types.py` — `NodeOutcome.ALREADY_DONE`.
- `src/factory/orchestrator/nodes.py` — `run_context_gatherer` already-done branch.
- `src/factory/orchestrator/prompts.py` / `roles.py` — context-gatherer prompt
  gains the already-done check + read-tool instruction.
- `src/factory/validation/manifest_validator.py` — accept optional `already_done`.
- `src/factory/orchestrator/runner.py` — `run_task` routing flag.
- `pi-ext/factory-watch/src/review-diff.ts` (+ review UI) — implementing-diff
  computation and the already-complete banner for the already-done route.
- Tests under `tests/unit/orchestrator/` and `pi-ext/factory-watch/test/`.
