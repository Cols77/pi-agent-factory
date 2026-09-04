---
id: sr050-t3-relation-maintenance-design
title: "SR-050 T3 -- implementation-workflow relation-maintenance obligation"
status: design draft for implementation planning
---

# SR-050 T3 — implementation-workflow relation-maintenance obligation

**Date:** 2026-09-04
**Status:** design draft for implementation planning
**Scope:** `coherence.policy.compiler`, `factory.preflight.checks`, `factory.orchestrator.runner`,
`substrate.codemap.build`
**Feature:** [[FEAT-001]] REQ-TRACEABILITY (T3 of the [[SR-050]] work-package plan)
**Related:** [[SR-057]], [[SR-058]] (register-wide reviewers T3 reuses helpers alongside),
[[SR-063]] (the completion-gate duplication this design deliberately does not resolve),
[[SR-064]] (the performance budget this design deliberately does not commit to)

## Decision summary

An implementation task that changes production or validation code must declare, via its own
`satisfies` SRs' `implemented_by`/`verified_by` relations (SR-050 T1), which files it changed. A
changed file with no owning relation on one of the task's own SRs blocks that task's completion in
the live orchestrator run, not just in a dashboard-visible advisory count.

This is the first FEAT-001 mechanism this session builds that changes what a live run can
actually complete, rather than a read-only reviewer or a CI-only check. It works because a prior
step in this same investigation confirmed `factory.preflight.checks.run_completion_preflight` —
the function actually consulted by `factory/orchestrator/runner.py` to decide whether a completed
run's outcome stands or gets escalated back to `todo` — already operates on `coherence`'s own
`Task`/register/trace objects (`factory.orchestrator.ledger`, `factory.requirements.register`, and
`factory.trace.graph` are deprecated re-exports of their `substrate`/`coherence` equivalents).

## Non-duplication boundary

- Reuses [[SR-050]] T1's `coherence.register.relations.resolve_sr_relations` and T4's
  `coherence.register.review`'s declared-path helpers for relation lookup; does not reimplement
  relation resolution.
- Reuses `substrate.codemap.build`'s existing `profile_source_dirs()`/`_CODE_EXTS`/`_SKIP_DIRS` to
  decide which changed files count as "production or validation code"; does not invent a second
  source-file classifier.
- Extends `coherence.policy.compiler` with one new Obligation kind, following the exact shape of
  `_task_justification_obligation` (same `task:*` scope, same `Task.satisfies` lookup); does not
  introduce a second obligation-compilation mechanism.
- Does **not** attempt the fuller unification of `run_completion_preflight`'s
  `validation_missing`/`validation_failed`/`validation_stale`/`review_missing`/
  `must_fix_unresolved` checks onto `compile_obligations` — those read this run's own live,
  not-yet-persisted transcript state, which the durable Obligation model cannot see until the
  run's evidence manifest is written. That gap is tracked as [[SR-063]], not resolved here.
- Does **not** add a performance budget or benchmark harness for the new per-task reconciliation
  pass, or for any existing FEAT-001 review mechanism. Tracked as [[SR-064]], not resolved here.

## New Obligation: `relation_maintenance`

`_relation_maintenance_obligation(root, scope_ref, profile, *, changed_files=None)`
in `src/coherence/policy/compiler.py`, appended to the `task:*` branch of `compile_obligations`
alongside `_task_justification_obligation`. `compile_obligations` itself grows the same
`changed_files: list[str] | None = None` keyword-only parameter (forwarded only to this one
obligation) so it can be threaded through from `run_completion_preflight`; every existing caller
(`coherence.navigate.obligations`, `coherence.audit.runner`, `coherence.runs.service`, etc.) keeps
calling it with no such argument, gets `None`, and sees `not_applicable` for this one new
obligation — identical to how those callers behave today, since the obligation did not exist
before this change.

**Inputs:**

