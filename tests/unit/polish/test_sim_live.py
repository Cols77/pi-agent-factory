import sys
import time

import pytest

from factory.polish.config import PLAYGROUND_TYPES
from factory.polish.playground import Playground
from factory.polish.sim_live import SimLivePlayground

pytestmark = pytest.mark.unit


def _mk(dir_, *parts, name, content="seed: 7\n"):
    target = dir_.joinpath(*parts)
    target.mkdir(parents=True, exist_ok=True)
    (target / name).write_text(content, encoding="utf-8")


def _pid_alive(pid: int) -> bool:
    """Return whether a process with *pid* is still running."""
    if sys.platform == "win32":
        import ctypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
            return code.value == STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    import os

    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def test_is_a_playground(tmp_path):
    pg = SimLivePlayground(tmp_path, ["echo"], project_root=tmp_path)
    assert isinstance(pg, Playground)


def test_list_usecases_globs_nested_yaml_stems(tmp_path):
    _mk(tmp_path, name="scn_001.yaml")
    _mk(tmp_path, "sub", name="scn_002.yaml")
    _mk(tmp_path, name="scn_003.json")  # not yaml: must be ignored
    pg = SimLivePlayground(tmp_path, ["echo"], project_root=tmp_path)
    assert pg.list_usecases() == ["scn_001", "scn_002"]


def test_setup_missing_scenario_raises(tmp_path):
    pg = SimLivePlayground(tmp_path, ["echo"], project_root=tmp_path)
    with pytest.raises(FileNotFoundError, match="scn_999"):
        pg.setup("scn_999")


def test_setup_spawns_child_then_teardown_kills_it(tmp_path):
    sentinel = tmp_path / "up.txt"
    script = (
        "import os, time\n"
        "from pathlib import Path\n"
        f"Path({str(sentinel)!r}).write_text(str(os.getpid()))\n"
        "time.sleep(300)\n"
    )
    _mk(tmp_path, name="scn_001.yaml")
    pg = SimLivePlayground(
        tmp_path, [sys.executable, "-c", script], project_root=tmp_path
    )
    session = pg.setup("scn_001")
    try:
        deadline = time.monotonic() + 10
        while not sentinel.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert sentinel.exists()
        pid = int(sentinel.read_text())
        assert _pid_alive(pid)  # the child really spawned
        assert session.entrypoints == [str(tmp_path / "scn_001.yaml")]
    finally:
        session.teardown()
    time.sleep(0.3)
    assert _pid_alive(pid) is False  # teardown killed it; no process leak


def test_from_config(tmp_path):
    _mk(tmp_path, "scenarios", "reference", name="scn_005.yaml")
    params = {
        "scenarios_dir": "scenarios/reference",
        "run_command": ["uv", "run", "python", "-m", "sim"],
    }
    pg = SimLivePlayground.from_config(params, tmp_path)
    assert pg.list_usecases() == ["scn_005"]


def test_registered_in_playground_types():
    # A classmethod access returns a fresh bound method each time, so compare
    # the underlying function's identity, not the wrapper object.
    assert PLAYGROUND_TYPES["sim-live"].__func__ is SimLivePlayground.from_config.__func__