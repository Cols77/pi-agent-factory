from __future__ import annotations

import json
import os
import time
from pathlib import Path

from factory.polish.orchestrator import PolishOrchestrator

_RETRY_ATTEMPTS = 5
_RETRY_SLEEP_S = 0.05


def _atomic_write(path: Path, text: str) -> None:
    """Write via temp file + atomic rename, retrying the rename.

    The mirror of atomicWriteWithRetry in polish-protocol.ts, and required for
    the same reason: Windows holds files open without delete-share, so
    os.replace raises PermissionError (WinError 5) whenever the UI happens to be
    reading polish-state.json as we republish it. The UI polls on the same
    interval we publish on, so this is routine, not exotic -- and without the
    retry a single collision kills the session and both dev-servers.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    last_err: OSError | None = None
    for _ in range(_RETRY_ATTEMPTS):
        try:
            os.replace(tmp, path)  # atomic on same filesystem
            return
        except OSError as err:
            last_err = err
            time.sleep(_RETRY_SLEEP_S)
    tmp.unlink(missing_ok=True)  # best-effort cleanup; don't leak .tmp files
    assert last_err is not None
    raise last_err


class PolishBridge:
    """File bridge between the Python PolishOrchestrator and the TS UI."""

    def __init__(self, orchestrator: PolishOrchestrator, state_path: Path,
                 commands_dir: Path) -> None:
        self._orch = orchestrator
        self._state_path = state_path
        self._commands_dir = commands_dir
        self._seq = 0

    def publish(self) -> None:
        self._seq += 1
        _atomic_write(
            self._state_path, json.dumps({"seq": self._seq, "state": self._orch.state()})
        )

    def dispatch(self, cmd: dict) -> None:
        kind = cmd.get("kind")
        args = cmd.get("args") or {}
        if kind == "feedback":
            self._orch.submit_feedback(str(args["text"]))
        elif kind == "accept":
            self._orch.accept_finding(str(args["gid"]))
        elif kind == "edit":
            self._orch.edit_finding(str(args["gid"]), **(args.get("changes") or {}))
        elif kind == "discard":
            self._orch.discard_finding(str(args["gid"]))
        elif kind == "tick":
            self._orch.tick(str(args["gid"]))
        elif kind == "comment":
            self._orch.comment(str(args["gid"]), str(args["text"]))
        # unknown kinds are ignored (forward-compat with a newer UI)

    def poll_commands(self) -> int:
        if not self._commands_dir.exists():
            return 0
        applied = 0
        for path in sorted(self._commands_dir.glob("*.json")):
            try:
                # utf-8-sig tolerates a BOM (some editors/tools emit one) and is
                # identical to utf-8 when there isn't one. A BOM previously made
                # json.loads raise, so the command was skipped on every poll forever.
                cmd = json.loads(path.read_text(encoding="utf-8-sig"))
            except (json.JSONDecodeError, OSError):
                continue  # a half-written file; try again next poll
            try:
                self.dispatch(cmd)
            except KeyError:
                # The UI polls state on the same interval we publish it, so its
                # view is always slightly behind: a Gate 1 row can be accepted or
                # reworked between the render the human saw and the key they
                # pressed. A command naming a gid that no longer exists is a
                # normal race, not a reason to kill the session (which took both
                # dev-servers with it when it happened live).
                pass
            path.unlink(missing_ok=True)
            applied += 1
        if applied:
            self.publish()
        return applied
