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


def _finding(identifier="F1", path="artifact.md", disposition="resolve_in_loop"):
    return {"id": identifier, "evidence": "bad", "confidence": 1.0,
            "disposition": disposition, "artifact_paths": [path]}


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
    finding = _finding()
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


def test_reviewer_provider_failure_escalates_instead_of_escaping(tmp_path: Path) -> None:
    source = tmp_path / "artifact.md"
    source.write_text("original", encoding="utf-8")

    class FailingBackend:
        def run(self, role, prompt, **kwargs):
            raise TimeoutError("provider timeout")

    loop = FreshReviewLoop(project_root=tmp_path, backend=FailingBackend(), model={"provider": "p", "model": "m"})
    packet = loop.build_packet("run-1", "spec_alignment", 1, [source], {}, "a" * 64)

    result = loop.run(packet)

    assert result.status is LoopStatus.ESCALATED
    assert "timeout" in (result.error or "")


def test_noop_scoped_fix_escalates_without_false_clean(tmp_path: Path) -> None:
    source = tmp_path / "artifact.md"
    source.write_text("original", encoding="utf-8")
    backend = Backend([])
    finding = {"id": "F1", "evidence": "needs change", "confidence": 1.0,
               "disposition": "resolve_in_loop", "artifact_paths": ["artifact.md"]}
    loop = FreshReviewLoop(project_root=tmp_path, backend=backend, model={"provider": "p", "model": "m"},
                           fixer=lambda path, _finding: None)
    packet = loop.build_packet("run-1", "spec_alignment", 1, [source], {}, "a" * 64)
    backend.reports = iter([_packet_report(packet, findings=[finding], verdict="findings")])

    result = loop.run(packet)

    assert result.status is LoopStatus.ESCALATED
    assert result.error == "scoped fix did not change an artifact"


