import pytest
from pathlib import Path
from factory.orchestrator.skills import load_skill_block

pytestmark = pytest.mark.unit


def test_load_skill_block_wraps_stripped_content(tmp_path):
    skill_dir = tmp_path / "my-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\nname: my-skill\ndescription: a test skill\n---\n\n# My Skill\n\nDo the thing.\n",
        encoding="utf-8",
    )
    block = load_skill_block(tmp_path, "my-skill")
    assert block.startswith('<skill name="my-skill" location="')
    assert "# My Skill" in block
    assert "Do the thing." in block
    assert block.endswith("</skill>")
    assert "---" not in block  # frontmatter stripped


def test_load_skill_block_missing_skill_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_skill_block(tmp_path, "does-not-exist")
