from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass
class PlaygroundSession:
    entrypoints: list[str] = field(default_factory=list)
    describe: str = ""
    on_teardown: Callable[[], None] | None = None

    def teardown(self) -> None:
        if self.on_teardown is not None:
            self.on_teardown()


@runtime_checkable
class Playground(Protocol):
    def list_usecases(self) -> list[str]: ...
    def setup(self, usecase: str) -> PlaygroundSession: ...
