from __future__ import annotations

import warnings

import pytest
from substrate.agents.skills import factory_skills_dir, load_skill_block

pytestmark = pytest.mark.unit


def _write_skill(skill_dir, body: str) -> None:
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(body, encoding="utf-8")


def test_load_skill_block_wraps_stripped_content(tmp_path):
    _write_skill(
        tmp_path / "my-skill",
        "---\nname: my-skill\ndescription: a test skill\n---\n\n# My Skill\n\nDo the thing.\n",
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
    block = load_skill_block(tmp_path, "verification-before-completion")
    assert block.startswith('<skill name="verification-before-completion"')
    assert str(factory_skills_dir()) in block  # located in the factory, not tmp_path


def test_project_vendored_skill_wins_over_the_factory_copy(tmp_path):
    _write_skill(
        tmp_path / "verification-before-completion",
        "---\nname: verification-before-completion\n---\n\nPROJECT LOCAL OVERRIDE\n",
    )
    block = load_skill_block(tmp_path, "verification-before-completion")
    assert "PROJECT LOCAL OVERRIDE" in block


def test_substrate_loader_reads_the_same_bytes_as_the_factory_shim(tmp_path):
    """factory.orchestrator.skills.load_skill_block is now a pure re-export of
    this function -- same object, so both call paths must read identical
    content for the same fixture (ground-truth-preservation check)."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        from factory.orchestrator.skills import load_skill_block as legacy_load_skill_block

    _write_skill(
        tmp_path / "byte-check",
        "---\nname: byte-check\n---\n\nSame bytes either way.\n",
    )
    assert load_skill_block(tmp_path, "byte-check") == legacy_load_skill_block(
        tmp_path, "byte-check"
    )
    assert legacy_load_skill_block is load_skill_block


def test_factory_shim_warns_and_preserves_identity():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", DeprecationWarning)
        import importlib
        import sys

        sys.modules.pop("factory.orchestrator.skills", None)
        legacy = importlib.import_module("factory.orchestrator.skills")

    deprecation = [item for item in caught if item.category is DeprecationWarning]
    assert len(deprecation) == 1
    assert legacy.load_skill_block is load_skill_block
    assert legacy.factory_skills_dir is factory_skills_dir
