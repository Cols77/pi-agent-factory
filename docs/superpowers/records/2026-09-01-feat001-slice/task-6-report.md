# T-6 evidence report — execute evidence for FEAT-001's eight SRs

Worktree: `C:/coding/pi-agent-factory-wt/feat001-slice`
Branch: `feat/feat001-slice`
Starting/final source HEAD (no code was changed): `44d585a5a0898ed52b8aa296b387cac3c948120b`

## Summary

Wrote two real evidence artifacts, both backed by an actual `pytest` execution
observed in this task (`rtk proxy uv run pytest -m sr -v -o addopts=''`, 32
passed / 0 failed / 2951 deselected, run 2026-09-01T11:40:21Z–11:40:28Z):

1. `evidence/runs/T-6-evidence-execution-20260901T114021Z.json` — a v1-shaped
   run manifest (`schema_version: 2`), written through the existing
   **atomic writer**, `factory.evidence.manifests.write_run_manifest`. Its
   `validation[0].requirements[]` carries one entry per FEAT-001 SR.
2. `validation/validation-report.json` — the report shape
   `coherence.trace.validation_status.load_validation` reads (path
   `<root>/validation/validation-report.json`), written through the existing
   writer `coherence.measurement.report.write_validation_report`. This is a
   **second, separate evidence mechanism** from (1) — see "Two mechanisms"
   below — and is what actually moves the `executed_evidence` health
   dimension, which is driven by the `verification_result` obligation, not by
   `register check`'s `_validation_state`.

