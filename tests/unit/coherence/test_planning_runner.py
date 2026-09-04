from __future__ import annotations

import json
import hashlib
import sqlite3
import threading
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest

import coherence.planning.runner as runner_module
from coherence.planning.runner import (
    AgentInvocation,
    GateRecord,
    PlanningRunner,
    PlanningStage,
    RunnerBlocked,
    RunnerError,
)
pytestmark = pytest.mark.unit


def _input(root: Path, text: str = "intent") -> Path:
    path = root / "input.json"
    path.write_text(text, encoding="utf-8")
    return path


def _parent_output(
    runner: PlanningRunner, invocation: AgentInvocation, content: bytes = b"parent artifact"
) -> Path:
    path = runner.project_root / invocation.output_path
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_bytes(content)
    return path


def _complete(runner: PlanningRunner, stage: PlanningStage, input_path: Path) -> None:
    invocation = runner.begin(
        stage,
        role=f"{stage.value}-agent",
        input_paths=(input_path,),
        output_path=f".intent/{stage.value}.json",
    )
    runner.record_result(invocation, {"ok": True, "payload": {"stage": stage.value}})
    _trusted_gate(runner, invocation)
    runner.advance(invocation)


def test_parent_runner_advances_only_through_the_closed_stage_order(tmp_path: Path) -> None:
    input_path = _input(tmp_path)
    runner = PlanningRunner(tmp_path, "run-1")

    for stage in PlanningStage:
        _complete(runner, stage, input_path)

    state = runner.status()
    assert state.current_stage is None
    assert state.blocked is False
    assert state.completed_stages == tuple(stage.value for stage in PlanningStage)
    events = (tmp_path / ".factory" / "planning" / "run-1" / "workflow-events.jsonl").read_text(
        encoding="utf-8"
    ).splitlines()
    assert [json.loads(line)["sequence"] for line in events] == list(range(1, len(events) + 1))


def test_parent_selected_target_cannot_be_replaced_by_worker_result(tmp_path: Path) -> None:
    input_path = _input(tmp_path)
    runner = PlanningRunner(tmp_path, "run-1")
    invocation = runner.begin(
        PlanningStage.CAPTURE,
        role="intent-capture",
        input_paths=(input_path,),
        output_path=".intent/intent.json",
    )

    with pytest.raises(RunnerError, match="output target|worker-selected"):
        runner.record_result(
            invocation,
            {"ok": True, "payload": {"output_path": "outside/forged.json"}},
        )

    assert not list((tmp_path / ".factory" / "planning" / "run-1" / "stages").rglob("result.json"))


def test_stale_input_blocks_without_advancing_or_replacing_invocation(tmp_path: Path) -> None:
    input_path = _input(tmp_path)
    runner = PlanningRunner(tmp_path, "run-1")
    invocation = runner.begin(
        PlanningStage.CAPTURE,
        role="intent-capture",
        input_paths=(input_path,),
        output_path=".intent/intent.json",
    )
    input_path.write_text("changed", encoding="utf-8")

    with pytest.raises(RunnerBlocked, match="stale"):
        runner.record_result(invocation, {"ok": True, "payload": {"captured": True}})

    state = runner.status()
    assert state.blocked is True
    assert state.current_stage == PlanningStage.CAPTURE.value
    assert state.reason == "stale_input"


def test_failed_gate_blocks_and_retry_preserves_the_failed_attempt(tmp_path: Path) -> None:
    input_path = _input(tmp_path)
    runner = PlanningRunner(tmp_path, "run-1")
    first = runner.begin(
        PlanningStage.CAPTURE,
        role="intent-capture",
        input_paths=(input_path,),
        output_path=".intent/intent.json",
    )
    runner.record_result(first, {"ok": True, "payload": {"captured": True}})
    _trusted_gate(runner, first, passed=False, detail="invalid evidence")

    with pytest.raises(RunnerBlocked, match="gate"):
        runner.advance(first)

    second = runner.begin(
        PlanningStage.CAPTURE,
        role="intent-capture",
        input_paths=(input_path,),
        output_path=".intent/intent.json",
    )
    assert second.attempt == 2
    assert (tmp_path / ".factory" / "planning" / "run-1" / "stages" / "capture" / "r1" / "a1" / "gate.json").is_file()
    assert not (tmp_path / ".factory" / "planning" / "run-1" / "stages" / "capture" / "r1" / "a1" / "result.json").read_text(encoding="utf-8").endswith("{}\n")


def test_invalid_transition_is_rejected_before_any_record_is_written(tmp_path: Path) -> None:
    input_path = _input(tmp_path)
    runner = PlanningRunner(tmp_path, "run-1")

    with pytest.raises(RunnerError, match="expected stage"):
        runner.begin(
            PlanningStage.SPEC_ALIGNMENT,
            role="spec-alignment-reviewer",
            input_paths=(input_path,),
            output_path="docs/spec.md",
        )

    assert not (tmp_path / ".factory" / "planning" / "run-1" / "workflow-events.jsonl").exists()


def test_begin_fences_an_unfinished_attempt(tmp_path: Path) -> None:
    input_path = _input(tmp_path)
    runner = PlanningRunner(tmp_path, "run-1")
    runner.begin(
        PlanningStage.CAPTURE,
        role="intent-capture",
        input_paths=(input_path,),
        output_path=".intent/intent.json",
    )

    with pytest.raises(RunnerError, match="unfinished|blocked|attempt"):
        runner.begin(
            PlanningStage.CAPTURE,
            role="intent-capture",
            input_paths=(input_path,),
            output_path=".intent/intent.json",
        )


def test_retries_follow_the_latest_input_revision_only(tmp_path: Path) -> None:
    input_path = _input(tmp_path)
    runner = PlanningRunner(tmp_path, "run-1")

    first = runner.begin(
        PlanningStage.CAPTURE,
        role="intent-capture",
        input_paths=(input_path,),
        output_path=".intent/intent.json",
    )
    with pytest.raises(RunnerBlocked):
        runner.record_result(first, {"ok": False, "payload": {}, "error": "retry"})
    second = runner.begin(
        PlanningStage.CAPTURE,
        role="intent-capture",
        input_paths=(input_path,),
        output_path=".intent/intent.json",
    )
    assert (second.revision, second.attempt) == (1, 2)
    with pytest.raises(RunnerBlocked):
        runner.record_result(second, {"ok": False, "payload": {}, "error": "retry"})

    input_path.write_text("changed", encoding="utf-8")
    third = runner.begin(
        PlanningStage.CAPTURE,
        role="intent-capture",
        input_paths=(input_path,),
        output_path=".intent/intent.json",
    )
    assert (third.revision, third.attempt) == (2, 1)
    with pytest.raises(RunnerBlocked):
        runner.record_result(third, {"ok": False, "payload": {}, "error": "retry"})
    fourth = runner.begin(
        PlanningStage.CAPTURE,
        role="intent-capture",
        input_paths=(input_path,),
        output_path=".intent/intent.json",
    )
    assert (fourth.revision, fourth.attempt) == (2, 2)


def test_status_rejects_a_forged_semantically_impossible_advance(tmp_path: Path) -> None:
    input_path = _input(tmp_path)
    runner = PlanningRunner(tmp_path, "run-1")
    runner.begin(
        PlanningStage.CAPTURE,
        role="intent-capture",
        input_paths=(input_path,),
        output_path=".intent/intent.json",
    )
    events_path = tmp_path / ".factory" / "planning" / "run-1" / "workflow-events.jsonl"
    with events_path.open("a", encoding="utf-8") as stream:
        stream.write(
            json.dumps(
                {
                    "schema": 1,
                    "action": "advance",
                    "run_id": "run-1",
                    "stage": "capture",
                    "revision": 1,
                    "attempt": 1,
                    "next_stage": "provisional_spec",
                    "sequence": 2,
                }
            )
            + "\n"
        )

    with pytest.raises(RunnerError, match="journal|advance|result|gate"):
        runner.status()


def test_advance_rejects_minimal_forged_result_and_gate_files(tmp_path: Path) -> None:
    input_path = _input(tmp_path)
    runner = PlanningRunner(tmp_path, "run-1")
    invocation = runner.begin(
        PlanningStage.CAPTURE,
        role="intent-capture",
        input_paths=(input_path,),
        output_path=".intent/intent.json",
    )
    record_dir = tmp_path / ".factory" / "planning" / "run-1" / "stages" / "capture" / "r1" / "a1"
    record_dir.mkdir(parents=True, exist_ok=True)
    (record_dir / "result.json").write_text('{"ok":true}\n', encoding="utf-8")
    (record_dir / "gate.json").write_text('{"status":"pass"}\n', encoding="utf-8")

    with pytest.raises(RunnerBlocked, match="evidence|result|gate"):
        runner.advance(invocation)

    assert runner.status().blocked is True


