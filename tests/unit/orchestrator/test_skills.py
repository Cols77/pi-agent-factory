from pathlib import Path

import pytest

import factory.paths
from factory.orchestrator.skills import factory_skills_dir, load_skill_block

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


def test_missing_project_skill_falls_back_to_the_factorys_own(tmp_path):
    # The role skills ship with the FACTORY. Resolving them only from the repo
    # being worked on made every cross-repo run die -- polishing CareerOS blew up
    # on <careeros>/.pi/skills/verification-before-completion/SKILL.md.
    block = load_skill_block(tmp_path, "verification-before-completion")
    assert block.startswith('<skill name="verification-before-completion"')
    assert str(factory_skills_dir()) in block  # located in the factory, not tmp_path


def test_project_vendored_skill_wins_over_the_factory_copy(tmp_path):
    # roles.py documents that a project MAY vendor its own skills; local wins.
    skill_dir = tmp_path / "verification-before-completion"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\nname: verification-before-completion\n---\n\nPROJECT LOCAL OVERRIDE\n",
        encoding="utf-8",
    )
    block = load_skill_block(tmp_path, "verification-before-completion")
    assert "PROJECT LOCAL OVERRIDE" in block


def test_no_module_derives_a_factory_asset_from_the_target_repo():
    """Factory-owned assets must resolve from factory.paths, never from --repo.

    This exact mistake has now caused three silent failures: the scope-guard
    path in polish, the role skills, and the scope-guard path in the
    orchestrator's own entrypoint -- where pi refused to start, context-gather
    rejected, and the run still exited 0 while committing nothing.
    """
    src_root = Path(factory.paths.__file__).resolve().parent
    offenders = [
        py.relative_to(src_root).as_posix()
        for py in src_root.rglob("*.py")
        if 'repo_root / "pi-ext"' in py.read_text(encoding="utf-8")
        or 'project_root / "pi-ext"' in py.read_text(encoding="utf-8")
    ]
    assert offenders == [], f"derive these from factory.paths instead: {offenders}"


def test_missing_everywhere_names_both_locations(tmp_path):
    with pytest.raises(FileNotFoundError) as exc:
        load_skill_block(tmp_path, "no-such-skill")
    msg = str(exc.value)
    assert str(tmp_path) in msg
    assert str(factory_skills_dir()) in msg
