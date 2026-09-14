# FEAT-017 Long-Term Stabilization and Closure Plan

> **For Hermes:** Use `subagent-driven-development` for implementation, one fresh worker per accepted task boundary. Use parent-side verification and fresh independent review for every source-changing commit. Do not execute this plan until the user explicitly authorizes implementation.

**Goal:** Stabilize FEAT-017 by reconciling the existing Claude candidate, making bundle/consent semantics consistent, preserving individual human authority, packaging verification schemas, adding feature-scoped health gates, and proving the non-starting planning lifecycle without modifying other feature owners’ requirements.

**Architecture:** Keep the transactional parent-owned planning run store authoritative; JSON, feature dossiers, bundles, task files, and DecisionFiles are validated projections. First freeze and verify the parallel Claude candidate at exact revisions, then land only independently accepted slices into a clean integration worktree. Mechanical projection and scoped-health checks may be automated, while requirement meaning, per-SR consent, adoption, implementation acceptance, integration, and downstream execution remain separate human-controlled gates.

**Tech stack:** Python 3.11/3.12, `uv`, pytest, Ruff, Pyright, Draft 2020-12 JSON Schema, `python-frontmatter`, Git worktrees, Coherence CLI.

---

## Current context and assumptions

### Canonical scope

- Repository: `C:/coding/pi-agent-factory`.
- Current planning worktree: `C:/coding/pi-agent-factory-wt/feat17-planning`.
- Planning branch/head at inspection time: `feat/coherence-feat17-planning` / `33c44fd`.
- FEAT-017 remains `draft`; no implementation, adoption, merge, push, release, or downstream execution is accepted by this plan.
- FEAT-017 owns exactly:
  - `SR-043`
  - `SR-044`
  - `SR-051`
  - `SR-052`
  - `SR-053`
  - `SR-054`
  - `SR-055`
- `SR-050` is a shared dependency consumed by `SR-054`; it is not owned by FEAT-017 and must not be modified by FEAT-017 implementation work.
- `SR-035` and `SR-036` are shared upstream dependencies of `SR-055`; they must not be absorbed into FEAT-017 ownership.
- Preserve the prior decision that T-032 and T-033 are accepted/complete. Do not reopen them unless a proposed integration changes their accepted files or acceptance boundary; if that occurs, stop for explicit scope authorization.
- T-034 and later implementation remain unaccepted.

### Parallel Claude candidate

At `2026-09-04 16:47 +10:00`, no running process named Claude, Codex, or Hermes was visible, but this is only a snapshot. Recheck before execution.

`C:/coding/pi-agent-factory-wt/feat17-deterministic-runner-dev` contains three commits not present on the planning branch:

| Commit | Observed scope | Initial classification |
|---|---|---|
| `343cc6f` | `src/coherence/planning/runner.py`, `tests/unit/coherence/test_planning_runner.py` | T-034 runner candidate; unaccepted |
| `a6b3d51` | runner malformed-journal fix and tests | T-034 follow-up; unaccepted |
| `212eff6` | durable intent/bootstrap/serialization changes and tests | Potential T-033 overlap; preserve but do not re-accept automatically |

The same worktree also had 13 tracked dirty files, approximately 543 insertions and 3,911 deletions, plus untracked FEAT-017 files. The dirty candidate is not a reviewable or integratable unit until Claude supplies an exact handoff revision or patch.

Other FEAT-017 worktrees are non-authoritative inputs:

- `feat17-doc-contract-fix`: dirty plan/spec edits on `76f460d`, no unique commit versus the planning branch.
- `feat17-worktree-enforcement`: dirty `kanban.py` and `test_planning_kanban.py`; this conflicts with the decision to remove the obsolete Kanban planning transport and must not be merged.

### Known live defects and debt

- Current membership coverage after the bounded projection repair: `72/222`; the global gate still fails on other-owner/historical artifacts.
- Trace remains `48 pending / 80 deferred / 5 exempt` globally.
- Register remains `55 pending` globally.
- The FEAT-017 bundle now contains its feature, seven owned SRs, canonical spec, two plans, and T-032–T-045.
- `docs/features/FEAT-017.md` still says the bundle contains only feature/SR projections; this narrative is stale.
- `src/coherence/planning/gates.py::validate_requirement_consent()` currently requires the bundle member set to equal only `{feat:FEAT-017 + seven SR refs}`. That conflicts with the full dossier membership required by the membership gate.
- `tasks/T-044-…md` currently lists `requirements/SR-050.md` as modifiable; that violates ownership.
- `coherence navigate bundle check` reloads artifact nodes repeatedly and exceeded 90 seconds for the 25-member FEAT-017 bundle.
- `src/substrate/schemas/verification_record.schema.json` and its manifest integration exist only as an uncommitted candidate; `pyproject.toml` has no package-data rule for `src/substrate/schemas/*.json`.
- The current Claude candidate still uses aggregate `sr-consent.json` and `requirement-consent.json`; individual immutable per-SR decisions are not implemented.

### Non-negotiable boundaries

1. Do not manufacture requirement satisfaction, measurements, consent, acceptance, or adoption to clear a gate.
2. Do not modify FEAT-002-owned requirements or bundles, including `SR-050`.
3. Do not merge, cherry-pick, commit, push, or release without the authorization appropriate to that operation.
4. Do not work in a checkout while Claude or another writer owns it.
5. Do not accept dirty-worktree tests as exact-commit evidence.
6. Keep implementation-gate execution downstream of an approved execution contract; FEAT-017 may compile and validate planning gates only.
7. Every gate must fail closed on missing, stale, malformed, contradictory, or unauthoritative evidence.

---

## Phase 0 — Reconcile and freeze the parallel work

### Task 0.1: Recheck all FEAT-017 worktrees and active writers

**Objective:** Establish a fresh ownership snapshot before anyone edits a FEAT-017 file.

**Files:** None.

**Steps:**

1. Run:

   ```bash
   git worktree list --porcelain
   ps -W | python -c 'import sys; print("".join(line for line in sys.stdin if any(x in line.lower() for x in ("claude", "codex", "hermes"))))'
   ```

   Expected: all FEAT-017 worktrees are listed; any live writer is visible. An empty filtered process list does not prove a GUI is idle, so also obtain a human handoff from the parallel Claude session.