def test_record_gate_rejects_a_result_without_a_validated_binding(tmp_path: Path) -> None:
    input_path = _input(tmp_path)
    runner = PlanningRunner(tmp_path, "run-1")
    invocation = runner.begin(
        PlanningStage.CAPTURE,
        role="intent-capture",
        input_paths=(input_path,),
        output_path=".intent/intent.json",
    )
    record_dir = tmp_path / ".factory" / "planning" / "run-1" / "stages" / "capture" / "r1" / "a1"
    record_dir.mkdir(parents=True, exist_ok=True)
    (record_dir / "result.json").write_text('{"ok":true}\n', encoding="utf-8")

    with pytest.raises(RunnerBlocked, match="result|evidence"):
        _trusted_gate(runner, invocation, detail="forged")

    assert not (record_dir / "gate.json").exists()


def test_advance_revalidates_result_hash_before_accepting_a_gate(tmp_path: Path) -> None:
    input_path = _input(tmp_path)
    runner = PlanningRunner(tmp_path, "run-1")
    invocation = runner.begin(
        PlanningStage.CAPTURE,
        role="intent-capture",
        input_paths=(input_path,),
        output_path=".intent/intent.json",
    )
    runner.record_result(invocation, {"ok": True, "payload": {"captured": True}})
    _trusted_gate(runner, invocation)
    result_path = tmp_path / ".factory" / "planning" / "run-1" / "stages" / "capture" / "r1" / "a1" / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result["payload"] = {"captured": "forged"}
    result_path.write_text(json.dumps(result) + "\n", encoding="utf-8")

    with pytest.raises(RunnerBlocked, match="evidence|result|hash"):
        runner.advance(invocation)

    assert runner.status().blocked is True


def test_invocation_json_rejects_duplicate_keys_even_when_the_value_matches(tmp_path: Path) -> None:
    input_path = _input(tmp_path)
    runner = PlanningRunner(tmp_path, "run-1")
    invocation = runner.begin(
        PlanningStage.CAPTURE,
        role="intent-capture",
        input_paths=(input_path,),
        output_path=".intent/intent.json",
    )
    invocation_path = tmp_path / ".factory" / "planning" / "run-1" / "stages" / "capture" / "r1" / "a1" / "invocation.json"
    stored = invocation.to_dict()
    invocation_path.write_text(
        '{"schema":1,"run_id":"run-1","run_id":"run-1",'
        + json.dumps({key: value for key, value in stored.items() if key != "schema"}, separators=(",", ":"))[1:],
        encoding="utf-8",
    )

    with pytest.raises(RunnerError, match="invocation|JSON|record"):
        runner.record_result(invocation, {"ok": True, "payload": {}})


def test_persisted_result_rejects_unknown_fields_and_non_finite_values(tmp_path: Path) -> None:
    input_path = _input(tmp_path)
    runner = PlanningRunner(tmp_path, "run-1")
    invocation = runner.begin(
        PlanningStage.CAPTURE,
        role="intent-capture",
        input_paths=(input_path,),
        output_path=".intent/intent.json",
    )
    record_dir = tmp_path / ".factory" / "planning" / "run-1" / "stages" / "capture" / "r1" / "a1"
    record_dir.mkdir(parents=True, exist_ok=True)
    (record_dir / "result.json").write_text(
        '{"schema":1,"run_id":"run-1","stage":"capture","revision":1,"attempt":1,'
        '"ok":true,"payload":{"value":NaN},"payload_sha256":"'
        + ("0" * 64)
        + '","session_id":null,"error":null,"unexpected":true}\n',
        encoding="utf-8",
    )

    with pytest.raises(RunnerBlocked, match="result|evidence|JSON"):
        runner.advance(invocation)


def test_advance_evidence_failure_is_durable_after_reopening(tmp_path: Path) -> None:
    input_path = _input(tmp_path)
    runner = PlanningRunner(tmp_path, "run-1")
    invocation = runner.begin(
        PlanningStage.CAPTURE,
        role="intent-capture",
        input_paths=(input_path,),
        output_path=".intent/intent.json",
    )

    with pytest.raises(RunnerBlocked, match="evidence|result|gate"):
        runner.advance(invocation)

    reopened = PlanningRunner(tmp_path, "run-1")
    state = reopened.status()
    assert state.blocked is True
    assert state.current_stage == PlanningStage.CAPTURE.value


def test_workflow_journal_rejects_duplicate_keys_and_unknown_fields(tmp_path: Path) -> None:
    runner = PlanningRunner(tmp_path, "run-1")
    runner.run_dir.mkdir(parents=True, exist_ok=True)
    runner.events_path.write_text(
        '{"schema":1,"action":"begin","run_id":"run-1","run_id":"run-1",'
        '"stage":"capture","revision":1,"attempt":1,"role":"intent-capture",'
        '"input_hashes":{},"output_path":".intent/intent.json","sequence":1}\n',
        encoding="utf-8",
    )

    with pytest.raises(RunnerError, match="journal|JSON|event"):
        runner.status()


def test_advance_and_record_gate_rehash_inputs_after_result_recording(tmp_path: Path) -> None:
    input_path = _input(tmp_path)
    runner = PlanningRunner(tmp_path, "run-1")
    invocation = runner.begin(
        PlanningStage.CAPTURE,
        role="intent-capture",
        input_paths=(input_path,),
        output_path=".intent/intent.json",
    )
    runner.record_result(invocation, {"ok": True, "payload": {"captured": True}})
    input_path.write_text("changed", encoding="utf-8")

    with pytest.raises(RunnerBlocked, match="stale"):
        _trusted_gate(runner, invocation)
    assert runner.status().blocked is True
    assert not (runner._record_dir(invocation) / "gate.json").exists()


def test_advance_rehashes_inputs_even_after_a_gate_was_recorded(tmp_path: Path) -> None:
    input_path = _input(tmp_path)
    runner = PlanningRunner(tmp_path, "run-1")
    invocation = runner.begin(
        PlanningStage.CAPTURE,
        role="intent-capture",
        input_paths=(input_path,),
        output_path=".intent/intent.json",
    )
    runner.record_result(invocation, {"ok": True, "payload": {"captured": True}})
    _trusted_gate(runner, invocation)
    input_path.write_text("changed", encoding="utf-8")

    with pytest.raises(RunnerBlocked, match="stale"):
        runner.advance(invocation)
    assert runner.status().blocked is True


def test_result_payload_rejects_path_aliases_as_worker_targets(tmp_path: Path) -> None:
    input_path = _input(tmp_path)
    runner = PlanningRunner(tmp_path, "run-1")
    invocation = runner.begin(
        PlanningStage.CAPTURE,
        role="intent-capture",
        input_paths=(input_path,),
        output_path=".intent/intent.json",
    )

    with pytest.raises(RunnerError, match="output target|worker-selected"):
        runner.record_result(
            invocation,
            {"ok": True, "payload": {"path": "outside/forged.json"}},
        )


def test_failed_result_blocks_without_calling_gate_or_advancing(tmp_path: Path) -> None:
    input_path = _input(tmp_path)
    runner = PlanningRunner(tmp_path, "run-1")
    invocation = runner.begin(
        PlanningStage.CAPTURE,
        role="intent-capture",
        input_paths=(input_path,),
        output_path=".intent/intent.json",
    )

    with pytest.raises(RunnerBlocked, match="failed|result"):
        runner.record_result(invocation, {"ok": False, "payload": {}, "error": "failed"})

    assert runner.status().blocked is True
    assert not (runner._record_dir(invocation) / "gate.json").exists()


def test_reopening_rejects_a_symlinked_invocation_record(tmp_path: Path) -> None:
    input_path = _input(tmp_path)
    runner = PlanningRunner(tmp_path, "run-1")
    invocation = runner.begin(
        PlanningStage.CAPTURE,
        role="intent-capture",
        input_paths=(input_path,),
        output_path=".intent/intent.json",
    )
    invocation_path = runner._record_dir(invocation) / "invocation.json"
    target = tmp_path / "invocation-copy.json"
    target.write_bytes(invocation_path.read_bytes())
    try:
        invocation_path.unlink()
        invocation_path.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are unavailable")

    with pytest.raises(RunnerError, match="invocation|unsafe|record"):
        runner.record_result(invocation, {"ok": True, "payload": {}})


def test_advance_rejects_a_symlinked_result_or_gate_record(tmp_path: Path) -> None:
    input_path = _input(tmp_path)
    runner = PlanningRunner(tmp_path, "run-1")
    invocation = runner.begin(
        PlanningStage.CAPTURE,
        role="intent-capture",
        input_paths=(input_path,),
        output_path=".intent/intent.json",
    )
    runner.record_result(invocation, {"ok": True, "payload": {"captured": True}})
    _trusted_gate(runner, invocation)
    record_dir = runner._record_dir(invocation)
    result_path = record_dir / "result.json"
    gate_path = record_dir / "gate.json"
    result_target = tmp_path / "result-copy.json"
    gate_target = tmp_path / "gate-copy.json"
    result_target.write_bytes(result_path.read_bytes())
    gate_target.write_bytes(gate_path.read_bytes())
    try:
        result_path.unlink()
        result_path.symlink_to(result_target)
        gate_path.unlink()
        gate_path.symlink_to(gate_target)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are unavailable")

    with pytest.raises(RunnerBlocked, match="evidence|unsafe|result|gate"):
        runner.advance(invocation)
    assert runner.status().blocked is True


