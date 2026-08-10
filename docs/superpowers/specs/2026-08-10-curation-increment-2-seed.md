# Curation Increment 2 — Seed

Five items were deliberately carried out of Increment 1 (`bind`/`defer`/`check`/`next`, branch
`feat/curation-inc1`). Each was found by review, ruled on, and left undone on purpose. This
document is the record so they are not rediscovered from scratch.

**Source:** the whole-branch review of Increment 1 and its fix wave. Increment 1's spec is
`2026-08-10-curation-workflow-design.md`; its plan is
`../plans/2026-08-10-curation-increment-1-cli-vocabulary.md`.

**State Increment 1 shipped.** Against the drone register (181 requirements): 106 pending,
1 measured-passing, 0 measured-failing, 0 unmeasurable, 74 declined — all 74 of which have no
binding. `check` exits 1.

---

## 1. Spec §3.1 contradicts the shipped code — amend it

**This one is a live trap, not a wish.** Spec §3.1 says a requirement is failing if *any*
validation entry has `passed: false`. Read across manifest history that makes `measured-failing`
absorbing: a requirement that failed, was fixed, and now passes stays failing forever, because one
ancient run outvotes every later pass.

Increment 1 fixed the code (`cli.py:_validation_state` resolves against the **newest** manifest
naming the id, `list_run_manifests` already returning newest-first). The spec sentence was not
touched, so spec and code now disagree.

Amend §3.1 to say newest-manifest-wins. Anyone implementing from the spec text as written will
reintroduce the bug.

## 2. `bind` cannot clear a binding key

Increment 1 fixed `bind` silently destroying an existing `window` and `cadence`: `write_binding`
now carries forward binding keys the call did not name. That is deliberate — silently unnaming a
harness is the same class of loss as dropping a window — but it means **no binding key can be
cleared through the CLI at all**. Removing a `window` now requires editing the file by hand, which
is the thing the write vocabulary exists to stop.

The write vocabulary should close this explicitly rather than by accident. Whatever the shape
(`--clear-window`, an explicit null sentinel, a `rebind` verb), it must not reopen the laundering
hole: clearing a checksum input has to re-stamp honestly, not quietly.

## 3. Extract `closure_report(project_root)` out of `cli.py`

`_deferred_reason`, `_linked_task_status`, `_validation_state` and `_findings` are the
input-resolution half of the closure model, currently living as private helpers in
`src/factory/requirements/cli.py`. They are not presentation.

Increment 3's `survey` node needs exactly `_findings`. As things stand a pipeline node would have
to import a private helper from a CLI module. Promote it to a public
`closure_report(project_root) -> list[tuple[Requirement, ClosureFinding]]` near `closure.py`.

`cli.py` is ~390 lines and carries four concerns; this is the natural seam. Note the constraint
that made the split non-trivial: `closure.py` is a **pure** state model with no I/O, so the
resolution layer cannot simply move into it — it belongs beside it, not inside it.

While there: `_deferred_reason` re-parses every requirement file a second time (181 extra YAML
parses per `check`, 362 per `next`, since `cmd_next` also loads tasks twice). Adding
`deferred: str | None` to `Requirement` in `register.py` removes both the duplicate parse and the
second parsing rule living in `cli.py`, which sits closer to the "reuse existing loaders, no
parallel parsing rules" constraint.

## 4. `check --summary`

Per the Increment 1 ruling, `check` now surfaces a `declined-with-no-binding` bucket so the 74
requirements closed by a traceability deferral are visible rather than silently closed. Honest, but
the report is now ~180 lines against the real register. A `--summary` flag showing counts and the
blocking section alone would likely earn its place for routine use.

## 5. No `undefer`

A deferral never stales and nothing re-opens it, so 74 requirements are closed with no re-review
trigger. This is the same shape as the gap spec §11 already acknowledges in trace ("trace has no
unlink").

Related and unresolved: `trace_deferred` is doing double duty. Those 74 values were written to
answer *traceability* questions — none names a measurement, none has a binding — yet they also
close the requirement for *closure* purposes. Increment 1 ruled to keep the shared field (no new
store, no migration) and make the overlap visible instead. If that proves insufficient, the open
options are a scoped value or a second key, both of which were considered and deferred.

---

## Process note

Every Critical and most Important findings in Increment 1 were gaps the **plan** carried, not
gaps an implementer introduced. The plan's self-review checked type consistency and spec-section
coverage, but never traced one artifact end-to-end through the new verbs. Two questions would have
caught nearly all of them:

- Does a `window` survive a round trip through every new verb?
- What happens when each new verb meets the state 180 of 181 requirements are actually in?

A "walk one artifact through every new verb" pass belongs in the next plan's self-review.