2. For each FEAT-017 worktree, run:

   ```bash
   git status --short --untracked-files=all
   git branch --show-current
   git rev-parse HEAD
   git diff --cached --name-status
   git diff --name-status
   ```

   Expected: exact branch, SHA, staged paths, unstaged paths, and untracked paths are recorded. Do not stage anything.

3. If Claude is still active or has not explicitly handed off the worktree, stop this plan at this task.

**Commit:** None.

### Task 0.2: Require an exact Claude handoff

**Objective:** Convert the parallel work from a mutable checkout into reviewable provenance.

**Files:** None unless Claude itself creates its scoped commits.

**Required handoff fields:**

```text
worktree
branch
base SHA
final SHA or patch path
commit list in order
changed paths per commit
which canonical T-### each commit claims
exact test/lint/type commands and outputs
known failed reviews or unresolved findings
staged/unstaged/untracked paths left behind
```

**Decision rules:**

- A dirty tree without a final SHA is a candidate, not an implementation.
- Preserve `343cc6f`, `a6b3d51`, and `212eff6`; do not rewrite or squash them during investigation.
- Do not accept `212eff6` as T-033 merely because its title mentions intent. Compare it to the already accepted T-033 boundary.
- Never merge the stale Kanban worktree.

**Commit:** None.

### Task 0.3: Review the three unique commits from clean snapshots

**Objective:** Determine which existing work can be reused without duplicating Claude’s work.

**Files:** None in the canonical worktree.

**Steps for each SHA:**

1. Create a disposable detached worktree:

   ```bash
   git worktree add --detach C:/Users/33630/AppData/Local/Temp/feat17-review-<sha> <sha>
   uv sync --all-groups
   ```

2. Verify provenance:

   ```bash
   git show --check --stat <sha>
   git show --name-status --format=fuller <sha>
   git diff <sha>^ <sha> --check
   ```

   Expected: no whitespace errors and only the declared paths.

3. For `343cc6f` plus `a6b3d51`, run:

   ```bash
   uv run pytest tests/unit/coherence/test_planning_runner.py -q -o addopts=''
   uv run ruff check src/coherence/planning/runner.py tests/unit/coherence/test_planning_runner.py
   uv run pyright src/coherence/planning/runner.py
   ```

   Expected: exit `0`; record exact pass/skip counts. Any hang, missing dependency, or dirty-sibling dependency fails review.

4. For `212eff6`, run:

   ```bash
   uv run pytest tests/unit/coherence/test_planning_intent.py tests/unit/coherence/test_planning_bootstrap.py -q -o addopts=''
   uv run ruff check src/coherence/planning/intent.py src/coherence/planning/bootstrap.py src/coherence/planning/serialization.py tests/unit/coherence/test_planning_intent.py tests/unit/coherence/test_planning_bootstrap.py
   uv run pyright src/coherence/planning/intent.py src/coherence/planning/bootstrap.py src/coherence/planning/serialization.py
   ```

   Expected: exit `0`; verification establishes technical integrity only, not renewed T-033 acceptance.

5. Dispatch one fresh broad reviewer per candidate boundary. Require a structured fail-closed verdict covering specification compliance, durability, security, path safety, stale evidence, recovery, resource bounds, and code quality.

6. Remove each disposable worktree only after evidence is recorded:

   ```bash
   git worktree remove C:/Users/33630/AppData/Local/Temp/feat17-review-<sha>
   ```

**Commit:** None.

### Task 0.4: Select the canonical integration baseline

**Objective:** Prevent accidental mixing of the dirty planning tree and the Claude candidate.

**Human gate:** Present the exact accepted/rejected commit table. Ask separately for authorization to integrate any accepted SHA.

**After authorization only:**

```bash
git worktree add C:/coding/pi-agent-factory-wt/feat17-longterm -b feat/coherence-feat17-longterm <authorized-base-sha>
uv sync --all-groups
uv run python -c "import coherence, substrate; print('imports ok')"
uv run pytest tests/unit/coherence/test_planning_trace_contract.py -q -o addopts=''
```

Expected: clean worktree, `imports ok`, and the baseline trace-contract tests pass. If not, stop and reconcile the baseline before continuing.

---

## Phase 1 — Make bundle and consent semantics consistent

### Task 1.1: Add a RED test for full dossier bundle consent validation

**Objective:** Prove that FEAT-017 may include its spec/plan/tasks without allowing foreign SR ownership.

**Files:**

- Create or modify after Claude handoff: `tests/unit/coherence/test_planning_gates.py`
- Later modify: `src/coherence/planning/gates.py`

**Step 1: Add these complete tests:**

```python
from coherence.planning.gates import _validate_feat17_bundle_members


def test_feat17_bundle_accepts_owned_srs_and_dossier_artifacts() -> None:
    members = [
        "feat:FEAT-017",
        "spec:docs/superpowers/specs/2026-08-27-feat17-planning-bootstrap-design.md",
        "plan:docs/superpowers/plans/2026-08-27-feat17-planning-workflow-plan.md",
        "sr:SR-043",
        "sr:SR-044",
        "sr:SR-051",
        "sr:SR-052",
        "sr:SR-053",
        "sr:SR-054",
        "sr:SR-055",
        "task:T-032",
        "task:T-045",
    ]

    assert _validate_feat17_bundle_members(
        members,
        ["SR-043", "SR-044", "SR-051", "SR-052", "SR-053", "SR-054", "SR-055"],
    ) == (True, "FEAT-017 bundle ownership is current")


def test_feat17_bundle_rejects_foreign_or_shared_sr_members() -> None:
    members = [
        "feat:FEAT-017",
        "sr:SR-043",
        "sr:SR-044",
        "sr:SR-050",
        "sr:SR-051",
        "sr:SR-052",
        "sr:SR-053",
        "sr:SR-054",
        "sr:SR-055",
    ]

    ok, detail = _validate_feat17_bundle_members(
        members,
        ["SR-043", "SR-044", "SR-051", "SR-052", "SR-053", "SR-054", "SR-055"],
    )

    assert not ok
    assert detail == "FEAT-017 bundle contains non-owned requirement(s): SR-050"
```

**Step 2: Run RED:**

```bash
uv run pytest tests/unit/coherence/test_planning_gates.py -q -o addopts=''
```

Expected: FAIL because `_validate_feat17_bundle_members` does not exist.

