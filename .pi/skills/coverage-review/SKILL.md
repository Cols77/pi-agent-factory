---
name: coverage-review
description: >
  Orchestrate a feature-scoped requirement coverage audit. Resolve the scope,
  dispatch one subagent per SR for semantic review, consolidate verdicts, run
  the gate, and present the report with human-gated disposition for new
  requirements.
---

# Requirement Coverage Review

Orchestrates the coverage audit (spec: `docs/superpowers/specs/2026-08-17-requirement-coverage-review-design.md`).
The deterministic phases are Python (`factory coverage`); only the judgment and
the report presentation are yours.

## Phase order

### Phase 0 + 1 — Machine resolution
Run:
```
python -m factory.coverage audit <feat:FEAT-XXX> --project-root .
```
This writes `coverage-reviews/<feat>-<run-id>/audit.json` with the scope,
completeness findings, and import-graph overlap results. Read it.

### Phase 2 — Per-SR subagent audit
For each SR in the audit result, dispatch one subagent with the packet below.
The subagents are independent sessions — never the session that wrote the code,
and never this one. Dispatch them in parallel.

Task packet (per SR):
```
You are auditing SR-{id} of feature {feat}.

Statement: {statement}
Binding: {harness}/{experiment} {metric} {assert_expr} (trials={trials})
Implementing tasks: {task_ids}
Changed files: {changed_files}
Binding test source: {experiment_path}
Validation report: {measurement}
Import-graph overlap: {overlap_ok} (reached {reached_files},
  changed {changed_files}, overlap {overlap})
Unresolved imports: {unresolved_modules}

Follow the requirement-traceability-audit skill. Return ONLY a JSON verdict
with these mandatory fields:

{sr_id, implemented, honest, confidence, margin, reasoning,
 checked: [...], assumed: [...], verify: [{item, file?, line?, why?}]}
```

Write the subagent's verdict to a JSON file and record it with:
```
python -m factory.coverage verdict <feat> <run-id> <sr_id> --file <verdict.json> --project-root .
```

If a subagent fails to dispatch or returns nothing usable, record it (do not
fabricate a verdict):
```
python -m factory.coverage failure <feat> <run-id> <sr_id> --issue "subagent tool error: <detail>" --project-root .
```
Continue with the remaining SRs. The gate reports `degraded` when a failure is
recorded — never invent a verdict to make a failed SR look audited.

### Phase 3 + 4 — Consolidation + gate
Run:
```
python -m factory.coverage consolidate <feat> <run-id> --project-root .
python -m factory.coverage gate <feat> <run-id> --project-root .
```
Report the gate outcome verbatim. `pass` | `fail` | `degraded`. A `fail` or
`degraded` gate is not green — never present it as covered.

### Phase 5 — Report + disposition
Run:
```
python -m factory.coverage report <feat> <run-id> --project-root .
```
Present the report to the human. For each new-requirement gap the audit exposes:
- **Accept** → route through the **doctor** skill (context → mint → human
  review → promote). Doctor performs every write; you never edit an SR file.
- **Reject** → record via doctor: create the SR file with
  `trace_deferred: <reason>` so the closure register reads it as declined and
  the next audit does not re-propose it.
- **Defer** → same pattern, with a reason that states what must happen first.

## Rules

- **Never write an SR file yourself.** Only the doctor skill does. The auditor
  must never author the audited artifact.
- **Never bind, rebind, or reaffirm a requirement** from this workflow. Route
  stale/weak bindings to the human, then to `binding-requirements`.
- **Report workflow_issues** (subagent failures, unreadable manifests or
  bindings) to the human so the workflow itself can be improved.
- **Every finding carries reasoning.** A verdict without `reasoning`/`checked`/
  `assumed` is invalid — the `verdict` verb rejects it. Do not soften that.
- **Reasoning-carrying presentation.** Show the human the per-SR reasoning and
  evidence, not just pass/fail.
