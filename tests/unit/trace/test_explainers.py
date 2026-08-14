from __future__ import annotations

from pathlib import Path

import pytest

from factory.freshness.fingerprint import fingerprint_value
from factory.trace.explainers import list_fresh_explainers, load_explainers

pytestmark = pytest.mark.unit


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _sr(root: Path, sr_id: str, statement: str) -> str:
    content = (
        f"---\nid: {sr_id}\ntitle: T\ndomain: behavioral\nstatement: {statement}\n---\n\nbody\n"
    )
    _write(root / "requirements" / f"{sr_id}.md", content)
    return content


def _explainer(
    root: Path, slug: str, explains: list[str], fingerprints: dict, extra: dict | None = None
) -> None:
    fp_lines = "\n".join(f"    {k}: {v}" for k, v in fingerprints.items())
    body = ""
    if extra:
        body = "\n".join(f"{k}: {v}" for k, v in extra.items())
    text = (
        f"---\ntitle: {slug}\n"
        f"explains:\n" + "\n".join(f"  - {s}" for s in explains) + "\n"
        f"dep_fingerprint:\n{fp_lines}\n{body}---\n\n# {slug}\n"
    )
    _write(root / "docs" / "visual-explain" / f"{slug}.md", text)


def test_load_explainers_reads_links_and_fingerprints(tmp_path: Path):
    _explainer(tmp_path, "a", ["SR-001"], {"SR-001": "sha256:abc"})
    loaded = load_explainers(tmp_path)
    assert len(loaded) == 1
    assert loaded[0].id == "a.md"
    assert loaded[0].explains == ["SR-001"]
    assert loaded[0].fingerprints == {"SR-001": "sha256:abc"}


def test_load_explainers_empty_when_dir_missing(tmp_path: Path):
    assert load_explainers(tmp_path) == []


def test_list_fresh_returns_relevant_up_to_date_explainer(tmp_path: Path):
    content = _sr(tmp_path, "SR-001", "scan")
    digest = fingerprint_value("SR-001", content).digest
    _explainer(tmp_path, "scan-arch", ["SR-001"], {"SR-001": digest})
    fresh = list_fresh_explainers(tmp_path, ["SR-001"])
    assert [e.id for e in fresh] == ["scan-arch.md"]


def test_list_fresh_ignores_explainer_with_no_links(tmp_path: Path):
    _sr(tmp_path, "SR-001", "scan")
    _explainer(tmp_path, "orphan", [], {})
    assert list_fresh_explainers(tmp_path, ["SR-001"]) == []


def test_list_fresh_ignores_explainer_with_no_recorded_fingerprint(tmp_path: Path):
    _sr(tmp_path, "SR-001", "scan")
    _explainer(tmp_path, "no-fp", ["SR-001"], {})
    assert list_fresh_explainers(tmp_path, ["SR-001"]) == []


def test_list_fresh_filters_out_stale_explainer(tmp_path: Path):
    content = _sr(tmp_path, "SR-001", "scan")
    digest = fingerprint_value("SR-001", content).digest
    # Record a digest that no longer matches current content.
    _explainer(tmp_path, "stale", ["SR-001"], {"SR-001": "sha256:old"})
    _explainer(tmp_path, "fresh", ["SR-001"], {"SR-001": digest})
    fresh = list_fresh_explainers(tmp_path, ["SR-001"])
    assert [e.id for e in fresh] == ["fresh.md"]


def test_list_fresh_is_relevance_filtered(tmp_path: Path):
    content = _sr(tmp_path, "SR-001", "scan")
    digest = fingerprint_value("SR-001", content).digest
    _explainer(tmp_path, "other", ["SR-999"], {"SR-999": digest})  # fresh but not our SR
    assert list_fresh_explainers(tmp_path, ["SR-001"]) == []


def test_list_fresh_requires_all_linked_targets_fresh(tmp_path: Path):
    c1 = _sr(tmp_path, "SR-001", "scan")
    _sr(tmp_path, "SR-002", "detect")
    d1 = fingerprint_value("SR-001", c1).digest
    _explainer(tmp_path, "partial", ["SR-001", "SR-002"], {"SR-001": d1, "SR-002": "sha256:stale"})
    assert list_fresh_explainers(tmp_path, ["SR-001"]) == []
