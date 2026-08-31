from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

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


def _complete(runner: PlanningRunner, stage: PlanningStage, input_path: Path) -> None:
    invocation = runner.begin(
        stage,
        role=f"{stage.value}-agent",
        input_paths=(input_path,),
        output_path=f".factory/planning/{runner.run_id}/{stage.value}.json",
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
    runner.run_dir.mkdir(parents=True, exist_ok=True)
    target = tmp_path / "events-copy.jsonl"
    target.write_text("", encoding="utf-8")
    try:
        runner.events_path.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are unavailable")

    with pytest.raises(RunnerError, match="journal|unsafe"):
        PlanningRunner(tmp_path, "run-1").status()


def _trusted_gate(
    runner: PlanningRunner,
    invocation: AgentInvocation,
    *,
    passed: bool = True,
    detail: str = "verified",
    evidence: dict[str, object] | None = None,
) -> GateRecord:
    verification = runner.parent_gate_verifier.attest(
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

    reopened = PlanningRunner(tmp_path, "run-1")
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

    reopened = PlanningRunner(tmp_path, "run-1")
    retry = reopened.begin(
        PlanningStage.CAPTURE,
        role="intent-capture",
        input_paths=(input_path,),
        output_path=".intent/intent.json",
    )
    assert (retry.revision, retry.attempt) == (1, 2)
