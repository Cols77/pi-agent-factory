from __future__ import annotations

import dataclasses
import itertools
from collections.abc import Callable

from factory.polish.finding import Finding


def _seq_ids(prefix: str) -> Callable[[], str]:
    counter = itertools.count(1)
    return lambda: f"{prefix}{next(counter)}"


class Gate1:
    """Pre-queue glance: a synthesized finding waits here for accept/edit/discard
    before it enters the fix queue. Nothing is enqueued without passing Gate 1."""

    def __init__(self, next_id: Callable[[], str] | None = None) -> None:
        self._next_id = next_id or _seq_ids("g1-")
        self._pending: dict[str, Finding] = {}

    def add(self, finding: Finding) -> str:
        gid = self._next_id()
        self._pending[gid] = finding
        return gid

    def pending(self) -> dict[str, Finding]:
        return dict(self._pending)

    def accept(self, gid: str) -> Finding:
        return self._pending.pop(gid)

    def edit(self, gid: str, **changes) -> Finding:
        finding = dataclasses.replace(self._pending.pop(gid), **changes)
        return finding

    def discard(self, gid: str) -> None:
        self._pending.pop(gid, None)
