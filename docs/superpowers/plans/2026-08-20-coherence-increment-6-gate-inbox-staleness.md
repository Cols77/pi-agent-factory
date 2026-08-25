# Coherence Increment 6: Gate Protocol, Inbox, and Staleness Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every assurance gate require an explicit durable decision, compute a single non-authoring inbox, preserve/expire deferrals, and route unresolved freshness safely.

**Architecture:** coherence.gate owns a versioned DecisionFile and atomic store; existing coverage and human-review flows adapt to it without conflating code review annotations with gate decisions. coherence.inbox derives items from source artifacts on read and calls no writer itself. Deferrals accept legacy strings and structured data; expiration creates an inbox item but never mutates authored intent. Freshness routes authoritative/provenance-blocked items to their owner command or blocker.

**Tech Stack:** Python 3.11+, dataclasses, JSON Schema, atomic files, datetime, pytest, TypeScript renderer tests.

---

## Execution Coordination

- Prerequisites: Increment 1 freshness recipes, Increment 4 producer observations, Increment 5 status contract.
- Parallel after DecisionFile schema freezes: pure gate model/store, backward-compatible deferral reader, inbox collectors, and TypeScript renderer.
- Serial: gate store then coverage runner adoption; final inbox/status integration after owner-writer adapters exist.
- HumanReviewGate wire format is not changed until its adapter regressions pass.

## File Structure

**Create:** src/coherence/gate/{__init__,model,store,service}.py, src/coherence/inbox.py, src/coherence/deferrals.py, src/coherence/staleness.py, tests/unit/coherence/{test_gate,test_inbox,test_deferrals,test_staleness_routing}.py.

**Modify:** src/coherence/audit/runner.py, src/factory/orchestrator/human_review.py, src/coherence/{trace,register}/write.py and readers, src/coherence/status.py, relevant Pi review renderer, tests/unit/{coverage,requirements,trace,orchestrator}.

### Task 1: Define and persist explicit decisions

- [x] **Step 1: Write failing DecisionFile tests.**

Use:

    DecisionFile(
      gate_id="coverage:FEAT-001",
      artifact_ref="artifact:coverage-reviews/FEAT-001/report.json",
      decisions=(Decision("SR-001", "accept"),),
      decided_at="2026-08-20T00:00:00Z",
      decided_by="human@example.invalid",
    )

Reject an empty decision set, unknown decision, reject/defer without nonblank reason, defer without ISO review_after, duplicate item IDs, and non-atomic/corrupt reload. Existing valid file must short-circuit re-prompt.

- [x] **Step 2: Implement model/store/service.**

Implement frozen Decision, DecisionFile, load_decision, write_decision, and resolve_gate. Writes use same-directory temporary replace. resolve_gate returns blocked when no decision and unattended mode is true; --no-gates is the sole explicit opt-out.

- [x] **Step 3: Verify and commit.**  (implementation f60eb55 + review fixes 36f2096)

Run:

    rtk proxy uv run python -m pytest tests/unit/coherence/test_gate.py -q
    git add src/coherence/gate tests/unit/coherence/test_gate.py
    git commit -m "feat(coherence): persist explicit gate decisions"

### Task 2: Adapt coverage gates without changing annotation review

- [x] **Step 1: Write failing coverage gate tests.**

Assert the former 300-second timeout no longer produces a human-reviewed report without a DecisionFile. An unattended run without decision exits nonzero; an existing valid decision resumes without a prompt; --no-gates remains explicit. Assert orchestrator human-review decision JSON stays byte-compatible.

- [x] **Step 2: Implement adapters.**

Replace coherence.audit runner timeout logic with coherence.gate.resolve_gate and map per-SR verdict items to DecisionFile entries. Keep factory/orchestrator HumanReviewGate separate; add an adapter only where its result is represented as a gate item.

- [x] **Step 3: Verify and commit.**  (f0230e2)

    rtk proxy uv run python -m pytest tests/unit/coverage/test_runner.py tests/unit/coverage/test_gate.py tests/unit/orchestrator/test_human_review.py tests/unit/coherence/test_gate.py -q
    git add src/coherence/audit src/factory/orchestrator/human_review.py tests/unit
    git commit -m "feat(gate): require decisions for coverage finalisation"

