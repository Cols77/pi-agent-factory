from __future__ import annotations

from shutil import copytree
from pathlib import Path
from typing import Any

import frontmatter
import pytest

from coherence.planning.review import GeneratedTaskReviewInput, review_cross_artifact_relations
from coherence.register.register import load_register

pytestmark = pytest.mark.unit

_FIXTURE_REPO = Path(__file__).parents[2] / "fixtures" / "planning-review" / "canonical-repo"


@pytest.fixture
def review_repo(tmp_path: Path) -> Path:
    copytree(_FIXTURE_REPO, tmp_path, dirs_exist_ok=True)
    return tmp_path


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _requirement(
    root: Path,
    sr_id: str,
    *,
    implemented_by: list[dict] | None = None,
    verified_by: list[dict] | None = None,
) -> None:
    metadata: dict[str, Any] = {
        "id": sr_id,
        "title": sr_id,
        "statement": "A deterministic review keeps planning traceable.",
        "domain": "behavioral",
    }
    if implemented_by is not None:
        metadata["implemented_by"] = implemented_by
    if verified_by is not None:
        metadata["verified_by"] = verified_by
    _write(
        root / "requirements" / f"{sr_id}.md",
        frontmatter.dumps(frontmatter.Post("body", **metadata)),
    )


def _canonical_requirement(root: Path, sr_id: str = "SR-101") -> None:
    if sr_id == "SR-101":
        return
    _requirement(
        root,
        sr_id,
        implemented_by=[{"path": "src/feature.py", "symbol": "feature:behavior"}],
        verified_by=[
            {
                "path": "tests/unit/test_feature.py",
                "test": "tests/unit/test_feature.py::test_behavior",
            }
        ],
    )


def _review(root: Path, *tasks: GeneratedTaskReviewInput):
    return review_cross_artifact_relations(root, load_register(root / "requirements"), tasks)


@pytest.mark.sr("SR-053")
def test_empty_review_does_not_discover_source_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unexpected_discovery(*_args: object, **_kwargs: object) -> list[str]:
        raise AssertionError("empty review must not discover source files")

    monkeypatch.setattr("substrate.codemap.build.discover_source_files", unexpected_discovery)

    report = review_cross_artifact_relations(tmp_path, (), ())

    assert report.ok is True
    assert report.findings == ()


@pytest.mark.sr("SR-053")
def test_production_task_without_affected_sr_declaration_is_missing(review_repo: Path) -> None:

    report = _review(
        review_repo,
        GeneratedTaskReviewInput("T-001", ("src/feature.py",), True, False, None),
    )

    assert [finding.code for finding in report.findings] == ["TASK_SR_DECLARATION_MISSING"]
    assert report.ok is False


@pytest.mark.sr("SR-053")
def test_dangling_canonical_relation_is_reported(review_repo: Path) -> None:
    _requirement(
        review_repo,
        "SR-101",
        implemented_by=[{"path": "src/missing.py", "symbol": "missing:behavior"}],
        verified_by=[],
    )

    report = _review(
        review_repo,
        GeneratedTaskReviewInput("T-001", ("src/missing.py",), True, False, ("SR-101",)),
    )

    assert "RELATION_DANGLING" in [finding.code for finding in report.findings]


@pytest.mark.sr("SR-053")
def test_duplicate_canonical_relation_is_reported(review_repo: Path) -> None:
    entry = {"path": "src/feature.py", "symbol": "feature:behavior"}
    _requirement(review_repo, "SR-101", implemented_by=[entry, dict(entry)], verified_by=[])

    report = _review(
        review_repo,
        GeneratedTaskReviewInput("T-001", ("src/feature.py",), True, False, ("SR-101",)),
    )

    assert "RELATION_DUPLICATE" in [finding.code for finding in report.findings]


@pytest.mark.sr("SR-053")
def test_task_relation_is_weak_when_affected_sr_has_no_validation_relation(
    review_repo: Path,
) -> None:
    _requirement(
        review_repo,
        "SR-101",
        implemented_by=[{"path": "src/feature.py", "symbol": "feature:behavior"}],
        verified_by=[],
    )

    report = _review(
        review_repo,
        GeneratedTaskReviewInput("T-001", ("src/feature.py",), True, False, ("SR-101",)),
    )

    assert "RELATION_WEAK" in [finding.code for finding in report.findings]


