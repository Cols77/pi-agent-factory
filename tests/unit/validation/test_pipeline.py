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
"""


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


def _project(tmp_path):
    req = tmp_path / "requirements"
    req.mkdir()
    _write_sr(req, "SR-001", "every_iteration")
    _write_sr(req, "SR-002", "periodic")
    fac = tmp_path / ".factory"
    fac.mkdir()
    (fac / "factory.yaml").write_text(_CONFIG, encoding="utf-8")
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


def test_unknown_harness_makes_it_not_ok(tmp_path):
    _project(tmp_path)
    (tmp_path / ".factory" / "factory.yaml").write_text("harnesses: {}\n", encoding="utf-8")
    report, ok = validate_task_requirements(tmp_path, ["SR-001"])
    assert ok is False
    assert "error" in report["requirements"][0]