def test_workflow_journal_symlink_is_not_followed_on_reopen(tmp_path: Path) -> None:
    runner = PlanningRunner(tmp_path, "run-1")
    input_path = _input(tmp_path)
    runner.begin(
        PlanningStage.CAPTURE,
        role="intent-capture",
        input_paths=(input_path,),
        output_path=".intent/intent.json",
    )
    target = tmp_path / "events-copy.jsonl"
    target.write_bytes(runner.events_path.read_bytes())
    try:
        runner.events_path.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are unavailable")

    with pytest.raises(RunnerError, match="journal|unsafe"):
        PlanningRunner(tmp_path, "run-1").status()


@pytest.mark.parametrize("projection", ["events_path", "integrity_path", "state_path"])
def test_explicit_recovery_blocks_on_high_level_projection_loss(
    tmp_path: Path, projection: str
) -> None:
    input_path = _input(tmp_path)
    runner = PlanningRunner(tmp_path, "run-1")
    _complete(runner, PlanningStage.CAPTURE, input_path)
    getattr(runner, projection).unlink()

    recovered = PlanningRunner(tmp_path, "run-1", recover=True)

    state = recovered.status()
    assert state.blocked is True
    assert state.reason == "recovery_integrity"
    with recovered._transaction() as connection:
        event = connection.execute(
            "SELECT action, event_json FROM workflow_events WHERE run_id=? ORDER BY sequence DESC LIMIT 1",
            (recovered.run_id,),
        ).fetchone()
    assert event is not None
    assert event[0] == "block"
    assert json.loads(event[1])["reason"] == "recovery_integrity"
    with recovered._transaction() as connection:
        before_count = connection.execute(
            "SELECT COUNT(*) FROM workflow_events WHERE run_id=?", (recovered.run_id,)
        ).fetchone()[0]
    with pytest.raises(RunnerBlocked, match="blocked|terminal"):
        recovered.begin(
            PlanningStage.PROVISIONAL_SPEC,
            role="provisional-spec-agent",
            input_paths=(input_path,),
            output_path="docs/spec.md",
        )
    with recovered._transaction() as connection:
        after_count = connection.execute(
            "SELECT COUNT(*) FROM workflow_events WHERE run_id=?", (recovered.run_id,)
        ).fetchone()[0]
    assert after_count == before_count


def test_explicit_recovery_blocks_on_tampered_integrity_projection(tmp_path: Path) -> None:
    input_path = _input(tmp_path)
    runner = PlanningRunner(tmp_path, "run-1")
    _complete(runner, PlanningStage.CAPTURE, input_path)
    integrity = json.loads(runner.integrity_path.read_text(encoding="utf-8"))
    integrity["head_sha256"] = "f" * 64
    runner.integrity_path.write_text(json.dumps(integrity) + "\n", encoding="utf-8")

    recovered = PlanningRunner(tmp_path, "run-1", recover=True)

    assert recovered.status().blocked is True
    assert recovered.status().reason == "recovery_integrity"


@pytest.mark.parametrize("table", ["schema_meta", "workflow_events"])
def test_reopen_rejects_deleted_authoritative_schema_object(
    tmp_path: Path, table: str
) -> None:
    runner = PlanningRunner(tmp_path, "run-1")
    with runner._transaction() as connection:
        connection.execute(f"DROP TABLE {table}")

    with pytest.raises(RunnerError, match="schema|incomplete|malformed"):
        PlanningRunner(tmp_path, "run-1")


def test_reopen_rejects_an_inert_immutable_trigger(tmp_path: Path) -> None:
    runner = PlanningRunner(tmp_path, "run-1")
    with runner._transaction() as connection:
        connection.execute("DROP TRIGGER invocation_records_immutable_update")
        connection.execute(
            "CREATE TRIGGER invocation_records_immutable_update "
            "BEFORE UPDATE ON invocation_records BEGIN SELECT 1; END"
        )

    with pytest.raises(RunnerError, match="schema|trigger|immutable"):
        PlanningRunner(tmp_path, "run-1")


@pytest.mark.parametrize("object_kind", ["table", "trigger"])
def test_reopen_rejects_unexpected_schema_objects(
    tmp_path: Path, object_kind: str
) -> None:
    runner = PlanningRunner(tmp_path, "run-1")
    with runner._transaction() as connection:
        connection.execute("CREATE TABLE injected_object (value TEXT)")
        if object_kind == "trigger":
            connection.execute(
                "CREATE TRIGGER injected_trigger "
                "AFTER INSERT ON injected_object BEGIN SELECT 1; END"
            )

    with pytest.raises(RunnerError, match="schema|object"):
        PlanningRunner(tmp_path, "run-1")


def test_explicit_recovery_blocks_on_tampered_leaf_projection(tmp_path: Path) -> None:
    input_path = _input(tmp_path)
    runner = PlanningRunner(tmp_path, "run-1")
    invocation = runner.begin(
        PlanningStage.CAPTURE,
        role="intent-capture",
        input_paths=(input_path,),
        output_path=".intent/intent.json",
    )
    runner.record_result(invocation, {"ok": True, "payload": {"kept": True}})
    _trusted_gate(runner, invocation)
    runner.advance(invocation)
    result_path = runner._record_dir(invocation) / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result["payload"]["kept"] = False
    result_path.write_text(json.dumps(result) + "\n", encoding="utf-8")

    recovered = PlanningRunner(tmp_path, "run-1", recover=True)

    assert recovered.status().blocked is True
    assert recovered.status().reason == "recovery_integrity"


def test_recovery_blocks_on_malformed_orphan_projection_path(tmp_path: Path) -> None:
    runner = PlanningRunner(tmp_path, "run-1")
    orphan = runner.run_dir / "stages" / "not-a-stage" / "r1" / "a1" / "result.json"
    orphan.parent.mkdir(parents=True, exist_ok=True)
    orphan.write_text("{}\n", encoding="utf-8")

    recovered = PlanningRunner(tmp_path, "run-1", recover=True)

    assert recovered.status().blocked is True
    assert recovered.status().reason == "orphan_record"
    with pytest.raises(RunnerBlocked, match="blocked|orphan|recovery"):
        recovered.begin(
            PlanningStage.CAPTURE,
            role="intent-capture",
            input_paths=(),
            output_path=".intent/intent.json",
        )


def test_record_gate_preflight_failure_is_durably_blocked(tmp_path: Path) -> None:
    input_path = _input(tmp_path)
    runner = PlanningRunner(tmp_path, "run-1")
    invocation = runner.begin(
        PlanningStage.CAPTURE,
        role="intent-capture",
        input_paths=(input_path,),
        output_path=".intent/intent.json",
    )
    runner.record_result(invocation, {"ok": True, "payload": {}})
    _parent_output(runner, invocation)

    with pytest.raises(RunnerBlocked, match="gate|invalid|durable"):
        runner.record_gate(invocation, verification={})
    assert runner.status().blocked is True


def test_gate_binding_rejects_parent_output_replacement(tmp_path: Path) -> None:
    input_path = _input(tmp_path)
    runner = PlanningRunner(tmp_path, "run-1")
    invocation = runner.begin(
        PlanningStage.CAPTURE,
        role="intent-capture",
        input_paths=(input_path,),
        output_path=".intent/intent.json",
    )
    runner.record_result(invocation, {"ok": True, "payload": {}})
    output = _parent_output(runner, invocation, b"original artifact")
    verification = runner._parent_gate_verifier.attest(
        invocation, gate_id="gate-capture", passed=True, detail="verified"
    )
    assert verification.output_sha256 == hashlib.sha256(
        b"original artifact"
    ).hexdigest()
    output.write_bytes(b"replacement artifact")

    with pytest.raises(RunnerBlocked, match="gate|output|invalid"):
        runner.record_gate(invocation, verification=verification)
    assert runner.status().blocked is True


