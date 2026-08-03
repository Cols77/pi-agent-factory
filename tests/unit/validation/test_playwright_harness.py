import json
from pathlib import Path

import pytest

from factory.validation.playwright_harness import _spec_passed

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
