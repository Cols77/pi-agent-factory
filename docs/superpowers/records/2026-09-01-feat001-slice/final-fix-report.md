# Final whole-branch review — fix wave report

Worktree: `C:/coding/pi-agent-factory-wt/feat001-slice`, branch `feat/feat001-slice`.
Start: `378c2a0`. End: `9b3d53a`. All findings in the brief are addressed; nothing
in the explicit out-of-scope list was touched.

## Commits

| SHA | Subject | Findings |
|---|---|---|
| `911b265` | fix(mirrors): bound the sentinel search to its own section | C1, I2, M1 |
| `2e76e98` | fix(policy): human_review requires an attributed decision | C3 |
| `5c7c4d3` | fix(validation): schema and provenance for the validation report | C2 |
| `d87e951` | fix(measurement): surface a failed validation-report write | I1 |
| `03a423f` | fix(registry): load v1 orchestration manifests too | I5 |
| `399668f` | fix(inbox): guard the register load, report an unreadable register | I7, M5 |
| `570ac4e` | fix(gates): run the wikilink mirror check in the full gate | I3 |
| `9b3d53a` | docs(plan): strike T-8b's false high_assurance premise | M8 |

---

## C1 — unbounded first-sentinel search (`src/coherence/mirrors/generate.py`)

### What changed

`_locate_block` no longer takes the first line-anchored `<!-- end derived -->`
anywhere after the heading. A new `_section_end` bounds the section at the next
`^## ` heading (a `### ` subheading does not match) or EOF, and the section must
carry **exactly one** sentinel:

| sentinels in section | other | outcome |
|---|---|---|
| 1 | — | the owned span, as before |
| ≥2 | — | `MirrorFormatError` — ambiguous end |
| 0 | a sentinel exists elsewhere in the file | `MirrorFormatError` — the boundary is named outside the span this generator owns (the shape that used to delete data silently) |
| 0 | this generator's own `MARKER_LINE` is inside the section | `MirrorFormatError` — derived content with no recorded end (the "zero-with-content" case) |
| 0 | none of the above | the bootstrap shape match, unchanged, now hard-bounded at the section end |

Every one of these is caught per file by `regenerate_all`/`check_all`, so it is a
reported failure with the file left byte-for-byte untouched. Each message names
the file and the exact repair.

### RED (against `378c2a0`)

Three new tests in `tests/unit/mirrors/test_generate.py`. Real assertion
failures, no `ImportError`:

```
    def test_a_sentinel_named_in_later_prose_never_swallows_the_sections_between(tmp_path):
        ...
        after = path.read_bytes()
>       assert after == before, "the file must not be rewritten at all"
E       AssertionError: the file must not be rewritten at all
E       assert b'---\r\nid: ... survive.\r\n' == b'---\r\nid: ... survive.\r\n'
E         At index 188 diff: b'<' != b'-'

    def test_a_stray_end_sentinel_inside_the_owned_span_is_reported_not_duplicated(tmp_path):
        ...
>       assert results[0].changed is False
E       AssertionError: assert True is False
E        +  where True = FeatureMirrorResult(feature_id='FEAT-098', ..., changed=True, error=None).changed

    def test_a_derived_block_whose_sentinel_was_deleted_is_reported_not_reguessed(tmp_path):
        ...
>       assert results[0].changed is False
E       AssertionError: assert True is False
E        +  where True = FeatureMirrorResult(feature_id='FEAT-097', ..., changed=True, error=None).changed

FAILED tests/unit/mirrors/test_generate.py::test_a_sentinel_named_in_later_prose_never_swallows_the_sections_between
FAILED tests/unit/mirrors/test_generate.py::test_a_stray_end_sentinel_inside_the_owned_span_is_reported_not_duplicated
FAILED tests/unit/mirrors/test_generate.py::test_a_derived_block_whose_sentinel_was_deleted_is_reported_not_reguessed
3 failed, 16 deselected in 1.02s
```

### GREEN

```
$ rtk proxy uv run pytest tests/unit/mirrors/ -q
.................................                                        [100%]
33 passed in 1.12s
```

---

## C2 — hand-authored, schema-unvalidated `validation/validation-report.json`