def test_fix_is_scoped_and_fresh_review_runs_after_gate(tmp_path: Path) -> None:
    source = tmp_path / "artifact.md"
    other = tmp_path / "other.md"
    source.write_text("bad", encoding="utf-8")
    other.write_text("untouched", encoding="utf-8")
    backend = Backend([])
    finding = _finding(path="artifact.md")
    class FreshBackend(Backend):
        def run(self, role, prompt, **kwargs):
            self.calls.append((role, prompt))
            payload = json.loads(prompt.split("\n", 1)[1])
            assert payload["artifacts"] == sorted(payload["artifacts"], key=lambda item: item["path"])
            if len(self.calls) == 1:
                return AgentResult(ok=True, output={}, raw=json.dumps({**payload, "packet_sha256": hashlib.sha256(
                    json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest(),
                    "findings": [finding], "human_prompts": [], "notes": [], "verdict": "findings"}))
            return AgentResult(ok=True, output={}, raw=json.dumps({**payload, "packet_sha256": hashlib.sha256(
                json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest(),
                "findings": [], "human_prompts": [], "notes": [], "verdict": "clean"}))
    backend = FreshBackend([])
    first = FreshReviewLoop(project_root=tmp_path, backend=backend, model={"provider": "p", "model": "m"})
    packet = first.build_packet("run-1", "spec_alignment", 1, [source], {}, "a" * 64)
    assert [item["path"] for item in packet.artifacts] == ["artifact.md"]
    calls = []
    first.fixer = lambda path, _finding: (calls.append(path.name), path.write_text("good", encoding="utf-8"))
    first.gate = lambda root: calls.append("gate") or True
    result = first.run(packet)
    assert result.status is LoopStatus.CLEAN, result.error
    assert calls == ["artifact.md", "gate", "gate"]
    assert len(backend.calls) == 2
    assert other.read_text(encoding="utf-8") == "untouched"


@pytest.mark.parametrize("failure", [TimeoutError("timeout"), RuntimeError("provider")])
def test_reviewer_failure_escalates_fail_closed(tmp_path: Path, failure: Exception) -> None:
    source = tmp_path / "artifact.md"
    source.write_text("x", encoding="utf-8")
    class Failing:
        def run(self, *args, **kwargs):
            raise failure
    loop = FreshReviewLoop(project_root=tmp_path, backend=Failing(), model={"provider": "p", "model": "m"})
    packet = loop.build_packet("run-1", "spec_alignment", 1, [source], {}, "a" * 64)
    result = loop.run(packet)
    assert result.status is LoopStatus.ESCALATED
    assert "provider" in (result.error or "") or "timeout" in (result.error or "")


def test_repeated_finding_escalates_and_preserves_journal(tmp_path: Path) -> None:
    source = tmp_path / "artifact.md"
    source.write_text("bad", encoding="utf-8")
    backend = Backend([])
    finding = _finding()
    class RepeatBackend(Backend):
        def run(self, role, prompt, **kwargs):
            self.calls.append((role, prompt))
            payload = json.loads(prompt.split("\n", 1)[1])
            digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
            return AgentResult(ok=True, output={}, raw=json.dumps({**payload, "packet_sha256": digest,
                "findings": [finding], "human_prompts": [], "notes": [], "verdict": "findings"}))
    backend = RepeatBackend([])
    loop = FreshReviewLoop(project_root=tmp_path, backend=backend, model={"provider": "p", "model": "m"},
                           fixer=lambda path, _finding: path.write_text("still-bad", encoding="utf-8"), max_iterations=3)
    first = loop.build_packet("run-1", "spec_alignment", 1, [source], {}, "a" * 64)
    result = loop.run(first)
    assert result.status is LoopStatus.ESCALATED
    assert "repeated" in (result.error or "")
    assert len((tmp_path / ".factory" / "planning" / "run-1" / "resolution-events.jsonl").read_text().splitlines()) == 2


def test_terminal_gate_failure_escalates_fail_closed(tmp_path: Path) -> None:
    source = tmp_path / "artifact.md"
    source.write_text("original", encoding="utf-8")
    backend = Backend([])
    loop = FreshReviewLoop(
        project_root=tmp_path,
        backend=backend,
        model={"provider": "p", "model": "m"},
        gate=lambda _root: (_ for _ in ()).throw(RuntimeError("gate unavailable")),
    )
    packet = loop.build_packet("run-1", "spec_alignment", 1, [source], {}, "a" * 64)
    backend.reports = iter([_packet_report(packet)])

    result = loop.run(packet)

    assert result.status is LoopStatus.ESCALATED
    assert result.error == "gate unavailable"


def test_scoped_fix_rejects_collateral_artifact_mutation(tmp_path: Path) -> None:
    source = tmp_path / "artifact.md"
    other = tmp_path / "other.md"
    source.write_text("bad", encoding="utf-8")
    other.write_text("untouched", encoding="utf-8")
    finding = _finding(path="artifact.md")
    backend = Backend([])

    def collateral_fixer(path: Path, _finding: dict) -> None:
        path.write_text("good", encoding="utf-8")
        other.write_text("collateral", encoding="utf-8")

    loop = FreshReviewLoop(
        project_root=tmp_path,
        backend=backend,
        model={"provider": "p", "model": "m"},
        fixer=collateral_fixer,
    )
    packet = loop.build_packet("run-1", "spec_alignment", 1, [source, other], {}, "a" * 64)
    backend.reports = iter([_packet_report(packet, findings=[finding], verdict="findings")])

    result = loop.run(packet)

    assert result.status is LoopStatus.ESCALATED
    assert "outside finding scope" in (result.error or "")
    assert len(backend.calls) == 1


def test_human_finding_is_recorded_before_escalation(tmp_path: Path) -> None:
    source = tmp_path / "artifact.md"
    source.write_text("needs-human", encoding="utf-8")
    backend = Backend([])
    finding = _finding(disposition="escalate_to_human")
    loop = FreshReviewLoop(project_root=tmp_path, backend=backend, model={"provider": "p", "model": "m"})
    packet = loop.build_packet("run-1", "spec_alignment", 1, [source], {}, "a" * 64)
    backend.reports = iter([_packet_report(packet, findings=[finding], verdict="findings")])

    result = loop.run(packet)

    assert result.status is LoopStatus.ESCALATED
    events = (tmp_path / ".factory" / "planning" / "run-1" / "resolution-events.jsonl").read_text().splitlines()
    assert len(events) == 1
    assert json.loads(events[0])["disposition"] == "escalate_to_human"


def test_informational_finding_is_recorded_before_clean_gate(tmp_path: Path) -> None:
    source = tmp_path / "artifact.md"
    source.write_text("note", encoding="utf-8")
    backend = Backend([])
    finding = _finding(disposition="informational")
    loop = FreshReviewLoop(project_root=tmp_path, backend=backend, model={"provider": "p", "model": "m"})
    packet = loop.build_packet("run-1", "spec_alignment", 1, [source], {}, "a" * 64)
    backend.reports = iter([_packet_report(packet, findings=[finding], verdict="findings")])

    result = loop.run(packet)

    assert result.status is LoopStatus.CLEAN
    event = json.loads((tmp_path / ".factory" / "planning" / "run-1" / "resolution-events.jsonl").read_text())
    assert event["disposition"] == "informational"
    assert event["pre_artifact_hashes"] == event["post_artifact_hashes"]
