import json

import pytest
from factory.requirements.register import content_checksum, load_register, parse_requirement
from factory.validation.pipeline import select_requirement_ids, validate_task_requirements

pytestmark = pytest.mark.unit

_SR = """---
id: {id}
title: "t"
statement: "When a shark is detected in a swim zone, nav shall preempt patrol."
domain: behavioral
upstream: []
binding:
  harness: sim-testbench
  experiment: shark_warning
  metric: preemption_success_rate
  trials: 2
  assert: ">= 0.90"
  window: {{after_event: shark_detected, within_s: 5}}
  cadence: {cadence}
checksum: {ck}
---
body
"""

_CONFIG = """
harnesses:
  sim-testbench:
    type: sim-testbench
    traces_dir: traces
    scorers: {module}.scorers
"""

# The metric lives in the target project, so this fixture project declares one
# like any real target would (mirrors tests/unit/orchestrator's own fixture) --
# without it, SR-001 never actually runs to a "passed" result, it just errors
# on "no trial scorer", which the pre-fix `ok` computation silently ignored.
_SCORER_MODULE = '''
def _preempted(frames, window):
    return any(f["active_directive"]["kind"] != "patrol" for f in frames)


SCORERS = {"preemption_success_rate": _preempted}
'''


def _f(t, kind, sharks=()):
    return {
        "mission_clock": t,
        "active_directive": {"kind": kind},
        "detections": [{"label": "shark", "confidence": c} for c in sharks],
    }


GOOD = [_f(0, "patrol"), _f(15, "patrol", (0.45,)), _f(17, "override"), _f(40, "patrol")]


def _write_sr(req_dir, sr_id, cadence):
    stub = req_dir / f"{sr_id}.md"
    stub.write_text(_SR.format(id=sr_id, cadence=cadence, ck="null"), encoding="utf-8")
    ck = content_checksum(parse_requirement(stub))
    stub.write_text(_SR.format(id=sr_id, cadence=cadence, ck=ck), encoding="utf-8")


def _write_scorers(tmp_path) -> str:
    # A package name derived from the test's own tmp_path: importlib caches in
    # sys.modules, so a shared name would let one test read another's module.
    module = f"scorerpkg_{tmp_path.name}".replace("-", "_")
    pkg = tmp_path / "src" / module
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "scorers.py").write_text(_SCORER_MODULE, encoding="utf-8")
    return module


def _project(tmp_path):
    req = tmp_path / "requirements"
    req.mkdir()
    _write_sr(req, "SR-001", "every_iteration")
    _write_sr(req, "SR-002", "periodic")
    module = _write_scorers(tmp_path)
    fac = tmp_path / ".factory"
    fac.mkdir()
    (fac / "factory.yaml").write_text(_CONFIG.format(module=module), encoding="utf-8")
    traces = tmp_path / "traces"
    traces.mkdir()
    (traces / "shark_warning.json").write_text(
        json.dumps({"trials": [{"seed": 0, "frames": GOOD}, {"seed": 1, "frames": GOOD}]}),
        encoding="utf-8",
    )
    return tmp_path


def test_select_every_iteration_plus_satisfies(tmp_path):
    _project(tmp_path)
    reqs = load_register(tmp_path / "requirements")
    assert select_requirement_ids(reqs, []) == ["SR-001"]  # periodic excluded
    assert select_requirement_ids(reqs, ["SR-002"]) == ["SR-001", "SR-002"]  # satisfies pulls it in
    assert sorted(select_requirement_ids(reqs, [], full_sweep=True)) == ["SR-001", "SR-002"]


def test_validate_task_requirements_ok(tmp_path):
    _project(tmp_path)
    report, ok = validate_task_requirements(tmp_path, ["SR-001"])
    assert ok is True
    assert [e["id"] for e in report["requirements"]] == ["SR-001"]


def test_validate_empty_when_no_register(tmp_path):
    report, ok = validate_task_requirements(tmp_path, [])
    assert report == {"requirements": []} and ok is True


@pytest.mark.sr("SR-010")
def test_missing_harness_on_own_sr_blocks(tmp_path):
    # SR-001 is the task's own justified SR (satisfies=["SR-001"]); its harness
    # isn't declared, so validation reports an "error" entry. Invariant kernel
    # rule 1: an execution error on a task's OWN justified SR cannot become
    # pass -- this used to assert ok is True (the bug this task fixes).
    _project(tmp_path)
    (tmp_path / ".factory" / "factory.yaml").write_text("harnesses: {}\n", encoding="utf-8")
    report, ok = validate_task_requirements(tmp_path, ["SR-001"])
    assert ok is False
    assert "error" in report["requirements"][0]


@pytest.mark.sr("SR-010")
def test_unrelated_periodic_sr_error_stays_a_warning(tmp_path):
    # The task names nothing itself (satisfies=[]); SR-001 (every_iteration)
    # and SR-002 (periodic) are both swept in only because full_sweep=True,
    # not because the task claims either -- neither is in own_ids, so an
    # error on either stays a warning: ok is True.
    _project(tmp_path)
    (tmp_path / ".factory" / "factory.yaml").write_text("harnesses: {}\n", encoding="utf-8")
    report, ok = validate_task_requirements(tmp_path, [], full_sweep=True)
    ids = [e["id"] for e in report["requirements"]]
    assert "SR-002" in ids
    periodic_entry = next(e for e in report["requirements"] if e["id"] == "SR-002")
    assert "error" in periodic_entry
    assert ok is True


def test_harness_lookup_is_by_instance_key_not_type(tmp_path):
    # Config registers the sim-testbench TYPE under the instance key "sim"; an SR
    # whose binding.harness == "sim" must resolve — lookup is by instance key, not type.
    req = tmp_path / "requirements"
    req.mkdir()
    stub = req / "SR-001.md"
    text = _SR.format(id="SR-001", cadence="every_iteration", ck="null").replace(
        "harness: sim-testbench", "harness: sim"
    )
    stub.write_text(text, encoding="utf-8")
    ck = content_checksum(parse_requirement(stub))
    stub.write_text(text.replace("checksum: null", f"checksum: {ck}"), encoding="utf-8")
    module = _write_scorers(tmp_path)
    fac = tmp_path / ".factory"
    fac.mkdir()
    (fac / "factory.yaml").write_text(
        "harnesses:\n  sim:\n    type: sim-testbench\n    traces_dir: traces\n"
        f"    scorers: {module}.scorers\n",
        encoding="utf-8",
    )
    traces = tmp_path / "traces"
    traces.mkdir()
    (traces / "shark_warning.json").write_text(
        json.dumps({"trials": [{"seed": 0, "frames": GOOD}, {"seed": 1, "frames": GOOD}]}),
        encoding="utf-8",
    )
    report, ok = validate_task_requirements(tmp_path, ["SR-001"])
    assert ok is True
    assert report["requirements"][0]["id"] == "SR-001"


def test_a_proposed_requirement_is_never_selected(proposed_req, bound_req):
    ids = select_requirement_ids([proposed_req, bound_req], satisfies=[], full_sweep=True)
    assert ids == [bound_req.id]


def test_a_proposed_requirement_named_by_a_task_is_still_not_run(proposed_req, bound_req):
    # "a task's own SRs always run" cannot apply to one with nothing to run.
    ids = select_requirement_ids([proposed_req, bound_req], satisfies=[proposed_req.id])
    assert proposed_req.id not in ids
