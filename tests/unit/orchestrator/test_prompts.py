import pytest
from pathlib import Path
from factory.orchestrator.types import AgentRole
from factory.orchestrator.ledger import Task
from factory.orchestrator.prompts import compose_prompt
from ._skill_fixtures import write_skill_stubs

pytestmark = pytest.mark.unit

TASK = Task(id="T-001", title="Do X", status="todo", dod=["crit A"], body="body text", path=Path("t"))


def test_prompt_is_deterministic_and_includes_key_parts(tmp_path):
    write_skill_stubs(tmp_path)
    skills_dir = tmp_path / ".pi" / "skills"
    kb = [{"id": "kb-0001", "title": "watch arming"}]
    a = compose_prompt(AgentRole.DEV, TASK, manifest=None, kb_entries=kb, feedback="fix Y", skills_dir=skills_dir)
    b = compose_prompt(AgentRole.DEV, TASK, manifest=None, kb_entries=kb, feedback="fix Y", skills_dir=skills_dir)
    assert a == b
    for needle in ["T-001", "Do X", "crit A", "kb-0001", "watch arming", "fix Y", "test-driven-development"]:
        assert needle in a
    assert '<skill name="test-driven-development"' in a


def test_no_feedback_no_kb_still_valid(tmp_path):
    write_skill_stubs(tmp_path)
    skills_dir = tmp_path / ".pi" / "skills"
    out = compose_prompt(AgentRole.REVIEW, TASK, skills_dir=skills_dir)
    assert "T-001" in out and "crit A" in out


def test_compose_prompt_tolerates_non_dict_manifest_context(tmp_path):
    """Malformed manifest with context=None should not raise AttributeError."""
    write_skill_stubs(tmp_path)
    skills_dir = tmp_path / ".pi" / "skills"
    manifest = {"context": None}
    out = compose_prompt(AgentRole.DEV, TASK, manifest=manifest, skills_dir=skills_dir)
    assert isinstance(out, str)
    assert "T-001" in out


def test_compose_prompt_tolerates_non_dict_context_value(tmp_path):
    """Malformed manifest with context as non-dict should degrade gracefully."""
    write_skill_stubs(tmp_path)
    skills_dir = tmp_path / ".pi" / "skills"
    manifest = {"context": "invalid_string"}
    out = compose_prompt(AgentRole.DEV, TASK, manifest=manifest, skills_dir=skills_dir)
    assert isinstance(out, str)
    assert "T-001" in out


def test_compose_prompt_requires_every_vendored_skill_to_exist(tmp_path):
    """Missing skill file for a role's ROLE_SKILLS entry is a hard error, not a
    silent fallback to a bare skill name."""
    (tmp_path / ".pi" / "skills").mkdir(parents=True)  # empty -- nothing vendored
    with pytest.raises(FileNotFoundError):
        compose_prompt(AgentRole.REVIEW, TASK, skills_dir=tmp_path / ".pi" / "skills")


# Repo root, resolved from this file's location (tests/unit/orchestrator/test_prompts.py).
_REPO_ROOT = Path(__file__).resolve().parents[3]
_REAL_SKILLS_DIR = _REPO_ROOT / ".pi" / "skills"


def test_compose_prompt_works_against_real_vendored_skills_for_live_roles():
    """Regression guard for the final-review "Finding": ROLE_SKILLS must stay in
    sync with what's actually vendored under the real .pi/skills/ directory for
    every role that is actually invoked today (CONTEXT_GATHERER, DEV, REVIEW --
    see nodes.py). Deliberately does NOT use write_skill_stubs, since that helper
    stubs over exactly the gap this test needs to catch: it exercises the REAL
    repo .pi/skills/ directory, not a synthetic one. If any of the 8 skills these
    three roles depend on were ever deleted/renamed under .pi/skills/ without
    updating ROLE_SKILLS (or vice versa), load_skill_block would raise
    FileNotFoundError and this test would fail.
    """
    kb = [{"id": "kb-0001", "title": "watch arming"}]

    context_gatherer_prompt = compose_prompt(
        AgentRole.CONTEXT_GATHERER, TASK, skills_dir=_REAL_SKILLS_DIR,
    )
    dev_prompt = compose_prompt(
        AgentRole.DEV, TASK, manifest=None, kb_entries=kb, feedback=None,
        skills_dir=_REAL_SKILLS_DIR,
    )
    review_prompt = compose_prompt(
        AgentRole.REVIEW, TASK, skills_dir=_REAL_SKILLS_DIR,
    )

    for prompt in (context_gatherer_prompt, dev_prompt, review_prompt):
        assert isinstance(prompt, str)
        assert "T-001" in prompt
