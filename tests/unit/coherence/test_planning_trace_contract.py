from __future__ import annotations

import json
import hashlib
from pathlib import Path
from typing import cast

import frontmatter
import pytest

from coherence.planning.gates import _source_matches, validate_requirement_consent, validate_sr_consent
from coherence.planning.run import planning_report_digest

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
    bundle_requirements = [
        member.removeprefix("sr:")
        for member in members
        if member.startswith("sr:")
    ]
    satisfies = [
        target
        for entry in justification
        for kind, target in entry.items()
        if kind == "satisfies"
    ]
    assert len(requirements) == len(_EXPECTED_SRS)
    assert len(requirements) == len(set(requirements))
    assert set(requirements) == _EXPECTED_SRS
    assert len(bundle_requirements) == len(_EXPECTED_SRS)
    assert len(bundle_requirements) == len(set(bundle_requirements))
    assert set(bundle_requirements) == _EXPECTED_SRS
    assert task["source_plan"] == _PLAN
    assert len(satisfies) == len(_EXPECTED_SRS)
    assert len(satisfies) == len(set(satisfies))
    assert set(satisfies) == _EXPECTED_SRS
    assert "src/coherence/planning/" in task.content
    assert "pi-ext/factory-watch/src/skill-prompt.ts" in task.content


def _source_text(root: Path, relative_path: str) -> str:
    return (root / relative_path).read_text(encoding="utf-8")


def _section(text: str, heading: str, next_heading: str | None) -> str:
    start = text.index(heading)
    end = len(text) if next_heading is None else text.index(next_heading, start + len(heading))
    return text[start:end]


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
    compact_brainstorm = " ".join(
        _section(
            spec,
            "#### 3a.1 Adaptive clarify and align",
            "### 3b. Ordering and ownership",
        ).split()
    )
    compact_checkpoint = " ".join(
        _section(spec, "### 3c. Semantic checkpoints", "### 3d. Deterministic contract and available gates").split()
    )
    compact_deterministic = " ".join(
        _section(spec, "### 3d. Deterministic contract and available gates", "### 3e. Review, resolution, escalation, and consent").split()
    )
    compact_review = " ".join(
        _section(spec, "### 3e. Review, resolution, escalation, and consent", "### 3f. Summary, downstream menu, and handoff").split()
    )
    compact_handoff = " ".join(
        _section(spec, "### 3f. Summary, downstream menu, and handoff", "## 4. Canonical artifact contracts").split()
    )
    compact_artifacts = " ".join(
        _section(spec, "## 4. Canonical artifact contracts", "## 5. Scope and explicit deferrals").split()
    )
    compact_plan_persistence = " ".join(
        _section(plan, "### 1.9 Persistence and handoff", "## 2. Existing substrate and dependencies to reuse").split()
    )
    compact_plan_consent = " ".join(
        _section(plan, "### 1.5 Human review and consent", "### 1.6 Requirement model").split()
    )
    plan_architecture = " ".join(
        plan.split("**Architecture:**", 1)[1].split("**Tech Stack:**", 1)[0].split()
    )

    # Intent discovery may be incomplete when the provisional authority spec is authored.
    assert "`adaptive-brainstorming` means" in compact_brainstorm
    assert "`provisional-spec` is intentional" in compact_brainstorm
    assert "before every question is answered" in compact_brainstorm

    # Each checkpoint has an exact lifecycle boundary and artifact coverage.
    checkpoint_coverage = {
        "PLANNING_ALIGNMENT": "after provisional authority-spec authoring; compare the spec with the complete intent capture and full current SR context",
        "PLANNING_PLAN_REVIEW": "after implementation plan and generated task authoring; review the intent/spec/plan/task chain",
        "PLANNING_DERIVATION": "after candidate SR, FEAT dossier, and bundle derivation; review thin-SR fidelity, obligation completeness, duplication, contradiction, exact anchors, and closure against the current SR register",
    }
    for role, coverage in checkpoint_coverage.items():
        assert role in compact_checkpoint
        assert coverage in compact_checkpoint

    # Review packets deliberately carry all current, non-deleted requirement context.
    assert "every non-deleted current SR" in compact_review
    assert "proposed, deferred, satisfied, and active" in compact_review
    assert "source anchors" in compact_review
    assert "available trace context" in compact_review

    # Classification and reviewer selection are host-owned and fail closed.
    assert "configured inexpensive classifier estimates complexity" in compact_review
    assert "The user chooses one reviewer model" in compact_review
    assert "all three passes and retries reuse it" in compact_review
    assert "Missing classifier/catalog/model availability pauses the run" in compact_review
    assert "there is no silent fallback" in compact_review

    # A scoped fix is never its own verification.
    assert "edit only permitted planning artifacts" in compact_review
    assert "Every fix requires a new independent reviewer invocation" in compact_review
    assert "deterministic reread and gates" in compact_review

    # Resolution evidence is an append-only run-local history.
    assert ".factory/planning/<run-id>/resolution-events.jsonl" in compact_plan_persistence
    assert "Earlier events are never replaced" in compact_review
    assert "state projections are derived from it" in compact_review

    # Semantic cleanliness and free-form answers do not substitute for SR consent.
    assert "requires a distinct explicit consent phrase after the derivation checkpoint is clean" in compact_review
    assert "A free-text answer alone does not grant SR consent" in compact_plan_consent

    # The first presentation milestone is text-only; the richer browser projection is deferred.
    assert "`text-summary-handoff` is the initial presentation surface" in compact_handoff
    assert "deferred-browser" in compact_handoff
    assert "interactive `/system` planning workbench" in compact_handoff

    # The clean result exposes choices and a hash-bound, separately revalidated handoff.
    assert "deterministic downstream menu" in compact_handoff
    assert ".factory/planning/<run-id>/handoff.json" in compact_handoff
    assert ".factory/planning/<run-id>/handoff.md" in compact_handoff
    assert "schema-versioned, hash-bound source" in compact_plan_persistence
    assert "new session revalidates the handoff before acting" in compact_plan_persistence
    assert "never started automatically" in compact_plan_persistence

    # Coherence owns deterministic syntax/path/link/hash enforcement; agents do not.
    assert "Keep the Python Coherence/substrate layer authoritative" in plan_architecture
    assert "safe relative paths, deterministic ordering, exact hashes" in compact_artifacts
    assert "The mature workflow adds deterministic contracts" in compact_deterministic
    assert "reuse existing Coherence gate/decision/trace machinery" in compact_deterministic


