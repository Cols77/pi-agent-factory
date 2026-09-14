# FEAT-017 Closure Bookkeeping Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring FEAT-017's task-status frontmatter, requirements register, and bundle scope back in sync with what is actually implemented and passing on `main`, correct one live SR-050 ownership violation, discard the four superseded parallel-candidate worktrees, and run the one genuinely outstanding gate (T-038's independent holistic review).

**Architecture:** No new production code. Every task here is a bookkeeping/reconciliation change (task frontmatter, the requirements register, `bundles/FEAT-017.json`, and disposal of dead worktrees) plus one dispatched independent review. Each task is independently verifiable and independently committable; none depend on new application logic.

**Tech Stack:** Python 3.11/3.12, `uv`, pytest, Ruff, Pyright, `coherence` CLI (`register`, `navigate`, `trace` groups), Git worktrees.

**Spec:** No separate spec document — this plan is derived directly from this session's audit of `main` against `docs/features/FEAT-017.md`, `tasks/T-032.md` through `T-038.md`, `requirements/SR-043/044/051-055/065.md`, and `requirements/index.json`. The audit trail is recorded in `.superpowers/sdd/2026-09-04_164749-feat17-long-term-stabilization/progress.md`.

## Global Constraints

- FEAT-017 owns exactly these eight requirements: `SR-043`, `SR-044`, `SR-051`, `SR-052`, `SR-053`, `SR-054`, `SR-055`, `SR-065`. Never add, remove, or reassign ownership of any other SR to/from FEAT-017 in this plan.
- Never modify `requirements/SR-050.md` from FEAT-017 work — `SR-050` belongs to FEAT-002.
- Do not fabricate requirement satisfaction, consent, adoption, or review verdicts. A task file's `status: done` must be backed by cited, checked evidence (file path + line, or a passing test node), never by assertion alone.
- No push, no merge to `main`, no force-push. Commit locally; stop for explicit authorization before any merge/push (per this session's standing instruction).
- Every focused test/lint/type command in a task must actually be run and its real output recorded before that task is marked complete — do not mark a step done from expected output alone.
- `git worktree remove` in Task 1 is destructive to uncommitted content in those worktrees. Task 1 requires the human's explicit go-ahead before removal, separate from authorization to run the rest of this plan.

---

### Task 1: Remove the four superseded FEAT-017 candidate worktrees

**Objective:** These four worktrees (`feat17-deterministic-runner-dev`, `feat17-doc-contract-fix`, `feat17-planning`, `feat17-worktree-enforcement`) all hold commits or dirty trees that were independently reviewed and rejected this session (see the ledger at `.superpowers/sdd/2026-09-04_164749-feat17-long-term-stabilization/progress.md`), or that are confirmed superseded by work already on `main`. Nothing in them is to be integrated.

**Files:** None (git worktree metadata only; no repository-tracked files change).

**Human gate:** Before running Step 1, show the human this exact list and get an explicit "yes, delete these" — this destroys uncommitted content in each worktree permanently:

```text
C:/coding/pi-agent-factory-wt/feat17-deterministic-runner-dev  (branch feat/coherence-feat17-deterministic-runner-dev, HEAD 212eff6, dirty)
C:/coding/pi-agent-factory-wt/feat17-doc-contract-fix           (branch feat/coherence-feat17-doc-contract-fix, HEAD 76f460d, dirty)
C:/coding/pi-agent-factory-wt/feat17-planning                   (branch feat/coherence-feat17-planning, HEAD 33c44fd, dirty)
C:/coding/pi-agent-factory-wt/feat17-worktree-enforcement        (branch feat/coherence-feat17-worktree-enforcement, HEAD 76f460d, dirty)
```

- [ ] **Step 1: Remove each worktree** (only after the human gate above is explicitly cleared)

Run each of these as its own single-line command (a multi-line loop has been observed to trip a project Bash hook into an unrelated false-positive block in this repo — run them one at a time):

```bash
git worktree remove --force "/c/coding/pi-agent-factory-wt/feat17-deterministic-runner-dev"
```
```bash
git worktree remove --force "/c/coding/pi-agent-factory-wt/feat17-doc-contract-fix"
```
```bash
git worktree remove --force "/c/coding/pi-agent-factory-wt/feat17-planning"
```
```bash
git worktree remove --force "/c/coding/pi-agent-factory-wt/feat17-worktree-enforcement"
```

Expected: each prints `ok` (or the worktree tool's equivalent success output) with no error.

- [ ] **Step 2: Delete the now-orphaned local branches**

```bash
git branch -D feat/coherence-feat17-deterministic-runner-dev
```
```bash
git branch -D feat/coherence-feat17-doc-contract-fix
```
```bash
git branch -D feat/coherence-feat17-planning
```
```bash
git branch -D feat/coherence-feat17-worktree-enforcement
```

Expected: each prints `Deleted branch <name> (was <sha>).`

- [ ] **Step 3: Verify removal**

```bash
git worktree list
```

Expected: none of the four paths above appear in the output.

**Commit:** None (no repository-tracked files changed; nothing to commit).

---

### Task 2: Fix T-037's ownership violation and point it at the SR it actually supports

**Objective:** `tasks/T-037-register-feat-17-trace-links-and-prove-the-feature-against-the-live-register.md` currently lists `Modify: requirements/SR-050.md` in its `Files` section and claims `satisfies: SR-050` — both violate the ownership boundary (`SR-050` belongs to FEAT-002; FEAT-017 must never modify or claim it). The task's actual described work — task-level `satisfies`/`source_plan` links, FEAT-017 membership, and a trace-contract test proving produced planning artifacts are named in the trace contract — is exactly `SR-054`'s statement ("require every FEAT-017 implementation task ... to include completion work for updating their canonical implementation/validation relations"). Repoint the task at `SR-054` and drop the `SR-050.md` edit target entirely.

**Files:**
- Modify: `tasks/T-037-register-feat-17-trace-links-and-prove-the-feature-against-the-live-register.md`
- Test: `tests/unit/coherence/test_planning_trace_contract.py` (run only — this task does not add a new test)

**Interfaces:**
- Consumes: nothing from another task in this plan.
- Produces: nothing another task in this plan consumes. (Task 5's status corrections are independent task files.)

- [ ] **Step 1: Read the current file**

```bash
cat "tasks/T-037-register-feat-17-trace-links-and-prove-the-feature-against-the-live-register.md"
```

Confirm it currently reads (frontmatter, abbreviated):

```yaml
satisfies:
- SR-050
```

and lists `- Modify: \`requirements/SR-050.md\`` under `Files`.

- [ ] **Step 2: Edit the frontmatter `satisfies` field**

Change:

```yaml
satisfies:
- SR-050
```

to:

```yaml
satisfies:
- SR-054
```

- [ ] **Step 3: Edit the `Files` list**

Change the file's body `Files` section from:

```text
- Modify: `requirements/SR-043.md`
- Modify: `requirements/SR-044.md`
- Modify: `requirements/SR-050.md`
- Modify: `requirements/SR-051.md`
- Modify: `requirements/SR-052.md`
- Modify: `requirements/SR-053.md`
- Modify: `requirements/SR-054.md`
- Modify: `bundles/FEAT-017.json`
- Modify: `docs/features/FEAT-017.md`
- Create: `tasks/T-<allocated>-feat17-planning-workflow.md`
- Test: `tests/unit/coherence/test_planning_trace_contract.py`
```

to:

```text
- Modify: `requirements/SR-043.md`
- Modify: `requirements/SR-044.md`
- Modify: `requirements/SR-051.md`
- Modify: `requirements/SR-052.md`
- Modify: `requirements/SR-053.md`
- Modify: `requirements/SR-054.md`
- Read-only dependency: `requirements/SR-050.md`
- Modify: `bundles/FEAT-017.json`
- Modify: `docs/features/FEAT-017.md`
- Test: `tests/unit/coherence/test_planning_trace_contract.py`
```

(The `Create: tasks/T-<allocated>-feat17-planning-workflow.md` line is dropped — `tasks/T-032-feat17-planning-workflow.md` already exists and is `status: done`; this line was a stale placeholder from before T-032 existed.)

- [ ] **Step 4: Verify no other task or doc still points FEAT-017 at `SR-050` as an owned/modifiable requirement**

```bash
grep -rn "SR-050" tasks/T-032-feat17-planning-workflow.md tasks/T-033-add-planning-run-evidence-review-seam-and-downstream-suggestion.md tasks/T-034-expose-the-deterministic-planning-gate-through-coherence-plan.md tasks/T-035-wire-the-existing-plan-authoring-host-to-the-backend-gate.md tasks/T-036-add-the-bootstrap-composition-and-available-deterministic-gates.md tasks/T-037-register-feat-17-trace-links-and-prove-the-feature-against-the-live-register.md tasks/T-038-holistic-integration-review-and-available-gate-deployment.md docs/features/FEAT-017.md bundles/FEAT-017.json
```

Expected: no output except the historical mention already present in `tasks/T-032-...md`'s body text ("Register the historical FEAT-017 SR-043/SR-044/SR-050–SR-054 projection; current FEAT-017 ownership is maintained separately") — that line documents history and does not claim `SR-050` as a modification target, so it is left as-is. If `T-037`'s frontmatter/`Files` section still shows `SR-050` after Step 2/3, redo those steps.

- [ ] **Step 5: Run the trace-contract test to confirm nothing regresses**

```bash
uv run pytest tests/unit/coherence/test_planning_trace_contract.py -q -o addopts=''
```

Expected: all tests pass (this test does not read task files' `Files` sections, only the registered bundle/trace graph, so this is a no-op regression check, not a new-behavior test — it must still pass unchanged).

- [ ] **Step 6: Commit**

```bash
git add tasks/T-037-register-feat-17-trace-links-and-prove-the-feature-against-the-live-register.md
git commit -m "fix(feat17): repoint T-037 at SR-054 and drop the SR-050 ownership violation"
```

---

### Task 3: Regenerate the requirements register index

**Objective:** `requirements/index.json` is stale: `SR-065` is entirely absent even though `requirements/SR-065.md` exists, because no one has re-run `coherence register index` since that file was added. Regenerate it.

**Files:**
- Modify: `requirements/index.json` (regenerated, not hand-edited)
- Read only: `requirements/SR-043.md`, `SR-044.md`, `SR-051.md`, `SR-052.md`, `SR-053.md`, `SR-054.md`, `SR-055.md`, `SR-065.md`

**Interfaces:** None — this task does not depend on Task 2's edits and Task 2 does not depend on this one; they may run in either order.

- [ ] **Step 1: Confirm the current gap**

```bash
python -c "import json; data = json.load(open('requirements/index.json', encoding='utf-8')); ids = {item['id'] for item in data['requirements']}; print('SR-065' in ids)"
```

Expected: `False`.

- [ ] **Step 2: Regenerate the index**

```bash
uv run coherence register index --requirements-dir requirements
```

Expected: exits 0 and rewrites `requirements/index.json`.

- [ ] **Step 3: Confirm `SR-065` is now present, and re-check the other seven owned SRs are still listed**

```bash
python -c "
import json
data = json.load(open('requirements/index.json', encoding='utf-8'))
ids = {item['id'] for item in data['requirements']}
owned = ['SR-043','SR-044','SR-051','SR-052','SR-053','SR-054','SR-055','SR-065']
missing = [sr for sr in owned if sr not in ids]
print('missing:', missing)
"
```

Expected: `missing: []`.

- [ ] **Step 4: Run the register and trace gates to confirm the regeneration didn't disturb anything else**

```bash
uv run coherence register check --project-root .
```
```bash
uv run pytest tests/unit/coherence/test_planning_trace_contract.py -q -o addopts=''
```

Expected: `register check` exits with its existing (pre-existing, unrelated) global pending count — do not expect this to turn fully green; FEAT-017's SRs remain at `proposed` until Task 5's review and the human's per-SR consent (out of scope for this plan). The trace-contract test passes with no new failures.

- [ ] **Step 5: Commit**

```bash
git add requirements/index.json
git commit -m "fix(requirements): regenerate register index to include SR-065"
```

---

### Task 4: Correct T-034/T-035/T-036 frontmatter status from `todo` to `done`

**Objective:** These three task files describe capability that already ships on `main`, verified this session:
- `T-034` (`coherence plan check`/`coherence plan suggest`): both subcommands exist in `src/coherence/planning/cli.py` (`sub.add_parser("check")` and `sub.add_parser("suggest")`) and are wired from `src/coherence/cli.py` (`"plan": planning_main`).
- `T-035` (pi-ext `/plan-gate` host adapter): `pi-ext/factory-watch/src/index.ts` imports `runPlanGate`/`runPlanHandoff` from `./plan-gate-command.js` and registers it (`pi.registerCommand("plan-gate", ...)`, line ~1009); `pi-ext/factory-watch/src/skill-prompt.ts` line 19 tells the authoring session to use `/plan-gate` exclusively, matching T-035's DoD text verbatim.
- `T-036` (`coherence plan bootstrap`): the `bootstrap` subcommand exists in `src/coherence/planning/cli.py` (`sub.add_parser("bootstrap")`), backed by `src/coherence/planning/bootstrap.py`.

Their `status: todo` frontmatter is stale and must be corrected so the task graph stops understating what is actually implemented — this is the same category of drift T-038's review (Task 5) needs an accurate starting picture for.

**Files:**
- Modify: `tasks/T-034-expose-the-deterministic-planning-gate-through-coherence-plan.md`
- Modify: `tasks/T-035-wire-the-existing-plan-authoring-host-to-the-backend-gate.md`
- Modify: `tasks/T-036-add-the-bootstrap-composition-and-available-deterministic-gates.md`

**Interfaces:** None — independent of Tasks 2 and 3.

- [ ] **Step 1: Confirm the cited evidence still holds before editing anything**

```bash
grep -n "add_parser(\"check\")\|add_parser(\"suggest\")\|add_parser(\"bootstrap\")" src/coherence/planning/cli.py
```

Expected: three matches, one per subcommand.

```bash
grep -n "registerCommand(\"plan-gate\"" pi-ext/factory-watch/src/index.ts
```

Expected: one match.

If either check fails to find the expected code, STOP this task — do not mark the file `done`; the evidence this task relies on no longer holds, and that must be reported rather than silently worked around.

- [ ] **Step 2: Edit `T-034`'s frontmatter**

In `tasks/T-034-expose-the-deterministic-planning-gate-through-coherence-plan.md`, change:

```yaml
status: todo
```

to:

```yaml
status: done
```

Immediately below the existing frontmatter's closing `---`, before the current body text, insert:

```markdown
## Closure note

Verified done on 2026-09-07: `coherence plan check` and `coherence plan suggest`
are both registered in `src/coherence/planning/cli.py` and wired from
`src/coherence/cli.py`'s `"plan"` group entry. No further implementation
required; remaining FEAT-017 work is per-SR human consent, tracked
separately from this task.
```

- [ ] **Step 3: Edit `T-035`'s frontmatter**

In `tasks/T-035-wire-the-existing-plan-authoring-host-to-the-backend-gate.md`, change `status: todo` to `status: done`, and insert below the frontmatter:

```markdown
## Closure note

Verified done on 2026-09-07: `pi-ext/factory-watch/src/index.ts` registers
`plan-gate` and `pi-ext/factory-watch/src/skill-prompt.ts` routes the
authoring session through it exclusively, matching this task's DoD text.
No further implementation required; remaining FEAT-017 work is per-SR
human consent, tracked separately from this task.
```

- [ ] **Step 4: Edit `T-036`'s frontmatter**

In `tasks/T-036-add-the-bootstrap-composition-and-available-deterministic-gates.md`, change `status: todo` to `status: done`, and insert below the frontmatter:

```markdown
## Closure note

Verified done on 2026-09-07: `coherence plan bootstrap` is registered in
`src/coherence/planning/cli.py`, backed by `src/coherence/planning/bootstrap.py`.
No further implementation required; remaining FEAT-017 work is per-SR
human consent, tracked separately from this task.
```

- [ ] **Step 5: Confirm no other file asserts these tasks are still open**

```bash
grep -rln "T-034\|T-035\|T-036" docs/features/FEAT-017.md bundles/FEAT-017.json
```

Expected: no output (neither file names individual task IDs today), so no further edit is needed there. If either file does list one of these IDs as pending, read the surrounding text and update it to match — do not leave a contradiction between a task's own `status: done` and another canonical document.

- [ ] **Step 6: Commit**

```bash
git add tasks/T-034-expose-the-deterministic-planning-gate-through-coherence-plan.md tasks/T-035-wire-the-existing-plan-authoring-host-to-the-backend-gate.md tasks/T-036-add-the-bootstrap-composition-and-available-deterministic-gates.md
git commit -m "docs(feat17): correct T-034/035/036 status to done with cited evidence"
```

---

### Task 5: Run T-038's independent holistic review

**Objective:** T-038 (`Holistic integration review and available-gate deployment`) is the one task in FEAT-017's canonical set that is genuinely still open — it requires an actual fresh, independent review, which has never been dispatched against the current state of `main`. Run it, record the verdict, and only then update `T-038`'s status.

**Files:**
- Read: everything under `src/coherence/planning/`, `tests/unit/coherence/test_planning_*.py`, `docs/features/FEAT-017.md`, `bundles/FEAT-017.json`, `requirements/SR-043.md` through `SR-055.md` and `SR-065.md`
- Create: `docs/superpowers/plans/2026-09-07-feat017-t038-review-report.md` (the review's findings, committed as a durable record)
- Modify: `tasks/T-038-holistic-integration-review-and-available-gate-deployment.md` (status only, after the review verdict is in hand)

**Interfaces:** Depends on Tasks 2, 3, and 4 being complete first — the reviewer must see the corrected task graph and regenerated index, not the stale versions, or its verdict will be reviewing bookkeeping this plan already knows is wrong.

- [ ] **Step 1: Run the full focused verification suite and capture its exact output**

```bash
uv run pytest tests/unit/coherence/test_planning_*.py -q -o addopts=''
```
```bash
uv run pytest tests/unit/substrate/test_verification_record_schema.py -q -o addopts=''
```
```bash
uv run ruff check src/coherence/planning tests/unit/coherence/test_planning_*.py
```
```bash
uv run pyright src/coherence/planning
```

Record the exact pass/fail/skip counts and exit codes from each command — the review report in Step 3 must cite these, not re-derive them.

- [ ] **Step 2: Dispatch one fresh, independent reviewer**

Dispatch a subagent with no prior context on this session, given:
- The eight owned SR statement texts (`requirements/SR-043.md`, `SR-044.md`, `SR-051.md` through `SR-055.md`, `SR-065.md`).
- `docs/features/FEAT-017.md` in full, including its "Mature workflow acceptance boundary" section.
- The exact verification output from Step 1.
- Instruction to read `src/coherence/planning/session.py`, `guided_entrypoint.py`, `guided_pipeline.py`, `adapter_backend.py`, `legal_actions_adapter.py`, `run.py`, `runner.py`, `workflow.py`, `bootstrap.py`, `handoff.py`, and their test files in full.

Require a structured, fail-closed verdict per the eight owned SRs (does the current implementation plausibly satisfy each SR's exact statement — not "is it a good idea", but "does this code do what this sentence requires"), plus the checks T-038's own DoD names: verified CLI help/output, and an explicit statement of what remains deferred to human browsing/visualization versus what is implemented. The reviewer must also flag any additional drift between task-file status and actual code, the way this session found `T-034`/`T-035`/`T-036` drifted — Tasks 2–4 fixed the three found this session, but the reviewer may find more.

End with, per SR: `SR-0NN: <SATISFIED | PARTIAL | NOT SATISFIED> — <evidence>`.

- [ ] **Step 3: Write the review report**

Create `docs/superpowers/plans/2026-09-07-feat017-t038-review-report.md` containing: the Step 1 command outputs verbatim, the reviewer's full structured verdict from Step 2, and one closing paragraph stating whether T-038's DoD ("verified CLI help/output, test/lint/type reports, and a reviewer-confirmed statement of deferred human browsing/visualization") is met.

- [ ] **Step 4: Update T-038's status based on the actual verdict — do not pre-decide this**

If the Step 2 reviewer's verdict is clean (no `NOT SATISFIED` findings, no unresolved drift): edit `tasks/T-038-holistic-integration-review-and-available-gate-deployment.md`, change `status: todo` to `status: done`, and add a `## Closure note` pointing at the new report file, dated 2026-09-07.

If the verdict finds any `NOT SATISFIED` or `PARTIAL` SR, or any further drift: leave `T-038`'s `status: todo`, and instead append a `## Findings pending resolution` section to `T-038`'s file listing each open item verbatim from the report, with a pointer to the report file. Do not mark `T-038` done over an open finding.

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/plans/2026-09-07-feat017-t038-review-report.md tasks/T-038-holistic-integration-review-and-available-gate-deployment.md
git commit -m "docs(feat17): run T-038 independent holistic review"
```

---

## Self-review notes

- **Spec coverage:** every bookkeeping gap identified in this session's audit (worktree cleanup, T-037's SR-050 leak, the stale register index, T-034/035/036 status drift, T-038's undispatched review) has a task. No SR consent/adoption task is included — that is explicitly out of scope, reserved for the human, per this plan's own audit conclusion.
- **Placeholder scan:** every step names an exact command, exact file, or exact frontmatter diff; Task 5's review is dispatched with a concrete brief rather than "review the code," and its completion criteria are decided by the verdict, not assumed in advance.
- **Type/name consistency:** N/A — no new code, functions, or types are introduced by this plan.