def test_recovery_missing_authoritative_record_fails_closed(tmp_path: Path) -> None:
    input_path = _input(tmp_path)
    runner = PlanningRunner(tmp_path, "run-1")
    runner.begin(
        PlanningStage.CAPTURE,
        role="intent-capture",
        input_paths=(input_path,),
        output_path=".intent/intent.json",
    )
    with runner._transaction() as connection:
        connection.execute("DROP TRIGGER invocation_records_immutable_delete")
        connection.execute(
            "DELETE FROM invocation_records WHERE run_id=?",
            (runner.run_id,),
        )
        connection.execute(
            "CREATE TRIGGER invocation_records_immutable_delete "
            "BEFORE DELETE ON invocation_records "
            "BEGIN SELECT RAISE(ABORT, 'immutable invocation record'); END"
        )

    with pytest.raises(RunnerBlocked, match="durable|recovery|mutation"):
        PlanningRunner(tmp_path, "run-1", recover=True)
    reopened = PlanningRunner(tmp_path, "run-1")
    assert reopened.status().blocked is True
    assert reopened.status().reason == "durable_unavailable"


def test_recovery_block_capacity_failure_is_explicitly_durable_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    input_path = _input(tmp_path)
    runner = PlanningRunner(tmp_path, "run-1")
    runner.begin(
        PlanningStage.CAPTURE,
        role="intent-capture",
        input_paths=(input_path,),
        output_path=".intent/intent.json",
    )
    monkeypatch.setattr(
        runner_module, "_MAX_WORKFLOW_JOURNAL_BYTES", runner.events_path.stat().st_size
    )

    with pytest.raises(RunnerBlocked, match="durable|recovery|mutation"):
        PlanningRunner(tmp_path, "run-1", recover=True)
    reopened = PlanningRunner(tmp_path, "run-1")
    assert reopened.status().blocked is True
    assert reopened.status().reason == "durable_unavailable"


def test_orphan_stage_projection_recovery_is_immutable_and_not_bypassable(
    tmp_path: Path,
) -> None:
    input_path = _input(tmp_path)
    runner = PlanningRunner(tmp_path, "run-1")
    _complete(runner, PlanningStage.CAPTURE, input_path)
    orphan = runner.run_dir / "stages" / "capture" / "r99" / "a1" / "result.json"
    orphan.parent.mkdir(parents=True, exist_ok=True)
    orphan.write_text("{}\n", encoding="utf-8")

    recovered = PlanningRunner(tmp_path, "run-1", recover=True)

    assert recovered.status().blocked is True
    assert recovered.status().reason == "orphan_record"
    with recovered._transaction() as connection:
        block_count = connection.execute(
            "SELECT COUNT(*) FROM blocks WHERE run_id=?", (recovered.run_id,)
        ).fetchone()[0]
        before_count = connection.execute(
            "SELECT COUNT(*) FROM workflow_events WHERE run_id=?", (recovered.run_id,)
        ).fetchone()[0]
    assert block_count == 1
    with pytest.raises(RunnerBlocked, match="blocked|recovery"):
        recovered.begin(
            PlanningStage.PROVISIONAL_SPEC,
            role="provisional-spec-agent",
            input_paths=(input_path,),
            output_path="docs/spec.md",
        )
    with recovered._transaction() as connection:
        after_count = connection.execute(
            "SELECT COUNT(*) FROM workflow_events WHERE run_id=?", (recovered.run_id,)
        ).fetchone()[0]
    assert after_count == before_count


def test_oversized_invocation_identity_fails_closed(tmp_path: Path) -> None:
    input_path = _input(tmp_path)
    runner = PlanningRunner(tmp_path, "run-1")
    invocation = runner.begin(
        PlanningStage.CAPTURE,
        role="intent-capture",
        input_paths=(input_path,),
        output_path=".intent/intent.json",
    )
    oversized = replace(invocation, revision=2**63)

    with pytest.raises(RunnerBlocked, match="durable|mutation|invalid"):
        runner.record_result(oversized, {"ok": True, "payload": {}})
    assert runner.status().blocked is True


def test_begin_journal_capacity_failure_is_explicitly_durable_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    input_path = _input(tmp_path)
    runner = PlanningRunner(tmp_path, "run-1")
    monkeypatch.setattr(runner_module, "_MAX_WORKFLOW_JOURNAL_BYTES", 1)

    with pytest.raises(RunnerBlocked, match="durable|mutation"):
        runner.begin(
            PlanningStage.CAPTURE,
            role="intent-capture",
            input_paths=(input_path,),
            output_path=".intent/intent.json",
        )


def test_immutable_block_persistence_failure_is_explicitly_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    input_path = _input(tmp_path)
    runner = PlanningRunner(tmp_path, "run-1")
    invocation = runner.begin(
        PlanningStage.CAPTURE,
        role="intent-capture",
        input_paths=(input_path,),
        output_path=".intent/intent.json",
    )

    def fail_event(*args: object, **kwargs: object) -> None:
        raise OSError("injected event failure")

    monkeypatch.setattr(runner, "_append_event", fail_event)
    with pytest.raises(RunnerBlocked, match="durable|unavailable|mutation"):
        runner.record_result(invocation, {"ok": True, "payload": {}})


