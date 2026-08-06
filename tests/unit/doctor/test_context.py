from pathlib import Path

import pytest
from factory.doctor.context import format_context, gather_context

pytestmark = pytest.mark.unit

_PROPOSED = """---
id: SR-009
title: Zone clear abandons investigate
statement: When the zone clears, the system shall resume patrol.
domain: behavioral
source: docs/superpowers/specs/2026-01-01-a-design.md
---
Rationale.
"""

_BOUND = """---
id: SR-001
title: Bound requirement
statement: When X, the system shall Y.
domain: behavioral
binding:
  harness: sim-testbench
  experiment: demo_experiment
  metric: demo_rate
  assert: ">= 0.90"
---
Rationale.
"""


def _repo(tmp_path) -> Path:
    (tmp_path / "requirements").mkdir()
    specs = tmp_path / "docs" / "superpowers" / "specs"
    specs.mkdir(parents=True)
    (specs / "2026-01-01-a-design.md").write_text("# A\n", encoding="utf-8")
    (tmp_path / "requirements" / "SR-009.md").write_text(_PROPOSED, encoding="utf-8")
    return tmp_path


def _declare_scorers(repo: Path, pkg: str, body: str) -> None:
    d = repo / "src" / pkg
    d.mkdir(parents=True)
    (d / "__init__.py").write_text("", encoding="utf-8")
    (d / "scorers.py").write_text(body, encoding="utf-8")
    (repo / ".factory").mkdir(exist_ok=True)
    (repo / ".factory" / "factory.yaml").write_text(
        "harnesses:\n  sim-testbench:\n    type: sim-testbench\n"
        f"    traces_dir: validation/traces\n    scorers: {pkg}.scorers\n"
        'gates:\n  unit:\n    - { cmd: "true" }\n',
        encoding="utf-8",
    )


def test_context_lists_specs_and_register_state(tmp_path):
    ctx = gather_context(_repo(tmp_path))
    assert ctx["specs"] == ["docs/superpowers/specs/2026-01-01-a-design.md"]
    entry = ctx["requirements"][0]
    assert entry["id"] == "SR-009"
    assert entry["state"] == "proposed"
    assert entry["source"].endswith("a-design.md")
    assert entry["binding"] is None


def test_a_bound_requirement_reports_its_binding(tmp_path):
    repo = _repo(tmp_path)
    (repo / "requirements" / "SR-001.md").write_text(_BOUND, encoding="utf-8")
    by_id = {r["id"]: r for r in gather_context(repo)["requirements"]}
    assert by_id["SR-001"]["state"] == "active"
    assert by_id["SR-001"]["binding"]["metric"] == "demo_rate"


def test_a_repo_with_no_factory_config_says_so_rather_than_failing(tmp_path):
    assert gather_context(_repo(tmp_path))["config"] == {"present": False, "harnesses": {}}


def test_declared_metrics_are_reported(tmp_path):
    repo = _repo(tmp_path)
    _declare_scorers(repo, "demo_ctx_ok", "SCORERS = {'demo_rate': lambda f, w: True}\n")
    harness = gather_context(repo)["config"]["harnesses"]["sim-testbench"]
    assert harness["metrics"] == ["demo_rate"]
    assert harness["error"] is None


def test_a_broken_scorer_module_is_reported_not_raised(tmp_path):
    repo = _repo(tmp_path)
    _declare_scorers(repo, "demo_ctx_bad", "NOT_SCORERS = {}\n")
    harness = gather_context(repo)["config"]["harnesses"]["sim-testbench"]
    assert harness["metrics"] == []
    assert "SCORERS" in harness["error"]


def test_context_never_emits_spec_text(tmp_path):
    rendered = format_context(gather_context(_repo(tmp_path)))
    assert "2026-01-01-a-design.md" in rendered
    assert "read these files yourself" in rendered.lower()


def test_an_empty_register_renders_without_crashing(tmp_path):
    (tmp_path / "requirements").mkdir()
    rendered = format_context(gather_context(tmp_path))
    assert "(empty)" in rendered