### Task 1.2: Implement the minimal bundle ownership validator

**Objective:** Separate exact SR ownership from broader dossier membership.

**Files:**

- Modify: `src/coherence/planning/gates.py`
- Test: `tests/unit/coherence/test_planning_gates.py`

**Step 1: Add this helper above `validate_requirement_consent()`:**

```python
def _validate_feat17_bundle_members(
    members: object,
    requirement_ids: list[str],
) -> tuple[bool, str]:
    if not isinstance(members, list) or any(not isinstance(item, str) for item in members):
        return False, "FEAT-017 bundle has invalid members"
    if len(members) != len(set(members)):
        return False, "FEAT-017 bundle has duplicate members"

    member_set = set(members)
    required = {"feat:FEAT-017", *(f"sr:{req_id}" for req_id in requirement_ids)}
    missing = sorted(required - member_set)
    if missing:
        return False, f"FEAT-017 bundle is missing required member(s): {', '.join(missing)}"

    owned_sr_refs = {f"sr:{req_id}" for req_id in requirement_ids}
    foreign_srs = sorted(
        member.removeprefix("sr:")
        for member in member_set
        if member.startswith("sr:") and member not in owned_sr_refs
    )
    if foreign_srs:
        return False, (
            "FEAT-017 bundle contains non-owned requirement(s): " + ", ".join(foreign_srs)
        )

    feature_refs = sorted(member for member in member_set if member.startswith("feat:"))
    if feature_refs != ["feat:FEAT-017"]:
        return False, "FEAT-017 bundle contains an invalid feature membership"
    return True, "FEAT-017 bundle ownership is current"
```

**Step 2: Replace the exact-set check in `validate_requirement_consent()`:**

```python
    members_ok, members_detail = _validate_feat17_bundle_members(
        bundle.get("members"), requirement_ids
    )
    if not members_ok:
        return False, members_detail
```

Delete the old `expected_members` and `set(members) != expected_members` block.

**Step 3: Run GREEN:**

```bash
uv run pytest tests/unit/coherence/test_planning_gates.py tests/unit/coherence/test_planning_review_resolution.py -q -o addopts=''
uv run ruff check src/coherence/planning/gates.py tests/unit/coherence/test_planning_gates.py
uv run pyright src/coherence/planning/gates.py
```

Expected: all commands exit `0` and both new tests pass.

**Step 4: Commit after explicit commit authorization:**

```bash
git add src/coherence/planning/gates.py tests/unit/coherence/test_planning_gates.py
git commit -m "fix(planning): separate bundle ownership from dossier membership"
```

### Task 1.3: Reconcile the feature dossier, bundle, and T-044 scope

**Objective:** Make all canonical projections describe the same ownership boundary.

**Files:**

- Modify: `docs/features/FEAT-017.md`
- Modify: `bundles/FEAT-017.json`
- Modify: `tasks/T-044-register-mature-feat-017-requirements-and-prove-semantic-trace-coverage.md`
- Test: `tests/unit/coherence/test_planning_trace_contract.py`
- Read only: `requirements/SR-050.md`

**Required textual changes:**

1. In `docs/features/FEAT-017.md`, replace the statement that the bundle contains only feature/SR projections with:

   ```text
   The bundle is the complete FEAT-017 dossier membership projection: the feature, its seven owned
   SRs, the canonical authority spec, the current implementation plan, retained historical handoff
   context, and T-032 through T-045. Membership does not imply consent, adoption, implementation
   acceptance, or verification. SR-050 remains a related shared contract and is not a member.
   ```

2. In T-044’s `## Files`, replace:

   ```text
   - Modify: `requirements/SR-050.md`
   ```

   with:

   ```text
   - Read-only dependency: `requirements/SR-050.md`
   ```

3. Ensure `bundles/FEAT-017.json` contains exactly:
   - `feat:FEAT-017`;
   - seven owned SR refs, excluding `SR-050`;
   - canonical FEAT-017 spec path;
   - current implementation plan path;
   - retained FEAT-017 requirements handoff path;
   - `task:T-032` through `task:T-045`.

4. Add a regression assertion to `tests/unit/coherence/test_planning_trace_contract.py` that `SR-050` is absent from bundle members and T-044 declares it read-only.

**Verification:**

```bash
uv run pytest tests/unit/coherence/test_planning_trace_contract.py tests/unit/coherence/test_planning_gates.py -q -o addopts=''
uv run coherence navigate membership --repo-root . --json
uv run coherence navigate brief --scope feat:FEAT-017 --repo-root . --json
uv run python -m json.tool bundles/FEAT-017.json >/dev/null

git diff --check -- docs/features/FEAT-017.md bundles/FEAT-017.json tasks/T-044-register-mature-feat-017-requirements-and-prove-semantic-trace-coverage.md tests/unit/coherence/test_planning_trace_contract.py
```

Expected: tests pass; brief shows exactly seven owned SRs and T-032–T-045; membership retains the FEAT-017 spec/plan/tasks; `SR-050` is absent from the bundle.

**Commit after authorization:**

```bash
git add docs/features/FEAT-017.md bundles/FEAT-017.json tasks/T-044-register-mature-feat-017-requirements-and-prove-semantic-trace-coverage.md tests/unit/coherence/test_planning_trace_contract.py
git commit -m "docs(feat17): align dossier membership and shared ownership"
```

---

## Phase 2 — Make bundle checks bounded and deterministic

### Task 2.1: Add a RED test proving one artifact scan per bundle check

**Objective:** Replace wall-clock assertions with a deterministic scan-count regression.

**Files:**

- Modify: `tests/unit/coherence/test_navigate_bundles.py`
- Later modify: `src/coherence/navigate/cli.py`

**Add this test:**

