---
id: T-061
status: done
title: 'Fix NC-0010: refuse to start/mutate a coherence-plan capture from the
  shared main checkout, only from an isolated git worktree'
dod:
- 'NC-0010: starting or mutating a capture (`guided_entrypoint start`/
  `append`/`resolve`/`finalize`, or whichever CLI entrypoint layer is the
  correct fix point) against a `project_root` that IS a git repository and
  is the *main* checkout (`git rev-parse --git-dir` ==
  `git rev-parse --git-common-dir` for that root) fails closed with a clear
  error identifying the reason (references NC-0010 / "run captures from an
  isolated worktree") instead of silently proceeding to write
  `.intent/intent.json`.'
- 'The same call against a `project_root` that IS a git repository and IS an
  isolated worktree (`git-dir` != `git-common-dir`) succeeds exactly as
  today -- unaffected.'
- 'The same call against a `project_root` that is NOT a git repository at
  all (e.g. a bare `tmp_path` used by most of this repo''s existing unit
  tests) succeeds exactly as today -- unaffected. Detect "not a git repo"
  by the `git rev-parse` invocation itself failing/erroring, and treat that
  as "guard not applicable," never as a block. This is the case most
  existing tests hit -- get this branch right or the whole suite breaks.'
- 'Fix point chosen deliberately: survey `src/coherence/planning/session.py`
  (`start_session`/`append_session_answer`/`resolve_challenge`/
  `finalize_session` or equivalent) vs `src/coherence/planning/
  guided_entrypoint.py`''s CLI handlers before choosing. Prefer the CLI
  entrypoint layer if `session.py`''s own functions are exercised directly
  by existing unit tests against non-git tmp_path roots in ways a
  git-repo-detecting guard inside `session.py` itself would complicate or
  slow down unnecessarily -- state which layer was chosen and why in the
  commit message.'
- 'New regression tests: (a) capture-mutation call against a simulated main
  checkout (a real git repo initialized in a tmp dir, no worktree) is
  refused with a clear error; (b) the same call against a real git worktree
  of that repo succeeds; (c) the same call against a non-git tmp_path
  succeeds unaffected (this may already be implicitly covered by the bulk
  of the existing suite -- confirm it still passes, do not skip re-running
  it).'
- 'Every pre-existing test in `tests/unit/coherence/` still passes
  unmodified in behavior (only touch a pre-existing test if it was itself
  asserting the old, now-incorrect behavior of allowing capture mutation
  from a simulated main checkout -- unlikely, but check).'
- 'Verification commands (this repo''s documented convention): `rtk uv run
  pytest tests/unit/coherence/ -q -o addopts=''''''` all green; `rtk uv run
  ruff check <changed file(s)>` clean; `rtk uv run pyright <changed
  file(s)>` clean.'
- No FEAT-018, FEAT-019, or COHERENCE-BACKEND-HARDENING planning artifact
  is modified by this task -- those are separate, concurrent planning runs,
  not this task's concern.
- Tests/gates pass and the change is committed.
trace_exempt: true
trace_exempt_reason: 'T-061 is exempt from both open gaps, matching T-029''s,
  T-058''s, T-059''s, and T-060''s precedent. (1) task_no_sr: no requirement
  node governs this bugfix -- it corrects behavior documented as a defect
  (NC-0010), not a feature requirement, so there is no SR to satisfy. (2)
  task_no_plan: this task is executed directly from its own brief (this task
  file IS the spec, per the nonconformance record it implements) -- no
  separate implementation plan was authored, since the fix is small and
  fully specified by NC-0010''s Correction section, item (1)/operational
  angle made structural.'
---

**Provenance note**: checked before authoring -- no existing reservation of `T-061` was found in
`docs/` or `tests/` at time of writing.

## Scope

- `src/coherence/planning/session.py` and/or `src/coherence/planning/guided_entrypoint.py` --
  whichever is the correct fix point once surveyed (see DoD).
- Its existing test file(s) -- search `tests/unit/coherence/` for `session.py`, `guided_entrypoint`,
  or a capture-start/append/finalize CLI-verb test.

## Background

Discovered while driving FEAT-018's own `/coherence-plan` workflow: a concurrent session capturing
FEAT-019 in this repo's shared main checkout (not an isolated worktree) overwrote the single,
unnamespaced legacy intent mirror at `.intent/intent.json` (see
`src/coherence/planning/session.py:88-114,360-378`), which then made FEAT-018's own
`legal_actions_adapter` report `STALE_SESSION_STATE` even though FEAT-018's own capture had not
changed. Filed as:

- `docs/nonconformances/NC-0010-shared-legacy-intent-mirror-collides-across-concurrent-runs.md`

Read it in full before starting -- it contains the precise root cause (exact line citations as of
filing time; re-locate by content) and both correction angles. This task implements correction
angle (2): a structural, code-level guard, on top of the already-updated operational rule
(captures must run from an isolated worktree -- see the `worktree-always` memory convention, not
part of this repo).

## Root cause

`_materialize` (`session.py`) writes to both the canonical, run-namespaced path
(`.factory/planning/<run_id>/intent.json`) and a single shared legacy path (`.intent/intent.json`)
on every capture mutation, for every run, unconditionally. When two runs mutate concurrently in the
same working directory, the second write silently clobbers the first run's mirror. The fix is not
to make the mirror itself safe to share (that is the larger, explicitly-deferred correction angle
(2)(a)/(b)/(c) in NC-0010 -- namespacing, locking, or deprecating the mirror) -- it is to refuse the
unsafe precondition outright: block capture mutation from a checkout where a second concurrent
capture could plausibly also be running (the shared main checkout), while leaving isolated worktrees
(which do not share a working directory, and therefore cannot collide this way) and non-git roots
(most existing tests) untouched.

## Verification

1. `rtk uv run pytest tests/unit/coherence/ -q -o addopts=''` -- all green, including new and
   pre-existing tests.
2. `rtk uv run ruff check <changed file(s)>`
3. `rtk uv run pyright <changed file(s)>`
4. Manually confirm: attempting `guided_entrypoint start --run-id TEST-GUARD --project-root .`
   (run from the actual shared main checkout root, `C:/coding/pi-agent-factory`) is refused with a
   clear NC-0010-referencing error, and the same command against an isolated worktree of this repo
   succeeds. Clean up (`.factory/planning/TEST-GUARD` and its `.intent/intent.json` write, if any)
   after this manual check -- do not leave test artifacts behind.
5. Do not touch any FEAT-018, FEAT-019, or COHERENCE-BACKEND-HARDENING planning artifact -- see the
   Definition of Done.
