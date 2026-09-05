from __future__ import annotations

from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

PROJECT_ROOT = Path(__file__).parents[3]
SKILL_PATH = PROJECT_ROOT / ".agents" / "skills" / "coherence-plan" / "SKILL.md"
METADATA_PATH = (
    PROJECT_ROOT
    / ".agents"
    / "skills"
    / "coherence-plan"
    / "agents"
    / "openai.yaml"
)


def _frontmatter_and_body(path: Path) -> tuple[dict[str, object], str]:
    raw = path.read_text(encoding="utf-8")
    assert raw.startswith("---\n")
    _, frontmatter, body = raw.split("---\n", 2)
    parsed = yaml.safe_load(frontmatter)
    assert isinstance(parsed, dict)
    return parsed, body


def test_skill_has_required_frontmatter_and_workflow_contract() -> None:
    frontmatter, body = _frontmatter_and_body(SKILL_PATH)
    description = frontmatter.get("description")

    assert frontmatter.get("name") == "coherence-plan"
    assert isinstance(description, str) and description.strip()

    normalized = " ".join(body.lower().replace("`", "").split())
    required_terms = (
        "$coherence-plan",
        "built-in /plan",
        "named run id",
        "concrete planning request",
        "[a-za-z0-9][a-za-z0-9._-]*",
        "explicit start",
        "explicit resume",
        "no silent fallback",
        "uv run python .agents/skills/coherence-plan/scripts/coherence_plan.py legal-actions",
        "coherence remains the authority",
        "never infer",
        "blocked",
        "legal_next_actions",
        "starts_automatically",
        "author-spec",
        "author-plan",
        "review-spec",
        "review-plan",
        "display-only",
        "fix-review-fix",
        "never grant consent",
        "never adopt",
        "warning acceptance",
        "gate bypass",
        "never launch downstream",
        "merge",
        "push",
        "handoff",
        "changed files",
        "evidence",
        "next legal action",
    )
    missing = [term for term in required_terms if term not in normalized]
    assert not missing, f"skill contract terms missing: {missing}"


def test_skill_requires_authoritative_projection_after_state_changes() -> None:
    _, body = _frontmatter_and_body(SKILL_PATH)
    normalized = " ".join(body.lower().replace("`", "").split())

    assert "after every state-changing operation" in normalized
    assert "do not infer state or actions" in normalized
    assert "starts_automatically=false" in normalized
    assert "apply fixes" in normalized
    assert "re-check legal actions" in normalized
    assert "review again" in normalized


def test_metadata_exposes_safe_codex_invocation() -> None:
    metadata = yaml.safe_load(METADATA_PATH.read_text(encoding="utf-8"))

    assert isinstance(metadata, dict)
    interface = metadata.get("interface")
    assert isinstance(interface, dict)
    assert interface.get("display_name") == "Coherence Plan"
    assert isinstance(interface.get("short_description"), str)
    assert interface["short_description"].strip()

    default_prompt = interface.get("default_prompt")
    assert isinstance(default_prompt, str)
    assert "$coherence-plan" in default_prompt
    assert "downstream" not in default_prompt.lower()
