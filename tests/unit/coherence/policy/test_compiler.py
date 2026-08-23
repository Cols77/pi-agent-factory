import pytest
from pathlib import Path

from coherence.policy.compiler import (
    UnsupportedScopeError,
    compile_obligations,
    resolve_profile,
)
from substrate.policy.vocabulary import UncompiledPresetError

pytestmark = pytest.mark.unit


def _seed_gates(root: Path) -> None:
    # {python} deliberately included: every real gate command in
    # .factory/factory.yaml uses it (verified against tests/integration/
    # orchestrator/test_resume_run.py's own fixture), and this is exactly
    # what proves _ci_verification_obligation reuses backends.py's real
    # substitution instead of joining raw step.cmd strings.
    (root / ".factory").mkdir(exist_ok=True)
    (root / ".factory" / "factory.yaml").write_text(
        "gates:\n"
        "  unit:\n"
        "  - { cmd: '{python} -m pytest -m unit -q' }\n"
        "  sim:\n"
        "  - { cmd: '{python} -m pytest -m sim -q' }\n"
        "  full:\n"
        "  - { cmd: '{python} -m pytest -m unit -q' }\n",
        encoding="utf-8",
    )


def test_resolve_profile_project_default(tmp_path):
    assert resolve_profile(tmp_path, "project") == "prototype"


def test_resolve_profile_project_scope_uses_project_default_explicitly(tmp_path):
    (tmp_path / ".factory").mkdir()
    (tmp_path / ".factory" / "factory.yaml").write_text(
        "profile: high_assurance\n", encoding="utf-8"
    )
    assert resolve_profile(tmp_path, "project") == "high_assurance"


def test_resolve_profile_unknown_artifact_scope_fails_closed(tmp_path):
    (tmp_path / ".factory").mkdir()
    (tmp_path / ".factory" / "factory.yaml").write_text(
        "profile: high_assurance\n", encoding="utf-8"
    )
    with pytest.raises(UnsupportedScopeError):
        resolve_profile(tmp_path, "sr:SR-404")


def test_resolve_profile_unsupported_artifact_scope_fails_closed(tmp_path):
    with pytest.raises(UnsupportedScopeError):
        resolve_profile(tmp_path, "file:src/not-a-trace-artifact.py")


def test_resolve_profile_rejects_uncompiled_preset(tmp_path):
    (tmp_path / ".factory").mkdir()
    (tmp_path / ".factory" / "factory.yaml").write_text("profile: exploration\n", encoding="utf-8")
    with pytest.raises(UncompiledPresetError):
        resolve_profile(tmp_path, "project")


def test_resolve_profile_rejects_uncompiled_preset_product(tmp_path):
    (tmp_path / ".factory").mkdir()
    (tmp_path / ".factory" / "factory.yaml").write_text("profile: product\n", encoding="utf-8")
    with pytest.raises(UncompiledPresetError):
        resolve_profile(tmp_path, "project")


def test_compile_obligations_ci_verification_substitutes_python_like_backends_does(tmp_path):
    _seed_gates(tmp_path)
    obligations = compile_obligations(tmp_path, "project")
    ci = next(o for o in obligations if o.kind == "ci_verification")
    assert ci.requiredness == "blocking"
    assert ci.source_policy == "prototype"
    # No literal "{python}" survives -- backends._target_python/_quote_for_shell
    # already ran, producing a real interpreter path/token in its place.
    assert all("{python}" not in command for command in (ci.resolve_cmd or ()))
    assert any("-m pytest -m unit -q" in command for command in (ci.resolve_cmd or ()))


def test_compile_obligations_preserves_configured_order_and_duplicates(tmp_path):
    _seed_gates(tmp_path)
    obligations = compile_obligations(tmp_path, "project")
    ci = next(o for o in obligations if o.kind == "ci_verification")

    assert ci.resolve_cmd is not None
    assert len(ci.resolve_cmd) == 3
    assert ci.resolve_cmd[0].endswith("-m pytest -m unit -q")
    assert ci.resolve_cmd[1].endswith("-m pytest -m sim -q")
    assert ci.resolve_cmd[2] == ci.resolve_cmd[0]


def test_compile_obligations_task_justification_for_task_scope(tmp_path):
    # task_justification lands here (not deferred to Increment 6B) because it
    # is a direct sibling of this same increment's typed-justification work
    # (Task 2) -- Increment 4's verification_result and Increment 6's
    # human_review obligation kinds are added by those increments' own plans,
    # since each is grounded in that increment's own deliverable.
    _seed_gates(tmp_path)
    (tmp_path / "tasks").mkdir()
    (tmp_path / "tasks" / "T-900.md").write_text(
        "---\nid: T-900\ntitle: t\nstatus: todo\ndod:\n- 'd'\n---\nbody\n", encoding="utf-8",
    )
    obligations = compile_obligations(tmp_path, "task:T-900")
    tj = next(o for o in obligations if o.kind == "task_justification")
    assert tj.requiredness == "advisory"  # prototype is the project default here
    assert tj.state == "open"  # T-900 has no justification at all


def test_resolve_profile_honors_preloaded_nodes_and_edges(tmp_path, monkeypatch):
    # Increment 5's per-SR health loop calls compile_obligations(root,
    # f"sr:{n.id}", nodes=nodes, edges=edges) inside a loop over every SR --
    # it must never trigger a fresh trace_model.load_nodes per call.
    from coherence.trace import model as trace_model

    (tmp_path / "docs" / "features").mkdir(parents=True)
    (tmp_path / "docs" / "features" / "FEAT-001.md").write_text(
        "---\nid: FEAT-001\ntitle: f\nprofile: high_assurance\nrequirements: [SR-001]\n---\n",
        encoding="utf-8",
    )
    (tmp_path / "requirements").mkdir()
    (tmp_path / "requirements" / "SR-001.md").write_text(
        "---\nid: SR-001\ntitle: t\nstatement: s\ndomain: d\n"
        "binding:\n  harness: h\n  experiment: e\n  metric: m\n  assert: '>= 0.9'\n---\n",
        encoding="utf-8",
    )
    nodes = trace_model.load_nodes(tmp_path)
    edges = trace_model.extract_edges(tmp_path, nodes)

    def _boom(*_a, **_k):
        raise AssertionError("must not reload nodes when already supplied")

    monkeypatch.setattr(trace_model, "load_nodes", _boom)
    assert resolve_profile(tmp_path, "sr:SR-001", nodes=nodes, edges=edges) == "high_assurance"