### What changed

**1. A schema, validated on load.**

* New `src/substrate/schemas/validation_report.schema.json`.
* New `src/substrate/validation/model.py` with `validation_report_errors` /
  `validate_validation_report`, following exactly the pattern
  `substrate/evidence/model.py`'s `validate_run_manifest` already gives
  `evidence/runs/*.json` (schema in `src/substrate/schemas/`, module resolves it
  once, one `validate_*` raising `ValueError` naming every violation).
* `coherence.trace.validation_status.load_validation` validates on load and
  returns **no statuses** for a report that does not validate — fail-closed, so
  nothing can be reported measured-passing out of a store whose shape nothing
  checked.
* `coherence.navigate.queries._validation_report_is_corrupt` now counts schema
  failure as corrupt, so an unvalidatable report reaches the navigator's existing
  DEGRADED path ("validation report is unreadable") instead of reading as "never
  validated". Without that, the fail-closed `{}` would itself be a silent
  inference, which is what I-03 forbids.

The schema requires `provenance`, and requires a `recorded_by: "hand"` report to
cite `run_id`, `evidence_manifest`, `commit` and a `note`. Entries are
shape-checked (known fields only, so a misspelled `pased` is rejected rather than
silently read as "not passed"; correct types; `passed`/`error` mutually exclusive,
since `_entry_state` reads `error` first and `passed` second). Optional
top-level `run_id`/`generated_at` are permitted because
`coherence.runs.measurement_adapter` reads them.

**2. The provenance block.** `validation/validation-report.json` gained exactly
one added object; every per-SR entry is byte-identical (`10 insertions(+), 1
deletion(-)`):

```json
"provenance": {
  "recorded_by": "hand",
  "recorded_at": "2026-09-01T11:40:28Z",
  "command": "rtk proxy uv run pytest -m sr -v -o addopts=\"\"",
  "run_id": "T-6-evidence-execution-20260901T114021Z",
  "evidence_manifest": "evidence/runs/T-6-evidence-execution-20260901T114021Z.json",
  "commit": "44d585a5a0898ed52b8aa296b387cac3c948120b",
  "note": "Recorded by hand, not emitted by a harness. No code in this repository can produce these entries: every FEAT-001 SR is binding-less, and coherence.measurement.report.run_requirement_validation returns {'id': ..., 'error': 'proposed requirement: no binding to validate'} and exits before measuring for a binding-less SR. A human ran the command above, read its output, and transcribed the per-SR results here; the `metric`/`assert`/`trials`/`declared_trials`/`stale` fields are that human's transcription of what the run showed, not values any code computed. The run itself is recorded in `evidence_manifest`, which carries the run id, the commit and the per-SR file hashes for the same event; these two files are the only record of it. Reproduce with the command above: it selects the @pytest.mark.sr tests named in each entry's `artifacts`."
}
```

`command` and `recorded_at` and `commit` are read straight out of the manifest's
own `validation[0].command`, `ended_at` and `result_commit`, so the two files
agree by construction; a test asserts that agreement.

**3. The producer.** `coherence.measurement.cli.cmd_validate` — the one place the
canonical report is built from a real measurement sweep — stamps
`recorded_by: "harness"` via a new `harness_provenance()` in
`coherence/measurement/report.py`. `recorded_by: "harness"` is a claim only the
producing code may make, so it is never written by hand.

### Cross-link direction — a deliberate one-way choice

The brief asked for a cross-link between the report and
`evidence/runs/T-6-evidence-execution-20260901T114021Z.json`. **I linked one way
only: report → manifest.** The manifest is a *record of an event*: it carries
per-input sha256 digests and is itself hashed by the freshness engine. Editing it
after the fact to add a back-pointer would change the record of something that
already happened, and would move its content hash. The validation report is the
derived, hand-recorded artefact, so it is the one that names its source. The
manifest is left byte-identical. If the reviewer wants a reciprocal pointer, it
should be a human decision about amending recorded evidence, not mine.

### RED (against `378c2a0`)

