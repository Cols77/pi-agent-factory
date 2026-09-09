# Planning cross-artifact evidence

The FEAT-017 `v1` planning pack requires `cross-artifact-review-current` before
handoff. Its run-local record is `.factory/planning/<run-id>/cross-artifact-review.json`.
Missing, malformed, changed, or blocking evidence fails the gate. Older gate
results must be regenerated because the compiled pack digest includes this gate.

After producing a current `report.json`, the producer records its explicit task
classification through the Python API:

```python
from pathlib import Path
from coherence.planning.gates import write_cross_artifact_review
from coherence.planning.review import GeneratedTaskReviewInput

write_cross_artifact_review(Path("."), "run-001", {
    "tasks/T-001-example.md": GeneratedTaskReviewInput(
        id="T-001",
        artifact_paths=("src/example.py", "tests/test_example.py"),
        changes_production=True,
        changes_validation=True,
        affected_srs=("SR-001",),
        satisfies=None,
    ),
})
```

Every canonical `tasks/T-*.md` file must appear in both the report and this
mapping. The existing ledger parser validates task records and supplies any
`satisfies`/`justification` mirror; the supplied `satisfies` value must match it
when present. A task without either mirror uses `None`. The producer owns
`artifact_paths`, both classification booleans, and `affected_srs`; paths are
never used to infer a docs-only classification. Production or validation tasks
require a nonempty, sorted, unique affected-SR declaration. Explicit docs-only
tasks use both booleans `False` and remain exempt. A run with no generated tasks
must explicitly record an empty mapping.

The record contains schema/run identity, the report digest, typed task inputs,
hashes of current report/task/affected-requirement/relation files, and the pure
reviewer's findings. The writer records blocking findings for inspection too;
writing a record does not mean it passed. The planning gate recomputes and
compares this entire record, preserving the missing, dangling, duplicate, weak,
overstated, and contradictory relation findings. Handoff creation and validation
revalidate the gate and all its evidence. Refresh the record after changing an
input, then use `coherence plan run-planning-gates --run-id <run-id> --json`.

This boundary does not run implementation gates, launch processes, classify
artifacts, grant consent, or supply a semantic review. Those facts remain with
their existing owners.
