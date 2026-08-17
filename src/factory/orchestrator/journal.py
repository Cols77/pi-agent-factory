from __future__ import annotations

import json
import os
from dataclasses import MISSING, asdict, dataclass, field, fields
from pathlib import Path


@dataclass(frozen=True)
class RunEvent:
    sequence: int
    at: str
    run_id: str
    task_id: str
    node: str
    attempt_id: str
    state: str
    data: dict = field(default_factory=dict)


@dataclass
class RunCheckpoint:
    schema_version: int
    run_id: str
    task_id: str
    node: str
    attempt: int
    remaining: dict[str, int]
    start_commit: str
    head_commit: str
    worktree_fingerprint: str
    tracked_fingerprint: str | None = None
    patch_path: str | None = None
    completed: list[dict] = field(default_factory=list)
    agent_sessions: dict[str, str] = field(default_factory=dict)
    pending_human_round: int | None = None
    artifacts: list[str] = field(default_factory=list)
    interruption: str | None = None


class RunJournal:
    def __init__(self, run_dir: Path) -> None:
        self.run_dir = run_dir
        self.journal_path = run_dir / "journal.jsonl"
        self.checkpoint_path = run_dir / "checkpoint.json"

    def append(self, event: RunEvent) -> None:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        encoded = (json.dumps(asdict(event), separators=(",", ":")) + "\n").encode("utf-8")
        with self.journal_path.open("ab") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())

    def checkpoint(self, checkpoint: RunCheckpoint) -> None:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        tmp = self.checkpoint_path.with_name(self.checkpoint_path.name + ".tmp")
        with tmp.open("w", encoding="utf-8") as stream:
            stream.write(json.dumps(asdict(checkpoint), indent=2))
            stream.flush()
            os.fsync(stream.fileno())
        tmp.replace(self.checkpoint_path)

    def events(self) -> list[RunEvent]:
        try:
            raw = self.journal_path.read_bytes()
        except FileNotFoundError:
            return []
        lines = raw.splitlines(keepends=True)
        out: list[RunEvent] = []
        for index, line in enumerate(lines):
            try:
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError("event is not an object")
                out.append(RunEvent(**value))
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                final_partial = index == len(lines) - 1 and not line.endswith((b"\n", b"\r"))
                if final_partial:
                    break
                raise ValueError(f"corrupt run journal at line {index + 1}") from exc
        return out

    def latest(self) -> RunCheckpoint | None:
        """Load the latest checkpoint, tolerating older schema versions.

        A checkpoint written before a field was added (e.g. the pre-KB-0004
        checkpoints that lack `tracked_fingerprint`) must still load so resume
        can fall back to the saved patch for the tracked-diff comparison.
        Unknown keys are dropped; missing defaulted fields are filled in."""
        try:
            value = json.loads(self.checkpoint_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except json.JSONDecodeError as exc:
            raise ValueError("corrupt run checkpoint") from exc
        if not isinstance(value, dict):
            raise ValueError("corrupt run checkpoint")
        known = {item.name: item for item in fields(RunCheckpoint)}
        filtered: dict = {}
        for key, item in known.items():
            if key in value:
                filtered[key] = value[key]
            elif item.default is not MISSING:
                filtered[key] = item.default
        try:
            return RunCheckpoint(**filtered)
        except TypeError as exc:
            raise ValueError("corrupt run checkpoint") from exc
