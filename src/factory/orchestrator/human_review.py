from __future__ import annotations

import json
import subprocess
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
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
    reviewed_files: list[str] = field(default_factory=list)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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
    def __init__(
        self,
        transcript_dir: Path,
        repo_root: Path | None = None,
        poll_interval: float = 1.0,
    ) -> None:
        self._transcript_dir = transcript_dir
        self._decision_path = transcript_dir / "review-decision.json"
        self._repo_root = repo_root
        self._poll_interval = poll_interval

    def _archive(self, task_id: str, start_commit: str, decision: HumanReviewDecision) -> None:
        """Preserve the exact reviewed working-tree diff before a retry mutates it."""
        reviews_dir = self._transcript_dir / "reviews"
        reviews_dir.mkdir(parents=True, exist_ok=True)
        sequence = 1
        while (reviews_dir / f"review-{sequence:03}.json").exists():
            sequence += 1

        diff = ""
        diff_error: str | None = None
        if self._repo_root is None:
            diff_error = "repository unavailable; diff was not captured"
        else:
            result = subprocess.run(
                ["git", "diff", "--binary", start_commit],
                cwd=self._repo_root,
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                diff = result.stdout
            else:
                diff_error = result.stderr.strip() or f"git diff exited {result.returncode}"

        record = {
            "version": 1,
            "reviewed_at": _now(),
            "task_id": task_id,
            "start_commit": start_commit,
            "decision": decision.decision,
            "annotations": [asdict(annotation) for annotation in decision.annotations],
            "reviewed_files": decision.reviewed_files,
            "diff": diff,
            "diff_error": diff_error,
        }
        # A review archive is append-only evidence.  Write it before consuming
        # the handoff file, so an I/O failure cannot silently erase a review;
        # publish only a complete JSON document for the browser to discover.
        path = reviews_dir / f"review-{sequence:03}.json"
        tmp_path = path.with_name(path.name + ".tmp")
        tmp_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
        tmp_path.replace(path)

    def request_review(self, task_id: str, start_commit: str) -> HumanReviewDecision:
        while not self._decision_path.exists():
            time.sleep(self._poll_interval)
        payload = json.loads(self._decision_path.read_text(encoding="utf-8"))
        reviewed_files = payload.get("reviewedFiles", [])
        decision = HumanReviewDecision(
            decision=payload["decision"],
            annotations=_parse_annotations(payload),
            reviewed_files=[file for file in reviewed_files if isinstance(file, str)]
            if isinstance(reviewed_files, list)
            else [],
        )
        self._archive(task_id, start_commit, decision)
        self._decision_path.unlink()
        return decision


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
