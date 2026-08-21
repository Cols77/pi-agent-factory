from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from factory.orchestrator.git_ops import GitOps
from factory.orchestrator.journal import RunCheckpoint, RunEvent, RunJournal

# Payloads larger than this are not inlined into the run journal / checkpoint.
# KB-0004: a context-gather manifest embedded whole into RunEvent.data and
# completed[].data produced 106MB checkpoint.json/journal.jsonl files and a
# MemoryError; oversized payloads are written to a blob file in the run dir and
# referenced by path instead, keeping both files bounded.
MAX_INLINE_PAYLOAD_BYTES = 512 * 1024


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class RunExecution:
    repo_root: Path
    run_id: str
    task_id: str
    start_commit: str
    git_ops: GitOps
    journal: RunJournal
    sequence: int = 0
    completed: list[dict] = field(default_factory=list)
    agent_sessions: dict[str, str] = field(default_factory=dict)
    artifacts: list[str] = field(default_factory=list)

    @classmethod
    def create(
        cls,
        repo_root: Path,
        run_id: str,
        task_id: str,
        start_commit: str,
        git_ops: GitOps,
    ) -> RunExecution:
        run_dir = repo_root / "sessions" / ".factory-runs" / "by-session" / run_id
        journal = RunJournal(run_dir)
        events = journal.events()
        return cls(
            repo_root,
            run_id,
            task_id,
            start_commit,
            git_ops,
            journal,
            max((event.sequence for event in events), default=0),
        )

    def resolve_data(self, data: dict) -> dict:
        """Resolve a possibly-externalised payload back to its real content.

        record() stores oversized payloads as {"payload_ref": <run-dir-relative
        path>}; resume reads the context-gather data through here so a
        checkpoint whose manifest was externalised still reconstructs it.
        Unknown or corrupt blobs degrade to the ref dict itself (never crash
        the resume)."""
        if not isinstance(data, dict):
            return data or {}
        ref = data.get("payload_ref")
        if not isinstance(ref, str):
            return data
        try:
            value = json.loads((self.journal.run_dir / ref).read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            return data
        return value if isinstance(value, dict) else data

    def record(
        self,
        *,
        node: str,
        state: str,
        attempt: int,
        next_node: str,
        remaining: dict[str, int],
        data: dict | None = None,
        session_id: str | None = None,
        interruption: str | None = None,
    ) -> RunCheckpoint:
        self.sequence += 1
        attempt_id = f"{node}-{attempt}"
        payload = self._bounded_payload(node, data or {})
        if session_id:
            self.agent_sessions[node] = session_id
        self.journal.append(
            RunEvent(
                sequence=self.sequence,
                at=_now(),
                run_id=self.run_id,
                task_id=self.task_id,
                node=node,
                attempt_id=attempt_id,
                state=state,
                data=payload,
            )
        )
        if state == "completed":
            self.completed.append(
                {
                    "node": node,
                    "attempt": attempt,
                    "data": payload,
                }
            )
        patch = self.journal.run_dir / "checkpoints" / f"{self.sequence:06d}.patch"
        self.git_ops.write_patch(self.repo_root, self.start_commit, patch)
        checkpoint = RunCheckpoint(
            schema_version=2,
            run_id=self.run_id,
            task_id=self.task_id,
            node=next_node,
            attempt=attempt,
            remaining=remaining,
            start_commit=self.start_commit,
            head_commit=self.git_ops.head_commit(self.repo_root),
            worktree_fingerprint=self.git_ops.worktree_fingerprint(
                self.repo_root, self.start_commit
            ),
            tracked_fingerprint=self.git_ops.tracked_fingerprint(
                self.repo_root, self.start_commit
            ),
            patch_path=patch.relative_to(self.repo_root).as_posix(),
            completed=list(self.completed),
            agent_sessions=dict(self.agent_sessions),
            pending_human_round=attempt if next_node == "human-review" else None,
            artifacts=list(self.artifacts),
            interruption=interruption,
        )
        self.journal.checkpoint(checkpoint)
        return checkpoint

    def _bounded_payload(self, node: str, payload: dict) -> dict:
        """Inline small payloads; externalise oversized ones to a blob file.

        The blob lives under sessions/.factory-runs/<run_id>/payloads/, which is
        factory scratch (never staged, never fingerprint-flipping). The
        checkpoint/journal entries keep a {"payload_ref": ...} stub, so a
        resume can resolve the content back via resolve_data()."""
        if len(json.dumps(payload, separators=(",", ":"))) <= MAX_INLINE_PAYLOAD_BYTES:
            return payload
        payload_dir = self.journal.run_dir / "payloads"
        payload_dir.mkdir(parents=True, exist_ok=True)
        blob = payload_dir / f"{self.sequence:06d}-{node}.json"
        tmp = blob.with_name(blob.name + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(blob)
        return {
            "payload_ref": blob.relative_to(self.journal.run_dir).as_posix(),
            "bytes": blob.stat().st_size,
        }
