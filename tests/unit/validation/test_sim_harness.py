import json
from pathlib import Path

import pytest
from factory.requirements.register import Binding
from factory.validation.harness import HarnessResult
from factory.validation.sim_harness import SimTestbenchHarness, UnknownMetricError

pytestmark = pytest.mark.unit


def _f(t, kind, sharks=()):
    return {
        "mission_clock": t,
        "active_directive": {"kind": kind},
        "detections": [{"label": "shark", "confidence": c} for c in sharks],
    }


GOOD = [_f(0, "patrol"), _f(15, "patrol", (0.45,)), _f(17, "override", (0.8,)), _f(40, "patrol")]
BAD = [_f(0, "patrol"), _f(20, "patrol")]  # no trigger → fail


def _binding(**kw):
    base = dict(
        harness="sim-testbench",
        experiment="shark_warning",
        metric="preemption_success_rate",
        assert_expr=">= 0.90",
        trials=4,
        window={"after_event": "shark_detected", "within_s": 5},
    )
    base.update(kw)
    return Binding(**base)


def _write_trace(dir_: Path, name: str, trials: list[list[dict]]) -> None:
    (dir_ / f"{name}.json").write_text(
        json.dumps({"trials": [{"seed": i, "frames": fr} for i, fr in enumerate(trials)]}),
        encoding="utf-8",
    )


def test_all_good_passes(tmp_path):
    _write_trace(tmp_path, "shark_warning", [GOOD, GOOD, GOOD, GOOD])
    res = SimTestbenchHarness(tmp_path).run(_binding(), tmp_path)
    assert isinstance(res, HarnessResult)
    assert res.metric_value == 1.0
    assert res.passed is True
    assert len(res.trials) == 4
    assert all(t.passed for t in res.trials)


def test_below_threshold_fails(tmp_path):
    _write_trace(tmp_path, "shark_warning", [GOOD, GOOD, GOOD, BAD])  # 0.75
    res = SimTestbenchHarness(tmp_path).run(_binding(), tmp_path)
    assert res.metric_value == 0.75
    assert res.passed is False
    assert res.trials[3].passed is False


def test_unknown_metric_raises(tmp_path):
    _write_trace(tmp_path, "shark_warning", [GOOD])
    with pytest.raises(UnknownMetricError):
        SimTestbenchHarness(tmp_path).run(_binding(metric="mystery"), tmp_path)
