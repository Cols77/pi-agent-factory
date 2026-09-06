from __future__ import annotations

from pathlib import Path

import pytest

from coherence.planning.artifact_navigator import (
    resolve_feature_context,
    seed_prompt,
)

pytestmark = pytest.mark.unit


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    _write(
        tmp_path / "docs/features/FEAT-018.md",
        "---\n"
        "id: FEAT-018\n"
        'title: "WIDGET-PIPELINE"\n'
        "description: Widgets flow from intake to dispatch.\n"
        "status: draft\n"
        "authority_spec: docs/superpowers/specs/widget-design.md\n"
        "implementation_plan: docs/superpowers/plans/widget-plan.md\n"
        "requirements:\n  - SR-090\n  - SR-091\n"
        "---\n\n# FEAT-018\n",
    )
    _write(
        tmp_path / "requirements/SR-090.md",
        "---\nid: SR-090\ntitle: \"Widget intake\"\n"
        'statement: "The system shall accept widgets."\ndomain: behavioral\n---\n\n'
        "> Status: proposed; semantic adoption remains subject to human consent.\n",
    )
    _write(tmp_path / "docs/superpowers/specs/widget-design.md", "# Widget design\n")
    return tmp_path


def test_resolves_feature_frontmatter_verbatim(project: Path) -> None:
    context = resolve_feature_context(project, "FEAT-018")

    assert context["title"] == "WIDGET-PIPELINE"
    assert context["description"] == "Widgets flow from intake to dispatch."
    assert context["status"] == "draft"
    assert context["feature_path"] == "docs/features/FEAT-018.md"


def test_resolves_each_requirement_with_its_statement_and_presence(project: Path) -> None:
    context = resolve_feature_context(project, "FEAT-018")
    by_id = {item["id"]: item for item in context["requirements"]}

    assert by_id["SR-090"]["present"] is True
    assert by_id["SR-090"]["statement"] == "The system shall accept widgets."
    assert "proposed" in by_id["SR-090"]["status_note"]
    assert by_id["SR-091"]["present"] is False
    assert by_id["SR-091"]["statement"] is None


def test_reports_drafted_and_missing_artifacts_without_erroring(project: Path) -> None:
    context = resolve_feature_context(project, "FEAT-018")

    assert context["authority_spec"]["present"] is True
    assert context["implementation_plan"]["present"] is False
    assert context["bundle"]["present"] is False
    assert "docs/superpowers/plans/widget-plan.md" in context["missing"]
    assert "requirements/SR-091.md" in context["missing"]


def test_unknown_feature_is_reported_not_raised(tmp_path: Path) -> None:
    context = resolve_feature_context(tmp_path, "FEAT-777")

    assert context["present"] is False
    assert context["requirements"] == []


@pytest.mark.parametrize("feature_id", ["", "FEAT-18", "feat-018", "../escape", "FEAT-018;rm"])
def test_unsafe_or_malformed_feature_ids_are_rejected(tmp_path: Path, feature_id: str) -> None:
    with pytest.raises(ValueError, match="feature_id"):
        resolve_feature_context(tmp_path, feature_id)


def test_seed_prompt_quotes_the_feature_verbatim_without_paraphrase(project: Path) -> None:
    prompt = seed_prompt(resolve_feature_context(project, "FEAT-018"))

    assert "FEAT-018" in prompt
    assert "WIDGET-PIPELINE" in prompt
    assert "Widgets flow from intake to dispatch." in prompt
    assert "docs/features/FEAT-018.md" in prompt
