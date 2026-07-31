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
    return {"mission_clock": t, "active_directive": {"kind": kind},
            "detections": [{"label": "shark", "confidence": c} for c in sharks]}


GOOD = [_f(0, "patrol"), _f(15, "patrol", (0.45,)), _f(17, "override"), _f(40, "patrol")]


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
    report = run_requirement_validation(
        ["SR-001"], reqs, default_harness_for(traces), tmp_path
    )
    entry = report["requirements"][0]
    assert entry["id"] == "SR-001"
    assert entry["value"] == 1.0
    assert entry["passed"] is True
    assert entry["trials"] == 2
    assert entry["stale"] is False


def test_unknown_requirement(tmp_path):
    req_dir, traces = _setup(tmp_path)
    reqs = load_register(req_dir)
    report = run_requirement_validation(["SR-404"], reqs, default_harness_for(traces), tmp_path)
    assert report["requirements"][0] == {"id": "SR-404", "error": "unknown requirement"}


def test_write_report_roundtrip(tmp_path):
    out = tmp_path / "sub" / "validation-report.json"
    write_validation_report(out, {"requirements": []})
    assert json.loads(out.read_text(encoding="utf-8")) == {"requirements": []}
