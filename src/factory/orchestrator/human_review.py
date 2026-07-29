from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass
class Annotation:
    file: str
    body: str
    line: int | None = None
    side: str | None = None
    severity: str | None = None


@dataclass
class HumanReviewDecision:
    decision: str  # "approve" or "reject"
    annotations: list[Annotation] = field(default_factory=list)


def _parse_annotations(payload: dict) -> list[Annotation]:
    raw = payload.get("annotations")
    if isinstance(raw, list):
        return [
            Annotation(
                file=a.get("file", ""),
                body=a.get("body", ""),
                line=a.get("line"),
                side=a.get("side"),
                severity=a.get("severity"),
            )
            for a in raw
            if isinstance(a, dict)
        ]
    # legacy shape: {"comments": {file: text}}
    legacy = payload.get("comments", {})
    return [Annotation(file=f, body=t) for f, t in legacy.items()]


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
        return HumanReviewDecision(
            decision=payload["decision"],
            annotations=_parse_annotations(payload),
        )


class FakeHumanReviewGate:
    def __init__(self, decisions: list[HumanReviewDecision]) -> None:
        self._decisions = list(decisions)
        self.requests: list[tuple[str, str]] = []

    def request_review(self, task_id: str, start_commit: str) -> HumanReviewDecision:
        self.requests.append((task_id, start_commit))
        assert self._decisions, "FakeHumanReviewGate: no scripted decision left"
        return self._decisions.pop(0)


def format_review_feedback(annotations: list[Annotation]) -> str:
    lines = ["human review requested changes:"]
    for a in annotations:
        loc = f"{a.file}:{a.line}" if a.line is not None else f"{a.file} (file)"
        sev = f" [{a.severity}]" if a.severity else ""
        lines.append(f"- {loc}{sev}: {a.body}")
    return "\n".join(lines)
