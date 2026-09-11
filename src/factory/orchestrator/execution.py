from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path

from coherence.execution.gate_plan import CANONICAL_EXECUTION_STAGES
from factory.orchestrator.git_ops import GitOps
from factory.orchestrator.journal import RunCheckpoint, RunEvent, RunJournal

# Payloads larger than this are not inlined into the run journal / checkpoint.
# KB-0004: a context-gather manifest embedded whole into RunEvent.data and
# completed[].data produced 106MB checkpoint.json/journal.jsonl files and a
# MemoryError; oversized payloads are written to a blob file in the run dir and
# referenced by path instead, keeping both files bounded.
MAX_INLINE_PAYLOAD_BYTES = 512 * 1024

_HEX = set("0123456789abcdef")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _stage_event_sha256(
    cursor: GovernedStageCursor, state: str, data: dict | None
) -> str:
    """The deterministic hash of one recorded stage evidence (the cursor chain)."""
    payload = {
        "stage_id": cursor.stage_id,
        "revision": cursor.revision,
        "attempt": cursor.attempt,
        "attempt_key": cursor.attempt_key,
        "state": state,
        "data": data or {},
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class RunCursorError(RuntimeError):
    """A governed stage cursor is unknown, stale, replayed or non-monotonic."""


@dataclass(frozen=True)
class GovernedStageCursor:
    """SR-049 governed position in the fixed execution graph.

    ``(stage_id, revision, attempt)`` identifies the evidence; ``attempt_key`` is
    the deterministic fencing key for that revision/attempt; and
    ``parent_event_sha256`` chains the cursor to the last recorded stage
    evidence, so a replay or a forged parent is detectable.
    """

    stage_id: str
    revision: int
    attempt: int
    parent_event_sha256: str | None
    attempt_key: str

    def __post_init__(self) -> None:
        if not isinstance(self.stage_id, str) or not self.stage_id:
            raise ValueError("stage_id must be a non-blank string")
        for name in ("revision", "attempt"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise ValueError(f"{name} must be an int >= 1")
        parent = self.parent_event_sha256
        if parent is not None and (
            not isinstance(parent, str) or len(parent) != 64 or set(parent) > _HEX
        ):
            raise ValueError("parent_event_sha256 must be a canonical sha256 digest or None")
        if not isinstance(self.attempt_key, str) or not self.attempt_key:
            raise ValueError("attempt_key must be a non-blank string")

    def to_dict(self) -> dict:
        return {
            "stage_id": self.stage_id,
            "revision": self.revision,
            "attempt": self.attempt,
            "parent_event_sha256": self.parent_event_sha256,
            "attempt_key": self.attempt_key,
        }


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
    stage_cursors: dict[str, GovernedStageCursor] = field(default_factory=dict)
    invalidated_stages: set[str] = field(default_factory=set)

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

    def open_cursor(self, stage_id: str) -> GovernedStageCursor:
        """Return the live cursor for a stage, or fail closed if it has none."""
        return self._live_cursor(stage_id)

    def begin_revision(self, stage_id: str) -> GovernedStageCursor:
        """Open the next revision of a stage (attempt 1) and invalidate descendants.

        A fixer revision is exactly this: revision ``n + 1`` of the stage makes
        every *later* stage in the canonical graph stale, so its old revision
        cannot be recorded or resumed.
        """
        self._require_canonical_stage(stage_id)
        previous = self.stage_cursors.get(stage_id)
        revision = 1 if previous is None else previous.revision + 1
        cursor = self._new_cursor(stage_id, revision, 1)
        self.stage_cursors[stage_id] = cursor
        if previous is not None:
            self._invalidate_descendants(stage_id)
        return cursor

    def begin_attempt(self, stage_id: str) -> GovernedStageCursor:
        """Open the next attempt of the *same* revision (human retry).

        The new attempt gets a fresh fencing key and no recorded parent; the
        previous attempt's evidence is left untouched.
        """
        previous = self.stage_cursors.get(stage_id)
        if previous is None:
            raise RunCursorError(f"no governed cursor for stage {stage_id!r}")
        cursor = self._new_cursor(stage_id, previous.revision, previous.attempt + 1)
        self.stage_cursors[stage_id] = cursor
        return cursor

    def record_stage(
        self, cursor: GovernedStageCursor, *, state: str = "completed", data: dict | None = None
    ) -> GovernedStageCursor:
        """Journal one stage evidence for the cursor's revision/attempt.

        Rejects an unknown stage, a stale/replayed cursor, a non-monotonic
        revision/attempt, a mismatched fencing key and a mismatched parent-event
        hash. Returns the advanced (frozen) cursor; the caller's cursor is never
        rewritten.
        """
        if not isinstance(cursor, GovernedStageCursor):
            raise RunCursorError("record_stage requires a GovernedStageCursor")
        stored = self.stage_cursors.get(cursor.stage_id)
        if stored is None:
            raise RunCursorError(f"no governed cursor for stage {cursor.stage_id!r}")
        if (cursor.revision, cursor.attempt) != (stored.revision, stored.attempt):
            raise RunCursorError(
                "stale or non-monotonic stage cursor: "
                f"{cursor.stage_id} r{cursor.revision} a{cursor.attempt} != "
                f"r{stored.revision} a{stored.attempt}"
            )
        if cursor.attempt_key != stored.attempt_key:
            raise RunCursorError(
                f"stage cursor fencing key does not match {stored.attempt_key!r}"
            )
        if cursor.parent_event_sha256 != stored.parent_event_sha256:
            raise RunCursorError(
                "replayed stage cursor or mismatched parent-event hash for "
                f"{cursor.stage_id!r}"
            )

        payload = {**(data or {}), "stage_cursor": cursor.to_dict()}
        self.record(
            node=cursor.stage_id,
            state=state,
            attempt=cursor.attempt,
            next_node=cursor.stage_id,
            remaining={},
            data=payload,
        )
        advanced = replace(cursor, parent_event_sha256=_stage_event_sha256(cursor, state, data))
        self.stage_cursors[cursor.stage_id] = advanced
        return advanced

    def _live_cursor(self, stage_id: str) -> GovernedStageCursor:
        cursor = self.stage_cursors.get(stage_id)
        if cursor is None:
            raise RunCursorError(
                f"no governed cursor for stage {stage_id!r} "
                "(never begun, or invalidated by a later revision)"
            )
        return cursor

    def _require_canonical_stage(self, stage_id: str) -> None:
        if stage_id not in CANONICAL_EXECUTION_STAGES:
            raise RunCursorError(
                f"unknown execution stage {stage_id!r}; the graph is fixed by SR-034"
            )

    def _new_cursor(self, stage_id: str, revision: int, attempt: int) -> GovernedStageCursor:
        return GovernedStageCursor(
            stage_id=stage_id,
            revision=revision,
            attempt=attempt,
            parent_event_sha256=None,
            attempt_key=f"{self.run_id}/{self.task_id}/{stage_id}/r{revision}/a{attempt}/v1",
        )

    def _invalidate_descendants(self, stage_id: str) -> None:
        """Every later stage in the canonical graph is stale after a revision."""
        index = CANONICAL_EXECUTION_STAGES.index(stage_id)
        for descendant in CANONICAL_EXECUTION_STAGES[index + 1 :]:
            self.invalidated_stages.add(descendant)
            self.stage_cursors.pop(descendant, None)

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
