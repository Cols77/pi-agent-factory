# Freshness, Preflight, and Reconciliation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Detect canonical-integrity defects and stale task evidence deterministically, fail before expensive work when appropriate, and report out-of-band changes without inventing provenance.

**Architecture:** Add a generic named-dependency fingerprint model over canonical files, Git trees, configuration, and producer versions. A preflight engine applies fixed severity policy at run start and completion; reconciliation compares repository/evidence/run state and exposes read-only JSON plus narrowly bounded deterministic repairs.

**Tech Stack:** Python 3.11+, hashlib, Git subprocesses, existing trace/requirements/evidence models, argparse, pytest.

## Global Constraints

- Freshness is based on content hashes and versions, never mtime.
- A stale disposable index is rebuilt, never treated as an integrity failure.
- Integrity failures cannot be overridden.
- Task-scoped missing/failed/stale mandatory evidence blocks completion.
- Unrelated stale evidence is warning-only.
- Reconciliation never attributes a change to a task automatically.
- `--repair` performs only deterministic rebuild, retry, or explicit-provenance migration.

---

## File Structure

**Create:**
- `src/factory/freshness/model.py` — fingerprints, dependencies, issues, reports.
- `src/factory/freshness/fingerprint.py` — canonical file/tree/config hashing.
- `src/factory/freshness/evaluate.py` — compare recorded and current dependencies.
- `src/factory/preflight/checks.py` — start/completion policy.
- `src/factory/preflight/cli.py`, `src/factory/preflight/__main__.py`.
- `src/factory/evidence/reconcile.py` — discrepancy inventory and repair routing.
- tests under `tests/unit/freshness/`, `tests/unit/preflight/`, and `tests/unit/evidence/test_reconcile.py`.

**Modify:**
- `src/factory/evidence/finalize.py` — record generic named dependencies.
- `src/factory/orchestrator/runner.py` and `__main__.py` — invoke start/completion preflight.
- `src/factory/evidence/cli.py` — add `reconcile`.
- `scripts/gates/all.py` or project gate registration — CI reconciliation check.

### Task 1: Generic fingerprint model

**Interfaces:**

```python
@dataclass(frozen=True)
class DependencyFingerprint:
    name: str
    kind: str  # file|git-tree|value|tool
    digest: str
    source: str

class FreshnessSeverity(str, Enum):
    INTEGRITY = "integrity"
    BLOCKING = "blocking"
    WARNING = "warning"

@dataclass(frozen=True)
class FreshnessIssue:
    code: str
    severity: FreshnessSeverity
    subject: str
    dependency: str
    expected: str | None
    actual: str | None
    detail: str
    repair: str | None

@dataclass(frozen=True)
class FreshnessReport:
    issues: list[FreshnessIssue]
    @property
    def ok(self) -> bool: ...
```

- [ ] Test deterministic file hashing, absent-file fingerprint, value/tool hashing, and Git tree fingerprint independent of mtime.
- [ ] Implement `sha256_bytes`, `fingerprint_file`, `fingerprint_value`, and `fingerprint_git_tree` in `fingerprint.py`.
- [ ] Test `compare_dependencies(recorded, current, subject, severity_for)` yields exact changed/missing reasons.
- [ ] Implement model/evaluator and JSON serialization helpers.
- [ ] Run tests/static checks and commit `feat(freshness): add dependency fingerprints`.

### Task 2: Record complete evidence dependencies

The run manifest `inputs.dependencies` becomes a sorted list of
`DependencyFingerprint` dictionaries. Record:

- task file;
- every declared satisfying requirement file;
- source plan/spec paths declared through trace edges;
- `.factory/factory.yaml`;
- code candidate tree;
- evidence schema version;
- validator/harness identity for each validation entry.

- [ ] Add finalizer fixture test asserting exact dependency names and stable ordering.
- [ ] Implement dependency gathering by consuming the existing trace graph rather than inferring filenames.
- [ ] Preserve top-level compatibility fields from evidence-manifest schema version 1; add dependencies as an optional then required schema field in version 2 with a migration reader for version 1.
- [ ] Add migration test and commit `feat(evidence): record freshness dependencies`.

### Task 3: Start-time preflight

**Interfaces:**

```python
class PreflightPhase(str, Enum):
    START = "start"
    COMPLETE = "complete"


def run_preflight(repo_root: Path, task_id: str, phase: PreflightPhase, *, candidate_tree: str | None = None) -> FreshnessReport: ...
```

Start checks:

- task parser succeeds and IDs are unique;
- selected task exists;
- declared requirement IDs exist;
- declared source plan/spec references resolve through the trace model;
- `.factory/factory.yaml` loads and required gates exist;
- Git baseline resolves;
- active/dead run checkpoint is compatible or explicitly abandoned;
- evidence manifests needed for resume validate.

