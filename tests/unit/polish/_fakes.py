"""Shared headless fakes for polish orchestrator tests (no LLM, no subprocess)."""
from pathlib import Path

from factory.orchestrator.backends import FakeAgentBackend
from factory.orchestrator.types import AgentResult, AgentRole
from factory.polish.orchestrator import PolishOrchestrator
from factory.polish.playground import PlaygroundSession
from factory.polish.worker import FixWorker, LandedChange


class StubPlayground:
    def list_usecases(self):
        return ["sign-in"]

    def setup(self, usecase):
        return PlaygroundSession(entrypoints=["http://x"], describe="up")


class FakeExecutor:
    """Stands in for WorktreeIsolatedExecutor: lands every finding."""

    def __init__(self):
        self.n = 0

    def execute(self, finding):
        self.n += 1
        return LandedChange(
            finding=finding,
            task_path=Path(f"tasks/T-{self.n:03d}.md"),
            task_id=f"T-{self.n:03d}",
            status="landed",
        )


def make_orchestrator(findings) -> PolishOrchestrator:
    backend = FakeAgentBackend(
        {AgentRole.SYNTHESIS: [AgentResult(ok=True, output={"findings": findings})]}
    )
    return PolishOrchestrator(
        StubPlayground(), backend, FixWorker(FakeExecutor()), open_nav=lambda e: None
    )