def test_feat17_feature_acceptance_rows_preserve_implementation_and_consent_boundaries() -> None:
    root = Path(__file__).parents[3]
    dossier = _source_text(root, "docs/features/FEAT-017.md")
    bundle = json.loads((root / "bundles" / "FEAT-017.json").read_text(encoding="utf-8"))
    compact_dossier = " ".join(dossier.split())
    compact_acceptance = " ".join(
        _section(dossier, "## Mature workflow acceptance boundary", None).split()
    )

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
    assert all(token in compact_acceptance for token in acceptance_tokens)
    assert bundle["draft"] is True
    assert "human consent" in bundle["description"]
    assert "implementation evidence" in bundle["description"]


def test_feat17_adopted_srs_bind_consent_to_clean_derivation() -> None:
    root = Path(__file__).parents[3]
    run_dir = root / ".factory" / "planning" / "feat17-finalized-planning"
    derivation = json.loads((run_dir / "derivation-report.json").read_text(encoding="utf-8"))
    consent = json.loads((run_dir / "sr-consent.json").read_text(encoding="utf-8"))

    assert derivation["ok"] is True
    assert derivation["findings"] == []
    assert consent["schema"] == 2
    assert consent["run_id"] == "feat17-finalized-planning"
    assert consent["decision"] == "approve"
    assert consent["reviewer"] == "human"
    assert consent["phrase"] == "I explicitly consent to adopt exactly these candidate SRs."
    assert consent["candidate_srs"] == sorted(_EXPECTED_SRS)
    assert consent["derivation_report_sha256"] == planning_report_digest(derivation)
    expected_hashes = {
        artifact["path"]: artifact["sha256"] for artifact in derivation["artifacts"]
    }
    assert consent["artifact_hashes"] == expected_hashes
    assert validate_sr_consent(
        root,
        "feat17-finalized-planning",
        sorted(_EXPECTED_SRS),
        consent["derivation_report_sha256"],
        expected_hashes,
    ) == (True, "explicit SR consent is current and exact")
    assert validate_requirement_consent(
        root,
        "feat17-finalized-planning",
        root / "docs/superpowers/specs/2026-08-27-feat17-planning-bootstrap-design.md",
    ) == (True, "requirement consent and FEAT-017 registration are current")
    for path, digest in expected_hashes.items():
        assert hashlib.sha256((root / path).read_bytes()).hexdigest() == digest, path