### Task 3: Migrate deferrals compatibly

- [x] **Step 1: Write legacy/structured read tests.**  (tests/unit/coherence/test_deferrals.py)

Require the reader to accept:

    trace_deferred: "reason"

and:

    trace_deferred:
      reason: "reason"
      review_after: "2026-09-01T00:00:00Z"
      decided_at: "2026-08-20T00:00:00Z"
      decided_by: "human@example.invalid"

Assert both render the same present deferral; only structured due deferrals appear expired. Unknown shapes are rejected, not treated current.

- [x] **Step 2: Implement reader-first migration.**

Add a shared parse_deferral value object. Retarget trace/register/coverage readers before writers. Extend defer CLI with --review-after; old calls still write/read legacy-compatible values. Expiration never clears frontmatter.

- [x] **Step 3: Verify and commit.**  (dcfed44)

Run:

    rtk proxy uv run python -m pytest tests/unit/requirements/test_write.py tests/unit/requirements/test_cli.py tests/unit/trace/test_write.py tests/unit/trace/test_model_nodes.py tests/unit/trace/test_gaps.py tests/unit/coverage/test_scope.py tests/unit/coherence/test_deferrals.py -q
    git add src/coherence tests/unit
    git commit -m "feat(coherence): support expiring deferrals"

### Task 4: Compute inbox and route blocked freshness

- [x] **Step 1: Write source collector tests.**  (tests/unit/coherence/test_inbox.py, test_staleness_routing.py)

Build fixtures for coverage reports, session review suggestions, KB candidates, expired deferrals, and stale register bindings. Assert `InboxItem(id, source, kind, ref, summary, evidence, resolve_cmd: tuple[str, ...] | None, review_after)` is stable-sorted, has no duplicate ID, and creates no new file. Assert authoritative_gate staleness maps to the owning ordered `resolve_cmd` tuple unchanged and provenance_blocked maps to a blocker without resolver execution.

- [x] **Step 2: Implement pure collectors.**

Implement coherence.inbox.list_items(root, now) reading all named sources and coherence.staleness.route(result). Inbox does not call doctor, trace, register, or KB writers; resolve_cmd is informational.

- [x] **Step 3: Integrate status and renderer.**

Add inbox triage and status counts from the pure items. The Pi renderer consumes DecisionFile/InboxItem JSON only. Run:

    rtk proxy uv run python -m pytest tests/unit/coherence/test_inbox.py tests/unit/coherence/test_staleness_routing.py tests/unit/coherence/test_deferrals.py -q
    rtk proxy npm test --prefix pi-ext/factory-watch -- review-protocol review-model coverage-run-command

- [x] **Step 4: Commit.**  (5a84e27)

    git add src/coherence/inbox.py src/coherence/staleness.py src/coherence/status.py pi-ext/factory-watch tests/unit/coherence
    git commit -m "feat(coherence): compute triage inbox and stale routing"

    Scoping note: inbox sources wired concretely = coverage gates, expired
    deferrals, stale register bindings; staleness routing for
    authoritative_gate/provenance_blocked. "Session review suggestions" and
    "KB candidates" sources are under-specified in the plan text and are not
    yet wired; the Pi renderer npm verify passed unchanged (22 tests).

### Task 5: Verify Increment 6

- [x] **Step 1: Run gates and checks.**  (note below)

Run:

    rtk proxy uv run python -m pytest tests/unit/coherence tests/unit/coverage tests/unit/requirements tests/unit/trace tests/unit/orchestrator -q
    rtk proxy uv run ruff check src tests
    rtk proxy uv run pyright

Expected: no finalisation without a decision; every input source appears in inbox; blocked freshness names ownership.

Verification note: 1183 passed / 1 skipped. Two orchestrator failures are
pre-existing and unrelated to Increment 6 (``test_exit_five_is_a_pass_in_run_detail
_too`` fails on a clean base -- a ``sim`` gate returncode 5; ``test_file_gate
_waits_for_the_file_to_appear`` passes in isolation and only flaked under full-suite
load). ruff: clean. pyright: 0 errors on every Increment 6 file (a repo-wide
pyright baseline of 74 errors pre-exists in `factory/*` / `substrate/*` and is
untouched by this work). New inbox sources all verified: expired deferrals,
stale register bindings, coverage gates, and suspect/invalid/waived edges.