Only SR-002, SR-003, SR-005 and SR-007 are recorded `passed: true` (in both
files). SR-001, SR-004, SR-006 and SR-050 each carry a `note`/`error`
explaining why they are *not* reported passing, and the `passed` key is
omitted for them entirely (never set to `null` — `_validation_state` tests
`"passed" in entry`, so a `null` would have read as *failing* rather than
*unmeasured*; omitting the key correctly leaves them exactly where they were:
pending, with the honest "no measurement, task, or deferral accounts for this
requirement" detail).

## Commands executed

```text
$ rtk proxy uv run pytest -m sr -v -o addopts=''
... (32 individual PASSED lines, one per @pytest.mark.sr("SR-###") test) ...
32 passed, 2951 deselected, 111 warnings in 5.28s
```

Captured to `t6-pytest-sr-run.txt` in the scratchpad; re-run a second time
immediately before authoring the manifest (`started_at`/`ended_at` in the
manifest are from that second run, `2026-09-01T11:40:21Z`–`11:40:28Z`, exit 0,
same 32/0/2951 result — deterministic).

Mapping test outcomes to each SR: `grep -n 'mark.sr('` across `tests/unit`
lists every `@pytest.mark.sr("SR-###")` decorator and the file/line it
decorates (recon step, before writing anything). Each SR's acceptance block in
`requirements/SR-###.md` names the same files via its `kind: test_marker`
`verification.ref`. Cross-referencing the two gave, per SR, the exact list of
pytest node ids to expect PASSED under `-m sr`; the actual `-v` run output was
then checked node-by-node against that expected list (all 32 matched, 0
unexpected, 0 missing). Those nine lists are the `tests:`/`artifacts:` arrays
recorded in both evidence files.

A single command produced all 32 results in one execution — no per-SR pytest
invocation was needed since `-m sr` selects every SR-marked test across the
whole `tests/unit/` tree in one collection pass.

## Two evidence mechanisms — both needed to move, and both are genuinely separate

The task brief's controller reconnaissance covers only `coherence register
check`'s mechanism (`evidence/runs/*.json` → `list_run_manifests` →
`_validation_state` → `classify()`). Investigating `coherence navigate health
--json`'s `executed_evidence` dimension (named explicitly in the brief's
"Verify" clause and in the task title, "record `verification_result`
observations") showed it is driven by an entirely different code path:

- `health.py`'s `executed_evidence_ok` counts `verification_result`
  obligations (`kind == "verification_result"`) whose `state == "satisfied"`.
- `_verification_result_obligation` (`src/coherence/policy/compiler.py:233`)
  computes that state from
  `coherence.trace.validation_status.load_validation(root).get(sr_id)` —
  which reads `<project_root>/validation/validation-report.json`
  (`REPORT_RELPATH`), **not** `evidence/runs/*.json`.
- The existing writer for that file, `coherence.measurement.cli.cmd_validate`
  → `coherence.measurement.pipeline.validate_task_requirements`, is the old
  binding/harness/metric measurement pipeline. It explicitly refuses any
  requirement with no `binding:` (`pipeline.py`: "A proposed requirement has
  no binding, so there is nothing to run"; `report.py`'s
  `run_requirement_validation` would emit `{"id": ..., "error": "proposed
  requirement: no binding to validate"}` for every one of these eight SRs,
  since none carries a `binding:` field — all eight are still in the
  `acceptance:`/`test_marker` "proposed" state T-1–T-5 introduced). Running
  that CLI genuinely, honestly, would not have moved `executed_evidence` at
  all for these SRs; it predates the acceptance-criteria regime and has no
  way to consume it.

So closing the `executed_evidence` gap required authoring
`validation/validation-report.json` directly, through the **existing writer
function** `write_validation_report(path, report)` (an atomic best-effort
JSON write, no schema validation of its own), with a report dict built from
the same real pytest results as the run manifest — not through the harness
pipeline, which cannot express this. This is not a new writer; it reuses the
one function in the codebase whose job is "write this file."

## Manifest writer

`factory.evidence.manifests.write_run_manifest(evidence_dir, manifest)` is the
sole atomic writer for `evidence/runs/*.json` (confirmed by
`src/substrate/evidence/read.py`'s own comment: "No write function lives here
… `factory.evidence.manifests.write_run_manifest` remains the sole atomic
writer"). No writer existed for run manifests importable without going
through the full orchestrator `finalize_run_evidence` pipeline (which needs a
live `Task`/`TaskResult`/`ArtifactStore`/`GitOps` from an actual orchestrated
run — not applicable here, since T-6 is a manual verification-and-recording
task, not an orchestrated task run). `write_run_manifest` itself needed no
orchestrator scaffolding — it just validates the dict against
`evidence_manifest.schema.json` (`substrate.evidence.model.validate_run_manifest`)
and writes it atomically. I built the manifest dict by hand (one-off script,
not committed — see below) and called this existing writer; it validated
successfully on the first real invocation (schema is strict,
`additionalProperties: false` throughout, so this required getting every
field genuinely right — `task_id` pattern `^T-[0-9]+$`, `start_commit`/
`result_commit` as real 40-hex commit SHAs, `sha256` fields as real,
un-prefixed 64-hex digests, `dependencies[].digest` in the prefixed form the
existing `substrate.freshness.fingerprint.fingerprint_file/tool/git_tree`
helpers already produce — I called those helpers directly for every
dependency entry rather than reinventing digest formatting).

No code was added to `src/`. The one-off assembly script lived only in the
scratchpad and is not part of this diff.

### Fields that needed real values (no invented provenance)

- `start_commit`/`result_commit`: `44d585a5a0898ed52b8aa296b387cac3c948120b`
  — the actual `git rev-parse HEAD` at the time, a clean working tree (no code
  changes were made in this task, so start == result).
- `implementation.changed_files`: `[]`; `implementation.patch`: a real,
  honestly-empty blob (`sha256:e3b0c4...` — the real SHA-256 of zero bytes,
  `size: 0`) — because no source file changed. This is not a placeholder; it
  is the true digest of an empty diff.
- `inputs.task`: `.superpowers/sdd/.../task-6-brief.md` with its real SHA-256.
- `inputs.requirements[]`: all eight `requirements/SR-###.md` files with real
  SHA-256s.
- `inputs.factory_config_sha256`: real SHA-256 of `.factory/factory.yaml`.
- `dependencies[]`: real file/tool/git-tree fingerprints via the existing
  `substrate.freshness.fingerprint` helpers (task file, all 8 requirement
  files, factory config, `pytest 9.1.1` as a tool dependency, the commit's
  git-tree via `git rev-parse <commit>^{tree}`).
- `validation[0]`: `command`, `started_at`/`ended_at`, `exit_code: 0`, and
  `summary` transcribed verbatim from the real pytest run.
- `reviews: []`, `decisions: []` — deliberately empty. No review pipeline was
  invoked and, per the task's hard scope limit, no `DecisionFile`/consent/
  `human_review` decision was authored.

## Verification output

### 1. `coherence register check`

Before (baseline, captured before any evidence was written):

```text
$ rtk proxy uv run coherence register check
requirements closure: 55 requirement(s) evaluated
55 pending, 0 unmeasurable, 0 measured-passing, 0 measured-failing, 0 declined (0 with no binding)

undecided requirements (the gate fails on these):
  ! SR-001     SR-001: no measurement, task, or deferral accounts for this requirement
  ! SR-002     SR-002: no measurement, task, or deferral accounts for this requirement
  ! SR-003     SR-003: no measurement, task, or deferral accounts for this requirement
  ! SR-004     SR-004: no measurement, task, or deferral accounts for this requirement
  ! SR-005     SR-005: no measurement, task, or deferral accounts for this requirement
  ! SR-006     SR-006: no measurement, task, or deferral accounts for this requirement
  ! SR-007     SR-007: no measurement, task, or deferral accounts for this requirement
  ...
  ! SR-050     SR-050: no measurement, task, or deferral accounts for this requirement
  ...
```

After (with the two evidence artifacts on disk):

```text
$ rtk proxy uv run coherence register check
requirements closure: 55 requirement(s) evaluated
51 pending, 0 unmeasurable, 4 measured-passing, 0 measured-failing, 0 declined (0 with no binding)

undecided requirements (the gate fails on these):
  ! SR-001     SR-001: no measurement, task, or deferral accounts for this requirement
  ! SR-004     SR-004: no measurement, task, or deferral accounts for this requirement
  ! SR-006     SR-006: no measurement, task, or deferral accounts for this requirement
  ! SR-008     SR-008: no measurement, task, or deferral accounts for this requirement
  ...
  ! SR-050     SR-050: no measurement, task, or deferral accounts for this requirement
  ...
```

**SR-002, SR-003, SR-005, SR-007 changed**: each dropped out of the "undecided"
list — `classify()` now returns `MEASURED_PASSING` for them, because
`evidence/runs/T-6-evidence-execution-20260901T114021Z.json`'s
`validation[0].requirements[]` carries `{"id": "SR-00X", "passed": true, ...}`
for each, backed by the real pytest run above.

**SR-001, SR-004, SR-006, SR-050 did not change** — still "no measurement,
task, or deferral accounts for this requirement". This is honest, not a miss:
each of these four SRs has at least one `kind: manual` acceptance criterion
that no `human_review` decision has ever resolved (SR-001/AC-3, SR-004/AC-3,
SR-006/AC-3, and all three of SR-050's criteria). The manifest documents each
one's real automated-test results (where any exist — SR-001/004/006's AC-1/
AC-2 test_marker tests did pass) in a `note` field, but deliberately carries
no `"passed"` key for these four SR ids, so `_validation_state` returns `None`
for them and `classify()` falls through to the same `PENDING`/blocking state
as before. Recording them as passing would have meant reporting an
unreviewed requirement as accounted — exactly what this task was told not to
do.

### 2. `coherence navigate health --json`

Before:

```json
{"name": "requirement_quality", "satisfied": 8, "expected": 55, "exempt": 0}
{"name": "verification_strategy", "satisfied": 55, "expected": 55, "exempt": 0}
{"name": "executed_evidence", "satisfied": 0, "expected": 55, "exempt": 0}
{"name": "human_review", "satisfied": 0, "expected": 0, "exempt": 0}
```

After:

```json
{"name": "requirement_quality", "satisfied": 8, "expected": 55, "exempt": 0}
{"name": "verification_strategy", "satisfied": 55, "expected": 55, "exempt": 0}
{"name": "executed_evidence", "satisfied": 4, "expected": 55, "exempt": 0}
{"name": "human_review", "satisfied": 0, "expected": 0, "exempt": 0}
```

`executed_evidence`: **0/55 → 4/55** (SR-002, SR-003, SR-005, SR-007 — the
same four `verification_result` obligations now compute `satisfied` because
`validation/validation-report.json` carries a `passed: true, stale: false`
entry for each, and this project's resolved profile for every one of these SR
scopes is `prototype` (confirmed via `resolve_profile(root, "sr:SR-00X")` for
all eight — none is `high_assurance` in this repository today, despite T-8's
brief describing FEAT-001 as intended to be `high_assurance`; that wiring is
not yet in place and is out of this task's scope), so the additional
binding/harness check in `_verification_result_obligation` (which only
applies `if profile == "high_assurance"`) does not suppress these four.

`requirement_quality` **unchanged at 8/55** — expected; that dimension counts
SRs with a resolvable acceptance/verification binding, which T-3/T-5 already
established and T-6 does not touch.

`verification_strategy` **unchanged at 55/55** — expected; it only checks
that each `verification_result` obligation carries a non-empty `resolve_cmd`,
which every one already does regardless of measurement state.

`human_review` **unchanged at 0/0** — expected; under the actual `prototype`
profile, `human_review` obligations compile `not_applicable` for every SR in
this repo today and are excluded from both numerator and denominator. This
dimension is untouched by T-6 and stays exactly where it was; closing it is
explicitly T-8's job, not this task's.

### 3. Manifest on disk

```text
$ cat evidence/runs/T-6-evidence-execution-20260901T114021Z.json
```

Full file is in the diff. The load-bearing entries in
`validation[0].requirements[]`:

```json
{
  "id": "SR-002",
  "passed": true,
  "command": "rtk proxy uv run pytest -m sr -v -o addopts=\"\"",
  "note": "every kind:test_marker acceptance criterion for SR-002 was executed and passed; no kind:manual criterion exists on this requirement.",
  "tests": [
    "tests/unit/requirements/test_cli.py::test_index_stamps_checksums_and_writes_index",
    "tests/unit/requirements/test_cli.py::test_index_leaves_a_proposed_requirement_untouched",
    "tests/unit/requirements/test_closure.py::test_an_unbound_requirement_with_no_disposition_is_pending",
    "tests/unit/requirements/test_register.py::test_load_register_and_get"
  ]
}
```

and, for a manual-blocked SR:

```json
{
  "id": "SR-001",
  "note": "AC-3 is kind:manual (mirrors typed lifecycle relations as Obsidian wikilinks in the requirement body) and unreviewed -- no human_review decision exists. AC-1/AC-2 automated tests passed (see artifacts) but the requirement is not reported measured-passing while a manual criterion is outstanding.",
  "command": "rtk proxy uv run pytest -m sr -v -o addopts=\"\"",
  "automated_tests_passed": [ "...5 real passing node ids..." ]
}
```

No `"passed"` key on the SR-001 entry — confirmed by reading it back through
the real reader:

```text
$ rtk proxy uv run python -c "
from pathlib import Path
from substrate.evidence.read import load_run_manifest, list_run_manifests
m = load_run_manifest(Path('evidence/runs/T-6-evidence-execution-20260901T114021Z.json'))
manifests = list_run_manifests(Path('evidence'))
print('list_run_manifests found:', len(manifests))
for req in m['validation'][0]['requirements']:
    print(req['id'], 'passed' in req, req.get('passed'))
"
loaded ok, task_id= T-6 run_id= T-6-evidence-execution-20260901T114021Z
list_run_manifests found: 1
SR-001 False None
SR-002 True True
SR-003 True True
SR-004 False None
SR-005 True True
SR-006 False None
SR-007 True True
SR-050 False None
```

This is the exact mechanism `coherence register check` consumes
(`_validation_state`), round-tripped through the real production reader, not
re-derived by hand.

### 4. `rtk proxy uv run pytest tests/unit/ -q`

Run in the foreground, blocking (per the coordinator's explicit correction —
an earlier attempt at this same command was silently moved to background by
the harness past its 120s default, and it was re-run explicitly in the
foreground with the full pytest output blocking this turn):

```text
$ rtk proxy uv run pytest tests/unit/ -q -o addopts=''
=========================== short test summary info ===========================
FAILED tests/unit/system/test_remediation.py::test_every_shell_command_names_a_real_subparser
1 failed, 2915 passed, 13 skipped, 113 warnings in 360.43s (0:06:00)
```

Only the known pre-existing failure,
`tests/unit/system/test_remediation.py::test_every_shell_command_names_a_real_subparser`,
fails — identical to the failure recorded in T-5's report. No other test
failed. Nothing in `tests/unit/` was touched by this task (T-6 changed no
`src/` or `tests/` files at all). (A concurrently-completing background
attempt of the same command produced the same result independently: `1
failed, 2915 passed, 13 skipped, 113 warnings in 433.78s` — same failure, same
counts, different wall-clock only.)

### 5. Lint

```text
$ rtk proxy uv run ruff check .
All checks passed!
```

No code was added or changed (only the two evidence data files below), so
this is a no-op confirmation, not new coverage.

## Which of the eight reached "accounted", and why the other four honestly did not

| SR | Acceptance criteria | Automated result | Accounted? | Why |
|----|---|---|---|---|
| SR-002 | AC-1/2/3, all `test_marker` | 4/4 passed | **Yes** — measured-passing | No manual criterion; every automated criterion executed and passed. |
| SR-003 | AC-1/2/3, all `test_marker` | 4/4 passed | **Yes** — measured-passing | Same. |
| SR-005 | AC-1/2/3, all `test_marker` | 5/5 passed | **Yes** — measured-passing | Same. |
| SR-007 | AC-1/2, all `test_marker` | 5/5 passed | **Yes** — measured-passing | Same. |
| SR-001 | AC-1/2 `test_marker`, AC-3 `manual` | 5/5 (AC-1/2) passed | **No** — still pending | AC-3 (body wikilinks mirror typed relations) has no automated check and no `human_review` decision exists. Reporting SR-001 passing would assert a human confirmed the mirror is correct, which nobody has. |
| SR-004 | AC-1/2 `test_marker`, AC-3 `manual` | 5/5 (AC-1/2) passed | **No** — still pending | AC-3 describes cross-language import-overlap coverage the system does not have; it was deliberately authored as an unmet criterion. No automation exists and none should be fabricated. |
| SR-006 | AC-1/2 `test_marker`, AC-3 `manual` | 4/4 (AC-1/2) passed | **No** — still pending | AC-3 describes gate-failing marker enforcement under every profile, which the system does not do (only `high_assurance` gates today); deliberately authored as unmet. |
| SR-050 | AC-1/2/3, all `manual` | none — no `test_marker` criteria exist at all | **No** — still pending | Every criterion requires a human structural-trace review and a gated `human_review` decision; nothing here is automatable at all. There is nothing this task could honestly execute for SR-050. |

**4 of 8 reached "accounted"; 4 of 8 correctly did not.** The task's own
acceptance line ("no SR in FEAT-001 remains 'no measurement, task, or
deferral'") is **not fully met**, by design and per the task's explicit
override: "if that means some of the eight cannot reach 'accounted', that is
the correct and honest outcome." The remaining four are blocked on the human
gates T-4a (authoring consent) and T-8/T-8a (human_review) are meant to
supply — not on anything an agent should paper over here.

## Manual criteria — how they were handled

The six `kind: manual` acceptance criteria across the eight SRs
(SR-001/AC-3, SR-004/AC-3, SR-006/AC-3, SR-050/AC-1, SR-050/AC-2, SR-050/AC-3)
were **never given `passed: true`**, anywhere, in either evidence file. For
each of the four affected SRs:

- The run manifest's `validation[0].requirements[]` entry carries a `note`
  explaining exactly which criterion is unresolved and why, and — where
  automated criteria on the same SR did pass — lists those results separately
  under `automated_tests_passed`, never conflated with the SR's overall
  status.
- The validation report's entry carries an `error` string with the same
  explanation (which `coherence.trace.validation_status._entry_state` reads
  as `state: "error"`, distinct from both `"passed"` and `"failed"` — an
  accurate reflection of "verification is blocked/incomplete", not "the
  requirement failed").
- No `human_review` decision, `DecisionFile`, or consent record was created —
  those are explicitly out of scope for an agent (invariant I-01).

## Files changed

- `evidence/runs/T-6-evidence-execution-20260901T114021Z.json` (new)
- `validation/validation-report.json` (new)
- No `src/`, `tests/`, or `requirements/*.md` files were touched.

## `evidence/` gitignore status

`evidence/` is **not** gitignored. `.gitignore` only excludes
`.factory/artifacts/` (the content-addressed blob store) with the comment
"Content-addressed evidence blobs; compact evidence/runs manifests stay
tracked." `validation/` is likewise not ignored. Confirmed:

```text
$ rtk proxy git check-ignore -v evidence/runs/T-6-evidence-execution-20260901T114021Z.json validation/validation-report.json
(no output, exit 1 -- neither path is ignored)
```

Both evidence artifacts are committed directly in this task's commit (see
below); no force-add was needed.

## Self-review

For every `passed: true` in both files (SR-002, SR-003, SR-005, SR-007 in
each), I checked it back against the real `-m sr -v` PASSED output captured in
this task — every one is a real observed pytest result, not invented. For
every SR reported as accounted, the register-check "before"/"after" quotes
above show the real state transition, driven by the manifest's content, not
by any change to `classify()`, `_validation_state`, or `cmd_check` (those
files were not touched — confirmed by `git status`/`git diff` scope below).
For SR-001/004/006/050, I re-confirmed no `"passed"` key exists on their
entries in either file, and that they remain in `register check`'s undecided
list unchanged.

`git status --short` at the end of this task, in the worktree:

```text
 M docs/superpowers/plans/2026-09-01-feat001-reference-run.md
?? evidence/
?? validation/
```

The modified plan doc was **not** edited by me — it already carried an
orchestrator-authored retrospective note (about this exact task stalling on a
backgrounded verification run) before I resumed. It is out of T-6's scope and
is left alone; only `evidence/` and `validation/` are staged and committed by
this task.

## Concerns

1. **Two separate, undocumented evidence mechanisms.** `evidence/runs/*.json`
   (feeds `register check`) and `validation/validation-report.json` (feeds
   `navigate health`'s `executed_evidence`/`verification_result` obligation)
   are not connected to each other and use different writers, different
   schemas, and different "root" conventions (`evidence/runs/` vs.
   `<project_root>/validation/`, not `evidence/validation/`). The task's own
   controller reconnaissance only describes the first. A future task wiring
   `human_review`/`verification_result` more fully should be aware both exist.
2. **The old `coherence measurement`/harness pipeline cannot serve any of
   these eight SRs** — it hard-refuses any requirement with no `binding:`.
   All eight FEAT-001 SRs are `binding`-less (the "proposed" state the
   acceptance/test_marker regime introduced). If a future task wants
   `coherence measurement run` itself to move `executed_evidence` for
   acceptance-criteria-based SRs, that pipeline needs new code — out of this
   task's scope, and I did not touch it.
3. **The first attempt at running the full unit suite stalled**: it was moved
   to background by the harness past its default 120s timeout, and I
   incorrectly ended a turn waiting on a Monitor notification instead of
   re-issuing the command in the foreground with an explicit longer timeout.
   The coordinator corrected this with an explicit nudge; the final
   verification numbers above come from a foreground, blocking run
   (`timeout: 600000`ms), and this is now recorded as a known failure mode
   for future tasks in this slice (per the orchestrator's own retrospective
   note already added to `docs/superpowers/plans/2026-09-01-feat001-reference-run.md`).
