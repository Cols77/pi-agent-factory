from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import pytest

from coherence.planning.run import execute_parent_stage
from coherence.planning.runner import (
    AgentInvocation,
    AgentResultRecord,
    GateVerification,
    PlanningRunner,
    PlanningStage,
)

pytestmark = pytest.mark.unit


def test_execute_parent_stage_passes_a_bound_gate_verification_to_runner(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "input.txt"
    input_path.write_text("intent", encoding="utf-8")
    runner = PlanningRunner(tmp_path, "run-1")

    def invoke(invocation: AgentInvocation) -> Mapping[str, object]:
        output = runner.project_root / invocation.output_path
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text('{"captured":true}\n', encoding="utf-8")
        return {"ok": True, "payload": {"captured": True}}

    def gate(
        invocation: AgentInvocation, result: AgentResultRecord
    ) -> GateVerification:
        assert result.ok is True
        return runner._parent_gate_verifier.attest(
            invocation,
            gate_id="gate-capture",
            passed=True,
            detail="verified",
            evidence={"stage": "capture"},
        )

    next_stage = execute_parent_stage(
        runner,
        PlanningStage.CAPTURE,
        role="intent-capture",
        input_paths=(input_path,),
        output_path=".intent/intent.json",
        invoke=invoke,
        gate=gate,
    )

    assert next_stage is PlanningStage.PROVISIONAL_SPEC
    state = runner.status()
    assert state.blocked is False
    assert state.completed_stages == (PlanningStage.CAPTURE.value,)
