from pathlib import Path

import pytest

from factory.system.labels import build_alias_map, build_labels, normalize_ref

from . import _fixtures

# Required: pyproject.toml:31 sets addopts = "-m unit". Without this marker
# every test here is deselected and pytest exits 5.
pytestmark = pytest.mark.unit


def test_normalize_bare_task_id(tmp_path: Path) -> None:
    _fixtures.write_task(tmp_path / "tasks", "T-060", title="Wire the governor")
    assert normalize_ref(tmp_path, "T-060") == "task:T-060"


def test_normalize_prefixed_task_ref_is_idempotent(tmp_path: Path) -> None:
    _fixtures.write_task(tmp_path / "tasks", "T-060", title="Wire the governor")
    assert normalize_ref(tmp_path, "task:T-060") == "task:T-060"


def test_normalize_spec_basename_resolves_to_path_form(tmp_path: Path) -> None:
    _fixtures.write_spec(tmp_path, "2026-07-16-foo-design.md", title="Foo")
    canonical = "spec:docs/superpowers/specs/2026-07-16-foo-design.md"
    assert normalize_ref(tmp_path, "spec:2026-07-16-foo-design.md") == canonical
    assert normalize_ref(tmp_path, canonical) == canonical


def test_normalize_unresolvable_returns_none(tmp_path: Path) -> None:
    assert normalize_ref(tmp_path, "T-999") is None
    assert normalize_ref(tmp_path, "nonsense") is None


def test_alias_map_contains_basename_and_bare_forms(tmp_path: Path) -> None:
    _fixtures.write_spec(tmp_path, "2026-07-16-foo-design.md", title="Foo")
    _fixtures.write_task(tmp_path / "tasks", "T-060", title="Wire the governor")
    aliases = build_alias_map(tmp_path)
    assert aliases["spec:2026-07-16-foo-design.md"] == (
        "spec:docs/superpowers/specs/2026-07-16-foo-design.md"
    )
    assert aliases["T-060"] == "task:T-060"


def test_sr_description_is_the_statement(tmp_path):
    _fixtures.write_sr(tmp_path / "requirements", "SR-121",
                       title="Battery-aware return",
                       statement="The system shall return to base.")
    entry = build_labels(tmp_path)["labels"]["sr:SR-121"]
    assert entry["title"] == "Battery-aware return"
    assert entry["description"] == "The system shall return to base."
    assert entry["description_source"] == "statement"
    assert entry["scope_href"] == "/system?scope=sr%3ASR-121"


def test_task_has_no_description_but_carries_relations(tmp_path):
    _fixtures.write_sr(tmp_path / "requirements", "SR-121", title="Battery")
    _fixtures.write_task(tmp_path / "tasks", "T-060", title="Wire the governor",
                         satisfies=["SR-121"])
    entry = build_labels(tmp_path)["labels"]["task:T-060"]
    assert entry["title"] == "Wire the governor"
    assert entry["description"] is None
    assert entry["description_source"] is None
    assert entry["relations"]["satisfies"] == ["sr:SR-121"]


def test_adr_entries_exist_even_though_the_graph_has_no_adr_nodes(tmp_path):
    # trace/model.py:102 emits no adr nodes -- ADRs come from load_adrs.
    adr_dir = tmp_path / "docs" / "adr"
    adr_dir.mkdir(parents=True)
    (adr_dir / "0001-use-bundles.md").write_text(
        "---\nid: ADR-0001\ntitle: Use bundles\nstatus: accepted\n---\n\n"
        "## Context\n\nSomething.\n\n## Decision\n\nWe group by feature bundle.\n",
        encoding="utf-8",
    )
    entry = build_labels(tmp_path)["labels"]["adr:ADR-0001"]
    assert entry["title"] == "Use bundles"
    assert entry["description"] == "We group by feature bundle."
    assert entry["description_source"] == "decision"


def test_deferral_reason_comes_from_the_trace_node(tmp_path):
    # Requirement has no trace_deferred attribute; Node.deferred does
    # (trace/model.py:34, populated by _disposition at :48).
    reqs = tmp_path / "requirements"
    reqs.mkdir(parents=True)
    (reqs / "SR-002.md").write_text(
        "---\nid: SR-002\ntitle: Battery\nstatement: Shall return.\n"
        "domain: behavioral\nupstream: []\n"
        "trace_deferred: No candidate task covers the 5% floor.\n---\n",
        encoding="utf-8",
    )
    entry = build_labels(tmp_path)["labels"]["sr:SR-002"]
    assert entry["deferral_reason"] == "No candidate task covers the 5% floor."


def test_spec_is_not_an_openable_scope(tmp_path):
    _fixtures.write_spec(tmp_path, "2026-07-16-foo-design.md", title="Foo")
    entry = build_labels(tmp_path)["labels"][
        "spec:docs/superpowers/specs/2026-07-16-foo-design.md"
    ]
    assert entry["scope_href"] is None


def test_aliases_resolve_the_basename_spelling(tmp_path):
    _fixtures.write_spec(tmp_path, "2026-07-16-foo-design.md", title="Foo")
    payload = build_labels(tmp_path)
    canonical = payload["aliases"]["spec:2026-07-16-foo-design.md"]
    assert canonical in payload["labels"]
