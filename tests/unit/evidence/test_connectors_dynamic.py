from __future__ import annotations

import pytest

from factory.orchestrator.backends import FakeGateRunner
from factory.evidence.types import EvidenceContext
from factory.evidence.connectors import TestResult

pytestmark = pytest.mark.unit


def _ctx(tmp_path, gate_rc):
    return EvidenceContext(repo_root=tmp_path, gates=FakeGateRunner({"unit": [gate_rc]}))


def test_expected_pass_when_gate_green(tmp_path):
    res = TestResult().evaluate({"gate": "unit", "expected": "pass"}, _ctx(tmp_path, 0))
    assert res.passed is True


def test_expected_pass_fails_when_gate_red(tmp_path):
    res = TestResult().evaluate({"gate": "unit", "expected": "pass"}, _ctx(tmp_path, 1))
    assert res.passed is False and "exit=1" in res.evidence


def test_expected_fail_passes_when_gate_red(tmp_path):
    # Bug-repro baseline: the suite is expected to FAIL right now.
    res = TestResult().evaluate({"gate": "unit", "expected": "fail"}, _ctx(tmp_path, 1))
    assert res.passed is True


def test_missing_gate_runner_is_failed_check(tmp_path):
    res = TestResult().evaluate({"gate": "unit", "expected": "pass"}, EvidenceContext(repo_root=tmp_path))
    assert res.passed is False and "gate runner" in res.evidence
