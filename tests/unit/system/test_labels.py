from pathlib import Path

import pytest

from factory.system.labels import build_alias_map, build_labels, file_entry, normalize_ref

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


def test_task_relations_carry_the_canonical_source_plan_ref(tmp_path):
    # I3: Task.source_plan (ledger.py:23) is recorded as the bare
    # repo-relative path, with no `plan:` prefix -- must resolve to the
    # canonical `plan:<path>` ref the same way `satisfies` resolves bare SR
    # ids, and be carried in `relations` (design:112's contract example).
    _fixtures.write_plan(tmp_path, "2026-07-20-factory-plan-and-run.md", title="Factory plan")
    _fixtures.write_task(
        tmp_path / "tasks", "T-060", title="Wire the governor",
        source_plan="docs/superpowers/plans/2026-07-20-factory-plan-and-run.md",
    )
    entry = build_labels(tmp_path)["labels"]["task:T-060"]
    assert entry["relations"]["source_plan"] == [
        "plan:docs/superpowers/plans/2026-07-20-factory-plan-and-run.md"
    ]


def test_task_with_no_source_plan_carries_no_source_plan_relation(tmp_path):
    _fixtures.write_task(tmp_path / "tasks", "T-060", title="Wire the governor")
    entry = build_labels(tmp_path)["labels"]["task:T-060"]
    assert "source_plan" not in entry["relations"]


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


def test_plan_goal_label_resolves_as_goal(tmp_path):
    # No named section, only the **Goal:** label line most plans carry.
    plans_dir = tmp_path / "docs" / "superpowers" / "plans"
    plans_dir.mkdir(parents=True)
    (plans_dir / "2026-08-14-example-plan.md").write_text(
        "# Example plan\n\n**Goal:** Ship the label index safely.\n\n- [ ] step one\n",
        encoding="utf-8",
    )
    entry = build_labels(tmp_path)["labels"][
        "plan:docs/superpowers/plans/2026-08-14-example-plan.md"
    ]
    assert entry["description"] == "Ship the label index safely."
    assert entry["description_source"] == "goal"


def test_spec_problem_section_resolves_as_problem(tmp_path):
    specs_dir = tmp_path / "docs" / "superpowers" / "specs"
    specs_dir.mkdir(parents=True)
    (specs_dir / "2026-08-14-example-design.md").write_text(
        "# Example design\n\n## Problem\n\nThe browser has no label index.\n",
        encoding="utf-8",
    )
    entry = build_labels(tmp_path)["labels"][
        "spec:docs/superpowers/specs/2026-08-14-example-design.md"
    ]
    assert entry["description"] == "The browser has no label index."
    assert entry["description_source"] == "problem"


def test_spec_with_no_named_source_yields_no_description(tmp_path):
    # _fixtures.write_spec's body ("Spec body.") has no named section and is
    # not a **Goal:** label -- this must no longer fall back to it.
    _fixtures.write_spec(tmp_path, "2026-07-16-foo-design.md", title="Foo")
    entry = build_labels(tmp_path)["labels"][
        "spec:docs/superpowers/specs/2026-07-16-foo-design.md"
    ]
    assert entry["description"] is None
    assert entry["description_source"] is None


def test_no_entry_reports_lead_paragraph_source(tmp_path):
    _fixtures.write_spec(tmp_path, "2026-07-16-foo-design.md", title="Foo")
    _fixtures.write_plan(tmp_path, "2026-07-16-foo-plan.md", title="Foo plan")
    payload = build_labels(tmp_path)
    sources = {entry["description_source"] for entry in payload["labels"].values()}
    assert "lead_paragraph" not in sources


def test_unreadable_spec_degrades_only_that_entry(tmp_path):
    specs_dir = tmp_path / "docs" / "superpowers" / "specs"
    specs_dir.mkdir(parents=True)
    (specs_dir / "2026-08-14-bad-design.md").write_bytes(
        b"# Bad\xff\xfe\n\n## Purpose\n\nInvalid bytes above.\n"
    )
    _fixtures.write_task(tmp_path / "tasks", "T-060", title="Wire the governor")

    payload = build_labels(tmp_path)
    ref = "spec:docs/superpowers/specs/2026-08-14-bad-design.md"

    assert ref in payload["labels"]
    assert payload["labels"][ref]["description"] is None
    assert any("2026-08-14-bad-design.md" in reason for reason in payload["degraded"])
    # The rest of the index is unaffected by the one bad file.
    assert payload["labels"]["task:T-060"]["title"] == "Wire the governor"


# --- C1: file: entries (final review fix wave) ------------------------------


def test_build_labels_emits_file_entries_from_evidence_manifests(tmp_path):
    _fixtures.write_run_manifest(
        tmp_path, run_id="run-001", task_id="T-001",
        changed_files=["src/drone/planning/reactive.py", "tests/test_reactive.py"],
    )
    payload = build_labels(tmp_path)
    file_refs = [ref for ref in payload["labels"] if ref.startswith("file:")]
    assert set(file_refs) == {
        "file:src/drone/planning/reactive.py",
        "file:tests/test_reactive.py",
    }


def test_a_known_changed_file_path_resolves_and_renders_with_its_path_as_title(tmp_path):
    _fixtures.write_run_manifest(
        tmp_path, run_id="run-001", task_id="T-001",
        changed_files=["src/drone/planning/reactive.py"],
    )
    payload = build_labels(tmp_path)
    ref = "file:src/drone/planning/reactive.py"
    entry = payload["labels"][ref]
    assert entry == file_entry(tmp_path, "src/drone/planning/reactive.py")
    assert entry["title"] == "src/drone/planning/reactive.py"
    assert entry["description"] is None
    assert entry["description_source"] is None

    # Resolvable both as the canonical ref (queries.py's _file_ref spelling,
    # used by the traversal payload) AND as the bare, unprefixed path
    # (system_claim.changed_files / the reverse-walk file field's spelling,
    # both frozen response schemas this feature does not touch) -- refChip
    # passes each site's own raw string straight through with no prefixing.
    assert payload["aliases"][ref] == ref
    assert payload["aliases"]["src/drone/planning/reactive.py"] == ref


def test_file_entry_never_invents_a_title_or_description(tmp_path):
    entry = file_entry(tmp_path, "src/a.py")
    assert entry == {
        "ref": "file:src/a.py", "id": "a.py", "kind": "file",
        "title": "src/a.py", "description": None, "description_source": None,
        "deferral_reason": None, "status": None, "relations": {},
        "path": "src/a.py", "scope_href": "/system?scope=file%3Asrc%2Fa.py",
    }
