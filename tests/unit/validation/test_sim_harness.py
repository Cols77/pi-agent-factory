import json
from pathlib import Path

import pytest
from factory.requirements.register import Binding
from factory.validation.harness import HarnessResult
from factory.validation.sim_harness import SimTestbenchHarness, UnknownMetricError

pytestmark = pytest.mark.unit


def _scored(frames: list[dict], window: dict | None) -> bool:
    """Stand-in scorer. The factory owns no real metric; targets declare their own."""
    return any(f.get("ok") for f in frames)


SCORERS = {"demo_rate": _scored}

GOOD = [{"tick": 0}, {"tick": 1, "ok": True}]
BAD = [{"tick": 0}, {"tick": 1, "ok": False}]


def _binding(**kw):
    base = dict(
        harness="sim-testbench",
        experiment="demo_experiment",
        metric="demo_rate",
        assert_expr=">= 0.90",
        trials=4,
        window=None,
    )
    base.update(kw)
    return Binding(**base)


def _write_trace(dir_: Path, name: str, trials: list[list[dict]]) -> None:
    (dir_ / f"{name}.json").write_text(
        json.dumps({"trials": [{"seed": i, "frames": fr} for i, fr in enumerate(trials)]}),
        encoding="utf-8",
    )


def test_all_good_passes(tmp_path):
    _write_trace(tmp_path, "demo_experiment", [GOOD, GOOD, GOOD, GOOD])
    res = SimTestbenchHarness(tmp_path, SCORERS).run(_binding(), tmp_path)
    assert isinstance(res, HarnessResult)
    assert res.metric_value == 1.0
    assert res.passed is True
    assert len(res.trials) == 4
    assert all(t.passed for t in res.trials)


def test_below_threshold_fails(tmp_path):
    _write_trace(tmp_path, "demo_experiment", [GOOD, GOOD, GOOD, BAD])  # 0.75
    res = SimTestbenchHarness(tmp_path, SCORERS).run(_binding(), tmp_path)
    assert res.metric_value == 0.75
    assert res.passed is False
    assert res.trials[3].passed is False


def test_unknown_metric_raises(tmp_path):
    _write_trace(tmp_path, "demo_experiment", [GOOD])
    with pytest.raises(UnknownMetricError):
        SimTestbenchHarness(tmp_path, SCORERS).run(_binding(metric="mystery"), tmp_path)


def test_a_project_declaring_no_scorers_implements_nothing(tmp_path):
    _write_trace(tmp_path, "demo_experiment", [GOOD])
    harness = SimTestbenchHarness.from_config({"traces_dir": "."}, tmp_path)
    with pytest.raises(UnknownMetricError):
        harness.run(_binding(), tmp_path)