def test_post_advance_projection_failure_creates_immutable_block(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    input_path = _input(tmp_path)
    runner = PlanningRunner(tmp_path, "run-1")
    invocation = runner.begin(
        PlanningStage.CAPTURE,
        role="intent-capture",
        input_paths=(input_path,),
        output_path=".intent/intent.json",
    )
    runner.record_result(invocation, {"ok": True, "payload": {}})
    _trusted_gate(runner, invocation)
    original_write_json = runner._write_json

    def fail_state_projection(path: Path, value: object, label: str) -> None:
        if label == "workflow state":
            raise OSError("injected projection failure")
        original_write_json(path, value, label)

    monkeypatch.setattr(runner, "_write_json", fail_state_projection)
    with pytest.raises(RunnerBlocked, match="advance_projection_failure"):
        runner.advance(invocation)

    with runner._transaction() as connection:
        event = connection.execute(
            "SELECT action, event_json FROM workflow_events WHERE run_id=? ORDER BY sequence DESC LIMIT 1",
            (runner.run_id,),
        ).fetchone()
        block_count = connection.execute(
            "SELECT COUNT(*) FROM blocks WHERE run_id=?", (runner.run_id,)
        ).fetchone()[0]
    assert event is not None
    assert event[0] == "block"
    assert json.loads(event[1])["reason"] == "advance_projection_failure"
    assert block_count == 1
    assert runner.status().blocked is True


def _trusted_gate(
    runner: PlanningRunner,
    invocation: AgentInvocation,
    *,
    passed: bool = True,
    detail: str = "verified",
    evidence: dict[str, object] | None = None,
) -> GateRecord:
    _parent_output(runner, invocation)
    verification = runner._parent_gate_verifier.attest(
        invocation,
        gate_id=f"gate-{invocation.stage.value}",
        passed=passed,
        detail=detail,
        evidence=evidence,
    )
    return runner.record_gate(invocation, verification=verification)


def test_invocation_result_and_gate_records_are_deeply_immutable_and_non_aliasing(tmp_path: Path) -> None:
    input_path = _input(tmp_path)
    runner = PlanningRunner(tmp_path, "run-1")
    invocation = runner.begin(
        PlanningStage.CAPTURE,
        role="intent-capture",
        input_paths=(input_path,),
        output_path=".intent/intent.json",
    )

    with pytest.raises(TypeError):
        cast(dict[str, str], invocation.input_hashes)["forged.json"] = "0" * 64

    result = runner.record_result(invocation, {"ok": True, "payload": {"nested": {"value": "kept"}}})
    with pytest.raises(TypeError):
        cast(dict[str, dict[str, str]], result.payload)["nested"]["value"] = "forged"
    result_projection = result.to_dict()
    cast(dict[str, dict[str, str]], result_projection["payload"])["nested"]["value"] = "forged"
    assert cast(dict[str, dict[str, str]], result.payload)["nested"]["value"] == "kept"

    gate = _trusted_gate(runner, invocation, evidence={"nested": {"value": "kept"}})
    with pytest.raises(TypeError):
        cast(dict[str, dict[str, str]], gate.evidence)["nested"]["value"] = "forged"
    gate_projection = gate.to_dict()
    cast(dict[str, dict[str, str]], gate_projection["evidence"])["nested"]["value"] = "forged"
    assert cast(dict[str, dict[str, str]], gate.evidence)["nested"]["value"] == "kept"


def test_reopening_an_interrupted_begin_recovers_a_durable_block(tmp_path: Path) -> None:
    input_path = _input(tmp_path)
    runner = PlanningRunner(tmp_path, "run-1")
    runner.begin(
        PlanningStage.CAPTURE,
        role="intent-capture",
        input_paths=(input_path,),
        output_path=".intent/intent.json",
    )

    reopened = PlanningRunner(tmp_path, "run-1", recover=True)
    state = reopened.status()
    assert state.blocked is True
    assert state.reason == "interrupted_attempt"
    assert json.loads(reopened.events_path.read_text(encoding="utf-8").splitlines()[-1])["action"] == "block"


@pytest.mark.parametrize("tamper", ["rewrite", "truncate", "delete", "resequence"])
def test_journal_hash_chain_rejects_history_tampering(tmp_path: Path, tamper: str) -> None:
    input_path = _input(tmp_path)
    runner = PlanningRunner(tmp_path, "run-1")
    runner.begin(
        PlanningStage.CAPTURE,
        role="intent-capture",
        input_paths=(input_path,),
        output_path=".intent/intent.json",
    )
    events_path = runner.events_path
    lines = events_path.read_text(encoding="utf-8").splitlines()
    if tamper == "rewrite":
        event = json.loads(lines[0])
        event["role"] = "rewritten"
        events_path.write_text(json.dumps(event) + "\n", encoding="utf-8")
    elif tamper == "truncate":
        events_path.write_text("", encoding="utf-8")
    elif tamper == "delete":
        events_path.unlink()
    else:
        event = json.loads(lines[0])
        event["sequence"] = 2
        events_path.write_text(json.dumps(event) + "\n", encoding="utf-8")

    with pytest.raises(RunnerError, match="journal|integrity|history"):
        PlanningRunner(tmp_path, "run-1").status()


@pytest.mark.parametrize("payload_kind", ["deep", "oversized", "nonfinite"])
def test_hostile_result_json_bounds_and_finite_numbers_fail_as_runner_errors(
    tmp_path: Path, payload_kind: str
) -> None:
    input_path = _input(tmp_path)
    runner = PlanningRunner(tmp_path, "run-1")
    invocation = runner.begin(
        PlanningStage.CAPTURE,
        role="intent-capture",
        input_paths=(input_path,),
        output_path=".intent/intent.json",
    )
    if payload_kind == "deep":
        payload = {}
        for _ in range(100):
            payload = {"nested": payload}
    elif payload_kind == "oversized":
        payload = {"blob": "x" * 1_100_000}
    else:
        payload = {"number": float("nan")}

    with pytest.raises(RunnerError):
        runner.record_result(invocation, {"ok": True, "payload": payload})


@pytest.mark.parametrize("evidence_kind", ["deep", "oversized"])
def test_hostile_gate_evidence_is_bounded_and_durably_blocks(tmp_path: Path, evidence_kind: str) -> None:
    input_path = _input(tmp_path)
    runner = PlanningRunner(tmp_path, "run-1")
    invocation = runner.begin(
        PlanningStage.CAPTURE,
        role="intent-capture",
        input_paths=(input_path,),
        output_path=".intent/intent.json",
    )
    runner.record_result(invocation, {"ok": True, "payload": {"captured": True}})
    if evidence_kind == "deep":
        evidence: dict[str, object] = {}
        for _ in range(100):
            evidence = {"nested": evidence}
    else:
        evidence = {"blob": "x" * 1_100_000}

    with pytest.raises(RunnerBlocked):
        _trusted_gate(runner, invocation, evidence=evidence)
    assert runner.status().blocked is True


def test_nested_worker_output_target_spoof_is_rejected(tmp_path: Path) -> None:
    input_path = _input(tmp_path)
    runner = PlanningRunner(tmp_path, "run-1")
    invocation = runner.begin(
        PlanningStage.CAPTURE,
        role="intent-capture",
        input_paths=(input_path,),
        output_path=".intent/intent.json",
    )

    with pytest.raises(RunnerError, match="output target|worker-selected"):
        runner.record_result(
            invocation,
            {"ok": True, "payload": {"metadata": [{"nested": {"output_path": "forged.json"}}]}},
        )


def test_advance_requires_the_persisted_parent_output_binding_to_match_its_hash(tmp_path: Path) -> None:
    input_path = _input(tmp_path)
    runner = PlanningRunner(tmp_path, "run-1")
    invocation = runner.begin(
        PlanningStage.CAPTURE,
        role="intent-capture",
        input_paths=(input_path,),
        output_path=".intent/intent.json",
    )
    runner.record_result(invocation, {"ok": True, "payload": {"captured": True}})
    _trusted_gate(runner, invocation)
    invocation_path = runner._record_dir(invocation) / "invocation.json"
    stored = json.loads(invocation_path.read_text(encoding="utf-8"))
    stored["output_path"] = ".intent/forged.json"
    invocation_path.write_text(json.dumps(stored) + "\n", encoding="utf-8")

    with pytest.raises(RunnerBlocked, match="binding|evidence|invocation"):
        runner.advance(invocation)
    assert runner.status().blocked is True


def test_record_gate_requires_a_trusted_parent_verification_capability(tmp_path: Path) -> None:
    input_path = _input(tmp_path)
    runner = PlanningRunner(tmp_path, "run-1")
    invocation = runner.begin(
        PlanningStage.CAPTURE,
        role="intent-capture",
        input_paths=(input_path,),
        output_path=".intent/intent.json",
    )
    runner.record_result(invocation, {"ok": True, "payload": {"captured": True}})

    with pytest.raises(RunnerError, match="trusted|verification|capability"):
        runner.record_gate(invocation, gate_id="gate-capture", passed=True, detail="self-certified")


def test_advance_revalidates_the_parent_output_path_for_reparse_points(tmp_path: Path) -> None:
    input_path = _input(tmp_path)
    runner = PlanningRunner(tmp_path, "run-1")
    invocation = runner.begin(
        PlanningStage.CAPTURE,
        role="intent-capture",
        input_paths=(input_path,),
        output_path=".intent/intent.json",
    )
    runner.record_result(invocation, {"ok": True, "payload": {"captured": True}})
    _trusted_gate(runner, invocation)
    outside = tmp_path.parent / "outside-output"
    outside.mkdir()
    link = tmp_path / ".intent"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are unavailable")

    with pytest.raises(RunnerBlocked, match="unsafe|path|evidence"):
        runner.advance(invocation)
    assert runner.status().blocked is True


def test_reopened_interrupted_attempt_can_retry_with_same_revision(tmp_path: Path) -> None:
    input_path = _input(tmp_path)
    runner = PlanningRunner(tmp_path, "run-1")
    runner.begin(
        PlanningStage.CAPTURE,
        role="intent-capture",
        input_paths=(input_path,),
        output_path=".intent/intent.json",
    )

    reopened = PlanningRunner(tmp_path, "run-1", recover=True)
    retry = reopened.begin(
        PlanningStage.CAPTURE,
        role="intent-capture",
        input_paths=(input_path,),
        output_path=".intent/intent.json",
    )
    assert (retry.revision, retry.attempt) == (1, 2)


def test_writer_lock_serializes_two_runner_instances_deterministically(tmp_path: Path) -> None:
    first = PlanningRunner(tmp_path, "run-1")
    second = PlanningRunner(tmp_path, "run-1")
    entered = threading.Event()

    def contender() -> None:
        with second._writer_lock():
            entered.set()

    with first._writer_lock():
        thread = threading.Thread(target=contender)
        thread.start()
        assert not entered.wait(0.1)
    thread.join(timeout=2)
    assert not thread.is_alive()
    assert entered.is_set()


def test_concurrent_begin_allocates_one_attempt_and_preserves_one_sequence_chain(tmp_path: Path) -> None:
    input_path = _input(tmp_path)
    runners = [PlanningRunner(tmp_path, "run-1"), PlanningRunner(tmp_path, "run-1")]
    start = threading.Barrier(2)
    outcomes: list[tuple[str, object]] = []
    outcome_lock = threading.Lock()

    def worker(runner: PlanningRunner) -> None:
        start.wait()
        try:
            invocation = runner.begin(
                PlanningStage.CAPTURE,
                role="intent-capture",
                input_paths=(input_path,),
                output_path=".intent/intent.json",
            )
        except Exception as exc:  # noqa: BLE001 - assert the exact winner below
            outcome = ("error", exc)
        else:
            outcome = ("ok", invocation)
        with outcome_lock:
            outcomes.append(outcome)

    threads = [threading.Thread(target=worker, args=(runner,)) for runner in runners]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=3)
    assert all(not thread.is_alive() for thread in threads)
    assert [kind for kind, _ in outcomes].count("ok") == 1
    assert [kind for kind, _ in outcomes].count("error") == 1
    events = [
        json.loads(line) for line in runners[0].events_path.read_text(encoding="utf-8").splitlines()
    ]
    assert [event["sequence"] for event in events] == [1]


@pytest.mark.parametrize("output_path", [
    "CON.txt",
    "reports/trailing. ",
    "reports/trailing.",
    "reports/aux.log",
    "reports/foo:bar.json",
    "reports/foo*bar.json",
    "reports/foo<bar.json",
    "reports/foo|bar.json",
    "reports/foo?bar.json",
    "CONIN$.txt",
    "CONOUT$.txt",
    ".factory/planning/run-1/workflow-events.jsonl",
])
def test_windows_unsafe_or_runner_control_output_targets_are_rejected(
    tmp_path: Path, output_path: str
) -> None:
    input_path = _input(tmp_path)
    runner = PlanningRunner(tmp_path, "run-1")

    with pytest.raises(RunnerError, match="output target|unsafe"):
        runner.begin(
            PlanningStage.CAPTURE,
            role="intent-capture",
            input_paths=(input_path,),
            output_path=output_path,
        )