```python
def test_bundle_check_builds_artifact_lookup_once(tmp_path, monkeypatch):
    from coherence.navigate.cli import cmd_bundle_check
    from coherence.trace import model as trace_model

    _seed_feature(tmp_path)
    for index in range(2, 26):
        (tmp_path / "tasks" / f"T-{index:03d}.md").write_text(
            "---\n"
            f"id: T-{index:03d}\n"
            f"title: Task {index}\n"
            "satisfies: [SR-001]\n"
            "---\n",
            encoding="utf-8",
        )
    draft = tmp_path / "FEAT-001.json"
    draft.write_text(
        json.dumps(
            {
                "id": "FEAT-001",
                "label": "Navigation",
                "members": [
                    "feat:FEAT-001",
                    "sr:SR-001",
                    *[f"task:T-{index:03d}" for index in range(1, 26)],
                ],
            }
        ),
        encoding="utf-8",
    )

    original = trace_model.load_nodes
    calls = 0

    def counted(root: Path):
        nonlocal calls
        calls += 1
        return original(root)

    monkeypatch.setattr(trace_model, "load_nodes", counted)

    result = cmd_bundle_check(tmp_path, str(draft))

    assert result["members_total"] == 27
    assert result["members_resolved"] == 26
    assert result["unresolved"] == ["feat:FEAT-001"]
    assert calls == 1
```

**Run RED:**

```bash
uv run pytest tests/unit/coherence/test_navigate_bundles.py::test_bundle_check_builds_artifact_lookup_once -q -o addopts=''
```

Expected: FAIL because `load_nodes` is called more than once.

### Task 2.2: Cache artifact resolution inside `cmd_bundle_check()`

**Objective:** Make bundle checking linear in repository size plus bundle size.

**Files:**

- Modify: `src/coherence/navigate/cli.py`
- Test: `tests/unit/coherence/test_navigate_bundles.py`

**Implementation:**

1. Add `build_artifact_lookup` to the existing coverage imports.
2. In `cmd_bundle_check()`, create one lookup immediately after reading `members`:

   ```python
   lookup = build_artifact_lookup(repo_root)
   ```

3. Pass it to every resolver and coverage call:

   ```python
   target = member_target(repo_root, ref, lookup=lookup)
   before = bundle_coverage(repo_root, lookup=lookup)
   already_claimed = {
       member_target(repo_root, member.ref, lookup=lookup)
       for bundle in list_bundles(repo_root / "bundles")
       for member in bundle.members
   }
   ```

4. Replace the overlap loop with this complete cached version:

   ```python
   loaded_bundles = list_bundles(repo_root / "bundles")
   overlaps: list[dict] = []
   for ref, target in resolved.items():
       containing = [
           bundle.id
           for bundle in loaded_bundles
           if any(
               member_target(repo_root, member.ref, lookup=lookup) == target
               for member in bundle.members
           )
       ]
       if containing:
           overlaps.append({"member": ref, "bundles": containing})
   ```

**Run GREEN and regression:**

```bash
uv run pytest tests/unit/coherence/test_navigate_bundles.py -q -o addopts=''
uv run ruff check src/coherence/navigate/cli.py tests/unit/coherence/test_navigate_bundles.py
uv run pyright src/coherence/navigate/cli.py

timeout 15s uv run coherence navigate bundle check --repo-root . --draft bundles/FEAT-017.json --json
```

Expected: unit tests pass; static checks exit `0`; the real FEAT-017 bundle check finishes before the 15-second external timeout and reports only `feat:FEAT-017` unresolved.

**Commit after authorization:**

```bash
git add src/coherence/navigate/cli.py tests/unit/coherence/test_navigate_bundles.py
git commit -m "perf(navigate): cache bundle artifact resolution"
```

---

## Phase 3 — Make verification schemas installable

### Task 3.1: Add a RED wheel-content test

**Objective:** Prove installed wheels contain every substrate JSON schema, including the FEAT-007 verification-record contract consumed by FEAT-017.

**Prerequisite:** The four-path FEAT-007/SR-024 candidate must receive its own explicit integration authorization; FEAT-017 must not silently adopt it.

**Files:**

- Create: `tests/integration/packaging/test_schema_package_data.py`
- Later modify: `pyproject.toml`

**Test code:**

```python
from __future__ import annotations

import subprocess
from pathlib import Path
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[3]


def test_wheel_contains_all_substrate_schemas(tmp_path: Path) -> None:
    subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(tmp_path)],
        cwd=ROOT,
        check=True,
        text=True,
    )
    wheels = list(tmp_path.glob("*.whl"))
    assert len(wheels) == 1

    expected = {
        f"substrate/schemas/{path.name}"
        for path in (ROOT / "src" / "substrate" / "schemas").glob("*.json")
    }
    with ZipFile(wheels[0]) as wheel:
        packaged = {name for name in wheel.namelist() if name.startswith("substrate/schemas/")}

    assert packaged == expected
    assert "substrate/schemas/verification_record.schema.json" in packaged
```

**Run RED:**

```bash
uv run pytest tests/integration/packaging/test_schema_package_data.py -q -o addopts=''
```

Expected: FAIL because no JSON schemas are included in the wheel.

### Task 3.2: Include substrate schemas in wheels

**Objective:** Fix packaging without changing runtime validation behavior.

**Files:**

- Modify: `pyproject.toml`
- Test: `tests/integration/packaging/test_schema_package_data.py`

**Add exactly:**

```toml
[tool.setuptools.package-data]
substrate = ["schemas/*.json"]
```

**Run GREEN:**

```bash
uv run pytest tests/integration/packaging/test_schema_package_data.py -q -o addopts=''
uv run pytest tests/unit/substrate/test_verification_record_schema.py -q -o addopts=''
uv run ruff check tests/integration/packaging/test_schema_package_data.py
uv build --wheel --out-dir "$LOCALAPPDATA/Temp/feat17-wheel-check"
```

Expected: both test commands pass; the wheel contains `substrate/schemas/verification_record.schema.json` and all sibling schemas.

**Commit after authorization:**

```bash
git add pyproject.toml tests/integration/packaging/test_schema_package_data.py
git commit -m "fix(packaging): include substrate schema resources"
```

---

## Phase 4 — Mature the seven FEAT-017 requirements without fabricating approval

### Task 4.1: Produce a seven-SR acceptance/binding proposal

**Objective:** Define measurable contracts before editing canonical SR files.

**Files:**

- Read: `requirements/SR-043.md`
- Read: `requirements/SR-044.md`
- Read: `requirements/SR-051.md`
- Read: `requirements/SR-052.md`
- Read: `requirements/SR-053.md`
- Read: `requirements/SR-054.md`
- Read: `requirements/SR-055.md`
- Read: `docs/superpowers/specs/2026-08-27-feat17-planning-bootstrap-design.md`
- Write only after approval: the same seven SR files.

**Required proposal table for each SR:**

