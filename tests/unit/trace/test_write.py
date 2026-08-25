from __future__ import annotations

from pathlib import Path

import frontmatter
import pytest
from factory.trace.write import (
    link_satisfies,
    link_source_plan,
    link_spec,
    set_deferred,
    set_exempt,
)

pytestmark = pytest.mark.unit


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _repo(tmp_path: Path) -> Path:
    _write(
        tmp_path / "tasks" / "T-001.md",
        "---\nid: T-001\ntitle: Thing\nstatus: todo\ndod: []\n---\n\nbody\n",
    )
    _write(
        tmp_path / "requirements" / "SR-001.md",
        "---\nid: SR-001\ntitle: t\nstatement: s\ndomain: d\n"
        "binding:\n  harness: h\n  experiment: e\n  metric: m\n  assert: '>= 0.9'\n---\n",
    )
    _write(tmp_path / "docs" / "superpowers" / "plans" / "p1.md", "# Plan One\n\nbody\n")
    _write(tmp_path / "docs" / "superpowers" / "specs" / "s1.md", "# Spec One\n")
    return tmp_path


def test_link_satisfies_writes_the_edge_and_preserves_the_body(tmp_path):
    root = _repo(tmp_path)

    path = link_satisfies(root, "T-001", "SR-001")

    post = frontmatter.load(str(path))
    assert post["satisfies"] == ["SR-001"]
    assert post["title"] == "Thing"
    assert "body" in post.content


def test_link_satisfies_is_idempotent(tmp_path):
    root = _repo(tmp_path)

    link_satisfies(root, "T-001", "SR-001")
    path = link_satisfies(root, "T-001", "SR-001")

    assert frontmatter.load(str(path))["satisfies"] == ["SR-001"]


def test_link_satisfies_refuses_a_missing_requirement(tmp_path):
    # A confirmed link must never create a fresh dangling reference. Spec section 6.4.
    root = _repo(tmp_path)

    with pytest.raises(ValueError, match="SR-999"):
        link_satisfies(root, "T-001", "SR-999")


def test_link_spec_appends_a_literal_path_the_reader_will_parse(tmp_path):
    root = _repo(tmp_path)

    path = link_spec(root, "plan:p1.md", "s1.md")

    assert "docs/superpowers/specs/s1.md" in path.read_text(encoding="utf-8")


def test_link_spec_refuses_a_missing_spec(tmp_path):
    root = _repo(tmp_path)

    with pytest.raises(ValueError, match="gone.md"):
        link_spec(root, "plan:p1.md", "gone.md")


def test_link_source_plan_writes_the_repo_relative_path(tmp_path):
    # task_no_plan must be closable, not only deferrable.
    root = _repo(tmp_path)

    path = link_source_plan(root, "T-001", "p1.md")

    assert frontmatter.load(str(path))["source_plan"] == "docs/superpowers/plans/p1.md"


def test_link_source_plan_refuses_a_missing_plan(tmp_path):
    with pytest.raises(ValueError, match="gone.md"):
        link_source_plan(_repo(tmp_path), "T-001", "gone.md")


def test_set_exempt_and_set_deferred_write_frontmatter(tmp_path):
    root = _repo(tmp_path)

    set_exempt(root, "T-001", "tooling task, no SR applies")
    post = frontmatter.load(str(root / "tasks" / "T-001.md"))
    assert post["trace_exempt"] is True
    assert post["trace_exempt_reason"] == "tooling task, no SR applies"

    set_deferred(root, "T-001", "needs an SR split")
    post = frontmatter.load(str(root / "tasks" / "T-001.md"))
    assert post["trace_deferred"] == "needs an SR split"

    # Structured write (Inc 6 Task 3): review_after switches trace_deferred to
    # the expiring dict form; the trace reader still renders the same reason.
    set_deferred(root, "T-001", "needs an SR split", review_after="2026-09-01T00:00:00Z")
    post = frontmatter.load(str(root / "tasks" / "T-001.md"))
    structured = post["trace_deferred"]
    assert isinstance(structured, dict)
    assert structured["reason"] == "needs an SR split"
    assert structured["review_after"] == "2026-09-01T00:00:00Z"
    from coherence.trace.model import load_nodes

    assert {n.id: n for n in load_nodes(root)}["T-001"].deferred == "needs an SR split"


def test_set_deferred_on_a_plan_that_has_no_frontmatter(tmp_path):
    root = _repo(tmp_path)

    path = set_deferred(root, "plan:p1.md", "spec not written yet")

    post = frontmatter.load(str(path))
    assert post["trace_deferred"] == "spec not written yet"
    assert "# Plan One" in post.content


def test_set_exempt_refuses_a_requirement(tmp_path):
    # Spec 4.4: SRs are not exemptable. Defer them instead.
    with pytest.raises(ValueError, match="cannot be exempted"):
        set_exempt(_repo(tmp_path), "SR-001", "inconvenient")


def test_unknown_node_raises(tmp_path):
    with pytest.raises(LookupError):
        set_exempt(_repo(tmp_path), "T-404", "nope")


def test_link_satisfies_does_not_rewrite_an_unrelated_spec_document(tmp_path):
    # Task 1: the link/unlink writers must only touch the requested node (the
    # task), never rewrite a co-located, unrelated spec document. A spec whose
    # canonical frontmatter id makes it resolvable must be left byte-identical.
    root = tmp_path
    _write(
        root / "docs" / "superpowers" / "specs" / "coherence.md",
        "---\nid: SPEC-COHERENCE-001\ntitle: Coherence\nstatus: accepted\n---\n\n# Coherence\n\nbody\n",
    )
    spec_path = root / "docs" / "superpowers" / "specs" / "coherence.md"
    before = spec_path.read_bytes()
    _write(
        root / "tasks" / "T-001.md",
        "---\nid: T-001\ntitle: Thing\nstatus: todo\ndod: []\n---\n\nbody\n",
    )
    _write(
        root / "requirements" / "SR-001.md",
        "---\nid: SR-001\ntitle: t\nstatement: s\ndomain: d\n"
        "binding:\n  harness: h\n  experiment: e\n  metric: m\n  assert: '>= 0.9'\n---\n",
    )

    link_satisfies(root, "T-001", "SR-001")

    assert spec_path.read_bytes() == before
