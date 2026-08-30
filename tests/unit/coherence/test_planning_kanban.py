from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from coherence.planning.kanban import (
    PLANNING_STAGES,
    PlanningKanban,
    PlanningKanbanError,
    StageBlocked,
    WorkspacePolicyError,
)

pytestmark = pytest.mark.unit


class TestGateVerifier:
    def verify_gate(
        self, *, card: object, gate: dict[str, object]
    ) -> dict[str, object]:
        return dict(gate)


class ToggleGateVerifier(TestGateVerifier):
    def __init__(self) -> None:
        self.allow = True

    def verify_gate(
        self, *, card: object, gate: dict[str, object]
    ) -> dict[str, object] | None:
        return dict(gate) if self.allow else None


class TestHumanDecisionVerifier:
    def verify_human_decision(
        self, *, card: object, decision: dict[str, object], context: dict[str, object]
    ) -> dict[str, object]:
        return dict(decision)


class TestFreshReviewVerifier:
    def verify_fresh_review(
        self, *, card: object, review: dict[str, object], context: dict[str, object]
    ) -> dict[str, object]:
        return dict(review)


_RAW_MATERIALIZE = PlanningKanban.materialize


def trusted_materialize(root: Path, run_id: str, **kwargs: object):
    kwargs.setdefault("assignee", "worker-1")
    kwargs.setdefault("authorized_assignees", {kwargs["assignee"]})
    kwargs.setdefault("gate_verifier", TestGateVerifier())
    kwargs.setdefault("human_decision_verifier", TestHumanDecisionVerifier())
    kwargs.setdefault("fresh_review_verifier", TestFreshReviewVerifier())
    return _RAW_MATERIALIZE(root, run_id, **kwargs)


@pytest.fixture(autouse=True)
def trusted_state_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PI_AGENT_FACTORY_KANBAN_STATE_KEY", "k" * 64)


def coherence_gate(label: str = "planning-checkpoint") -> dict[str, object]:
    return {
        "gate": {
            "kind": "coherence",
            "name": label,
            "passed": True,
            "evidence": {"report_sha256": "a" * 64, "scope": label},
        }
    }


def resume_context() -> dict[str, object]:
    return {
        "inputs": {"spec_sha256": "b" * 64},
        "finding_scope": ["finding-1", "finding-2"],
    }


def resume_evidence(context: dict[str, object]) -> dict[str, object]:
    return {
        "human_decision": {
            "decision": "answer",
            "response": "Use the current approved boundary.",
            **context,
        },
        "fresh_review": {
            "kind": "coherence",
            "passed": True,
            "evidence": {"report_sha256": "c" * 64},
            **context,
        },
    }


def materialize_ready_capture(tmp_path: Path):
    run = trusted_materialize(tmp_path, "run-1", assignee="worker-1")
    root = run.cards[0]
    run.claim(root.id, worker="worker-1")
    run.complete(root.id, evidence=coherence_gate("root-graph"))
    return run


def state_path(tmp_path: Path, run_id: str = "run-1") -> Path:
    return tmp_path / ".factory" / "planning" / run_id / "kanban-run.json"


def test_materializes_root_and_exact_canonical_graph_and_is_idempotent(tmp_path: Path) -> None:
    first = trusted_materialize(tmp_path, "run-1", assignee="planner")
    second = trusted_materialize(tmp_path, "run-1", assignee="planner")

    assert first == second
    assert [card.stage for card in first.cards] == ["planning-run", *PLANNING_STAGES]
    assert first.cards[0].id == "run-1:planning-run:v1"
    assert first.cards[0].parents == ()
    assert first.cards[1].parents == (first.cards[0].id,)
    assert all(
        card.parents == (first.cards[index - 1].id,)
        for index, card in enumerate(first.cards[2:], start=2)
    )
    assert all(
        card.idempotency_key == f"feat17/run-1/{card.stage}/v1"
        for card in first.cards
    )
    payload = json.loads(state_path(tmp_path).read_text(encoding="utf-8"))
    assert payload["contract_sha256"] == first.contract_sha256
    assert len(payload["cards"]) == len(PLANNING_STAGES) + 1
    assert payload["edges"] == [
        [first.cards[index - 1].id, first.cards[index].id]
        for index in range(1, len(first.cards))
    ]