```text
SR ID and exact normative statement
source anchor
owner and shared dependencies
AC-### criterion(s)
B-### binding ID
harness or command
metric
assertion
required artifacts
failure semantics
current implementation candidate paths
current validation test nodes
known evidence status
```

**Rules:**

- Present each SR individually to the user before changing it.
- Use complete universal fields independent of project profile.
- An implementation link is not verification evidence.
- A proposed test command is not a passing observation.
- Do not bind an SR to a test that does not exercise the complete behavior.
- Split genuinely distinct measurements into distinct SRs rather than overloading one binding.

**Human gate:** Obtain explicit approval for each SR contract independently. No aggregate approval.

**Commit:** None at proposal stage.

### Task 4.2: Apply one approved SR contract at a time

**Objective:** Keep provenance and review boundaries small.

**Files:** One `requirements/SR-###.md` per task, then `requirements/index.json` only through the canonical register/index command.

**Required frontmatter shape:**

```yaml
acceptance:
  - id: AC-001
    criterion: "<approved measurable criterion>"
verification:
  binding_id: B-001
  contract: "verification-record@1"
binding:
  id: B-001
  harness: "<approved harness>"
  experiment: "<approved experiment or command identity>"
  metric: "<approved metric>"
  assert: "<approved assertion>"
  trials: 1
```

Do not substitute placeholder text. If any approved value is missing, stop.

**Verification for each SR:**

```bash
uv run coherence register show SR-### --requirements-dir requirements
uv run coherence trace graph --project-root . --json
uv run pytest <approved-test-node> -q -o addopts=''
```

Expected: the record parses; the exact test passes if implementation is accepted and available. If implementation is not accepted, record the requirement as proposed/allocated and do not manufacture a passing verification record.

**Commit after authorization, one SR per commit:**

```bash
git add requirements/SR-###.md requirements/index.json
git commit -m "docs(requirements): bind SR-### acceptance contract"
```

---

## Phase 5 — Replace aggregate consent with individual parent-authorized decisions

### Task 5.1: Freeze the authority model before code

**Objective:** Avoid turning writable JSON into self-certified human authority.

**Decision to record in the canonical spec before implementation:**

- The transactional planning run store owns immutable decision events.
- A DecisionFile is a derived, read-only projection of one authority event.
- One event concerns one SR revision only.
- The join keys are `run_id`, `requirement_id`, `requirement_sha256`, and `derivation_report_sha256`.
- Decision vocabulary is closed: `accept`, `reject`, `defer`, `revise`.
- Only a parent-owned human-input adapter may issue the opaque authority attestation consumed by the runner.
- No public runner method or CLI flag may mint a trusted human attestation from caller-supplied fields.
- A changed SR hash invalidates prior acceptance.
- A later decision uses a new event and names the superseded event; prior bytes remain immutable.

**Human gate:** Obtain explicit architecture approval. Do not edit `gates.py`, `runner.py`, or consent schemas before this decision.

### Task 5.2: Add the DecisionFile projection schema with RED tests

**Files:**

- Create: `src/substrate/schemas/planning_sr_decision.schema.json`
- Create: `tests/unit/substrate/test_planning_sr_decision_schema.py`

