from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from coherence.planning.loop import FreshReviewLoop, LoopStatus
from substrate.agents.model import AgentResult

pytestmark = pytest.mark.unit


def _packet_report(packet, *, findings=(), verdict="clean") -> str:
    return json.dumps({
        **packet.to_dict(),
        "packet_sha256": packet.sha256,
        "findings": list(findings),
        "human_prompts": [], "notes": [], "verdict": verdict,
    })


class Backend:
    def __init__(self, reports):
        self.reports = iter(reports)
        self.calls = []

    def run(self, role, prompt, **kwargs):
        self.calls.append((role, prompt))
        return AgentResult(ok=True, output={}, raw=next(self.reports), session_id=f"s{len(self.calls)}")


def test_fresh_loop_calls_reviewer_and_returns_clean(tmp_path: Path) -> None:
    source = tmp_path / "artifact.md"
    source.write_text("original", encoding="utf-8")
    backend = Backend([])
    loop = FreshReviewLoop(project_root=tmp_path, backend=backend, model={"provider": "p", "model": "m"})
    packet = loop.build_packet("run-1", "spec_alignment", 1, [source], {}, "a" * 64)
    backend.reports = iter([_packet_report(packet)])

    result = loop.run(packet)

    assert result.status is LoopStatus.CLEAN
    assert len(backend.calls) == 1


def test_fresh_loop_applies_fix_then_uses_fresh_packet_and_journal(tmp_path: Path) -> None:
    source = tmp_path / "artifact.md"
    source.write_text("bad", encoding="utf-8")
    backend = Backend([])
    finding = {"id": "F1", "evidence": "bad", "confidence": 1.0, "disposition": "resolve_in_loop"}
    loop = FreshReviewLoop(project_root=tmp_path, backend=backend, model={"provider": "p", "model": "m"},
                           fixer=lambda path, _finding: path.write_text("good", encoding="utf-8"))
    first = loop.build_packet("run-1", "spec_alignment", 1, [source], {}, "a" * 64)
    backend.reports = iter([_packet_report(first, findings=[finding], verdict="findings")])
    original_run = loop.run

    result = original_run(first)

    assert result.status is LoopStatus.ESCALATED
    assert source.read_text(encoding="utf-8") == "good"
    journal = tmp_path / ".factory" / "planning" / "run-1" / "resolution-events.jsonl"
    assert journal.exists()
    assert hashlib.sha256(source.read_bytes()).hexdigest() in journal.read_text(encoding="utf-8")
