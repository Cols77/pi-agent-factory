"""SR-049 governed run execution: journal, checkpoint and stage-cursor state.

Deviation from the Task 8 brief (adversarial review, blocking): a governed stage
record must never be able to make a resume skip DEV.

``record_stage`` journals the stage evidence with the *bare* canonical stage id
(``node=cursor.stage_id``, e.g. ``"validation"``) because Task 5's kernel
consumes that governed identity there and in ``data["stage_cursor"]``. But the
checkpoint it writes is *also* read by the legacy router in ``runner.py``, which
does ``resume_at = resume.node`` and treats
``resume_at in {"validation", "review", "human-review"}`` as "already past DEV",
skipping the whole ``run_dev`` block. Writing the bare stage id into
``RunCheckpoint.node`` therefore let a single ``record_stage`` call on a fresh
run make a later resume skip DEV entirely (reproduced by the adversarial
reviewer).

The fix keeps the governed identity in the journal, and namespaces only the
checkpoint's node with :data:`STAGE_CHECKPOINT_NODE_PREFIX` (``stage:<id>``), a
value the legacy router vocabulary can never contain -- ``runner.py`` is not
modified, and the legacy ``record()`` nodes are untouched. The regression test
in ``tests/unit/orchestrator/test_execution.py`` extracts the router's skip-set
literal from ``runner.py`` itself and proves the stage-record node is not in it.

SR-034 Task 5 (increment 4) additions, all additive to the accepted Task 8 surface
(``open_cursor``, ``record_stage``, ``begin_revision``, ``begin_attempt``,
``GovernedStageCursor``, ``RunCursorError`` keep their exact accepted meaning):

* :meth:`RunExecution.open_human_decision_request` / :meth:`RunExecution.consume_human_decision`
  -- the durable ``needs_input`` request and its append-only human decision record.
* :meth:`RunExecution.restore_cursors` -- rebuilds the monotonic governed cursor tail
  from the persisted journal (``create`` calls it) so a resumed process continues
  instead of restarting at r1/a1, and a journalled ``attempt_key`` can never be reused.
* :meth:`RunExecution.open_task_cursor` -- the run/task-identity entry cursor.

Plan Task-5 snippet call -> shipped, accepted API (the kernel increment follows the
shipped column; nothing here renames the accepted surface):

    plan snippet                                    shipped API
    open_cursor(task.id, self.gate_plan)            open_task_cursor(task.id, self.gate_plan)
    record_stage(cursor, state=..., data=...)       record_stage(cursor, state=..., data=...)  (identical)
    begin_revision(cursor, stage_id=..., reason=..) begin_revision(cursor.stage_id)           (reason is kernel evidence)
    begin_attempt(cursor, reason=...)               begin_attempt(cursor.stage_id)
    consume_human_decision(task.id, **fields)       consume_human_decision(task.id, **fields)  (identical)
    (a fresh dispatch's entry cursor)               RunExecution.create(...)  # restores cursors

``open_cursor`` also accepts an optional ``gate_plan`` second argument (validating the
stage is in the plan), so the snippet's argument shape has a home; the one-argument
call keeps its exact accepted meaning.
"""

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

# A stage record's checkpoint node is namespaced so it can never collide with the
# legacy resume vocabulary runner.py's router reads (`validation`, `review`,
# `human-review` all mean "already past DEV" there). The bare stage id stays in
# the journal event node and in data["stage_cursor"] for Task 5's kernel.
STAGE_CHECKPOINT_NODE_PREFIX = "stage:"

# A stage record publishes an empty checkpoint `remaining`: a governed stage owns
# no legacy budget counters. This marker rides in the record's data so no resume
# consumer can read that empty dict as "nothing left".
STAGE_RECORD_BUDGET_NOTE = (
    "governed stage record: `remaining` is empty by design, not an exhausted budget"
)

_HEX = set("0123456789abcdef")