**Schema:**

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://factory.local/schemas/planning_sr_decision.schema.json",
  "title": "Planning SR decision projection",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "schema_version",
    "decision_id",
    "run_id",
    "requirement_id",
    "requirement_sha256",
    "derivation_report_sha256",
    "decision",
    "reviewer",
    "reason",
    "authority_event_id",
    "authority_head_sha256",
    "supersedes"
  ],
  "properties": {
    "schema_version": {"const": 1},
    "decision_id": {"type": "string", "pattern": "^D-[0-9]{6}$"},
    "run_id": {"type": "string", "pattern": "^[A-Za-z0-9][A-Za-z0-9_.-]*$"},
    "requirement_id": {"type": "string", "pattern": "^SR-[0-9]+$"},
    "requirement_sha256": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
    "derivation_report_sha256": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
    "decision": {"enum": ["accept", "reject", "defer", "revise"]},
    "reviewer": {"const": "human"},
    "reason": {"type": "string", "minLength": 1},
    "authority_event_id": {"type": "string", "minLength": 1},
    "authority_head_sha256": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
    "supersedes": {
      "oneOf": [
        {"type": "null"},
        {"type": "string", "pattern": "^D-[0-9]{6}$"}
      ]
    }
  }
}
```

**Tests must cover:** valid record, unknown field, malformed IDs/hashes, non-human reviewer, empty reason, invalid decision, and malformed supersession.

**RED:**

```bash
uv run pytest tests/unit/substrate/test_planning_sr_decision_schema.py -q -o addopts=''
```

Expected: FAIL because the schema does not exist.

**GREEN:**

```bash
uv run pytest tests/unit/substrate/test_planning_sr_decision_schema.py -q -o addopts=''
uv run ruff check tests/unit/substrate/test_planning_sr_decision_schema.py
```

Expected: pass.

**Commit after authorization:**

```bash
git add src/substrate/schemas/planning_sr_decision.schema.json tests/unit/substrate/test_planning_sr_decision_schema.py
git commit -m "feat(planning): define individual SR decision projection"
```

### Task 5.3: Add immutable decision events to the accepted runner

**Objective:** Make per-SR decisions authoritative without a self-certifying API.

**Files depend on the accepted Claude/T-034 result and must be re-read before implementation:**

- Modify: `src/coherence/planning/runner.py`
- Modify: `src/coherence/planning/run.py`
- Modify: `src/coherence/planning/gates.py`
- Modify: `src/coherence/planning/resolution.py`
- Test: `tests/unit/coherence/test_planning_runner.py`
- Test: `tests/unit/coherence/test_planning_review_resolution.py`
- Test: `tests/unit/coherence/test_planning_resolution.py`

**Required TDD cases:**

1. No public API accepts `reviewer="human"` or a bare decision mapping as authority.
2. One parent-attested event records exactly one SR hash and one derivation hash.
3. Replaying the same event ID is idempotent only when bytes match; contradictory replay blocks.
4. Changing the SR hash makes the previous decision non-current.
5. Aggregate approval never satisfies the gate.
6. A projection missing from disk can be regenerated from the authority store.
7. A projection contradicting the authority store blocks and cannot advance.
8. Reject/defer/revise are non-passing.
9. Supersession preserves prior events and requires a valid existing predecessor.
10. Decision projection failure after authority commit appends an immutable block or returns a durable-unavailable failure.

**Verification:**

```bash
uv run pytest tests/unit/coherence/test_planning_runner.py tests/unit/coherence/test_planning_review_resolution.py tests/unit/coherence/test_planning_resolution.py -q -o addopts=''
uv run ruff check src/coherence/planning/runner.py src/coherence/planning/run.py src/coherence/planning/gates.py src/coherence/planning/resolution.py tests/unit/coherence/test_planning_runner.py tests/unit/coherence/test_planning_review_resolution.py tests/unit/coherence/test_planning_resolution.py
uv run pyright src/coherence/planning/runner.py src/coherence/planning/run.py src/coherence/planning/gates.py src/coherence/planning/resolution.py
```

Expected: all pass. Then require a fresh independent fail-closed review before committing.

**Commit after review and authorization:**

```bash
git add src/coherence/planning/runner.py src/coherence/planning/run.py src/coherence/planning/gates.py src/coherence/planning/resolution.py tests/unit/coherence/test_planning_runner.py tests/unit/coherence/test_planning_review_resolution.py tests/unit/coherence/test_planning_resolution.py
git commit -m "feat(planning): enforce individual hash-bound SR decisions"
```

### Task 5.4: Retire aggregate consent as authority without deleting history

**Objective:** Preserve legacy files for audit while making them incapable of authorizing adoption.

**Files:**

- Modify: `src/coherence/planning/gates.py`
- Modify: `src/coherence/planning/check.py`
- Modify: `src/coherence/planning/cli.py`
- Modify: relevant planning tests
- Preserve read-only: historical `sr-consent.json` and `requirement-consent.json`

**Required behavior:**

- Legacy aggregate files may be displayed as `legacy_non_authoritative`.
- They never satisfy current consent.
- Current status lists the exact SR IDs still awaiting individual decisions.
- No migration script synthesizes individual decisions from aggregate approval.

**Verification:**

```bash
uv run pytest tests/unit/coherence/test_planning_review_resolution.py tests/unit/coherence/test_planning_cli.py tests/unit/coherence/test_planning_trace_contract.py -q -o addopts=''
```

Expected: tests prove aggregate records remain readable but non-passing.

**Commit after authorization:**

```bash
git add src/coherence/planning/gates.py src/coherence/planning/check.py src/coherence/planning/cli.py tests/unit/coherence/test_planning_review_resolution.py tests/unit/coherence/test_planning_cli.py tests/unit/coherence/test_planning_trace_contract.py
git commit -m "fix(planning): retire aggregate consent authority"
```

---

## Phase 6 — Add feature-scoped health without weakening global gates

### Task 6.1: Define the scoped artifact selection contract

**Objective:** Make FEAT-017 readiness observable independently of unrelated repository debt.

**Files:**

- Create: `src/coherence/scope.py`
- Create: `tests/unit/coherence/test_scope_selection.py`

**Contract:**

`load_feature_scope(root, "FEAT-017")` returns:

- the feature ref;
- owned SR IDs from `docs/features/FEAT-017.md` frontmatter;
- task IDs that justify at least one owned SR;
- the canonical authority spec and implementation plan paths;
- all resolvable bundle members;
- shared upstream SR IDs as dependencies, not owned members.

It must fail on duplicate owned SRs, missing owned SR files, a bundle missing an owned SR, foreign SR membership, malformed task justification, or a feature/bundle ID mismatch.

**Do not include:** other features’ tasks merely because they touch a shared SR.

**RED/GREEN commands:**

```bash
uv run pytest tests/unit/coherence/test_scope_selection.py -q -o addopts=''
uv run ruff check src/coherence/scope.py tests/unit/coherence/test_scope_selection.py
uv run pyright src/coherence/scope.py
```

Expected: RED before `scope.py`; GREEN afterward. Require tests for FEAT-017 ownership, shared `SR-050`, and a foreign-SR bundle fixture.

**Commit after authorization:**

```bash
git add src/coherence/scope.py tests/unit/coherence/test_scope_selection.py
git commit -m "feat(coherence): define fail-closed feature scope selection"
```

### Task 6.2: Add `--scope` to trace check

**Objective:** Filter reporting, never semantics.

**Files:**

- Modify: `src/coherence/trace/cli.py`
- Create or modify: `tests/unit/trace/test_cli.py`

**Behavior:**

```text
coherence trace check --scope feat:FEAT-017 --project-root .
```

- builds the full graph once;
- filters gaps to owned SRs and selected FEAT-017 tasks;
- separately reports shared dependency findings;
- exits non-zero for any pending in-scope finding;
- does not hide or mutate the global gate.

**TDD command:**

```bash
uv run pytest tests/unit/trace/test_cli.py -q -o addopts=''
```

Expected: tests cover in-scope pending, out-of-scope exclusion, shared dependency visibility, malformed scope, and unchanged global results.

**Commit after authorization:**

```bash
git add src/coherence/trace/cli.py tests/unit/trace/test_cli.py
git commit -m "feat(trace): add fail-closed feature-scoped check"
```

### Task 6.3: Add `--scope` to register check

**Objective:** Report closure only for owned requirements while preserving dependency visibility.

**Files:**

- Modify: `src/coherence/register/cli.py`
- Create or modify: `tests/unit/register/test_cli.py`

**Behavior:**

```text
coherence register check --scope feat:FEAT-017 --project-root .
```

- classifies all requirements using existing logic;
- renders owned FEAT-017 findings as gating;
- renders `SR-050`, `SR-035`, and `SR-036` as shared dependency state;
- never treats a task link as measured-passing;
- never changes the global `register check` behavior.

**TDD command:**

```bash
uv run pytest tests/unit/register/test_cli.py -q -o addopts=''
```

Expected: pass after implementation; new tests prove proposed/allocated/verified remain distinct.

**Commit after authorization:**

```bash
git add src/coherence/register/cli.py tests/unit/register/test_cli.py
git commit -m "feat(register): add feature-scoped closure reporting"
```

### Task 6.4: Add `--scope` to membership gate

**Objective:** Require complete FEAT-017 dossier membership without bundling unrelated historical documents.

**Files:**

- Modify: `src/coherence/navigate/coverage.py`
- Modify: `src/coherence/navigate/cli.py`
- Modify: `tests/unit/coherence/test_navigate_bundles.py`

**Behavior:**

```text
coherence navigate membership --scope feat:FEAT-017 --gate --repo-root . --json
```

- gates the selected scope only;
- includes owned SRs, FEAT-017 tasks, canonical spec/plan, and declared FEAT-017 historical handoff;
- excludes global unrelated documents;
- rejects foreign SR membership;
- leaves the existing unscoped global command unchanged.

**TDD command:**

```bash
uv run pytest tests/unit/coherence/test_navigate_bundles.py -q -o addopts=''
```

Expected: scoped fixture passes; removing one FEAT-017 task makes it fail; global fixture result remains unchanged.

**Commit after authorization:**

```bash
git add src/coherence/navigate/coverage.py src/coherence/navigate/cli.py tests/unit/coherence/test_navigate_bundles.py
git commit -m "feat(navigate): gate feature-scoped membership"
```

### Task 6.5: Compose a scoped FEAT-017 readiness command

**Objective:** Provide one projection without creating a second assurance authority.

**Files:**

- Prefer modifying existing `src/coherence/navigate/health.py` and `src/coherence/navigate/cli.py`; do not invent a new top-level CLI group.
- Modify: relevant `tests/unit/system/` or `tests/unit/coherence/` health tests.

**Behavior:**

```text
coherence navigate health --scope feat:FEAT-017 --repo-root . --json
```

The result must include independent dimensions for:

- authority/spec/plan freshness;
- seven-SR ownership;
- individual consent count;
- task dependency/acceptance status;
- scoped trace;
- scoped register closure;
- scoped membership;
- planning gate-pack status;
- verification evidence status;
- human review status;
- non-starting handoff status.

Worst-outcome composition remains fail-closed. A green mechanical dimension cannot override missing consent or verification.

**Verification:**

```bash
uv run pytest tests/unit/coherence/test_navigate_health.py tests/unit/coherence/test_status.py -q -o addopts=''
uv run coherence navigate health --scope feat:FEAT-017 --repo-root . --json
```

Expected now: structured non-green output naming exactly the unresolved FEAT-017 dimensions. Green is not expected until later phases complete.

**Commit after authorization:**

```bash
git add src/coherence/navigate/health.py src/coherence/navigate/cli.py tests/unit/coherence/test_navigate_health.py tests/unit/coherence/test_status.py
git commit -m "feat(navigate): compose scoped feature readiness"
```

---

## Phase 7 — Execute remaining FEAT-017 tasks without reopening accepted slices

### Task 7.1: Reconcile the canonical task graph after Claude integration

**Objective:** Determine the first legal unaccepted task.

**Files:**

- Read: `tasks/T-032-*.md` through `tasks/T-045-*.md`
- Read: accepted commit/review records
- Modify only if factual projection drift is proven: affected task file and canonical plan

**Rules:**

- Preserve T-032/T-033 as accepted unless their exact accepted boundary changed.
- T-034 cannot be accepted from commit titles or passing dirty-worktree tests.
- Every later task remains blocked until its `depends_on` predecessor has an accepted exact revision and fresh review evidence.
- Delete obsolete Kanban implementation artifacts; never implement or revive them.
- Do not let T-044 modify `SR-050`.

**Verification:**

```bash
uv run coherence navigate brief --scope feat:FEAT-017 --repo-root . --json
uv run pytest tests/unit/coherence/test_planning_trace_contract.py -q -o addopts=''
```

Expected: exact task ordering and owned-SR mapping; no obsolete transport references in active artifacts.

### Task 7.2: Implement T-034 through T-044 one task at a time

**Objective:** Follow the canonical plan without duplicating accepted Claude work.

For each task:

1. Re-read its exact `## Files`, acceptance, `depends_on`, source anchor, and verification node.
2. Confirm the predecessor’s exact accepted SHA and reviews.
3. Create an isolated worktree from the current integration head.
4. Write one failing test first and observe the expected RED.
5. Implement only the minimal task scope.
6. Run the task’s focused tests, Ruff, Pyright, and `git diff --check`.
7. Commit with scoped `git add`; never use `git add -A`.
8. Parent verifies the SHA from a clean snapshot.
9. Dispatch one fresh broad reviewer; on a concrete in-contract defect, use one fresh fixer and one re-review.
10. Integrate only after explicit authorization.

