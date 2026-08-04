from __future__ import annotations

import json
import os
from pathlib import Path

from factory.polish.orchestrator import PolishOrchestrator


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)  # atomic on same filesystem


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
                cmd = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue  # a half-written file; try again next poll
            self.dispatch(cmd)
            path.unlink(missing_ok=True)
            applied += 1
        if applied:
            self.publish()
        return applied
