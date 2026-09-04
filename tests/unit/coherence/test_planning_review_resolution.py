from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from coherence.planning.gates import validate_sr_consent
from coherence.planning.run import build_escalation

pytestmark = pytest.mark.unit


def test_escalation_contains_exact_findings_prompt_and_next_loop_input() -> None:
    report = {
        "stage": "plan_task_alignment",
        "iteration": 2,
        "findings": [
            {"id": "F-2", "detail": "missing owner", "evidence": "plan.md:4", "disposition": "escalate_to_human"}
        ],
        "human_prompts": ["Which owner should this task use?"],
    }
    payload = build_escalation("run-7", report, next_loop_input={"answer": "required"})
    assert payload == {
        "schema": 1,
        "run_id": "run-7",
        "stage": "plan_task_alignment",
        "iteration": 2,
        "finding_ids": ["F-2"],
        "findings": [{"id": "F-2", "detail": "missing owner", "evidence": "plan.md:4"}],
        "prompts": ["Which owner should this task use?"],
        "next_loop_input": {"answer": "required"},
        "legal_actions": ["answer", "revise", "defer", "cancel"],
        "blocked": True,
    }


def test_sr_consent_requires_phrase_and_exact_hash_bound_candidate_set(tmp_path: Path) -> None:
    run_id = "run-7"
    candidates = ["SR-001", "SR-002"]
    artifacts = {"spec.md": hashlib.sha256(b"spec").hexdigest()}
    report_hash = hashlib.sha256(b"derivation").hexdigest()
    path = tmp_path / ".factory" / "planning" / run_id / "sr-consent.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({
        "schema": 2,
        "run_id": run_id,
        "decision": "approve",
        "reviewer": "human",
        "phrase": "I explicitly consent to adopt exactly these candidate SRs.",
        "candidate_srs": candidates,
        "derivation_report_sha256": report_hash,
        "artifact_hashes": artifacts,
    }), encoding="utf-8")
    assert validate_sr_consent(tmp_path, run_id, candidates, report_hash, artifacts)[0]
    path.write_text(path.read_text(encoding="utf-8").replace("SR-002", "SR-003"), encoding="utf-8")
    assert not validate_sr_consent(tmp_path, run_id, candidates, report_hash, artifacts)[0]


def test_sr_consent_does_not_accept_semantic_cleanliness_or_free_text_alone(tmp_path: Path) -> None:
    path = tmp_path / ".factory" / "planning" / "run-7" / "sr-consent.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"schema": 1, "verdict": "clean", "answer": "yes"}), encoding="utf-8")
    assert not validate_sr_consent(tmp_path, "run-7", ["SR-001"], "0" * 64, {"spec.md": "1" * 64})[0]
