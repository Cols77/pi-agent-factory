"""SR-034/SR-049 host seam: one leased workspace + one write policy, no allocator.

This module deliberately contains no worktree allocation, retry loop, scheduler
or per-role ownership. It defines only:

- :class:`WritePolicy` -- the harness-enforced denial rules (denied roots +
  declared allowlist). ``on_denied`` has exactly one legal value,
  ``"deny-and-evidence"``: the harness refuses the write and records the
  refusal as evidence. There is deliberately no ``"fail-task"`` mode
  (decision 2, 2026-09-11).
- :class:`WorkspaceLease` -- the frozen identity of one acquired execution
  workspace (execution id, path, policy) used as checkpoint evidence (SR-049).
- :class:`WorkspaceOwner` / :class:`BackendFactory` -- the protocols the driver
  and hosts depend on, implemented elsewhere (worktree allocation belongs to
  the caller, not here).
- :class:`BoundExecution` -- the frozen wrapper handed to the existing node
  seams: ``bound.backend`` is the unchanged ``AgentBackend`` and
  ``bound.assignment(lane)`` is the only worker-assignment construction path.
"""

from __future__ import annotations

import os
import tempfile
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from factory.orchestrator.backends import AgentBackend
from factory.orchestrator.execution_contract import (
    ExecutionContract,
    Lane,
    WorkerAssignment,
    workspace_prompt_suffix,
)

__all__ = [
    "BoundExecution",
    "BackendFactory",
    "DENY_AND_EVIDENCE",
    "WritePolicy",
    "WorkspaceLease",
    "WorkspaceOwner",
    "build_write_policy",
    "workspace_prompt_suffix",
]

# The single legal denial mode: refuse the write, keep the refusal as evidence.
DENY_AND_EVIDENCE = "deny-and-evidence"


@dataclass(frozen=True)
class WritePolicy:
    """Declarative write-denial rules carried by the lease into every binding.

    ``deny_outside_roots`` is the leased worktree root; ``allowed_roots`` is the
    declared carve-out list (session temp dir, tool cache roots, the shared
    ``.git`` objects, the transcript dir), so a deny is a rule decision rather
    than an ad-hoc check.
    """

    deny_outside_roots: tuple[Path, ...]
    allowed_roots: tuple[Path, ...]
    on_denied: str = DENY_AND_EVIDENCE

    def __post_init__(self) -> None:
        if self.on_denied != DENY_AND_EVIDENCE:
            raise ValueError(
                f"on_denied must be {DENY_AND_EVIDENCE!r}; there is no fail-task mode"
            )
        for field_name in ("deny_outside_roots", "allowed_roots"):
            roots = tuple(getattr(self, field_name))
            if any(not isinstance(root, Path) or not root.is_absolute() for root in roots):
                raise ValueError(f"{field_name} must contain only absolute paths")
            object.__setattr__(self, field_name, roots)
        if not self.deny_outside_roots:
            raise ValueError("deny_outside_roots must name the leased workspace root")


@dataclass(frozen=True)
class WorkspaceLease:
    """One acquired execution workspace: identity + path + write policy."""

    execution_id: str
    path: Path
    policy: WritePolicy

    def __post_init__(self) -> None:
        if not self.execution_id.strip():
            raise ValueError("execution_id must be a non-blank string")
        if not self.path.is_absolute():
            raise ValueError(f"lease path must be absolute: {self.path}")


class WorkspaceOwner(Protocol):
    """The driver's workspace provider. Allocation is the implementation's job."""

    def acquire(self, contract: ExecutionContract) -> AbstractContextManager[WorkspaceLease]: ...


class BackendFactory(Protocol):
    """Binds one backend to one lease; never schedules or allocates."""

    def bind(self, lease: WorkspaceLease, contract: ExecutionContract) -> BoundExecution: ...


@dataclass(frozen=True)
class BoundExecution:
    """One backend bound to one leased workspace and its write policy."""

    backend: AgentBackend
    contract: ExecutionContract
    workspace: Path
    policy: WritePolicy

    def assignment(self, lane: Lane) -> WorkerAssignment:
        """The only way the driver and hosts build a worker assignment."""
        return WorkerAssignment.for_lane(self.contract, lane, self.workspace)


def build_write_policy(
    workspace: Path, *, on_denied: str = DENY_AND_EVIDENCE, extra_allowed: tuple[Path, ...] = ()
) -> WritePolicy:
    """The default declared carve-out list for one leased workspace."""
    root = workspace.resolve()
    allowed = [
        Path(tempfile.gettempdir()).resolve(),
        Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")).resolve(),
        (root / ".git").resolve(),
        (root / ".factory" / "transcripts").resolve(),
        *(extra.resolve() for extra in extra_allowed),
    ]
    deduped = tuple(dict.fromkeys(allowed))
    return WritePolicy(deny_outside_roots=(root,), allowed_roots=deduped, on_denied=on_denied)
