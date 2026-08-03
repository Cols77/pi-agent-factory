from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Callable, Iterator
from pathlib import Path

from factory.requirements.register import Binding
from factory.validation.assertions import evaluate_assertion
from factory.validation.harness import HarnessResult, TrialResult


def _iter_specs(report: dict) -> Iterator[dict]:
    """Flatten Playwright's nested suites -> spec objects.

    The JSON reporter emits {"suites": [{"file", "specs": [...], "suites": [...]}]}
    with arbitrary nesting. Each yielded spec carries its inherited "file" so
    callers can match on file OR title.
    """

    def walk(suite: dict, file_hint: str) -> Iterator[dict]:
        file = suite.get("file", file_hint)
        for spec in suite.get("specs", []):
            yield {**spec, "file": spec.get("file", file)}
        for child in suite.get("suites", []):
            yield from walk(child, file)

    for suite in report.get("suites", []):
        yield from walk(suite, "")


def _spec_passed(report: dict, experiment: str) -> bool:
    """True iff at least one spec matches *experiment* (substring of file or
    title) and every matched spec is ok. No match -> False (a requirement whose
    spec did not run is not silently 'passed')."""
    matched = [
        s
        for s in _iter_specs(report)
        if experiment in s.get("file", "") or experiment in s.get("title", "")
    ]
    if not matched:
        return False
    return all(bool(s.get("ok")) for s in matched)


# (seed, experiment, workdir) -> path to that trial's Playwright JSON report.
# Injected so aggregation is testable without invoking Playwright.
TrialRunner = Callable[[int, str, Path], Path]


def _subprocess_runner(
    app_dir: Path, seed_env: str, test_cmd: list[str], timeout_s: float = 600
) -> TrialRunner:
    def run_trial(seed: int, experiment: str, workdir: Path) -> Path:
        workdir.mkdir(parents=True, exist_ok=True)
        report_path = workdir / f"pw-report-seed{seed}.json"
        env = {
            **os.environ,
            seed_env: str(seed),
            "PLAYWRIGHT_JSON_OUTPUT_NAME": str(report_path),
        }
        # `experiment` is passed as Playwright's positional path filter, so it must
        # be a file-path substring (Playwright positional args filter by file, not
        # title) -- matches the naming convention the SR bindings will use.
        cmd_list = [*test_cmd, experiment, "--reporter=json"]
        # Platform-gated launch. Windows: npx/playwright resolve to .cmd shims
        # that CreateProcess cannot launch from a bare list arg (WinError 2), so
        # run a single joined command STRING through the shell (cmd.exe), same
        # convention as polish/devserver.py. POSIX: subprocess.run(shell=True)
        # with a *list* argument is `sh -c argv[0] argv[1:]` -- only argv[0]
        # ("npx") becomes the command, and everything else (including
        # "--reporter=json") is passed to the shell as positional params
        # ($0, $1, ...) instead of to npx. So on POSIX we must run the list
        # directly with shell=False to get correct arg passing.
        use_shell = sys.platform == "win32"
        run_arg = subprocess.list2cmdline(cmd_list) if use_shell else cmd_list
        # Windows minor: with shell=True the joined string is interpreted by
        # cmd.exe, which treats `& | ^ % < >` etc. as shell metacharacters.
        # `experiment` comes from developer-authored SR-binding config (not
        # runtime user input), so this is low risk -- an experiment value
        # containing those characters is simply unsupported.
        with (workdir / f"pw-stdout-seed{seed}.log").open("w", encoding="utf-8") as log:
            try:
                subprocess.run(
                    run_arg,
                    cwd=str(app_dir), env=env, check=False,
                    stdout=log, stderr=subprocess.STDOUT,
                    shell=use_shell,
                    timeout=timeout_s,
                )
            except subprocess.TimeoutExpired:
                # Don't let a hung run wedge the trial loop; the report file is
                # absent/incomplete, so the parser will score this trial False.
                pass
        return report_path

    return run_trial


class PlaywrightE2EHarness:
    """Live harness: run a Playwright e2e spec headless N times (seeded) and
    score the pass-rate. Executes runs instead of replaying a fixture trace."""

    SUPPORTED_METRIC = "e2e_pass_rate"

    def __init__(self, run_trial: TrialRunner) -> None:
        self._run_trial = run_trial

    @classmethod
    def from_config(cls, params: dict, project_root: Path) -> PlaywrightE2EHarness:
        app_dir = project_root / params.get("app_dir", "frontend")
        seed_env = params.get("seed_env", "E2E_SEED")
        test_cmd = list(params.get("test_cmd", ["npx", "playwright", "test"]))
        timeout_s = params.get("timeout_s", 600)
        return cls(_subprocess_runner(app_dir, seed_env, test_cmd, timeout_s))

    def run(self, binding: Binding, workdir: Path) -> HarnessResult:
        if binding.metric != self.SUPPORTED_METRIC:
            raise ValueError(
                f"PlaywrightE2EHarness supports metric {self.SUPPORTED_METRIC!r}, "
                f"got {binding.metric!r}"
            )
        trials: list[TrialResult] = []
        reports: list[dict] = []
        n = max(1, binding.trials)
        for seed in range(n):
            report_path = self._run_trial(seed, binding.experiment, workdir)
            report = json.loads(Path(report_path).read_text(encoding="utf-8"))
            reports.append(report)
            trials.append(TrialResult(seed=seed, passed=_spec_passed(report, binding.experiment)))
        rate = sum(1 for t in trials if t.passed) / len(trials)
        return HarnessResult(
            metric_value=rate,
            passed=evaluate_assertion(rate, binding.assert_expr),
            trials=trials,
            artifacts=[],
            raw={"reports": reports},
        )
