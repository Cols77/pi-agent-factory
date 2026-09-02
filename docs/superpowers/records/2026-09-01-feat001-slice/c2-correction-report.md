# Correction: false human-attribution claim in validation-report provenance

## The problem, restated

A prior fix wave added a `provenance` block to `validation/validation-report.json`
to close the honest finding that the report's entries had no stated origin.
The mechanism (a schema-validated provenance block with a two-value
`recorded_by` enum, `hand`/`harness`) is sound and stays. Its *content* was
false: it claimed `recorded_by: "hand"` and a note saying "a human ran the
command... and transcribed the per-SR results here." No human ran anything.
An agent ran `rtk proxy uv run pytest -m sr -v -o addopts=""`, read the
output, and transcribed the per-SR results. Both human gates
(`authoring_consent`, `human_review`) are still open on this branch, which is
independently visible in `evidence/runs/T-6-evidence-execution-20260901T114021Z.json`
as `"reviews": []` and `"decisions": []`.

The root cause was a closed two-value vocabulary (`hand`/`harness`) that had
no honest value for "an AI agent ran this and transcribed the output" — the
common case for a substrate built for agentic engineering, not an edge case.

## Vocabulary choice

**Added a third enum value, `agent`, to `recorded_by`.** Rejected the
alternative (an `actor` free-text field plus a `computed: bool` flag) because:

- The existing schema is a closed enum precisely to keep `recorded_by`
  answerable in one lookup by every reader (`load_validation`, the
  `if`/`then` conditional, this test file, a future human skimming the
  file). A third enum value keeps that property; splitting the field into
  two would change every reader's shape for no benefit here — the *shape* of
  "harness vs. hand vs. agent" is already exactly three closed cases, not an
  open-ended actor space.
- `evidence_record.schema.json`'s free-text `recorded_by` (used by
  `src/factory/evidence/records.py:160` for agent/session identities)
  answers a different question — *which* actor, by durable identity, for an
  append-only evidence record. This schema's `recorded_by` answers a
  narrower question — *what kind* of actor, for the specific purpose of
  triggering the citation requirement (`run_id`/`evidence_manifest`/`commit`/
  `note`) whenever a human did not independently attest to the numbers. A
  closed enum is the right shape for that question; free text would let a
  typo silently fail to trigger the citation requirement, exactly the
  failure mode the `if`/`then` exists to prevent.
- `agent` is honest and unambiguous: "a non-human (AI) actor ran the command,
  read its output, and transcribed the results; no human has attested to
  them." It says exactly what happened without overstating (not `harness`,
  since no code emitted these values) or understating (not `hand`, since no
  human was involved) human involvement.

## The four sites, corrected

1. **`validation/validation-report.json` — `provenance.recorded_by`**: changed
   from `"hand"` to `"agent"`.

2. **`validation/validation-report.json` — `provenance.note`**: rewritten to
   say an agent ran the command and transcribed the results; that no human
   has reviewed or attested to them; that the `authoring_consent` and
   `human_review` gates for these requirements are both still open; and that
   the evidence manifest it cites records no `reviews` and no `decisions`.
   Kept: the explanation of why no code in this repo can emit these entries
   (every FEAT-001 SR is binding-less), the cross-link to
   `evidence_manifest`, and the reproduction command. Full text below.

3. **`src/substrate/schemas/validation_report.schema.json` —
   `$defs.provenance.properties.recorded_by`**: enum extended to
   `["hand", "harness", "agent"]`; description corrected so each value is
   true: `harness` = emitted by code in this repository; `hand` = a human ran
   the command, read its output, and transcribed the results; `agent` = a
   non-human (AI) actor did the same, and no human has attested to them.

4. **`src/substrate/schemas/validation_report.schema.json` — top-level
   `description`**: "when a human transcribed it rather than a harness
   emitting it" corrected to "when anything other than a harness emitted it"
   — matching the generalised trigger (see below).

5. **`tests/unit/validation/test_validation_report_schema.py`** —
   `test_the_repositorys_validation_report_says_it_was_recorded_by_hand`
   renamed to
   `test_the_repositorys_validation_report_says_it_was_recorded_by_an_agent`
   and retargeted to assert `recorded_by == "agent"` and that the note does
   not (falsely) claim human attribution. It also asserts the invariant
   worth having going forward: if `recorded_by` is ever `"hand"`, the cited
   evidence manifest's `decisions` list must be non-empty (a real human
   decision must back a human-attribution claim); otherwise (the `agent`
   case, matching current reality) the manifest's `decisions` list must be
   `[]`. This makes the test fail on a future false "hand" claim, not just
   pin today's string.

## Schema `if`/`then` — generalised, not weakened

The conditional requiring `run_id`, `evidence_manifest`, `commit`, `note` now
fires on `recorded_by` being anything other than `"harness"` (previously:
only on `"hand"`):

```json
"if": {
  "properties": {"recorded_by": {"not": {"const": "harness"}}},
  "required": ["recorded_by"]
},
"then": {
  "required": ["run_id", "evidence_manifest", "commit", "note"]
}
```

So an `agent`-recorded report carries the same citation burden a
`hand`-recorded one always did. `test_a_hand_recorded_report_must_cite_a_run_and_a_manifest`
and `test_a_harness_emitted_report_need_not_cite_a_run` (both pre-existing,
untouched) continue to pass and continue to exercise this conditional.

