from __future__ import annotations

import json
from pathlib import Path

import pytest

from coherence.course.check import check_course
from coherence.course.cli import main as course_main


pytestmark = pytest.mark.unit

FIXTURES = Path(__file__).parents[2] / "fixtures" / "course"


def _sr(root: Path, sid: str) -> None:
    """A requirement file -> graph SR node with id == sid."""
    p = root / "requirements" / f"{sid}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        f"---\nid: {sid}\ntitle: {sid}\nstatement: s\ndomain: d\n---\nbody\n",
        encoding="utf-8",
    )


def _spec(root: Path, sid: str, title: str = "S", status: str = "approved") -> None:
    """A frontmatter spec -> graph node `spec:<sid>`."""
    p = root / "docs" / "superpowers" / "specs" / f"{sid}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        f"---\nid: {sid}\ntitle: {title}\nstatus: {status}\n---\nbody\n",
        encoding="utf-8",
    )


def _add_course(root: Path, name: str) -> Path:
    """Copy a fixture course note into the tmp repo's docs/course dir."""
    dst = root / "docs" / "course" / name
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text((FIXTURES / name).read_text(encoding="utf-8"), encoding="utf-8")
    return dst


def _course_dir(root: Path) -> Path:
    return root / "docs" / "course"


# -- 1. unknown frontmatter ID -----------------------------------------------


def test_fails_on_unknown_frontmatter_id(tmp_path):
    _sr(tmp_path, "SR-001")
    _spec(tmp_path, "alpha")
    _add_course(tmp_path, "unknown_frontmatter.md")

    report = check_course(tmp_path)
    assert report.ok is False
    assert any("SR-9999" in e and "traceability" in e for e in report.errors)


def test_unknown_frontmatter_id_cli_exit_1(tmp_path: Path, capsys) -> None:
    _sr(tmp_path, "SR-001")
    _add_course(tmp_path, "unknown_frontmatter.md")

    code = course_main(["check", "--project-root", str(tmp_path), "--json"])
    out = json.loads(capsys.readouterr().out)
    assert code == 1
    assert out["ok"] is False


# --2. unknown body wikilink token ------------------------------------------


def test_fails_on_unknown_body_token(tmp_path):
    _sr(tmp_path, "SR-001")
    _add_course(tmp_path, "unknown_body.md")

    report = check_course(tmp_path)
    assert report.ok is False
    assert any("SR-9999" in e and "[[" in e for e in report.errors)


def test_unknown_body_token_cli_exits_one(tmp_path: Path, capsys) -> None:
    _sr(tmp_path, "SR-001")
    _add_course(tmp_path, "unknown_body.md")

    code = course_main(["check", "--project-root", str(tmp_path), "--json"])
    assert code == 1


# -- 3. reports unreached known SR/spec nodes -----------------------


def test_reports_unreached_known_nodes(tmp_path):
    _sr(tmp_path, "SR-001")
    _sr(tmp_path, "SR-002")
    _spec(tmp_path, "beta")
    _add_course(tmp_path, "partial.md")  # covers only SR-001

    report = check_course(tmp_path)
    # no unknown refs remaining, but SR-002 and spec:beta stay uncovered
    assert not any("unknown" in e for e in report.errors)
    assert report.unreached
    assert set(report.unreached) >= {"SR-002", "spec:beta"}
    assert report.ok is False


# -- 4. multiple notes cover all nodes --------------------------------------


def test_multiple_notes_jointly_cover_all_nodes(tmp_path):
    _sr(tmp_path, "SR-001")
    _sr(tmp_path, "SR-002")
    _spec(tmp_path, "alpha")
    _add_course(tmp_path, "covering_a.md")  # SR-001 + SPEC-alpha
    _add_course(tmp_path, "covering_b.md")  # SR-002

    report = check_course(tmp_path)
    assert report.errors == []
    assert report.unreached == []
    assert report.ok is True
    assert len(report.notes) == 2


def test_clean_cli_exits_zero_and_emits_empty_unreached(tmp_path: Path, capsys) -> None:
    _sr(tmp_path, "SR-001")
    _spec(tmp_path, "alpha")
    _add_course(tmp_path, "covering_a.md")

    code = course_main(["check", "--project-root", str(tmp_path), "--json"])
    out = json.loads(capsys.readouterr().out)
    assert code == 0
    assert out["ok"] is True
    assert out["unreached"] == []


# -- 5. malformed traceability ----------------------------------------------


def test_reports_malformed_traceability(tmp_path):
    _sr(tmp_path, "SR-001")
    _add_course(tmp_path, "malformed_traceability.md")

    report = check_course(tmp_path)
    assert report.ok is False
    assert any("traceability" in e and "list" in e for e in report.errors)


def test_malformed_traceability_cli_exits_one(tmp_path: Path, capsys) -> None:
    _sr(tmp_path, "SR-001")
    _add_course(tmp_path, "malformed_traceability.md")

    code = course_main(["check", "--project-root", str(tmp_path), "--json"])
    assert code == 1


# -- ambiguity: bare titles/paths are rejected -----------------------


def test_rejects_ambiguous_bare_token_in_body(tmp_path):
    _sr(tmp_path, "SR-001")
    _add_course(tmp_path, "ambiguous.md")

    report = check_course(tmp_path)
    assert report.ok is False
    assert any("ambiguous" in e.lower() for e in report.errors)


# -- 6. no-course empty-state ----------------------------------------------


def test_empty_state_succeeds_with_empty_arrays(tmp_path):
    # no requirements, no specs, no course docs -> clean exit 0
    report = check_course(tmp_path)
    assert report.notes == []
    assert report.unreached == []
    assert report.errors == []
    assert report.ok is True


def test_empty_state_cli_exits_zero(tmp_path: Path, capsys) -> None:
    code = course_main(["check", "--project-root", str(tmp_path), "--json"])
    out = json.loads(capsys.readouterr().out)
    assert code == 0
    assert out["notes"] == []
    assert out["unreached"] == []
    assert out["ok"] is True