## Plan Self-review

- Covers the original unified gate, inbox, expiring deferral, and unresolved-staleness requirements without making inbox an author or resolver.

## Review Amendments

DecisionFile has schema=1 and is stored as <run_dir>/gate-decisions/<gate_id>.json; load_decision(path) returns a typed corrupt-file diagnostic, write_decision(run_dir, file) validates then atomically replaces. The Pi renderer writes this file through the same validated service. Item IDs are coverage:<run>:proposal:<id>, coverage:<run>:warning:<id>, doctor:<id>, trace:<id>, or review:<id>; accept/reject/defer never author a requirement/trace change, and owning writers apply any follow-up action.

Adopt the DecisionFile adapter for coverage, doctor proposals, trace-gap review, and HumanReviewGate. Human review maps approve to accept and reject to reject while retaining review-decision.json compatibility. Inbox collectors start only after the deferral parser and staleness source are final. unresolved_staleness(root) performs the documented guarded-read/status sweep and exposes recorded StalenessObservation/ResolutionBlocker items; inbox reads that sweep, never executes a resolver.

## Addendum (2026-08-22): progressive assurance — requiredness in the gate protocol, suspect-edge review, milestone baselines

See `docs/superpowers/specs/2026-08-22-coherence-progressive-assurance-design.md` (section 4 suspect relationships and baselines, section 10 disposition row for Increment 6). Requires this plan's Tasks 1-5, Increment 2B, and Increment 4's addendum merged first. Increment 6B's dogfood slice is this addendum's mandatory successor and consumes everything it adds.

### Task 6: `coherence.trace.suspect.edge_validity` and the `human_review` obligation kind

**Unresolved review-contract decisions (not closed by this addendum):** do not choose between
`reviewer` and `reviewed_by` as the human-review identity field. Do not decide whether that
evidence is a separate `human_review` contract or part of `verification_result`; no unapproved
contract may be introduced here. The waiver source/loader and its authority also remain open;
this round does not select governed-artifact frontmatter versus `DecisionFile` as authoritative.

- [ ] **Step 1: Write the failing tests.**

Add `tests/unit/coherence/trace/test_suspect.py`:

```python
import pytest
from dataclasses import dataclass

from coherence.trace.suspect import edge_validity

pytestmark = pytest.mark.unit


@dataclass
class _FakeGap:
    kind: str
    disposition: str


def test_no_gaps_without_recorded_prior_state_is_valid():
    assert edge_validity([]) == "valid"


def test_empty_gaps_preserve_recorded_suspect_state():
    assert edge_validity([], prior_state="suspect") == "suspect"


def test_empty_gaps_preserve_recorded_waived_state():
    assert edge_validity([], prior_state="waived") == "waived"


def test_pending_sr_stale_is_suspect():
    assert edge_validity([_FakeGap("sr_stale", "pending")]) == "suspect"


def test_pending_sr_unsatisfied_is_invalid():
    assert edge_validity([_FakeGap("sr_unsatisfied", "pending")]) == "invalid"


def test_only_non_pending_gaps_is_waived():
    # A deferred/exempt gap is an explicit, recorded acceptance -- not a
    # silent return to "never had a problem." Spec section 13 amendment row 3
    # (STRICT reading): no automatic path to `valid` exists at any
    # requiredness level; a deferred/exempt gap classifies as `waived`, never
    # `valid`. Restoring `valid` always requires a policy-authorized
    # DecisionFile `accept` action.
    assert edge_validity([_FakeGap("sr_stale", "deferred")]) == "waived"


def test_only_exempt_gaps_is_waived():
    assert edge_validity([_FakeGap("sr_unsatisfied", "exempt")]) == "waived"
```