# SR-034 Task 5 durable human-decision contract (plan lifecycle section). The
# request and the decision are two distinct record types, both namespaced in the
# governed journal data so no legacy reader can mistake one for a stage record.
HUMAN_DECISION_REQUEST_KEY = "human_decision_request"
HUMAN_DECISION_KEY = "human_decision"
DECISION_RECORD_SCHEMA = 2
# The closed decision vocabulary; the kernel may never widen it (plan: retry|defer|block).
ALLOWED_HUMAN_DECISIONS: tuple[str, ...] = ("retry", "defer", "block")
# Only a real human may record a decision; an agent-authored one is refused.
HUMAN_DECIDED_BY = "human"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _canonical_sha256(payload: dict) -> str:
    """The deterministic record digest: sorted-key compact JSON, SHA-256."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


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
    #: attempt_keys already journalled by an *earlier* process (restore_cursors
    #: fills this). A restarted process can therefore never re-open a position
    #: whose fencing key is already on disk -- see ``_new_cursor``.
    prior_attempt_keys: set[str] = field(default_factory=set)

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
        execution = cls(
            repo_root,
            run_id,
            task_id,
            start_commit,
            git_ops,
            journal,
            max((event.sequence for event in events), default=0),
        )
        # Restore the governed cursor tail: a resumed process continues from the
        # journal's monotonic revision/attempt position instead of restarting at
        # r1/a1 (the Task 5 obligation review flagged on the empty in-memory map).
        execution.restore_cursors(events)
        return execution

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

    def open_cursor(
        self, stage_id: str, gate_plan: object | None = None
    ) -> GovernedStageCursor:
        """Return the live cursor for a stage, or fail closed if it has none.

        The one-argument call is the accepted Task 8 meaning, unchanged. The
        additive optional ``gate_plan`` mirrors the plan snippet's
        ``open_cursor(task.id, self.gate_plan)`` argument shape: when supplied the
        stage must belong to that plan's stage tuple, so a kernel cannot address a
        stage the compiled graph does not contain. Use :meth:`open_task_cursor`
        for the run/task-identity entry cursor the snippet actually wants.
        """
        if gate_plan is not None:
            self._require_plan_stage(stage_id, gate_plan)
        return self._live_cursor(stage_id)

    def open_task_cursor(
        self, task_id: str, gate_plan: object | None = None
    ) -> GovernedStageCursor:
        """The run/task-identity entry cursor for a fresh or resumed dispatch.

        This is the shipped form of the Task-5 snippet's
        ``self.execution.open_cursor(task.id, self.gate_plan)``: ``task_id``
        addresses the run (it must be this execution's task) and ``gate_plan``
        supplies the canonical stage tuple whose *first* stage opens the graph.
        After :meth:`restore_cursors` a resumption returns the journal's live
        root cursor rather than a fresh r1/a1; a dispatch with no governed
        evidence yet opens revision 1, attempt 1.
        """
        if task_id != self.task_id:
            raise RunCursorError(
                f"task {task_id!r} is not this run's task {self.task_id!r}"
            )
        stages = (
            CANONICAL_EXECUTION_STAGES
            if gate_plan is None
            else getattr(gate_plan, "stages", None)
        )
        if not isinstance(stages, (tuple, list)) or not stages:
            raise RunCursorError(
                "open_task_cursor requires a GatePlan with a non-empty stage tuple"
            )
        root = stages[0]
        self._require_canonical_stage(root)
        live = self.stage_cursors.get(root)
        if live is not None:
            return live
        return self.begin_revision(root)

    def _require_plan_stage(self, stage_id: str, gate_plan: object) -> None:
        stages = getattr(gate_plan, "stages", None)
        if not isinstance(stages, (tuple, list)) or stage_id not in stages:
            raise RunCursorError(
                f"stage {stage_id!r} is not in the supplied GatePlan's stage tuple"
            )

    def begin_revision(self, stage_id: str) -> GovernedStageCursor:
        """Open the next revision of a stage (attempt 1) and invalidate descendants.

        A fixer revision is exactly this: revision ``n + 1`` of the stage makes
        every *later* stage in the canonical graph stale, so its old revision
        cannot be recorded or resumed.

        ``invalidated_stages`` describes the *current* revision chain: re-opening
        a stage clears its own entry, so a consumer can tell "invalidated by the
        latest revision" from "invalidated earlier and since re-established"
        (the set used to only ever grow, which made the two indistinguishable).
        """
        self._require_canonical_stage(stage_id)
        previous = self.stage_cursors.get(stage_id)
        revision = 1 if previous is None else previous.revision + 1
        cursor = self._new_cursor(stage_id, revision, 1)
        self.stage_cursors[stage_id] = cursor
        self.invalidated_stages.discard(stage_id)
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

        payload = {
            **(data or {}),
            "stage_cursor": cursor.to_dict(),
            "budget_note": STAGE_RECORD_BUDGET_NOTE,
        }
        # The record's own digest, computed from the caller's evidence exactly as
        # before (so previously recorded digests are unchanged) but now stored:
        # restore_cursors() needs it to rebuild the parent-event chain on resume,
        # since the journal payload carries extra keys the digest never covered.
        digest = _stage_event_sha256(cursor, state, data)
        payload["stage_event_sha256"] = digest
        self.record(
            node=cursor.stage_id,
            state=state,
            attempt=cursor.attempt,
            # Namespaced on purpose: the bare stage id here is what the legacy
            # router reads as "past DEV" and skipped run_dev for. The governed
            # identity lives in `node` (journal) and in data["stage_cursor"].
            next_node=f"{STAGE_CHECKPOINT_NODE_PREFIX}{cursor.stage_id}",
            # A governed stage owns no legacy budget counters, so the driver's
            # {"dev": n, "review": n} evidence is deliberately not overwritten
            # here; see STAGE_RECORD_BUDGET_NOTE for the marker consumers read.
            remaining={},
            data=payload,
        )
        advanced = replace(cursor, parent_event_sha256=digest)
        self.stage_cursors[cursor.stage_id] = advanced
        return advanced

    def restore_cursors(
        self, events: list[RunEvent] | None = None
    ) -> dict[str, GovernedStageCursor]:
        """Rebuild the live governed cursors from the persisted journal.

        The kernel must "load its monotonic tail from RunExecution before
        starting": ``stage_cursors``/``invalidated_stages`` were in-memory only,
        so a resumed process restarted every stage at r1/a1 and the journal's
        revision/attempt position was lost. This replays the stage records in
        journal order and rebuilds, for each stage, the *latest* recorded
        cursor (revision, attempt, fencing key and the parent-event digest that
        record chained onto), plus the descendant-invalidation set the last
        revision produced. A later revision of a stage drops its descendants,
        exactly as ``begin_revision`` does live.

        ``attempt_key`` uniqueness is enforced across the whole journal: a key
        already used for a different position is a tamper signal and raises. The
        keys seen here are retained in :attr:`prior_attempt_keys`, so
        ``_new_cursor`` can never hand a restarted process a fencing key that is
        already on disk.

        Returns the restored live cursors (also assigned to ``stage_cursors``).
        """
        journal_events = self.journal.events() if events is None else events
        restored: dict[str, GovernedStageCursor] = {}
        invalidated: set[str] = set()
        seen_keys: dict[str, str] = {}
        for event in journal_events:
            data = event.data if isinstance(event.data, dict) else {}
            raw = data.get("stage_cursor")
            if not isinstance(raw, dict):
                continue
            cursor = self._cursor_from_record(raw, data)
            key_position = f"{cursor.stage_id}/r{cursor.revision}/a{cursor.attempt}"
            recorded_position = seen_keys.get(cursor.attempt_key)
            if recorded_position is not None and recorded_position != key_position:
                raise RunCursorError(
                    f"journalled attempt_key {cursor.attempt_key!r} was reused for "
                    f"{recorded_position} and {key_position}"
                )
            seen_keys[cursor.attempt_key] = key_position

            previous = restored.get(cursor.stage_id)
            if previous is None or (cursor.revision, cursor.attempt) >= (
                previous.revision,
                previous.attempt,
            ):
                if previous is not None and cursor.revision > previous.revision:
                    self._invalidate_descendants(cursor.stage_id, restored, invalidated)
                restored[cursor.stage_id] = cursor
                invalidated.discard(cursor.stage_id)

        self.stage_cursors = restored
        self.invalidated_stages = invalidated
        self.prior_attempt_keys = set(seen_keys)
        return dict(restored)

    def open_human_decision_request(
        self,
        cursor: GovernedStageCursor,
        *,
        reason: str,
        finding_universe_sha256: str | None = None,
        input_sha256: str | None = None,
        allowed_decisions: tuple[str, ...] = ALLOWED_HUMAN_DECISIONS,
    ) -> tuple[GovernedStageCursor, dict]:
        """Journal one durable ``needs_input`` request; return it and the advanced cursor.

        This is the kernel's ``_request_human_decision`` building block at the
        ``RunExecution`` layer: it appends the request record (``record_schema:
        2``, ``state="pending"``) as a ``needs_input`` stage record and returns a
        deterministic ``request_sha256`` the human decision is later matched
        against, append-only. It does not choose or consume a decision.

        Only the closed ``retry|defer|block`` vocabulary is accepted, and a
        second request while one is still pending is refused: the ledger holds
        exactly one live request per run/task.
        """
        if not isinstance(cursor, GovernedStageCursor):
            raise RunCursorError("open_human_decision_request requires a GovernedStageCursor")
        decisions = tuple(allowed_decisions)
        if not decisions or any(
            decision not in ALLOWED_HUMAN_DECISIONS for decision in decisions
        ):
            raise RunCursorError(
                f"allowed_decisions must be a non-empty subset of {ALLOWED_HUMAN_DECISIONS}; "
                f"got {decisions!r}"
            )
        if self.pending_human_decision_request() is not None:
            raise RunCursorError(
                "a pending human decision request already exists for this run; "
                "resolve it before opening another"
            )

        payload = {
            "record_schema": DECISION_RECORD_SCHEMA,
            "request_id": (
                f"{self.run_id}/{self.task_id}/{cursor.stage_id}"
                f"/r{cursor.revision}/a{cursor.attempt}/request"
            ),
            "run_id": self.run_id,
            "task_id": self.task_id,
            "stage_id": cursor.stage_id,
            "revision": cursor.revision,
            "attempt": cursor.attempt,
            "reason": reason,
            "finding_universe_sha256": finding_universe_sha256,
            "input_sha256": input_sha256,
            "allowed_decisions": decisions,
            "state": "pending",
        }
        request_sha256 = _canonical_sha256(payload)
        advanced = self.record_stage(
            cursor,
            state="needs_input",
            data={HUMAN_DECISION_REQUEST_KEY: {**payload, "request_sha256": request_sha256}},
        )
        request = {
            **payload,
            "request_sha256": request_sha256,
            # The hash of the enclosing needs_input record, i.e. the cursor link
            # the request is bound to. Returned for the kernel's NodeEvent.extra;
            # the hash's own payload stays acyclic on purpose.
            "created_event_sha256": advanced.parent_event_sha256,
        }
        return advanced, request

    def pending_human_decision_request(self) -> dict | None:
        """The latest human-decision request that has not been consumed yet."""
        consumed = self.consumed_request_sha256s()
        pending: dict | None = None
        for event in self.journal.events():
            data = event.data if isinstance(event.data, dict) else {}
            request = data.get(HUMAN_DECISION_REQUEST_KEY)
            if not isinstance(request, dict):
                continue
            if request.get("request_sha256") not in consumed:
                pending = request
        return pending

    def consumed_request_sha256s(self) -> set[str]:
        """Every request hash a journalled human decision has already consumed."""
        consumed: set[str] = set()
        for event in self.journal.events():
            data = event.data if isinstance(event.data, dict) else {}
            decision = data.get(HUMAN_DECISION_KEY)
            if not isinstance(decision, dict):
                continue
            digest = decision.get("request_sha256")
            if isinstance(digest, str):
                consumed.add(digest)
        return consumed

    def consume_human_decision(
        self,
        task_id: str,
        *,
        request_sha256: str,
        decision: str,
        response: str,
        decided_by: str,
    ) -> GovernedStageCursor:
        """Match and journal one human decision against the pending request.

        Append-only and fail-closed: the decision must name the exact
        ``request_sha256`` of the run's current pending request, the decision
        must be from the closed ``retry|defer|block`` vocabulary, ``decided_by``
        must be ``"human"``, and a request hash that was already consumed (or an
        unknown one, or one with no pending request at all) is refused. The
        decision is journalled as its own ``human-decision-recorded`` record and
        the advanced cursor is returned -- this method never chooses a decision,
        never re-opens an attempt/revision, and never touches the fixer budget
        (a ``retry`` records ``retry_reset_iteration: 0`` for the kernel to read;
        the reset itself is the kernel's ``begin_attempt``).
        """
        if task_id != self.task_id:
            raise RunCursorError(
                f"task {task_id!r} is not this run's task {self.task_id!r}"
            )
        if decision not in ALLOWED_HUMAN_DECISIONS:
            raise RunCursorError(
                f"unknown human decision {decision!r}; allowed {ALLOWED_HUMAN_DECISIONS}"
            )
        if decided_by != HUMAN_DECIDED_BY:
            raise RunCursorError(
                f"a human decision must be decided_by={HUMAN_DECIDED_BY!r}, "
                f"not {decided_by!r}"
            )
        if (
            not isinstance(request_sha256, str)
            or len(request_sha256) != 64
            or set(request_sha256) > _HEX
        ):
            raise RunCursorError(
                "request_sha256 must be a canonical lowercase sha256 digest"
            )
        if request_sha256 in self.consumed_request_sha256s():
            raise RunCursorError(
                f"human decision request {request_sha256} was already consumed"
            )
        pending = self.pending_human_decision_request()
        if pending is None:
            raise RunCursorError(
                "no pending human decision request for this run to consume"
            )
        if pending.get("request_sha256") != request_sha256:
            raise RunCursorError(
                "mismatched human decision request hash: the pending request is "
                f"{pending.get('request_sha256')!r}, not {request_sha256!r}"
            )

        record = {
            "record_schema": DECISION_RECORD_SCHEMA,
            "decision_id": f"{pending['request_id']}/{decision}",
            "request_id": pending["request_id"],
            "request_sha256": request_sha256,
            "decision": decision,
            "response": response,
            "decided_by": decided_by,
            "decided_at": _now(),
            "stage_id": pending["stage_id"],
            "revision": pending["revision"],
            "attempt": pending["attempt"],
        }
        if decision == "retry":
            record["retry_reset_iteration"] = 0
        cursor = self._live_cursor(pending["stage_id"])
        return self.record_stage(
            cursor, state="human-decision-recorded", data={HUMAN_DECISION_KEY: record}
        )

    def _cursor_from_record(self, raw: dict, data: dict) -> GovernedStageCursor:
        """Rebuild one live cursor from a journalled stage record.

        The record stores the cursor as it stood *before* the record; the live
        cursor after it chains the record's own digest
        (``stage_event_sha256``). A record written before that digest existed
        degrades to its stored parent link rather than breaking resume.
        """
        try:
            cursor = GovernedStageCursor(
                stage_id=raw["stage_id"],
                revision=raw["revision"],
                attempt=raw["attempt"],
                parent_event_sha256=raw.get("parent_event_sha256"),
                attempt_key=raw["attempt_key"],
            )
        except (KeyError, ValueError) as exc:
            raise RunCursorError(f"corrupt governed stage record in the journal: {exc}") from exc
        digest = data.get("stage_event_sha256")
        if isinstance(digest, str) and len(digest) == 64 and set(digest) <= _HEX:
            return replace(cursor, parent_event_sha256=digest)
        return cursor


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
        """Build the next cursor, never reusing an attempt_key already on disk.

        ``attempt_key`` is a pure function of (run, task, stage, revision,
        attempt), so a restarted process that recomputed r1/a1 would collide with
        the record an earlier process wrote. ``restore_cursors`` fills
        :attr:`prior_attempt_keys`; here the requested position advances
        monotonically past anything already journalled, which makes a reused
        attempt_key impossible across a restart without changing the in-process
        semantics the accepted surface relies on.
        """
        revision = max(1, revision)
        attempt = max(1, attempt)
        key = self._attempt_key(stage_id, revision, attempt)
        while key in self.prior_attempt_keys:
            revision += 1
            key = self._attempt_key(stage_id, revision, attempt)
        while key in self.prior_attempt_keys:
            attempt += 1
            key = self._attempt_key(stage_id, revision, attempt)
        return GovernedStageCursor(
            stage_id=stage_id,
            revision=revision,
            attempt=attempt,
            parent_event_sha256=None,
            attempt_key=key,
        )

    def _attempt_key(self, stage_id: str, revision: int, attempt: int) -> str:
        return f"{self.run_id}/{self.task_id}/{stage_id}/r{revision}/a{attempt}/v1"

    def _invalidate_descendants(
        self,
        stage_id: str,
        cursors: dict[str, GovernedStageCursor] | None = None,
        invalidated: set[str] | None = None,
    ) -> None:
        """Every later stage in the canonical graph is stale after a revision.

        The entry is cleared again when that descendant opens a fresh revision
        (see ``begin_revision``); the set therefore describes staleness caused by
        the latest revision, not an ever-growing history.

        ``cursors``/``invalidated`` default to the live state; ``restore_cursors``
        passes its in-progress rebuild so a journalled revision invalidates the
        same descendants a live revision would have.
        """
        live = self.stage_cursors if cursors is None else cursors
        stale = self.invalidated_stages if invalidated is None else invalidated
        index = CANONICAL_EXECUTION_STAGES.index(stage_id)
        for descendant in CANONICAL_EXECUTION_STAGES[index + 1 :]:
            stale.add(descendant)
            live.pop(descendant, None)

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
