# SR-050 T3 relation-maintenance obligation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An implementation task that changes production/validation code and fails to declare the
change via one of its own `satisfies` SRs' `implemented_by`/`verified_by` relations cannot
complete a live orchestrator run — it is blocked (escalated back to `todo`), not merely flagged in
an advisory dashboard count.

**Architecture:** One new `coherence.policy.compiler` Obligation kind
(`relation_maintenance`, `task:*` scope) reconciles a task's own `satisfies` SRs' declared
relations against a caller-supplied list of changed files, filtered to real source/test code via a
new `substrate.codemap.build.is_source_path` helper. `factory.preflight.checks.
run_completion_preflight` — the function the live orchestrator (`factory/orchestrator/runner.py`)
already consults to decide whether a completed run's outcome stands — calls this obligation and
surfaces an open result as a new `BLOCKING` issue. The runner supplies the changed-files list via
the same `GitOps.changed_files` call the eventual evidence manifest uses.

**Tech Stack:** Python 3.12, pytest, existing `coherence`/`substrate`/`factory` layering.

**Spec:** [docs/superpowers/specs/2026-09-04-sr050-t3-relation-maintenance-design.md](../specs/2026-09-04-sr050-t3-relation-maintenance-design.md)

## Global Constraints

- `coherence.register.*` and `coherence.policy.*` may never import `factory.*` (statically enforced
  by `tests/unit/requirements/test_coherence_parity.py`) — every import in this plan respects that
  direction; `factory.preflight.checks`/`factory.orchestrator.runner` importing `coherence.*` is
  the already-established, opposite-and-legal direction.
- Every new/changed function signature is backward compatible: existing callers of
  `compile_obligations` and `run_completion_preflight` that pass no new keyword argument must see
  identical behavior to today (the new obligation reports `not_applicable`, the new check never
  fires).
- Use `rtk proxy uv run pytest ...` / `rtk proxy uv run ruff check ...` for every verification
  command in this plan — the shortened `rtk proxy pytest ...` (dropping `uv run`) silently resolves
  to the wrong Python and produces `ModuleNotFoundError` on every test.
- This plan does not touch `validation_missing`/`validation_failed`/`validation_stale`/
  `review_missing`/`must_fix_unresolved` in `factory/preflight/checks.py` — tracked separately as
  [[SR-063]]. Do not "helpfully" unify them while in this file.

---

### Task 1: `is_source_path` — the shared source/test-file classifier

**Files:**
- Modify: `src/substrate/codemap/build.py`
- Test: `tests/unit/codeindex/test_codeindex.py`

**Interfaces:**
- Produces: `is_source_path(repo_root: Path, rel_path: str, *, source_dirs: list[str] | None = None) -> bool`, importable as `from substrate.codemap.build import is_source_path`. Consumed by Task 2.

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/codeindex/test_codeindex.py` (append near the other `discover_source_files`
tests, e.g. after `test_discover_source_files_skips_vendor_dirs`):

```python
from substrate.codemap.build import is_source_path


def test_is_source_path_true_under_default_src_fallback(tmp_path):
    (tmp_path / "src").mkdir()
    assert is_source_path(tmp_path, "src/coherence/foo.py") is True


def test_is_source_path_false_outside_every_source_dir(tmp_path):
    (tmp_path / "src").mkdir()
    assert is_source_path(tmp_path, "requirements/SR-001.md") is False
    assert is_source_path(tmp_path, "tasks/T-001.md") is False


def test_is_source_path_false_for_non_code_extension(tmp_path):
    (tmp_path / "src").mkdir()
    assert is_source_path(tmp_path, "src/coherence/notes.txt") is False


def test_is_source_path_false_inside_skip_dir(tmp_path):
    (tmp_path / "src").mkdir()
    assert is_source_path(tmp_path, "src/vendor/node_modules/pkg/index.js") is False


def test_is_source_path_false_for_absolute_or_parent_escaping(tmp_path):
    (tmp_path / "src").mkdir()
    assert is_source_path(tmp_path, "/etc/passwd") is False
    assert is_source_path(tmp_path, "../outside.py") is False


def test_is_source_path_does_not_require_the_file_to_exist(tmp_path):
    # A git-diff-reported deletion still classifies correctly -- this is a
    # pure path classifier, unlike discover_source_files's filesystem walk.
    (tmp_path / "src").mkdir()
    assert is_source_path(tmp_path, "src/coherence/deleted_module.py") is True


