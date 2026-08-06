import json

import pytest
from factory.requirements.register import content_checksum, load_register, parse_requirement
from factory.validation.report import (
    default_harness_for,
    run_requirement_validation,
    write_validation_report,
)

pytestmark = pytest.mark.unit

_SR = """---
id: SR-001
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
checksum: {ck}
---
body
"""


def _f(t, kind, sharks=()):
    return {
        "mission_clock": t,
        "active_directive": {"kind": kind},
        "detections": [{"label": "shark", "confidence": c} for c in sharks],
    }


GOOD = [_f(0, "patrol"), _f(15, "patrol", (0.45,)), _f(17, "override"), _f(40, "patrol")]


def _preempted(frames, window):
    """Local stand-in for the scorer the drone repo now owns."""
    return any(f["active_directive"]["kind"] != "patrol" for f in frames)


_SCORERS = {"preemption_success_rate": _preempted}


def _setup(tmp_path):
    req_dir = tmp_path / "requirements"
    req_dir.mkdir()
    stub = req_dir / "SR-001.md"
    stub.write_text(_SR.format(ck="null"), encoding="utf-8")
    ck = content_checksum(parse_requirement(stub))
    stub.write_text(_SR.format(ck=ck), encoding="utf-8")  # stamp current checksum
    traces = tmp_path / "traces"
    traces.mkdir()
    (traces / "shark_warning.json").write_text(
        json.dumps({"trials": [{"seed": 0, "frames": GOOD}, {"seed": 1, "frames": GOOD}]}),
        encoding="utf-8",
    )
    return req_dir, traces


def test_run_and_report(tmp_path):
    req_dir, traces = _setup(tmp_path)
    reqs = load_register(req_dir)
    report = run_requirement_validation(["SR-001"], reqs, default_harness_for(traces, _SCORERS), tmp_path)
    entry = report["requirements"][0]
    assert entry["id"] == "SR-001"
    assert entry["value"] == 1.0
    assert entry["passed"] is True
    assert entry["trials"] == 2
    assert entry["stale"] is False


def test_unknown_requirement(tmp_path):
    req_dir, traces = _setup(tmp_path)
    reqs = load_register(req_dir)
    report = run_requirement_validation(["SR-404"], reqs, default_harness_for(traces, _SCORERS), tmp_path)
    assert report["requirements"][0] == {"id": "SR-404", "error": "unknown requirement"}


def test_harness_failure_isolated(tmp_path):
    req_dir, traces = _setup(tmp_path)
    # A second requirement bound to a trace experiment that does not exist.
    stub = req_dir / "SR-002.md"
    stub.write_text(
        _SR.format(ck="null")
        .replace("SR-001", "SR-002")
        .replace("experiment: shark_warning", "experiment: does_not_exist"),
        encoding="utf-8",
    )
    reqs = load_register(req_dir)
    report = run_requirement_validation(
        ["SR-002", "SR-001"], reqs, default_harness_for(traces, _SCORERS), tmp_path
    )
    by_id = {e["id"]: e for e in report["requirements"]}
    assert "error" in by_id["SR-002"]  # missing trace isolated to SR-002
    assert by_id["SR-001"]["passed"] is True  # good requirement still processed


def test_write_report_roundtrip(tmp_path):
    out = tmp_path / "sub" / "validation-report.json"
    write_validation_report(out, {"requirements": []})
    assert json.loads(out.read_text(encoding="utf-8")) == {"requirements": []}


def test_report_flags_trials_shortfall(tmp_path):
    # SR declares trials: 5 but the fixture has only the 2 GOOD trials → not passed.
    req_dir = tmp_path / "requirements"
    req_dir.mkdir()
    stub = req_dir / "SR-001.md"
    text = _SR.format(ck="null").replace("trials: 2", "trials: 5")
    stub.write_text(text, encoding="utf-8")
    from factory.requirements.register import content_checksum, load_register, parse_requirement

    ck = content_checksum(parse_requirement(stub))
    stub.write_text(text.replace("checksum: null", f"checksum: {ck}"), encoding="utf-8")
    traces = tmp_path / "traces"
    traces.mkdir()
    (traces / "shark_warning.json").write_text(
        json.dumps({"trials": [{"seed": 0, "frames": GOOD}, {"seed": 1, "frames": GOOD}]}),
        encoding="utf-8",
    )
    reqs = load_register(req_dir)
    report = run_requirement_validation(["SR-001"], reqs, default_harness_for(traces, _SCORERS), tmp_path)
    entry = report["requirements"][0]
    assert entry["declared_trials"] == 5
    assert entry["trials"] == 2
    assert entry["passed"] is False  # metric passed but too few trials


def test_a_proposed_requirement_reports_an_error_not_a_crash(proposed_req, tmp_path):
    report = run_requirement_validation(
        [proposed_req.id], [proposed_req], lambda name: None, tmp_path
    )
    entry = report["requirements"][0]
    assert entry["id"] == proposed_req.id
    assert "proposed" in entry["error"]
    assert "passed" not in entry
