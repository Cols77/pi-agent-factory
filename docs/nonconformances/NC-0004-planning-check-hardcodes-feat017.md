---
id: NC-0004
title: coherence.planning.check's cross-reference validator hardcodes FEAT-017, blocking bootstrap/check for every other run
external_ref: null
detected_by: FEAT-018 plan-authoring session
status: open
---

## Symptom

`guided_pipeline bootstrap --decompose` and `guided_pipeline check` both fail closed
(`PLANNING_REFERENCE_INVALID`, one finding per requirement) for **any** run whose selected
requirements were not originally derived from FEAT-017's own closure spec — including FEAT-018,
whose run this was detected on.

Root cause, read directly from `src/coherence/planning/check.py`:

- `_planning_reference_paths(root, run_id)` (line 376) takes `run_id` as a parameter and uses it
  correctly for `consent_path`/`capture_journal`, but its FEAT-dossier/bundle lookup is hardcoded:
  `feature_path = root / "docs" / "features" / "FEAT-017.md"` and
  `bundle_path = root / "bundles" / "FEAT-017.json"` — literal `"FEAT-017"`, not `run_id`.
- `_check_planning_references(root, spec_path, spec_text, findings)` (line 406) is called
  unconditionally from `check_planning_input` (line 533) for every run, and repeats the same
  hardcoding at line 413: `feature_candidate = root / "docs" / "features" / "FEAT-017.md"`.
- For each requirement `docs/features/FEAT-017.md`'s frontmatter lists, it reads that
  requirement's own `source` field (a `path#anchor` reference) and checks
  `safe_source != safe_spec` where `safe_spec` is `safe_resolve(root, spec_path)` — `spec_path`
  being **the current run's own `--spec` argument**, not FEAT-017's actual closure spec (line 480).
  Since FEAT-017's real requirements' `source` fields correctly point at FEAT-017's own closure
  spec (`docs/superpowers/specs/2026-09-08-feat017-closure-slice-design.md` and similar), and any
  other run passes its own, different `--spec` path, this comparison is false for every run except
  one that happens to pass FEAT-017's exact closure spec as `--spec` — which no other run has
  reason to do.

Reproduced on this session's FEAT-018 run: `guided_pipeline check --run-id FEAT-018 --spec
docs/superpowers/specs/2026-09-14-feat018-execution-proposal-validator-design.md --plan
docs/superpowers/plans/2026-09-14-feat018-execution-proposal-validator-plan.md` returns
`backend_exit_code: 1`, `ok: false`, with ten `PLANNING_REFERENCE_INVALID` findings — one per
requirement FEAT-017's dossier lists (`SR-043`, `SR-044`, `SR-051` through `SR-055`, `SR-065`,
`SR-071`, `SR-072`) — each reading `"requirement source does not resolve to the authority spec"`.
This reproduces after fixing every other finding the same `check` call raised (spec/plan
frontmatter, intent-answer traceability), confirming it is unrelated to FEAT-018's own content and
is purely a function of FEAT-017.md existing in the repo at all.

Not fixed here: this is a `src/coherence/planning/check.py` code defect, out of scope for a
planning session (which authors spec/plan/intent content, not backend code) to fix as a side
effect.

## Correction

Not yet corrected. Needs its own scoped change:

1. Parameterize `_check_planning_references`/`_planning_reference_paths` by the run's own selected
   feature/spec rather than hardcoding `"FEAT-017"`, OR scope this specific cross-check so it only
   runs when `run_id == "FEAT-017"` (i.e. only re-validates FEAT-017's own closure, as it was
   presumably originally written to do during FEAT-017's own dogfooding run), so an unrelated run's
   `bootstrap`/`check` call does not spuriously re-validate FEAT-017's requirements against the
   unrelated run's own `--spec` argument.
2. Add a regression test that calls `check_planning_input`/`bootstrap --decompose` for a run_id
   other than `"FEAT-017"` (with `docs/features/FEAT-017.md` present in the same repo, as it now
   permanently is) and asserts no `PLANNING_REFERENCE_INVALID` finding is raised for FEAT-017's own
   requirements.
3. Until fixed, `bootstrap --decompose`/`check` cannot reach a clean, `ok: true` result for any run
   other than one that passes FEAT-017's own closure spec as `--spec` — this blocks FEAT-018 (and
   any future run) from completing the guided-planning checkpoint.
