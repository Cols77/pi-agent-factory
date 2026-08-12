from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections.abc import Callable
from pathlib import Path

from factory.requirements.register import Binding
from factory.validation.assertions import evaluate_assertion
from factory.validation.harness import HarnessResult, TrialResult
from factory.validation.scorer_registry import load_scorers


class UnknownMetricError(ValueError):
    pass


# Reserved, harness-intrinsic metric for the pytest trial source. A contract /
# architecture requirement measured by its own pytest selection uses this
# metric name; the harness computes it internally (fraction of collected tests
# that pass) rather than from a product scorer, so it must never be shadowed
# by a product scorer of the same name.
UNIT_PASS_RATE = "unit_pass_rate"


class SimTestbenchHarness:
    """Multi-source experiment harness.

    A requirement's ``binding.experiment`` selects a trial source:

    * **Frame-trace source** (the original increment-1 behaviour): if
      ``traces_dir / f"{binding.experiment}.json"`` exists, it is read as
      ``{"trials": [{"seed": int, "frames": [frame, ...]}, ...]}`` and each
      frame stream is scored by the product scorer named by ``binding.metric``.

    * **Pytest source**: otherwise ``binding.experiment`` is a pytest
      selection (file path or node id) run in ``workdir``. Each collected test
      is one trial; ``binding.metric`` must be the reserved
      ``unit_pass_rate``. Results come from a machine-readable JUnit XML
      report, which is also kept as an artifact.

    Both sources yield the same :class:`HarnessResult`; ``report`` /
    ``pipeline`` / manifests do not care which source produced a measurement.
    """

    def __init__(
        self,
        traces_dir: Path,
        scorers: dict[str, Callable[..., bool]] | None = None,
        *,
        pytest_python: str | None = None,
        pytest_marker: str | None = "unit",
    ) -> None:
        self._traces_dir = traces_dir
        # Per-trial scorers: (frames, window) -> bool. Rate = mean of the booleans.
        # An empty map means the target project has implemented no metrics yet.
        self._scorers = scorers if scorers is not None else {}
        self._pytest_python = pytest_python or sys.executable
        self._pytest_marker = pytest_marker

    @classmethod
    def from_config(
        cls, params: dict, project_root: Path
    ) -> "SimTestbenchHarness":
        return cls(
            project_root / params["traces_dir"],
            load_scorers(params.get("scorers"), project_root),
            pytest_python=params.get("pytest_python"),
            pytest_marker=params.get("pytest_marker", "unit"),
        )

    def run(self, binding: Binding, workdir: Path) -> HarnessResult:
        trace = self._traces_dir / f"{binding.experiment}.json"
        if trace.exists():
            return self._run_frames(binding, trace)
        # Not a frame-trace fixture, so the experiment is a pytest selection.
        # A product (frame) metric cannot score a test run -- refuse rather than
        # silently returning a bogus rate.
        if binding.metric != UNIT_PASS_RATE:
            raise UnknownMetricError(
                f"experiment {binding.experiment!r} is not a frame-trace fixture; "
                f"metric {binding.metric!r} requires a frame trace"
            )
        return self._run_pytest(binding, workdir)

    def _run_frames(
        self, binding: Binding, path: Path
    ) -> HarnessResult:
        scorer = self._scorers.get(binding.metric)
        if scorer is None:
            raise UnknownMetricError(f"no trial scorer for metric {binding.metric!r}")
        data = json.loads(path.read_text(encoding="utf-8"))
        trials_raw = data["trials"]
        results: list[TrialResult] = []
        for tr in trials_raw:
            ok = scorer(tr["frames"], binding.window)
            results.append(TrialResult(seed=int(tr.get("seed", 0)), passed=bool(ok)))
        rate = (sum(1 for r in results if r.passed) / len(results)) if results else 0.0
        return HarnessResult(
            metric_value=rate,
            passed=evaluate_assertion(rate, binding.assert_expr),
            trials=results,
            artifacts=[],
            raw={"trace": str(path), "trials": len(results)},
        )

    def _run_pytest(self, binding: Binding, workdir: Path) -> HarnessResult:
        """Run ``binding.experiment`` as a pytest selection in ``workdir``.

        Purpose: measure contract / architecture requirements (interface,
        component, state-machine tests) that the frame-trace source cannot
        express. Each collected test is one trial; a test that passes counts as
        a passing trial, anything else (failure, error, skipped) counts as not
        passing -- a measurement, never a silent pass.

        Args:
            binding: the requirement binding naming the pytest selection and
                the assert expression.
            workdir: the project root the selection runs in.

        Returns:
            A ``HarnessResult`` with ``metric_value`` = fraction of collected
            tests that passed and the JUnit XML report attached as an artifact.

        Raises:
            UnknownMetricError: if ``binding.metric`` is not the reserved
                ``unit_pass_rate`` (already enforced in ``run``); never raised
                here.
        """
        out_dir = workdir / ".tmp"
        out_dir.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha1(binding.experiment.encode("utf-8")).hexdigest()[:12]
        xml_path = out_dir / f"unit-{digest}.xml"
        cmd = [
            self._pytest_python,
            "-m",
            "pytest",
            binding.experiment,
            "-q",
            "--tb=no",
            "-p",
            "no:cacheprovider",
            "--color=no",
            f"--junitxml={xml_path}",
        ]
        if self._pytest_marker is not None:
            cmd.extend(["-m", self._pytest_marker])
        proc = subprocess.run(cmd, cwd=workdir, capture_output=True, text=True)

        trials, collected = self._parse_xml(xml_path)
        if collected is None or collected == 0:
            # Nothing was collected/measured: report an honest non-pass with a
            # diagnostic, never a fabricated 1.0 (or 0.0 that could read as pass
            # for an inverted assert).
            detail = f"no tests collected for {binding.experiment!r}: rc={proc.returncode}"
            return HarnessResult(
                metric_value=0.0,
                passed=False,
                trials=[],
                artifacts=[],
                raw={"selection": binding.experiment, "error": detail},
            )

        passed_count = sum(1 for t in trials if t.passed)
        rate = passed_count / collected
        return HarnessResult(
            metric_value=rate,
            passed=evaluate_assertion(rate, binding.assert_expr),
            trials=trials,
            artifacts=[xml_path] if xml_path.exists() else [],
            raw={
                "selection": binding.experiment,
                "collected": collected,
                "passed": passed_count,
                "report": str(xml_path),
                "rc": proc.returncode,
            },
        )

    @staticmethod
    def _parse_xml(
        xml_path: Path,
    ) -> tuple[list[TrialResult], int | None]:
        """Parse a pytest JUnit XML report into one trial per test case.

        Purpose: derive per-test pass/fail (and the collected count) from
        machine-readable XML rather than brittle console-text parsing.

        Args:
            xml_path: the JUnit XML report path.

        Returns:
            A ``(trials, collected)`` pair. ``collected`` is the ``tests``
            attribute of the root ``<testsuite>``, or ``None`` if the report
            could not be read.

        Raises:
            None.
        """
        if not xml_path.exists():
            return [], None
        try:
            root = ET.parse(xml_path).getroot()
        except ET.ParseError:
            return [], None
        suite = next(root.iter("testsuite"), None)
        if suite is None:
            return [], None
        tests = suite.get("tests")
        if tests is None:
            return [], None
        collected = int(tests)
        trials: list[TrialResult] = []
        for i, tc in enumerate(suite.iter("testcase")):
            node = tc.find("failure")
            node = node if node is not None else tc.find("error")
            skipped = tc.find("skipped") is not None
            detail = ""
            if node is not None:
                detail = (node.get("message") or "")[:400]
            elif skipped:
                detail = "skipped"
            trials.append(
                TrialResult(seed=i, passed=node is None and not skipped, detail=detail)
            )
        return trials, collected