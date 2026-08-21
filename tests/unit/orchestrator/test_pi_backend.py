from __future__ import annotations

import importlib
import subprocess
import sys
import warnings

import pytest
from factory.orchestrator.pi_backend import AgentResult, InterruptionReason, PiAgentBackend
from factory.orchestrator.roles import ROLE_SCOPE
from factory.orchestrator.types import AgentRole

pytestmark = pytest.mark.unit

# factory.orchestrator.pi_backend is now a thin AgentRole-typed composition
# wrapper around substrate.agents.backend.PiAgentBackend (Coherence Increment
# 1B, Task 3): almost the entire prior implementation -- timeouts, output
# caps, process-tree teardown, parsing -- moved verbatim to
# substrate.agents.backend and is exercised there directly in
# tests/unit/substrate/test_agents_backend.py (that is now the ground truth
# for that behavior: constants/monkeypatches only take effect where the code
# actually lives). This file tests exactly what the wrapper adds: translating
# AgentRole -> ROLE_SCOPE via scope_for, preserving AgentResult/
# InterruptionReason identity, and the module's deprecation warning.


def test_module_warns_once_with_the_substrate_target_on_import():
    sys.modules.pop("factory.orchestrator.pi_backend", None)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", DeprecationWarning)
        importlib.import_module("factory.orchestrator.pi_backend")

    deprecation = [item for item in caught if item.category is DeprecationWarning]
    assert len(deprecation) == 1
    assert str(deprecation[0].message) == (
        "factory.orchestrator.pi_backend is deprecated; import substrate.agents.backend "
        "and compose scope_for from factory.orchestrator.roles.ROLE_SCOPE"
    )


def test_agent_result_and_interruption_reason_are_the_substrate_types():
    from substrate.agents.model import AgentResult as SubstrateAgentResult
    from substrate.agents.model import InterruptionReason as SubstrateInterruptionReason

    # Not copies -- the SAME class objects, so isinstance/equality checks by
    # canonical (substrate) and legacy (factory) callers agree.
    assert AgentResult is SubstrateAgentResult
    assert InterruptionReason is SubstrateInterruptionReason


@pytest.mark.parametrize("role", list(AgentRole))
def test_run_injects_the_matching_role_scope_into_the_child_env(monkeypatch, tmp_path, role):
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
    backend = PiAgentBackend(tmp_path, tmp_path / "ext.ts")
    backend.run(role, "hi")

    expected = ROLE_SCOPE[role]
    assert captured["env"]["PI_SCOPE_ALLOW"] == ",".join(expected.allow)
    assert captured["env"]["PI_SCOPE_BASH"] == expected.bash


def test_run_preserves_agent_result_and_interruption_reason_end_to_end(monkeypatch, tmp_path):
    import threading

    killed: list[bool] = []
    block = threading.Event()

    class _StallProc:
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

    monkeypatch.setattr(subprocess, "Popen", lambda cmd, **kw: _StallProc())
    backend = PiAgentBackend(
        tmp_path,
        tmp_path / "ext.py",
        idle_timeout_s=0.1,
        total_timeout_s=5,
        idle_grace=2,
        liveness_root=tmp_path,
    )
    result = backend.run(AgentRole.DEV, "hi")

    assert isinstance(result, AgentResult)
    assert result.ok is False
    assert result.interruption is InterruptionReason.IDLE_TIMEOUT
    assert killed == [True]  # exactly once, and only after the grace budget
    assert result.session_id == "sess-x"  # captured before the kill


def test_run_launches_child_as_group_leader_on_posix(monkeypatch, tmp_path) -> None:
    # The child must start a new session/process group so a tree-kill can
    # TERM/KILL the whole group including grandchildren on POSIX. Exercised
    # here (not only in substrate's own tests) to prove the wrapper actually
    # wires role -> scope -> subprocess through to a real Popen call.
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
    PiAgentBackend(tmp_path, tmp_path / "ext.ts").run(AgentRole.DEV, "hi")
    assert captured.get("start_new_session") is True