```
    def test_the_repositorys_validation_report_says_it_was_recorded_by_hand():
        raw = json.loads(report_path(factory_root()).read_text(encoding="utf-8"))
>       provenance = raw["provenance"]
E       KeyError: 'provenance'

    def test_load_validation_reports_nothing_for_a_provenance_less_report(tmp_path):
        ...
>       assert load_validation(tmp_path) == {}
E       AssertionError: assert {'SR-001': Sr..., error=None)} == {}
E         Left contains 1 more item:
E         {'SR-001': SrStatus(id='SR-001', state='passed', ...

    def test_a_corrupt_report_is_still_visible_to_the_navigator(tmp_path):
        ...
>       assert _validation_report_is_corrupt(tmp_path) is True
E       AssertionError: assert False is True
```

### GREEN

```
$ rtk proxy uv run pytest tests/unit/validation/ -q
........................................................................ [100%]
72 passed in 25.07s
```

### Blast radius, and why I absorbed it rather than reporting BLOCKED

Requiring provenance on load invalidated every test fixture that models a
validation report — 26 failures across 11 files on the first full run. I judged
this mechanical rather than structural: the new contract is "a validation report
declares its provenance", and a fixture that models a validation report should
model that too. Each fixture now carries a three-field
`{"recorded_by": "harness", ...}` block (a fixture stands in for harness output,
so it says so). Files touched:
`tests/unit/system/_fixtures.py` (the shared helper, which covers most of the
`tests/unit/system/` failures), `tests/unit/trace/test_validation_status.py`,
`tests/unit/coherence/test_health_dimensions.py`,
`tests/unit/coherence/policy/test_compiler.py`,
`tests/unit/coherence/test_audit_parallel.py`,
`tests/unit/coherence/test_staleness_routing.py`,
`tests/unit/system/test_vcycle_health.py`, and the two
`tests/integration/system/` fixtures.

One thing I deliberately did **not** do: I drafted the schema with
`dependentRequired` forcing a `passed` entry to carry `metric`/`assert`/
`trials`/`declared_trials`/`stale`, then removed it. It is a real tightening and
directly on point for `_entry_state`'s bare-truthy read — but it changes what
counts as a well-formed *entry*, not what the store says about its own origin,
and the brief scoped this schema to provenance and shape and told me not to
expand C2 on my own judgement. It is documented as an explicit non-goal in
`src/substrate/validation/model.py`'s docstring for whoever revisits
`_entry_state`.

---

## C3 — `human_review` satisfied by a decision that names nobody

### What changed

`_human_review_obligation` (`src/coherence/policy/compiler.py`) now also requires:

```python
attributed = bool(decision_file.decided_by.strip()) and _is_iso(decision_file.decided_at)
```

`_is_iso` is imported from `coherence.gate.model` — the repo's one ISO validator,
not a second copy.

Enforced at the obligation, **not** in the shared `validate_decisions`, exactly as
the brief allowed for: `validate_decisions` is used by every gate kind including
the `sr:` authoring-consent decisions already recorded on this branch, and
tightening it would retroactively invalidate them. Attribution is this
obligation's admissibility rule, so it lives at this obligation. `gate/model.py`
is unmodified.

The docstring was rewritten to state what the code actually proves. It used to
claim `reviewed` was `True` "only for an explicit human `accept`". It now says:
*the substrate cannot distinguish an agent-written decision from a human one;
nothing on disk carries proof of humanity, so no code here may claim to have
verified it. What it enforces is that the decision is attributed and timestamped
— it names a decider and says when — so a `satisfied` is always traceable to a
named party who can be asked, and a decision naming nobody is nobody's decision.*
The obligation's `reason` and `resolve_cmd` now name the two fields explicitly.

### RED (against `378c2a0`)

```
    def test_human_review_accept_naming_nobody_at_no_time_stays_open(tmp_path):
        """decided_at="" and decided_by="" with a single accept."""
        ...
>       assert hr.state == "open"
E       AssertionError: assert 'satisfied' == 'open'
E         - open
E         + satisfied

FAILED ...::test_human_review_accept_with_a_blank_decided_by_stays_open
FAILED ...::test_human_review_accept_with_a_whitespace_decided_by_stays_open
FAILED ...::test_human_review_accept_with_a_blank_decided_at_stays_open
FAILED ...::test_human_review_accept_with_a_non_iso_decided_at_stays_open
FAILED ...::test_human_review_accept_naming_nobody_at_no_time_stays_open
5 failed, 2 passed, 43 deselected in 1.37s
```