Severity is `integrity` for malformed/duplicate/missing canonical references and
corrupt resume evidence; an unrelated trace gap is `warning`.

- [ ] Build fixtures for each issue and a clean repository.
- [ ] Assert no model/backend call occurs when start preflight has an integrity issue.
- [ ] Implement checks by composing existing parsers (`load_tasks`, trace graph, `load_config`, recovery assessment), not duplicating their rules.
- [ ] Add CLI:

```text
python -m factory.preflight --repo . --task T-042 --phase start --json
```

Exit `0` clean/warnings, `2` blocking, `3` integrity.
- [ ] Run tests and commit `feat(factory): fail early on project integrity defects`.

### Task 4: Completion preflight and override evidence

Completion checks:

- candidate-tree dependency equals latest task-scoped validation evidence;
- every task `satisfies` requirement has a current non-failed validation entry unless binding is explicitly proposed/unvalidatable under existing requirement policy;
- review evidence persisted for interactive runs;
- no unresolved `must-fix` annotation in the final review state;
- implementation manifest can be validated and every required blob exists.

**Interfaces:**

```python
@dataclass(frozen=True)
class Override:
    issue_codes: list[str]
    reason: str
    actor: str
    at: str


def apply_override(report: FreshnessReport, override: Override) -> FreshnessReport: ...
```

`apply_override` rejects integrity issues, blank reasons, unknown issue codes, and
issues not configured as overridable. Accepted override is stored in run evidence.

- [ ] Test current/stale/missing/failed validation and unresolved/resolved annotations.
- [ ] Test overrides, including integrity refusal.
- [ ] Invoke completion preflight before final code commit/evidence finalization; blocked runs return to human review or escalate with exact issues rather than marking done.
- [ ] Add `--override CODE --reason ... --actor ...` to explicit CLI resume/completion path, not ordinary autonomous execution.
- [ ] Commit `feat(factory): gate completion on current task evidence`.

### Task 5: Read-only reconciliation inventory

**Interfaces:**

```python
class ReconcileKind(str, Enum):
    MISSING_EVIDENCE = "missing_evidence"
    UNRESOLVED_COMMIT = "unresolved_commit"
    UNATTRIBUTED_CHANGE = "unattributed_change"
    STALE_VALIDATION = "stale_validation"
    MISSING_BLOB = "missing_blob"
    PUBLICATION_FAILED = "publication_failed"
    INTERRUPTED_RUN = "interrupted_run"
    LEGACY_REVIEW = "legacy_review"

@dataclass(frozen=True)
class ReconcileItem:
    kind: ReconcileKind
    subject: str
    detail: str
    repairable: bool
    source: str


def reconcile(repo_root: Path, task_id: str | None = None) -> list[ReconcileItem]: ...
```

Attribution rules:

- a code commit is attributed only if a validated evidence manifest names it;
- current working-tree changes are attributed only to a compatible active run;
- task completion with no evidence is missing evidence, never assigned the nearest commit;
- legacy review is repairable only when its JSON already includes task/run/start commit.

- [ ] Create a Git/evidence fixture for every kind and assert deterministic ordering `(kind, subject, source)`.
- [ ] Implement inventory using manifest repository, artifact store, run journals, task ledger, and Git reachability.
- [ ] Add `factory.evidence reconcile [--task] --json`; pending inventory returns `1`, clean returns `0`, operational error returns `2`.
- [ ] Commit `feat(evidence): reconcile repository and run evidence`.

### Task 6: Deterministic repairs and CI gate

Allowed repairs:

- retry publication of a known hash;
- rebuild a disposable index;
- migrate an explicit legacy review into its already-identified run manifest;
- mark a dead run abandoned only with supplied reason.

No repair may create task attribution, requirement links, or design rationale.

- [ ] Test each allowed repair and test refusal of `UNATTRIBUTED_CHANGE` and `MISSING_EVIDENCE` without explicit provenance.
- [ ] Add `--repair`, `--reason`, and idempotency tests.
- [ ] Add a CI/gate command that fails only on integrity/blocking reconciliation items; warnings remain visible but non-zero only under an optional strict flag.
- [ ] Run full Python gates and commit `feat(evidence): repair and gate evidence health`.

## Plan Self-review

- Covers content freshness, start/completion policy, explicit override, reconciliation, bounded repair, and CI integration.
- Reuses canonical parsers and trace declarations; it does not create a parallel rule set.
- No generated cache can block the run.
- Browser/API presentation is left to the integration plan.
