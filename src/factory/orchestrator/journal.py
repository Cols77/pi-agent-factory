from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
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
    patch_path: str | None
    completed: list[dict]
    agent_sessions: dict[str, str]
    pending_human_round: int | None
    artifacts: list[str]
    interruption: str | None


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
        tmp.write_text(json.dumps(asdict(checkpoint), indent=2), encoding="utf-8")
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
        try:
            value = json.loads(self.checkpoint_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except json.JSONDecodeError as exc:
            raise ValueError("corrupt run checkpoint") from exc
        if not isinstance(value, dict):
            raise ValueError("corrupt run checkpoint")
        try:
            return RunCheckpoint(**value)
        except TypeError as exc:
            raise ValueError("corrupt run checkpoint") from exc