The 2 that passed are the positive controls (an attributed accept, and a
date-only `decided_at`) — deliberately included so the RED run shows the change
is a new requirement on attribution, not a new obstacle to a genuine review.

### GREEN

```
$ rtk proxy uv run pytest tests/unit/coherence/policy/ -q
..........................................s...........                   [100%]
53 passed, 1 skipped in 2.10s
```

No `DecisionFile` with an accept/reject/defer outcome was authored anywhere
outside a `tmp_path` fixture. The two deliberately-open human gates on this
branch are untouched.

---

## I1 — `except OSError: pass` on the validation-report write

`write_validation_report` now raises a new `ValidationReportWriteError(OSError)`
naming the path and saying the report on disk does not describe this run. There
is no honest "best effort" here: either the file is the report just produced, or
the caller must be told it is not.

RED — captured by temporarily restoring the old `except OSError: pass`:

```
>       with pytest.raises(ValidationReportWriteError) as excinfo:
E       Failed: DID NOT RAISE ValidationReportWriteError
FAILED tests/unit/validation/test_report.py::test_a_failed_report_write_is_raised_not_swallowed
1 failed, 8 deselected in 0.40s
```

The test also asserts the *previous* report is still on disk afterwards — which is
exactly why the caller must be told rather than proceeding.

---

## I2 — one bad dossier aborting `regenerate_all`

The per-node catch in `regenerate_all`/`check_all` is now unconditional
(`except Exception`), routed through one `_per_file_failure(node, exc)` that keeps
`MirrorFormatError`/`MirrorDivergenceError` messages verbatim and renders anything
else as `<path>: <ExcType>: <message>`. The catch is deliberately unconditional
rather than a hand-maintained tuple: the module docstring's promise is
unconditional, and a tuple would silently reacquire the same defect the first time
a dependency raised a type nobody had listed. Nothing is swallowed — every
exception becomes a reported per-file error.

RED — a `FEAT-*.md` with unparseable frontmatter still becomes a `feat` trace node
(node ids come from the filename), so `frontmatter.load` is reached:

```
E   yaml.scanner.ScannerError: while scanning a quoted scalar
E     in "<unicode string>", line 3, column 8
E   found unexpected end of stream
FAILED ...::test_a_dossier_with_unparseable_frontmatter_is_reported_and_the_run_continues
FAILED ...::test_check_all_reports_an_unparseable_dossier_and_keeps_checking
2 failed, 19 deselected in 1.28s
```

The first test seeds `FEAT-059` (good), `FEAT-060` (malformed), `FEAT-061` (good)
so the RED run demonstrates the half-regenerated tree specifically: `FEAT-059` was
written, then the exception escaped and `FEAT-061` was never processed.

---

## I3 — `coherence mirrors check` in no gate

Added to `.factory/factory.yaml`'s `full` gate:

```yaml
    - { cmd: "{python} -m coherence mirrors check" }
```

`python -m coherence` is a real entry point (`src/coherence/__main__.py`) and was
run to confirm before wiring. `tests/unit/test_factory_own_gates.py` gained a test
asserting the command is present, RED at `378c2a0`:

```
>       assert "{python} -m coherence mirrors check" in cmds
E       AssertionError: assert '{python} -m coherence mirrors check' in ['{python} -m ruff check .', '{python} -m pyright', '{python} -m pytest -m unit -q', '{python} scripts/gates/ext.py', '{python} scripts/gates/watch_ext.py']
```

**This has a consequence — see the risks section: it is what moved
`evidence_freshness` to 0/1.**

---

## I5 — `load_runs` skipping T-6's manifest

`load_runs` (`src/coherence/simulation/registry.py`) reads a run id from `run`
**or** `run_id`; the flat-file layout (`runs/<run_id>.json`) resolves to the real
path via a new `_manifest_path` instead of a phantom bundle path;
`commit`/`result`/`recorded_ts` fall back to `result_commit`/`outcome`/`ended_at`;
a v1 manifest declaring no experiment is the shape, not a scope error, while a
spec §20 bundle missing its experiment still reports one. Nothing is invented —
fields the v1 shape does not carry stay empty (in particular `requirements` is
*not* derived from `inputs.requirements`, which lists hashed input files, not
requirements the run validated).

