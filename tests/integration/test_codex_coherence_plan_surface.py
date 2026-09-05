from pathlib import Path

import pytest


pytestmark = pytest.mark.integration


def test_codex_coherence_plan_surface_is_documented():
    repo_root = Path(__file__).resolve().parents[2]

    for relative_path in (
        ".agents/skills/coherence-plan/SKILL.md",
        ".agents/skills/coherence-plan/scripts/coherence_plan.py",
        ".agents/skills/coherence-plan/agents/openai.yaml",
    ):
        assert (repo_root / relative_path).is_file(), relative_path

    readme = (repo_root / "README.md").read_text(encoding="utf-8")
    assert "$coherence-plan" in readme
    assert "coherence plan legal-actions" in readme
