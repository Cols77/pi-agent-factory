from __future__ import annotations

import pytest

from factory.requirements.register import Binding
from factory.validation.sim_harness import (
    UNIT_PASS_RATE,
    SimTestbenchHarness,
    UnknownMetricError,
)

pytestmark = pytest.mark.unit


def _binding(experiment: str, metric: str, assert_expr: str = "== 1.0", trials: int = 1) -> Binding:
    return Binding(
        experiment=experiment,
        metric=metric,
        assert_expr=assert_expr,
        harness="sim-testbench",
        trials=trials,
    )


def _write_project(root: pytest.TempPathFactory, src: str) -> None:
    (root / "tests").mkdir(parents=True, exist_ok=True)
    (root / "tests" / "test_contract.py").write_text(src, encoding="utf-8")


_PASSING = """\
import pytest
pytestmark = pytest.mark.unit

def test_sr_contract_a():
    assert True

def test_sr_contract_b():
    assert True
"""


def test_pytest_source_reports_a_pass(tmp_path):
    _write_project(tmp_path, _PASSING)
    harness = SimTestbenchHarness(tmp_path / "traces", {})
    result = harness.run(
        _binding("tests", UNIT_PASS_RATE, trials=2), tmp_path
    )
    assert result.metric_value == 1.0
    assert result.passed is True
    assert len(result.trials) == 2
    assert all(t.passed for t in result.trials)


def test_pytest_source_reports_a_failure(tmp_path):
    _write_project(
        tmp_path,
        "import pytest\npytestmark = pytest.mark.unit\n"
        "def test_ok():\n    assert True\n"
        "def test_bad():\n    assert False\n",
    )
    harness = SimTestbenchHarness(tmp_path / "traces", {})
    result = harness.run(_binding("tests", UNIT_PASS_RATE, trials=2), tmp_path)
    assert result.metric_value == 0.5
    assert result.passed is False
    assert len(result.trials) == 2
    assert [t.passed for t in result.trials] == [True, False]


def test_pytest_source_treats_collection_failure_as_non_pass(tmp_path):
    # A selection that collects no tests must not read as a pass (or a 1.0).
    _write_project(tmp_path, "import pytest\npytestmark = pytest.mark.unit\n# no tests\n")
    harness = SimTestbenchHarness(tmp_path / "traces", {})
    result = harness.run(_binding("tests", UNIT_PASS_RATE, trials=1), tmp_path)
    assert result.passed is False
    assert result.metric_value == 0.0
    assert result.trials == []


def test_pytest_source_keeps_junit_xml_artifact(tmp_path):
    _write_project(tmp_path, _PASSING)
    harness = SimTestbenchHarness(tmp_path / "traces", {})
    result = harness.run(_binding("tests", UNIT_PASS_RATE, trials=2), tmp_path)
    assert len(result.artifacts) == 1
    assert result.artifacts[0].exists()
    assert result.artifacts[0].suffix == ".xml"


def test_pytest_source_requires_the_reserved_metric(tmp_path):
    # A product (frame) metric cannot be scored from a pytest selection.
    _write_project(tmp_path, _PASSING)
    harness = SimTestbenchHarness(tmp_path / "traces", {})
    with pytest.raises(UnknownMetricError):
        harness.run(_binding("tests", "preemption_success_rate", trials=2), tmp_path)


def test_frame_trace_source_still_works_when_fixture_exists(tmp_path):
    # Resolution stays backward compatible: a real trace JSON takes the frames
    # path and the product scorer path is unchanged.
    traces = tmp_path / "traces"
    traces.mkdir(exist_ok=True)
    (traces / "shark_warning.json").write_text(
        '{"trials":[{"seed":0,"frames":[{"mission_clock":0,'
        '"active_directive":{"kind":"patrol"},"detections":[]}]}]}',
        encoding="utf-8",
    )

    def always_patrol(frames, window):
        return True

    harness = SimTestbenchHarness(traces, {"patrol_rate": always_patrol})
    result = harness.run(
        _binding("shark_warning", "patrol_rate", trials=1), tmp_path
    )
    assert result.metric_value == 1.0
    assert result.passed is True
    assert result.raw["trace"] == str(traces / "shark_warning.json")
    assert result.artifacts == []


def test_unknown_frame_metric_still_raises(tmp_path):
    traces = tmp_path / "traces"
    traces.mkdir(exist_ok=True)
    (traces / "x.json").write_text('{"trials":[]}', encoding="utf-8")
    harness = SimTestbenchHarness(traces, {})
    with pytest.raises(UnknownMetricError):
        harness.run(_binding("x", "nope", trials=1), tmp_path)