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


@pytest.mark.sr("SR-005")
def test_fails_on_unknown_frontmatter_id(tmp_path):
    _sr(tmp_path, "SR-001")
    _spec(tmp_path, "alpha")
    _add_course(tmp_path, "unknown_frontmatter.md")

    report = check_course(tmp_path)
    assert report.ok is False
    assert any("SR-9999" in e and "traceability" in e for e in report.errors)


@pytest.mark.sr("SR-005")
def test_unknown_frontmatter_id_cli_exit_1(tmp_path: Path, capsys) -> None:
    _sr(tmp_path, "SR-001")
    _add_course(tmp_path, "unknown_frontmatter.md")

    code = course_main(["check", "--project-root", str(tmp_path), "--json"])
    out = json.loads(capsys.readouterr().out)
    assert code == 1
    assert out["ok"] is False


# --2. unknown body wikilink token ------------------------------------------


@pytest.mark.sr("SR-005")
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


@pytest.mark.sr("SR-005")
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


@pytest.mark.sr("SR-005")
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


# -- Defect 1: a malformed/unrelated spec surfaces SpecError cleanly (exit 1) --


def _malformed_spec(root: Path, name: str = "broken") -> None:
    """A spec with an id-less frontmatter block -> build_graph raises SpecError."""
    p = root / "docs" / "superpowers" / "specs" / f"{name}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    # missing required frontmatter id/title/status -> deterministic SpecError
    p.write_text("---\ntitle: Broken\nstatus: approved\n---\nbody\n", encoding="utf-8")


def test_malformed_spec_is_surfaced_not_crash(tmp_path):
    _sr(tmp_path, "SR-001")
    _add_course(tmp_path, "partial.md")
    _malformed_spec(tmp_path)

    # must not raise; SpecError is captured into the report's errors channel
    report = check_course(tmp_path)
    assert report.ok is False
    assert any("spec" in e.lower() and "error" in e.lower() for e in report.errors)
    assert "broken.md" in " ".join(report.errors)


def test_malformed_spec_cli_exits_one_cleanly(tmp_path: Path, capsys) -> None:
    _sr(tmp_path, "SR-001")
    _add_course(tmp_path, "partial.md")
    _malformed_spec(tmp_path)

    code = course_main(["check", "--project-root", str(tmp_path), "--json"])
    out = json.loads(capsys.readouterr().out)
    assert code == 1
    assert out["ok"] is False
    assert out["errors"]


def test_duplicate_spec_ids_with_differing_content_surface_cleanly(
    tmp_path: Path, capsys
) -> None:
    _spec(tmp_path, "dup")
    _add_course(tmp_path, "covering_a.md")
    p2 = tmp_path / "docs" / "superpowers" / "specs" / "dup2.md"
    p2.parent.mkdir(parents=True, exist_ok=True)
    p2.write_text(
        "---\nid: dup\ntitle: Different\nstatus: approved\n---\nbody\n",
        encoding="utf-8",
    )

    report = check_course(tmp_path)
    assert report.ok is False
    assert any("duplicate spec id" in e for e in report.errors)

    code = course_main(["check", "--project-root", str(tmp_path), "--json"])
    out = json.loads(capsys.readouterr().out)
    assert code == 1
    assert out["ok"] is False
    assert any("duplicate spec id" in e for e in out["errors"])


# -- Defect 2: a valid spec id outside the SPEC-... grammar is not a false
# -- unreached (it can never be covered) --


def test_non_course_grammar_spec_id_not_false_unreached(tmp_path):
    _sr(tmp_path, "SR-001")
    # id contains characters the course grammar cannot reference
    _spec(tmp_path, "Foo Bar", title="Foo Bar")
    _add_course(tmp_path, "partial.md")  # covers only SR-001

    report = check_course(tmp_path)
    # spec:Foo Bar is known but cannot be referenced by any SPEC-... token
    assert "spec:Foo Bar" in report.non_referenceable
    # it must NOT be reported unreached (that failure could never be covered)
    assert "spec:Foo Bar" not in report.unreached
    # the normal id coverage math still holds for the referenceable node
    assert "SR-001" not in report.unreached  # covered by partial.md
    assert report.unreached == []