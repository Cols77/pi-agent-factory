import json
from pathlib import Path

import pytest

from factory.requirements.register import Binding
from factory.validation.playwright_harness import PlaywrightE2EHarness, _spec_passed

pytestmark = pytest.mark.unit

FIX = Path(__file__).parent / "fixtures"


def _load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def test_spec_passed_true_when_matched_spec_ok():
    report = _load("pw-report-pass.json")
    assert _spec_passed(report, "sign-in") is True


def test_spec_passed_false_when_matched_spec_failed():
    report = _load("pw-report-fail.json")
    assert _spec_passed(report, "sign-in") is False


def test_spec_passed_false_when_no_spec_matches_experiment():
    report = _load("pw-report-pass.json")
    assert _spec_passed(report, "nonexistent-flow") is False


def _binding(trials, assert_expr="> 0.5"):
    return Binding(harness="playwright-e2e", experiment="sign-in",
                   metric="e2e_pass_rate", assert_expr=assert_expr, trials=trials)


def _fake_runner(seq):
    # seq: list of fixture names, one per seed
    calls = []
    def run_trial(seed, experiment, workdir):
        calls.append((seed, experiment))
        return FIX / seq[seed]
    run_trial.calls = calls
    return run_trial


def test_run_pass_rate_all_pass(tmp_path):
    h = PlaywrightE2EHarness(_fake_runner(["pw-report-pass.json"] * 3))
    res = h.run(_binding(3), tmp_path)
    assert res.metric_value == 1.0
    assert res.passed is True
    assert [t.seed for t in res.trials] == [0, 1, 2]


def test_run_pass_rate_mixed_and_assertion(tmp_path):
    seq = ["pw-report-pass.json", "pw-report-fail.json", "pw-report-pass.json"]
    h = PlaywrightE2EHarness(_fake_runner(seq))
    res = h.run(_binding(3, assert_expr=">= 0.9"), tmp_path)
    assert abs(res.metric_value - (2 / 3)) < 1e-9
    assert res.passed is False  # 0.666 < 0.9


def test_run_rejects_unsupported_metric(tmp_path):
    b = Binding(harness="playwright-e2e", experiment="sign-in",
                metric="preemption_success_rate", assert_expr="> 0.5", trials=1)
    h = PlaywrightE2EHarness(_fake_runner(["pw-report-pass.json"]))
    with pytest.raises(ValueError):
        h.run(b, tmp_path)


def test_from_config_builds_harness_with_defaults(tmp_path):
    h = PlaywrightE2EHarness.from_config({}, tmp_path)
    assert isinstance(h, PlaywrightE2EHarness)


def test_from_config_runner_is_callable(tmp_path):
    h = PlaywrightE2EHarness.from_config({"app_dir": "frontend", "seed_env": "E2E_SEED"}, tmp_path)
    # the injected runner is a 3-arg callable (seed, experiment, workdir)
    assert callable(h._run_trial)