@pytest.mark.sr("SR-053")
def test_task_relation_is_overstated_when_task_artifacts_have_no_canonical_overlap(
    review_repo: Path,
) -> None:

    report = _review(
        review_repo,
        GeneratedTaskReviewInput("T-001", ("src/unrelated.py",), True, False, ("SR-101",)),
    )

    assert "RELATION_OVERSTATED" in [finding.code for finding in report.findings]


@pytest.mark.sr("SR-053")
@pytest.mark.parametrize("artifact_path", ("./src/feature.py", r"src\feature.py"))
def test_equivalent_task_artifact_path_does_not_overstate_relation(
    review_repo: Path,
    artifact_path: str,
) -> None:
    report = _review(
        review_repo,
        GeneratedTaskReviewInput("T-001", (artifact_path,), True, False, ("SR-101",)),
    )

    assert "RELATION_OVERSTATED" not in [finding.code for finding in report.findings]


@pytest.mark.sr("SR-053")
@pytest.mark.parametrize("relation_path", ("./src/feature.py", r"src\feature.py"))
def test_equivalent_canonical_relation_path_does_not_overstate_task(
    review_repo: Path,
    relation_path: str,
) -> None:
    _requirement(
        review_repo,
        "SR-101",
        implemented_by=[{"path": relation_path, "symbol": "feature:behavior"}],
        verified_by=[
            {
                "path": "tests/unit/test_feature.py",
                "test": "tests/unit/test_feature.py::test_behavior",
            }
        ],
    )

    report = _review(
        review_repo,
        GeneratedTaskReviewInput("T-001", ("src/feature.py",), True, False, ("SR-101",)),
    )

    assert "RELATION_OVERSTATED" not in [finding.code for finding in report.findings]


@pytest.mark.sr("SR-053")
def test_review_is_read_only_when_resolving_canonical_relations(review_repo: Path) -> None:
    report = _review(
        review_repo,
        GeneratedTaskReviewInput("T-001", ("src/feature.py",), True, False, ("SR-101",)),
    )

    assert report.ok is True
    assert not (review_repo / ".factory").exists()


@pytest.mark.sr("SR-053")
def test_task_declaration_and_existing_satisfies_mirror_must_not_contradict(
    review_repo: Path,
) -> None:
    _canonical_requirement(review_repo, "SR-102")

    report = _review(
        review_repo,
        GeneratedTaskReviewInput(
            "T-001", ("src/feature.py",), True, False, ("SR-101",), ("SR-102",)
        ),
    )

    assert "RELATION_CONTRADICTORY" in [finding.code for finding in report.findings]


@pytest.mark.sr("SR-054")
@pytest.mark.parametrize("affected_srs", [(), ("SR-101", "SR-101"), ("SR-102", "SR-101")])
def test_affected_srs_must_be_unique_and_sorted(
    review_repo: Path, affected_srs: tuple[str, ...]
) -> None:
    _canonical_requirement(review_repo, "SR-102")

    report = _review(
        review_repo,
        GeneratedTaskReviewInput("T-001", ("src/feature.py",), True, False, affected_srs),
    )

    assert "TASK_SR_DECLARATION_INVALID" in [finding.code for finding in report.findings]


@pytest.mark.sr("SR-054")
def test_docs_only_task_needs_no_affected_sr_declaration(review_repo: Path) -> None:

    report = _review(
        review_repo,
        GeneratedTaskReviewInput("T-001", ("docs/runbook.md",), False, False, None),
    )

    assert report.ok is True


@pytest.mark.sr("SR-054")
def test_declared_srs_reconcile_with_existing_satisfies_mirror(review_repo: Path) -> None:

    report = _review(
        review_repo,
        GeneratedTaskReviewInput(
            "T-001", ("src/feature.py",), True, False, ("SR-101",), ("SR-101",)
        ),
    )

    assert report.ok is True