def test_is_source_path_respects_explicit_source_dirs_override(tmp_path):
    assert is_source_path(tmp_path, "scripts/tool.py", source_dirs=["scripts"]) is True
    assert is_source_path(tmp_path, "src/coherence/foo.py", source_dirs=["scripts"]) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `rtk proxy uv run pytest tests/unit/codeindex/test_codeindex.py -k is_source_path -v`
Expected: FAIL with `ImportError: cannot import name 'is_source_path'`

- [ ] **Step 3: Implement `is_source_path`**

In `src/substrate/codemap/build.py`, add near `discover_source_files` (after its definition, before
`profile_source_dirs`):

```python
from pathlib import PurePosixPath


def is_source_path(
    repo_root: Path, rel_path: str, *, source_dirs: list[str] | None = None,
) -> bool:
    """True when `rel_path` (a repository-relative path, native or POSIX
    separators) is real production/validation source code by this repo's own
    code-map convention: inside a configured source directory
    (`profile_source_dirs`, falling back to `["src"]` exactly like
    `discover_source_files`), not inside a `_SKIP_DIRS` segment
    (vendored/build output), with a `_CODE_EXTS` extension.

    A pure path classifier -- unlike `discover_source_files`, it never
    touches the filesystem and does not require the file to currently exist,
    so it also correctly classifies a path a git diff reports as deleted.
    SR-050 T3's relation-maintenance obligation is the first caller; treat
    this as the one shared classifier for "is this changed path real
    project code" rather than adding a second one.
    """
    candidate = PurePosixPath(rel_path.replace("\\", "/"))
    if candidate.is_absolute() or ".." in candidate.parts:
        return False
    if any(part in _SKIP_DIRS for part in candidate.parts):
        return False
    if candidate.suffix.lower() not in _CODE_EXTS:
        return False
    dirs = source_dirs or _profile_source_dirs(repo_root) or ["src"]
    return any(
        candidate == PurePosixPath(d) or PurePosixPath(d) in candidate.parents
        for d in dirs
    )
```

