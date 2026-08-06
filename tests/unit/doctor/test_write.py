import pytest
from factory.doctor.write import mint
from factory.requirements.register import parse_requirement

pytestmark = pytest.mark.unit


def _repo(tmp_path):
    specs = tmp_path / "docs" / "superpowers" / "specs"
    specs.mkdir(parents=True)
    (specs / "a.md").write_text("# A\n", encoding="utf-8")
    return tmp_path


def test_mint_writes_a_parseable_proposed_requirement(tmp_path):
    path = mint(
        _repo(tmp_path),
        source="docs/superpowers/specs/a.md",
        title="Zone clear abandons investigate",
        statement="When the zone clears, the system shall resume patrol.",
        domain="behavioral",
    )
    req = parse_requirement(path)
    assert req.id == "SR-001"
    assert req.binding is None
    assert req.source == "docs/superpowers/specs/a.md"
    assert req.statement.startswith("When the zone clears")
    assert req.domain == "behavioral"


def test_mint_assigns_consecutive_ids(tmp_path):
    repo = _repo(tmp_path)
    first = mint(repo, "docs/superpowers/specs/a.md", "one", "s", "behavioral")
    second = mint(repo, "docs/superpowers/specs/a.md", "two", "s", "behavioral")
    assert (first.name, second.name) == ("SR-001.md", "SR-002.md")


def test_mint_refuses_a_source_that_does_not_exist(tmp_path):
    # Mirrors link_satisfies refusing a non-existent target: a provenance pointer
    # that dangles is worse than none. Nothing is created on the way out.
    with pytest.raises(ValueError, match="no such source"):
        mint(_repo(tmp_path), "docs/superpowers/specs/missing.md", "t", "s", "behavioral")
    assert not (tmp_path / "requirements").exists()