The accommodation is entirely in the reader.
`evidence/runs/T-6-evidence-execution-20260901T114021Z.json` is untouched.

RED (against `378c2a0`, with the fix reverted and the fixtures final):

```
>       assert [r.run_id for r in runs] == ["T-6-evidence-execution-20260901T114021Z"]
E       AssertionError: assert [] == ['T-6-evidenc...0901T114021Z']
E         Right contains one more item: 'T-6-evidence-execution-20260901T114021Z'

>       assert len(load_runs(evidence)) == 2
E       AssertionError: assert 1 == 2
FAILED ...::test_load_runs_sees_a_v1_manifest_keyed_run_id
FAILED ...::test_both_manifest_shapes_load_side_by_side
```

Immediately after I5 and before I3, the dimension read **1/1** and it was a real
verdict, not a default: all ten of the run's recorded dependency digests matched.
Proven by probing, byte-preserving, against a real requirement file:

```
after edit: FreshnessState.STALE ['code:requirements/SR-002.md: changed since evidence']
restored:   FreshnessState.FRESH
```

---

## I7 / M5 — the inbox

**I7.** A new `_load_register_or_report(req_dir)` in `src/coherence/inbox.py`
returns `(requirements, [])` or `([], [one InboxItem])`. Both
`_stale_binding_items` **and** `_authoring_consent_items` use it. The brief named
only `_authoring_consent_items`, but `_stale_binding_items` calls `load_register`
unguarded too and runs *first* in `list_items`, so it would have raised before the
named site ever ran; fixing only the named one would have left the reported harm
in place.

The failure is reported, not swallowed. An unreadable register is not "no
requirements" (I-03), so it becomes a visible `register:unreadable` item carrying
the parser's own message and `coherence register check` as its resolve hint. Both
callers emit the same id and `list_items` de-duplicates by id, so the human sees
it exactly once.

RED:

```
E           ValueError: SR-900.md: acceptance: must be a list, got dict
src\coherence\register\register.py:86: ValueError
FAILED ...::test_a_malformed_acceptance_block_does_not_take_down_the_whole_inbox
FAILED ...::test_an_unreadable_register_is_reported_never_silently_dropped
```

**M5.** `assert "invalid" in item.summary or "stale" in item.summary` replaced.
The constructed case (a duplicate item id inside the `decisions` array) is
rejected by `validate_decisions` and deterministically yields the
invalid-DecisionFile summary. Note: I first wrote `assert "stale" not in summary`
as the complement and it failed — "stale" matches incidentally through pytest's
own tmp_path name (`...test_malformed_or_stale_sr_con0\gate-decisions\...`), which
is itself a small demonstration of why the original disjunction proved nothing.
The assertion is now on the exact reason: `"invalid DecisionFile"` and
`"duplicate item id"`.

---

## M1 — `_detect_eol`

I fixed the **docstring**, not the function, and said so in the docstring itself.
First-newline detection is deterministic, O(1), and cannot itself rewrite a file's
endings; true dominance (a majority vote) would, on a mixed-ending file, emit the
majority ending into a block whose neighbours use the other one — an unrequested
rewrite of exactly the kind this module exists not to do. Nothing requires
dominance and every dossier this generator touches is single-convention. The
module docstring's matching "dominant" claim was corrected too.

---

## M8 — T-8b's false premise

`docs/superpowers/plans/2026-09-01-feat001-first-vertical-slice.md`. The sentence
is struck through and annotated rather than deleted, so the record shows what was
believed and why it was wrong: FEAT-001 carries no `profile:` field and none is
configured, so every FEAT-001 SR resolves to `prototype`, under which
`human_review` compiles as `not_applicable` — which is why the dimension reads 0/0
rather than 0/8. The note records explicitly that declaring `high_assurance` would
flip `executed_evidence` from 4/55 to 0/55 and is a human's decision. No `profile:`
field was added to any dossier. What T-8b still asks for is preserved verbatim.

