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
    paths = run_polish_session(
        pg, "uc", findings, tmp_path / "tasks", open_nav=lambda eps: opened.extend(eps)
    )
    assert len(paths) == 2
    assert opened == ["http://localhost:3000"]  # navigator opened with entrypoints
    assert torn == ["uc"]  # teardown ran
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
    assert torn == ["uc"]  # teardown still ran


def test_open_navigator_swallows_errors(monkeypatch):
    calls = []

    def _boom(*a, **k):
        calls.append(a)
        raise OSError("nope")

    monkeypatch.setattr(session_mod.subprocess, "Popen", _boom)
    open_navigator(["http://x"])  # must not raise
    assert calls  # attempted


def test_sigterm_handler_tears_down(monkeypatch, tmp_path):
    import signal as signal_mod

    from factory.polish import session as sm

    captured = {}

    def _fake_signal(sig, handler):
        if sig == signal_mod.SIGTERM and callable(handler):
            captured["term"] = handler  # capture the real handler before it's uninstalled
        return signal_mod.SIG_DFL

    monkeypatch.setattr(sm.signal, "signal", _fake_signal)

    torn = []

    class _PG:
        def list_usecases(self):
            return ["uc"]

        def setup(self, usecase):
            return PlaygroundSession(on_teardown=lambda: torn.append(1))

    # Run a normal session; capture the SIGTERM handler that was installed after setup.
    sm.run_polish_session(_PG(), "uc", [], tmp_path / "tasks")
    assert torn == [1]  # normal teardown ran exactly once
    assert callable(captured.get("term"))  # a SIGTERM handler was installed during the session

    # Invoking that handler raises SystemExit (torn flag prevents redundant teardown).
    with pytest.raises(SystemExit):
        captured["term"](signal_mod.SIGTERM, None)
    # torn remains [1] because idempotent guard prevents double-teardown
    assert torn == [1]


def test_teardown_registered_and_unregistered_with_atexit(monkeypatch, tmp_path):
    from factory.polish import session as sm

    reg, unreg = [], []
    monkeypatch.setattr(sm.atexit, "register", lambda fn: reg.append(fn) or fn)
    monkeypatch.setattr(sm.atexit, "unregister", lambda fn: unreg.append(fn))

    class _PG:
        def setup(self, usecase):
            return PlaygroundSession(on_teardown=lambda: None)

    sm.run_polish_session(_PG(), "uc", [], tmp_path / "tasks")
    assert reg and unreg and reg[0] is unreg[0]  # registered then cleaned up


def test_sigterm_during_body_tears_down_once(monkeypatch, tmp_path):
    import signal as signal_mod

    from factory.polish import session as sm

    installed = {}
    monkeypatch.setattr(
        sm.signal,
        "signal",
        lambda sig, h: installed.setdefault(sig, h) or signal_mod.SIG_DFL,
    )
    count = {"n": 0}

    class _PG:
        def setup(self, usecase):
            return PlaygroundSession(
                entrypoints=["x"],
                on_teardown=lambda: count.__setitem__("n", count["n"] + 1),
            )

    def _mid(_eps):
        # simulate SIGTERM arriving mid-body: invoke the installed handler
        installed[signal_mod.SIGTERM](signal_mod.SIGTERM, None)

    with pytest.raises(SystemExit):
        sm.run_polish_session(_PG(), "uc", [], tmp_path / "tasks", open_nav=_mid)
    assert count["n"] == 1  # torn-flag guard prevents double teardown
