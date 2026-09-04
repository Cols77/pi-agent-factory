from __future__ import annotations

import json

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
        _section(spec, "### 3f. Summary, downstream menu, and handoff", "### 3g. State machine and invariants").split()
    )
    compact_artifacts = " ".join(
        _section(spec, "### 2.2 Canonical and derived outputs", "### 2.3 Exact original prompt and challenge provenance").split()
    )
    compact_plan_persistence = " ".join(
        _section(plan, "### 2.1 Run inputs and evidence paths", "### 2.2 Real producer interface").split()
    )
    compact_plan_consent = " ".join(
        _section(plan, "### 2.4 Shared DecisionFile, boundary, and handoff contracts (prerequisite)", "## 2.5 Secure provenance and path-write contract").split()
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
        "PLANNING_ALIGNMENT": "after the real provisional-spec producer and compares the spec with complete intent/provenance and full current SR context",
        "CANDIDATE_SR_ALIGNMENT": "after the one run-local candidate SR derivation and before plan authoring; it checks duplicates, conflicts, unsupported claims, compatibility, missing obligations, complete context, and feature boundaries",
        "CROSS_ARTIFACT_ALIGNMENT": "after implementation-plan authoring and task materialization; it checks the intent/spec/candidate/task chain and bidirectional trace closure",
    }
    for role, coverage in checkpoint_coverage.items():
        assert role in compact_checkpoint
        assert coverage in compact_checkpoint

    # Review packets deliberately carry all current, non-deleted requirement context.
    assert "complete non-deleted SR context" in compact_review
    assert "proposed, deferred, satisfied, and active" in compact_review
    assert "source anchors" in compact_review
    assert "available trace context" in compact_review

    # Reviewer selection and scoped fixes remain host-owned and independent.
    assert "The selected reviewer model is fixed for the run" in compact_review
    assert "A scoped fix is followed by deterministic reread and a fresh independent review" in compact_review
    assert "resolution history is append-only" in compact_review

    # Resolution evidence is an append-only run-local history.
    assert ".factory/planning/<run-id>/resolution-events.jsonl" in compact_plan_persistence
    assert "resolution history is append-only" in compact_review

    # Semantic cleanliness and free-form answers do not substitute for SR consent.
    assert "A clean review never grants consent" in compact_review
    assert "Consent binds exact candidate IDs/artifact hash" in compact_plan_consent

    # The first presentation milestone is text-only; the richer browser projection is deferred.
    assert "The first presentation is a text summary" in compact_handoff
    assert "A richer browser workbench is deferred" in compact_handoff

    # The clean result exposes choices and a hash-bound, separately revalidated handoff.
    assert "clean run exposes an explicit menu" in compact_handoff
    assert "hash-bound handoff" in compact_handoff
    assert "new session revalidates it before acting" in compact_handoff
    assert "starts_automatically: false" in compact_handoff
    assert "append-only revision index" in compact_plan_persistence
    assert "current pointer is replaceable derived state" in compact_plan_persistence
    assert "starts_automatically: false" in compact_plan_consent

    # Coherence owns deterministic syntax/path/link/hash enforcement; agents do not.
    assert "Coherence/substrate remains authoritative for canonical artifacts, schemas" in plan_architecture
    assert "The run produces or references these artifacts. Run-local evidence is never overwritten in place" in compact_artifacts
    assert "Every producer and checkpoint uses strict parsing" in compact_deterministic
    assert "Existing Coherence gate, decision, trace, register, and filesystem machinery is reused rather than replaced" in compact_deterministic


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


def test_feat17_legacy_evidence_cannot_establish_current_consent() -> None:
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
    # This committed snapshot is legacy aggregate evidence, not current adoption.
    # It references an untracked intent snapshot and incorrectly includes shared SR-050.
    assert ".intent/intent.json" in expected_hashes
    assert "SR-050" in consent["candidate_srs"]
    owned_srs = sorted(_EXPECTED_SRS - {"SR-050"})
    current_run_id = "feat17-baseline-reconciliation"
    assert not (root / ".factory" / "planning" / current_run_id).exists()
    assert validate_sr_consent(
        root,
        current_run_id,
        owned_srs,
        consent["derivation_report_sha256"],
        expected_hashes,
    )[0] is False
    assert validate_requirement_consent(
        root,
        current_run_id,
        root / "docs" / "superpowers" / "specs" / "2026-08-27-feat17-planning-bootstrap-design.md",
    )[0] is False


def test_feat17_plan_amendment_reserves_tasks_and_registers_proposed_sr055() -> None:
    root = Path(__file__).parents[3]
    plan = _source_text(root, _PLAN)
    sr055 = frontmatter.load(str(root / "requirements" / "SR-055.md"))
    compact_plan = " ".join(plan.split())

    assert "Task identity reservation amendment" in plan
    assert "`T-046` through `T-056`" in compact_plan
    assert "2d752d16c9333b3f0a759e454a17f7e56fa7801b" in compact_plan
    assert "`source_plan` path + `source_task` number" in compact_plan
    assert "`T-046` | implements `SR-043`, `SR-051`, `SR-052`; maintains `SR-054` foundation" in compact_plan
    assert "`T-053` | implements `SR-043`, `SR-051`, `SR-054`, `SR-055`" in compact_plan
    assert "`T-055` | verifies/maintains all seven owned SRs" in compact_plan
    assert "Omitted SR/task pairs have no finding" in compact_plan
    assert "No `satisfies` relationship is asserted before independent implementation acceptance" in compact_plan
    assert "`SR-050` remains foreign/shared and read-only" in compact_plan

    assert sr055["id"] == "SR-055"
    assert sr055["title"] == "Versioned planning gate pack enforcement"
    assert sr055["domain"] == "behavioral"
    assert sr055["upstream"] == ["SR-035", "SR-036"]
    assert sr055["source"] == (
        "docs/superpowers/specs/2026-08-27-feat17-planning-bootstrap-design.md#3d"
    )
    statement = cast(str, sr055["statement"])
    assert "compile an explicit versioned planning gate pack" in statement
    assert "block proposal handoff" in statement
    assert "proposed; semantic adoption remains subject" in " ".join(sr055.content.split())
