"""Increment 7: unified long-run status model, store protocol, and transport.

Task 1 freezes the source-discriminated ``RunStatus`` model and the read-only
``RunSource`` protocol; the addendum introduces the internal ``RunStatusInput``
carrier and the canonical ``serialize_run_statuses`` transport. Service-side
assembly and the source adapters live in `test_run_adapters.py` / `service.py`.
"""
import pytest
import json
from pathlib import Path

from coherence.runs.model import RunStatus, RunStatusInput
from coherence.runs.store import RunSource
from coherence.runs.transport import serialize_run_statuses
from substrate.artifacts import ArtifactRef

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


# -- service / Task 5: blocking obligation + rerun ----------------------------------


def _seed_dogfood_repo(root: Path) -> Path:
    """Seed a minimal repo with one high-assurance SR and a prototype default."""
    from substrate.policy.vocabulary import COMPILED_PRESETS  # noqa: F401

    root.mkdir(parents=True, exist_ok=True)
    (root / "requirements").mkdir(parents=True, exist_ok=True)
    (root / "docs" / "features").mkdir(parents=True, exist_ok=True)
    (root / "requirements" / "SR-DOGFOOD-001.md").write_text(
        "\n".join(
            [
                "---",
                "id: SR-DOGFOOD-001",
                "title: Dogfood high-criticality requirement",
                "statement: A seeded requirement used only to exercise the high_assurance obligation set.",
                "domain: dogfood",
                "binding:",
                "  experiment: dogfood-exp",
                "  metric: dogfood-metric",
                "  assert: 'dogfood-metric > 0'",
                "---",
                "",
                "Fixture only -- not a real product requirement.",
            ]
        ),
        encoding="utf-8",
    )
    (root / "docs" / "features" / "FEAT-DOGFOOD-HIGH-ASSURANCE.md").write_text(
        "\n".join(
            [
                "---",
                "id: FEAT-DOGFOOD-HIGH-ASSURANCE",
                "title: Dogfood high-assurance-profile feature",
                "requirements:",
                "  - SR-DOGFOOD-001",
                "profile: high_assurance",
                "---",
                "",
                "Seeded fixture for the Increment 7 service test.",
                "Fixture only -- not a real product feature.",
            ]
        ),
        encoding="utf-8",
    )
    return root


def _seed_sim_run(root: Path, run_id: str, requirements: list[str], result: str) -> None:
    (root / "evidence" / "runs" / run_id).mkdir(parents=True, exist_ok=True)
    (root / "evidence" / "runs" / run_id / "manifest.json").write_text(
        json.dumps(
            {
                "run": run_id,
                "experiment": "dogfood-exp",
                "feature": "FEAT-DOGFOOD-HIGH-ASSURANCE",
                "requirements": requirements,
                "goals": [],
                "commit": "abc",
                "result": result,
            }
        ),
        encoding="utf-8",
    )


def test_service_attaches_blocking_obligation_for_failed_high_assurance_run(tmp_path):
    from coherence.runs.service import list_run_statuses

    _seed_dogfood_repo(tmp_path)
    _seed_sim_run(tmp_path, "RUN-1", ["SR-DOGFOOD-001"], "failed")
    statuses = list_run_statuses(tmp_path)
    assert statuses
    run = next(s for s in statuses if s.producer == "simulation")
    # high_assurance SR has an open blocking verification_result obligation.
    assert run.blocking_obligation is not None
    assert "verification_result" in run.blocking_obligation
    assert run.blocking_obligation_resolve_cmd is not None


def test_service_no_blocking_obligation_when_prototype_only(tmp_path):
    from coherence.runs.service import list_run_statuses

    _seed_dogfood_repo(tmp_path)
    _seed_sim_run(tmp_path, "RUN-1", ["SR-OTHER-PROTOTYPE"], "failed")
    statuses = list_run_statuses(tmp_path)
    assert statuses
    run = next(s for s in statuses if s.producer == "simulation")
    assert run.blocking_obligation is None
    assert run.blocking_obligation_resolve_cmd is None
    assert run.rerun_allowed is False


def test_service_deterministic_first_winning_sr_when_many(tmp_path):
    from coherence.runs.service import list_run_statuses

    _seed_dogfood_repo(tmp_path)
    # Seed a second prototype SR; only SR-DOGFOOD-001 is high_assurance/blocking.
    _seed_sim_run(tmp_path, "RUN-1", ["SR-OTHER", "SR-DOGFOOD-001"], "failed")
    statuses = list_run_statuses(tmp_path)
    run = next(s for s in statuses if s.producer == "simulation")
    assert run.blocking_obligation is not None and "SR-DOGFOOD-001" in run.blocking_obligation


def test_service_rerun_allowed_with_all_prerequisites(tmp_path):
    from coherence.runs.service import list_run_statuses

    _seed_dogfood_repo(tmp_path)
    _seed_sim_run(tmp_path, "RUN-1", ["SR-DOGFOOD-001"], "failed")
    verdict_dir = tmp_path / "coverage-reviews" / "FEAT-DOGFOOD-HIGH-ASSURANCE-run1" / "verdicts"
    verdict_dir.mkdir(parents=True)
    (verdict_dir / "SR-DOGFOOD-001.json").write_text("{}", encoding="utf-8")
    verdict_files = {"SR-DOGFOOD-001": verdict_dir / "SR-DOGFOOD-001.json"}
    statuses = list_run_statuses(
        tmp_path,
        policy_bound=True,
        verdict_files=verdict_files,
        repeatable_policy={"SR-DOGFOOD-001": True},
        max_reruns=2,
        reruns_used=1,
    )
    run = next(s for s in statuses if s.producer == "simulation")
    assert run.rerun_allowed is True
    assert run.blocking_obligation_resolve_cmd is not None