def test_reopening_rejects_a_persisted_windows_unsafe_output_target(tmp_path: Path) -> None:
    input_path = _input(tmp_path)
    runner = PlanningRunner(tmp_path, "run-1")
    invocation = runner.begin(
        PlanningStage.CAPTURE,
        role="intent-capture",
        input_paths=(input_path,),
        output_path=".intent/intent.json",
    )
    invocation_path = runner._record_dir(invocation) / "invocation.json"
    stored = invocation.to_dict()
    stored["output_path"] = "CON.txt"
    invocation_path.write_text(json.dumps(stored) + "\n", encoding="utf-8")

    with pytest.raises(RunnerError, match="invocation|output target|unsafe"):
        runner.record_result(invocation, {"ok": True, "payload": {}})


def test_oversized_control_file_is_rejected_before_json_decoding(tmp_path: Path) -> None:
    input_path = _input(tmp_path)
    runner = PlanningRunner(tmp_path, "run-1")
    invocation = runner.begin(
        PlanningStage.CAPTURE,
        role="intent-capture",
        input_paths=(input_path,),
        output_path=".intent/intent.json",
    )
    control_path = runner._record_dir(invocation) / "invocation.json"
    control_path.write_bytes(b"x" * (1_048_576 + 1))

    with pytest.raises(RunnerError, match="oversized"):
        runner._read_json(control_path, "invocation record")


def test_oversized_workflow_journal_is_rejected_before_reading_the_journal(tmp_path: Path) -> None:
    runner = PlanningRunner(tmp_path, "run-1")
    limit = getattr(runner_module, "_MAX_WORKFLOW_JOURNAL_BYTES", 1_048_576)
    runner.run_dir.mkdir(parents=True, exist_ok=True)
    runner.events_path.write_bytes(b"x" * (limit + 1))

    with pytest.raises(RunnerError, match="oversized"):
        runner.status()


def test_oversized_result_error_is_rejected_before_result_write(tmp_path: Path) -> None:
    input_path = _input(tmp_path)
    runner = PlanningRunner(tmp_path, "run-1")
    invocation = runner.begin(
        PlanningStage.CAPTURE,
        role="intent-capture",
        input_paths=(input_path,),
        output_path=".intent/intent.json",
    )

    with pytest.raises(RunnerBlocked, match="result|error|oversized"):
        runner.record_result(
            invocation,
            {"ok": False, "payload": {}, "error": "x" * 100_000},
        )
    assert not (runner._record_dir(invocation) / "result.json").exists()


def test_oversized_gate_evidence_is_rejected_before_gate_write(tmp_path: Path) -> None:
    input_path = _input(tmp_path)
    runner = PlanningRunner(tmp_path, "run-1")
    invocation = runner.begin(
        PlanningStage.CAPTURE,
        role="intent-capture",
        input_paths=(input_path,),
        output_path=".intent/intent.json",
    )
    runner.record_result(invocation, {"ok": True, "payload": {}})

    with pytest.raises(RunnerBlocked, match="evidence|oversized"):
        _trusted_gate(runner, invocation, evidence={"blob": "x" * 100_000})
    assert not (runner._record_dir(invocation) / "gate.json").exists()


def test_forged_serialized_gate_verification_cannot_authorize_advancement(tmp_path: Path) -> None:
    input_path = _input(tmp_path)
    runner = PlanningRunner(tmp_path, "run-1")
    invocation = runner.begin(
        PlanningStage.CAPTURE,
        role="intent-capture",
        input_paths=(input_path,),
        output_path=".intent/intent.json",
    )
    runner.record_result(invocation, {"ok": True, "payload": {}})
    _parent_output(runner, invocation)
    valid = runner._parent_gate_verifier.attest(
        invocation, gate_id="gate-capture", passed=True, detail="verified"
    )

    with pytest.raises(RunnerError, match="trusted|provenance|verification"):
        runner.record_gate(invocation, verification=valid.to_dict())


@pytest.mark.parametrize("schema", [True, 1.0])
def test_non_integer_invocation_schema_is_rejected_without_result_record(
    tmp_path: Path, schema: object
) -> None:
    input_path = _input(tmp_path)
    runner = PlanningRunner(tmp_path, "run-1")
    invocation = runner.begin(
        PlanningStage.CAPTURE,
        role="intent-capture",
        input_paths=(input_path,),
        output_path=".intent/intent.json",
    )
    malformed = AgentInvocation(
        cast(int, schema),
        invocation.run_id,
        invocation.stage,
        invocation.revision,
        invocation.attempt,
        invocation.role,
        invocation.input_hashes,
        invocation.output_path,
    )

    with pytest.raises(RunnerError, match="invocation|schema"):
        runner.record_result(malformed, {"ok": True, "payload": {}})
    assert not (runner._record_dir(invocation) / "result.json").exists()


@pytest.mark.parametrize(
    "failure_boundary",
    ["invocation.json", "result.json", "gate.json", "workflow-integrity.json", "workflow-state.json"],
)
def test_write_failure_reopens_as_a_durable_blocked_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure_boundary: str
) -> None:
    input_path = _input(tmp_path)
    runner = PlanningRunner(tmp_path, "run-1")
    original_write_json = runner._write_json

    def fail_boundary(path: Path, value: object, label: str) -> None:
        if path.name == failure_boundary:
            raise OSError(f"injected {failure_boundary} failure")
        original_write_json(path, value, label)

    monkeypatch.setattr(runner, "_write_json", fail_boundary)
    if failure_boundary in {"invocation.json", "workflow-integrity.json", "workflow-state.json"}:
        with pytest.raises(RunnerBlocked, match="mutation|write|durab"):
            runner.begin(
                PlanningStage.CAPTURE,
                role="intent-capture",
                input_paths=(input_path,),
                output_path=".intent/intent.json",
            )
    else:
        invocation = runner.begin(
            PlanningStage.CAPTURE,
            role="intent-capture",
            input_paths=(input_path,),
            output_path=".intent/intent.json",
        )
        if failure_boundary == "result.json":
            with pytest.raises(RunnerBlocked, match="mutation|write|durab"):
                runner.record_result(invocation, {"ok": True, "payload": {}})
        else:
            runner.record_result(invocation, {"ok": True, "payload": {}})
            _parent_output(runner, invocation)
            verification = runner._parent_gate_verifier.attest(
                invocation,
                gate_id="gate-capture",
                passed=True,
                detail="verified",
            )
            with pytest.raises(RunnerBlocked, match="mutation|write|durab"):
                runner.record_gate(invocation, verification=verification)

    reopened = PlanningRunner(tmp_path, "run-1")
    assert reopened.status().blocked is True


def test_one_shot_journal_fsync_failure_reopens_as_a_durable_blocked_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    input_path = _input(tmp_path)
    runner = PlanningRunner(tmp_path, "run-1")
    invocation = runner.begin(
        PlanningStage.CAPTURE,
        role="intent-capture",
        input_paths=(input_path,),
        output_path=".intent/intent.json",
    )
    original_fsync = runner_module.os.fsync
    failed = False

    def fail_once(fd: int) -> None:
        nonlocal failed
        if not failed:
            failed = True
            raise OSError("injected fsync failure")
        original_fsync(fd)

    monkeypatch.setattr(runner_module.os, "fsync", fail_once)
    with pytest.raises(RunnerBlocked, match="mutation|write|durab"):
        runner.record_result(invocation, {"ok": True, "payload": {}})

    reopened = PlanningRunner(tmp_path, "run-1")
    assert reopened.status().blocked is True


def test_reopening_missing_result_record_reconciles_a_durable_block(tmp_path: Path) -> None:
    input_path = _input(tmp_path)
    runner = PlanningRunner(tmp_path, "run-1")
    invocation = runner.begin(
        PlanningStage.CAPTURE,
        role="intent-capture",
        input_paths=(input_path,),
        output_path=".intent/intent.json",
    )
    runner.record_result(invocation, {"ok": True, "payload": {}})
    (runner._record_dir(invocation) / "result.json").unlink()

    reopened = PlanningRunner(tmp_path, "run-1", recover=True)
    state = reopened.status()
    assert state.blocked is True
    assert json.loads(reopened.events_path.read_text(encoding="utf-8").splitlines()[-1])["action"] == "block"


def test_reopening_an_orphan_control_record_blocks_without_deleting_it(tmp_path: Path) -> None:
    runner = PlanningRunner(tmp_path, "run-1")
    orphan = runner.run_dir / "stages" / "capture" / "r1" / "a1" / "result.json"
    orphan.parent.mkdir(parents=True, exist_ok=True)
    orphan.write_text("{}\n", encoding="utf-8")

    reopened = PlanningRunner(tmp_path, "run-1", recover=True)
    assert reopened.status().blocked is True
    assert orphan.exists()


