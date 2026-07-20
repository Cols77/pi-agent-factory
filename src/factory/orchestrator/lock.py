from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class LockInfo:
    pid: int
    started_at: str


class AlreadyRunningError(RuntimeError):
    def __init__(self, pid: int) -> None:
        super().__init__(f"factory orchestrator already running (pid {pid})")
        self.pid = pid


def read_lock(path: Path) -> LockInfo | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return LockInfo(pid=int(data["pid"]), started_at=str(data["started_at"]))
    except (json.JSONDecodeError, KeyError, ValueError):
        return None


def write_lock(path: Path, pid: int, started_at: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"pid": pid, "started_at": started_at}), encoding="utf-8")


def remove_lock(path: Path) -> None:
    path.unlink(missing_ok=True)


def is_pid_alive(pid: int) -> bool:
    """Cross-platform liveness check using only the stdlib. POSIX uses the
    standard os.kill(pid, 0) idiom; Windows doesn't support that (os.kill
    there only understands CTRL_C_EVENT/CTRL_BREAK_EVENT), so this shells
    out to `tasklist` there instead -- matching this codebase's existing
    win32/posix branching pattern (e.g. scripts/gates/ext.py's npm.cmd)."""
    if sys.platform == "win32":
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}"], capture_output=True, text=True
        )
        return str(pid) in result.stdout
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists, just not owned by us
    return True


def acquire_lock(path: Path, pid: int, started_at: str) -> None:
    """Raise AlreadyRunningError if a live lock already exists; otherwise
    (no lock, or a stale lock left by a dead process) write a fresh lock."""
    existing = read_lock(path)
    if existing is not None and is_pid_alive(existing.pid):
        raise AlreadyRunningError(existing.pid)
    write_lock(path, pid, started_at)