Add to `tests/unit/coherence/policy/test_compiler.py` (Increment 2B): seed an SR under
`profile: high_assurance` with no human-review identity evidence, compile obligations for its
`sr:` scope, and assert a `human_review` obligation comes back `requiredness == "blocking"`,
`state == "open"`; assert the same SR under `profile: prototype` gets `requiredness ==
"not_applicable"` (D16: `human_review` does not even apply under `prototype`).

Run:

    rtk proxy uv run python -m pytest tests/unit/coherence/trace/test_suspect.py tests/unit/coherence/policy/test_compiler.py -k "suspect or human_review" -v

Expected: FAIL (`coherence.trace.suspect` does not exist yet; no `human_review` obligation is
emitted yet).

- [x] **Step 2: Implement `src/coherence/trace/suspect.py`.**

```python
"""Suspect relationship validity (spec section 4), derived FROM the existing
gap engine -- not a second dependency graph. coherence.trace.gaps.find_gaps
already detects when an edge's target changed since a validation/binding was
recorded (sr_stale) or is missing outright (sr_unsatisfied/sr_unvalidated/
sr_unvalidatable); this module only classifies a gap set into the guide's
five-state validity vocabulary. With no gaps, `valid` is the initial result
only when no prior state is recorded; a supplied prior non-`valid` state is
preserved, so an empty current gap set never silently restores `proposed`,
`suspect`, `invalid`, or `waived`. Deterministic code only ever downgrades
from an assumed valid baseline or records an explicit waiver -- restoring
`valid` after a downgrade/waiver is a policy-authorized human action recorded
through the gate protocol's DecisionFile (Task 3/4 of this plan), never
computed here, and there is no requiredness level (advisory/required/
blocking) at which that rule relaxes (spec section 13 amendment row 3,
STRICT reading).

Note on granularity: `find_gaps` returns node-keyed gaps (`Gap.node_id`), so
"governed edge validity" here is really governed SR-NODE validity today --
a genuinely per-edge (not per-SR-node) model is future work, not something
this module or its callers should claim.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from coherence.trace.gaps import Gap

ValidityState = Literal["proposed", "valid", "suspect", "invalid", "waived"]

_INVALID_GAP_KINDS = ("sr_unsatisfied", "sr_unvalidated", "sr_unvalidatable")
_SUSPECT_GAP_KINDS = ("sr_stale",)
_WAIVER_DISPOSITIONS = ("deferred", "exempt")


def edge_validity(
    gaps_for_edge: "list[Gap]", *, prior_state: ValidityState | None = None
) -> ValidityState:
    """Classify current gaps without silently clearing recorded state.

    An empty gap set returns the supplied prior state, if any, and otherwise
    establishes the initial `valid` state. Only explicit `deferred`/`exempt`
    dispositions produce `waived`; absence of a pending gap, an empty set, or
    an unknown disposition is not waiver evidence. The waiver source and its
    authority are selected by a later gate-policy decision, not here.
    """
    if not gaps_for_edge:
        return prior_state if prior_state is not None else "valid"
    pending = [g for g in gaps_for_edge if g.disposition == "pending"]
    if any(g.kind in _INVALID_GAP_KINDS for g in pending):
        return "invalid"
    if any(g.kind in _SUSPECT_GAP_KINDS for g in pending):
        return "suspect"
    if all(g.disposition in _WAIVER_DISPOSITIONS for g in gaps_for_edge):
        return "waived"
    return "proposed"
```

- [x] **Step 3: Add the `human_review` obligation kind.**