---

## Verification

### 1. `rtk proxy uv run pytest tests/unit/ -q`

```
FAILED tests/unit/system/test_remediation.py::test_every_shell_command_names_a_real_subparser
1 failed, 2988 passed, 13 skipped in 310.38s (0:05:10)
```

The one failure is the known pre-existing one named in the brief.

### 2. `rtk proxy uv run ruff check .`

```
All checks passed!
```

### 3. `rtk proxy uv run pyright <changed paths>`

Changed **sources**:

```
$ rtk proxy uv run pyright src/coherence/mirrors/generate.py src/coherence/policy/compiler.py \
    src/coherence/trace/validation_status.py src/coherence/navigate/queries.py \
    src/coherence/measurement/report.py src/coherence/measurement/cli.py \
    src/coherence/simulation/registry.py src/coherence/inbox.py src/substrate/validation/model.py
0 errors, 0 warnings, 0 informations
```

Changed **tests**: 28 errors, every one a pre-existing
`reportAttributeAccessIssue` against a deprecated `factory.*` shim that reassigns
`sys.modules` (`"load_runs" is unknown import symbol`,
`"vcycle_health" is not a known attribute of module "factory.system.health"`,
…), all on import lines and call sites I did not touch. Confirmed pre-existing by
running pyright on the same file set with my changes stashed: identical error
count.

Note for the record, not caused by this wave: the configured gate
(`pyright` over `include = ["src", "scripts"]`) reports **74 errors, 21 warnings**
and reported exactly the same 74/21 with all my changes stashed. The `full` gate's
pyright step is therefore already failing at `378c2a0`. Flagging, not fixing —
out of scope.

### 4. `rtk proxy uv run coherence mirrors check`

```
wikilink mirrors: 20 feature dossier(s) checked
0 divergent -- every mirror matches its frontmatter/trace-graph derivation
```

### 5. `rtk proxy uv run coherence register check`

```
51 pending, 0 unmeasurable, 4 measured-passing, 0 measured-failing, 0 declined (0 with no binding)
```

Still 4 measured-passing.

### 6. `rtk proxy uv run coherence navigate health --json`

| dimension | before | after |
|---|---|---|
| `requirement_quality` | 8/55 | **8/55** |
| `executed_evidence` | 4/55 | **4/55** |
| `evidence_freshness` | 0/0 | **0/1** |
| `human_review` | 0/0 | **0/0** |

Full dimension list after:

```
requirement_quality: 8/55        decomposition_allocation: 17/20
implementation_trace: 2/24       verification_strategy: 55/55
executed_evidence: 4/55          validation_scenarios: 0/55
evidence_freshness: 0/1          suspect_relationships: 55/55
nonconformance_closure: 1/1      deferrals_waivers: 57/173
human_review: 0/0
```

**`evidence_freshness` reads 0/1, and the "0" is a real verdict I caused.** The
causal chain, in order:

1. Before I5 the dimension was 0/0 — `freshness_universe` was empty because
   `load_runs` skipped the only recorded manifest. Nothing was measurable.
2. After I5 alone it read **1/1**: the T-6 run was in the universe and *verified
   fresh*, all ten recorded dependency digests matching.
3. I3 then edited `.factory/factory.yaml` to add the mirrors-check gate step. The
   T-6 manifest records `inputs.factory_config_sha256` and the freshness engine
   hashes that file as a dependency of the run. So the run is now genuinely stale:

```
state: FreshnessState.STALE
  - code:.factory/factory.yaml: changed since evidence
```

This is the substrate reporting a true fact, and it is the behaviour the fix
exists to enable — the same evidence was previously *unable* to be reported stale.
I did not touch the recorded manifest to make the number nicer: re-recording
evidence to clear a staleness signal an agent itself caused is the
self-certification I-01 forbids. **The remedy is a human re-running the T-6
evidence against the new config, and that decision is theirs.**

`human_review` stays 0/0 because every FEAT-001 SR resolves to `prototype`, under
which the obligation compiles `not_applicable` and is excluded from the
denominator — see M8. C3 changes what makes it `satisfied`, not whether it counts.

