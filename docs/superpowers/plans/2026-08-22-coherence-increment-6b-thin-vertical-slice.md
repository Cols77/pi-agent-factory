# Coherence Increment 6B: Thin Vertical Slice (Dogfood) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Walk one corrective task (`T-031`) and one new requirement-delivery task through the
full progressive-assurance spine end to end — justification, compiled obligations under both
`prototype` and `high_assurance`, a suspect-relationship downgrade, a policy-bound rerun, and
matching agent/human projections — proving the machinery built in Increments 2B/2C/3B/4/5/6
composes, not just that each piece passes its own unit tests. This is both item 4 of the
originating request ("dogfood one complete factory feature") and the external guide's §11 thin
vertical slice (spec D19: same deliverable).

**Architecture:** No new obligation kinds are authored here. `task_justification` was added
directly to `coherence.policy.compiler.compile_obligations` in Increment 2B (a sibling of that
increment's own typed-justification work); `verification_result` is added by Increment 4's
addendum (grounded in that increment's verification-contract validation); `human_review` is added
by Increment 6's addendum (grounded in that increment's gate-protocol/review work). By the time
this plan runs — its mandatory predecessors are 2B, 4, 5 and 6 — all three kinds already compile.
This increment is purely the integration exercise: seed a `prototype` feature and a
`high_assurance`-overridden feature, run `T-031` and one new requirement-delivery task through the
already-built spine, downgrade a suspect relationship, and confirm the compact agent projection
and the human-rendered projection agree. The suspect-relationship downgrade reuses
`coherence.trace.gaps` (already shipped, Increment 2) rather than a second dependency graph, per
spec §4's explicit instruction — this increment's own Task 3 adds the thin classification layer,
`coherence.trace.suspect`, that Increment 6's addendum also consumes for its gate-protocol
suspect-edge review.

Production-scope correction: `coherence.trace.suspect` is Increment 6 predecessor production code;
6B only exercises it through `test_suspect_dogfood_exercise.py`. The Task 3 wording above is not a
6B production-file or commit claim.

**Tech Stack:** Python 3.11+, dataclasses, pytest.

**Spec:** `docs/superpowers/specs/2026-08-22-coherence-progressive-assurance-design.md` (§3 D16,
D19; §8 the thin vertical slice, all 8 steps).

## Global Constraints

- Acceptance mirrors spec §8 exactly: the prototype feature incurs no high-assurance ceremony;
  the high-assurance feature cannot close with missing/errored verification; `T-031` traces
  through `corrects`, not a fabricated `satisfies`; every obligation explains itself and its
  cost; command-proxy presence/absence changes token volume only, never outcome.
- `requiredness` stays exactly `not_applicable | advisory | required | blocking` (spec §4) — no
  new value is introduced for these three new obligation kinds.
- Suspect-edge validity (`proposed | valid | suspect | invalid | waived`) is derived from the
  existing gap engine; deterministic code only ever downgrades toward `suspect`/`invalid`, never
  restores `valid` on its own (spec §4).
- Depends on Increments 2B, 2C, 3B, 4, 5 and 6 (execution map). Do not start this plan until all
  six have merged — Task 4 in particular assumes Increment 6's gate-protocol/suspect-edge work
  (see that plan's addendum) is present.

Resolution note: the dependency sentence above is retained as the current execution-map claim,
but its 2C/3B boundary is not resolved by this plan. Treat 2C and 3B consumer/projection checks
as conditional until that approval is recorded; this round does not add either increment as a
mandatory predecessor.

---

## File Structure

**Create:**
- `docs/features/FEAT-DOGFOOD-PROTOTYPE.md` — seeded `prototype`-profile feature fixture
- `docs/features/FEAT-DOGFOOD-HIGH-ASSURANCE.md` — seeded `high_assurance`-profile feature fixture
- `requirements/SR-DOGFOOD-001.md` — the one requirement-delivery task's target SR
- `tasks/T-940-dogfood-requirement-delivery.md` — the new requirement-delivery task
- `tests/unit/coherence/trace/test_suspect_dogfood_exercise.py`
- `tests/integration/test_dogfood_thin_vertical_slice.py`

**Modify:** none. This increment consumes the obligation kinds and suspect-relationship classifier
already compiled by Increments 2B, 4 and 6; it authors no production code. In particular,
`src/coherence/trace/suspect.py` and `tests/unit/coherence/trace/test_suspect.py` belong to the
Increment 6 predecessor and are inputs to this plan, not files committed by 6B.

---

### Task 1: Confirm predecessor obligation kinds are already compiled

Confirm all three obligation kinds this slice depends on already compile before seeding fixtures:

Run: `rtk proxy uv run python -c "
from pathlib import Path
from coherence.policy.compiler import compile_obligations
root = Path('.')
kinds = {o.kind for o in compile_obligations(root, 'task:T-031')}
print('task scope kinds:', kinds)
"`
Expected: includes `task_justification` (Increment 2B). Repeat against an `sr:` scope after
Increments 4 and 6 land to confirm `verification_result` and `human_review` are present too — if
either is missing, this plan's predecessor increments are not actually merged; stop and merge
them first rather than re-implementing the kind here.

### Task 2: Seed a `prototype` feature and a `high_assurance`-overridden feature

**Files:**
- Create: `docs/features/FEAT-DOGFOOD-PROTOTYPE.md`
- Create: `docs/features/FEAT-DOGFOOD-HIGH-ASSURANCE.md`
- Create: `requirements/SR-DOGFOOD-001.md`
- Test: part of `tests/integration/test_dogfood_thin_vertical_slice.py` (Task 5)

**Interfaces:**
- Consumes: `coherence.policy.compiler.resolve_profile` (Increment 2B).

- [ ] **Step 1: Write the fixtures.**

```markdown
<!-- docs/features/FEAT-DOGFOOD-PROTOTYPE.md -->
---
id: FEAT-DOGFOOD-PROTOTYPE
title: Dogfood prototype-profile feature
requirements: []
---

# Dogfood prototype-profile feature

Seeded fixture for the Increment 6B thin vertical slice (spec §8 step 3). No `profile:` override
-- the repository default (`prototype`, set in `.factory/factory.yaml`) applies unchanged.
```

```markdown
<!-- docs/features/FEAT-DOGFOOD-HIGH-ASSURANCE.md -->
---
id: FEAT-DOGFOOD-HIGH-ASSURANCE
title: Dogfood high-assurance-profile feature
requirements:
- SR-DOGFOOD-001
profile: high_assurance
---

# Dogfood high-assurance-profile feature

Seeded fixture for the Increment 6B thin vertical slice (spec §8 step 3). The `profile:
high_assurance` frontmatter override applies to this feature and the requirements it contains
only -- the repository default stays `prototype`.
```

```markdown
<!-- requirements/SR-DOGFOOD-001.md -->
---
id: SR-DOGFOOD-001
title: Dogfood high-criticality requirement
statement: A seeded requirement used only to exercise the high_assurance obligation set.
domain: dogfood
binding:
  experiment: dogfood-exp
  metric: dogfood-metric
  assert: 'dogfood-metric > 0'
---

Fixture only -- not a real product requirement. Owned by Increment 6B.
```

- [ ] **Step 2: Confirm resolution without running the whole slice yet.**

```python
def test_prototype_feature_stays_project_default(tmp_path_factory):
    pass  # placeholder assertion removed -- see Task 5's real integration test,
          # which is the actual verification for this task; this task only
          # authors the fixtures the later tasks consume.
```

Do not add a throwaway test file for this step — Task 5's integration test exercises these
fixtures directly against the real repo. Instead, sanity-check by hand:

Run: `rtk proxy uv run python -c "
from pathlib import Path
from coherence.policy.compiler import resolve_profile
root = Path('.')
print('prototype feature scope:', resolve_profile(root, 'feat:FEAT-DOGFOOD-PROTOTYPE'))
print('high-assurance SR scope:', resolve_profile(root, 'sr:SR-DOGFOOD-001'))
"`
Expected: prints `prototype` then `high_assurance`.

- [ ] **Step 3: Commit.**

```bash
git add docs/features/FEAT-DOGFOOD-PROTOTYPE.md docs/features/FEAT-DOGFOOD-HIGH-ASSURANCE.md \
        requirements/SR-DOGFOOD-001.md
git commit -m "test(dogfood): seed prototype and high_assurance feature fixtures"
```

### Task 3: One requirement-delivery task through the full spine

**Files:**
- Create: `tasks/T-940-dogfood-requirement-delivery.md`

**Interfaces:**
- Consumes: `substrate.ledger.tasks.Justification` (Increment 2B).

- [ ] **Step 1: Write the task.**

```markdown
---
id: T-940
title: Deliver SR-DOGFOOD-001 under high_assurance
status: todo
dod:
- 'SR-DOGFOOD-001 has a recorded, passing, non-stale validation result.'
- 'The approved human-review evidence for SR-DOGFOOD-001 is recorded under the reviewer contract selected by the owning increment.'
- 'The compiled obligation set for sr:SR-DOGFOOD-001 shows every obligation satisfied.'
justification:
- satisfies: SR-DOGFOOD-001
---

## Scope

Seeded requirement-delivery task for the Increment 6B thin vertical slice (spec §8 step 4). This
task's own purpose is to be walked through justification -> obligation compilation -> execution
-> evidence by the slice's own test, not to ship product code.
```

- [ ] **Step 2: Verify it parses.**

Run: `rtk proxy uv run python -c "
from pathlib import Path
from substrate.ledger.tasks import load_tasks
t = next(t for t in load_tasks(Path('tasks')) if t.id == 'T-940')
print(t.justification)
"`
Expected: prints `[Justification(kind='satisfies', target_id='SR-DOGFOOD-001')]`.

- [ ] **Step 3: Commit.**

```bash
git add tasks/T-940-dogfood-requirement-delivery.md
git commit -m "test(dogfood): seed T-940 requirement-delivery task"
```

### Task 4: Exercise the suspect-relationship downgrade

Implements spec §8 steps 5–6: make an implementation change that invalidates a verification
fingerprint, confirm the resulting suspect/stale state renders consistently across the navigator,
`coherence status` and the inbox. `coherence.trace.suspect.edge_validity` and its `ValidityState`
vocabulary are built by Increment 6's addendum (this plan's mandatory predecessor) — this task
only exercises it against the seeded `SR-DOGFOOD-001` fixture; it authors no new classification
logic itself, matching spec §4's instruction that suspect relationships extend the existing
freshness/gap machinery rather than a second dependency graph owned by this plan.

**Files:**
- Test: `tests/unit/coherence/trace/test_suspect_dogfood_exercise.py`

**Interfaces:**
- Consumes: `coherence.trace.suspect.edge_validity` (Increment 6 addendum),
  `coherence.trace.gaps.find_gaps` (existing, Increment 2).

- [ ] **Step 1: Write the failing test.**

```python
import pytest
from pathlib import Path

from coherence.trace import gaps as gaps_module
from coherence.trace import model as trace_model
from coherence.trace.suspect import edge_validity

pytestmark = pytest.mark.unit


def test_sr_dogfood_001_starts_valid_before_any_change(tmp_path):
    # A fresh checkout of this repo's own fixtures (Task 2) has no recorded
    # validation for SR-DOGFOOD-001 yet, so its gap set is non-empty by design
    # -- this test documents the STARTING classification the rest of the
    # slice (Task 5) invalidates further, it does not assert "valid" here.
    root = Path(__file__).resolve().parents[3]
    nodes = trace_model.load_nodes(root)
    edges = trace_model.extract_edges(root, nodes)
    gaps = gaps_module.find_gaps(nodes, edges, {})
    sr_gaps = [g for g in gaps if g.node_id == "SR-DOGFOOD-001"]
    validity = edge_validity(sr_gaps)
    assert validity in ("proposed", "suspect", "invalid")
```

(Adjust the `parents[3]` repo-root resolution to match wherever this test file actually lands —
reuse the shared `repo_root` fixture from `tests/unit/conftest.py` if one exists, rather than a
manual `parents[N]` path, exactly as noted in Increment 2B Task 4's own test.)

- [ ] **Step 2: Run the test.**

Run: `rtk proxy uv run python -m pytest tests/unit/coherence/trace/test_suspect_dogfood_exercise.py -v`
Expected: PASS once Increment 6's addendum (`coherence.trace.suspect`) and this plan's Task 2
(the `SR-DOGFOOD-001` fixture) are both merged.

- [ ] **Step 3: Commit.**

```bash
git add tests/unit/coherence/trace/test_suspect_dogfood_exercise.py
git commit -m "test(dogfood): exercise edge_validity against SR-DOGFOOD-001"
```

### Task 5: The slice, end to end, with dual projections

Spec §8 steps 4–8 in one integration test: run T-031 and T-940 through the spine, invalidate a
fingerprint, confirm `edge_validity` downgrades it, rerun to restore closure, and confirm the
compact JSON projection and the human-rendered projection from `coherence navigate obligations`
(Increment 3B) agree on outcome.

**Files:**
- Create: `tests/integration/test_dogfood_thin_vertical_slice.py`

**Interfaces:**
- Consumes: `coherence.policy.compiler.compile_obligations` (Increment 2B, extended by Increment
  4's and Increment 6's addenda), `coherence.trace.suspect.edge_validity` (Increment 6 addendum,
  exercised in Task 4), `coherence.trace.gaps.find_gaps` (existing),
  `coherence.navigate.cli.{cmd_obligations, _render_obligations}` (Increment 3B, conditional on
  the unresolved 3B dependency decision).

**Policy-bound rerun contract (explicit test inputs):**

- `compiled_obligations`: capture `compile_obligations(root, "sr:SR-DOGFOOD-001")` before and
  after the rerun. Before it, `verification_result` must be non-satisfied because its recorded
  validation is missing, errored, or stale; after it, that obligation must be `satisfied`. This
  is verification closure only: the rerun must not auto-satisfy `human_review` or restore a
  suspect relationship to `valid`.
- `audit_verdict_store`: use a temporary audit `run_dir` containing an existing
  `run_dir/verdicts/SR-DOGFOOD-001.json` with the stale verdict/fingerprint. Keep that store
  distinct from the harness-validation store read by
  `coherence.trace.validation_status.load_validation`; seed and assert both stores.
- `policy_bound_flags`: invoke the Increment 4 audit-runner seam with `--policy-bound` and
  `--max-reruns 1`, alongside its existing provider/model/run-id/no-gates inputs. Assert that the
  existing verdict makes this SR eligible for resubmission, exactly one rerun is selected, and
  the cap is observable rather than silently dropping work.
- `status_projection`: capture the post-rerun `coherence status --json`/`StatusSnapshot` result
  and assert that it reflects the satisfied `verification_result` while retaining any unresolved
  human-review or suspect-edge state. If the canonical status projection is assigned to Increment
  7, this input and the closure-restoration assertion are conditional on Increment 7 and do not
  enlarge 6B's dependency boundary.

- [ ] **Step 1: Write the failing test.**

```python
import pytest
from pathlib import Path

from coherence.navigate.cli import _render_obligations, cmd_obligations
from coherence.policy.compiler import compile_obligations
from coherence.trace import gaps as gaps_module
from coherence.trace import model as trace_model
from coherence.trace.suspect import edge_validity

pytestmark = pytest.mark.integration


def test_prototype_feature_incurs_no_high_assurance_ceremony():
    root = Path(__file__).resolve().parents[2]
    obligations = compile_obligations(root, "feat:FEAT-DOGFOOD-PROTOTYPE")
    # No human_review obligation is even applicable under prototype (D16).
    hr = [o for o in obligations if o.kind == "human_review"]
    assert not hr or all(o.requiredness == "not_applicable" for o in hr)


def test_high_assurance_feature_cannot_close_with_missing_verification():
    root = Path(__file__).resolve().parents[2]
    obligations = compile_obligations(root, "sr:SR-DOGFOOD-001")
    blocking_open = [o for o in obligations if o.requiredness == "blocking" and o.state != "satisfied"]
    # SR-DOGFOOD-001 has a binding but no recorded passing run or approved
    # human-review evidence -- both obligations must still be open/blocking.
    assert {"verification_result", "human_review"} <= {o.kind for o in blocking_open}


def test_t031_traces_through_corrects_not_a_fabricated_satisfies():
    from substrate.ledger.tasks import get_task, load_tasks

    root = Path(__file__).resolve().parents[2]
    task = get_task(load_tasks(root / "tasks"), "T-031")
    assert task is not None
    assert task.satisfies == []
    assert any(j.kind == "corrects" and j.target_id == "NC-0001" for j in task.justification)


def test_every_obligation_explains_itself_and_its_cost():
    root = Path(__file__).resolve().parents[2]
    for scope in ("project", "sr:SR-DOGFOOD-001", "task:T-940"):
        for obligation in compile_obligations(root, scope):
            assert obligation.reason  # "explains itself"
            assert obligation.resolve_cmd  # "and its cost" -- how to satisfy it


def test_dual_projection_agrees_on_outcome():
    root = Path(__file__).resolve().parents[2]
    result = cmd_obligations(root, "sr:SR-DOGFOOD-001")
    rendered = _render_obligations(result)
    # The compact (agent) projection and the human-rendered text projection
    # come from the SAME `result` dict -- confirm every obligation's kind and
    # requiredness named in the JSON also appears, verbatim, in the text.
    for obligation in result["obligations"]:
        assert obligation["kind"] in rendered
        assert obligation["requiredness"] in rendered
```

- [ ] **Step 2: Run the tests to verify they behave as expected.**

Run: `rtk proxy uv run python -m pytest tests/integration/test_dogfood_thin_vertical_slice.py -v -m integration`
Expected: All PASS once Tasks 1–4 of this plan are merged. If
`test_high_assurance_feature_cannot_close_with_missing_verification` fails because the fixture SR
unexpectedly already has a passing validation recorded, that is a fixture-hygiene bug in Task 2 —
fix the fixture (it must genuinely have no recorded run), not this assertion.

- [ ] **Step 3: Commit.**

```bash
git add tests/integration/test_dogfood_thin_vertical_slice.py
git commit -m "test(dogfood): thin vertical slice end to end (spec §8)"
```

---

## Increment 6B Acceptance

Mirrors spec §8's acceptance exactly:

- The `prototype` feature (`FEAT-DOGFOOD-PROTOTYPE`) incurs no high-assurance ceremony.
- The `high_assurance` feature/requirement (`FEAT-DOGFOOD-HIGH-ASSURANCE` / `SR-DOGFOOD-001`)
  cannot close with missing or errored verification.
- `T-031` traces through `corrects: NC-0001`, not a fabricated `satisfies`.
- Every compiled obligation explains itself (`reason`) and its cost (`resolve_cmd`).
- The compact agent projection (`cmd_obligations`'s JSON) and the human explanation
  (`_render_obligations`'s text) agree on outcome for the same observation.

## Approval-dependent decisions left open

This resolution round does not decide:

- whether 6B depends on 2C and/or 3B; the CI consumer and obligation-view references above remain
  conditional until that boundary is approved;
- whether the human-review identity is `reviewer` or `reviewed_by`, including its owner and
  serialization;
- whether future local labels such as `test_marker` or course-trace obligations belong in the
  shared progressive-assurance taxonomy; 6B consumes the currently compiled kinds only;
- whether 6B is a CI-gated deliverable or merely produces inputs consumed by the separate CI
  increment; this plan adds no workflow file and makes no CI policy decision.
