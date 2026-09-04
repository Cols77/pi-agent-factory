from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from coherence.planning.semantic import (
    REVIEW_STAGES,
    SemanticReviewError,
    SemanticReviewPacket,
    SemanticReviewReport,
    build_review_packet,
    parse_review_report,
    write_review_packet,
    write_review_report,
)

pytestmark = pytest.mark.unit


def test_packet_is_hash_bound_and_deterministically_ordered(tmp_path: Path) -> None:
    first = tmp_path / "z.txt"
    second = tmp_path / "a.txt"
    first.write_text("z", encoding="utf-8")
    second.write_text("a", encoding="utf-8")
    packet = build_review_packet(
        run_id="run-1", stage="spec_alignment", iteration=1,
        artifact_paths=[first, second], project_root=tmp_path,
        context={"intent": "goal", "spec": "spec.md"},
        sr_context_digest="a" * 64,
        model={"provider": "local", "model": "reviewer"},
        reviewer_role="PLANNING_ALIGNMENT", reviewer_session_id="child-1",
    )
    assert packet.schema == 1
    assert [a["path"] for a in packet.artifacts] == ["a.txt", "z.txt"]
    assert packet.artifacts[0]["sha256"] == hashlib.sha256(b"a").hexdigest()
    assert packet.stage in REVIEW_STAGES


def test_report_parser_is_strict_and_requires_findings_contract() -> None:
    packet_fields = {
        "artifacts": [], "context": {}, "sr_context_digest": "b" * 64,
        "model": {"provider": "p", "model": "m"}, "reviewer_role": "role",
        "reviewer_session_id": None,
    }
    payload = {
        "schema": 1, "run_id": "r", "stage": "spec_alignment", "iteration": 1,
        "packet_sha256": "a" * 64, "findings": [], "human_prompts": [],
        "notes": [], "verdict": "clean", **packet_fields,
    }
    report = parse_review_report(json.dumps(payload))
    assert report.verdict == "clean"
    with pytest.raises(SemanticReviewError):
        parse_review_report('{"schema":1,"schema":1}')


def test_packet_writer_rejects_traversal_and_report_never_is_consent(tmp_path: Path) -> None:
    with pytest.raises(SemanticReviewError):
        build_review_packet(
            run_id="../escape", stage="spec_alignment", iteration=1,
            artifact_paths=[], project_root=tmp_path, context={},
            sr_context_digest="a" * 64, model={"provider": "p", "model": "m"},
            reviewer_role="role", reviewer_session_id=None,
        )
    packet = build_review_packet(
        run_id="r", stage="plan_task_alignment", iteration=1,
        artifact_paths=[], project_root=tmp_path, context={},
        sr_context_digest="a" * 64, model={"provider": "p", "model": "m"},
        reviewer_role="role", reviewer_session_id=None,
    )
    path = write_review_packet(tmp_path, packet)
    assert path.name == "semantic-review-packet.json"
    assert "consent" not in packet.to_dict()


def test_packet_writer_revalidates_forged_identity(tmp_path: Path) -> None:
    forged = SemanticReviewPacket(
        1, "../escape", "spec_alignment", 1, (), {}, "a" * 64,
        {"provider": "p", "model": "m"}, "role", None,
    )
    with pytest.raises(SemanticReviewError):
        write_review_packet(tmp_path, forged)


def test_report_writer_revalidates_forged_identity(tmp_path: Path) -> None:
    forged = SemanticReviewReport(
        1, "../escape", "spec_alignment", 1, "a" * 64, (), {}, "b" * 64,
        {"provider": "p", "model": "m"}, "role", None, (), (), (), "clean",
    )
    with pytest.raises(SemanticReviewError):
        write_review_report(tmp_path, forged)


def test_report_preserves_the_full_hash_bound_packet_contract(tmp_path: Path) -> None:
    source = tmp_path / "spec.md"
    source.write_text("spec", encoding="utf-8")
    packet = build_review_packet(
        run_id="r", stage="spec_alignment", iteration=2, artifact_paths=[source],
        project_root=tmp_path, context={"intent": "goal", "spec": "spec.md"},
        sr_context_digest="a" * 64, model={"provider": "p", "model": "m"},
        reviewer_role="role", reviewer_session_id="session",
    )
    payload = {
        **packet.to_dict(), "packet_sha256": packet.sha256, "findings": [],
        "human_prompts": [], "notes": [], "verdict": "clean",
    }
    report = parse_review_report(json.dumps(payload), packet=packet)
    assert report.artifacts == packet.artifacts
    assert report.context == packet.context
    assert report.model == packet.model
    assert report.reviewer_session_id == "session"