**Stop conditions:** two fix cycles, 30 minutes of review/fix work, changed architecture, cross-owner file requirement, or missing human decision.

### Task 7.3: Preserve implementation/planning separation

**Objective:** Prevent FEAT-017 from executing downstream implementation gates.

**Required assertions in existing tests:**

```python
assert handoff["starts_automatically"] is False
assert handoff["prerequisites"] == ["human_review", "requirement_consent"]
assert no_implementation_gate_was_executed
assert no_implementation_evidence_was_created
```

Use the final accepted APIs rather than these placeholder variable names. If no observable seam exists for the third and fourth assertions, add a narrow recorder/spy fixture; do not weaken them to prose.

---

## Phase 8 — Dogfood and acceptance

### Task 8.1: Build the clean planning lifecycle fixture

**Files:**

- Create/modify: `tests/fixtures/planning-dogfood/`
- Modify: `tests/integration/coherence/test_planning_dogfood.py`

**Scenarios:**

1. clean initial run;
2. interruption and deterministic resume;
3. stale artifact hash;
4. malformed or contradictory run-store record;
5. failed review;
6. fresh fixer and mandatory re-review;
7. missing individual consent;
8. one rejected/deferred candidate among accepted candidates;
9. changed SR after consent;
10. missing required planning gate;
11. unevidenced or downgraded planning gate;
12. valid non-starting handoff;
13. attempted automatic downstream start;
14. corrupted DecisionFile projection with intact authority store;
15. damaged authority store with plausible projections.

**TDD cycle:** add one scenario at a time, observe RED, implement minimally, rerun GREEN, commit only after the scenario and adjacent suite pass.

### Task 8.2: Run the final scoped and representative campaign