In `src/coherence/policy/compiler.py` (Increment 2B), extend the existing `elif
scope_ref.startswith("sr:")` branch (already appending `_verification_result_obligation`, added
by Increment 4's addendum) to also append `_human_review_obligation(root, scope_ref, profile,
nodes=nodes, edges=edges)` -- passing the SAME preloaded `nodes`/`edges` objects from
`compile_obligations` through `resolve_profile` and both helpers; no helper reloads the graph.
via Increment 2B's `nodes=`/`edges=` passthrough param, so this does not add a second graph
reload on top of the one `resolve_profile` already does:

```python
def _human_review_obligation(
    root: Path, scope_ref: str, profile: str, *, nodes, edges,
) -> Obligation:
    sr_id = scope_ref.partition(":")[2]
    # Resolve the SR's real file the same way resolve_profile already does
    # correctly -- via the trace node's `.path`, found by loading nodes and
    # matching by frontmatter id -- never a guessed `requirements/<id>.md`
    # path, which breaks for any file not literally named `<id>.md` (e.g.
    # `SR-002-foo.md`).
    node = next((n for n in nodes if n.id == sr_id and n.kind == "sr"), None)
    sr_path = node.path if node is not None else None
    # The identity field and obligation ownership are unresolved. Do not read
    # either `reviewer` or `reviewed_by`, and do not invent a separate contract
    # until the open decisions above are approved.
    reviewed = False
    # Only high_assurance requires a recorded human review; prototype does not
    # apply this obligation at all (D16's "three obligation kinds" scope).
    requiredness = "blocking" if profile == "high_assurance" else "not_applicable"
    resolve_cmd = (
        (f"record approved human-review identity for {sr_path.name} once the field contract is decided",)
        if sr_path is not None
        else (f"{sr_id}: no matching sr: trace node found -- register the SR first",)
    )
    return Obligation(
        id=f"ob:human_review:{scope_ref}",
        scope_ref=scope_ref,
        kind="human_review",
        requiredness=requiredness,
        reason=f"{profile} requires a recorded human reviewer for high-criticality requirement {sr_id}",
        source_policy=profile,
        state="satisfied" if reviewed else "open",
        resolve_cmd=resolve_cmd,
    )
