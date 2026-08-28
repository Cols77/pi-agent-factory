from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from coherence.navigate.requirements_context import query_requirements_context

pytestmark = pytest.mark.unit


def _write_sr(root: Path, name: str, *, statement: str, extra: str = "") -> None:
    path = root / "requirements" / f"{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\nid: {name}\ntitle: {name} title\ndomain: behavioral\n"
        f"statement: {statement}\n{extra}---\nBody for {name}.\n",
        encoding="utf-8",
    )


def test_context_includes_full_non_deleted_sr_with_status_and_relationships(tmp_path: Path) -> None:
    _write_sr(tmp_path, "SR-002", statement="The system shall avoid duplicate alerts.", extra="upstream: [SR-001]\nsource: docs/spec.md#4\nbinding: {experiment: E, metric: m, assert: '>=0'}\n")
    _write_sr(tmp_path, "SR-001", statement="The system shall emit one alert.")
    _write_sr(tmp_path, "SR-003", statement="old", extra="deleted: true\n")
    tasks = tmp_path / "tasks"
    tasks.mkdir()
    (tasks / "T-001.md").write_text(
        "---\nid: T-001\ntitle: Implement alert\nstatus: done\ndod: [x]\n"
        "justification: [{satisfies: SR-001}]\n---\n",
        encoding="utf-8",
    )
    result = query_requirements_context(tmp_path)

    assert [item["id"] for item in result["requirements"]] == ["SR-001", "SR-002"]
    first = result["requirements"][0]
    assert first["statement"] == "The system shall emit one alert."
    assert first["content"] == "Body for SR-001."
    assert first["status"] == "satisfied"
    second = result["requirements"][1]
    assert second["status"] == "active"
    assert second["source_anchors"] == ["docs/spec.md#4"]
    assert second["relationships"]["upstream"] == ["SR-001"]
    assert second["relationships"]["downstream"] == []
    assert second["relationships"]["tasks"] == []
    assert first["relationships"]["downstream"] == ["SR-002"]
    assert result["deferred"] == {"token_efficient_retrieval": True}


def test_context_digest_and_order_are_stable_and_read_only(tmp_path: Path) -> None:
    _write_sr(tmp_path, "SR-010", statement="A requirement.")
    before = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*"))
    left = query_requirements_context(tmp_path)
    right = query_requirements_context(tmp_path)
    assert left == right
    assert left["context_digest"].startswith("sha256:")
    canonical = json.dumps(left["requirements"], sort_keys=True, separators=(",", ":"))
    assert left["context_digest"] == "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()
    assert sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*")) == before


def test_invalid_sr_is_diagnosed_without_hiding_valid_context(tmp_path: Path) -> None:
    _write_sr(tmp_path, "SR-001", statement="valid")
    bad = tmp_path / "requirements" / "SR-999.md"
    bad.write_text("---\nid: SR-999\ntitle: broken\n---\n", encoding="utf-8")
    result = query_requirements_context(tmp_path)
    assert [item["id"] for item in result["requirements"]] == ["SR-001"]
    assert result["diagnostics"]
    assert "SR-999.md" in result["diagnostics"][0]["path"]