### 7. The two C1 reproductions, re-run against real files

Byte-preserving throughout; `FEAT-006` restored and verified byte-identical, `git
status` clean afterwards.

**Repro A — silent deletion.** A dossier whose section carries no sentinel yet and
which mentions the sentinel later in its own prose:

```
--- `coherence mirrors generate` stdout ---
wikilink mirrors: 21 feature dossier(s) processed
no changes -- every mirror already matched its derivation

1 could not be regenerated (left untouched):
  ! docs\features\FEAT-099.md: '<!-- end derived -->' appears outside the '## Related requirements'
    section, which itself carries none. This generator only ever owns a span inside that section, so
    the boundary is ambiguous and the file is left untouched. Remove or reword the out-of-section
    sentinel, then rerun `coherence mirrors generate`
exit code: 1
file byte-identical after generate : True
'## Design notes' still present    : True
hand-authored prose still present  : True
changed= False  error= docs\features\FEAT-099.md: '<!-- end derived -->' appears outside ...

--- `coherence mirrors check` ---
wikilink mirrors: 21 feature dossier(s) checked
1 divergent (the gate fails on these):

  ! docs\features\FEAT-099.md: '<!-- end derived -->' appears outside the '## Related requirements' ...
exit code: 1
```

Previously: the entire `## Design notes` section was deleted, no error,
`changed=True`, and the CLI printed `regenerated: FEAT-099`.

**Repro B — self-consistent duplication.** A stray sentinel inside the owned span
of the real `FEAT-006.md`:

```
--- check, with the stray sentinel in place ---
wikilink mirrors: 20 feature dossier(s) checked
1 divergent (the gate fails on these):

  ! docs\features\FEAT-006.md: the '## Related requirements' section contains 2 '<!-- end derived -->'
    lines; the generator-owned span has no unambiguous end. Delete the stray sentinel(s) so exactly
    one remains, then rerun `coherence mirrors generate`
exit code: 1

--- `coherence mirrors generate` ---
  ! docs\features\FEAT-006.md: the '## Related requirements' section contains 2 '<!-- end derived -->' ...
exit code: 1
file byte-identical after generate : True
end-sentinel count in file         : 2
derived-marker count in file       : 1

--- check again (this used to report 0 divergent forever) ---
wikilink mirrors: 20 feature dossier(s) checked
1 divergent (the gate fails on these):

  ! docs\features\FEAT-006.md: the '## Related requirements' section contains 2 '<!-- end derived -->' ...
exit code: 1

FEAT-006 restored byte-identical: True
final check: 0 divergent -- every mirror matches its frontmatter/trace-graph derivation
```

Previously: `generate` wrote the derived block twice, both fingerprinted and
sentinel-closed (`derived-marker count` would have been 2), after which `check`
reported `0 divergent` permanently.

---

## Self-review

### C1 — a shape my fix does *not* handle

`_section_end` is a lexical `^## ` scan with **no fenced-code-block awareness**.
A dossier whose `## Related requirements` section contains a fenced block with a
`## ` line inside it — e.g. a markdown example — will have its section truncated
at that line.

What happens then: if the real sentinel lies after the fence, it reads as
out-of-section and the file raises `MirrorFormatError`, is left byte-for-byte
untouched, and is named by `check` and `generate`. If the fence sits after the
sentinel, there is no effect at all. So the unhandled shape degrades to a *false
positive error*, never a silent rewrite. No real dossier has this shape (all 20
pass `mirrors check`), and the escape hatch is the same for every other error
here: the message names the file and the repair.

Two more shapes worth naming, both fail-closed:

* A sentinel appearing *before* the heading with none in the section is treated as
  out-of-section and errors, even though the bootstrap fallback would have been
  correct. Over-strict; reported, never silent.
* Two `## Related requirements` headings: the first wins, the second terminates
  the section, and anything under the second is preserved but never regenerated —
  and a sentinel under it errors.

Has the defect moved? No. Both harms were *silent*; every replacement path is a
named, per-file, file-untouched error. The one behaviour that got stricter
(bootstrap now refuses when a sentinel exists anywhere else) trades a
correct-but-lucky rewrite for a reported refusal, which is the direction this
codebase's doctrine points.

