import json

import pytest
from factory.orchestrator.nodes import run_validation
from factory.orchestrator.types import NodeOutcome

pytestmark = pytest.mark.unit


class _Gates:
    def run(self, name):
        return 0  # all gates green


def _f(t, kind, sharks=()):
    return {
        "mission_clock": t,
        "active_directive": {"kind": kind},
        "detections": [{"label": "shark", "confidence": c} for c in sharks],
    }


GOOD = [_f(0, "patrol"), _f(15, "patrol", (0.45,)), _f(17, "override"), _f(40, "patrol")]
BAD = [_f(0, "patrol"), _f(20, "patrol")]  # no trigger → preemption fails

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

_CONFIG = "harnesses:\n  sim-testbench:\n    type: sim-testbench\n    traces_dir: traces\n"


def _project(tmp_path, trials):
    from factory.requirements.register import content_checksum, parse_requirement

    req = tmp_path / "requirements"
    req.mkdir()
    stub = req / "SR-001.md"
    stub.write_text(_SR.format(ck="null"), encoding="utf-8")
    ck = content_checksum(parse_requirement(stub))
    stub.write_text(_SR.format(ck=ck), encoding="utf-8")
    (tmp_path / ".factory").mkdir()
    (tmp_path / ".factory" / "factory.yaml").write_text(_CONFIG, encoding="utf-8")
    traces = tmp_path / "traces"
    traces.mkdir()
    (traces / "shark_warning.json").write_text(
        json.dumps({"trials": [{"seed": i, "frames": fr} for i, fr in enumerate(trials)]}),
        encoding="utf-8",
    )
    return tmp_path


def test_backward_compatible_without_repo_root():
    outcome, ev = run_validation(_Gates(), "T-1")
    assert outcome == NodeOutcome.PASS  # no requirement work when repo_root is None


def test_passes_when_sr_green(tmp_path):
    _project(tmp_path, [GOOD, GOOD])
    td = tmp_path / "td"
    td.mkdir()
    outcome, ev = run_validation(
        _Gates(), "T-1", repo_root=tmp_path, satisfies=["SR-001"], transcript_dir=td
    )
    assert outcome == NodeOutcome.PASS
    report = json.loads((td / "validation-report.json").read_text(encoding="utf-8"))
    assert report["requirements"][0]["passed"] is True


def test_fails_when_sr_red(tmp_path):
    _project(tmp_path, [GOOD, BAD])  # rate 0.5 < 0.90
    outcome, ev = run_validation(_Gates(), "T-1", repo_root=tmp_path, satisfies=["SR-001"])
    assert outcome == NodeOutcome.FAIL
    assert ev.extra["failed_requirements"] == ["SR-001"]
