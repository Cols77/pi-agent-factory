import pytest
from factory.orchestrator.ledger import load_tasks
from factory.polish import session as session_mod
from factory.polish.finding import Finding
from factory.polish.playground import PlaygroundSession
from factory.polish.session import open_navigator, run_polish_session

pytestmark = pytest.mark.unit


class _FakePlayground:
    def __init__(self, torn):
        self._torn = torn

    def list_usecases(self):
        return ["uc"]

    def setup(self, usecase):
        return PlaygroundSession(
            entrypoints=["http://localhost:3000"],
            describe="d",
            on_teardown=lambda: self._torn.append(usecase),
        )


def test_run_routes_findings_and_tears_down(tmp_path):
    torn, opened = [], []
    pg = _FakePlayground(torn)
    findings = [Finding("uc", "a", sr="SR-001"), Finding("uc", "b")]
    paths = run_polish_session(pg, "uc", findings, tmp_path / "tasks",
                               open_nav=lambda eps: opened.extend(eps))
    assert len(paths) == 2
    assert opened == ["http://localhost:3000"]      # navigator opened with entrypoints
    assert torn == ["uc"]                            # teardown ran
    tasks = load_tasks(tmp_path / "tasks")
    assert [t.satisfies for t in tasks] == [["SR-001"], []]


def test_teardown_runs_even_if_routing_raises(tmp_path):
    torn = []
    pg = _FakePlayground(torn)
    # A tasks_dir that is actually a file makes route() fail on mkdir.
    bad = tmp_path / "afile"
    bad.write_text("x", encoding="utf-8")
    with pytest.raises(OSError):
        run_polish_session(pg, "uc", [Finding("uc", "a")], bad)
    assert torn == ["uc"]                            # teardown still ran


def test_open_navigator_swallows_errors(monkeypatch):
    calls = []

    def _boom(*a, **k):
        calls.append(a)
        raise OSError("nope")

    monkeypatch.setattr(session_mod.subprocess, "Popen", _boom)
    open_navigator(["http://x"])                     # must not raise
    assert calls  # attempted
