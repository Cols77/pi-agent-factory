import json

import pytest
from factory.requirements.register import content_checksum, parse_requirement
from factory.validation.cli import cmd_validate, main

pytestmark = pytest.mark.unit

_SR = """---
id: SR-001
title: t
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


def _project(tmp_path):
    req = tmp_path / "requirements"
    req.mkdir()
    stub = req / "SR-001.md"
    stub.write_text(_SR.format(ck="null"), encoding="utf-8")
    ck = content_checksum(parse_requirement(stub))
    stub.write_text(_SR.format(ck=ck), encoding="utf-8")
    (tmp_path / ".factory").mkdir()
    (tmp_path / ".factory" / "factory.yaml").write_text(
        "harnesses:\n  sim-testbench:\n    type: sim-testbench\n    traces_dir: traces\n",
        encoding="utf-8",
    )
    traces = tmp_path / "traces"
    traces.mkdir()
    (traces / "shark_warning.json").write_text(
        json.dumps({"trials": [{"seed": 0, "frames": GOOD}, {"seed": 1, "frames": GOOD}]}),
        encoding="utf-8",
    )
    return tmp_path


def test_cmd_validate_all_writes_report(tmp_path):
    _project(tmp_path)
    report, ok = cmd_validate(tmp_path, full_sweep=True)
    assert ok is True
    assert [e["id"] for e in report["requirements"]] == ["SR-001"]
    on_disk = json.loads(
        (tmp_path / "validation" / "validation-report.json").read_text(encoding="utf-8")
    )
    assert on_disk == report


def test_main_returns_exit_code(tmp_path, capsys):
    _project(tmp_path)
    rc = main(["run", "--project-root", str(tmp_path), "--all"])
    assert rc == 0
    assert "SR-001" in capsys.readouterr().out
