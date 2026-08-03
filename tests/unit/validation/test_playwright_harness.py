import json
from pathlib import Path

import pytest

import factory.validation.playwright_harness as pw_harness
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


def test_subprocess_runner_builds_expected_argv_and_env(tmp_path, monkeypatch):
    captured = {}

    def fake_run(cmd, cwd=None, env=None, check=None, stdout=None, stderr=None,
                 shell=None, timeout=None):
        captured["cmd"] = cmd
        captured["cwd"] = cwd
        captured["env"] = env
        captured["check"] = check
        captured["shell"] = shell
        captured["timeout"] = timeout

        class _Result:
            returncode = 0

        return _Result()

    monkeypatch.setattr(pw_harness.subprocess, "run", fake_run)

    app_dir = tmp_path / "frontend"
    app_dir.mkdir()
    h = PlaywrightE2EHarness.from_config(
        {"app_dir": "frontend", "seed_env": "E2E_SEED"}, tmp_path
    )

    workdir = tmp_path / "trial-workdir"
    report_path = h._run_trial(0, "sign-in", workdir)

    expected_report = workdir / "pw-report-seed0.json"
    assert report_path == expected_report

    assert captured["env"]["E2E_SEED"] == "0"
    assert captured["env"]["PLAYWRIGHT_JSON_OUTPUT_NAME"] == str(expected_report)

    cmd = captured["cmd"]
    assert cmd[:3] == ["npx", "playwright", "test"]
    assert "sign-in" in cmd
    assert "--reporter=json" in cmd

    assert captured["cwd"] == str(app_dir)
    assert captured["check"] is False
    assert captured["shell"] is True
    assert captured["timeout"] == 600


def test_subprocess_runner_swallows_timeout_and_still_returns_report_path(tmp_path, monkeypatch):
    import subprocess as real_subprocess

    def fake_run_timeout(*args, **kwargs):
        raise real_subprocess.TimeoutExpired(cmd="npx playwright test", timeout=1)

    monkeypatch.setattr(pw_harness.subprocess, "run", fake_run_timeout)

    h = PlaywrightE2EHarness.from_config(
        {"app_dir": "frontend", "seed_env": "E2E_SEED", "timeout_s": 1}, tmp_path
    )
    workdir = tmp_path / "trial-workdir"
    report_path = h._run_trial(0, "sign-in", workdir)

    assert report_path == workdir / "pw-report-seed0.json"
