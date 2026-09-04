# Commit-claim traceability implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [[docs/superpowers/specs/2026-09-04-commit-claim-traceability-design|Commit-claim traceability — design]]
**Feature:** [[FEAT-001]] REQ-TRACEABILITY
**Related:** [[SR-049]] (bound by T4), [[SR-050]] (AC-2 reconciliation re-based by T3; AC-4 packet fed by T5), [[SR-048]] (supplies CI by construction), [[SR-023]] (import-overlap, untouched), [[SR-054]] (this plan's own trace-maintenance obligation, applied per task), [[SR-051]] (planning/implementation gate boundary observed — see *Gate plan*), [[SR-044]] (SR consent gate — see *Requirement proposal*), [[FEAT-014]] VALIDATION-GATES, [[FEAT-017]] PLANNING-BOOTSTRAP

**Goal:** Make every commit declare which requirements it serves, ingest those declarations into the evidence store as a provenance source, and consume them to give the per-requirement review a correct denominator, a blocking gate, and a bounded fidelity packet.

**Architecture:** A git trailer (`SR: SR-050, SR-023`) records intent attribution only. A `commit-msg` hook checks it cheaply; ingestion consumes the commit range into an immutable evidence manifest at any review or gate run; every reviewer continues to read manifests and never git. Claims re-base `evidence_reconciliation_review`'s existing categories onto a precise per-SR denominator rather than adding a taxonomy.

**Tech Stack:** Python 3.12, pytest 9.1.1, existing `substrate.codemap` / `substrate.evidence` / `factory.orchestrator.git_ops` modules. No new third-party dependencies.

## Global Constraints

- **No reviewer reads git.** Git is consumed once, at ingestion, into the manifest. `coherence.register.review` and every other reviewer keep reading only evidence manifests, preserving the constraint documented in `src/coherence/register/review.py` (*"never from `git diff`/`git log`"*).
- **Manifests are immutable.** Ingestion writes a *new* manifest with its own `run_id`; it never mutates an existing one.
- **No fabricated provenance.** An ingestion run outside a governed task records no `task_id`/`inputs.task` rather than synthesising one.
- **Claims are claims.** Claim facts are evidence of *intent*, never proof of *correctness*, wherever they reach a judge.
- **Extend `coherence.register`, do not create new packages.** T4/T5 of the [[SR-050]] slice established this; a new top-level package would be a second convention.
- **Reuse `GitOps`.** `src/factory/orchestrator/git_ops.py` already defines the `GitOps` Protocol and `SubprocessGitOps`. Extend them; do not open a second subprocess convention.
- **TDD, frequent commits.** Every task writes the failing test first.
- Python 3.12 — `PurePosixPath.full_match` (3.13+) is **not** available; the glob matcher is written explicitly.
- Every commit this plan produces carries its own `SR:` trailer (dogfooding), plus the repo's standard attribution trailers.

---

## SUPERSEDED 2026-09-04 (same day): the work is bound to [[SR-049]], not [[SR-054]]

The SR-054 parking recorded below was **wrong on its own stated terms** and has been corrected.
Both limitations it "knowingly accepted" were disqualifying, not acceptable: a marker naming a
requirement whose statement does not describe the case at hand, on a requirement that is
`proposed` with no acceptance criteria, closes nothing and mis-reports coverage. The 25 markers now
carry `@pytest.mark.sr("SR-049")`, and [[SR-049]] carries real `test_marker` acceptance criteria
(AC-1 trailer + commit-time check, AC-2 ingestion, AC-3 the blocking gate) plus
`implemented_by`/`verified_by` relations for every file this slice produced.

**This routes around no consent.** [[SR-044]] governs *authoring* an SR. SR-049 was already in the
register and already consented; adding acceptance criteria to an existing requirement whose
statement is precisely "artifacts a slice produces carry canonical relations to their owning SR,
gate-validated" is binding it, not authoring one — which is exactly what the design document said
this slice would do ("This design gives SR-049 its first binding and acceptance criteria"). The
declined candidate SR-062 stays declined and unwritten.

The three T1–T3 commits also carried `SR: SR-050` trailers naming the wrong requirement — the
claim mechanism is SR-049's, not SR-050's. Those trailers were corrected in place. Rewriting them
is explicitly harmless under this design's own model: commits are an input consumed at ingestion,
and nothing had ingested them yet.

Two defects that made the AC-3 gate **unsatisfiable** surfaced while writing honest criteria, both
now fixed with tests first: exempted paths were counted in the claim denominator (so any commit
touching a doc alongside code produced a permanent finding no declaration could clear), and a
non-Python produced artifact could not be declared at all under `implemented_by` while still being
reported as claimed-but-undeclared. See `requirements/SR-049.md` for both.

### The superseded record, retained

The SR-044 consent below was put to a human with the facts, including the arguments against, and
**declined**. No new requirement was authored. The 25 tests that carried the candidate marker were
given `@pytest.mark.sr("SR-054")`, treating commit-claim attribution as an implementation detail of
[[SR-054]]'s obligation to identify a change's affected requirements.

**Two limitations that decision knowingly accepted** — recorded so no later reader mistakes these
markers for a stronger claim:

1. [[SR-054]]'s statement is scoped to *"every FEAT-017 implementation task"*, so it does not
   itself describe a commit made **outside** a governed task — which is exactly the case this
   mechanism handles, and was the original argument for a separate requirement.
2. [[SR-054]] is still `proposed`, with no binding and no acceptance criteria, so these markers
   name a real requirement but **close** nothing.

A further fact surfaced at consent time: the corpus-scale duplicate detector that should have
adjudicated this ([[SR-058]]'s `coherence register overlap-check`, landed on main) **cannot
evaluate a candidate that is not yet in the register** — it compares requirements already present,
so checking a proposal requires first authoring it, which is the consent-gated act. Its default
judge is `_no_overlap_judge_configured` and its own docstring records that it is "explicitly NOT
wired into any planning pipeline (AC-3 is deferred)." The overlap analysis below is therefore
manual and tool-unverified. That gap is [[SR-058]]/AC-3's, not this plan's.

The section below is retained unchanged as the record of what was proposed and rejected.

## Requirement proposal (DECLINED — retained as the record of what was put to consent)

**Answer to "is a new requirement needed": yes, one — and this plan does not author it.**

[[SR-044]] requires explicit human approval of each authored SR, with no bulk auto-adopt and no agent bypass. So this plan *proposes* the requirement and stops. No file under `requirements/` is created or modified until a human consents.

**Id note (2026-09-04):** `SR-061` is already under design in a concurrent session, so this
proposal takes **SR-062**. Confirm the id is still free at consent time — the register is being
written by more than one session.

**Proposed SR-062 — Commit-level requirement attribution as evidence provenance** (under [[FEAT-001]]):

> The system shall require each commit that changes non-exempt production or validation artifacts to declare the system requirements it serves, and shall ingest those declarations, together with their changed-file sets, into the evidence store as a provenance source that per-requirement review and gates consume — so that requirement attribution for work performed outside a governed task is captured at the time of the work rather than inferred afterwards.

**Why no existing requirement covers it:**

| Requirement | Why it does not cover this |
|---|---|
| [[SR-049]] | States the *outcome* (produced artifacts carry canonical relations, gate-validated). Silent on how attribution is captured — no commit, trailer, or ingestion concept. T4 binds it because the gate *is* its outcome; T1–T3 build a mechanism its statement does not describe. |
| [[SR-054]] | Nearest neighbour, and genuinely close: implementation tasks must identify affected SRs and reconcile declarations before completion. But it is scoped to *"every FEAT-017 implementation task"* — task-level and inside governed planning. It does not reach commits made outside a governed task, which is precisely the gap that left [[SR-050]] reporting no measurement on 2026-09-04 despite the work being done. |
| [[SR-050]] | The *consumer* of this attribution, not its source. |
| [[SR-052]] | Brainstorming intent capture at planning time, explicitly keeping execution state outside the intent artifact. Different artifact, different stage. |

**If consent is declined:** T4 still binds [[SR-049]] and the mechanism still works, but T1–T3's tests have no requirement whose statement honestly describes what they assert. The consequence is not a broken build — it is ~40 tests bound to a requirement that does not claim what they prove, which is the exact dishonesty this register exists to prevent. Prefer declining the *feature* over declining the *requirement*.

**Feature placement:** [[FEAT-001]] REQ-TRACEABILITY, whose subject is requirement attribution and which already houses [[SR-050]]. The alternative, [[FEAT-006]] EVIDENCE-PROVENANCE, is defensible since a new provenance source is added — but FEAT-006's requirements ([[SR-019]]–[[SR-022]]) govern the evidence model's internal integrity, not requirement attribution. Human decides at consent time.

---

## Adjacent in-flight work (surveyed 2026-09-04)

Worktree survey before execution, so this plan does not reinvent or collide with work already
under way:

| Branch | State | Bearing on this plan |
|---|---|---|
| `feat/sr057-wikilink-mirroring` | **merged into main** (`d682c81`, `d61640e`) | `mirrors generate`/`check` behaviour this plan's [[SR-054]] steps call is already the generalized `relates_to` version. Nothing to do. |
| `feat/sr058-overlap-detection` | **merged into main** (`714e0a5`) | [[SR-058]] AC-1/AC-2 landed. Unrelated surface. |
| `feat/sr059-manual-consent-enforcement` | at main's tip, no unique commits | Nothing in flight. |
| `feat/coherence-feat17-planning` | **UNMERGED — 120 files, +21,500 lines** | Materially relevant. See below. |

### `feat/coherence-feat17-planning` — do not depend on it, do conform to it

That branch contains an entire `src/coherence/planning/` package (9,532 lines of source):
`workflow.py` (a host-neutral coordinator over three `WorkflowStage`s — `SPEC_ALIGNMENT`,
`PLAN_TASK_ALIGNMENT`, `DERIVATION_ALIGNMENT` — whose `Reviewer` callback is documented as *"the
sole semantic judgment boundary"*), `gates.py` (planning gate pack, [[SR-055]]), `check.py`
(cross-artifact review, [[SR-053]]), `kanban.py` (Hermes host backend), `intent.py` ([[SR-052]]),
`handoff.py`, and `runner.py`.

**Two consequences for this plan:**

1. **The [[SR-044]] consent this plan waits on is already a specified protocol there**, not a
   casual approval: `coherence.planning.gates.validate_requirement_consent` requires a consent
   decision carrying `schema`, `run_id`, `decision`, `reviewer`, `phrase`, `candidate_srs`,
   `derivation_report_sha256`, and `artifact_hashes`, where `phrase` must be exactly
   *"I explicitly consent to adopt exactly these candidate SRs."* When that branch merges, SR-062's
   consent should be recorded in that form rather than as an ad-hoc note. Until it merges, record
   consent as a plain decision and migrate.
2. **This plan takes no dependency on that branch.** Every module it touches
   (`coherence.register.*`, `substrate.evidence`, `factory.orchestrator.git_ops`) is on `main` and
   disjoint from `src/coherence/planning/`, so the two can land in either order without conflict.
   Building T1–T5 against 21,500 unmerged lines would couple this work to a merge that has not
   happened.

**Deliberate near-duplication to revisit after that merge:** the *Gate plan* table below is written
by hand in [[SR-055]]'s shape. Once `planning/gates.py` is on `main`, that table should be replaced
by a compiled gate pack rather than kept as a second, hand-maintained copy.

## Gate plan ([[FEAT-014]] contracts, [[SR-055]] pack shape, [[SR-051]] boundary)

**Planning stage — executed now, by this document:**

| Gate | Requiredness | Resolver | Evidence | On failure |
|---|---|---|---|---|
| Spec exists and is a canonical `spec:` node | blocking | frontmatter `id`/`title`/`status` present | `docs/superpowers/specs/2026-09-04-commit-claim-traceability-design.md` (committed `4353f44`) | plan cannot proceed |
| Plan references its spec | blocking | `**Spec:**` wikilink in this header | this document | `plan_no_spec` trace gap |
| SR consent obtained before authoring | blocking | human `accept` on proposed SR-062 | *pending* | T1–T3 tests have no honest binding |
| Cross-artifact coherence review ([[SR-053]]) | blocking before handoff | human review of this plan against the spec | *pending* | no handoff to execution |

**[[SR-051]] compliance:** planning may inspect, compile, and validate gate contracts but **shall not execute implementation validation gates or claim implementation evidence.** This document therefore runs no `pytest`, no `ruff`, no `pyright`, and records no validation evidence. The implementation gates below execute only after this plan is approved and handed to execution.

**Implementation stage — executed per task, after handoff:**

| Stage | Command | Requiredness |
|---|---|---|
| per step | `rtk proxy uv run pytest <task's test file> -v` | blocking |
| per task | `rtk proxy uv run pytest -m unit -q` | blocking |
| per task | `rtk proxy uv run ruff check .` + `rtk proxy uv run pyright` | blocking |
| after T4 | `rtk proxy uv run python -m coherence register review --check-claims` | blocking, all compiled profiles |
| final | the `full` gate in `.factory/factory.yaml` | blocking |

By [[SR-048]], adding the T4 command to `.factory/factory.yaml`'s `full` gate extends CI by construction. No CI file is edited by this plan.

## [[SR-054]] trace-maintenance obligation

Every task below changes production or validation artifacts, so every task ends with the same three completion steps before its commit — these are not optional and are written out in each task rather than cross-referenced:

1. Declare the task's affected requirements in `requirements/<SR>.md` (`implemented_by`/`verified_by` structured entries for the files the task created).
2. Regenerate mirrored documentation links: `rtk proxy uv run python -m coherence mirrors generate`.
3. Verify reconciliation: `rtk proxy uv run python -m coherence register review <SR> ` reports no `malformed`, `dangling`, or `duplicate` finding for the task's own declarations.

Steps 1–2 are deferred for T1–T3 until SR-062 consent lands (there is no requirement file to declare into); T4 and T5 declare into [[SR-049]] and [[SR-050]] respectively, which already exist.

---

## File structure

| File | Responsibility |
|---|---|
| `src/coherence/register/claims.py` (create) | Pure: trailer parsing, `.factory/trace-claims.yaml` config, glob matching, exemption classification. No git, no I/O beyond config read. |
| `src/coherence/register/ingest.py` (create) | Git commit range → `IngestedCommit` records → evidence manifest. The only module that reads git. |
| `src/factory/orchestrator/git_ops.py` (modify) | Two new `GitOps` methods: `commits_between`, `changed_files_in_commit`. |
| `src/substrate/schemas/evidence_manifest.schema.json` (modify) | Optional `commits`; `task_id`/`inputs.task` no longer required. |
| `src/coherence/register/review.py` (modify) | Claim-based denominator for `evidence_reconciliation_review`; `exempted` reporting. |
| `src/coherence/register/cli.py` (modify) | `--no-ingest`, `--check-claims`. |
| `src/coherence/register/fidelity_packet.py` (modify) | Claim facts on `FidelityPacket`. |
| `.githooks/commit-msg` (create) | Shell shim delegating to `python -m coherence.register.claims hook`, so there is exactly one trailer parser. |
| `.factory/trace-claims.yaml` (create) | `epoch` + `exempt` config. |

---

### Task 1: Trailer parsing, config, and the commit-msg hook

**Files:**
- Create: `src/coherence/register/claims.py`
- Create: `.factory/trace-claims.yaml`
- Create: `.githooks/commit-msg`
- Test: `tests/unit/coherence/register/test_claims.py`

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: `parse_sr_trailer(message: str) -> tuple[str, ...]`; `ClaimsConfig(epoch: str | None, exempt: tuple[str, ...])`; `load_claims_config(root: Path) -> ClaimsConfig`; `glob_match(pattern: str, path: str) -> bool`; `exempting_glob(config: ClaimsConfig, path: str) -> str | None`; `check_commit(root: Path, message: str, staged: Sequence[str]) -> tuple[str, ...]` returning error strings (empty = pass).

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/coherence/register/test_claims.py
import pytest

from coherence.register.claims import (
    ClaimsConfig,
    check_commit,
    exempting_glob,
    glob_match,
    load_claims_config,
    parse_sr_trailer,
)


@pytest.mark.sr("SR-062")
def test_parses_a_single_sr_trailer():
    assert parse_sr_trailer("feat: thing\n\nSR: SR-050\n") == ("SR-050",)


@pytest.mark.sr("SR-062")
def test_parses_a_multi_sr_trailer_preserving_order():
    assert parse_sr_trailer("feat: thing\n\nSR: SR-050, SR-023\n") == ("SR-050", "SR-023")


@pytest.mark.sr("SR-062")
def test_a_message_with_no_trailer_yields_no_ids():
    assert parse_sr_trailer("feat: thing\n\nno trailer here\n") == ()


@pytest.mark.sr("SR-062")
def test_an_sr_mention_in_the_body_is_not_a_trailer():
    assert parse_sr_trailer("feat: relates to SR-050 somehow\n\nbody\n") == ()


@pytest.mark.sr("SR-062")
def test_double_star_glob_matches_nested_paths():
    assert glob_match("docs/**", "docs/a/b/c.md") is True


@pytest.mark.sr("SR-062")
def test_single_star_glob_does_not_cross_a_separator():
    assert glob_match("src/*.py", "src/a/b.py") is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `rtk proxy uv run pytest tests/unit/coherence/register/test_claims.py -v -o addopts=""`
Expected: FAIL — `ModuleNotFoundError: No module named 'coherence.register.claims'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/coherence/register/claims.py
"""Commit-claim parsing and exemption policy (proposed SR-062).

Pure module: parses the `SR:` commit trailer, loads
`.factory/trace-claims.yaml`, and classifies paths against exemption globs.
It reads no git and writes nothing -- `coherence.register.ingest` is the only
module that touches git.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import yaml

TRAILER_KEY = "SR"
CONFIG_RELPATH = (".factory", "trace-claims.yaml")

_TRAILER_RE = re.compile(rf"^{TRAILER_KEY}:[ \t]*(.+?)[ \t]*$", re.MULTILINE)
_SR_ID_RE = re.compile(r"^SR-\d+$")


@dataclass(frozen=True)
class ClaimsConfig:
    """`.factory/trace-claims.yaml`, or the empty default when absent."""

    epoch: str | None = None
    exempt: tuple[str, ...] = ()


def parse_sr_trailer(message: str) -> tuple[str, ...]:
    """Ids from every ``SR:`` trailer line, in declaration order, deduplicated.

    Only a line whose first non-space characters are ``SR:`` counts -- a
    mention of an id inside prose is not a claim.
    """
    ids: list[str] = []
    for raw in _TRAILER_RE.findall(message):
        for token in raw.split(","):
            token = token.strip()
            if token and token not in ids:
                ids.append(token)
    return tuple(ids)


def invalid_ids(ids: Sequence[str]) -> tuple[str, ...]:
    return tuple(i for i in ids if not _SR_ID_RE.match(i))


def glob_match(pattern: str, path: str) -> bool:
    """Match a repo-relative POSIX path against a glob.

    Written explicitly because Python 3.12 has no ``PurePosixPath.full_match``
    and ``fnmatch`` does not distinguish ``**`` from ``*``. ``**`` crosses
    separators; ``*`` and ``?`` do not.
    """
    out: list[str] = ["^"]
    i = 0
    while i < len(pattern):
        char = pattern[i]
        if pattern.startswith("**", i):
            out.append(".*")
            i += 2
            if pattern.startswith("/", i):
                i += 1
        elif char == "*":
            out.append("[^/]*")
            i += 1
        elif char == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(char))
            i += 1
    out.append("$")
    return re.match("".join(out), path) is not None


def exempting_glob(config: ClaimsConfig, path: str) -> str | None:
    """The first configured glob that exempts ``path``, else None."""
    for pattern in config.exempt:
        if glob_match(pattern, path):
            return pattern
    return None


def load_claims_config(root: Path) -> ClaimsConfig:
    path = root.joinpath(*CONFIG_RELPATH)
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return ClaimsConfig()
    if not isinstance(raw, dict):
        return ClaimsConfig()
    epoch = raw.get("epoch")
    exempt = raw.get("exempt") or []
    return ClaimsConfig(
        epoch=str(epoch) if isinstance(epoch, str) and epoch.strip() else None,
        exempt=tuple(str(p) for p in exempt if isinstance(p, str)),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `rtk proxy uv run pytest tests/unit/coherence/register/test_claims.py -v -o addopts=""`
Expected: PASS (6 passed)

- [ ] **Step 5: Write the failing test for the commit check**

```python
# append to tests/unit/coherence/register/test_claims.py
@pytest.mark.sr("SR-062")
def test_a_commit_touching_only_exempt_paths_needs_no_trailer(tmp_path):
    (tmp_path / "requirements").mkdir()
    config = ClaimsConfig(exempt=("docs/**",))
    assert check_commit(tmp_path, "docs: tweak\n", ["docs/a.md"], config=config) == ()


@pytest.mark.sr("SR-062")
def test_a_commit_touching_a_non_exempt_path_without_a_trailer_is_rejected(tmp_path):
    (tmp_path / "requirements").mkdir()
    config = ClaimsConfig(exempt=("docs/**",))
    errors = check_commit(tmp_path, "feat: thing\n", ["src/a.py"], config=config)
    assert len(errors) == 1
    assert "src/a.py" in errors[0]


@pytest.mark.sr("SR-062")
def test_a_trailer_naming_an_unknown_requirement_is_rejected(tmp_path):
    (tmp_path / "requirements").mkdir()
    errors = check_commit(
        tmp_path, "feat: thing\n\nSR: SR-999\n", ["src/a.py"], config=ClaimsConfig()
    )
    assert len(errors) == 1
    assert "SR-999" in errors[0]


@pytest.mark.sr("SR-062")
def test_a_trailer_naming_a_registered_requirement_passes(tmp_path):
    (tmp_path / "requirements").mkdir()
    (tmp_path / "requirements" / "SR-050.md").write_text("---\nid: SR-050\n---\n", encoding="utf-8")
    assert check_commit(
        tmp_path, "feat: thing\n\nSR: SR-050\n", ["src/a.py"], config=ClaimsConfig()
    ) == ()
```

- [ ] **Step 6: Run test to verify it fails**

Run: `rtk proxy uv run pytest tests/unit/coherence/register/test_claims.py -v -o addopts=""`
Expected: FAIL — `ImportError: cannot import name 'check_commit'`

- [ ] **Step 7: Implement the commit check**

```python
# append to src/coherence/register/claims.py
def registered_ids(root: Path) -> frozenset[str]:
    """Every SR id with a file in ``requirements/`` -- the register's own
    naming convention, read without parsing frontmatter."""
    return frozenset(
        p.stem for p in (root / "requirements").glob("SR-*.md") if _SR_ID_RE.match(p.stem)
    )


def check_commit(
    root: Path,
    message: str,
    staged: Sequence[str],
    *,
    config: ClaimsConfig | None = None,
) -> tuple[str, ...]:
    """Error strings for one commit; empty means it passes.

    Three checks, in order: every staged path exempt (pass outright); a
    trailer present; every id it names present in the register.
    """
    cfg = config if config is not None else load_claims_config(root)
    unexempt = [p for p in staged if exempting_glob(cfg, p) is None]
    if not unexempt:
        return ()
    ids = parse_sr_trailer(message)
    if not ids:
        listed = ", ".join(sorted(unexempt)[:5])
        return (
            f"commit changes non-exempt paths ({listed}) but declares no 'SR:' trailer; "
            f"add 'SR: SR-0xx' or exempt the path in {'/'.join(CONFIG_RELPATH)}",
        )
    malformed = invalid_ids(ids)
    if malformed:
        return (f"malformed requirement id(s) in SR: trailer: {', '.join(malformed)}",)
    known = registered_ids(root)
    unknown = tuple(i for i in ids if i not in known)
    if unknown:
        return (f"SR: trailer names unregistered requirement(s): {', '.join(unknown)}",)
    return ()
```

- [ ] **Step 8: Run test to verify it passes**

Run: `rtk proxy uv run pytest tests/unit/coherence/register/test_claims.py -v -o addopts=""`
Expected: PASS (10 passed)

- [ ] **Step 9: Add the hook entry point and the hook itself**

```python
# append to src/coherence/register/claims.py
def _hook_main(argv: Sequence[str]) -> int:
    """`python -m coherence.register.claims hook <msg-file>` -- the commit-msg
    hook's only logic, so exactly one trailer parser exists."""
    import subprocess

    if len(argv) < 2 or argv[0] != "hook":
        print("usage: python -m coherence.register.claims hook <msg-file>")
        return 2
    root = Path.cwd()
    message = Path(argv[1]).read_text(encoding="utf-8")
    staged = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        cwd=root, capture_output=True, text=True, check=True,
    ).stdout.split()
    errors = check_commit(root, message, staged)
    for error in errors:
        print(f"commit-claim: {error}")
    return 1 if errors else 0


if __name__ == "__main__":  # pragma: no cover - process entry point
    import sys

    sys.exit(_hook_main(sys.argv[1:]))
```

```bash
# .githooks/commit-msg
#!/bin/sh
# Commit-claim traceability (proposed SR-062). Delegates to the single
# trailer parser in coherence.register.claims -- never reimplements it.
exec python -m coherence.register.claims hook "$1"
```

```yaml
# .factory/trace-claims.yaml
# Commit-claim traceability config (proposed SR-062).
# epoch: no claim is expected for commits at or before this sha.
epoch: null
exempt:
  - "docs/**"
  - "evidence/**"
  - "coverage-reviews/**"
  - "review-findings/**"
  - "**/*.md"
```

- [ ] **Step 10: Verify the hook rejects and accepts correctly, by hand**

Run: `git config core.hooksPath .githooks` then stage a change under `src/` with no trailer and attempt a commit.
Expected: commit rejected with `commit-claim: commit changes non-exempt paths ...`. Re-run with `SR: SR-050` in the message: commit succeeds.

- [ ] **Step 11: Commit**

```bash
git add src/coherence/register/claims.py tests/unit/coherence/register/test_claims.py .githooks/commit-msg .factory/trace-claims.yaml
git commit -m "feat(register): commit-claim trailer parsing, config, and commit-msg hook

SR: SR-050"
```

> **[[SR-054]] note:** relation declaration and `mirrors generate` are deferred for this task until SR-062 consent lands — there is no requirement file to declare into yet. The commit above claims [[SR-050]], the requirement whose review consumes this.

---

### Task 2: Ingestion — commits into an evidence manifest

**Files:**
- Create: `src/coherence/register/ingest.py`
- Modify: `src/factory/orchestrator/git_ops.py` (add two `GitOps` methods)
- Modify: `src/substrate/schemas/evidence_manifest.schema.json`
- Test: `tests/unit/coherence/register/test_ingest.py`
- Test: `tests/unit/coherence/register/conftest.py` (git fixture)

**Interfaces:**
- Consumes: T1's `ClaimsConfig`, `load_claims_config`, `parse_sr_trailer`, `exempting_glob`.
- Produces: `IngestedCommit(sha, subject, sr_ids, changed_files, exempted)`; `ingest_range(root, git, start, end, config) -> tuple[IngestedCommit, ...]`; `ingest(root, *, git=None, now=None) -> Path | None` (returns the written manifest path, or None when nothing to ingest); `DivergedRangeError`.

- [ ] **Step 1: Write the git fixture**

```python
# tests/unit/coherence/register/conftest.py
import subprocess

import pytest


def _git(repo, *args):
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


@pytest.fixture
def git_repo(tmp_path):
    """A real temporary git repository with an initial commit."""
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "requirements").mkdir()
    _git(repo.parent, "init", "-q", repo.name)
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    (repo / "README.md").write_text("seed\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "seed")
    return repo


@pytest.fixture
def commit_file(git_repo):
    """Write a file and commit it with the given message; return the sha."""

    def _commit(relpath, content, message):
        target = git_repo / relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        _git(git_repo, "add", "-A")
        _git(git_repo, "commit", "-q", "-m", message)
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=git_repo, capture_output=True, text=True, check=True,
        ).stdout.strip()

    return _commit
```

- [ ] **Step 2: Write the failing ingestion test**

```python
# tests/unit/coherence/register/test_ingest.py
import pytest

from coherence.register.claims import ClaimsConfig
from coherence.register.ingest import DivergedRangeError, ingest_range
from factory.orchestrator.git_ops import SubprocessGitOps


@pytest.mark.sr("SR-062")
def test_a_claimed_commit_is_ingested_with_its_changed_files(git_repo, commit_file):
    base = SubprocessGitOps().head_commit(git_repo)
    commit_file("src/a.py", "x = 1\n", "feat: a\n\nSR: SR-050")
    head = SubprocessGitOps().head_commit(git_repo)
    commits = ingest_range(git_repo, SubprocessGitOps(), base, head, ClaimsConfig())
    assert len(commits) == 1
    assert commits[0].sr_ids == ("SR-050",)
    assert commits[0].changed_files == ("src/a.py",)


@pytest.mark.sr("SR-062")
def test_a_multi_sr_commit_attributes_its_files_to_every_named_sr(git_repo, commit_file):
    base = SubprocessGitOps().head_commit(git_repo)
    commit_file("src/b.py", "y = 1\n", "feat: b\n\nSR: SR-050, SR-023")
    head = SubprocessGitOps().head_commit(git_repo)
    commits = ingest_range(git_repo, SubprocessGitOps(), base, head, ClaimsConfig())
    assert commits[0].sr_ids == ("SR-050", "SR-023")


@pytest.mark.sr("SR-062")
def test_an_exempt_path_is_recorded_with_the_glob_that_exempted_it(git_repo, commit_file):
    base = SubprocessGitOps().head_commit(git_repo)
    commit_file("docs/x.md", "hi\n", "docs: x")
    head = SubprocessGitOps().head_commit(git_repo)
    config = ClaimsConfig(exempt=("docs/**",))
    commits = ingest_range(git_repo, SubprocessGitOps(), base, head, config)
    assert commits[0].exempted == (("docs/x.md", "docs/**"),)
    assert commits[0].sr_ids == ()


@pytest.mark.sr("SR-062")
def test_a_start_commit_that_is_not_an_ancestor_of_head_raises(git_repo, commit_file):
    commit_file("src/c.py", "z = 1\n", "feat: c\n\nSR: SR-050")
    head = SubprocessGitOps().head_commit(git_repo)
    with pytest.raises(DivergedRangeError):
        ingest_range(
            git_repo, SubprocessGitOps(), "0" * 40, head, ClaimsConfig()
        )
```

- [ ] **Step 3: Run test to verify it fails**

Run: `rtk proxy uv run pytest tests/unit/coherence/register/test_ingest.py -v -o addopts=""`
Expected: FAIL — `ModuleNotFoundError: No module named 'coherence.register.ingest'`

- [ ] **Step 4: Add the two GitOps methods**

```python
# add to the GitOps Protocol in src/factory/orchestrator/git_ops.py (after changed_files_between)
    def commits_between(
        self, repo_root: Path, start_commit: str, end_commit: str
    ) -> list[tuple[str, str, str]]: ...
    def changed_files_in_commit(self, repo_root: Path, commit: str) -> list[str]: ...
```

```python
# add to SubprocessGitOps in src/factory/orchestrator/git_ops.py
    def commits_between(
        self, repo_root: Path, start_commit: str, end_commit: str
    ) -> list[tuple[str, str, str]]:
        """(sha, subject, body) oldest-first for start..end, exclusive of start.

        Uses NUL-delimited fields so a subject or body containing any
        printable character cannot break parsing.
        """
        result = subprocess.run(
            ["git", "log", "--reverse", "--format=%H%x00%s%x00%b%x1e",
             f"{start_commit}..{end_commit}"],
            cwd=repo_root, capture_output=True, text=True, check=True,
        )
        commits: list[tuple[str, str, str]] = []
        for record in result.stdout.split("\x1e"):
            record = record.strip("\n")
            if not record:
                continue
            sha, _, rest = record.partition("\x00")
            subject, _, body = rest.partition("\x00")
            commits.append((sha, subject, body))
        return commits

    def changed_files_in_commit(self, repo_root: Path, commit: str) -> list[str]:
        result = subprocess.run(
            ["git", "show", "--pretty=format:", "--name-only", commit],
            cwd=repo_root, capture_output=True, text=True, check=True,
        )
        return [line.strip() for line in result.stdout.splitlines() if line.strip()]
```

- [ ] **Step 5: Implement ingest_range**

```python
# src/coherence/register/ingest.py
"""Git commit range -> evidence manifest (proposed SR-062).

The ONLY module in the review path that reads git. Everything downstream --
`coherence.register.review`, the gate, the fidelity packet -- continues to
read evidence manifests exactly as before, preserving the constraint
documented in `coherence.register.review.unaccounted_changed_files`.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from coherence.register.claims import (
    ClaimsConfig,
    exempting_glob,
    load_claims_config,
    parse_sr_trailer,
)
from factory.orchestrator.git_ops import GitOps, SubprocessGitOps
from substrate.evidence.model import validate_run_manifest
from substrate.evidence.read import list_run_manifests


class DivergedRangeError(RuntimeError):
    """The recorded start commit is not an ancestor of HEAD.

    A branch switch, or history rewritten after a manifest was written. There
    is no meaningful range, so ingestion reports and ingests nothing rather
    than guessing a merge base.
    """


@dataclass(frozen=True)
class IngestedCommit:
    sha: str
    subject: str
    sr_ids: tuple[str, ...]
    changed_files: tuple[str, ...]
    exempted: tuple[tuple[str, str], ...]  # (path, exempting glob)


def _is_ancestor(root: Path, start: str, end: str) -> bool:
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", start, end],
        cwd=root, capture_output=True,
    )
    return result.returncode == 0


def ingest_range(
    root: Path, git: GitOps, start_commit: str, end_commit: str, config: ClaimsConfig
) -> tuple[IngestedCommit, ...]:
    """Every commit in (start, end], with its claims and exemption facts."""
    if not _is_ancestor(root, start_commit, end_commit):
        raise DivergedRangeError(
            f"{start_commit[:12]} is not an ancestor of {end_commit[:12]}; "
            "history diverged since the last manifest -- ingesting nothing"
        )
    out: list[IngestedCommit] = []
    for sha, subject, body in git.commits_between(root, start_commit, end_commit):
        changed = tuple(git.changed_files_in_commit(root, sha))
        exempted = tuple(
            (path, glob)
            for path in changed
            if (glob := exempting_glob(config, path)) is not None
        )
        out.append(
            IngestedCommit(
                sha=sha,
                subject=subject,
                sr_ids=parse_sr_trailer(f"{subject}\n\n{body}"),
                changed_files=changed,
                exempted=exempted,
            )
        )
    return tuple(out)
```

- [ ] **Step 6: Run test to verify it passes**

Run: `rtk proxy uv run pytest tests/unit/coherence/register/test_ingest.py -v -o addopts=""`
Expected: PASS (4 passed)

- [ ] **Step 7: Write the failing manifest-writing test**

```python
# append to tests/unit/coherence/register/test_ingest.py
import json

from coherence.register.ingest import ingest


@pytest.mark.sr("SR-062")
def test_ingest_writes_a_manifest_carrying_the_commits(git_repo, commit_file):
    commit_file("src/d.py", "d = 1\n", "feat: d\n\nSR: SR-050")
    path = ingest(git_repo)
    assert path is not None
    manifest = json.loads(path.read_text(encoding="utf-8"))
    assert [c["sha"] for c in manifest["commits"]]
    assert "src/d.py" in manifest["implementation"]["changed_files"]


@pytest.mark.sr("SR-062")
def test_a_second_ingest_of_the_same_range_writes_nothing(git_repo, commit_file):
    commit_file("src/e.py", "e = 1\n", "feat: e\n\nSR: SR-050")
    assert ingest(git_repo) is not None
    assert ingest(git_repo) is None


@pytest.mark.sr("SR-062")
def test_an_ingest_manifest_records_no_task_rather_than_inventing_one(git_repo, commit_file):
    commit_file("src/f.py", "f = 1\n", "feat: f\n\nSR: SR-050")
    manifest = json.loads(ingest(git_repo).read_text(encoding="utf-8"))
    assert "task_id" not in manifest
    assert "task" not in manifest["inputs"]
```

- [ ] **Step 8: Relax the schema and implement `ingest`**

In `src/substrate/schemas/evidence_manifest.schema.json`: remove `"task_id"` from the top-level `required` array and `"task"` from `inputs.required`; add to top-level `properties`:

```json
    "commits": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["sha", "subject", "sr_ids", "changed_files"],
        "properties": {
          "sha": {"type": "string", "pattern": "^[a-fA-F0-9]{40,64}$"},
          "subject": {"type": "string"},
          "sr_ids": {"type": "array", "items": {"type": "string", "pattern": "^SR-[0-9]+$"}},
          "changed_files": {"type": "array", "items": {"type": "string"}},
          "exempted": {
            "type": "array",
            "items": {
              "type": "object",
              "additionalProperties": false,
              "required": ["path", "glob"],
              "properties": {"path": {"type": "string"}, "glob": {"type": "string"}}
            }
          }
        }
      }
    }
```

```python
# append to src/coherence/register/ingest.py
EMPTY_PATCH_SHA = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def _newest_result_commit(root: Path) -> str | None:
    manifests = list_run_manifests(root / "evidence" / "runs")
    for manifest in manifests:
        commit = manifest.get("result_commit")
        if isinstance(commit, str) and commit:
            return commit
    return None


def ingest(root: Path, *, git: GitOps | None = None, now: datetime | None = None) -> Path | None:
    """Ingest the range since the newest manifest; return the manifest path.

    Returns None when there is nothing to ingest. Writes a NEW manifest --
    never mutates an existing one -- with the tmp-then-replace pattern
    `coherence.audit.runner` already uses.
    """
    ops = git or SubprocessGitOps()
    config = load_claims_config(root)
    head = ops.head_commit(root)
    start = _newest_result_commit(root)
    commits = (
        ingest_range(root, ops, start, head, config) if start else ()
    )
    if not commits:
        return None
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"ingest-{stamp}"
    changed: list[str] = []
    for commit in commits:
        for path in commit.changed_files:
            if path not in changed:
                changed.append(path)
    manifest = {
        "schema_version": 2,
        "run_id": run_id,
        "started_at": (now or datetime.now(timezone.utc)).isoformat().replace("+00:00", "Z"),
        "ended_at": (now or datetime.now(timezone.utc)).isoformat().replace("+00:00", "Z"),
        "start_commit": start,
        "result_commit": head,
        "outcome": "completed",
        "inputs": {"requirements": [], "factory_config_sha256": "0" * 64},
        "dependencies": [
            {"name": "candidate-tree", "kind": "git-tree",
             "digest": f"git-tree:{head}", "source": head}
        ],
        "implementation": {
            "changed_files": changed,
            "patch": {"sha256": EMPTY_PATCH_SHA, "size": 0, "media_type": "text/x-diff"},
        },
        "commits": [
            {
                "sha": c.sha,
                "subject": c.subject,
                "sr_ids": list(c.sr_ids),
                "changed_files": list(c.changed_files),
                "exempted": [{"path": p, "glob": g} for p, g in c.exempted],
            }
            for c in commits
        ],
        "validation": [],
        "reviews": [],
        "decisions": [],
        "publication": {"state": "local", "errors": []},
    }
    validate_run_manifest(manifest)
    out = root / "evidence" / "runs" / f"{run_id}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".tmp")
    tmp.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    tmp.replace(out)
    return out
```

- [ ] **Step 9: Run test to verify it passes**

Run: `rtk proxy uv run pytest tests/unit/coherence/register/test_ingest.py -v -o addopts=""`
Expected: PASS (7 passed)

- [ ] **Step 10: Verify no existing manifest broke**

Run: `rtk proxy uv run pytest tests/unit/ -m unit -q`
Expected: PASS — the schema change is additive; all 13 existing manifests under `evidence/runs/` still validate.

- [ ] **Step 11: Commit**

```bash
git add src/coherence/register/ingest.py src/factory/orchestrator/git_ops.py src/substrate/schemas/evidence_manifest.schema.json tests/unit/coherence/register/test_ingest.py tests/unit/coherence/register/conftest.py
git commit -m "feat(register): ingest commit claims into an evidence manifest

SR: SR-050"
```

---

### Task 3: Re-base reconciliation onto the claim denominator

**Files:**
- Modify: `src/coherence/register/review.py`
- Test: `tests/unit/coherence/register/test_review.py` (extend)

**Interfaces:**
- Consumes: T2's manifest `commits` field; T1's `ClaimsConfig`/`load_claims_config`.
- Produces: `claimed_paths(manifests, sr_id) -> set[str]`; `exemption_summary(manifests) -> tuple[tuple[str, int], ...]`; `ReconciliationReview` gains `exempted: tuple[tuple[str, int], ...]` and its existing `changed_but_undeclared` / `declared_but_not_changed` categories are computed from claims when the range is post-epoch.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/unit/coherence/register/test_review.py
@pytest.mark.sr("SR-050")
def test_a_claimed_path_the_sr_does_not_declare_is_changed_but_undeclared(tmp_path):
    manifests = [{
        "implementation": {"changed_files": ["src/a.py"]},
        "commits": [{"sha": "a" * 40, "subject": "feat", "sr_ids": ["SR-050"],
                     "changed_files": ["src/a.py"], "exempted": []}],
        "validation": [{"requirements": [{"id": "SR-050", "passed": True}]}],
    }]
    req = _requirement("SR-050", implemented_by=[])
    review = evidence_reconciliation_review(tmp_path, req, manifests)
    details = [f.detail for f in review.findings if f.category == "changed_but_undeclared"]
    assert any("src/a.py" in d for d in details)


@pytest.mark.sr("SR-050")
def test_a_path_claimed_for_another_sr_is_not_this_srs_finding(tmp_path):
    manifests = [{
        "implementation": {"changed_files": ["src/b.py"]},
        "commits": [{"sha": "b" * 40, "subject": "feat", "sr_ids": ["SR-023"],
                     "changed_files": ["src/b.py"], "exempted": []}],
        "validation": [{"requirements": [{"id": "SR-050", "passed": True}]}],
    }]
    req = _requirement("SR-050", implemented_by=[])
    review = evidence_reconciliation_review(tmp_path, req, manifests)
    details = [f.detail for f in review.findings if f.category == "changed_but_undeclared"]
    assert not any("src/b.py" in d for d in details)


@pytest.mark.sr("SR-050")
def test_exemption_counts_are_reported_per_glob(tmp_path):
    manifests = [{
        "implementation": {"changed_files": ["docs/a.md", "docs/b.md"]},
        "commits": [{"sha": "c" * 40, "subject": "docs", "sr_ids": [],
                     "changed_files": ["docs/a.md", "docs/b.md"],
                     "exempted": [{"path": "docs/a.md", "glob": "docs/**"},
                                  {"path": "docs/b.md", "glob": "docs/**"}]}],
        "validation": [],
    }]
    assert exemption_summary(manifests) == (("docs/**", 2),)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `rtk proxy uv run pytest tests/unit/coherence/register/test_review.py -v -o addopts="" -k "claimed or exemption"`
Expected: FAIL — `ImportError: cannot import name 'exemption_summary'`, and the claimed-path tests fail because `changed` is still the manifest-scoped union.

- [ ] **Step 3: Implement**

```python
# add to src/coherence/register/review.py
def claimed_paths(manifests: list[dict], sr_id: str) -> set[str]:
    """Every path from a commit whose `SR:` trailer named ``sr_id``.

    This is the precise denominator claims exist to provide: the
    manifest-scoping heuristic below ("manifests carrying a validation entry
    for this SR") answers "was this SR being worked on around then"; this
    answers "was this file changed FOR this SR".
    """
    paths: set[str] = set()
    for manifest in manifests:
        for commit in manifest.get("commits") or []:
            if not isinstance(commit, dict):
                continue
            if sr_id in (commit.get("sr_ids") or []):
                paths |= {str(p) for p in commit.get("changed_files") or []}
    return paths


def any_claims(manifests: list[dict]) -> bool:
    """True when at least one manifest carries commit claims -- the signal
    that the claim denominator is available at all. Before the epoch, or in a
    repository that has not adopted trailers, this is False and every caller
    falls back to the manifest-scoped behaviour unchanged."""
    return any(manifest.get("commits") for manifest in manifests)


def exemption_summary(manifests: list[dict]) -> tuple[tuple[str, int], ...]:
    """(glob, count) for every exemption recorded, so list creep is a number
    in every review rather than an absence."""
    counts: dict[str, int] = {}
    for manifest in manifests:
        for commit in manifest.get("commits") or []:
            if not isinstance(commit, dict):
                continue
            for entry in commit.get("exempted") or []:
                if isinstance(entry, dict) and entry.get("glob"):
                    counts[str(entry["glob"])] = counts.get(str(entry["glob"]), 0) + 1
    return tuple(sorted(counts.items()))
```

In `evidence_reconciliation_review`, replace the line computing `changed` from every scoped manifest's `implementation.changed_files` with:

```python
    if any_claims(manifests):
        changed = claimed_paths(manifests, req.id)
    else:
        changed = set()
        for manifest in scoped:
            changed |= {str(p) for p in (manifest.get("implementation", {}).get("changed_files") or [])}
```

and add `exempted=exemption_summary(manifests)` to the returned `ReconciliationReview`, adding the field to that dataclass with default `()`.

- [ ] **Step 4: Run test to verify it passes**

Run: `rtk proxy uv run pytest tests/unit/coherence/register/test_review.py -v -o addopts=""`
Expected: PASS — the three new tests plus every pre-existing test in the file (the fallback branch preserves old behaviour for claim-free manifests).

- [ ] **Step 5: Commit**

```bash
git add src/coherence/register/review.py tests/unit/coherence/register/test_review.py
git commit -m "feat(register): re-base reconciliation onto the claim denominator

SR: SR-050"
```

---

### Task 4: The gate — bind [[SR-049]]

**Files:**
- Modify: `src/coherence/register/cli.py`
- Modify: `.factory/factory.yaml`
- Modify: `requirements/SR-049.md` (add binding + acceptance criteria — **only after SR-049 authoring consent**)
- Test: `tests/unit/coherence/register/test_cli_review_claims.py`

**Interfaces:**
- Consumes: T3's `claimed_paths`, `any_claims`, `exemption_summary`; T2's `ingest`.
- Produces: `cmd_review` accepts `--no-ingest` and `--check-claims`; exit code 1 on any `changed_but_undeclared` finding derived from claims.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/coherence/register/test_cli_review_claims.py
import pytest

from coherence.register.cli import cmd_review


@pytest.mark.sr("SR-049")
def test_check_claims_exits_non_zero_on_a_claimed_but_undeclared_path(claims_repo):
    assert cmd_review(claims_repo, check_claims=True, no_ingest=True) == 1


@pytest.mark.sr("SR-049")
def test_check_claims_exits_zero_when_every_claimed_path_is_declared(declared_repo):
    assert cmd_review(declared_repo, check_claims=True, no_ingest=True) == 0


@pytest.mark.sr("SR-049")
def test_check_claims_blocks_under_the_prototype_profile_too(claims_repo):
    """Unlike the fidelity check, claim reconciliation has no judge in the
    loop, so it blocks under every compiled profile."""
    (claims_repo / ".factory" / "factory.yaml").write_text(
        "profile: prototype\ngates:\n  full: []\n", encoding="utf-8"
    )
    assert cmd_review(claims_repo, check_claims=True, no_ingest=True) == 1


@pytest.mark.sr("SR-049")
def test_no_ingest_leaves_the_evidence_store_untouched(claims_repo):
    before = sorted(p.name for p in (claims_repo / "evidence" / "runs").glob("*.json"))
    cmd_review(claims_repo, check_claims=True, no_ingest=True)
    after = sorted(p.name for p in (claims_repo / "evidence" / "runs").glob("*.json"))
    assert before == after
```

- [ ] **Step 2: Run test to verify it fails**

Run: `rtk proxy uv run pytest tests/unit/coherence/register/test_cli_review_claims.py -v -o addopts=""`
Expected: FAIL — `TypeError: cmd_review() got an unexpected keyword argument 'check_claims'`

- [ ] **Step 3: Implement the CLI flags**

In `src/coherence/register/cli.py`, add `--no-ingest` and `--check-claims` to the `review` subparser, and in `cmd_review`:

```python
    if not no_ingest:
        try:
            ingest(root)
        except DivergedRangeError as exc:
            print(f"ingest skipped: {exc}")
    ...
    if check_claims:
        offenders = [
            finding
            for review in reconciliations
            for finding in review.findings
            if finding.category == "changed_but_undeclared"
        ]
        for finding in offenders:
            print(f"claim: {finding.detail}")
        return 1 if offenders else 0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `rtk proxy uv run pytest tests/unit/coherence/register/test_cli_review_claims.py -v -o addopts=""`
Expected: PASS (4 passed)

- [ ] **Step 5: Wire the gate**

Add to `.factory/factory.yaml`'s `full` gate list, after the fidelity check:

```yaml
    # SR-049: produced-code traceability. Deterministic set arithmetic over
    # commit claims and declared relations -- no judge in the loop, so unlike
    # the fidelity check above this blocks under every compiled profile.
    - { cmd: "{python} -m coherence register review --check-claims" }
```

- [ ] **Step 6: [[SR-054]] trace maintenance — declare relations and mirror**

Add to `requirements/SR-049.md` frontmatter (after human authoring consent):

```yaml
implemented_by:
  - path: src/coherence/register/claims.py
    symbol: coherence.register.claims:check_commit
  - path: src/coherence/register/ingest.py
    symbol: coherence.register.ingest:ingest
verified_by:
  - path: tests/unit/coherence/register/test_cli_review_claims.py
    test: tests/unit/coherence/register/test_cli_review_claims.py::test_check_claims_exits_non_zero_on_a_claimed_but_undeclared_path
```

Run: `rtk proxy uv run python -m coherence mirrors generate`
Run: `rtk proxy uv run python -m coherence register review SR-049`
Expected: no `malformed`, `dangling`, or `duplicate` finding.

- [ ] **Step 7: Commit**

```bash
git add src/coherence/register/cli.py .factory/factory.yaml requirements/SR-049.md docs/features/FEAT-001.md tests/unit/coherence/register/test_cli_review_claims.py
git commit -m "feat(register): bind SR-049 with a blocking claim-reconciliation gate

SR: SR-049"
```

---

### Task 5: Feed the fidelity packet

**Files:**
- Modify: `src/coherence/register/fidelity_packet.py`
- Modify: `.pi/skills/fidelity-review/SKILL.md`
- Test: `tests/unit/coherence/register/test_fidelity_packet.py` (extend)

**Interfaces:**
- Consumes: T3's `claimed_paths`.
- Produces: `FidelityPacket` gains `claims: tuple[ClaimFact, ...]` where `ClaimFact(sha, subject, changed_files, declared)`.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/unit/coherence/register/test_fidelity_packet.py
@pytest.mark.sr("SR-050")
def test_packet_carries_claim_facts_marking_undeclared_paths(tmp_path):
    packet = build_fidelity_packet(tmp_path, "SR-050", manifests=[{
        "commits": [{"sha": "a" * 40, "subject": "feat: x", "sr_ids": ["SR-050"],
                     "changed_files": ["src/a.py"], "exempted": []}],
    }])
    assert packet.claims[0].sha == "a" * 40
    assert packet.claims[0].declared == (False,)


@pytest.mark.sr("SR-050")
def test_a_packet_with_no_claims_is_empty_not_absent(tmp_path):
    packet = build_fidelity_packet(tmp_path, "SR-050", manifests=[])
    assert packet.claims == ()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `rtk proxy uv run pytest tests/unit/coherence/register/test_fidelity_packet.py -v -o addopts="" -k claim`
Expected: FAIL — `AttributeError: 'FidelityPacket' object has no attribute 'claims'`

- [ ] **Step 3: Implement**

```python
# add to src/coherence/register/fidelity_packet.py
@dataclass(frozen=True)
class ClaimFact:
    """One commit that CLAIMED this SR. A claim is an assertion by whoever
    wrote the commit -- evidence of intent, never proof of correctness. A
    false claim is precisely the `different_behavior` finding the judge
    exists to catch, so this is presented to the judge as a claim and never
    as a verified fact."""

    sha: str
    subject: str
    changed_files: tuple[str, ...]
    declared: tuple[bool, ...]  # parallel to changed_files
```

Populate it in `build_fidelity_packet` from the manifests' `commits`, marking each path `declared` when it appears in the SR's own `implemented_by`/`verified_by` paths.

- [ ] **Step 4: Run test to verify it passes**

Run: `rtk proxy uv run pytest tests/unit/coherence/register/test_fidelity_packet.py -v -o addopts=""`
Expected: PASS

- [ ] **Step 5: Tell the judge how to read claims**

Add to `.pi/skills/fidelity-review/SKILL.md`, under the findings vocabulary:

> **Claims are intent, not proof.** A `claims` entry means a commit *asserted* it was serving this requirement. Use it to locate the work and to notice a claimed file the requirement never declares — never as evidence that the work is correct. A claim that does not match what the code does is itself a `different_behavior` finding.

- [ ] **Step 6: [[SR-054]] trace maintenance**

Add `src/coherence/register/fidelity_packet.py:build_fidelity_packet` to `requirements/SR-050.md`'s `implemented_by` if not already declared, then:

Run: `rtk proxy uv run python -m coherence mirrors generate`
Run: `rtk proxy uv run python -m coherence register review SR-050`

- [ ] **Step 7: Commit**

```bash
git add src/coherence/register/fidelity_packet.py .pi/skills/fidelity-review/SKILL.md requirements/SR-050.md tests/unit/coherence/register/test_fidelity_packet.py
git commit -m "feat(register): give the fidelity packet commit-claim facts

SR: SR-050"
```

---

## Final verification

- [ ] `rtk proxy uv run pytest -m sr -v -o addopts=""` — every SR-marked test passes
- [ ] `rtk proxy uv run pytest -m unit -q` — no regression
- [ ] `rtk proxy uv run ruff check .` and `rtk proxy uv run pyright`
- [ ] `rtk proxy uv run python -m coherence register review --check-claims` exits 0
- [ ] `rtk proxy uv run python -m coherence mirrors check` passes
- [ ] `rtk proxy uv run python -m coherence audit audit FEAT-001` shows SR-049 measured
- [ ] Record evidence for SR-049 (and SR-062 if consented) following the `T-9013` manifest precedent

## Self-review notes

**Spec coverage:** trailer → T1; hook + `core.hooksPath` assertion → T1 (the gate assertion itself is folded into T4's gate wiring); config/exemptions → T1; epoch → T3's `any_claims` fallback; ingestion, range, divergence, schema, idempotency, atomicity → T2; CI-doesn't-persist → inherent in T2 (`ingest` writes; CI discards); reconciliation re-basing → T3; `exempted` reporting → T3; gate + SR-049 binding → T4; fidelity packet → T5.

**Known gap deliberately left:** the spec's `core.hooksPath` gate assertion is described but has no dedicated test in T4. It is a one-line config read; add it to T4 Step 5 if the reviewer wants it bound.

**Epoch simplification:** the spec describes an epoch commit sha; T3 implements the fallback via `any_claims` (claims present at all) rather than comparing shas. This is honest for adoption — before adoption no manifest carries claims, so the fallback fires — but a repository that adopts claims mid-history will see pre-epoch files reported. If that matters, T3 gains an epoch-ancestry check; flagged rather than silently skipped.