```bash
uv run pytest tests/unit/coherence/test_planning_*.py -q -o addopts=''
uv run pytest tests/unit/substrate/test_verification_record_schema.py tests/unit/substrate/test_planning_sr_decision_schema.py -q -o addopts=''
uv run pytest tests/integration/coherence/test_planning_dogfood.py tests/integration/packaging/test_schema_package_data.py -q -o addopts=''
uv run ruff check src/coherence/planning src/coherence/navigate src/coherence/register src/coherence/trace src/coherence/scope.py tests/unit/coherence tests/unit/substrate tests/integration/coherence tests/integration/packaging
uv run pyright src/coherence/planning src/coherence/navigate src/coherence/register src/coherence/trace src/coherence/scope.py
uv run coherence trace check --scope feat:FEAT-017 --project-root .
uv run coherence register check --scope feat:FEAT-017 --project-root .
uv run coherence navigate membership --scope feat:FEAT-017 --gate --repo-root . --json
uv run coherence navigate health --scope feat:FEAT-017 --repo-root . --json
git diff --check
```

Expected:

- all focused/unit/integration commands exit `0` with exact counts recorded;
- scoped trace/register/membership are green only if real bindings, accepted tasks, and evidence exist;
- scoped health includes a real human-review dimension;
- global trace/register/membership debt is reported separately and is not claimed resolved;
- no downstream workflow started.

### Task 8.3: Fresh holistic review

**Objective:** Review the complete exact integration revision after all fixes.

Reviewer must check:

- exact FEAT-017 owned-SR set;
- no modification or ownership of `SR-050`, `SR-035`, or `SR-036`;
- no Kanban planning authority or dead obsolete transport;
- production wiring, not merely exported dead code;
- run-store authority and derived-only projections;
- path/reparse/hard-link boundaries;
- bounded JSON, hashing, journals, diagnostics, and retries;
- individual human consent and stale-hash invalidation;
- gate-pack integrity and no silent downgrade;
- package-installed schema availability;
- clean fixture and repository dogfood evidence;
- non-starting handoff;
- no secret/credential persistence.

A malformed or incomplete review verdict fails closed.

### Task 8.4: Present separate final decisions

Do not combine these approvals. Present them in order:

1. implementation acceptance for exact commits;
2. canonical projection reconciliation;
3. individual SR consent/adoption;
4. integration/cherry-pick authorization;
5. merge authorization;
6. push authorization;
7. release authorization;
8. downstream execution authorization.

No later decision is implied by an earlier one.

---

## Tests and validation summary

| Concern | Primary tests |
|---|---|
| Claude candidate provenance | clean detached worktree tests at each exact SHA |
| Bundle/consent consistency | `tests/unit/coherence/test_planning_gates.py`, `test_planning_trace_contract.py` |
| Bundle-check performance | `tests/unit/coherence/test_navigate_bundles.py` scan-count regression |
| Verification schema packaging | `tests/integration/packaging/test_schema_package_data.py` |
| Verification record compatibility | `tests/unit/substrate/test_verification_record_schema.py` |
| Individual SR decision schema | `tests/unit/substrate/test_planning_sr_decision_schema.py` |
| Decision authority/invalidation | planning runner, resolution, and review-resolution tests |
| Scoped trace/register/membership | trace/register CLI tests, navigate bundle tests |
| Scoped composed health | navigate health/status tests |
| End-to-end lifecycle | `tests/integration/coherence/test_planning_dogfood.py` |

Every source-changing task follows RED → verify RED → minimal GREEN → focused regression → Ruff/Pyright → scoped commit → parent exact-SHA verification → fresh review.

---

## Risks and tradeoffs

1. **Parallel-work collision:** Claude may resume after this snapshot. Recheck ownership immediately before implementation; never edit its worktree concurrently.
2. **Large dirty candidate:** The Claude worktree’s uncommitted plan/spec rewrite deletes thousands of lines. Treat it as a proposal requiring an exact handoff, not as progress to preserve at any cost.
3. **Accepted-slice regression:** Integrating `212eff6` may alter already accepted T-033 behavior. Preserve the accepted boundary and exclude or separately authorize any change.
4. **Bundle semantics:** Allowing spec/plan/task members must not weaken exact SR ownership. The validator therefore requires all seven owned SRs and rejects every foreign SR.
5. **Scope self-certification:** A scoped gate cannot trust a bundle alone to define its own scope. Cross-check feature frontmatter, requirement files, task justification, and bundle membership.
6. **Consent forgery:** A JSON file with `reviewer: human` is not proof of human authority. Bind decisions to parent-owned authority events and keep files as projections.
7. **Packaging portability:** Tests that read schemas from the source tree can pass while installed wheels fail. The wheel-content test is mandatory.
8. **Historical-artifact policy:** This plan does not globally migrate all 134 spec/plan documents to lifecycle metadata. Scoped FEAT-017 readiness is implemented first; repository-wide historical classification should be a separately owned feature to avoid laundering old documents into active bundles.
9. **Global debt remains:** Scoped green does not make the global trace/register/membership gates green. Report both states.
10. **Performance thresholds:** Avoid flaky wall-clock unit tests. Count repository scans deterministically; use the 15-second real-command bound only as an integration smoke check.
11. **Runner API drift:** T-034 is still unaccepted and Claude may change its interfaces. Re-read the accepted runner before implementing Phase 5; update this plan rather than adapting code by guesswork.
12. **Migration compatibility:** Preserve legacy `evidence_manifest.validation` and aggregate consent files as readable historical formats. Additive contracts must not reinterpret legacy records as current authority.

---

## Open questions requiring explicit decisions

1. Which exact Claude commits, if any, are authorized for integration after clean review?
2. Is `212eff6` identical to the accepted T-033 boundary, an unauthorized extension, or a replacement candidate?
3. Should the 2026-08-31 FEAT-017 requirements handoff remain an active bundle member or move to an explicitly historical archive class when repository-wide artifact lifecycle metadata is implemented?
4. What are the exact approved acceptance criteria and verification bindings for each of the seven FEAT-017 SRs?
5. Does the parent human-input adapter already expose an unforgeable attestation seam suitable for individual SR decisions, or must that seam be specified before Phase 5?
6. Should feature-scoped health be required for FEAT-017 adoption immediately, or land first as advisory while global health remains red?
7. Is schema wheel packaging part of the FEAT-007/SR-024 acceptance boundary, or a separate packaging task that FEAT-017 may depend on?
8. After scoped FEAT-017 health is green, should global historical membership debt be handled by archive lifecycle metadata, owner-by-owner bundles, or a combination? This is deliberately outside FEAT-017 ownership.
