"""Increment 7: unified long-run status model, store protocol, and transport.

Task 1 freezes the source-discriminated ``RunStatus`` model and the read-only
``RunSource`` protocol; the addendum introduces the internal ``RunStatusInput``
carrier and the canonical ``serialize_run_statuses`` transport. Service-side
assembly and the source adapters live in `test_run_adapters.py` / `service.py`.
"""
import pytest
from pathlib import Path

from coherence.runs.model import RunStatus, RunStatusInput
from coherence.runs.store import RunSource
from coherence.runs.transport import serialize_run_statuses
from substrate.artifacts import ArtifactRef
from substrate.observations import Diagnostic

pytestmark = pytest.mark.unit


def _artifact(ref: str = "artifact:a") -> ArtifactRef:
    return ArtifactRef(
        schema=1,
        kind="test",
        ref=ref,
        location="sessions/test.jsonl",
        content_hash="sha256:" + "0" * 64,
        scope_refs=(),
        media_type="application/json",
    )


def _status(**overrides) -> RunStatus:
    base = dict(
        producer="factory",
        run_id="run-1",
        state="passed",
        observation_ref="obs:factory:run-1",
    )
    base.update(overrides)
    return RunStatus(**base)


# -- model: producer/run/state/ref validation ---------------------------------


def test_reject_missing_producer():
    with pytest.raises(ValueError):
        _status(producer="")


def test_reject_missing_run_id():
    with pytest.raises(ValueError):
        _status(run_id="")


def test_reject_missing_observation_ref():
    with pytest.raises(ValueError):
        _status(observation_ref="")


def test_reject_state_outside_enum():
    with pytest.raises(ValueError):
        _status(state="suspended")


def test_reject_unknown_producer():
    with pytest.raises(ValueError):
        _status(producer="who-knows")


# -- model: artifact uniqueness -----------------------------------------------


def test_reject_duplicate_artifact_refs():
    with pytest.raises(ValueError):
        RunStatus(
            producer="factory",
            run_id="run-1",
            state="passed",
            observation_ref="obs:1",
            artifacts=(_artifact("artifact:a"), _artifact("artifact:a")),
        )


def test_artifact_refs_may_be_empty():
    status = _status(state="running")
    assert status.artifacts == ()


# -- model: frozen / non-mutating ---------------------------------------------


def test_model_is_frozen():
    status = _status()
    with pytest.raises(Exception):
        status.run_id = "mutated"  # type: ignore[misc]


def test_model_does_not_inspect_mtime_or_modify_tmp(tmp_path):
    src = tmp_path / "source.jsonl"
    src.write_text('{"x": 1}', encoding="utf-8")
    before = src.stat().st_mtime_ns
    _status()  # constructing a model must not read or write anything
    assert src.stat().st_mtime_ns == before


# -- RunStatusInput internal carrier ------------------------------------------


def test_run_status_input_carries_requirement_ids():
    inp = RunStatusInput(
        producer="simulation",
        run_id="sim-1",
        state="failed",
        observation_ref="obs:sim-1",
        requirement_ids=("SR-B", "SR-A"),
    )
    assert inp.requirement_ids == ("SR-B", "SR-A")


def test_run_status_input_nonblank_validation():
    with pytest.raises(ValueError):
        RunStatusInput(producer="factory", run_id="", state="passed", observation_ref="obs:1")


# -- store protocol ------------------------------------------------------------


class _DummySource:
    def iter_status_inputs(self) -> list[RunStatusInput]:
        return [
            RunStatusInput(
                producer="simulation",
                run_id="sim-1",
                state="failed",
                observation_ref="obs:sim-1",
                requirement_ids=("SR-B", "SR-A"),
            )
        ]


def test_run_source_is_runtime_checkable():
    assert isinstance(_DummySource(), RunSource)


def test_run_source_is_read_only_protocol():
    assert not hasattr(RunSource, "write")
    assert not hasattr(RunSource, "iter_status_inputs__set_name__")


# -- transport (Task 5) --------------------------------------------------------


def test_transport_omits_internal_carrier_and_emits_public_fields():
    payload = serialize_run_statuses(
        [
            RunStatus(
                producer="simulation",
                run_id="sim-1",
                state="failed",
                observation_ref="obs:sim-1",
                blocking_obligation="SR-001:verification_result",
                blocking_obligation_resolve_cmd=("c1", "c2"),
                rerun_allowed=True,
            )
        ]
    )
    row = payload["runs"][0]
    assert row["producer"] == "simulation"
    assert row["blocking_obligation"] == "SR-001:verification_result"
    assert row["blocking_obligation_resolve_cmd"] == ["c1", "c2"]
    assert row["rerun_allowed"] is True
    assert "requirement_ids" not in row
    assert row["resume_cmd"] is None  # emitted as null, never omitted


def test_transport_resume_cmd_null_when_missing():
    payload = serialize_run_statuses([_status(resume_cmd=None)])
    assert payload["runs"][0]["resume_cmd"] is None


def test_transport_preserves_resolve_cmd_as_array_not_string():
    payload = serialize_run_statuses(
        [
            RunStatus(
                producer="simulation",
                run_id="s",
                state="failed",
                observation_ref="obs:s",
                blocking_obligation_resolve_cmd=("python -m x", "--dry-run"),
            )
        ]
    )
    value = payload["runs"][0]["blocking_obligation_resolve_cmd"]
    assert isinstance(value, list)
    assert value == ["python -m x", "--dry-run"]


def test_transport_missing_diagnostics_default_empty():
    payload = serialize_run_statuses([_status()])
    assert payload["runs"][0]["diagnostics"] == []