def test_dependency_gating_requires_completed_parent_and_valid_gate(tmp_path: Path) -> None:
    run = trusted_materialize(tmp_path, "run-1")
    root, capture = run.cards[:2]
    with pytest.raises(StageBlocked, match="parent"):
        run.claim(capture.id, worker="worker-1")

    run.claim(root.id, worker="worker-1")
    with pytest.raises(StageBlocked, match="gate"):
        run.complete(root.id, evidence={"gate": "intent/provenance"})
    assert run.card(root.id).status == "running"

    run.complete(root.id, evidence=coherence_gate("root"))
    claim = run.claim(capture.id, worker="worker-1")
    assert claim.attempt == 1


def test_claim_rejects_worker_not_in_card_assignee_allowlist(tmp_path: Path) -> None:
    run = trusted_materialize(tmp_path, "run-1", assignee="worker-1")

    with pytest.raises(StageBlocked, match="assignee|worker"):
        run.claim(run.cards[0].id, worker="spoofed-worker")


def test_materialize_rejects_an_assignee_outside_the_authorized_allowlist(tmp_path: Path) -> None:
    with pytest.raises(PlanningKanbanError, match="assignee|authorized|allowlist"):
        PlanningKanban.materialize(tmp_path, "run-1", assignee="untrusted-worker")


def test_fresh_unleased_instance_cannot_mutate_non_running_block_or_gate(
    tmp_path: Path,
) -> None:
    run = trusted_materialize(tmp_path / "block", "run-1")
    fresh = PlanningKanban.load(tmp_path / "block", "run-1")
    with pytest.raises(StageBlocked, match="coordinator|authority|instance"):
        fresh.block(run.cards[0].id, reason="unauthorized")

    run = materialize_ready_capture(tmp_path / "gate")
    fresh = PlanningKanban.load(tmp_path / "gate", "run-1")
    with pytest.raises(StageBlocked, match="coordinator|authority|instance"):
        fresh.mark_gate(run.cards[0].id, passed=False, detail="unauthorized")


