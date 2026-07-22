from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from typing import IO, Protocol


@dataclass
class HumanReviewDecision:
    decision: str  # "approve" or "reject"
    comments: dict[str, str] = field(default_factory=dict)


class HumanReviewGate(Protocol):
    def request_review(self, task_id: str, start_commit: str) -> HumanReviewDecision: ...


class StdioHumanReviewGate:
    def __init__(self, stdout: IO[str] = sys.stdout, stdin: IO[str] = sys.stdin) -> None:
        self._stdout = stdout
        self._stdin = stdin

    def request_review(self, task_id: str, start_commit: str) -> HumanReviewDecision:
        self._stdout.write(
            json.dumps({"type": "review_pending", "task_id": task_id, "start_commit": start_commit}) + "\n"
        )
        self._stdout.flush()
        line = self._stdin.readline()
        if not line:
            raise EOFError("human review gate: stdin closed before a decision was received")
        payload = json.loads(line)
        return HumanReviewDecision(decision=payload["decision"], comments=payload.get("comments", {}))


class FakeHumanReviewGate:
    def __init__(self, decisions: list[HumanReviewDecision]) -> None:
        self._decisions = list(decisions)
        self.requests: list[tuple[str, str]] = []

    def request_review(self, task_id: str, start_commit: str) -> HumanReviewDecision:
        self.requests.append((task_id, start_commit))
        assert self._decisions, "FakeHumanReviewGate: no scripted decision left"
        return self._decisions.pop(0)


def format_review_feedback(comments: dict[str, str]) -> str:
    lines = ["human review requested changes:"]
    lines.extend(f"- {file}: {text}" for file, text in comments.items())
    return "\n".join(lines)
