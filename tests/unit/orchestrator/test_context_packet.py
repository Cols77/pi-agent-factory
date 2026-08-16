from __future__ import annotations

import pathlib
import pytest

from factory.orchestrator.context_packet import (
    build_context_packet,
    read_context_packet,
    write_context_packet,
    primary_paths,
    render_packet,
    signature_summary_for_file,
)
from factory.orchestrator.ledger import Task
from factory.orchestrator.prompts import compose_prompt
from factory.orchestrator.types import AgentRole
from ._skill_fixtures import write_skill_stubs

pytestmark = pytest.mark.unit


def _task(body: str, task_id: str = "T-001") -> Task:
    return Task(
        id=task_id,
        title="t",
        status="todo",
        dod=["x"],
        body=body,
        path=pathlib.Path(f"tasks/{task_id}.md"),
    )


def _make_tree(tmp_path):
    (tmp_path / "src").mkdir(parents=True, exist_ok=True)
    (tmp_path / "src" / "mod.py").write_text(
        '"""Module purpose line."""\n\ndef alpha(a, b):\n    """Returns a+b."""\n    return a + b\n\n'
        "class Beta:\n    \"\"\"Beta class docs.\"\"\"\n    def method(self, x):\n        return x\n",
        encoding="utf-8",
    )
    (tmp_path / "src" / "big.py").write_text("# big\n" + "x = 0\n" * 5000, encoding="utf-8")
    (tmp_path / "src" / "notes.md").write_text("# Notes\n", encoding="utf-8")
    return tmp_path


def _manifest(task_id: str, source_files: list[str]) -> dict:
    return {
        "task_id": task_id,
        "generated_by": "context-gatherer",
        "generated_at": "t",
        "coherence": {"checks": []},
        "context": {"task": f"tasks/{task_id}.md", "source_files": source_files, "skills": []},
    }


def test_primary_paths_intersects_deliverables_with_source_files(tmp_path):
    task = _task("- Modify: `src/mod.py`\n- Create: `src/out.py`\n")
    manifest = _manifest("T-001", ["src/mod.py", "README.md"])
    assert primary_paths(task, manifest) == {"src/mod.py"}


def test_primary_file_gets_full_content(tmp_path):
    root = _make_tree(tmp_path)
    task = _task("- Modify: `src/mod.py`", "T-001")
    manifest = _manifest("T-001", ["src/mod.py"])
    packet = build_context_packet(task, manifest, root)
    entry = packet["files"]["src/mod.py"]
    assert entry["primary"] is True
    assert entry["kind"] == "content"
    assert "def alpha" in entry["content"]


def test_reference_file_gets_signatures(tmp_path):
    root = _make_tree(tmp_path)
    task = _task("- Modify: `src/notes.md`", "T-001")
    manifest = _manifest("T-001", ["src/mod.py", "src/notes.md"])
    packet = build_context_packet(task, manifest, root)
    mod = packet["files"]["src/mod.py"]
    assert mod["primary"] is False
    assert mod["kind"] == "signatures"
    names = {s["name"] for s in mod["signatures"]}
    assert names == {"alpha", "Beta", "method"}
    # a method got a method kind
    method = [s for s in mod["signatures"] if s["name"] == "method"][0]
    assert method["kind"] == "method"


def test_missing_file_recorded_not_fatal(tmp_path):
    root = _make_tree(tmp_path)
    task = _task("", "T-001")
    manifest = _manifest("T-001", ["src/does-not-exist.py"])
    packet = build_context_packet(task, manifest, root)
    assert packet["missing"] == ["src/does-not-exist.py"]


def test_primary_over_cap_falls_back_to_signatures(tmp_path, monkeypatch):
    root = _make_tree(tmp_path)
    monkeypatch.setenv("FACTORY_PACKET_PRIMARY_CAP_CHARS", "200")
    # force reload of the module caps by re-reading via env is not trivial; instead
    # build with a huge primary that exceeds default cap: big.py is >12000 chars.
    task = _task("- Modify: `src/big.py`", "T-001")
    manifest = _manifest("T-001", ["src/big.py"])
    packet = build_context_packet(task, manifest, root)
    entry = packet["files"]["src/big.py"]
    assert entry["kind"] == "signatures"
    assert entry["reason"] == "over-cap primary file"


def test_render_packet_is_closed_and_deterministic(tmp_path):
    root = _make_tree(tmp_path)
    task = _task("- Modify: `src/mod.py`", "T-001")
    manifest = _manifest("T-001", ["src/mod.py", "src/notes.md", "src/missing.py"])
    packet = build_context_packet(task, manifest, root)
    out1 = render_packet(packet)
    out2 = render_packet(packet)
    assert out1 == out2
    assert "PRIMARY" in out1
    assert "src/missing.py" not in out1  # missing file noted, not rendered
    assert "missing" in out1


def test_signature_summary_for_file_bounds_sigs(tmp_path):
    root = _make_tree(tmp_path)
    sigs = signature_summary_for_file("src/mod.py", root, max_sigs=2)
    assert len(sigs) == 2


def test_write_read_round_trip(tmp_path):
    transcript = tmp_path / "tr"
    packet = {"schema": 1, "task_id": "T-001", "files": {}}
    write_context_packet(packet, transcript)
    assert read_context_packet(transcript) == packet
    # missing dir returns None
    assert read_context_packet(transcript / "nope") is None


def test_compose_prompt_packet_embeds_content_instead_of_bullets(tmp_path):
    skills = tmp_path / "skills"
    write_skill_stubs(skills)
    root = _make_tree(tmp_path / "tree")
    task = _task("- Modify: `src/mod.py`", "T-001")
    manifest = _manifest("T-001", ["src/mod.py"])
    packet = build_context_packet(task, manifest, root)

    with_packet = compose_prompt(
        AgentRole.DEV, task, manifest, skills_dir=skills, packet=packet
    )
    assert "def alpha" in with_packet
    assert "## Context packet" in with_packet

    without_packet = compose_prompt(AgentRole.DEV, task, manifest, skills_dir=skills)
    assert "## Context (from manifest)" in without_packet
    assert "src/mod.py" in without_packet
    assert "## Context packet" not in without_packet

