from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass
class HumanReviewDecision:
    decision: str  # "approve" or "reject"
    comments: dict[str, str] = field(default_factory=dict)


class HumanReviewGate(Protocol):
    def request_review(self, task_id: str, start_commit: str) -> HumanReviewDecision: ...


class FileHumanReviewGate:
    def __init__(self, transcript_dir: Path, poll_interval: float = 1.0) -> None:
        self._decision_path = transcript_dir / "review-decision.json"
        self._poll_interval = poll_interval

    def request_review(self, task_id: str, start_commit: str) -> HumanReviewDecision:
        while not self._decision_path.exists():
            time.sleep(self._poll_interval)
        payload = json.loads(self._decision_path.read_text(encoding="utf-8"))
        self._decision_path.unlink()
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