`src/substrate/validation/model.py`'s docstring (touched, per the allowed
scope, because it directly documents this behaviour) was updated from "a
`recorded_by: hand` report must cite..." to "any non-`harness` `recorded_by`
value (`hand` or `agent`) must cite...".

No change was needed in `src/coherence/trace/validation_status.py`: it
validates generically via `validation_report_errors`/the JSON Schema and
carries no hardcoded enum logic, so it needed no edit.

## Per-SR entries: unchanged

`git diff validation/validation-report.json` touches exactly two lines
(`recorded_by` and `note`, both inside `provenance`). Every `requirements[]`
entry — `id`, `error`, `metric`, `assert`, `trials`, `declared_trials`,
`passed`, `stale`, `artifacts` — is byte-identical to before this change.

## RED

Ran the retargeted test before implementing:

```
$ rtk proxy uv run pytest tests/unit/validation/test_validation_report_schema.py -q -k recorded_by_an_agent
F
AssertionError: assert 'hand' == 'agent'
  - agent
  + hand
tests\unit\validation\test_validation_report_schema.py:83: AssertionError
1 failed, 12 deselected, 2 warnings in 0.81s
```

A real assertion failure on the (still-`"hand"`) repository content, not an
`ImportError` — the test, schema and loader all imported cleanly; only the
value asserted was wrong.

## GREEN

```
$ rtk proxy uv run pytest tests/unit/validation/test_validation_report_schema.py -v
...
====================== 13 passed, 11 warnings in 25.62s =======================
```

## Verification commands and output

1. `rtk proxy uv run pytest tests/unit/validation/ tests/unit/trace/ -q`
   → `206 passed, 31 warnings in 8.73s`

2. `rtk proxy uv run pytest tests/unit/ -q` (full suite, foregrounded, ~9m)
   → `1 failed, 2988 passed, 13 skipped, 113 warnings in 562.80s (0:09:22)`
   The one failure is the pre-existing, known one:
   `tests/unit/system/test_remediation.py::test_every_shell_command_names_a_real_subparser`
   (missing `add_parser("run")` in the deprecated `coherence.measurement.cli`
   shim) — unrelated to this change, not introduced by it.

3. `rtk proxy uv run ruff check .`
   → `All checks passed!`

4. `rtk proxy uv run coherence navigate health --json`
   → `executed_evidence`: `{"satisfied": 4, "expected": 55, "exempt": 0}` —
   **unchanged at 4/55**, as required (the correction is to attribution, not
   to what is reported passing).

5. Corrected `provenance` block in full:

```json
{
  "recorded_by": "agent",
  "recorded_at": "2026-09-01T11:40:28Z",
  "command": "rtk proxy uv run pytest -m sr -v -o addopts=\"\"",
  "run_id": "T-6-evidence-execution-20260901T114021Z",
  "evidence_manifest": "evidence/runs/T-6-evidence-execution-20260901T114021Z.json",
  "commit": "44d585a5a0898ed52b8aa296b387cac3c948120b",
  "note": "Recorded by an agent, not emitted by a harness and not attested by a human. No code in this repository can produce these entries: every FEAT-001 SR is binding-less, and coherence.measurement.report.run_requirement_validation returns {'id': ..., 'error': 'proposed requirement: no binding to validate'} and exits before measuring for a binding-less SR. An agent ran the command above, read its output, and transcribed the per-SR results here; the `metric`/`assert`/`trials`/`declared_trials`/`stale` fields are that agent's transcription of what the run showed, not values any code computed and not values any human has reviewed. No human has acted on this branch: the `authoring_consent` and `human_review` gates for these requirements are both still open, and the evidence manifest this note cites records no `reviews` and no `decisions`. The run itself is recorded in `evidence_manifest`, which carries the run id, the commit and the per-SR file hashes for the same event; these two files are the only record of it. Reproduce with the command above: it selects the @pytest.mark.sr tests named in each entry's `artifacts`."
}
```

## Self-review

Read the corrected note and schema descriptions as a stranger: no sentence
claims or implies a human saw this evidence. `grep -i human` over the diff
shows every remaining occurrence is either (a) part of the abstract, still-
true definition of what `hand` *would* mean if it were ever used (a human
ran the command and transcribed the results) or (b) an explicit statement
that *no* human was involved / attested / acted on this branch. None asserts
that a human was involved in producing this report.

## Scope discipline

Touched only: `validation/validation-report.json`,
`src/substrate/schemas/validation_report.schema.json`,
`tests/unit/validation/test_validation_report_schema.py`, and
`src/substrate/validation/model.py` (docstring only, to keep its prose
description of the `if`/`then` trigger accurate after generalising it — no
behavioural change). `src/coherence/trace/validation_status.py` needed no
edit. No other finding was reopened; no `docs/` file, no
`.factory/factory.yaml`, no `src/coherence/mirrors/`,
`src/coherence/policy/compiler.py`, `src/coherence/inbox.py`,
`src/coherence/simulation/registry.py`, or
`src/coherence/measurement/report.py` was touched.
`evidence/runs/T-6-evidence-execution-20260901T114021Z.json` was not
modified (verified byte-identical via `git status` — not listed as changed).
No gate `DecisionFile` was authored outside a `tmp_path` fixture. No
`profile:` field was added to any feature dossier.
