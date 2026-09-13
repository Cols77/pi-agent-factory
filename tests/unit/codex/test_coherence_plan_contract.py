from __future__ import annotations

import re
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


def _section(body: str, heading: str) -> str:
    start = body.index(f"## {heading}")
    next_heading = re.search(r"^## ", body[start + len(heading) + 3 :], re.MULTILINE)
    end = start + len(heading) + 3 + next_heading.start() if next_heading else len(body)
    return body[start:end]


def _safe_loop_allowlist(body: str) -> list[str]:
    section = _section(body, "Safe fix-review-fix loop")
    marker = "Only these backend-declared actions may enter the bounded loop:"
    list_text = section.split(marker, 1)[1].split("Unknown actions", 1)[0]
    return re.findall(r"^\s*-\s*`([^`]+)`\s*$", list_text, re.MULTILINE)


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
        "explicitly choose either start or resume",
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
        "run-planning-gates",
        "write-artifact-manifest",
        "write-cross-artifact-review",
        "record-sr-consent",
        "propose-challenge",
        "intent",
        "spec",
        "plan",
        "feature",
        "bundle",
        "requirements",
        "fresh sha-256",
        "stale hashes are not evidence",
        "never hand-edit",
        "schema-2",
        "schema-1",
        "action_registry",
        "run_identity",
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


def test_safe_loop_preserves_exact_allowlist_and_current_backend_actions() -> None:
    _, body = _frontmatter_and_body(SKILL_PATH)
    section = _section(body, "Safe fix-review-fix loop")
    normalized = " ".join(section.lower().replace("`", "").split())

    assert _safe_loop_allowlist(body) == [
        "author-spec",
        "author-plan",
        "review-spec",
        "review-plan",
    ]
    for action in (
        "inspect-handoff",
        "revalidate-handoff",
        "select-downstream-workflow",
        "create-downstream-session",
        "resolve-blocking-input",
    ):
        assert action in normalized
    assert "present every backend action exactly as returned" in normalized
    assert "display-only" in normalized
    assert "never be translated, renamed, or auto-selected" in normalized
    assert "if no allowlisted action is declared" in normalized
    assert "stop for human decision" in normalized
    assert "do not claim the loop was performed" in normalized


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