def test_transactional_parent_owned_stage_contract(tmp_path: Path) -> None:
    input_path = _input(tmp_path)
    runner = PlanningRunner(tmp_path, "run-1")
    store_path = tmp_path / ".factory" / "planning" / "run-1" / "workflow.sqlite3"

    assert store_path.is_file()
    with sqlite3.connect(store_path) as connection:
        assert connection.execute("PRAGMA synchronous").fetchone() == (2,)
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert {"run_metadata", "stage_attempts", "workflow_events"} <= tables

    invocation = runner.begin(
        PlanningStage.CAPTURE,
        role="intent-capture",
        input_paths=(input_path,),
        output_path=".intent/intent.json",
    )
    runner.record_result(invocation, {"ok": True, "payload": {}})
    _trusted_gate(runner, invocation)
    runner.advance(invocation)

    with sqlite3.connect(store_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM workflow_events").fetchone() == (4,)
        assert connection.execute("SELECT COUNT(*) FROM stage_attempts").fetchone() == (1,)
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(
                "UPDATE stage_attempts SET role='worker-selected' WHERE run_id='run-1'"
            )
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(
                "UPDATE transitions SET action='block' WHERE run_id='run-1' AND sequence=1"
            )


def test_gate_verification_is_bound_to_the_current_lineage_and_policy(
    tmp_path: Path,
) -> None:
    input_path = _input(tmp_path)
    runner = PlanningRunner(tmp_path, "run-1")
    invocation = runner.begin(
        PlanningStage.CAPTURE,
        role="intent-capture",
        input_paths=(input_path,),
        output_path=".intent/intent.json",
    )
    runner.record_result(invocation, {"ok": True, "payload": {}})
    _parent_output(runner, invocation)

    verification = runner._parent_gate_verifier.attest(
        invocation,
        gate_id="gate-capture",
        passed=True,
        detail="verified",
        policy_version="planning-gates-v1",
        resolver_id="resolver-v1",
    )

    assert verification.run_id == "run-1"
    assert verification.stage is PlanningStage.CAPTURE
    assert verification.revision == invocation.revision
    assert verification.attempt == invocation.attempt
    assert dict(verification.input_hashes) == dict(invocation.input_hashes)
    assert verification.policy_version == "planning-gates-v1"
    assert verification.resolver_id == "resolver-v1"
    assert runner.record_gate(invocation, verification=verification).passed is True


def test_failed_gate_attestation_cannot_be_cloned_into_a_passing_gate(tmp_path: Path) -> None:
    input_path = _input(tmp_path)
    runner = PlanningRunner(tmp_path, "run-1")
    invocation = runner.begin(
        PlanningStage.CAPTURE,
        role="intent-capture",
        input_paths=(input_path,),
        output_path=".intent/intent.json",
    )
    runner.record_result(invocation, {"ok": True, "payload": {}})
    _parent_output(runner, invocation)
    failed = runner._parent_gate_verifier.attest(
        invocation, gate_id="gate-capture", passed=False, detail="rejected"
    )
    forged = replace(failed, passed=True)

    with pytest.raises(RunnerBlocked, match="gate|verification|mutation"):
        runner.record_gate(invocation, verification=forged)
    assert runner.status().blocked is True


def test_cyclic_worker_output_is_rejected_without_hanging(tmp_path: Path) -> None:
    input_path = _input(tmp_path)
    runner = PlanningRunner(tmp_path, "run-1")
    invocation = runner.begin(
        PlanningStage.CAPTURE,
        role="intent-capture",
        input_paths=(input_path,),
        output_path=".intent/intent.json",
    )
    cyclic: dict[str, object] = {}
    cyclic["self"] = cyclic

    with pytest.raises(RunnerBlocked, match="cyclic|JSON|mutation"):
        runner.record_result(invocation, {"ok": True, "payload": cyclic})
    assert runner.status().blocked is True


def test_stale_input_rehashing_is_bounded_by_the_input_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    input_path = _input(tmp_path)
    runner = PlanningRunner(tmp_path, "run-1")
    invocation = runner.begin(
        PlanningStage.CAPTURE,
        role="intent-capture",
        input_paths=(input_path,),
        output_path=".intent/intent.json",
    )
    monkeypatch.setattr(runner_module, "_MAX_INPUT_BYTES", 4)
    input_path.write_text("changed", encoding="utf-8")

    assert runner._stale_input_reason(invocation) == "input set is oversized"


@pytest.mark.parametrize("field", ["revision", "attempt"])
@pytest.mark.parametrize("malformed", [True, 1.0])
def test_gate_verification_lineage_requires_exact_positive_integers(
    tmp_path: Path, field: str, malformed: object
) -> None:
    input_path = _input(tmp_path)
    runner = PlanningRunner(tmp_path, "run-1")
    invocation = runner.begin(
        PlanningStage.CAPTURE,
        role="intent-capture",
        input_paths=(input_path,),
        output_path=".intent/intent.json",
    )
    runner.record_result(invocation, {"ok": True, "payload": {}})
    _parent_output(runner, invocation)
    verification = runner._parent_gate_verifier.attest(
        invocation, gate_id="gate-capture", passed=True, detail="verified"
    )
    malformed_verification = replace(verification, **{field: malformed})

    with pytest.raises(RunnerError, match="lineage|verification|invalid"):
        runner.record_gate(invocation, verification=malformed_verification)
    assert not (runner._record_dir(invocation) / "gate.json").exists()


def test_stale_input_block_persistence_failure_is_not_swallowed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    input_path = _input(tmp_path)
    runner = PlanningRunner(tmp_path, "run-1")
    invocation = runner.begin(
        PlanningStage.CAPTURE,
        role="intent-capture",
        input_paths=(input_path,),
        output_path=".intent/intent.json",
    )
    original_insert_block = runner._insert_block
    failed_once = False

    def fail_once(connection: sqlite3.Connection, target: object, reason: str, detail: str) -> None:
        nonlocal failed_once
        if not failed_once:
            failed_once = True
            raise OSError("injected block failure")
        original_insert_block(connection, target, reason, detail)  # type: ignore[arg-type]

    monkeypatch.setattr(runner, "_insert_block", fail_once)
    input_path.write_text("changed", encoding="utf-8")

    with pytest.raises(RunnerBlocked, match="invalid|stale"):
        runner._parent_gate_verifier.attest(
            invocation, gate_id="gate-capture", passed=True, detail="verified"
        )
    assert runner.status().blocked is True


def test_current_invocation_projection_tamper_durably_blocks_result_recording(
    tmp_path: Path,
) -> None:
    input_path = _input(tmp_path)
    runner = PlanningRunner(tmp_path, "run-1")
    invocation = runner.begin(
        PlanningStage.CAPTURE,
        role="intent-capture",
        input_paths=(input_path,),
        output_path=".intent/intent.json",
    )
    stored = json.loads((runner._record_dir(invocation) / "invocation.json").read_text())
    stored["role"] = "forged-role"
    (runner._record_dir(invocation) / "invocation.json").write_text(json.dumps(stored) + "\n")

    with pytest.raises(RunnerBlocked, match="evidence|invalid|projection"):
        runner.record_result(invocation, {"ok": True, "payload": {}})
    assert runner.status().blocked is True


def test_explicit_recovery_uses_authoritative_store_when_all_projections_are_missing(
    tmp_path: Path,
) -> None:
    input_path = _input(tmp_path)
    runner = PlanningRunner(tmp_path, "run-1")
    runner.begin(
        PlanningStage.CAPTURE,
        role="intent-capture",
        input_paths=(input_path,),
        output_path=".intent/intent.json",
    )
    for path in (runner.events_path, runner.integrity_path, runner.state_path):
        path.unlink()

    recovered = PlanningRunner(tmp_path, "run-1", recover=True)
    assert recovered.status().blocked is True
    assert recovered.status().reason == "interrupted_attempt"


def test_malformed_invocation_stage_is_rejected_and_durably_blocks_advance(
    tmp_path: Path,
) -> None:
    input_path = _input(tmp_path)
    runner = PlanningRunner(tmp_path, "run-1")
    invocation = runner.begin(
        PlanningStage.CAPTURE,
        role="intent-capture",
        input_paths=(input_path,),
        output_path=".intent/intent.json",
    )
    malformed = replace(invocation, stage="capture")

    with pytest.raises(RunnerBlocked, match="invocation|invalid"):
        runner.advance(malformed)
    assert runner.status().blocked is True


def test_surrogate_gate_detail_is_bounded_and_durably_blocks(
    tmp_path: Path,
) -> None:
    input_path = _input(tmp_path)
    runner = PlanningRunner(tmp_path, "run-1")
    invocation = runner.begin(
        PlanningStage.CAPTURE,
        role="intent-capture",
        input_paths=(input_path,),
        output_path=".intent/intent.json",
    )
    runner.record_result(invocation, {"ok": True, "payload": {}})

    with pytest.raises(RunnerBlocked, match="gate|invalid"):
        runner._parent_gate_verifier.attest(
            invocation, gate_id="gate-capture", passed=True, detail="\ud800"
        )
    assert runner.status().blocked is True


def test_journal_writer_overflow_durably_blocks_before_projection_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    input_path = _input(tmp_path)
    runner = PlanningRunner(tmp_path, "run-1")
    invocation = runner.begin(
        PlanningStage.CAPTURE,
        role="intent-capture",
        input_paths=(input_path,),
        output_path=".intent/intent.json",
    )
    current_size = runner.events_path.stat().st_size
    monkeypatch.setattr(runner_module, "_MAX_WORKFLOW_JOURNAL_BYTES", current_size + 1)

    with pytest.raises(RunnerBlocked, match="evidence|mutation"):
        runner.record_result(invocation, {"ok": True, "payload": {}})
    assert runner.status().blocked is True


def test_projection_refresh_retries_when_store_generation_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    input_path = _input(tmp_path)
    runner = PlanningRunner(tmp_path, "run-1")
    invocation = runner.begin(
        PlanningStage.CAPTURE,
        role="intent-capture",
        input_paths=(input_path,),
        output_path=".intent/intent.json",
    )
    other = PlanningRunner(tmp_path, "run-1")
    original_write_json = runner._write_json
    mutation_started = False

    def write_json(path: Path, value: object, label: str) -> None:
        nonlocal mutation_started
        original_write_json(path, value, label)
        if label == "workflow integrity" and not mutation_started:
            mutation_started = True
            with other._writer_lock():
                with other._transaction() as connection:
                    other._insert_block(connection, invocation, "test_block", "concurrent update")

    monkeypatch.setattr(runner, "_write_json", write_json)
    runner._refresh_projections()

    events = [json.loads(line) for line in runner.events_path.read_text().splitlines()]
    assert events[-1]["action"] == "block"


def test_projection_cannot_authorize_or_replace_store_state(tmp_path: Path) -> None:
    input_path = _input(tmp_path)
    runner = PlanningRunner(tmp_path, "run-1")
    invocation = runner.begin(
        PlanningStage.CAPTURE,
        role="intent-capture",
        input_paths=(input_path,),
        output_path=".intent/intent.json",
    )

    runner.state_path.write_text(
        json.dumps(
            {
                "schema": 1,
                "run_id": "run-1",
                "current_stage": None,
                "blocked": False,
                "reason": None,
                "completed_stages": [stage.value for stage in PlanningStage],
                "attempts": {},
            }
        ),
        encoding="utf-8",
    )
    runner.events_path.write_text('{"projection":"forged"}\n', encoding="utf-8")

    with pytest.raises(RunnerError, match="projection|journal|JSON|event"):
        runner.status()
    with pytest.raises(RunnerBlocked, match="result|evidence"):
        runner.advance(invocation)


@pytest.mark.parametrize("tamper", ["nested-output", "gate-id"])
def test_persisted_gate_parser_rejects_spoofed_nested_evidence_and_gate_identity(
    tmp_path: Path, tamper: str
) -> None:
    input_path = _input(tmp_path)
    runner = PlanningRunner(tmp_path, "run-1")
    invocation = runner.begin(
        PlanningStage.CAPTURE,
        role="intent-capture",
        input_paths=(input_path,),
        output_path=".intent/intent.json",
    )
    runner.record_result(invocation, {"ok": True, "payload": {}})
    gate = _trusted_gate(runner, invocation)
    persisted = gate.to_dict()
    if tamper == "nested-output":
        persisted["evidence"] = {"nested": [{"output_path": "forged.json"}]}
        persisted["evidence_sha256"] = runner_module._gate_evidence_hash(
            gate.invocation_sha256,
            gate.result_sha256,
            gate.output_sha256,
            persisted["evidence"],
        )
    else:
        persisted["gate_id"] = "forged-gate"

    with pytest.raises(RunnerError, match="gate|evidence|output"):
        runner_module._gate_from_record(persisted, "run-1")


def test_second_runner_does_not_recover_another_runner_live_attempt(tmp_path: Path) -> None:
    input_path = _input(tmp_path)
    first = PlanningRunner(tmp_path, "run-1")
    invocation = first.begin(
        PlanningStage.CAPTURE,
        role="intent-capture",
        input_paths=(input_path,),
        output_path=".intent/intent.json",
    )

    second = PlanningRunner(tmp_path, "run-1")

    assert second.status().blocked is False
    first.record_result(invocation, {"ok": True, "payload": {}})


def test_begin_projection_failure_blocks_the_committed_attempt_and_allows_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    input_path = _input(tmp_path)
    runner = PlanningRunner(tmp_path, "run-1")

    def fail_refresh() -> None:
        raise OSError("injected projection failure")

    monkeypatch.setattr(runner, "_refresh_projections", fail_refresh)
    with pytest.raises(RunnerBlocked):
        runner.begin(
            PlanningStage.CAPTURE,
            role="intent-capture",
            input_paths=(input_path,),
            output_path=".intent/intent.json",
        )

    reopened = PlanningRunner(tmp_path, "run-1")
    assert reopened.status().blocked is True
    retry = reopened.begin(
        PlanningStage.CAPTURE,
        role="intent-capture",
        input_paths=(input_path,),
        output_path=".intent/intent.json",
    )
    assert retry.attempt == 2


def test_mutation_failure_diagnostics_are_bounded_and_durable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    input_path = _input(tmp_path)
    runner = PlanningRunner(tmp_path, "run-1")

    def fail_refresh() -> None:
        raise OSError("é" * 20_000 + "\n\x00")

    monkeypatch.setattr(runner, "_refresh_projections", fail_refresh)
    with pytest.raises(RunnerBlocked):
        runner.begin(
            PlanningStage.CAPTURE,
            role="intent-capture",
            input_paths=(input_path,),
            output_path=".intent/intent.json",
        )

    with sqlite3.connect(runner.database_path) as connection:
        block = connection.execute(
            "SELECT detail FROM blocks WHERE run_id='run-1' ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
    assert block is not None
    assert len(block[0].encode("utf-8")) <= runner_module._MAX_TEXT_BYTES
    assert "\x00" not in block[0]


def test_recovery_blocks_on_an_unrecognized_stage_projection_file(tmp_path: Path) -> None:
    runner = PlanningRunner(tmp_path, "run-1")
    orphan = runner.run_dir / "stages" / "capture" / "r1" / "a1" / "unknown.json"
    orphan.parent.mkdir(parents=True, exist_ok=True)
    orphan.write_text("{}\n", encoding="utf-8")

    recovered = PlanningRunner(tmp_path, "run-1", recover=True)

    assert recovered.status().blocked is True
    assert recovered.status().reason == "orphan_record"


def test_status_rejects_real_stage_attempt_identity_without_coercion(
    tmp_path: Path,
) -> None:
    input_path = _input(tmp_path)
    runner = PlanningRunner(tmp_path, "run-1")
    runner.begin(
        PlanningStage.CAPTURE,
        role="intent-capture",
        input_paths=(input_path,),
        output_path=".intent/intent.json",
    )
    with runner._transaction() as connection:
        connection.execute("DROP TRIGGER stage_attempts_immutable_update")
        connection.execute(
            "UPDATE stage_attempts SET revision=? WHERE run_id=?",
            (1.5, runner.run_id),
        )

    with pytest.raises(RunnerError, match="revision|identity|store"):
        runner.status()


def test_record_gate_rejects_legacy_decision_fields_alongside_attestation(
    tmp_path: Path,
) -> None:
    input_path = _input(tmp_path)
    runner = PlanningRunner(tmp_path, "run-1")
    invocation = runner.begin(
        PlanningStage.CAPTURE,
        role="intent-capture",
        input_paths=(input_path,),
        output_path=".intent/intent.json",
    )
    runner.record_result(invocation, {"ok": True, "payload": {}})
    _parent_output(runner, invocation)
    verification = runner._parent_gate_verifier.attest(
        invocation, gate_id="gate-capture", passed=True, detail="verified"
    )

    with pytest.raises(RunnerBlocked, match="trusted|verification|caller"):
        runner.record_gate(invocation, verification=verification, passed=False)


def test_recovery_blocks_when_stage_projection_root_is_not_a_directory(
    tmp_path: Path,
) -> None:
    runner = PlanningRunner(tmp_path, "run-1")
    stages_dir = runner.run_dir / "stages"
    stages_dir.write_text("not a directory", encoding="utf-8")

    recovered = PlanningRunner(tmp_path, "run-1", recover=True)

    assert recovered.status().blocked is True
    assert recovered.status().reason == "orphan_record"
