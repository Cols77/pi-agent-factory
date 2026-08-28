from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import frontmatter
import pytest

from coherence.planning.gates import _source_matches

pytestmark = pytest.mark.unit

_EXPECTED_SRS = {"SR-043", "SR-044", "SR-050", "SR-051", "SR-052", "SR-053", "SR-054"}
_PLAN = "docs/superpowers/plans/2026-08-27-feat17-planning-workflow-plan.md"


def test_feat17_requirement_sources_match_all_live_authority_anchors() -> None:
    root = Path(__file__).parents[3]
    spec_path = root / "docs" / "superpowers" / "specs" / "2026-08-27-feat17-planning-bootstrap-design.md"

    for requirement_id in sorted(_EXPECTED_SRS):
        requirement_path = root / "requirements" / f"{requirement_id}.md"
        requirement = frontmatter.load(str(requirement_path))
        assert _source_matches(root, requirement["source"], spec_path), requirement_id


def test_feat17_trace_contract_names_all_requirements_and_implementation_task() -> None:
    root = Path(__file__).parents[3]
    dossier = frontmatter.load(str(root / "docs" / "features" / "FEAT-017.md"))
    bundle = json.loads((root / "bundles" / "FEAT-017.json").read_text(encoding="utf-8"))
    task_path = root / "tasks" / "T-032-feat17-planning-workflow.md"
    task = frontmatter.load(str(task_path))

    requirements = cast(list[str], dossier["requirements"])
    members = cast(list[str], bundle["members"])
    justification = cast(list[dict[str, str]], task["justification"])
    assert set(requirements) == _EXPECTED_SRS
    assert {member.removeprefix("sr:") for member in members if member.startswith("sr:")} == _EXPECTED_SRS
    assert task["source_plan"] == _PLAN
    assert {
        target
        for entry in justification
        for kind, target in entry.items()
        if kind == "satisfies"
    } == _EXPECTED_SRS
    assert "src/coherence/planning/" in task.content
    assert "pi-ext/factory-watch/src/skill-prompt.ts" in task.content


def _source_text(root: Path, relative_path: str) -> str:
    return (root / relative_path).read_text(encoding="utf-8")


def test_feat17_authority_and_plan_freeze_the_mature_host_neutral_contracts() -> None:
    root = Path(__file__).parents[3]
    spec = _source_text(
        root,
        "docs/superpowers/specs/2026-08-27-feat17-planning-bootstrap-design.md",
    )
    plan = _source_text(
        root,
        "docs/superpowers/plans/2026-08-27-feat17-planning-workflow-plan.md",
    )
    compact_spec = " ".join(spec.split())
    compact_plan = " ".join(plan.split())

    # Intent discovery may be incomplete when the provisional authority spec is authored.
    assert "`adaptive-brainstorming` means" in spec
    assert "`provisional-spec` is intentional" in spec
    assert "before every question is answered" in compact_spec

    # Each checkpoint has an exact lifecycle boundary and artifact coverage.
    checkpoint_coverage = {
        "PLANNING_ALIGNMENT": "after provisional authority-spec authoring; compare the spec with the complete intent capture and full current SR context",
        "PLANNING_PLAN_REVIEW": "after implementation plan and generated task authoring; review the intent/spec/plan/task chain",
        "PLANNING_DERIVATION": "after candidate SR, FEAT dossier, and bundle derivation; review thin-SR fidelity, obligation completeness, duplication, contradiction, exact anchors, and closure against the current SR register",
    }
    for role, coverage in checkpoint_coverage.items():
        assert role in spec
        assert coverage in compact_spec

    # Review packets deliberately carry all current, non-deleted requirement context.
    assert "every non-deleted current SR" in compact_spec
    assert "proposed, deferred, satisfied, and active" in compact_spec
    assert "source anchors" in compact_spec
    assert "available trace context" in compact_spec

    # Classification and reviewer selection are host-owned and fail closed.
    assert "configured inexpensive classifier estimates complexity" in compact_spec
    assert "The user chooses one reviewer model" in compact_spec
    assert "all three passes and retries reuse it" in compact_spec
    assert "Missing classifier/catalog/model availability pauses the run" in compact_spec
    assert "there is no silent fallback" in compact_spec

    # A scoped fix is never its own verification.
    assert "edit only permitted planning artifacts" in compact_spec
    assert "Every fix requires a new independent reviewer invocation" in compact_spec
    assert "deterministic reread and gates" in compact_spec

    # Resolution evidence is an append-only run-local history.
    assert ".factory/planning/<run-id>/resolution-events.jsonl" in compact_plan
    assert "Earlier events are never replaced" in compact_spec
    assert "state projections are derived from it" in compact_spec

    # Semantic cleanliness and free-form answers do not substitute for SR consent.
    assert "requires a distinct explicit consent phrase after the derivation checkpoint is clean" in compact_spec
    assert "A free-text answer alone does not grant SR consent" in compact_plan

    # The first presentation milestone is text-only; the richer browser projection is deferred.
    assert "`text-summary-handoff` is the initial presentation surface" in spec
    assert "deferred-browser" in spec
    assert "interactive `/system` planning workbench" in compact_spec

    # The clean result exposes choices and a hash-bound, separately revalidated handoff.
    assert "deterministic downstream menu" in compact_spec
    assert ".factory/planning/<run-id>/handoff.json" in compact_plan
    assert ".factory/planning/<run-id>/handoff.md" in compact_plan
    assert "schema-versioned, hash-bound source" in compact_plan
    assert "new session revalidates the handoff before acting" in compact_plan
    assert "never started automatically" in compact_plan

    # Coherence owns deterministic syntax/path/link/hash enforcement; agents do not.
    assert "Keep the Python Coherence/substrate layer authoritative" in compact_plan
    assert "safe relative paths, deterministic ordering, exact hashes" in compact_spec
    assert "The mature workflow adds deterministic contracts" in compact_spec
    assert "reuse existing Coherence gate/decision/trace machinery" in compact_spec


def test_feat17_feature_acceptance_rows_preserve_implementation_and_consent_boundaries() -> None:
    root = Path(__file__).parents[3]
    dossier = _source_text(root, "docs/features/FEAT-017.md")
    bundle = json.loads((root / "bundles" / "FEAT-017.json").read_text(encoding="utf-8"))
    compact_dossier = " ".join(dossier.split())

    assert "implementation, human review, SR consent, and executed evidence remain pending" in compact_dossier
    assert "The authority spec is canonical" in dossier
    assert "No planning artifact may infer human approval or automatically start FEAT-13" in compact_dossier

    acceptance_tokens = {
        "adaptive-brainstorming",
        "provisional-spec",
        "three-checkpoints",
        "complete-sr-context",
        "selected-review-model",
        "fresh-review-loop",
        "append-only-journal",
        "explicit-sr-consent",
        "text-summary-handoff",
        "deferred-browser",
        "no-auto-execution",
    }
    assert all(token in dossier for token in acceptance_tokens)
    assert bundle["draft"] is True
    assert "human consent" in bundle["description"]
    assert "implementation evidence" in bundle["description"]