Note: `repo_root` is accepted (and required, matching `discover_source_files`'s own signature) even
though this function never reads the filesystem directly itself — it is forwarded to
`_profile_source_dirs(repo_root)`, which does.

- [ ] **Step 4: Run tests to verify they pass**

Run: `rtk proxy uv run pytest tests/unit/codeindex/test_codeindex.py -v`
Expected: PASS (all tests in the file, not just the new ones — confirms no regression)

- [ ] **Step 5: Lint and commit**

Run: `rtk proxy uv run ruff check src/substrate/codemap/build.py tests/unit/codeindex/test_codeindex.py`

```bash
git add src/substrate/codemap/build.py tests/unit/codeindex/test_codeindex.py
git commit -m "feat(codemap): add is_source_path, the shared changed-file source classifier"
```

---

### Task 2: `relation_maintenance` Obligation

**Files:**
- Modify: `src/coherence/policy/compiler.py`
- Test: `tests/unit/coherence/policy/test_compiler.py`

**Interfaces:**
- Consumes: `is_source_path(repo_root, rel_path, *, source_dirs=None) -> bool` (Task 1);
  `substrate.ledger.tasks.get_task`/`load_tasks`; `coherence.register.register.load_register`;
  `coherence.register.review._raw_meta(req) -> dict`, `coherence.register.review._declared_paths(meta, field) -> set[str]` (both already exist, reused directly — not copied — matching this file's existing style of reaching into `coherence.register.*` submodules for exactly what each obligation needs, e.g. `_test_marker_obligation`'s `coherence.register.markers` import).
- Produces: `compile_obligations(root, scope_ref="project", *, nodes=None, edges=None, changed_files=None) -> list[Obligation]` grows the new `changed_files` keyword-only parameter (default `None`, backward compatible). A compiled `task:*` scope now includes one more `Obligation` with `kind="relation_maintenance"`. Consumed by Task 3.

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/coherence/policy/test_compiler.py`. First, check the file's existing fixture
helpers for writing a task file and an SR file with relations (reuse them if present — do not
duplicate a second `write_task`/`write_sr` helper). If none exist, add these two small helpers near
the top of the file, following the file's existing style:

```python
def _write_task(root, task_id="T-001", satisfies=("SR-900",)):
    tasks_dir = root / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    justification = "\n".join(f"  - satisfies: {sr}" for sr in satisfies)
    (tasks_dir / f"{task_id}.md").write_text(
        f"---\nid: {task_id}\ntitle: t\nstatus: todo\ndod:\n  - d\n"
        + (f"justification:\n{justification}\n" if satisfies else "")
        + "---\nbody\n",
        encoding="utf-8",
    )


def _write_sr_with_relations(root, sr_id="SR-900", implemented_by=(), verified_by=()):
    reqs_dir = root / "requirements"
    reqs_dir.mkdir(parents=True, exist_ok=True)

    def block(field, paths):
        if not paths:
            return ""
        entries = "\n".join(f"  - path: {p}" for p in paths)
        return f"{field}:\n{entries}\n"

    (reqs_dir / f"{sr_id}.md").write_text(
        f"---\nid: {sr_id}\ntitle: t\nstatement: s\ndomain: behavioral\n"
        + block("implemented_by", implemented_by)
        + block("verified_by", verified_by)
        + "---\nbody\n",
        encoding="utf-8",
    )
```

Then add the test cases:

```python
def test_relation_maintenance_not_applicable_when_task_has_no_satisfies_sr(tmp_path):
    _write_task(tmp_path, satisfies=())
    obligations = compile_obligations(
        tmp_path, "task:T-001", changed_files=["src/x.py"],
    )
    ob = next(o for o in obligations if o.kind == "relation_maintenance")
    assert ob.state == "not_applicable"


def test_relation_maintenance_not_applicable_when_no_run_data_available(tmp_path):
    _write_task(tmp_path, satisfies=("SR-900",))
    _write_sr_with_relations(tmp_path, "SR-900")
    obligations = compile_obligations(tmp_path, "task:T-001")  # changed_files defaults to None
    ob = next(o for o in obligations if o.kind == "relation_maintenance")
    assert ob.state == "not_applicable"


def test_relation_maintenance_satisfied_when_changed_files_empty_after_filtering(tmp_path):
    _write_task(tmp_path, satisfies=("SR-900",))
    _write_sr_with_relations(tmp_path, "SR-900")
    obligations = compile_obligations(
        tmp_path, "task:T-001", changed_files=["requirements/SR-900.md", "tasks/T-001.md"],
    )
    ob = next(o for o in obligations if o.kind == "relation_maintenance")
    assert ob.state == "satisfied"


def test_relation_maintenance_open_when_source_file_uncovered(tmp_path):
    _write_task(tmp_path, satisfies=("SR-900",))
    _write_sr_with_relations(tmp_path, "SR-900", implemented_by=("src/coherence/other.py",))
    obligations = compile_obligations(
        tmp_path, "task:T-001", changed_files=["src/coherence/uncovered.py"],
    )
    ob = next(o for o in obligations if o.kind == "relation_maintenance")
    assert ob.state == "open"
    assert any("uncovered.py" in cmd for cmd in ob.resolve_cmd)


def test_relation_maintenance_satisfied_when_every_source_file_covered(tmp_path):
    _write_task(tmp_path, satisfies=("SR-900",))
    _write_sr_with_relations(
        tmp_path, "SR-900",
        implemented_by=("src/coherence/foo.py",),
        verified_by=("tests/unit/coherence/test_foo.py",),
    )
    obligations = compile_obligations(
        tmp_path, "task:T-001",
        changed_files=["src/coherence/foo.py", "tests/unit/coherence/test_foo.py"],
    )
    ob = next(o for o in obligations if o.kind == "relation_maintenance")
    assert ob.state == "satisfied"


def test_relation_maintenance_requiredness_always_blocking(tmp_path):
    _write_task(tmp_path, satisfies=())
    obligations = compile_obligations(tmp_path, "task:T-001", changed_files=[])
    ob = next(o for o in obligations if o.kind == "relation_maintenance")
    assert ob.requiredness == "blocking"
```

Check whether this file's existing tests write requirement/task fixtures under a real `src`
directory too (`is_source_path`'s `_profile_source_dirs` fallback needs `["src"]` to exist as a
concept, not necessarily on disk — re-read `substrate/codemap/build.py::discover_source_files`: it
only skips a source dir that does not `.exists()` when WALKING it; `is_source_path` never checks
existence, only prefix-matching against the `dirs` list itself, so no `src/` directory needs to
exist on disk in these fixtures for `"src/coherence/foo.py"` to classify as a source path. Confirm
this by running the tests, not by re-deriving it a second time here).

- [ ] **Step 2: Run tests to verify they fail**

Run: `rtk proxy uv run pytest tests/unit/coherence/policy/test_compiler.py -k relation_maintenance -v`
Expected: FAIL with `AttributeError`/`StopIteration` (no obligation of that kind exists yet)

- [ ] **Step 3: Implement `_relation_maintenance_obligation` and wire it in**

In `src/coherence/policy/compiler.py`:

1. Change `compile_obligations`'s signature to add `changed_files: list[str] | None = None,` as a
   new keyword-only parameter (after `edges`), and update its docstring's final sentence to
   mention it.
2. In the `task:*` branch, add the new obligation call:

```python
    if scope_ref.startswith("task:"):
        obligations.append(_task_justification_obligation(root, scope_ref, profile))
        obligations.append(
            _relation_maintenance_obligation(
                root, scope_ref, profile, changed_files=changed_files,
            )
        )
```

3. Add the new function (near `_task_justification_obligation`, after it):

```python
def _relation_maintenance_obligation(
    root: Path, scope_ref: str, profile: str, *, changed_files: list[str] | None,
) -> Obligation:
    """relation_maintenance (SR-050 T3): a task that changes production or
    validation code must declare, via its own `satisfies` SRs'
    implemented_by/verified_by relations (SR-050 T1), which files it
    changed. Scoped to ONLY the task's own satisfies SRs -- reconciling
    against any SR anywhere in the register is SR-057/058's
    coherence.register.review.unaccounted_changed_files, already built, not
    duplicated here.

    `changed_files=None` means no run data is available (the
    navigate/dashboard call path, e.g. `coherence navigate present`) --
    reports `not_applicable`, not `open`: this says "not checked yet", never
    "checked and failed". The live gate
    (factory.preflight.checks.run_completion_preflight) is the one caller
    that supplies a real, possibly-empty list, computed from
    GitOps.changed_files the same way the eventual evidence manifest's
    `implementation.changed_files` will be -- see that module for the
    wiring. `requiredness` is always `"blocking"`, unconditionally: this
    obligation, unlike `_task_justification_obligation`, does not graduate
    by profile.
    """
    from substrate.codemap.build import is_source_path
    from substrate.ledger.tasks import get_task, load_tasks

    task_id = scope_ref.partition(":")[2]
    task = get_task(load_tasks(root / "tasks"), task_id)
    satisfies = list(task.satisfies) if task is not None else []

    base = dict(
        id=f"ob:relation_maintenance:{scope_ref}",
        scope_ref=scope_ref,
        kind="relation_maintenance",
        requiredness="blocking",
        source_policy=profile,
    )

    if not satisfies:
        return Obligation(
            **base,
            reason="task declares no satisfies SR to reconcile changed files against",
            state="not_applicable",
            resolve_cmd=None,
        )
    if changed_files is None:
        return Obligation(
            **base,
            reason="no run data available yet to reconcile changed files against declared relations",
            state="not_applicable",
            resolve_cmd=None,
        )

    from coherence.register.register import load_register
    from coherence.register.review import _declared_paths, _raw_meta

    source_files = [f for f in changed_files if is_source_path(root, f)]
    register = {r.id: r for r in load_register(root / "requirements")}
    declared: set[str] = set()
    for sr_id in satisfies:
        req = register.get(sr_id)
        if req is None:
            continue
        meta = _raw_meta(req)
        declared |= _declared_paths(meta, "implemented_by")
        declared |= _declared_paths(meta, "verified_by")
    uncovered = [f for f in source_files if f not in declared]

    return Obligation(
        **base,
        reason=(
            f"{profile} requires every changed production/validation file to be declared by an "
            f"implemented_by/verified_by relation on one of this task's own satisfies SRs "
            f"({', '.join(satisfies)})"
        ),
        state="satisfied" if not uncovered else "open",
        resolve_cmd=(
            tuple(
                f"declare {f} as implemented_by/verified_by on one of {', '.join(satisfies)}"
                for f in uncovered
            )
            if uncovered else None
        ),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `rtk proxy uv run pytest tests/unit/coherence/policy/test_compiler.py -v`
Expected: PASS (whole file — confirms no regression to `_task_justification_obligation` or any
other existing obligation in the same `task:*`/`sr:*` branches)

Also run the broader obligation-consuming suites to confirm nothing downstream (e.g.
`coherence.navigate.obligations`, which calls `compile_obligations` with no `changed_files`
argument) regressed:

Run: `rtk proxy uv run pytest tests/unit/coherence -q`
Expected: PASS

- [ ] **Step 5: Lint and commit**

Run: `rtk proxy uv run ruff check src/coherence/policy/compiler.py tests/unit/coherence/policy/test_compiler.py`

```bash
git add src/coherence/policy/compiler.py tests/unit/coherence/policy/test_compiler.py
git commit -m "feat(policy): add relation_maintenance obligation (SR-050 T3)"
```

---

### Task 3: Live-gate wiring in `run_completion_preflight`

**Files:**
- Modify: `src/factory/preflight/checks.py`
- Test: `tests/unit/preflight/test_completion_preflight.py`

**Interfaces:**
- Consumes: `coherence.policy.compiler.compile_obligations(root, scope_ref, *, changed_files=None)` (Task 2).
- Produces: `run_completion_preflight(repo_root, task, transcript_dir, *, require_review, changed_files=None) -> FreshnessReport` grows the new `changed_files` keyword-only parameter (default `None`, backward compatible — every existing test in this file calls it without this argument and must keep passing unmodified). A `relation_uncovered` `BLOCKING` issue code is now possible. Consumed by Task 4.

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/preflight/test_completion_preflight.py` (reuse the file's existing `task`/
`requirement`/`codes` helpers already defined there — do not redefine them):

```python
def test_uncovered_changed_file_blocks_with_relation_uncovered(tmp_path):
    requirement(tmp_path)  # writes requirements/SR-001.md with a real binding, no relations
    transcript = tmp_path / "runtime"
    write_report(transcript, [{"id": "SR-001", "passed": True, "stale": False}])
    (tmp_path / "src").mkdir()
    report = run_completion_preflight(
        tmp_path, task(tmp_path), transcript, require_review=False,
        changed_files=["src/uncovered.py"],
    )
    assert "relation_uncovered" in codes(report)
    assert report.ok is False


def test_changed_files_none_never_introduces_relation_uncovered(tmp_path):
    requirement(tmp_path)
    transcript = tmp_path / "runtime"
    write_report(transcript, [{"id": "SR-001", "passed": True, "stale": False}])
    report = run_completion_preflight(
        tmp_path, task(tmp_path), transcript, require_review=False,
    )  # changed_files omitted entirely -- must default to None, not []
    assert "relation_uncovered" not in codes(report)
    assert report.ok is True


def test_task_with_no_satisfies_sr_is_never_blocked_by_relation_uncovered(tmp_path):
    transcript = tmp_path / "runtime"
    write_report(transcript, [])
    t = task(tmp_path, satisfies=[])
    report = run_completion_preflight(
        tmp_path, t, transcript, require_review=False, changed_files=["src/anything.py"],
    )
    assert "relation_uncovered" not in codes(report)
```

Note: the file's existing `task()` fixture hard-codes `satisfies or ["SR-001"]` — the third test
above relies on it already accepting an explicit `satisfies=[]` override; if it does not, this step
also updates that one-line fixture to accept and pass through `satisfies=[]` correctly (an empty
list is falsy in Python, so the existing `satisfies or ["SR-001"]` would incorrectly substitute the
default — change it to `["SR-001"] if satisfies is None else satisfies`).

- [ ] **Step 2: Run tests to verify they fail**

Run: `rtk proxy uv run pytest tests/unit/preflight/test_completion_preflight.py -v`
Expected: FAIL — `TypeError: run_completion_preflight() got an unexpected keyword argument 'changed_files'`

- [ ] **Step 3: Implement the wiring**

In `src/factory/preflight/checks.py`:

1. Change `run_completion_preflight`'s signature to add `changed_files: list[str] | None = None,`
   after `require_review: bool,`.
2. Add the new check right before the function's final `return FreshnessReport(...)` line:

```python
    # SR-050 T3: relation-maintenance obligation (coherence.policy.compiler).
    # A policy-resolution failure here (e.g. the task is not yet a resolvable
    # trace node) must never crash a real run over this one new check -- fail
    # open on the obligation lookup itself (no issue added), the same
    # defensive posture run_preflight already uses around its own
    # trace-graph/evidence-manifest reads elsewhere in this module.
    try:
        from coherence.policy.compiler import compile_obligations

        relation_obligations = compile_obligations(
            repo_root, f"task:{task.id}", changed_files=changed_files,
        )
    except (OSError, TypeError, ValueError):
        relation_obligations = []
    relation_obligation = next(
        (o for o in relation_obligations if o.kind == "relation_maintenance"), None
    )
    if relation_obligation is not None and relation_obligation.state == "open":
        issues.append(
            _issue(
                "relation_uncovered",
                FreshnessSeverity.BLOCKING,
                task.id,
                relation_obligation.reason,
                "relation-maintenance",
            )
        )

    return FreshnessReport(sorted(issues, key=lambda item: (item.code, item.dependency)))
```

(This replaces the existing final `return FreshnessReport(...)` line — the rest of the function
above it is untouched.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `rtk proxy uv run pytest tests/unit/preflight/test_completion_preflight.py -v`
Expected: PASS (all tests in the file, old and new)

- [ ] **Step 5: Lint and commit**

Run: `rtk proxy uv run ruff check src/factory/preflight/checks.py tests/unit/preflight/test_completion_preflight.py`

```bash
git add src/factory/preflight/checks.py tests/unit/preflight/test_completion_preflight.py
git commit -m "feat(preflight): block completion on an uncovered changed file (SR-050 T3)"
```

---

### Task 4: Runner wiring — pass this run's actual changed files

**Files:**
- Modify: `src/factory/orchestrator/runner.py`
- Test: `tests/unit/orchestrator/test_runner_e2e.py`

**Interfaces:**
- Consumes: `run_completion_preflight(..., changed_files=None)` (Task 3); the existing `GitOps.changed_files(repo_root, start_commit) -> list[str]` protocol method (already implemented by both `SubprocessGitOps` and `FakeGitOps`).
- Produces: nothing new for later tasks — this is the plan's last code change.

- [ ] **Step 1: Write the failing test**

At the top of `tests/unit/orchestrator/test_runner_e2e.py`, alongside the existing imports, add:

```python
import factory.orchestrator.runner as runner_module
from factory.orchestrator.git_ops import FakeGitOps
from substrate.freshness.model import FreshnessReport
```

Then add the test itself:

```python
def test_completion_preflight_receives_this_runs_changed_files(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    task = Task("T-001", "t", "todo", ["c"], "body", repo / "tasks" / "T-001.md")
    captured = {}

    def fake_preflight(repo_root, task, transcript_dir, *, require_review, changed_files=None):
        captured["changed_files"] = changed_files
        return FreshnessReport([])

    monkeypatch.setattr(runner_module, "run_completion_preflight", fake_preflight)
    git_ops = FakeGitOps(changed_files_result=["src/x.py", "requirements/SR-001.md"])

    r = run_task(
        task, FakeAgentBackend(_scripts()), FakeGateRunner(), repo,
        git_ops=git_ops, transcript_dir=tmp_path / "runtime",
    )

    assert r.outcome == "completed"
    assert captured["changed_files"] == ["src/x.py", "requirements/SR-001.md"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `rtk proxy uv run pytest tests/unit/orchestrator/test_runner_e2e.py -k this_runs_changed_files -v`
Expected: FAIL — `captured["changed_files"]` is `None` (the call site does not pass it yet)

- [ ] **Step 3: Implement the wiring**

In `src/factory/orchestrator/runner.py`, find the existing call (around line 705-711):

```python
    if result.outcome == "completed" and transcript_dir is not None:
        completion = run_completion_preflight(
            repo_root,
            task,
            transcript_dir,
            require_review=human_review is not None and artifact_store is not None,
        )
```

Change it to:

```python
    if result.outcome == "completed" and transcript_dir is not None:
        completion = run_completion_preflight(
            repo_root,
            task,
            transcript_dir,
            require_review=human_review is not None and artifact_store is not None,
            changed_files=git_ops.changed_files(repo_root, start_commit),
        )
```

`start_commit` and `git_ops` are both already in scope at this point in the function (set at the
top of `run_task` and threaded through the whole run) — no new parameter needed on `run_task`
itself.

- [ ] **Step 4: Run tests to verify they pass**

Run: `rtk proxy uv run pytest tests/unit/orchestrator/test_runner_e2e.py -v`
Expected: PASS (whole file)

Then run the full orchestrator suite to confirm this one-line change at a shared call site did not
regress any other completion path:

Run: `rtk proxy uv run pytest tests/unit/orchestrator -q`
Expected: PASS

- [ ] **Step 5: Lint and commit**

Run: `rtk proxy uv run ruff check src/factory/orchestrator/runner.py tests/unit/orchestrator/test_runner_e2e.py`

```bash
git add src/factory/orchestrator/runner.py tests/unit/orchestrator/test_runner_e2e.py
git commit -m "feat(runner): pass this run's changed files into completion preflight (SR-050 T3)"
```

---

### Task 5: Author SR-050 AC-5

**Files:**
- Modify: `requirements/SR-050.md`

**Interfaces:**
- None (documentation-only task; closes the loop by giving T3's landed behavior a bound,
  test-verified acceptance criterion, matching every prior T-package's own closure convention in
  this same file).

- [ ] **Step 1: Add the new acceptance criterion to the frontmatter**

In `requirements/SR-050.md`, add a fifth entry to the `acceptance:` list (after `AC-4`):

```yaml
  - id: AC-5
    criterion: "An implementation task whose changed production or validation code is not declared by an implemented_by or verified_by relation on one of that task's own satisfies requirements cannot complete a live orchestrator run: the run's own completion preflight reports the uncovered file(s) as a blocking issue and the task returns to todo, while a task with no satisfies requirement, or one whose run data is not yet available, is never falsely blocked."
    verification:
      kind: test_marker
      ref: "tests/unit/coherence/policy/test_compiler.py"
```

- [ ] **Step 2: Add the closure note to the body**

Append a new section at the end of `requirements/SR-050.md`'s body (after the existing "AC-4's
fidelity reviewer landed" section), following this file's own established closure-note style
(state what was built, where, and why the verification kind is honest):

```markdown
**AC-5's relation-maintenance obligation landed (2026-09-04, SR-050 T3).**
`coherence.policy.compiler._relation_maintenance_obligation` (new `relation_maintenance` Obligation
kind, `task:*` scope) reconciles a task's own `satisfies` SRs' declared `implemented_by`/
`verified_by` relations against a caller-supplied changed-files list, filtered to real
production/validation code via the new `substrate.codemap.build.is_source_path` -- scoped to only
the task's own SRs (register-wide reconciliation against any SR is SR-057/058's already-built
`unaccounted_changed_files`, not duplicated here). `factory.preflight.checks.
run_completion_preflight` -- the function `factory/orchestrator/runner.py` already consults to
decide whether a completed run's outcome stands -- now calls this obligation and raises a new
`BLOCKING` `relation_uncovered` issue when it reports `open`, escalating the run back to `todo`
exactly like every pre-existing check in that function. The runner supplies the changed-files list
via `GitOps.changed_files(repo_root, start_commit)`, the same call the evidence manifest's own
`implementation.changed_files` will make moments later -- not a second, divergent way of asking
"what changed."

Deliberately unresolved by this AC, tracked separately: whether `run_completion_preflight`'s other
four checks (`validation_missing`/`validation_failed`/`validation_stale`/`review_missing`/
`must_fix_unresolved`) should ever be migrated onto `compile_obligations` too ([[SR-063]]); no
performance budget for this or any other FEAT-001 review mechanism ([[SR-064]]).
```

- [ ] **Step 3: Verify the register still loads cleanly**

Run: `rtk proxy uv run python -m coherence register check`
Expected: exits without a schema/parse error for SR-050 (the pre-existing "undecided" advisory
noise for other SRs in the corpus is expected and unrelated — confirm SR-050 itself is not newly
listed as invalid/malformed, not that the whole command exits 0)

- [ ] **Step 4: Commit**

```bash
git add requirements/SR-050.md
git commit -m "docs(SR-050): close AC-5 -- relation-maintenance obligation now blocks completion"
```

---

## Final verification (run once, after all 5 tasks)

```bash
rtk proxy uv run pytest tests/unit/codeindex tests/unit/coherence tests/unit/preflight tests/unit/orchestrator -q
rtk proxy uv run ruff check src tests
rtk proxy uv run python -m coherence register check
rtk proxy uv run python -m coherence navigate health --json
```

Completion requires every task's tests green, `ruff check` clean, and both `coherence` commands
exiting without a NEW error attributable to this plan's changes (the pre-existing "undecided
requirements" advisory list is expected baseline noise, not a regression).
