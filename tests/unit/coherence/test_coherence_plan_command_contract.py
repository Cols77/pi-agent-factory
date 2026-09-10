from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

COMMAND = Path(__file__).parents[3] / ".claude" / "commands" / "coherence-plan.md"


@pytest.fixture(scope="module")
def text() -> str:
    return COMMAND.read_text(encoding="utf-8")


def test_frontmatter_declares_the_argument(text: str) -> None:
    assert text.startswith("---\n")
    assert "argument-hint:" in text


def test_every_stage_uses_an_adapter_module(text: str) -> None:
    for module in ("artifact_navigator", "guided_entrypoint", "guided_pipeline",
                   "legal_actions_adapter"):
        assert f"coherence.planning.{module}" in text


def test_command_never_calls_the_backend_directly(text: str) -> None:
    assert "uv run coherence plan" not in text


def test_author_requirements_has_explicit_manifest_transport(text: str) -> None:
    assert "author-requirements" in text
    assert "coherence.planning.guided_pipeline write-artifact-manifest" in text
    assert "--artifacts-json" in text
    assert "sha256" in text


def test_human_decisions_are_marked_as_never_the_models(text: str) -> None:
    lowered = text.lower()
    assert "never choose" in lowered
    assert "resolve/revise/defer/accept" in lowered
    assert "provisional" in lowered and "cancelled" in lowered and "needs_user" in lowered


def test_authoring_stages_are_present_with_reviews(text: str) -> None:
    lowered = text.lower()
    assert "author the spec" in lowered
    assert "author the plan" in lowered
    assert lowered.count("subagent") >= 2


def test_decomposition_and_parity_gate_are_present(text: str) -> None:
    assert "--decompose" in text
    assert "PLAN_TASK_PARITY" in text


def test_non_executing_boundary_is_stated(text: str) -> None:
    lowered = text.lower()
    assert "starts_automatically" in lowered
    assert "downstream" in lowered


def test_run_id_grammar_and_usage_message_are_present(text: str) -> None:
    assert "^[A-Za-z0-9][A-Za-z0-9._-]*$" in text
    assert "usage: /coherence-plan <run-id-or-FEAT-NNN>" in text


def test_start_or_resume_dispatch_is_not_swapped(text: str) -> None:
    """Pin which verb each status outcome dispatches to. A swap here (calling
    `start` on `ok: true` or `resume` on `ok: false`) would double-start every
    existing run and never resume one, and every other assertion in this file
    is blind to that swap."""
    section = text[text.index("## 2. Start or resume") : text.index("## 3.")]

    true_branch = section[section.index("`ok: true`") : section.index("`ok: false`")]
    false_branch = section[section.index("`ok: false`") :]

    assert "resume" in true_branch
    assert "start" not in true_branch
    assert "start" in false_branch


def test_claude_command_labels_manual_compatibility_route_separately_from_guided_route(
    text: str,
) -> None:
    lowered = text.lower()
    assert "compatibility route" in lowered
    assert "guided route" in lowered
    assert "does not claim a lifecycle-derived stage" in lowered
    assert "legal-actions" in lowered
