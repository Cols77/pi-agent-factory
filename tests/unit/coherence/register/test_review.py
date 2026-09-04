from __future__ import annotations

import json
from pathlib import Path

import frontmatter as fm
import pytest

from coherence.register.cli import cmd_review
from coherence.register.register import Binding, Requirement
from coherence.register.review import (
    evidence_reconciliation_review,
    claimed_paths,
    exemption_summary,
    structural_review,
    unaccounted_changed_files,
)

pytestmark = pytest.mark.unit

# SR-050/AC-2: "The per-requirement review reports structural-coverage
# findings (missing/dangling relations, unresolved or duplicate declarations,
# changed production files or executed tests with no owning SR relation) and
# evidence-integrity findings (declared-vs-changed and declared-vs-executed
# reconciliation against manifests and validation output) as two categories,
# distinct from each other and from semantic-fidelity findings, never merged
# into one verdict."


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _write_meta(path: Path, meta: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(fm.dumps(fm.Post("body", **meta)), encoding="utf-8")
    return path


def _bound(req_id: str, path: Path) -> Requirement:
    return Requirement(
        id=req_id,
        title="t",
        statement="s",
        domain="behavioral",
        upstream=[],
        binding=Binding(experiment="x", metric="m", assert_expr="a"),
        body="",
        path=path,
    )


def _unbound(req_id: str, path: Path) -> Requirement:
    return Requirement(
        id=req_id,
        title="t",
        statement="s",
        domain="behavioral",
        upstream=[],
        binding=None,
        body="",
        path=path,
    )


def _write_prod(root: Path) -> None:
    _write(
        root / "src" / "widgets" / "feature.py",
        "def feature_context():\n    return 1\n",
    )


def _write_test_file(root: Path) -> None:
    _write(
        root / "tests" / "unit" / "test_feature.py",
        "def test_feature_context():\n    assert True\n",
    )


# ---------------------------------------------------------------------------
# Structural trace reviewer: one fixture per finding class.
# ---------------------------------------------------------------------------


@pytest.mark.sr("SR-050")
def test_a_bound_sr_declaring_no_implemented_by_entries_is_missing(tmp_path: Path):
    req_path = _write_meta(
        tmp_path / "requirements" / "SR-100.md",
        {"id": "SR-100", "verified_by": []},
    )
    req = _bound("SR-100", req_path)
    review = structural_review(tmp_path, req)
    missing = [f for f in review.findings if f.category == "missing"]
    assert {f.field for f in missing} == {"implemented_by", "verified_by"}


@pytest.mark.sr("SR-050")
def test_a_bound_sr_with_only_a_legacy_verified_by_string_is_still_missing(tmp_path: Path):
    # A legacy plain-string verified_by entry (the pre-existing SR-to-task
    # graph edge) carries no path/symbol/test identity at all and cannot
    # satisfy AC-1's structured relation -- its mere presence must not
    # permanently defeat the "missing" finding for a bound SR that has zero
    # structured verified_by entries.
    _write_prod(tmp_path)
    req_path = _write_meta(
        tmp_path / "requirements" / "SR-117.md",
        {
            "id": "SR-117",
            "implemented_by": [
                {"path": "src/widgets/feature.py", "symbol": "widgets.feature:feature_context"}
            ],
            "verified_by": ["T-001"],
        },
    )
    req = _bound("SR-117", req_path)
    review = structural_review(tmp_path, req)
    missing = [f for f in review.findings if f.category == "missing"]
    assert {f.field for f in missing} == {"verified_by"}


@pytest.mark.sr("SR-050")
def test_a_verified_by_field_mixing_legacy_and_structured_entries_is_not_missing(tmp_path: Path):
    _write_test_file(tmp_path)
    req_path = _write_meta(
        tmp_path / "requirements" / "SR-118.md",
        {
            "id": "SR-118",
            "implemented_by": [],
            "verified_by": [
                "T-001",
                {
                    "path": "tests/unit/test_feature.py",
                    "test": "tests/unit/test_feature.py::test_feature_context",
                },
            ],
        },
    )
    req = _bound("SR-118", req_path)
    review = structural_review(tmp_path, req)
    missing = [f for f in review.findings if f.category == "missing"]
    assert {f.field for f in missing} == {"implemented_by"}


@pytest.mark.sr("SR-050")
def test_a_verified_by_link_to_a_deleted_test_node_is_dangling(tmp_path: Path):
    # The plan's explicit fixture: "a link to a deleted test node" -- the
    # test FILE still exists, but the function it names does not (deleted).
    _write_test_file(tmp_path)
    req_path = _write_meta(
        tmp_path / "requirements" / "SR-101.md",
        {
            "id": "SR-101",
            "verified_by": [
                {
                    "path": "tests/unit/test_feature.py",
                    "test": "tests/unit/test_feature.py::test_deleted_node",
                }
            ],
        },
    )
    req = _bound("SR-101", req_path)
    review = structural_review(tmp_path, req)
    dangling = [f for f in review.findings if f.category == "dangling"]
    assert len(dangling) == 1
    assert "does not resolve" in dangling[0].detail


@pytest.mark.sr("SR-050")
def test_an_implemented_by_entry_missing_its_symbol_is_malformed(tmp_path: Path):
    _write_prod(tmp_path)
    req_path = _write_meta(
        tmp_path / "requirements" / "SR-102.md",
        {"id": "SR-102", "implemented_by": [{"path": "src/widgets/feature.py"}]},
    )
    req = _bound("SR-102", req_path)
    review = structural_review(tmp_path, req)
    malformed = [f for f in review.findings if f.category == "malformed"]
    assert len(malformed) == 1
    assert "symbol" in malformed[0].detail


@pytest.mark.sr("SR-050")
def test_a_repeated_identical_declaration_is_a_duplicate(tmp_path: Path):
    _write_prod(tmp_path)
    entry = {"path": "src/widgets/feature.py", "symbol": "widgets.feature:feature_context"}
    req_path = _write_meta(
        tmp_path / "requirements" / "SR-103.md",
        {"id": "SR-103", "implemented_by": [dict(entry), dict(entry)]},
    )
    req = _bound("SR-103", req_path)
    review = structural_review(tmp_path, req)
    duplicate = [f for f in review.findings if f.category == "duplicate"]
    assert len(duplicate) == 1


@pytest.mark.sr("SR-050")
def test_a_path_outside_the_project_is_out_of_scope(tmp_path: Path):
    req_path = _write_meta(
        tmp_path / "requirements" / "SR-104.md",
        {"id": "SR-104", "implemented_by": [{"path": "/etc/passwd", "symbol": "etc.passwd:root"}]},
    )
    req = _bound("SR-104", req_path)
    review = structural_review(tmp_path, req)
    out_of_scope = [f for f in review.findings if f.category == "out_of_scope"]
    assert len(out_of_scope) == 1


@pytest.mark.sr("SR-050")
def test_a_changed_file_with_no_sr_link_anywhere_is_unaccounted(tmp_path: Path):
    # The plan's explicit fixture: "a changed file that has no SR link."
    _write_prod(tmp_path)
    linked_path = _write_meta(
        tmp_path / "requirements" / "SR-105.md",
        {
            "id": "SR-105",
            "implemented_by": [
                {"path": "src/widgets/feature.py", "symbol": "widgets.feature:feature_context"}
            ],
        },
    )
    unrelated_path = _write_meta(tmp_path / "requirements" / "SR-106.md", {"id": "SR-106"})
    reqs = [_unbound("SR-105", linked_path), _unbound("SR-106", unrelated_path)]
    manifests = [
        {"implementation": {"changed_files": ["src/widgets/feature.py", "src/widgets/orphan.py"]}}
    ]
    findings = unaccounted_changed_files(tmp_path, reqs, manifests)
    assert len(findings) == 1
    assert "src/widgets/orphan.py" in findings[0].detail


@pytest.mark.sr("SR-050")
def test_a_claim_exempt_changed_file_is_not_unaccounted(tmp_path: Path):
    """AC-2's criterion says "changed *production* files ... with no owning SR
    relation", and the exempt list is precisely the repository's declaration of
    which paths are not that. Before commit-claim ingestion existed this bucket
    only ever saw manifests written by orchestrated task runs, whose changed
    files were the task's produced code; ingestion now feeds it the union of
    every commit in the range, docs and requirement files included. Those can
    never be cleared -- no SR declares its own `requirements/SR-0xx.md` as an
    implementation of itself -- so without this filter every doc commit adds a
    permanent finding and the bucket decays into noise it can never shed. Same
    exempt list, same reason, as the claim denominator's own filter.
    """
    _write(
        tmp_path / ".factory" / "trace-claims.yaml",
        """
epoch: null
exempt:
  - "docs/**"
  - "**/*.md"
""",
    )
    _write_prod(tmp_path)
    linked_path = _write_meta(
        tmp_path / "requirements" / "SR-105.md",
        {
            "id": "SR-105",
            "implemented_by": [
                {"path": "src/widgets/feature.py", "symbol": "widgets.feature:feature_context"}
            ],
        },
    )
    reqs = [_unbound("SR-105", linked_path)]
    manifests = [
        {
            "implementation": {
                "changed_files": [
                    "src/widgets/feature.py",
                    "requirements/SR-105.md",
                    "docs/superpowers/plans/some-plan.md",
                    "src/widgets/orphan.py",
                ]
            }
        }
    ]
    findings = unaccounted_changed_files(tmp_path, reqs, manifests)
    details = [f.detail for f in findings]
    assert len(findings) == 1, details
    assert "src/widgets/orphan.py" in findings[0].detail


@pytest.mark.sr("SR-050")
def test_an_executed_test_with_no_sr_link_anywhere_is_unaccounted(tmp_path: Path):
    # AC-2's criterion names two distinct unaccounted cases -- "changed
    # production files OR executed tests with no owning SR relation" -- not
    # just the first. A pre-existing, unmodified test file that is executed
    # (recorded via the evidence writers' conventional
    # validation[*].requirements[*].tests field) but never declared as any
    # SR's implemented_by/verified_by path, and never itself a changed
    # file, must still surface as unaccounted.
    unrelated_path = _write_meta(tmp_path / "requirements" / "SR-108.md", {"id": "SR-108"})
    reqs = [_unbound("SR-108", unrelated_path)]
    manifests = [
        {
            "implementation": {"changed_files": []},
            "validation": [
                {
                    "requirements": [
                        {
                            "id": "SR-902",
                            "passed": True,
                            "tests": ["tests/unit/test_orphan.py::test_something"],
                        }
                    ]
                }
            ],
        }
    ]
    findings = unaccounted_changed_files(tmp_path, reqs, manifests)
    assert len(findings) == 1
    assert findings[0].category == "unaccounted"
    assert "tests/unit/test_orphan.py" in findings[0].detail
    assert "executed" in findings[0].detail


@pytest.mark.sr("SR-050")
def test_an_executed_test_also_declared_is_not_unaccounted(tmp_path: Path):
    req_path = _write_meta(
        tmp_path / "requirements" / "SR-109.md",
        {
            "id": "SR-109",
            "verified_by": [
                {"path": "tests/unit/test_owned.py", "test": "tests/unit/test_owned.py::test_x"}
            ],
        },
    )
    reqs = [_unbound("SR-109", req_path)]
    manifests = [
        {
            "implementation": {"changed_files": []},
            "validation": [
                {"requirements": [{"id": "SR-109", "tests": ["tests/unit/test_owned.py::test_x"]}]}
            ],
        }
    ]
    findings = unaccounted_changed_files(tmp_path, reqs, manifests)
    assert findings == ()


@pytest.mark.sr("SR-050")
def test_structural_review_never_emits_unaccounted_for_a_single_sr(tmp_path: Path):
    # unaccounted has no single owning SR by definition -- structural_review
    # (per-SR) must never emit it; only unaccounted_changed_files (register
    # -wide) does.
    req_path = _write_meta(tmp_path / "requirements" / "SR-107.md", {"id": "SR-107"})
    review = structural_review(tmp_path, _unbound("SR-107", req_path))
    assert all(f.category != "unaccounted" for f in review.findings)


# ---------------------------------------------------------------------------
# Evidence reconciliation reviewer: one fixture per finding class.
# ---------------------------------------------------------------------------


@pytest.mark.sr("SR-050")
def test_a_declared_path_changed_by_a_scoped_manifest_is_declared_and_changed(tmp_path: Path):
    req_path = _write_meta(
        tmp_path / "requirements" / "SR-110.md",
        {"id": "SR-110", "implemented_by": [{"path": "src/a.py", "symbol": "a:f"}]},
    )
    manifests = [
        {
            "implementation": {"changed_files": ["src/a.py"]},
            "validation": [{"requirements": [{"id": "SR-110", "passed": True}]}],
        }
    ]
    review = evidence_reconciliation_review(tmp_path, _unbound("SR-110", req_path), manifests)
    hits = [f for f in review.findings if f.category == "declared_and_changed"]
    assert len(hits) == 1
    assert "src/a.py" in hits[0].detail


@pytest.mark.sr("SR-050")
def test_a_declared_path_not_in_any_scoped_manifests_changed_files_is_declared_but_not_changed(
    tmp_path: Path,
):
    req_path = _write_meta(
        tmp_path / "requirements" / "SR-111.md",
        {"id": "SR-111", "implemented_by": [{"path": "src/a.py", "symbol": "a:f"}]},
    )
    manifests = [
        {
            "implementation": {"changed_files": []},
            "validation": [{"requirements": [{"id": "SR-111", "passed": True}]}],
        }
    ]
    review = evidence_reconciliation_review(tmp_path, _unbound("SR-111", req_path), manifests)
    hits = [f for f in review.findings if f.category == "declared_but_not_changed"]
    assert len(hits) == 1


@pytest.mark.sr("SR-050")
def test_a_changed_file_in_a_scoped_manifest_that_is_not_declared_is_changed_but_undeclared(
    tmp_path: Path,
):
    req_path = _write_meta(tmp_path / "requirements" / "SR-112.md", {"id": "SR-112"})
    manifests = [
        {
            "implementation": {"changed_files": ["src/surprise.py"]},
            "validation": [{"requirements": [{"id": "SR-112", "passed": True}]}],
        }
    ]
    review = evidence_reconciliation_review(tmp_path, _unbound("SR-112", req_path), manifests)
    hits = [f for f in review.findings if f.category == "changed_but_undeclared"]
    assert len(hits) == 1
    assert "src/surprise.py" in hits[0].detail


@pytest.mark.sr("SR-050")
def test_declared_relations_with_an_executed_validation_entry_is_declared_and_executed(tmp_path: Path):
    req_path = _write_meta(
        tmp_path / "requirements" / "SR-113.md",
        {"id": "SR-113", "implemented_by": [{"path": "src/a.py", "symbol": "a:f"}]},
    )
    manifests = [{"validation": [{"requirements": [{"id": "SR-113"}]}]}]
    review = evidence_reconciliation_review(tmp_path, _unbound("SR-113", req_path), manifests)
    hits = [f for f in review.findings if f.category == "declared_and_executed"]
    assert len(hits) == 1


@pytest.mark.sr("SR-050")
def test_an_executed_sr_with_no_verified_by_declared_is_executed_but_unlinked(tmp_path: Path):
    req_path = _write_meta(tmp_path / "requirements" / "SR-114.md", {"id": "SR-114"})
    manifests = [{"validation": [{"requirements": [{"id": "SR-114", "passed": True}]}]}]
    review = evidence_reconciliation_review(tmp_path, _unbound("SR-114", req_path), manifests)
    hits = [f for f in review.findings if f.category == "executed_but_unlinked"]
    assert len(hits) == 1


@pytest.mark.sr("SR-050")
def test_a_linked_sr_whose_validation_entry_failed_is_linked_but_stale_or_failed(tmp_path: Path):
    req_path = _write_meta(
        tmp_path / "requirements" / "SR-115.md",
        {
            "id": "SR-115",
            "verified_by": [{"path": "tests/unit/test_feature.py", "test": "tests/unit/test_feature.py::test_feature_context"}],
        },
    )
    manifests = [{"validation": [{"requirements": [{"id": "SR-115", "passed": False}]}]}]
    review = evidence_reconciliation_review(tmp_path, _unbound("SR-115", req_path), manifests)
    hits = [f for f in review.findings if f.category == "linked_but_stale_or_failed"]
    assert len(hits) == 1
    assert "failed" in hits[0].detail


@pytest.mark.sr("SR-050")
def test_a_linked_sr_changed_again_after_its_last_recorded_validation_is_stale(tmp_path: Path):
    # Genuine staleness, not just "never executed": evidence that WAS valid
    # once (manifest #1: passing validation for this SR) has since gone out
    # of date (manifest #2, later, changes the linked file again and
    # records no validation entry for this SR at all -- so it isn't
    # "scoped" per this reviewer's own scoping rule, and would otherwise
    # pass as clean).
    req_path = _write_meta(
        tmp_path / "requirements" / "SR-902.md",
        {
            "id": "SR-902",
            "verified_by": [
                {"path": "tests/unit/test_x.py", "test": "tests/unit/test_x.py::test_it"}
            ],
        },
    )
    manifests = [
        {
            "ended_at": "2026-09-01T00:00:00Z",
            "implementation": {"changed_files": ["tests/unit/test_x.py"]},
            "validation": [{"requirements": [{"id": "SR-902", "passed": True}]}],
        },
        {
            "ended_at": "2026-09-02T00:00:00Z",
            "implementation": {"changed_files": ["tests/unit/test_x.py"]},
            "validation": [],
        },
    ]
    review = evidence_reconciliation_review(tmp_path, _unbound("SR-902", req_path), manifests)
    hits = [f for f in review.findings if f.category == "linked_but_stale_or_failed"]
    assert len(hits) == 1
    assert "stale" in hits[0].detail


@pytest.mark.sr("SR-050")
def test_a_linked_sr_with_no_covering_manifest_at_all_is_linked_but_stale_or_failed(tmp_path: Path):
    req_path = _write_meta(
        tmp_path / "requirements" / "SR-116.md",
        {
            "id": "SR-116",
            "verified_by": [{"path": "tests/unit/test_feature.py", "test": "tests/unit/test_feature.py::test_feature_context"}],
        },
    )
    review = evidence_reconciliation_review(tmp_path, _unbound("SR-116", req_path), manifests=[])
    hits = [f for f in review.findings if f.category == "linked_but_stale_or_failed"]
    assert len(hits) == 1
    assert "no manifest" in hits[0].detail


# ---------------------------------------------------------------------------
# The claim denominator: when manifests carry commit claims, "changed" is
# what commits claimed for THIS SR, not the manifest-scoped union.
# ---------------------------------------------------------------------------


@pytest.mark.sr("SR-050")
def test_a_claimed_path_the_sr_does_not_declare_is_changed_but_undeclared(tmp_path: Path):
    req_path = _write_meta(tmp_path / "requirements" / "SR-130.md", {"id": "SR-130"})
    manifests = [
        {
            "implementation": {"changed_files": ["src/a.py"]},
            "commits": [
                {
                    "sha": "a" * 40,
                    "subject": "feat",
                    "sr_ids": ["SR-130"],
                    "changed_files": ["src/a.py"],
                    "exempted": [],
                }
            ],
            "validation": [{"requirements": [{"id": "SR-130", "passed": True}]}],
        }
    ]
    review = evidence_reconciliation_review(tmp_path, _unbound("SR-130", req_path), manifests)
    details = [f.detail for f in review.findings if f.category == "changed_but_undeclared"]
    assert any("src/a.py" in d for d in details)


@pytest.mark.sr("SR-050")
def test_a_path_claimed_for_another_sr_is_not_this_srs_finding(tmp_path: Path):
    req_path = _write_meta(tmp_path / "requirements" / "SR-131.md", {"id": "SR-131"})
    manifests = [
        {
            "implementation": {"changed_files": ["src/b.py"]},
            "commits": [
                {
                    "sha": "b" * 40,
                    "subject": "feat",
                    "sr_ids": ["SR-023"],
                    "changed_files": ["src/b.py"],
                    "exempted": [],
                }
            ],
            "validation": [{"requirements": [{"id": "SR-131", "passed": True}]}],
        }
    ]
    review = evidence_reconciliation_review(tmp_path, _unbound("SR-131", req_path), manifests)
    details = [f.detail for f in review.findings if f.category == "changed_but_undeclared"]
    assert not any("src/b.py" in d for d in details)


@pytest.mark.sr("SR-049")
def test_a_path_the_commit_exempted_is_not_in_the_claim_denominator(tmp_path: Path):
    """An exempted path is one the claim policy says never needs a declared
    relation. Counting it as claimed anyway made every commit that touched a
    doc alongside code produce a permanent `changed_but_undeclared` finding no
    declaration could ever clear -- the exempt list was wired into the
    commit-time check only, and had no effect on the denominator it exists to
    shrink."""
    req_path = _write_meta(tmp_path / "requirements" / "SR-133.md", {"id": "SR-133"})
    manifests = [
        {
            "implementation": {"changed_files": ["src/a.py", "docs/note.md"]},
            "commits": [
                {
                    "sha": "d" * 40,
                    "subject": "feat",
                    "sr_ids": ["SR-133"],
                    "changed_files": ["src/a.py", "docs/note.md"],
                    "exempted": [{"path": "docs/note.md", "glob": "docs/**"}],
                }
            ],
            "validation": [],
        }
    ]
    assert claimed_paths(manifests, "SR-133") == {"src/a.py"}
    review = evidence_reconciliation_review(tmp_path, _unbound("SR-133", req_path), manifests)
    details = [f.detail for f in review.findings if f.category == "changed_but_undeclared"]
    assert any("src/a.py" in d for d in details)
    assert not any("docs/note.md" in d for d in details)


@pytest.mark.sr("SR-050")
def test_exemption_counts_are_reported_per_glob(tmp_path: Path):
    manifests = [
        {
            "implementation": {"changed_files": ["docs/a.md", "docs/b.md"]},
            "commits": [
                {
                    "sha": "c" * 40,
                    "subject": "docs",
                    "sr_ids": [],
                    "changed_files": ["docs/a.md", "docs/b.md"],
                    "exempted": [
                        {"path": "docs/a.md", "glob": "docs/**"},
                        {"path": "docs/b.md", "glob": "docs/**"},
                    ],
                }
            ],
            "validation": [],
        }
    ]
    assert exemption_summary(manifests) == (("docs/**", 2),)
    req_path = _write_meta(tmp_path / "requirements" / "SR-132.md", {"id": "SR-132"})
    review = evidence_reconciliation_review(tmp_path, _unbound("SR-132", req_path), manifests)
    assert review.exempted == (("docs/**", 2),)


# ---------------------------------------------------------------------------
# AC-2's own "never merged into one verdict" requirement, exercised through
# the actual CLI surface (`coherence register review`).
# ---------------------------------------------------------------------------


@pytest.mark.sr("SR-050")
def test_cmd_review_reports_structural_and_evidence_reconciliation_as_distinct_top_level_keys(
    tmp_path: Path,
):
    _write_prod(tmp_path)
    _write_meta(
        tmp_path / "requirements" / "SR-120.md",
        {
            "id": "SR-120",
            "title": "t",
            "statement": "s",
            "domain": "behavioral",
            "implemented_by": [
                {"path": "src/widgets/feature.py", "symbol": "widgets.feature:does_not_exist"}
            ],
        },
    )
    manifests_dir = tmp_path / "evidence" / "runs"
    manifests_dir.mkdir(parents=True)
    zero_sha = "0" * 64
    (manifests_dir / "run.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "run_id": "run-1",
                "task_id": "T-1",
                "started_at": "2026-09-03T00:00:00Z",
                "ended_at": "2026-09-03T00:00:01Z",
                "start_commit": "a" * 40,
                "result_commit": "a" * 40,
                "outcome": "completed",
                "inputs": {
                    "task": {"path": "tasks/T-1.md", "sha256": zero_sha},
                    "requirements": [
                        {"id": "SR-120", "path": "requirements/SR-120.md", "sha256": zero_sha}
                    ],
                    "factory_config_sha256": zero_sha,
                },
                "dependencies": [],
                "implementation": {
                    "changed_files": ["src/widgets/orphan.py"],
                    "patch": {"sha256": zero_sha, "size": 0, "media_type": "text/x-diff"},
                },
                "validation": [{"requirements": [{"id": "SR-120", "passed": False}]}],
                "reviews": [],
                "decisions": [],
                "publication": {"state": "local", "errors": []},
            }
        ),
        encoding="utf-8",
    )
    result = json.loads(cmd_review(tmp_path, None))
    assert set(result.keys()) == {"structural", "evidence_reconciliation"}
    assert result["structural"] is not result["evidence_reconciliation"]
    # A dangling relation must show up ONLY on the structural side, never
    # folded into the evidence-reconciliation verdict, and vice versa.
    structural_categories = {f["category"] for f in result["structural"]["SR-120"]}
    reconciliation_categories = {f["category"] for f in result["evidence_reconciliation"]["SR-120"]}
    assert "dangling" in structural_categories
    assert "dangling" not in reconciliation_categories
    assert structural_categories.isdisjoint(reconciliation_categories)
    assert "src/widgets/orphan.py" in str(result["structural"]["_unaccounted"])