### C3 — is there any remaining path to `satisfied` without an attributed decision?

`_human_review_obligation` at `src/coherence/policy/compiler.py:316` is the **only**
producer of a `review:<sr_id>` obligation state in `src/` (verified by grep;
`factory/orchestrator/human_review.py` is the separate interactive orchestrator
gate, a different mechanism, and does not feed this obligation). Within it:

* `sr_path is None`, `expected_artifact_ref is None`, `path` not a file,
  `CorruptDecisionFile` — all leave `reviewed = False`.
* The satisfied branch is one boolean conjunction and `attributed` is a term in
  it. There is no early return, no default-True, and no other assignment to
  `reviewed`.
* `decided_by` is compared after `.strip()`, so whitespace does not pass.
  `decided_at` goes through `gate/model.py`'s `_is_iso`, which rejects blank and
  free-form strings and validates the date semantically.

So no. What the fix does **not** and cannot do is prove the decider is human —
and the docstring now says exactly that rather than implying otherwise.

### C2 — has the defect moved?

Partly, and I want this on the record. What is fixed: the file is no longer
un-labelled, no longer un-schema-checked, and can no longer be read at all if its
shape is wrong. What remains: `_entry_state` still returns `"passed"` from a bare
truthy `passed` key, and the schema does not (see above) force that key to be
accompanied by its measurement. A future hand-authored report could still assert
`passed: true` with no `metric` — it would just have to say `recorded_by: "hand"`
and cite a run while doing it. That is a smaller hole than the one that was there,
and it is now labelled, but it is not closed.

---

## New risks introduced

1. **`evidence_freshness` is 0/1 because of my own I3 change.** Detailed above.
   True verdict, caused by editing `.factory/factory.yaml`, which the T-6 manifest
   fingerprinted. Any future edit to that file re-stales the recorded run. A human
   must decide whether to re-record the evidence.
2. **A legacy validation report in a downstream repo now reads as empty.**
   `load_validation` returns `{}` for a report without provenance. In the
   navigator (`brief`/`matrix`/`guide`) this surfaces as DEGRADED via
   `_validation_report_is_corrupt`. But `health.py`, `graph.py`,
   `navigate/feature.py` and `policy/compiler.py` call `load_validation`
   directly and see only `{}` — so in a repo carrying a pre-schema report,
   `executed_evidence` would silently drop toward 0 with the reason visible only
   through the navigator. It is fail-closed (nothing looks green that should not),
   which is the right direction, but the *reason* is not reported on every
   surface. Closing that would mean threading a corruption signal through those
   four call sites — a change bigger than this finding, so I stopped.
3. **`except Exception` in the mirrors loop (I2).** A genuine bug in
   `regenerate_file` now surfaces as a per-file error line rather than a crash.
   Deliberate — the docstring's promise is unconditional — but it does make a
   programming error look like a data error. `_per_file_failure` prefixes the
   exception type into the message so the two are still distinguishable in the
   output.
4. **`ValidationReportWriteError` is a new raise on a path that never raised.**
   `cmd_validate` and anything calling it will now propagate a write failure.
   That is the point, but it is a behaviour change for callers that assumed the
   call could not fail. `factory.validation.report` re-exports the canonical
   module, so the new symbol is available through the shim too.
5. **`load_runs` now returns v1 orchestration manifests.** Consumers that assumed
   every `Run` is a §20 simulation bundle will now see runs with an empty
   `experiment` and no feature/requirements/goals. `runs_for(feature=…)` and
   `latest_run` are unaffected (v1 manifests have `feature=None`), and the whole
   unit suite is green, but a consumer filtering on `experiment=""` would now
   match them.

## Not fixed

Nothing from the brief's fix list. The explicitly out-of-scope items (I4, I6,
M2/M3/M4/M6/M7, `verification_strategy`'s 55/55 tautology) were not touched, no
gate `DecisionFile` was authored outside `tmp_path`, no `profile:` field was
added, no `requirements/SR-*.md` acceptance block or `@pytest.mark.sr` decorator
was modified, and `docs/superpowers/plans/2026-09-01-feat001-reference-run.md` was
not edited.