def test_expired_owner_cannot_heartbeat_complete_or_block(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import coherence.planning.kanban as kanban_module

    for operation in ("heartbeat", "complete", "block"):
        run = materialize_ready_capture(tmp_path / operation)
        capture = run.cards[1]
        run.claim(capture.id, worker="worker-1")
        with monkeypatch.context() as patcher:
            patcher.setattr(kanban_module, "_now_ms", lambda: 10**15)

            with pytest.raises(StageBlocked, match="expired|lease|ownership"):
                if operation == "heartbeat":
                    run.heartbeat(capture.id)
                elif operation == "complete":
                    run.complete(capture.id, evidence=coherence_gate("expired"))
                else:
                    run.block(capture.id, reason="expired")


def test_structural_gate_evidence_without_authoritative_verification_is_rejected(
    tmp_path: Path,
) -> None:
    run = _RAW_MATERIALIZE(
        tmp_path,
        "run-1",
        assignee="worker-1",
        authorized_assignees={"worker-1"},
    )
    root = run.cards[0]
    run.claim(root.id, worker="worker-1")
    forged = coherence_gate("forged-structural-gate")
    with pytest.raises(StageBlocked, match="authoritative|verified|gate"):
        run.complete(root.id, evidence=forged)

    assert run.card(root.id).status == "running"
    assert run.card(run.cards[1].id).status == "pending"


def test_mark_gate_requires_authoritative_verification_for_a_passing_gate(
    tmp_path: Path,
) -> None:
    verifier = ToggleGateVerifier()
    run = _RAW_MATERIALIZE(
        tmp_path,
        "run-1",
        assignee="worker-1",
        authorized_assignees={"worker-1"},
        gate_verifier=verifier,
    )
    root = run.cards[0]
    run.claim(root.id, worker="worker-1")
    run.complete(root.id, evidence=coherence_gate("root"))
    verifier.allow = False

    with pytest.raises(StageBlocked, match="authoritative|verified|gate"):
        run.mark_gate(root.id, passed=True, detail=run.card(root.id).output["gate"])


def test_resume_rejects_self_asserted_human_decision_and_fresh_review(
    tmp_path: Path,
) -> None:
    run = _RAW_MATERIALIZE(
        tmp_path,
        "run-1",
        assignee="worker-1",
        authorized_assignees={"worker-1"},
        gate_verifier=TestGateVerifier()
    )
    root, capture = run.cards[:2]
    run.claim(root.id, worker="worker-1")
    run.complete(root.id, evidence=coherence_gate("root"))
    context = resume_context()
    run.block(capture.id, reason="needs answer", needs_input=True, evidence=context)

    with pytest.raises(StageBlocked, match="authoritative|verified|resume"):
        run.resume(capture.id, evidence=resume_evidence(context))

    assert run.card(capture.id).status == "needs_input"


def test_gate_revocation_recursively_blocks_running_and_completed_descendants(
    tmp_path: Path,
) -> None:
    run = materialize_ready_capture(tmp_path)
    root, capture, spec_alignment = run.cards[:3]
    run.claim(capture.id, worker="worker-1")
    run.complete(capture.id, evidence=coherence_gate("capture"))
    run.claim(spec_alignment.id, worker="worker-1")

    revoked = run.mark_gate(root.id, passed=False, detail="root evidence revoked")

    assert revoked.status == "blocked"
    assert run.card(capture.id).status == "blocked"
    assert run.card(spec_alignment.id).status == "blocked"
    with pytest.raises(StageBlocked, match="blocked|parent|gate|ownership|capability|claimed"):
        run.complete(spec_alignment.id, evidence=coherence_gate("late"))


def test_gate_revocation_releases_a_running_writer_descendant(tmp_path: Path) -> None:
    run = materialize_ready_capture(tmp_path)
    root, capture = run.cards[:2]
    run.claim(capture.id, worker="worker-1")

    revoked = run.mark_gate(root.id, passed=False, detail="root evidence revoked")

    assert revoked.status == "blocked"
    assert run.card(capture.id).status == "blocked"
    assert run.card(capture.id).lease_token is None
    assert not (tmp_path / ".factory" / "planning" / ".planning-writer.lock").exists()


def test_fresh_unleased_instance_cannot_resume_a_needs_input_card(tmp_path: Path) -> None:
    run = _RAW_MATERIALIZE(
        tmp_path,
        "run-1",
        assignee="worker-1",
        authorized_assignees={"worker-1"},
        gate_verifier=TestGateVerifier(),
        human_decision_verifier=TestHumanDecisionVerifier(),
        fresh_review_verifier=TestFreshReviewVerifier(),
    )
    root, capture = run.cards[:2]
    run.claim(root.id, worker="worker-1")
    run.complete(root.id, evidence=coherence_gate("root"))
    context = resume_context()
    run.block(capture.id, reason="needs answer", needs_input=True, evidence=context)
    fresh = PlanningKanban.load(
        tmp_path,
        "run-1",
        human_decision_verifier=TestHumanDecisionVerifier(),
        fresh_review_verifier=TestFreshReviewVerifier(),
    )

    with pytest.raises(StageBlocked, match="coordinator|authority|instance"):
        fresh.resume(capture.id, evidence=resume_evidence(context))


def test_invalid_gate_evidence_is_rejected_and_never_releases_child(tmp_path: Path) -> None:
    run = trusted_materialize(tmp_path, "run-1")
    root, capture = run.cards[:2]
    run.claim(root.id, worker="worker-1")

    for evidence in ({}, {"gate": ""}, {"gate": {}}, {"gate": {"passed": True}}):
        with pytest.raises(StageBlocked, match="gate"):
            run.complete(root.id, evidence=evidence)

    assert run.card(root.id).status == "running"
    assert run.card(capture.id).status == "pending"


def test_lock_record_rejects_duplicate_and_unknown_fields(tmp_path: Path) -> None:
    import coherence.planning.kanban as kanban_module

    lock_path = tmp_path / "lock.json"
    valid_prefix = '{"schema":1,"pid":1,"run_id":"run-1","card_id":"card-1","token":"tok"'
    lock_path.write_text(valid_prefix + ',"token":"forged"}', encoding="utf-8")
    with pytest.raises(WorkspacePolicyError, match="malformed"):
        kanban_module._read_lock_record(lock_path)

    lock_path.write_text(valid_prefix + ',"extra":"shadow"}', encoding="utf-8")
    with pytest.raises(WorkspacePolicyError, match="malformed"):
        kanban_module._read_lock_record(lock_path)


def test_stale_lock_recovery_preserves_a_replacement_lock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import coherence.planning.kanban as kanban_module

    lock_path = tmp_path / "lock.json"
    original = '{"schema":1,"pid":999999,"run_id":"run-1","card_id":"card-1","token":"old"}'
    replacement = '{"schema":1,"pid":999998,"run_id":"run-1","card_id":"card-1","token":"new"}'
    lock_path.write_text(original, encoding="utf-8")

    def replace_before_liveness_check(pid: int) -> bool:
        lock_path.write_text(replacement, encoding="utf-8")
        return False

    monkeypatch.setattr(kanban_module, "_pid_is_alive", replace_before_liveness_check)
    with pytest.raises(WorkspacePolicyError, match="changed"):
        kanban_module._try_recover_stale_lock(lock_path)
    assert lock_path.read_text(encoding="utf-8") == replacement


def test_human_block_pause_and_resume_require_current_decision_and_fresh_review(
    tmp_path: Path,
) -> None:
    run = materialize_ready_capture(tmp_path)
    capture = run.cards[1]
    context = resume_context()
    run.block(capture.id, reason="needs explicit human answer", needs_input=True, evidence=context)
    assert run.card(capture.id).status == "needs_input"
    with pytest.raises(StageBlocked, match="needs_input"):
        run.claim(capture.id, worker="worker-1")
    with pytest.raises(StageBlocked, match="evidence"):
        run.resume(capture.id)
    with pytest.raises(StageBlocked, match="evidence"):
        run.resume(capture.id, evidence={"human_response": "yes"})
    with pytest.raises(StageBlocked, match="current"):
        run.resume(capture.id, evidence=resume_evidence({**context, "finding_scope": ["old"]}))

    resumed = run.resume(capture.id, evidence=resume_evidence(context))
    assert resumed.status == "ready"
    assert resumed.status != "complete"
    assert run.card(capture.id).status == "ready"


def test_reclaim_reuses_card_preserves_attempt_evidence_and_cleans_lock(tmp_path: Path) -> None:
    run = materialize_ready_capture(tmp_path)
    capture = run.cards[1]
    run.claim(capture.id, worker="worker-1")
    assert (tmp_path / ".factory" / "planning" / ".planning-writer.lock").exists()
    reclaimed = run.reclaim(capture.id, reason="worker interrupted")
    assert reclaimed.status == "ready"
    assert reclaimed.attempt == 1
    assert reclaimed.attempts[-1]["reason"] == "worker interrupted"
    assert not (tmp_path / ".factory" / "planning" / ".planning-writer.lock").exists()
    assert run.claim(capture.id, worker="worker-1").attempt == 2


def test_heartbeat_preserves_the_current_attempt_evidence(tmp_path: Path) -> None:
    run = materialize_ready_capture(tmp_path)
    capture = run.cards[1]
    run.claim(capture.id, worker="worker-1")

    heartbeat = run.heartbeat(capture.id)
    assert heartbeat.attempts[-1] == {"attempt": 1, "event": "heartbeat"}
    assert PlanningKanban.load(tmp_path, "run-1").card(capture.id).attempts[-1] == {
        "attempt": 1,
        "event": "heartbeat",
    }
    run.reclaim(capture.id, reason="cleanup")


def test_fresh_instance_recovers_dead_owner_same_attempt_with_higher_fence(
    tmp_path: Path,
) -> None:
    run = materialize_ready_capture(tmp_path)
    capture = run.cards[1]
    owner_script = (
        "import sys; "
        "from pathlib import Path; "
        "from coherence.planning.kanban import PlanningKanban; "
        "r = PlanningKanban.load(Path(sys.argv[1]), 'run-1'); "
        "r.claim(r.cards[1].id, worker='worker-1')"
    )
    subprocess.run(
        [sys.executable, "-c", owner_script, str(tmp_path)],
        check=True,
        env=os.environ.copy(),
    )

    stale = PlanningKanban.load(tmp_path, "run-1")
    before = stale.card(capture.id)
    assert before.status == "running"
    recovered = PlanningKanban.load(tmp_path, "run-1").recover(
        capture.id,
        reason="owner process exited",
        revision=before.revision,
        attempt=before.attempt,
    )

    assert recovered.status == "ready"
    assert recovered.revision == before.revision
    assert recovered.attempt == before.attempt == 1
    assert recovered.fencing_token > before.fencing_token
    assert recovered.attempts[-1]["event"] == "crash_reclaim"
    assert not (tmp_path / ".factory" / "planning" / ".planning-writer.lock").exists()
    with pytest.raises(StageBlocked, match="ownership|capability"):
        stale.complete(capture.id, evidence=coherence_gate("stale"))


def test_writer_paths_are_exact_and_shared_writers_are_serialized(tmp_path: Path) -> None:
    run = trusted_materialize(tmp_path, "run-1", workspace_mode="dir")
    capture = run.card(run.cards[1].id)
    assert ".intent" in capture.allowed_paths
    assert "docs/superpowers/plans" not in capture.allowed_paths
    run.claim(run.cards[0].id, worker="worker-1")
    run.complete(run.cards[0].id, evidence=coherence_gate("root"))
    run.claim(capture.id, worker="worker-1")

    other = trusted_materialize(tmp_path, "run-2", workspace_mode="dir")
    other_root = other.cards[0]
    other.claim(other_root.id, worker="worker-1")
    other.complete(other_root.id, evidence=coherence_gate("root-2"))
    with pytest.raises(WorkspacePolicyError):
        other.claim(other.cards[1].id, worker="worker-1")


def test_stale_in_memory_claim_reconciles_before_mutating(tmp_path: Path) -> None:
    stale = trusted_materialize(tmp_path, "run-1")
    current = PlanningKanban.load(tmp_path, "run-1")
    root = stale.cards[0]
    current.claim(root.id, worker="worker-1")

    with pytest.raises(StageBlocked, match="stale|running"):
        stale.claim(root.id, worker="worker-1")
    assert PlanningKanban.load(tmp_path, "run-1").card(root.id).attempt == 1


def test_stale_in_memory_completion_cannot_fence_a_new_attempt(tmp_path: Path) -> None:
    run = trusted_materialize(tmp_path, "run-1")
    root = run.cards[0]
    run.claim(root.id, worker="worker-1")
    stale = PlanningKanban.load(tmp_path, "run-1")
    run.reclaim(root.id, reason="worker interrupted")
    run.claim(root.id, worker="worker-1")

    with pytest.raises(StageBlocked, match="stale|ownership"):
        stale.complete(root.id, evidence=coherence_gate("stale"))
    assert PlanningKanban.load(tmp_path, "run-1").card(root.id).status == "running"


def test_persisted_writer_policy_cannot_be_bypassed_by_stale_card_fields(tmp_path: Path) -> None:
    materialize_ready_capture(tmp_path)
    stale = PlanningKanban.load(tmp_path, "run-1")
    stale.cards[1].workspace_mode = "worktree"

    claimed = stale.claim(stale.cards[1].id, worker="worker-1")
    assert claimed.status == "running"
    assert (tmp_path / ".factory" / "planning" / ".planning-writer.lock").exists()
    stale.reclaim(stale.cards[1].id, reason="cleanup")


def test_load_rejects_tampered_contract_and_exact_graph_variants(tmp_path: Path) -> None:
    run = trusted_materialize(tmp_path, "run-1")
    path = state_path(tmp_path)
    original = json.loads(path.read_text(encoding="utf-8"))

    for mutate in (
        lambda payload: payload["cards"].__setitem__(0, {**payload["cards"][0], "stage": "capture"}),
        lambda payload: payload["cards"].__setitem__(1, {**payload["cards"][1], "parents": []}),
        lambda payload: payload["cards"].__setitem__(1, {**payload["cards"][1], "parents": ["orphan"]}),
        lambda payload: payload["cards"].append(dict(payload["cards"][0])),
        lambda payload: payload.__setitem__("edges", []),
        lambda payload: payload.__setitem__("contract_sha256", "0" * 64),
    ):
        payload = json.loads(json.dumps(original))
        mutate(payload)
        path.write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(PlanningKanbanError):
            PlanningKanban.load(tmp_path, "run-1")

    path.write_text(json.dumps(original), encoding="utf-8")
    assert PlanningKanban.load(tmp_path, "run-1").contract_sha256 == run.contract_sha256


def test_load_rejects_invalid_status_and_ready_child_without_gate(tmp_path: Path) -> None:
    trusted_materialize(tmp_path, "run-1")
    path = state_path(tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["cards"][0]["status"] = "complete"
    payload["cards"][0]["gate_passed"] = False
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(PlanningKanbanError):
        PlanningKanban.load(tmp_path, "run-1")

    trusted_materialize(tmp_path, "run-2")
    path = state_path(tmp_path, "run-2")
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["cards"][1]["status"] = "ready"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(PlanningKanbanError):
        PlanningKanban.load(tmp_path, "run-2")


def test_load_rejects_tampered_gate_detail_and_missing_resume_context(tmp_path: Path) -> None:
    run = trusted_materialize(tmp_path, "run-1")
    root = run.cards[0]
    run.claim(root.id, worker="worker-1")
    run.complete(root.id, evidence=coherence_gate("root"))
    path = state_path(tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["cards"][0]["gate_detail"] = "tampered"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(PlanningKanbanError):
        PlanningKanban.load(tmp_path, "run-1")

    run = trusted_materialize(tmp_path, "run-2")
    root = run.cards[0]
    run.claim(root.id, worker="worker-1")
    run.complete(root.id, evidence=coherence_gate("root"))
    context = resume_context()
    run.block(run.cards[1].id, reason="needs answer", needs_input=True, evidence=context)
    path = state_path(tmp_path, "run-2")
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["cards"][1]["required_context"] = {}
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(PlanningKanbanError):
        PlanningKanban.load(tmp_path, "run-2")


def test_invalidating_a_running_writer_gate_releases_its_lease(tmp_path: Path) -> None:
    run = materialize_ready_capture(tmp_path)
    capture = run.cards[1]
    run.claim(capture.id, worker="worker-1")
    blocked = run.mark_gate(capture.id, passed=False, detail="fresh review failed")
    assert blocked.status == "blocked"
    assert blocked.lease_token is None
    assert not (tmp_path / ".factory" / "planning" / ".planning-writer.lock").exists()


def test_running_writer_handle_cannot_be_reused_for_another_card(tmp_path: Path) -> None:
    run = materialize_ready_capture(tmp_path)
    capture = run.cards[1]
    run.claim(capture.id, worker="worker-1")

    with pytest.raises(WorkspacePolicyError):
        run.mark_gate(run.cards[2].id, passed=False, detail="not this writer")
    assert run.card(run.cards[2].id).status == "pending"


def test_dead_owner_lock_is_recovered_exclusively(tmp_path: Path) -> None:
    run = materialize_ready_capture(tmp_path)
    lock_path = tmp_path / ".factory" / "planning" / ".planning-writer.lock"
    lock_path.write_text(
        json.dumps(
            {"schema": 1, "pid": 99999999, "run_id": "old", "card_id": "old", "token": "stale"}
        ),
        encoding="utf-8",
    )

    claimed = run.claim(run.cards[1].id, worker="worker-1")
    assert claimed.status == "running"
    run.reclaim(claimed.id, reason="recovered interruption")
    assert not lock_path.exists()


def test_materialization_refuses_an_active_state_lock(tmp_path: Path) -> None:
    run_path = tmp_path / ".factory" / "planning" / "run-1"
    run_path.mkdir(parents=True)
    (run_path / ".kanban-state.lock").write_text(
        json.dumps(
            {"schema": 1, "pid": os.getpid(), "run_id": "run-1", "card_id": "root", "token": "live"}
        ),
        encoding="utf-8",
    )

    with pytest.raises(WorkspacePolicyError):
        trusted_materialize(tmp_path, "run-1")


def test_unsafe_run_ids_are_rejected_before_path_creation(tmp_path: Path) -> None:
    unsafe_ids = (
        "",
        ".",
        "..",
        " ",
        "run\n1",
        "run\t1",
        "a/b",
        r"a\b",
        "CON",
        "NUL",
        "COM1",
        "run.",
        "run ",
        "run:1",
    )
    for run_id in unsafe_ids:
        with pytest.raises(PlanningKanbanError):
            trusted_materialize(tmp_path, run_id)
    assert not (tmp_path / ".factory" / "planning").exists()


def test_atomic_lock_refuses_live_owner_and_malformed_lock(tmp_path: Path) -> None:
    run = materialize_ready_capture(tmp_path)
    lock_path = tmp_path / ".factory" / "planning" / ".planning-writer.lock"
    lock_path.write_text(
        json.dumps({"pid": os.getpid(), "run_id": "other", "card_id": "other", "token": "live"}),
        encoding="utf-8",
    )
    with pytest.raises(WorkspacePolicyError):
        run.claim(run.cards[1].id, worker="worker-1")
    lock_path.write_text("not-json", encoding="utf-8")
    with pytest.raises(WorkspacePolicyError):
        run.claim(run.cards[1].id, worker="worker-1")


def test_loaded_instance_cannot_replay_a_persisted_lease_capability(tmp_path: Path) -> None:
    run = materialize_ready_capture(tmp_path)
    capture = run.cards[1]
    run.claim(capture.id, worker="worker-1")
    replay = PlanningKanban.load(tmp_path, "run-1")
    replay.card(capture.id).lease_token = run.card(capture.id).lease_token

    with pytest.raises(StageBlocked, match="ownership|capability"):
        replay.heartbeat(capture.id)
    with pytest.raises(StageBlocked, match="ownership|capability"):
        replay.complete(capture.id, evidence=coherence_gate("replay"))
    with pytest.raises(StageBlocked, match="ownership|capability"):
        replay.block(capture.id, reason="replay")
    with pytest.raises(StageBlocked, match="ownership|capability"):
        replay.reclaim(capture.id, reason="replay")
    current = PlanningKanban.load(tmp_path, "run-1").card(capture.id)
    assert current.status == "running"
    assert current.attempts[-1] == {"attempt": 1, "worker": "worker-1", "event": "claimed"}


def test_stale_instance_cannot_mutate_reclaimed_card_after_a_new_attempt(tmp_path: Path) -> None:
    run = trusted_materialize(tmp_path, "run-1")
    root = run.cards[0]
    run.claim(root.id, worker="worker-1")
    stale = PlanningKanban.load(tmp_path, "run-1")
    run.reclaim(root.id, reason="worker interrupted")
    run.claim(root.id, worker="worker-1")
    stale.card(root.id).lease_token = run.card(root.id).lease_token

    with pytest.raises(StageBlocked, match="ownership|capability"):
        stale.heartbeat(root.id)
    with pytest.raises(StageBlocked, match="ownership|capability"):
        stale.complete(root.id, evidence=coherence_gate("stale"))
    with pytest.raises(StageBlocked, match="ownership|capability"):
        stale.block(root.id, reason="stale")
    with pytest.raises(StageBlocked, match="ownership|capability"):
        stale.reclaim(root.id, reason="stale")
    current = PlanningKanban.load(tmp_path, "run-1").card(root.id)
    assert current.status == "running"
    assert current.attempt == 2
    assert current.attempts[-1] == {"attempt": 2, "worker": "worker-1", "event": "claimed"}


def test_load_rejects_mutable_state_forgery_with_an_unchanged_contract(tmp_path: Path) -> None:
    run = trusted_materialize(tmp_path, "run-1")
    path = state_path(tmp_path)
    original = json.loads(path.read_text(encoding="utf-8"))
    forged_gate = coherence_gate("forged")["gate"]
    mutations = (
        lambda payload: payload["cards"][0].update(
            {
                "status": "complete",
                "attempt": 1,
                "attempts": [{"attempt": 1, "event": "completed", "evidence": coherence_gate("forged")}],
                "gate_passed": True,
                "gate_detail": json.dumps(forged_gate, sort_keys=True, separators=(",", ":")),
                "output": coherence_gate("forged"),
            }
        ),
        lambda payload: payload["cards"][1].update({"status": "ready"}),
        lambda payload: payload["cards"][0].update({"attempt": 99}),
        lambda payload: payload["cards"][0].update({"output": {"forged": True}}),
    )

    for mutate in mutations:
        payload = json.loads(json.dumps(original))
        mutate(payload)
        assert payload["contract_sha256"] == run.contract_sha256
        path.write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(PlanningKanbanError, match="state integrity|authentication|hash|attempt"):
            PlanningKanban.load(tmp_path, "run-1")

    path.write_text(json.dumps(original), encoding="utf-8")


def test_load_rejects_replay_of_a_valid_authenticated_old_snapshot(tmp_path: Path) -> None:
    run = trusted_materialize(tmp_path, "run-1")
    path = state_path(tmp_path)
    old_snapshot = path.read_text(encoding="utf-8")
    run.claim(run.cards[0].id, worker="worker-1")

    path.write_text(old_snapshot, encoding="utf-8")
    with pytest.raises(PlanningKanbanError, match="replay|generation|high.?water"):
        PlanningKanban.load(tmp_path, "run-1")


def test_load_rejects_a_state_hash_mismatch(tmp_path: Path) -> None:
    trusted_materialize(tmp_path, "run-1")
    path = state_path(tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["state_hmac_sha256"] = "0" * 64
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(PlanningKanbanError, match="state authentication"):
        PlanningKanban.load(tmp_path, "run-1")


def test_load_rejects_mutable_forgery_even_when_an_attacker_recomputes_old_hash(
    tmp_path: Path,
) -> None:
    run = trusted_materialize(tmp_path, "run-1")
    path = state_path(tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["cards"][0]["output"] = {"forged": True}
    unsigned = {key: value for key, value in payload.items() if key != "state_hmac_sha256"}
    payload["state_hmac_sha256"] = hashlib.sha256(
        json.dumps(unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    path.write_text(json.dumps(payload), encoding="utf-8")

    assert "state_sha256" not in payload
    assert "k" * 64 not in path.read_text(encoding="utf-8")
    assert run.card(run.cards[0].id).output == {}
    with pytest.raises(PlanningKanbanError, match="authentic|integrity|hash"):
        PlanningKanban.load(tmp_path, "run-1")


def test_load_rejects_unknown_state_and_card_fields(tmp_path: Path) -> None:
    trusted_materialize(tmp_path, "run-1")
    path = state_path(tmp_path)
    original = json.loads(path.read_text(encoding="utf-8"))

    for mutate in (
        lambda payload: payload.__setitem__("unexpected", True),
        lambda payload: payload["cards"][0].__setitem__("unexpected", True),
    ):
        payload = json.loads(json.dumps(original))
        mutate(payload)
        path.write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(PlanningKanbanError, match="schema|field|unknown"):
            PlanningKanban.load(tmp_path, "run-1")


def test_load_rejects_missing_required_card_operational_fields(tmp_path: Path) -> None:
    trusted_materialize(tmp_path, "run-1")
    path = state_path(tmp_path)
    original = json.loads(path.read_text(encoding="utf-8"))

    for field in ("status", "attempt", "attempts", "gate_passed", "output", "required_context"):
        payload = json.loads(json.dumps(original))
        del payload["cards"][0][field]
        path.write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(PlanningKanbanError, match="missing|schema|field"):
            PlanningKanban.load(tmp_path, "run-1")


def test_stage_card_rejects_malformed_attempt_events_and_status_mismatch(tmp_path: Path) -> None:
    run = trusted_materialize(tmp_path, "run-1")
    card = run.cards[0]
    payload = card.to_dict()

    payload["attempts"] = [
        {"attempt": 1, "event": "claimed", "worker": "planning-worker", "unexpected": True}
    ]
    with pytest.raises(PlanningKanbanError, match="attempt|event|schema"):
        from coherence.planning.kanban import StageCard

        StageCard.from_dict(payload)

    payload = card.to_dict()
    payload.update(
        {
            "status": "running",
            "attempt": 1,
            "attempts": [{"attempt": 1, "event": "completed", "evidence": coherence_gate("x")}],
            "lease_token": "lease",
            "lease_owner_pid": os.getpid(),
            "lease_started_at": 1,
            "lease_expires_at": 2,
            "fencing_token": 1,
        }
    )
    with pytest.raises(PlanningKanbanError, match="attempt|status|running"):
        StageCard.from_dict(payload)


def test_load_fails_closed_when_trusted_state_key_is_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trusted_materialize(tmp_path, "run-1")
    monkeypatch.delenv("PI_AGENT_FACTORY_KANBAN_STATE_KEY")

    with pytest.raises(PlanningKanbanError, match="authenticated kanban state"):
        PlanningKanban.load(tmp_path, "run-1")
