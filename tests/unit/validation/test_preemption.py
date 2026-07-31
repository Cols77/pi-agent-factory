import pytest
from factory.validation.metrics.preemption import (
    preemption_success_rate,
    trial_preempted,
)

pytestmark = pytest.mark.unit


def _f(t, kind, sharks=()):
    return {
        "mission_clock": t,
        "active_directive": {"kind": kind},
        "detections": [{"label": "shark", "confidence": c} for c in sharks],
    }


WINDOW = {"after_event": "shark_detected", "within_s": 5}

GOOD = [_f(0, "patrol"), _f(15, "patrol", (0.45,)), _f(17, "override", (0.8,)), _f(40, "patrol")]
LATE = [_f(0, "patrol"), _f(15, "patrol", (0.45,)), _f(30, "override"), _f(40, "patrol")]
NO_RESUME = [_f(0, "patrol"), _f(15, "patrol", (0.45,)), _f(17, "override")]
NO_TRIGGER = [_f(0, "patrol"), _f(20, "patrol")]


def test_good_trial_passes():
    assert trial_preempted(GOOD, WINDOW) is True


def test_late_preemption_fails_window():
    assert trial_preempted(LATE, WINDOW) is False


def test_no_resume_fails():
    assert trial_preempted(NO_RESUME, WINDOW) is False


def test_no_trigger_fails():
    assert trial_preempted(NO_TRIGGER, WINDOW) is False


def test_rate_over_trials():
    assert preemption_success_rate([GOOD, GOOD, LATE, NO_TRIGGER], WINDOW) == 0.5
    assert preemption_success_rate([], WINDOW) == 0.0
