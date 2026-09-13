"""SR-034/SR-049 `coherence execution` host command surface (RED first).

The CLI is the *only* Python-owned host seam: Codex, Claude Code, Pi and a
direct terminal all read the same schema-1 `ExecutionProjection` /
`ExecutionHandoff` JSON. These tests assert the honest contract: unsafe
identifiers are refused, the projection is read-only, a pending human decision
is surfaced rather than answered, `starts_automatically` is always the literal
JSON `false`, and no command can mark a task complete on its own.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from coherence.execution.cli import main as execution_main
from coherence.execution.gate_plan import compile_gate_plan
from factory.orchestrator.execution import RunExecution
from factory.orchestrator.git_ops import FakeGitOps
from factory.orchestrator.types import NodeEvent, TaskResult

pytestmark = [pytest.mark.unit, pytest.mark.sr("SR-034")]

RUN_ID = "run-013"
TASK_ID = "T-013"
_WORKFLOW = "governed-execution/v1"


# -- fixtures / helpers -------------------------------------------------------


def gate_plan_fixture():
    return compile_gate_plan(
        workflow_version=_WORKFLOW,
        version="behavior-change@1",
        required_gates=("unit", "full"),
        preflight_policy="mandatory-only",
    )


def execution_fixture(root: Path) -> RunExecution:
    return RunExecution.create(root, RUN_ID, TASK_ID, "a" * 40, FakeGitOps(head="a" * 40))


def paused_run(root: Path) -> str:
    """A real run journal paused on a durable `needs_input` request."""
    execution = execution_fixture(root)
    plan = gate_plan_fixture()
    cursor = execution.open_task_cursor(TASK_ID, plan)
    _advanced, request = execution.open_human_decision_request(
        cursor, reason="the project fixer budget was exhausted"
    )
    return request["request_sha256"]


def completed_run(root: Path) -> None:
    """A real run journal whose canonical `handoff` stage is recorded."""
    execution = execution_fixture(root)
    plan = gate_plan_fixture()
    execution.open_task_cursor(TASK_ID, plan)
    for stage in ("contract-compiled", "handoff"):
        execution.record_stage(execution.begin_revision(stage), state="completed", data={})


def configured_repo(root: Path) -> Path:
    """A project that declares gates and the SR-034 project-wide fixer budget."""
    config = root / ".factory" / "factory.yaml"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(
        "gates:\n"
        '  unit:\n    - { cmd: "{python} -c pass" }\n'
        '  integration:\n    - { cmd: "{python} -c pass" }\n'
        '  full:\n    - { cmd: "{python} -c pass" }\n'
        "governed_execution:\n  max_fixer_iterations: 2\n",
        encoding="utf-8",
    )
    return root


def task_file(root: Path, task_id: str = TASK_ID) -> Path:
    path = root / "tasks" / f"{task_id.lower()}-governed-execution.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n"
        f"id: {task_id}\n"
        "title: Governed execution driver\n"
        "status: todo\n"
        "dod:\n  - both reviews reported\n"
        "---\n\nbody\n",
        encoding="utf-8",
    )
    return path


def completed_result(task_id: str = TASK_ID) -> TaskResult:
    return TaskResult(
        task_id,
        "Governed execution driver",
        "completed",
        3,
        [NodeEvent("handoff", "pass", 1, {"governed_execution": {"stage_id": "handoff"}})],
        True,
    )


def escalated_result(task_id: str = TASK_ID) -> TaskResult:
    return TaskResult(task_id, "Governed execution driver", "escalated", 1, [], False)


# -- Step 1: argument validation ---------------------------------------------


def test_execution_dispatch_requires_safe_run_and_task_ids(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert execution_main(["dispatch-task", "../escape", "--run-id", RUN_ID]) == 2
    assert "safe" in capsys.readouterr().err.lower()


def test_execution_dispatch_rejects_an_unsafe_run_id(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert execution_main(["dispatch-task", TASK_ID, "--run-id", "../escape"]) == 2
    assert "safe" in capsys.readouterr().err.lower()


def test_execution_legal_actions_rejects_an_unsafe_task_id(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert execution_main(["legal-actions", "--run-id", RUN_ID, "--task-id", "..", "--json"]) == 2
    assert "safe" in capsys.readouterr().err.lower()


def test_unknown_subcommand_is_invalid_input_not_a_crash() -> None:
    assert execution_main(["teleport", "--run-id", RUN_ID]) == 2


# -- Step 1: read-only projections -------------------------------------------


def test_execution_legal_actions_is_the_only_host_transition_projection(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert execution_main([
        "legal-actions",
        "--run-id", RUN_ID,
        "--task-id", TASK_ID,
        "--project-root", str(tmp_path),
        "--json",
    ]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema"] == 1
    assert payload["run_id"] == RUN_ID
    assert payload["task_id"] == TASK_ID
    assert payload["starts_automatically"] is False
    assert payload["state"] in {"ready", "needs_input", "completed", "escalated", "blocked"}
    assert isinstance(payload["legal_next_actions"], list)
    assert payload["denied_write_count"] == 0


def test_legal_actions_surfaces_the_pending_request_without_answering_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    request_sha256 = paused_run(tmp_path)
    before = (tmp_path / "sessions").rglob("journal.jsonl")
    journal_bytes = {path: path.read_bytes() for path in before}

    assert execution_main([
        "legal-actions",
        "--run-id", RUN_ID,
        "--task-id", TASK_ID,
        "--project-root", str(tmp_path),
        "--json",
    ]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["state"] == "needs_input"
    assert payload["legal_next_actions"] == ["resolve-human", "stream-progress"]
    assert payload["pending_request"]["request_sha256"] == request_sha256
    assert payload["pending_request"]["allowed_decisions"] == ["retry", "defer", "block"]
    # read-only: the projection never mutates the journal it read
    assert {path: path.read_bytes() for path in journal_bytes} == journal_bytes


def test_legal_actions_reports_a_completed_run_without_starting_anything(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    completed_run(tmp_path)

    assert execution_main([
        "legal-actions",
        "--run-id", RUN_ID,
        "--task-id", TASK_ID,
        "--project-root", str(tmp_path),
        "--json",
    ]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["state"] == "completed"
    assert payload["legal_next_actions"] == ["inspect-handoff", "stream-progress"]
    assert payload["starts_automatically"] is False


def test_legal_actions_refuses_a_run_whose_journal_is_another_task(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    paused_run(tmp_path)

    assert execution_main([
        "legal-actions",
        "--run-id", RUN_ID,
        "--task-id", "T-999",
        "--project-root", str(tmp_path),
        "--json",
    ]) == 1

    payload = json.loads(capsys.readouterr().out)
    assert payload["blocked"] is True
    assert payload["state"] == "blocked"
    assert payload["reason"] == "TASK_MISMATCH"


def test_execution_progress_returns_driver_events_verbatim(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    paused_run(tmp_path)

    assert execution_main([
        "stream-progress", RUN_ID, "--project-root", str(tmp_path), "--json",
    ]) == 0

    payload = json.loads(capsys.readouterr().out)
    journal = tmp_path / "sessions" / ".factory-runs" / "by-session" / RUN_ID / "journal.jsonl"
    expected = [json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines()]
    assert payload["run_id"] == RUN_ID
    assert payload["events"] == expected
    assert [event["sequence"] for event in payload["events"]] == sorted(
        event["sequence"] for event in payload["events"]
    )
    assert payload["starts_automatically"] is False


def test_stream_progress_on_an_unknown_run_is_an_empty_sequence_not_an_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert execution_main([
        "stream-progress", RUN_ID, "--project-root", str(tmp_path), "--json",
    ]) == 0
    assert json.loads(capsys.readouterr().out)["events"] == []


# -- Step 1: dispatch ---------------------------------------------------------


def test_completed_execution_handoff_cannot_auto_start_downstream_work(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    task_file(configured_repo(tmp_path))
    seen: list[dict] = []

    def _factory(**kw):
        seen.append(kw)
        return completed_result()

    assert execution_main(
        [
            "dispatch-task", TASK_ID,
            "--run-id", RUN_ID,
            "--project-root", str(tmp_path),
            "--json",
        ],
        driver_factory=_factory,
        git_ops=FakeGitOps(head="a" * 40),
    ) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["handoff"]["starts_automatically"] is False
    assert payload["handoff"]["outcome"] == "completed"
    assert payload["handoff"]["dod_met"] is True
    assert payload["handoff"]["denied_write_count"] == 0
    assert payload["result"]["outcome"] == "completed"
    assert seen[0]["task"].id == TASK_ID
    assert seen[0]["session_id"] == RUN_ID


def test_dispatch_of_an_escalated_result_reports_one_and_writes_no_handoff(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    task_file(configured_repo(tmp_path))

    assert execution_main(
        [
            "dispatch-task", TASK_ID,
            "--run-id", RUN_ID,
            "--project-root", str(tmp_path),
            "--json",
        ],
        driver_factory=lambda **kw: escalated_result(),
        git_ops=FakeGitOps(head="a" * 40),
    ) == 1

    payload = json.loads(capsys.readouterr().out)
    assert payload["handoff"] is None
    assert payload["result"]["outcome"] == "escalated"
    assert payload["starts_automatically"] is False


def test_dispatch_without_wired_collaborators_fails_closed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    task_file(tmp_path)

    assert execution_main([
        "dispatch-task", TASK_ID,
        "--run-id", RUN_ID,
        "--project-root", str(tmp_path),
        "--json",
    ]) == 1

    payload = json.loads(capsys.readouterr().out)
    assert payload["blocked"] is True
    assert payload["reason"] == "EXECUTION_WIRING_UNAVAILABLE"
    assert payload["starts_automatically"] is False


def test_dispatch_on_an_unconfigured_project_fails_closed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    task_file(tmp_path)  # no .factory/factory.yaml: no gates, no fixer budget

    assert execution_main(
        [
            "dispatch-task", TASK_ID,
            "--run-id", RUN_ID,
            "--project-root", str(tmp_path),
            "--json",
        ],
        driver_factory=lambda **kw: completed_result(),
    ) == 1

    payload = json.loads(capsys.readouterr().out)
    assert payload["reason"] == "PROJECT_NOT_CONFIGURED"
    assert payload["starts_automatically"] is False


def test_dispatch_refuses_a_task_the_ledger_does_not_have(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    task_file(tmp_path)

    assert execution_main(
        [
            "dispatch-task", "T-404",
            "--run-id", RUN_ID,
            "--project-root", str(tmp_path),
            "--json",
        ],
        driver_factory=lambda **kw: completed_result("T-404"),
    ) == 1

    payload = json.loads(capsys.readouterr().out)
    assert payload["reason"] == "TASK_NOT_FOUND"


def test_dispatch_refuses_to_run_over_a_pending_human_decision(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    task_file(tmp_path)
    paused_run(tmp_path)
    dispatched: list[dict] = []

    assert execution_main(
        [
            "dispatch-task", TASK_ID,
            "--run-id", RUN_ID,
            "--project-root", str(tmp_path),
            "--json",
        ],
        driver_factory=lambda **kw: dispatched.append(kw) or completed_result(),
    ) == 1

    payload = json.loads(capsys.readouterr().out)
    assert payload["reason"] == "NEEDS_INPUT"
    assert dispatched == []


# -- Step 1: resolve-human ----------------------------------------------------


def _resolve_argv(root: Path, request_sha256: str, decision: str, **extra: str) -> list[str]:
    argv = [
        "resolve-human",
        "--run-id", RUN_ID,
        "--task-id", TASK_ID,
        "--request-sha256", request_sha256,
        "--decision-id", extra.get("decision_id", _expected_decision_id(decision)),
        "--decision", decision,
        "--response", extra.get("response", "human says so"),
        "--decided-by", extra.get("decided_by", "human"),
        "--project-root", str(root),
        "--json",
    ]
    return argv


def _expected_decision_id(decision: str) -> str:
    return f"{RUN_ID}/{TASK_ID}/contract-compiled/r1/a1/request/{decision}"


def test_resolve_human_refuses_a_non_human_writer(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    request_sha256 = paused_run(tmp_path)

    assert execution_main(
        _resolve_argv(tmp_path, request_sha256, "block", decided_by="agent"),
        git_ops=FakeGitOps(head="a" * 40),
    ) == 2
    assert "human" in capsys.readouterr().err.lower()


def test_resolve_human_block_records_one_decision_and_stays_escalated(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    request_sha256 = paused_run(tmp_path)

    assert execution_main(
        _resolve_argv(tmp_path, request_sha256, "block"),
        git_ops=FakeGitOps(head="a" * 40),
    ) == 1

    payload = json.loads(capsys.readouterr().out)
    assert payload["decision"] == "block"
    assert payload["replayed"] is False
    assert payload["projection"]["state"] == "blocked"
    assert payload["projection"]["starts_automatically"] is False
    journal = tmp_path / "sessions" / ".factory-runs" / "by-session" / RUN_ID / "journal.jsonl"
    decisions = [
        line for line in journal.read_text(encoding="utf-8").splitlines()
        if '"human_decision"' in line
    ]
    assert len(decisions) == 1


def test_resolve_human_defer_writes_the_existing_deferral(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    task_path = task_file(tmp_path)
    request_sha256 = paused_run(tmp_path)

    assert execution_main(
        _resolve_argv(tmp_path, request_sha256, "defer", response="defer to next cycle"),
        git_ops=FakeGitOps(head="a" * 40),
    ) == 1

    payload = json.loads(capsys.readouterr().out)
    assert payload["decision"] == "defer"
    assert payload["projection"]["state"] == "escalated"
    assert "defer to next cycle" in task_path.read_text(encoding="utf-8")


def test_defer_without_a_ledger_task_appends_no_decision(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    request_sha256 = paused_run(tmp_path)  # no tasks/ directory at all
    journal = tmp_path / "sessions" / ".factory-runs" / "by-session" / RUN_ID / "journal.jsonl"
    before = journal.read_bytes()

    assert execution_main(
        _resolve_argv(tmp_path, request_sha256, "defer"), git_ops=FakeGitOps(head="a" * 40)
    ) == 1

    payload = json.loads(capsys.readouterr().out)
    assert payload["reason"] == "TASK_NOT_FOUND"
    # A Deferral with nowhere to land must not leave a consumed request behind.
    assert journal.read_bytes() == before


def test_an_identical_decision_replay_appends_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    request_sha256 = paused_run(tmp_path)
    argv = _resolve_argv(tmp_path, request_sha256, "block")
    assert execution_main(argv, git_ops=FakeGitOps(head="a" * 40)) == 1
    journal = tmp_path / "sessions" / ".factory-runs" / "by-session" / RUN_ID / "journal.jsonl"
    after_first = journal.read_bytes()
    capsys.readouterr()

    assert execution_main(argv, git_ops=FakeGitOps(head="a" * 40)) == 1

    payload = json.loads(capsys.readouterr().out)
    assert payload["replayed"] is True
    assert journal.read_bytes() == after_first


def test_a_conflicting_decision_for_the_same_request_is_rejected(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    request_sha256 = paused_run(tmp_path)
    assert execution_main(
        _resolve_argv(tmp_path, request_sha256, "block"), git_ops=FakeGitOps(head="a" * 40)
    ) == 1
    journal = tmp_path / "sessions" / ".factory-runs" / "by-session" / RUN_ID / "journal.jsonl"
    after_first = journal.read_bytes()
    capsys.readouterr()

    assert execution_main(
        _resolve_argv(tmp_path, request_sha256, "defer"), git_ops=FakeGitOps(head="a" * 40)
    ) == 1

    payload = json.loads(capsys.readouterr().out)
    assert payload["blocked"] is True
    assert payload["reason"] == "DECISION_REJECTED"
    assert journal.read_bytes() == after_first


def test_a_stale_request_hash_is_rejected(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    paused_run(tmp_path)

    assert execution_main(
        _resolve_argv(tmp_path, "b" * 64, "block"), git_ops=FakeGitOps(head="a" * 40)
    ) == 1

    payload = json.loads(capsys.readouterr().out)
    assert payload["reason"] == "DECISION_REJECTED"


def test_a_mismatched_decision_id_is_rejected_before_anything_is_written(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    request_sha256 = paused_run(tmp_path)
    journal = tmp_path / "sessions" / ".factory-runs" / "by-session" / RUN_ID / "journal.jsonl"
    before = journal.read_bytes()

    assert execution_main(
        _resolve_argv(tmp_path, request_sha256, "block", decision_id="someone-elses-decision"),
        git_ops=FakeGitOps(head="a" * 40),
    ) == 1

    payload = json.loads(capsys.readouterr().out)
    assert payload["reason"] == "DECISION_ID_MISMATCH"
    assert journal.read_bytes() == before


def test_resolve_human_retry_without_wired_collaborators_keeps_the_request_pending(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    task_file(tmp_path)
    request_sha256 = paused_run(tmp_path)
    journal = tmp_path / "sessions" / ".factory-runs" / "by-session" / RUN_ID / "journal.jsonl"
    before = journal.read_bytes()

    assert execution_main(
        _resolve_argv(tmp_path, request_sha256, "retry"), git_ops=FakeGitOps(head="a" * 40)
    ) == 1

    payload = json.loads(capsys.readouterr().out)
    assert payload["reason"] == "EXECUTION_WIRING_UNAVAILABLE"
    # Fail closed: an unrunnable retry never consumes the human's request.
    assert journal.read_bytes() == before


def test_resolve_human_retry_invokes_the_resume_entrypoint(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    task_file(configured_repo(tmp_path))
    request_sha256 = paused_run(tmp_path)
    seen: list[dict] = []

    def _factory(**kw):
        seen.append(kw)
        return completed_result()

    assert execution_main(
        _resolve_argv(tmp_path, request_sha256, "retry", response="one more attempt"),
        driver_factory=_factory,
        git_ops=FakeGitOps(head="a" * 40),
    ) == 0

    payload = json.loads(capsys.readouterr().out)
    assert seen[0]["request_sha256"] == request_sha256
    assert seen[0]["decision"] == "retry"
    assert seen[0]["response"] == "one more attempt"
    assert seen[0]["decided_by"] == "human"
    assert payload["result"]["outcome"] == "completed"
    assert payload["handoff"]["starts_automatically"] is False


# -- Step 1: worker results ---------------------------------------------------


def test_report_worker_result_appends_evidence_and_never_completes_a_task(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    execution_fixture(tmp_path)

    assert execution_main(
        [
            "report-worker-result",
            "--run-id", RUN_ID,
            "--task-id", TASK_ID,
            "--lane", "review-spec",
            "--result", "fail",
            "--detail", "two findings",
            "--denied-writes", "3",
            "--project-root", str(tmp_path),
            "--json",
        ],
        git_ops=FakeGitOps(head="a" * 40),
    ) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["recorded"]["lane"] == "review-spec"
    assert payload["recorded"]["result"] == "fail"
    assert payload["projection"]["state"] != "completed"
    assert payload["projection"]["denied_write_count"] == 3
    assert payload["starts_automatically"] is False


def test_report_worker_result_rejects_an_unknown_result_vocabulary(
    tmp_path: Path,
) -> None:
    execution_fixture(tmp_path)

    assert execution_main([
        "report-worker-result",
        "--run-id", RUN_ID,
        "--task-id", TASK_ID,
        "--lane", "review-spec",
        "--result", "completed",
        "--detail", "nice try",
        "--project-root", str(tmp_path),
        "--json",
    ]) == 2


def test_denied_writes_are_visibility_only_and_never_block_a_transition(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    execution_fixture(tmp_path)
    assert execution_main(
        [
            "report-worker-result",
            "--run-id", RUN_ID,
            "--task-id", TASK_ID,
            "--lane", "dev",
            "--result", "pass",
            "--detail", "denied one out-of-worktree write",
            "--denied-writes", "1",
            "--project-root", str(tmp_path),
            "--json",
        ],
        git_ops=FakeGitOps(head="a" * 40),
    ) == 0
    capsys.readouterr()

    assert execution_main([
        "legal-actions",
        "--run-id", RUN_ID,
        "--task-id", TASK_ID,
        "--project-root", str(tmp_path),
        "--json",
    ]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["denied_write_count"] == 1
    assert payload["state"] == "ready"
    assert payload["blocked"] is False
    assert "dispatch-task" in payload["legal_next_actions"]


# -- Step 1: human-only flaky registration ------------------------------------


def test_flaky_register_is_human_only(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert execution_main([
        "flaky-register", "tests/test_x.py::test_a",
        "--reason", "network timing",
        "--decided-by", "driver",
        "--project-root", str(tmp_path),
        "--json",
    ]) == 2
    assert "human" in capsys.readouterr().err.lower()
    assert not (tmp_path / "flaky-tests").exists()


def test_flaky_register_writes_the_human_curated_record(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert execution_main([
        "flaky-register", "tests/test_x.py::test_a",
        "--reason", "network timing",
        "--decided-by", "human",
        "--project-root", str(tmp_path),
        "--json",
    ]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["record"]["test_id"] == "tests/test_x.py::test_a"
    assert payload["record"]["decided_by"] == "human"
    written = json.loads(
        (tmp_path / "flaky-tests" / "tests-test-x-py-test-a.json").read_text(encoding="utf-8")
    )
    assert written["reason"] == "network timing"


# -- Step 2: the shared serializers ------------------------------------------


def test_every_projection_and_handoff_emits_a_literal_json_false(tmp_path: Path) -> None:
    from coherence.execution.cli import ExecutionHandoff, ExecutionProjection

    projection = ExecutionProjection(run_id=RUN_ID, task_id=TASK_ID, state="ready")
    handoff = ExecutionHandoff(
        run_id=RUN_ID, task_id=TASK_ID, outcome="completed", dod_met=True, summary="done"
    )

    for payload in (projection.to_dict(), handoff.to_dict()):
        assert payload["schema"] == 1
        assert payload["starts_automatically"] is False
        assert '"starts_automatically": false' in json.dumps(payload, indent=2)
        assert payload["denied_write_count"] == 0


def test_a_truthy_starts_automatically_cannot_be_constructed() -> None:
    from coherence.execution.cli import ExecutionHandoff, ExecutionProjection

    with pytest.raises(ValueError):
        ExecutionProjection(
            run_id=RUN_ID, task_id=TASK_ID, state="ready", starts_automatically=True  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError):
        ExecutionHandoff(
            run_id=RUN_ID,
            task_id=TASK_ID,
            outcome="completed",
            dod_met=True,
            summary="done",
            starts_automatically=True,  # type: ignore[arg-type]
        )


def test_the_execution_group_is_registered_on_the_coherence_cli() -> None:
    from coherence.cli import GROUPS

    assert GROUPS["execution"] is execution_main


# -- Step 3: the checked-in host parity fixture -------------------------------


PARITY_FIXTURE = (
    Path(__file__).resolve().parents[2] / "fixtures" / "execution_legal_actions_parity.json"
)


def test_legal_actions_json_is_byte_identical_to_the_checked_in_host_expectation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The one right-hand side the Pi adapter parity test compares against."""
    assert execution_main([
        "legal-actions",
        "--run-id", "feat013-parity",
        "--task-id", "T-013",
        "--project-root", str(tmp_path),
        "--json",
    ]) == 0

    produced = capsys.readouterr().out
    (tmp_path / "produced.json").write_text(produced, encoding="utf-8")
    assert produced == PARITY_FIXTURE.read_text(encoding="utf-8")
