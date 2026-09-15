---
id: NC-0009
title: run-planning-gates/handoff always evaluate FEAT-017's own closure gate pack, never the run under review's
external_ref: null
detected_by: FEAT-018 handoff attempt, after NC-0004/0005/0007/0008 were fixed and merged
status: open
---

## Symptom

`guided_pipeline run-planning-gates --run-id <any-run>` (and therefore `handoff`, which requires
its result) always evaluates the same three closure gates — `human-review-current`,
`requirement-consent-current`, `cross-artifact-review-current` — against **FEAT-017's own**
closure evidence, regardless of which run is actually being processed.

Root cause, confirmed directly from source: `src/coherence/planning/cli.py`'s `_run_planning_gates`
(~line 535) calls `compile_planning_gate_pack("FEAT-017", "v1")` with a literal string, not
`args.run_id`/the run's own feature id. `compile_planning_gate_pack` itself (`gates.py:153`) does
take `feature_id` as a real parameter — the bug is entirely in this one caller passing a constant.

Reproduced on FEAT-018's own run, after `check`/`review` both passed cleanly (`ok: true`, zero
findings — NC-0004/NC-0005/NC-0007/NC-0008 all fixed and merged): `run-planning-gates` failed with
`PLANNING_GATES_BLOCKED`, and the persisted `.factory/planning/FEAT-018/planning-gate-result.json`
shows `"feature_id":"FEAT-017"` even though `"run_id":"FEAT-018"`, with `human-review-current`,
`requirement-consent-current`, and `cross-artifact-review-current` all `"status":"fail"` with empty
evidence.

**Important distinction from NC-0004/NC-0005/NC-0007/NC-0008**: fixing the hardcoded string alone
would not unblock a non-FEAT-017 run's handoff. Those three gates check for real SR-consent
records and a real cross-artifact review — evidence that FEAT-018 (or any run without an adopted
SR) genuinely does not have, by design: no SR has been authored or consented to for FEAT-018, and
authoring/adopting one is an explicit, separate, later human-consent step (not this planning run's
concern; see this run's own `HANDOFF.md`/spec's repeated "no SR is assigned yet" notes). Fixing the
hardcoding would correctly change the failure from "checking FEAT-017's evidence" to "checking
FEAT-018's own (still-nonexistent) evidence" — the run would still fail to reach handoff, for the
right reason instead of the wrong one. This is not a quick, narrowly-scoped bug the way the prior
four were; it surfaces a materially larger open question — what `human-review`/`requirement-
consent`/`cross-artifact-review` evidence should even mean for a non-FEAT-017, no-SR-yet run — that
deserves its own scoped design, not an ad hoc fix bundled into an unrelated run.

## Correction

Not yet corrected, and not scoped here (deliberately — see distinction above). Whoever picks this
up should:

1. Parameterize `_run_planning_gates`'s `compile_planning_gate_pack` call by the run's own feature
   id instead of the literal `"FEAT-017"`.
2. Separately and primarily: define what `human-review-current`/`requirement-consent-current`/
   `cross-artifact-review-current` evidence should require for a run that has not (yet) adopted any
   SR — whether that's a different, smaller gate pack for pre-SR runs, an explicit "not applicable
   yet" pass condition, or something else is a design decision, not a bugfix.
3. Until this lands, a Claude Code compat-route (`/coherence-plan`) run for any feature other than
   FEAT-017 itself cannot reach a successful `handoff` — the correct, current behavior for such a
   run is to stop at `review` (which does work correctly, per NC-0004/0005/0007/0008's fixes) and
   report the block, exactly as this run did.