def test_service_rerun_not_allowed_when_budget_exhausted(tmp_path):
    from coherence.runs.service import list_run_statuses

    _seed_dogfood_repo(tmp_path)
    _seed_sim_run(tmp_path, "RUN-1", ["SR-DOGFOOD-001"], "failed")
    verdict = tmp_path / "verdicts" / "SR-DOGFOOD-001.json"
    verdict.parent.mkdir(parents=True)
    verdict.write_text("{}", encoding="utf-8")
    statuses = list_run_statuses(
        tmp_path,
        policy_bound=True,
        verdict_files={"SR-DOGFOOD-001": verdict},
        repeatable_policy={"SR-DOGFOOD-001": True},
        max_reruns=2,
        reruns_used=2,  # exhausted
    )
    run = next(s for s in statuses if s.producer == "simulation")
    assert run.rerun_allowed is False


def test_service_rerun_not_allowed_when_max_reruns_zero(tmp_path):
    from coherence.runs.service import list_run_statuses

    _seed_dogfood_repo(tmp_path)
    _seed_sim_run(tmp_path, "RUN-1", ["SR-DOGFOOD-001"], "failed")
    verdict = tmp_path / "verdicts" / "SR-DOGFOOD-001.json"
    verdict.parent.mkdir(parents=True)
    verdict.write_text("{}", encoding="utf-8")
    statuses = list_run_statuses(tmp_path, policy_bound=True, verdict_files={"SR-DOGFOOD-001": verdict})
    run = next(s for s in statuses if s.producer == "simulation")
    assert run.rerun_allowed is False  # max_reruns defaults to 0


def test_service_rerun_not_allowed_when_not_policy_bound(tmp_path):
    from coherence.runs.service import list_run_statuses

    _seed_dogfood_repo(tmp_path)
    _seed_sim_run(tmp_path, "RUN-1", ["SR-DOGFOOD-001"], "failed")
    verdict = tmp_path / "verdicts" / "SR-DOGFOOD-001.json"
    verdict.parent.mkdir(parents=True)
    verdict.write_text("{}", encoding="utf-8")
    statuses = list_run_statuses(
        tmp_path,
        policy_bound=False,
        verdict_files={"SR-DOGFOOD-001": verdict},
        repeatable_policy={"SR-DOGFOOD-001": True},
        max_reruns=2,
    )
    run = next(s for s in statuses if s.producer == "simulation")
    assert run.rerun_allowed is False


def test_service_human_review_winner_never_reruns_even_with_all_prereqs(monkeypatch, tmp_path):
    from coherence.runs import service as runs_service
    from coherence.policy import compiler as policy_compiler

    _seed_dogfood_repo(tmp_path)

    class _Win:
        kind = "human_review"
        requiredness = "blocking"
        state = "open"
        scope_ref = "sr:SR-DOGFOOD-001"
        id = "ob:human_review:sr:SR-DOGFOOD-001"
        resolve_cmd = ("python -m audit run FEAT-DOGFOOD-HIGH-ASSURANCE",)

    def _fake_compile(root, scope_ref):
        return [_Win()]

    monkeypatch.setattr(policy_compiler, "compile_obligations", _fake_compile)
    verdict = tmp_path / "verdicts" / "SR-DOGFOOD-001.json"
    verdict.parent.mkdir(parents=True)
    verdict.write_text("{}", encoding="utf-8")
    blocking_id, resolve_cmd, rerun = runs_service._blocking_for(
        tmp_path,
        ("SR-DOGFOOD-001",),
        policy_bound=True,
        verdict_files={"SR-DOGFOOD-001": verdict},
        repeatable_policy={"SR-DOGFOOD-001": True},
        max_reruns=3,
        reruns_used=0,
    )
    assert blocking_id == _Win.id
    assert resolve_cmd == _Win.resolve_cmd
    assert rerun is False  # human_review needs a human decision, never auto-rerun


def test_service_never_raises_frozen_instance_error(tmp_path):
    from coherence.runs.service import list_run_statuses

    _seed_dogfood_repo(tmp_path)
    _seed_sim_run(tmp_path, "RUN-1", ["SR-DOGFOOD-001"], "failed")
    for _ in range(3):
        statuses = list_run_statuses(tmp_path)
        assert all(isinstance(r.blocking_obligation, (str, type(None))) for r in statuses)


def test_service_serialize_end_to_end_omits_carrier(tmp_path):
    from coherence.runs.service import list_run_statuses
    from coherence.runs.transport import serialize_run_statuses

    _seed_dogfood_repo(tmp_path)
    _seed_sim_run(tmp_path, "RUN-1", ["SR-B", "SR-A"], "failed")
    payload = serialize_run_statuses(list_run_statuses(tmp_path))
    sim = next(r for r in payload["runs"] if r["producer"] == "simulation")
    assert "blocking_obligation" in sim
    assert "blocking_obligation_resolve_cmd" in sim
    assert "rerun_allowed" in sim
    assert "requirement_ids" not in sim
    assert "resume_cmd" in sim