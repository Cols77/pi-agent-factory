---
id: per-criterion-measurement-seed
title: "Per-criterion measurement and complete verdicts — seed"
status: seed
---

# Per-criterion measurement and complete verdicts — seed

> **Status: seed, not a design.** This captures the rationale for one new requirement
> ([[SR-070]]) discovered while auditing why every "measured passing" verdict in
> `validation/validation-report.json` traces back to an agent's own transcription rather than a
> run, and records recon toward its eventual design. Not committed here.

## The gap: acceptance criteria never execute

`verify_sr_marker` (`src/coherence/register/closure.py:129`) does `has_marker = req.id in
collect_markers(path)` — a static AST scan for a marker's *presence* on a file, never an outcome
from running anything. The only path that produces a real pass/fail is a `Binding` plus a harness.
Checked directly: no requirement in the register declares `binding.harness` — all seven bound SRs
(`SR-001`–`SR-007`) carry `harness: null`. `coherence-measurement run --all` (`select_requirement_ids`
in `src/coherence/measurement/pipeline.py`) selects exactly those seven bound SRs and skips the
other 55 (`binding is None`, nothing to run), then errors on all seven identically: `{"id": ...,
"error": "binding: no harness named yet"}` (`src/coherence/measurement/report.py:64`). Every
"measured passing" entry actually on disk instead comes from `validation/validation-report.json`,
whose own `provenance` block says `"recorded_by": "agent"` — an agent read a command's output and
hand-typed the verdict. Nothing in `src/` produces that file's shape today.

## The granularity gap: one file, not one criterion

`SimTestbenchHarness._run_pytest` (`src/coherence/measurement/sim_harness.py:112`) already runs a
pytest selection against `binding.experiment` and computes `unit_pass_rate` from real JUnit XML —
this machinery is not hypothetical. But `binding.experiment` names exactly one file or node id, and
the run is scoped by a bare marker name (`-m unit` by default, `pytest_marker` from `from_config`).
`pyproject.toml` registers `sr` as a marker that *takes an argument* (`pytest.mark.sr("SR-0001")`),
and pytest's `-m` expression language cannot select on a marker's argument value — confirmed no
`conftest.py` anywhere in this repo hooks `pytest_collection_modifyitems` to make it possible. So
the existing harness can measure "this file's tests passed," never "this requirement's own
acceptance criteria passed." Corpus-wide: 51 of 54 `acceptance[].verification.ref` entries name a
bare file; only 3 name a pytest node id. A requirement with three acceptance criteria bound to the
same test file today gets one pass rate for the file, not three individually-addressable outcomes.

## The boundary: what this does not duplicate

- [[SR-002]] owns the register's closure state machine (proposed / measured / declined). It says
  nothing about how a measurement is computed — this seed's requirement does not touch `classify`'s
  state transitions, only what feeds `validation` into them.
- [[SR-024]] owns running harnesses and recording verdicts plus evidence manifests. It is silent on
  granularity — nothing in its statement says a verdict must be per-criterion rather than per-file.
- [[SR-059]] owns visibility and currency of human-consent criteria: requiredness never dropping to
  `not_applicable`, and a `review:<sr_id>` accept going stale on content change. It already gestures
  at the rule this seed needs ("as trackable and impossible to silently skip as a passing automated
  check is") but states no closure consequence for a requirement that mixes `manual` with measured
  criteria, and nothing today enforces one.

## Reusable parts, not a rebuild

`coherence.register.relations._resolve_test` (SR-050 T1) already validates a `path::node::node`
pytest node id against the code index and rejects a line number used as identity — exactly the
per-criterion `ref` shape AC-2 needs to resolve. `SimTestbenchHarness._run_pytest` already executes
a selection and emits a JUnit artifact. `Binding` already carries the assertion threshold, the
re-measurement cadence, and the checksum-staleness mechanism (`content_checksum` /
`is_checksum_current`) that today only the seven bound SRs get. `coherence register show` already
prints a `binding:` line (`src/coherence/register/cli.py:133`) exactly where a per-criterion pass
rate would read naturally.

## A named consequence, checked rather than assumed

`SR-050` and `SR-058` are the only two registered requirements mixing a `manual` criterion with
`test_marker` criteria (grepped across the full register, not assumed). Neither can be reported
measured-passing under this seed's rule without an attributed `review:<sr_id>` decision recorded
for it — and `gate-decisions/` holds zero `review:*` files today (15 files, all `sr:*` authoring
consent). `SR-050`'s own entry in `validation/validation-report.json` already carries a hand-written
`error` explaining it withholds a passing verdict for exactly this reason, predating that
requirement's later AC changes; `SR-058` has never been measured at all. This is the honest
baseline this seed's requirement would make structural instead of something a transcribing agent
has to keep remembering to say by hand.

## Why this is FEAT-007's territory

The gap lives in measurement granularity — how a verdict is computed from a requirement's own
acceptance criteria, not how the register's closure states are named or transitioned
([[FEAT-001]]'s territory, per [[SR-002]]) and not how obligation requiredness is compiled across
governed profiles ([[FEAT-002]]'s territory, per [[SR-059]]). It is a direct extension of
[[SR-024]]'s "run measurement harnesses and record verdicts," which is [[FEAT-007]] MEASURE-AUDIT's
declared scope.

## What is deliberately left open here

- The exact schema change: whether a criterion gains its own `Binding`-shaped block, or whether
  `binding.experiment` grows a structured per-criterion mapping onto the same harness.
- How `_run_pytest` reports one outcome per collected test back up to a specific acceptance
  criterion id, rather than one aggregate rate for the whole selection.
- Whether the `sr` marker itself needs an argument-aware collection hook, or whether per-criterion
  measurement bypasses it entirely by always naming a full node id.

None of this is committed by [[SR-070]]'s acceptance criteria, which state the observable contract
only — the same reasoning [[SR-057]] and [[SR-059]] both used to register `manual`, honestly-reasoned
criteria before choosing an implementation.