- `task.satisfies` (via `substrate.ledger.tasks.get_task`/`load_tasks`, the same lookup
  `_task_justification_obligation` already performs) — the task's own declared SRs. Register-wide
  reconciliation (any SR, not just the task's own) is [[SR-057]]/[[SR-058]]'s existing job and is
  not duplicated here.
- `changed_files`: an optional caller-supplied list of repository-relative paths. When `None` (the
  navigate/dashboard call path — `coherence.navigate.obligations`, `coherence navigate present`),
  the obligation cannot know what changed and reports `not_applicable`. When supplied (the live
  gate call path, see below), it is the actual set this run touched.

**Logic** (deliberately ordered — each step only applies once the prior ones didn't already decide
the state; this is what earlier drafting got wrong by conflating "no data yet" with "data says
zero," see below):

1. If the task has no `satisfies` SRs at all: `state="not_applicable"` — there is no SR set to
   reconcile against, regardless of what changed. This is `_task_justification_obligation`'s
   problem, not this one's.
2. Else if `changed_files` is `None` (the navigate/dashboard call path — no run data available at
   all, not even "zero"): `state="not_applicable"` — nothing to check yet, per the agreed
   no-manifest-state answer. `not_applicable` is distinct from `satisfied`: it says the check has
   not run, not that it passed.
3. Else (the task has `satisfies` SRs, and a real, run-derived `changed_files` list is available —
   even if that list is empty): filter `changed_files` to real source/test code — repository
   -relative, resolves under one of `profile_source_dirs(root)`, has a `_CODE_EXTS` suffix, no path
   segment in `_SKIP_DIRS`. This is the one new small addition to `substrate.codemap.build` — a
   public `is_source_path(root, rel_path) -> bool` wrapping the same three checks `discover_source_files`
   already performs per-file, so this obligation (and any future caller) never re-derives the rule.
   For each of the task's `satisfies` SRs, collect the `path` of every dict-shaped
   `implemented_by`/`verified_by` entry (same read as `coherence.register.review._declared_paths`,
   reused directly, not copied). A filtered changed file absent from the union of those declared
   paths is "uncovered". `state="satisfied"` iff there are zero uncovered files — including the
   trivial case where filtering left no files at all (a docs-only or non-code task run) — else
   `state="open"`.
4. `requiredness="blocking"` unconditionally in every branch above (per the agreed severity — no
   profile softening; only `state` varies).

**Resolve_cmd** names the specific uncovered files and which of the task's SRs they should be
declared under (there being more than one candidate SR is left to the resolver/human, not guessed).

## Live-gate wiring

`factory/preflight/checks.py::run_completion_preflight` gains a new parameter,
`changed_files: list[str] | None = None`, and one new check: call
`coherence.policy.compiler.compile_obligations(repo_root, f"task:{task.id}")`, find the
`relation_maintenance` obligation, and if its `state == "open"`, append a new `BLOCKING`
`FreshnessIssue` (`code="relation_uncovered"`) built from its `resolve_cmd`. This is the one new
issue this task adds; every existing hand-rolled check in that function is untouched.

`factory/orchestrator/runner.py`'s existing call site (already computing `start_commit` and
holding `git_ops`) passes `changed_files=git_ops.changed_files(repo_root, start_commit)` — the
identical call `finalize_run_evidence` makes later for the manifest's own
`implementation.changed_files`, so this is not a second, divergent way of asking "what changed";
it is the same fact, asked earlier, before the manifest exists to read it from. This is git used to
answer "what did this run touch," not to infer SR ownership from git history/reachability — the
distinction the source design's "Out of scope" section draws.

```text
runner: task run completes (outcome == "completed")
  -> git_ops.changed_files(repo_root, start_commit)
  -> run_completion_preflight(..., changed_files=...)
       -> compile_obligations(root, f"task:{task.id}")
            -> _relation_maintenance_obligation(...)  [NEW]
       -> existing validation/review checks [UNCHANGED]
  -> completion.ok? outcome stays "completed" : outcome = "escalated", task -> todo
  -> (only then) finalize_run_evidence writes the manifest
```

## Testing

- `tests/unit/coherence/policy/test_compiler.py`: new obligation's distinct states —
  `changed_files=None` (task has `satisfies` SRs) -> `not_applicable`; task with no `satisfies` SR
  at all, regardless of `changed_files` -> `not_applicable`; `changed_files=[]` or a list containing
  only non-source paths, with `satisfies` SRs declared -> `satisfied` (trivially, nothing to
  reconcile — must NOT be confused with the `None` case above, which is what earlier drafting of
  this design got wrong); a real source/test file not covered by any of the task's SRs' relations
  -> `open`; every filtered changed file covered -> `satisfied`. A non-source path (e.g.
  `requirements/SR-001.md` itself, `tasks/T-001.md`) never counts as uncovered.
- `substrate/codemap/build.py`: unit tests for the new `is_source_path` helper directly (inside a
  source dir + code ext -> true; outside every source dir -> false; inside a `_SKIP_DIRS` segment
  -> false), mirroring `discover_source_files`'s own existing per-file logic.
- `tests/unit/preflight/test_completion_preflight.py`: new `relation_uncovered` case (task
  satisfies an SR with no relations, `changed_files` includes a `.py` file under `src/` -> blocks);
  a covered case does not regress the existing passing-validation test; `changed_files=None`
  (default) never introduces the new issue, so every existing test in that file keeps passing
  unmodified.
- Integration-shaped: a `factory/orchestrator/runner.py` test (or extension of an existing one)
  confirming `git_ops.changed_files(repo_root, start_commit)` is what gets passed through, not a
  second computation.

## Out of scope

- Reconciling against SRs the task does not `satisfy` (register-wide coverage is [[SR-057]]/
  [[SR-058]]'s job, already built).
- Any profile-dependent softening of this obligation's requiredness (always `blocking`, per the
  agreed decision).
- Unifying `run_completion_preflight`'s other four checks onto `compile_obligations` ([[SR-063]]).
- A performance budget for this or any other FEAT-001 review mechanism ([[SR-064]]).
- Auto-suggesting or auto-writing the missing relation entry — this obligation only reports; T2
  (the Obsidian mirror/relation writer) remains the tool that would write one.

## Acceptance intent

A task whose `satisfies` SR(s) fail to declare a relation to a changed production or validation
file cannot complete a live orchestrator run: the run escalates back to `todo` with a
`relation_uncovered` issue naming the exact file and candidate SR(s). A task whose relations fully
cover its changed files completes exactly as it does today. A task with no `satisfies` SR, or one
whose evidence isn't available yet at preflight time, is never falsely blocked.
