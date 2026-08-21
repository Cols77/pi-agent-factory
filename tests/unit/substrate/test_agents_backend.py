from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import pytest
from substrate.agents.backend import (
    PiAgentBackend,
    _IdleKeeper,
    _drain_lines,
    _kill_process_tree,
    _pid_is_alive,
    _probe_file_heartbeat,
)
from substrate.agents.model import InterruptionReason

pytestmark = pytest.mark.unit


@dataclass(frozen=True)
class _Scope:
    """Minimal ScopeLike stand-in -- substrate must never import the real
    `factory.orchestrator.roles.Scope`, so tests exercise the Protocol's
    structural surface (.allow / .bash) with a local dataclass instead."""

    allow: list[str]
    bash: str


_STUB_SCOPE = _Scope(allow=[], bash="allow")


def _stub_scope_for(role: str) -> _Scope:
    return _STUB_SCOPE


# --- injected scope_for (Coherence Increment 1B, Task 3) --------------------
# substrate.agents.backend.PiAgentBackend takes an injected scope_for callable
# instead of importing a role catalogue (ROLE_SCOPE/AgentRole/Scope) directly.


def test_run_never_imports_factory_or_coherence():
    for module_name in ("substrate.agents.backend", "substrate.agents.model"):
        import importlib

        module = importlib.import_module(module_name)
        source = Path(module.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        roots = {
            (node.module or "").split(".", 1)[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        }
        roots.update(
            alias.name.split(".", 1)[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        )
        assert roots.isdisjoint({"factory", "coherence"}), module_name


def test_run_consults_the_injected_scope_for_not_a_role_catalogue(monkeypatch, tmp_path):
    injected = _Scope(allow=["src/**", "tests/**"], bash="deny")
    calls: list[str] = []

    def scope_for(role: str) -> _Scope:
        calls.append(role)
        return injected

    captured: dict = {}

    class _FakeProc:
        returncode = 0
        stdout: list = []

        def wait(self) -> None:
            pass

        def kill(self) -> None:
            pass

    def _fake_popen(cmd, **kwargs):
        captured["env"] = kwargs.get("env")
        return _FakeProc()

    monkeypatch.setattr(subprocess, "Popen", _fake_popen)
    backend = PiAgentBackend(tmp_path, tmp_path / "ext.ts", scope_for=scope_for)
    backend.run("some-custom-role", "hi")

    assert calls == ["some-custom-role"]  # the plain role string, unmodified
    assert captured["env"]["PI_SCOPE_ALLOW"] == "src/**,tests/**"
    assert captured["env"]["PI_SCOPE_BASH"] == "deny"


class _FakeClock:
    """Deterministic monotonic-ish clock for keeper tests."""

    def __init__(self, start: float = 100.0) -> None:
        self._t = start

    def advance(self, delta: float) -> None:
        self._t += delta

    def __call__(self) -> float:
        return self._t


def test_idle_keeper_strikes_up_to_grace_then_kills() -> None:
    clock = _FakeClock()
    keeper = _IdleKeeper(grace=4, now=clock)
    # Grace windows are permitted; the breach must EXCEED grace to kill.
    for idx in range(4):
        clock.advance(1.0)
        assert keeper.on_elapsed() == "keep-running"
        assert keeper.breaches == idx + 1
    clock.advance(1.0)
    assert keeper.on_elapsed() == "kill"
    assert keeper.breaches == 5  # exceeded the 4-window grace budget


def test_idle_keeper_note_live_resets_strike() -> None:
    clock = _FakeClock()
    keeper = _IdleKeeper(grace=2, now=clock)
    clock.advance(1.0)
    assert keeper.on_elapsed() == "keep-running"
    assert keeper.breaches == 1
    keeper.note_live()
    assert keeper.breaches == 0
    # After a live reset, a fresh run of silent windows still behaves: 2 grace
    # windows, then a kill on the 3rd.
    clock.advance(1.0)
    assert keeper.on_elapsed() == "keep-running"  # breach 1
    clock.advance(1.0)
    assert keeper.on_elapsed() == "keep-running"  # breach 2 (== grace, allowed)
    clock.advance(1.0)
    assert keeper.on_elapsed() == "kill"  # breach 3 > grace
    assert keeper.breaches == 3


def test_idle_keeper_probe_reset_keeps_silent_child_alive() -> None:
    clock = _FakeClock()
    keeper = _IdleKeeper(grace=2, now=clock)
    # A liveness probe reporting fresh file progress every window resets the
    # breach, so a child that never emits output is never killed.
    for _ in range(30):
        clock.advance(1.0)
        assert keeper.on_elapsed(probe_result=True) == "keep-running"
        assert keeper.breaches == 0


def test_probe_file_heartbeat_detects_fresh_write_under_watch_dir(tmp_path) -> None:
    watch = tmp_path / "tasks"
    watch.mkdir()
    since = time.time()
    assert _probe_file_heartbeat([str(watch)], since_seconds=since) is False
    (watch / "T-001.md").write_text("hello", encoding="utf-8")
    # A file written after the watermark is a heartbeat.
    assert _probe_file_heartbeat([str(watch)], since_seconds=time.time() - 1.0) is True


def test_probe_file_heartbeat_ignores_stale_and_missing_dirs(tmp_path) -> None:
    watch = tmp_path / "docs"
    watch.mkdir()
    stale = watch / "old.md"
    stale.write_text("old", encoding="utf-8")
    # Backdate the mtime: a file older than the watermark is NOT a heartbeat.
    os.utime(stale, (0.0, 0.0))
    assert _probe_file_heartbeat([str(watch)], since_seconds=time.time()) is False
    # A missing dir yields no signal, not an error.
    assert _probe_file_heartbeat([str(tmp_path / "nope")], since_seconds=0.0) is False


def test_drain_lines_survives_silence_while_writing_deliverables(tmp_path) -> None:
    watch = tmp_path / "tasks"
    watch.mkdir()
    stop = threading.Event()

    def writing():
        yield "first\n"
        # Writes deliverables while staying silent on stdout -- must not be
        # mistaken for a stall.
        for i in range(10):
            (watch / f"burst-{i}.md").write_text("x", encoding="utf-8")
            stop.wait(0.05)

    fired: list[str] = []
    out = list(
        _drain_lines(
            writing(),
            idle_timeout=0.1,
            total_timeout=5,
            on_timeout=fired.append,
            idle_grace=2,
            liveness_root=tmp_path,
            liveness_dirs=("tasks",),
        )
    )
    stop.set()
    assert out == ["first\n"]  # the one stdout line
    assert fired == []  # never tripped idle despite the silence


def test_drain_lines_still_trips_idle_after_grace_when_truly_silent(tmp_path) -> None:
    block = threading.Event()

    def silent():
        yield "1\n"
        block.wait(5)  # no output AND no deliverable writes -> genuine stall

    fired: list[str] = []
    out = list(
        _drain_lines(
            silent(),
            idle_timeout=0.05,
            total_timeout=5,
            on_timeout=fired.append,
            idle_grace=2,
            liveness_root=tmp_path,
            liveness_dirs=("tasks",),
        )
    )
    block.set()
    assert out == ["1\n"]
    assert fired == ["idle"]  # grace of silent windows eventually trips idle


def test_run_kills_stalled_child_only_after_idle_grace(monkeypatch, tmp_path) -> None:
    killed: list[bool] = []
    block = threading.Event()

    class _Stall:
        def __init__(self) -> None:
            self.returncode = 0

            def gen():
                yield '{"type":"session","id":"sess-x"}\n'
                block.wait(5)  # stalls after the session id

            self.stdout = gen()

        def kill(self) -> None:
            killed.append(True)
            block.set()

        def wait(self) -> None:
            pass

    monkeypatch.setattr(subprocess, "Popen", lambda cmd, **kw: _Stall())
    backend = PiAgentBackend(
        tmp_path,
        tmp_path / "ext.py",
        scope_for=_stub_scope_for,
        idle_timeout_s=0.1,
        total_timeout_s=5,
        idle_grace=2,
        liveness_root=tmp_path,
    )
    result = backend.run("dev", "hi")

    assert result.ok is False
    assert result.interruption is InterruptionReason.IDLE_TIMEOUT
    assert killed == [True]  # exactly once, and only after the grace budget
    assert result.session_id == "sess-x"  # captured before the kill


def test_run_does_not_kill_stalled_child_while_deliverables_are_written(
    monkeypatch, tmp_path
) -> None:
    killed: list[bool] = []
    block = threading.Event()

    class _Busy:
        def __init__(self) -> None:
            self.returncode = 0

            def gen():
                yield '{"type":"session","id":"sess-y"}\n'
                block.wait(6)  # silent as far as stdout is concerned

            self.stdout = gen()

        def kill(self) -> None:
            killed.append(True)
            block.set()

        def wait(self) -> None:
            pass

    monkeypatch.setattr(subprocess, "Popen", lambda cmd, **kw: _Busy())
    backend = PiAgentBackend(
        tmp_path,
        tmp_path / "ext.py",
        scope_for=_stub_scope_for,
        idle_timeout_s=0.1,
        total_timeout_s=0.6,
        idle_grace=2,
        # The injected liveness probe reports a fresh deliverable write every
        # window, so the silent child survives far past idle grace; only the
        # (smaller-in-test) total bound eventually trips -- never an idle kill.
        liveness_probe=lambda since: True,
    )
    result = backend.run("dev", "hi")

    assert result.ok is False
    assert result.interruption is InterruptionReason.TOTAL_TIMEOUT
    assert killed == [True]
    assert result.session_id == "sess-y"


# --- PART-2a of T-029: process-tree termination on child kill -----------------
# A stalled/runaway child pi that spawned grandchildren (shell, tools) used to
# leak those descendants when only the direct pid was killed. The tree kill
# sends SIGTERM to the whole group (the child is the pgid leader), gives it a
# short grace to exit, then escalates to SIGKILL. The SIGTERM/SIGKILL
# assertions below are POSIX-only because Windows has no killpg semantics.


def test_kill_process_tree_escalates_to_sigkill_when_mount_survives_term():
    if sys.platform == "win32":
        pytest.skip("killpg semantics are POSIX-only")
    from substrate.agents.backend import _SIG_KILL, _SIG_TERM

    signals_sent: list[int] = []
    hard_killed = {"yes": False}

    def record_killpg(pid: int, sig: int) -> None:
        signals_sent.append(sig)
        if sig == _SIG_KILL:
            hard_killed["yes"] = True  # the fake dies only on the hard kill

    def alive(pid: int) -> bool:
        return not hard_killed["yes"]  # TERM does not stop it; SIGKILL does

    class _FakeGroup:
        pid = 4242

        def kill(self) -> None:
            raise AssertionError("POSIX tree-kill must not fall back to direct kill")

    _kill_process_tree(
        _FakeGroup(),
        grace_step=0.05,
        grace_total=0.1,
        sleep=lambda _: None,  # deterministic, no real waiting
        alive=alive,
        killpg=record_killpg,
    )
    # TERM first, then (the group still living past grace) an escalated SIGKILL.
    assert signals_sent == [_SIG_TERM, _SIG_KILL]


def test_kill_process_tree_winds_down_after_term_without_sigkill():
    if sys.platform == "win32":
        pytest.skip("killpg semantics are POSIX-only")
    from substrate.agents.backend import _SIG_TERM

    signals_sent: list[int] = []

    def record_killpg(pid: int, sig: int) -> None:
        signals_sent.append(sig)

    class _FakeGroup:
        pid = 7

        def kill(self) -> None:
            raise AssertionError("must not fall back to direct kill")

    _kill_process_tree(
        _FakeGroup(),
        grace_step=0.05,
        grace_total=2.0,
        sleep=lambda _: None,
        alive=lambda pid: False,  # the group promptly died on SIGTERM
        killpg=record_killpg,
    )
    # Only the graceful TERM was needed; no SIGKILL escalation.
    assert signals_sent == [_SIG_TERM]


def test_kill_process_tree_falls_back_to_direct_kill_without_group():
    # A proc with no usable leader pid (or a non-POSIX platform) must still
    # best-effort kill the direct child rather than silently leak it.
    killed: list[bool] = []

    class _ProcWithoutPid:
        def kill(self) -> None:
            killed.append(True)

    _kill_process_tree(_ProcWithoutPid(), sleep=lambda _: None, alive=lambda pid: True)
    assert killed == [True]


def test_run_launches_child_as_group_leader_on_posix(monkeypatch, tmp_path) -> None:
    # The child must start a new session/process group so a tree-kill can
    # TERM/KILL the whole group including grandchildren on POSIX.
    if sys.platform == "win32":
        pytest.skip("start_new_session is POSIX-only")
    captured: dict = {}

    class _FakeProc:
        returncode = 0
        stdout: list = []

        def wait(self) -> int:
            return 0

        def kill(self) -> None:
            pass

    def _fake_popen(cmd, **kwargs):
        captured.update(kwargs)
        return _FakeProc()

    monkeypatch.setattr(subprocess, "Popen", _fake_popen)
    monkeypatch.setattr("substrate.agents.backend._DEFAULT_IDLE_TIMEOUT_S", 1.0)
    monkeypatch.setattr("substrate.agents.backend._DEFAULT_TOTAL_TIMEOUT_S", 1.0)
    PiAgentBackend(tmp_path, tmp_path / "ext.ts", scope_for=_stub_scope_for).run("dev", "hi")
    assert captured.get("start_new_session") is True


def test_kill_process_tree_terminates_real_grandchild(monkeypatch, tmp_path) -> None:
    # Integration: a real child spawned as a group leader, which itself spawns
    # a sleeping grandchild. After the tree kill, BOTH must be gone -- not just
    # the direct child. POSIX-only (needs a real group).
    if sys.platform == "win32":
        pytest.skip("POSIX-only process-group kill")
    from substrate.agents.backend import _SIG_KILL

    gc_pid_file = tmp_path / "grandchild.pid"
    script = (
        "import subprocess, sys, time\n"
        "g = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])\n"
        "open(sys.argv[1], 'w').write(str(g.pid))\n"
        "time.sleep(30)\n"
    )
    child = None
    gc_pid = None
    try:
        child = subprocess.Popen(
            [sys.executable, "-c", script, str(gc_pid_file)],
            start_new_session=True,
        )
        # Wait (bounded) for the grandchild to report its pid.
        deadline = time.time() + 10
        while time.time() < deadline and not gc_pid_file.exists():
            time.sleep(0.02)
        assert gc_pid_file.exists(), "grandchild never reported its pid"
        gc_pid = int(gc_pid_file.read_text(encoding="utf-8").strip())
        # Sanity: both are genuinely running before the process-tree kill.
        assert child.pid != gc_pid
        assert _pid_is_alive(gc_pid) is True

        _kill_process_tree(child, grace_step=0.05, grace_total=0.3)

        # Both the direct child and its grandchild are gone.
        assert child.poll() is not None
        assert _pid_is_alive(gc_pid) is False
    finally:
        # Teardown even on failure so the test never leaks processes.
        if child is not None and child.poll() is None:
            try:
                child.kill()
            except OSError:
                pass
        if gc_pid is not None and _pid_is_alive(gc_pid):
            try:
                os.kill(gc_pid, _SIG_KILL)
            except OSError:
                pass
        if gc_pid_file.exists():
            gc_pid_file.unlink()


# --- PART-2b of T-029: transient spawn retry --------------------------------
# A launch that fails to START the process at all (missing bin / transient race)
# should be retried a bounded number of times before spawn failure; a child
# that STARTED and then stalled must never be relaunched (that death is a kill).


def test_run_retries_transient_spawn_failure_then_succeeds(monkeypatch, tmp_path) -> None:
    from substrate.agents.backend import _SPAWN_RETRIES

    calls: list[int] = []

    class _OkProc:
        returncode = 0
        stdout: list = []

        def wait(self) -> None:
            pass

        def kill(self) -> None:
            pass

    errors = iter([OSError("boom-1"), OSError("boom-2")])

    def _popen(cmd, **kw):
        calls.append(1)
        try:
            raise next(errors)
        except StopIteration:
            # The fake raised for the first two launches, then starts cleanly:
            # the third (final) attempt is the success.
            return _OkProc()

    monkeypatch.setattr(subprocess, "Popen", _popen)
    backend = PiAgentBackend(tmp_path, tmp_path / "ext.ts", scope_for=_stub_scope_for)
    result = backend.run("dev", "hi")

    assert result.ok is True
    # Initial attempt + the two retries (the exact retry budget).
    assert calls == [1] * (_SPAWN_RETRIES + 1)


def test_retry_gives_up_after_budget_when_spawn_always_fails(monkeypatch, tmp_path) -> None:
    from substrate.agents.backend import _SPAWN_RETRIES

    calls: list[int] = []
    # A genuinely missing `pi` bin (FileNotFoundError, an OSError subclass) must
    # NOT spin forever: retry up to the budget, then report failure.
    monkeypatch.setattr(
        "substrate.agents.backend._SPAWN_BACKOFF_S", 0.0
    )  # deterministic: no real backoff sleep in the test

    def _popen(cmd, **kw):
        calls.append(1)
        raise FileNotFoundError("no pi binary on PATH")

    monkeypatch.setattr(subprocess, "Popen", _popen)
    backend = PiAgentBackend(tmp_path, tmp_path / "ext.ts", scope_for=_stub_scope_for)
    with pytest.raises(OSError):
        backend.run("dev", "hello")

    # Exactly the retry budget (initial + retries), no busy-launch loop.
    assert calls == [1] * (_SPAWN_RETRIES + 1)


def test_retry_never_relaunches_a_started_but_stalled_child(monkeypatch, tmp_path) -> None:
    # A child that STARTED and then went silent is killed by the idle timeout;
    # it must NEVER be relaunched (only a failure to start is retried).
    calls: list[int] = []
    block = threading.Event()

    class _StallProc:
        def __init__(self) -> None:
            self.returncode = 0

            def gen():
                yield '{"type":"session","id":"sess-stall"}\n'
                block.wait(5)  # starts, then goes silent -> idle kill

            self.stdout = gen()

        def kill(self) -> None:
            block.set()

        def wait(self) -> None:
            pass

    def _popen(cmd, **kw):
        calls.append(1)
        return _StallProc()

    monkeypatch.setattr(subprocess, "Popen", _popen)
    backend = PiAgentBackend(
        tmp_path,
        tmp_path / "ext.ts",
        scope_for=_stub_scope_for,
        idle_timeout_s=0.1,
        total_timeout_s=5,
        idle_grace=1,
    )
    result = backend.run("dev", "hi")
    block.set()

    assert result.ok is False
    assert result.interruption is InterruptionReason.IDLE_TIMEOUT
    # Exactly ONE launch: a started-but-stalled child is killed, not re-spawned.
    assert calls == [1]


# --- PART-2b of T-029: output hard-cap ---------------------------------------
# A pathological child flooding stdout must not blow up memory: the backend
# keeps only a bounded rolling TAIL (so the final manifest survives) and marks
# over-budget runs as truncated without flipping the ok/interruption class.


def test_run_caps_output_and_keeps_final_manifest(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("substrate.agents.backend._MAX_OUTPUT_TOTAL_CHARS", 800)
    monkeypatch.setattr("substrate.agents.backend._MAX_OUTPUT_RETAINED_CHARS", 400)

    # A huge silent flood, then the real manifest at the very end of the stream.
    flood_line = "x" * 4000
    manifest = json.dumps({
        "type": "message_end",
        "message": {
            "role": "assistant",
            "content": [
                {"type": "text", "text": '```json\n{"dod_met": true, "findings": []}\n```'},
            ],
        },
    })
    lines = [
        '{"type":"session","id":"sess-cap"}\n',
        flood_line + "\n",
        flood_line + "\n",
        manifest + "\n",
    ]

    class _FakeProc:
        def __init__(self) -> None:
            self.stdout = iter(lines)
            self.returncode = 0

        def wait(self) -> None:
            pass

    monkeypatch.setattr(subprocess, "Popen", lambda cmd, **kw: _FakeProc())
    result = PiAgentBackend(tmp_path, tmp_path / "ext.ts", scope_for=_stub_scope_for).run(
        "dev", "hi"
    )

    assert result.ok is True  # truncation must not flip the ok classification
    assert "truncated" in result.raw
    # The final manifest survives inside the retained tail and still parses.
    assert result.output == {"dod_met": True, "findings": []}
    # Retained output stays bounded: far below the flood and under the cap.
    assert len(result.raw) < 800


def test_run_output_under_cap_has_no_truncation_note(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("substrate.agents.backend._MAX_OUTPUT_TOTAL_CHARS", 1000)
    monkeypatch.setattr("substrate.agents.backend._MAX_OUTPUT_RETAINED_CHARS", 500)

    session = '{"type":"session","id":"sess-small"}\n'
    message = json.dumps({
        "type": "message_end",
        "message": {
            "role": "assistant",
            "content": [{"type": "text", "text": "small"}],
        },
    }) + "\n"

    class _FakeProc:
        def __init__(self) -> None:
            self.stdout = iter([session, message])
            self.returncode = 0

        def wait(self) -> None:
            pass

    monkeypatch.setattr(subprocess, "Popen", lambda cmd, **kw: _FakeProc())
    result = PiAgentBackend(tmp_path, tmp_path / "ext.ts", scope_for=_stub_scope_for).run(
        "dev", "hi"
    )

    assert result.ok is True
    assert "truncated" not in result.raw
    assert result.session_id == "sess-small"


def test_retain_line_capped_truncates_a_lone_oversized_line() -> None:
    # A single pathological event line must not defeat the retention cap: it is
    # truncated to the line cap (tail kept) with a marker, so one giant event
    # cannot be retained whole and multiplied across the counters (T-029 I2).
    from substrate.agents.backend import _retain_line_capped

    retained: list[str] = []
    chars = _retain_line_capped(retained, 0, limit=100, line="x" * 10_000, line_cap=100)
    assert len(retained) == 1
    assert retained[0].startswith("<snip>")
    assert chars <= 100 + len("<snip>")
    # The rolling window keeps the newest line even when the cap is exceeded.
    retained2: list[str] = []
    chars2 = _retain_line_capped(retained2, 0, limit=50, line="a" * 40, line_cap=0)
    chars2 = _retain_line_capped(retained2, chars2, limit=50, line="b" * 40, line_cap=0)
    assert len(retained2) == 1
    assert retained2[0] == "b" * 40


def test_kill_process_tree_post_sigkill_poll_is_bounded(monkeypatch) -> None:
    # The post-SIGKILL poll must terminate even if the leader never reaps
    # (a zombie reads as alive via os.kill(pid,0)): the bounded budget stops
    # teardown from spinning forever (T-029 B1).
    from substrate.agents.backend import _kill_process_tree

    if sys.platform == "win32":
        pytest.skip("POSIX-only tree-kill behavior")
    slept: list[float] = []
    signals: list[int] = []

    class _FakeProc:
        pid = 12345

        def kill(self) -> None:
            pass

        def poll(self) -> None:
            return None  # never reaps -> leader always reads alive

    def _fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    def _fake_alive(pid: int) -> bool:
        return True  # group never appears dead

    def _fake_killpg(pid: int, sig: int) -> None:
        signals.append(sig)

    _kill_process_tree(
        _FakeProc(),
        grace_step=0.1,
        grace_total=0.3,
        sleep=_fake_sleep,
        alive=_fake_alive,
        killpg=_fake_killpg,
        poll_budget=4,
    )
    assert signals.count(15) == 1  # SIGTERM once
    assert signals.count(9) == 1  # SIGKILL once after grace
    # Bound: grace (3 sleeps) + poll budget (4 sleeps) = 7 sleeps max.
    assert len(slept) <= 7


def test_kill_process_tree_default_probe_escalates_for_a_running_child(
    monkeypatch,
) -> None:
    # The DEFAULT alive probe (no injected ``alive``) must read a still-running
    # child as alive so the TERM grace + SIGKILL escalation actually fire. This
    # exercises the exact production path: a reaped-unaware probe would invert
    # the boolean and send only SIGTERM, never escalating (T-029 B1 re-review).
    from substrate.agents.backend import _kill_process_tree

    if sys.platform == "win32":
        pytest.skip("POSIX-only tree-kill behavior")
    signals: list[int] = []
    slept: list[float] = []

    class _RunningProc:
        pid = 23456

        def kill(self) -> None:
            pass

        def poll(self) -> None:
            return None  # child is still running -> not reaped

    def _fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    def _fake_killpg(pid: int, sig: int) -> None:
        signals.append(sig)

    # Patch the group-liveness primitive the DEFAULT wrapper falls back to: a
    # running child reads as alive, so escalation must fire.
    monkeypatch.setattr(
        "substrate.agents.backend._pid_is_alive",
        lambda pid: True,
    )
    _kill_process_tree(
        _RunningProc(),
        grace_step=0.01,
        grace_total=0.05,
        sleep=_fake_sleep,
        killpg=_fake_killpg,
        poll_budget=2,
    )
    # TERM was sent once, then the child stayed alive past grace, so SIGKILL
    # escalated -- the default probe did NOT invert and stop at SIGTERM.
    assert signals.count(15) == 1
    assert signals.count(9) == 1


def test_kill_process_tree_default_probe_stops_once_reaped(monkeypatch) -> None:
    # The DEFAULT probe must read a reaped (zombie-cleared) leader as dead so
    # teardown does not spin after a clean TERM wind-down.
    from substrate.agents.backend import _kill_process_tree

    if sys.platform == "win32":
        pytest.skip("POSIX-only tree-kill behavior")
    signals: list[int] = []
    slept: list[float] = []

    class _ReapedProc:
        pid = 34567

        def kill(self) -> None:
            pass

        def poll(self) -> int:
            return 0  # child already reaped -> dead

    def _fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    def _fake_killpg(pid: int, sig: int) -> None:
        signals.append(sig)

    monkeypatch.setattr(
        "substrate.agents.backend._pid_is_alive",
        lambda pid: True,  # a zombie would still read as alive via kill(pid,0)
    )
    _kill_process_tree(
        _ReapedProc(),
        grace_step=0.01,
        grace_total=0.05,
        sleep=_fake_sleep,
        killpg=_fake_killpg,
        poll_budget=2,
    )
    # The leader was already reaped -> no escalation, no SIGKILL, no spin.
    assert signals.count(15) == 1
    assert signals.count(9) == 0
    assert len(slept) == 0
