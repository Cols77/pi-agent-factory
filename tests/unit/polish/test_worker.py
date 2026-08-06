import threading
from pathlib import Path

import pytest

from factory.polish.finding import Finding
from factory.polish.worker import FixWorker, LandedChange

pytestmark = pytest.mark.unit


def _finding(desc="x"):
    return Finding(usecase="sign-in", description=desc)


def _landed(task_id="T-007", status="landed"):
    return LandedChange(
        finding=_finding(), task_path=Path(f"tasks/{task_id}.md"), task_id=task_id, status=status
    )


class _FakeExecutor:
    def __init__(self, results):
        self.results = results
        self.seen = []

    def execute(self, finding):
        self.seen.append(finding.description)
        return self.results.pop(0)


def test_process_next_delegates_to_executor():
    ex = _FakeExecutor([_landed(status="landed")])
    w = FixWorker(ex)
    w.submit(_finding("sign-in broken"))
    landed = w.process_next()
    assert landed.status == "landed"
    assert ex.seen == ["sign-in broken"]


def test_process_next_returns_none_when_empty():
    assert FixWorker(_FakeExecutor([])).process_next(timeout=0.01) is None


def test_start_drains_in_background():
    ex = _FakeExecutor([_landed("T-001"), _landed("T-002")])
    w = FixWorker(ex)
    seen: list[str] = []
    done = threading.Event()

    def on_landed(lc):
        seen.append(lc.task_id)
        if len(seen) == 2:
            done.set()

    w.submit(_finding("a"))
    w.submit(_finding("b"))
    w.start(on_landed)
    assert done.wait(timeout=5.0), "worker did not drain both in time"
    w.stop()
    assert len(seen) == 2
