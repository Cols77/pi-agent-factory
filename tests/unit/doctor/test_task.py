import frontmatter
import pytest
from factory.doctor.write import emit_task, mint

pytestmark = pytest.mark.unit


def _repo(tmp_path):
    specs = tmp_path / "docs" / "superpowers" / "specs"
    specs.mkdir(parents=True)
    (specs / "a.md").write_text("# A\n", encoding="utf-8")
    mint(tmp_path, "docs/superpowers/specs/a.md", "t", "s", "behavioral")
    return tmp_path


def test_emit_task_links_the_requirement(tmp_path):
    path = emit_task(
        _repo(tmp_path),
        "SR-001",
        "Implement the zone_clear_resume_rate scorer",
        ["SCORERS exposes zone_clear_resume_rate", "unit test covers pass and fail trials"],
        body="Add the scorer to src/drone/validation/scorers.py.",
    )
    post = frontmatter.load(str(path))
    assert post["id"] == "T-001"
    assert post["satisfies"] == ["SR-001"]
    assert post["status"] == "todo"
    assert len(post["dod"]) == 2
    assert "src/drone/validation/scorers.py" in post.content


def test_emit_task_assigns_consecutive_ids(tmp_path):
    repo = _repo(tmp_path)
    first = emit_task(repo, "SR-001", "one", ["d"])
    second = emit_task(repo, "SR-001", "two", ["d"])
    assert (first.name, second.name) == ("T-001.md", "T-002.md")


def test_emit_task_refuses_an_unknown_requirement(tmp_path):
    with pytest.raises(ValueError, match="SR-404"):
        emit_task(_repo(tmp_path), "SR-404", "t", ["d"])


def test_emit_task_refuses_an_empty_dod(tmp_path):
    with pytest.raises(ValueError, match="dod"):
        emit_task(_repo(tmp_path), "SR-001", "t", [])
