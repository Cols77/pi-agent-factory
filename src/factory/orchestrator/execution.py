from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from factory.orchestrator.git_ops import GitOps
from factory.orchestrator.journal import RunCheckpoint, RunEvent, RunJournal


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
        payload = data or {}
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
            schema_version=1,
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
            patch_path=patch.relative_to(self.repo_root).as_posix(),
            completed=list(self.completed),
            agent_sessions=dict(self.agent_sessions),
            pending_human_round=attempt if next_node == "human-review" else None,
            artifacts=list(self.artifacts),
            interruption=interruption,
        )
        self.journal.checkpoint(checkpoint)
        return checkpoint