```

Coordination note with Increment 5's addendum: Increment 5's `compile_health_dimensions` (dimension
11, `human_review`) filters `human_review` obligations to `requiredness in ("required",
"blocking")` before computing satisfied/expected, so `_human_review_obligation` correctly returning
`not_applicable` for every `sr:` scope under `prototype` needs no change here — the two addenda were
checked against each other and are consistent: `not_applicable` is emitted once, here, and excluded
from the denominator once, in Increment 5's dimension compiler, never double-handled.

- [x] **Step 4: Wire requiredness into the gate protocol.**  (commit 076e61f)

The gate protocol's DecisionFile (this plan's Task 3/4) gains one new item kind: `suspect:<sr_id>`,
emitted by inbox collection whenever `edge_validity` returns `suspect`, `invalid` or `waived` for
an SR's gap set (a `waived` classification still surfaces in the inbox as an explicit, recorded
acceptance — never silently dropped from view). Per the spec's STRICT rule (§13 amendment row 3):
**no automatic path to `valid` exists at any requiredness level.** A `suspect`/`invalid`/`waived`
item never auto-closes back to `valid` regardless of whether its obligations are `blocking`,
`required`, or `advisory` — `unresolved_staleness` (this plan's own machinery) reports it as a
`ResolutionBlocker` until a human writes an `accept` DecisionFile entry, the one policy-authorized
action allowed to record `valid` again. (An earlier draft of this step said a `suspect` item under
only `advisory`/`required` obligations "may still auto-resolve once its underlying gap clears" —
that contradicted the spec's decided rule and is removed with no replacement carve-out.
Deterministic code may only ever downgrade `valid → suspect/invalid` or record `waived` for a
deferred/exempt gap; restoring `valid` is always the same human, policy-authorized act, uniformly,
independent of requiredness.)

**Expiring exceptions (spec §10 row 6).** Spec row 6 assigns "expiring exceptions" to this
increment, but Task 7's `expired_baselines` below only covers baseline documents, not a general
obligation waiver with an expiry. This is closed here with one small, real mechanism: an SR or
task's frontmatter may declare an optional `waived_until: <ISO date>` field, and a `DecisionFile`
entry of kind `accept` on a `suspect:<sr_id>`/`ob:<kind>:<scope_ref>` item may set `waived_until`
the same way a `defer` decision already carries `review_after` (this plan's Task 3). However, the
existing plan text names both the governed artifact frontmatter and the `DecisionFile` entry as
possible sources and does not define precedence, so the authoritative waiver source and loader are
an explicit open decision, not an implementation choice in this increment:

> **Open decision — waiver source/loader:** choose whether `waived_until` is authoritative in the
> governed SR/task frontmatter or in the loaded `DecisionFile` accept entry, and then name one
> loader/API as the sole compiler input. Until that decision is made, do not support two writable
> copies or infer precedence between them.

After that decision, `coherence.policy.compiler.compile_obligations` must read the one authoritative
source: while `today <= waived_until`, the obligation keeps the canonical recorded state
`state == "waived"` even though the underlying gap is still open; once
`today > waived_until`, the waiver stops applying — the obligation reverts to its normal,
gap-derived `state`/`requiredness`, and the item reappears in the inbox as an ordinary open item,
not a specially-flagged "expired" state. An expired waiver is not a new state; it is simply the
absence of an active one, computed by a date comparison, not a stored transition. This remains the
smallest mechanism that satisfies "expiring exceptions": one authoritative expiry field, one date
comparison in the compiler, no new record type or CLI verb.

- [x] **Step 5: Run the tests.**

Run:

    rtk proxy uv run python -m pytest tests/unit/coherence/trace/test_suspect.py tests/unit/coherence/policy/test_compiler.py tests/unit/coherence -q

Expected: PASS.

- [x] **Step 6: Commit.** (implementation 86f0c8 + review fixes 14f29ba)

    git add src/coherence/trace/suspect.py src/coherence/policy/compiler.py tests/unit/coherence/trace/test_suspect.py tests/unit/coherence/policy/test_compiler.py
    git commit -m "feat(gate): human_review obligation, suspect-edge validity, gate-protocol wiring"

### Task 7: Milestone baselines (optional, product/high_assurance only)

- [x] **Step 1: Write the failing tests.**  (tests/unit/memory/test_baseline.py, committed 219034d)

Add `tests/unit/memory/test_baseline.py`, mirroring the existing `FR-*`/`NC-*` record
tests: a `Baseline` record at `docs/baselines/BASELINE-*.md` with frontmatter `id`, `title`,
`git_ref` (a commit sha the snapshot pins), `scope` (list of `sr:`/`adr:`/`feat:` refs it covers),
and `approved_by`. Assert loading a directory with no baselines returns `{}` (baselines are
optional, per spec section 4, not required to run an experiment or ship a prototype); assert a
malformed record degrades to `scope_errors`, matching every other record type in this repo.

Run:

    rtk proxy uv run python -m pytest tests/unit/memory/test_baseline.py -v

Expected: FAIL (`ModuleNotFoundError`).

- [x] **Step 2: Implement `src/factory/memory/baseline.py`.**

Mirror `factory/memory/nonconformance.py` (Increment 2B) exactly: `Baseline` frozen dataclass
(`id`, `title`, `path`, `git_ref`, `scope: list[str]`, `approved_by`, `scope_errors`),
`load_baselines(repo_root) -> dict[str, Baseline]`, `DuplicateBaselineIdError`. Add
`src/substrate/schemas/baseline.schema.json` requiring `id` (pattern `^BASELINE-[0-9]+$`),
`title`, `git_ref`, `approved_by`; `scope` defaults to `[]`.

- [x] **Step 3: Wire an expiry check.**

A baseline whose `scope` includes an SR that has since gone `suspect`/`invalid`
(`coherence.trace.suspect.edge_validity`, Task 6) is a stale baseline, not merely a stale SR --
add `expired_baselines(root) -> list[str]` to `src/coherence/trace/suspect.py`, returning baseline
ids whose scope contains at least one suspect/invalid SR. This is queried, never enforced
automatically: closing an expired baseline is a human decision recorded the same way any other
gate-protocol decision is (Task 4), not an auto-transition.

- [x] **Step 4: Run the tests.**

Run:

    rtk proxy uv run python -m pytest tests/unit/memory/test_baseline.py tests/unit/coherence/trace -q

Expected: PASS.

- [x] **Step 5: Commit.**  (219034d)

    git add src/factory/memory/baseline.py src/substrate/schemas/baseline.schema.json src/coherence/trace/suspect.py tests/unit/memory/test_baseline.py
    git commit -m "feat(baseline): optional product/high_assurance baseline records and expiry"
