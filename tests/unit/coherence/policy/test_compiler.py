import json
import subprocess
import sys
from pathlib import Path

import pytest

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


def test_compile_obligations_verification_result_high_assurance_no_validation_is_blocking_open(
    tmp_path,
):
    # An SR with a declared harness but no recorded validation at all: under
    # high_assurance this must block, and stay open (never satisfied by
    # absence of evidence -- spec's "missing evidence is unknown, never
    # passing" invariant).
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
    obligations = compile_obligations(tmp_path, "sr:SR-001")
    vr = next(o for o in obligations if o.kind == "verification_result")
    assert vr.requiredness == "blocking"
    assert vr.state == "open"


def test_compile_obligations_verification_result_prototype_pass_nonstale_is_satisfied(
    tmp_path,
):
    # prototype's contract is pass/fail only -- no harness-declared check --
    # so a passing, non-stale validation entry alone satisfies it, and its
    # requiredness must be "required", never "blocking" (D16: only
    # high_assurance blocks on this kind).
    (tmp_path / "requirements").mkdir()
    (tmp_path / "requirements" / "SR-002.md").write_text(
        "---\nid: SR-002\ntitle: t\nstatement: s\ndomain: d\n---\n",
        encoding="utf-8",
    )
    (tmp_path / "validation").mkdir()
    (tmp_path / "validation" / "validation-report.json").write_text(
        json.dumps({"requirements": [{"id": "SR-002", "passed": True, "stale": False}]}),
        encoding="utf-8",
    )
    obligations = compile_obligations(tmp_path, "sr:SR-002")
    vr = next(o for o in obligations if o.kind == "verification_result")
    assert vr.state == "satisfied"
    assert vr.requiredness == "required"


def test_compile_obligations_verification_result_high_assurance_missing_harness_stays_open(
    tmp_path,
):
    # Same passing, non-stale validation entry as above, but under
    # high_assurance with no declared harness: the extra high_assurance check
    # must still hold this open, naming the missing harness in the reason.
    (tmp_path / "requirements").mkdir()
    (tmp_path / "requirements" / "SR-003.md").write_text(
        "---\nid: SR-003\ntitle: t\nstatement: s\ndomain: d\nprofile: high_assurance\n---\n",
        encoding="utf-8",
    )
    (tmp_path / "validation").mkdir()
    (tmp_path / "validation" / "validation-report.json").write_text(
        json.dumps({"requirements": [{"id": "SR-003", "passed": True, "stale": False}]}),
        encoding="utf-8",
    )
    obligations = compile_obligations(tmp_path, "sr:SR-003")
    vr = next(o for o in obligations if o.kind == "verification_result")
    assert vr.requiredness == "blocking"
    assert vr.state == "open"
    assert "harness" in vr.reason


def test_compile_obligations_human_review_high_assurance_no_review_identity_is_blocking_open(
    tmp_path,
):
    # An SR under high_assurance with no human-review identity evidence at
    # all: D16 human_review is blocking here and stays open -- absence of a
    # recorded human reviewer is "unknown", never treated as satisfied.
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
    obligations = compile_obligations(tmp_path, "sr:SR-001")
    hr = next(o for o in obligations if o.kind == "human_review")
    assert hr.requiredness == "blocking"
    assert hr.state == "open"


def test_compile_obligations_human_review_under_prototype_is_not_applicable(tmp_path):
    # D16: human_review does not apply under prototype -- the obligation is
    # still compiled so CI/dimension-11 sees a real node, but non-blocking.
    (tmp_path / "requirements").mkdir()
    (tmp_path / "requirements" / "SR-002.md").write_text(
        "---\nid: SR-002\ntitle: t\nstatement: s\ndomain: d\n---\n",
        encoding="utf-8",
    )
    obligations = compile_obligations(tmp_path, "sr:SR-002")  # project default: prototype
    hr = next(o for o in obligations if o.kind == "human_review")
    assert hr.requiredness == "not_applicable"


# --------------------------------------------------------------------------
# Task 6 addendum: compiled test_marker obligation (profile-aware closure)
# --------------------------------------------------------------------------


def _seed_test_marker_trace(tmp_path, sr_id, *, experiment, profile=None) -> None:
    (tmp_path / "requirements").mkdir(exist_ok=True)
    profile_line = f"profile: {profile}\n" if profile else ""
    (tmp_path / "requirements" / f"{sr_id}.md").write_text(
        "---\n"
        f"id: {sr_id}\ntitle: t\nstatement: s\ndomain: d\n"
        f"{profile_line}"
        "binding:\n"
        f"  experiment: {experiment}\n"
        "  metric: m\n"
        "  assert: '>= 0.9'\n"
        "  harness: h\n"
        "---\n",
        encoding="utf-8",
    )


def test_compile_obligations_test_marker_required_under_default_prototype(tmp_path):
    # The project default (prototype) compiles the test_marker obligation with
    # requiredness "required", and a bound experiment test file missing the
    # marker stays open -- this is exactly the value the closure CHECK reads.
    experiment = "tests/test_sr_req.py"
    exp = tmp_path / experiment
    exp.parent.mkdir(parents=True, exist_ok=True)
    exp.write_text("def test_x():\n    assert True\n", encoding="utf-8")
    _seed_test_marker_trace(tmp_path, "SR-011", experiment=experiment)
    obligations = compile_obligations(tmp_path, "sr:SR-011")  # project default: prototype
    tm = next(o for o in obligations if o.kind == "test_marker")
    assert tm.requiredness == "required"
    assert tm.state == "open"


def test_compile_obligations_test_marker_blocking_under_high_assurance_override(tmp_path):
    experiment = "tests/test_sr_high_ob.py"
    exp = tmp_path / experiment
    exp.parent.mkdir(parents=True, exist_ok=True)
    exp.write_text("def test_x():\n    assert True\n", encoding="utf-8")
    _seed_test_marker_trace(tmp_path, "SR-012", experiment=experiment, profile="high_assurance")
    obligations = compile_obligations(tmp_path, "sr:SR-012")
    tm = next(o for o in obligations if o.kind == "test_marker")
    assert tm.requiredness == "blocking"
    assert tm.state == "open"


def test_compile_obligations_test_marker_satisfied_when_marker_present(tmp_path):
    experiment = "tests/test_sr_sat.py"
    exp = tmp_path / experiment
    exp.parent.mkdir(parents=True, exist_ok=True)
    exp.write_text(
        '@pytest.mark.sr("SR-013")\n'
        "def test_x():\n"
        "    assert True\n",
        encoding="utf-8",
    )
    _seed_test_marker_trace(tmp_path, "SR-013", experiment=experiment)
    obligations = compile_obligations(tmp_path, "sr:SR-013")  # project default: prototype
    tm = next(o for o in obligations if o.kind == "test_marker")
    assert tm.requiredness == "required"
    assert tm.state == "satisfied"


def test_compile_obligations_test_marker_not_applicable_for_command_experiment(tmp_path):
    # A command / non-file experiment is a separate configuration finding (Task
    # 3), NOT this obligation's concern: test_marker is not_applicable for it.
    _seed_test_marker_trace(tmp_path, "SR-014", experiment="patrol")
    obligations = compile_obligations(tmp_path, "sr:SR-014")
    tm = next(o for o in obligations if o.kind == "test_marker")
    assert tm.requiredness == "not_applicable"
    assert tm.state == "satisfied"


# --------------------------------------------------------------------------
# Task 5 addendum: test_marker obligation resolves through acceptance criteria
# for an SR that carries no `binding` (the proposed/unbound state).
# --------------------------------------------------------------------------


def _seed_unbound_sr_with_acceptance(tmp_path, sr_id, *, acceptance_yaml, profile=None):
    (tmp_path / "requirements").mkdir(exist_ok=True)
    profile_line = f"profile: {profile}\n" if profile else ""
    (tmp_path / "requirements" / f"{sr_id}.md").write_text(
        "---\n"
        f"id: {sr_id}\ntitle: t\nstatement: s\ndomain: d\n"
        f"{profile_line}"
        f"{acceptance_yaml}"
        "---\n",
        encoding="utf-8",
    )


def test_compile_obligations_test_marker_via_acceptance_satisfied(tmp_path):
    # An unbound SR (no `binding:`) with one `test_marker` acceptance
    # criterion whose ref file carries a matching @pytest.mark.sr marker
    # must compile a satisfied test_marker obligation.
    experiment = "tests/test_ac_sat.py"
    exp = tmp_path / experiment
    exp.parent.mkdir(parents=True, exist_ok=True)
    exp.write_text(
        '@pytest.mark.sr("SR-020")\ndef test_x():\n    assert True\n', encoding="utf-8",
    )
    _seed_unbound_sr_with_acceptance(
        tmp_path,
        "SR-020",
        acceptance_yaml=(
            "acceptance:\n"
            "  - id: AC-1\n"
            '    criterion: "c"\n'
            "    verification:\n"
            "      kind: test_marker\n"
            f"      ref: \"{experiment}\"\n"
        ),
    )
    obligations = compile_obligations(tmp_path, "sr:SR-020")
    tm = next(o for o in obligations if o.kind == "test_marker")
    assert tm.requiredness == "required"  # project default: prototype
    assert tm.state == "satisfied"


def test_compile_obligations_test_marker_rejects_duplicate_registered_ids(tmp_path):
    # Conflicting duplicate SR declarations must not let the valid acceptance
    # source hide the invalid one: duplicate registration is ambiguous.
    good = "tests/test_ac_duplicate_good.py"
    bad = "tests/test_ac_duplicate_bad.py"
    (tmp_path / "tests").mkdir(parents=True, exist_ok=True)
    (tmp_path / good).write_text(
        '@pytest.mark.sr("SR-DUP")\ndef test_good():\n    assert True\n', encoding="utf-8"
    )
    (tmp_path / bad).write_text("def test_bad():\n    assert True\n", encoding="utf-8")
    duplicate_yaml = (
        "---\n"
        "id: SR-DUP\ntitle: t\nstatement: s\ndomain: d\n"
        "acceptance:\n"
        "  - id: AC-1\n"
        '    criterion: "c"\n'
        "    verification:\n"
        "      kind: test_marker\n"
    )
    (tmp_path / "requirements").mkdir()
    (tmp_path / "requirements" / "SR-DUP-a.md").write_text(
        f"{duplicate_yaml}      ref: \"{bad}\"\n---\n", encoding="utf-8"
    )
    (tmp_path / "requirements" / "SR-DUP-b.md").write_text(
        f"{duplicate_yaml}      ref: \"{good}\"\n---\n", encoding="utf-8"
    )

    obligations = compile_obligations(tmp_path, "sr:SR-DUP")
    tm = next(o for o in obligations if o.kind == "test_marker")

    assert tm.state == "open"
    assert "duplicate" in tm.reason


@pytest.mark.parametrize(
    ("high_name", "prototype_name"),
    [
        ("SR-MIX-a.md", "SR-MIX-b.md"),
        ("SR-MIX-b.md", "SR-MIX-a.md"),
    ],
)
def test_compile_obligations_duplicate_profiles_are_ambiguous_and_blocking(
    tmp_path, high_name, prototype_name
):
    duplicate_yaml = (
        "---\n"
        "id: SR-MIX\ntitle: t\nstatement: s\ndomain: d\n"
        "acceptance:\n"
        "  - id: AC-1\n"
        '    criterion: "c"\n'
        "    verification:\n"
        "      kind: test_marker\n"
        "      ref: \"tests/test_mixed_profile.py\"\n"
        "---\n"
    )
    requirements = tmp_path / "requirements"
    requirements.mkdir()
    (requirements / high_name).write_text(
        duplicate_yaml.replace("domain: d\n", "domain: d\nprofile: high_assurance\n"),
        encoding="utf-8",
    )
    (requirements / prototype_name).write_text(duplicate_yaml, encoding="utf-8")

    obligations = compile_obligations(tmp_path, "sr:SR-MIX")
    tm = next(o for o in obligations if o.kind == "test_marker")

    assert tm.requiredness == "blocking"
    assert tm.state == "open"
    assert tm.source_policy == "ambiguous"
    assert "duplicate" in tm.reason


def test_compile_obligations_test_marker_via_acceptance_unresolved_ref_stays_open(tmp_path):
    # The ref file exists but carries no matching marker: unsatisfied.
    experiment = "tests/test_ac_unsat.py"
    exp = tmp_path / experiment
    exp.parent.mkdir(parents=True, exist_ok=True)
    exp.write_text("def test_x():\n    assert True\n", encoding="utf-8")
    _seed_unbound_sr_with_acceptance(
        tmp_path,
        "SR-021",
        acceptance_yaml=(
            "acceptance:\n"
            "  - id: AC-1\n"
            '    criterion: "c"\n'
            "    verification:\n"
            "      kind: test_marker\n"
            f"      ref: \"{experiment}\"\n"
        ),
        profile="high_assurance",
    )
    obligations = compile_obligations(tmp_path, "sr:SR-021")
    tm = next(o for o in obligations if o.kind == "test_marker")
    assert tm.requiredness == "blocking"
    assert tm.state == "open"
    assert "SR-021" in " ".join(tm.resolve_cmd or ())
    assert experiment in " ".join(tm.resolve_cmd or ())


def test_compile_obligations_test_marker_rejects_traversal_ref(tmp_path):
    outside = tmp_path.parent / f"{tmp_path.name}_outside_traversal.py"
    outside.write_text(
        '@pytest.mark.sr("SR-025")\ndef test_x():\n    assert True\n',
        encoding="utf-8",
    )
    ref = f"../{outside.name}"
    _seed_unbound_sr_with_acceptance(
        tmp_path,
        "SR-025",
        acceptance_yaml=(
            "acceptance:\n"
            "  - id: AC-1\n"
            '    criterion: "c"\n'
            "    verification:\n"
            "      kind: test_marker\n"
            f"      ref: \"{ref}\"\n"
        ),
    )
    obligations = compile_obligations(tmp_path, "sr:SR-025")
    tm = next(o for o in obligations if o.kind == "test_marker")
    assert tm.state == "open"
    assert ref in " ".join(tm.resolve_cmd or ())


def test_compile_obligations_test_marker_rejects_absolute_outside_ref(tmp_path):
    outside = tmp_path.parent / f"{tmp_path.name}_outside_absolute.py"
    outside.write_text(
        '@pytest.mark.sr("SR-026")\ndef test_x():\n    assert True\n',
        encoding="utf-8",
    )
    ref = outside.resolve().as_posix()
    _seed_unbound_sr_with_acceptance(
        tmp_path,
        "SR-026",
        acceptance_yaml=(
            "acceptance:\n"
            "  - id: AC-1\n"
            '    criterion: "c"\n'
            "    verification:\n"
            "      kind: test_marker\n"
            f"      ref: \"{ref}\"\n"
        ),
    )
    obligations = compile_obligations(tmp_path, "sr:SR-026")
    tm = next(o for o in obligations if o.kind == "test_marker")
    assert tm.state == "open"
    assert ref in " ".join(tm.resolve_cmd or ())


def test_compile_obligations_test_marker_rejects_symlink_outside_ref(tmp_path):
    outside = tmp_path.parent / f"{tmp_path.name}_outside_symlink.py"
    outside.write_text(
        '@pytest.mark.sr("SR-027")\ndef test_x():\n    assert True\n',
        encoding="utf-8",
    )
    ref = "tests/test_ac_symlink_outside.py"
    link = tmp_path / ref
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlinks are not supported: {exc}")
    _seed_unbound_sr_with_acceptance(
        tmp_path,
        "SR-027",
        acceptance_yaml=(
            "acceptance:\n"
            "  - id: AC-1\n"
            '    criterion: "c"\n'
            "    verification:\n"
            "      kind: test_marker\n"
            f"      ref: \"{ref}\"\n"
        ),
    )
    obligations = compile_obligations(tmp_path, "sr:SR-027")
    tm = next(o for o in obligations if o.kind == "test_marker")
    assert tm.state == "open"
    assert ref in " ".join(tm.resolve_cmd or ())


def test_compile_obligations_test_marker_rejects_directory_junction_ref(tmp_path):
    target_dir = tmp_path / "tests" / "ordinary"
    target_dir.mkdir(parents=True)
    target = target_dir / "target.py"
    target.write_text(
        '@pytest.mark.sr("SR-028")\ndef test_target():\n    assert True\n',
        encoding="utf-8",
    )
    alias = tmp_path / "tests" / "alias"
    if sys.platform == "win32":
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(alias), str(target_dir)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            pytest.skip(f"could not create a directory junction: {result.stderr or result.stdout}")
    else:
        try:
            alias.symlink_to(target_dir, target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            pytest.skip(f"directory symlinks are not supported: {exc}")

    ref = "tests/alias/target.py"
    _seed_unbound_sr_with_acceptance(
        tmp_path,
        "SR-028",
        acceptance_yaml=(
            "acceptance:\n"
            "  - id: AC-1\n"
            '    criterion: "c"\n'
            "    verification:\n"
            "      kind: test_marker\n"
            f"      ref: \"{ref}\"\n"
        ),
    )

    obligations = compile_obligations(tmp_path, "sr:SR-028")
    tm = next(o for o in obligations if o.kind == "test_marker")

    assert tm.state == "open"
    assert ref in " ".join(tm.resolve_cmd or ())


def test_compile_obligations_test_marker_via_acceptance_partial_is_not_satisfied(tmp_path):
    # Two test_marker criteria; only one resolves. Partial satisfaction must
    # NOT be reported as satisfied -- this is the false-green this obligation
    # exists to prevent.
    good = "tests/test_ac_partial_good.py"
    bad = "tests/test_ac_partial_bad.py"
    (tmp_path / "tests").mkdir(parents=True, exist_ok=True)
    (tmp_path / good).write_text(
        '@pytest.mark.sr("SR-022")\ndef test_x():\n    assert True\n', encoding="utf-8",
    )
    (tmp_path / bad).write_text("def test_y():\n    assert True\n", encoding="utf-8")
    _seed_unbound_sr_with_acceptance(
        tmp_path,
        "SR-022",
        acceptance_yaml=(
            "acceptance:\n"
            "  - id: AC-1\n"
            '    criterion: "a"\n'
            "    verification:\n"
            "      kind: test_marker\n"
            f"      ref: \"{good}\"\n"
            "  - id: AC-2\n"
            '    criterion: "b"\n'
            "    verification:\n"
            "      kind: test_marker\n"
            f"      ref: \"{bad}\"\n"
        ),
    )
    obligations = compile_obligations(tmp_path, "sr:SR-022")
    tm = next(o for o in obligations if o.kind == "test_marker")
    assert tm.state == "open"
    assert bad in " ".join(tm.resolve_cmd or ())
    assert good not in " ".join(tm.resolve_cmd or ())


def test_compile_obligations_test_marker_manual_only_criteria_is_not_applicable(tmp_path):
    # An SR whose acceptance criteria are all `kind: manual` (no test_marker
    # criteria at all) and carries no binding: not this obligation's concern.
    _seed_unbound_sr_with_acceptance(
        tmp_path,
        "SR-023",
        acceptance_yaml=(
            "acceptance:\n"
            "  - id: AC-1\n"
            '    criterion: "c"\n'
            "    verification:\n"
            "      kind: manual\n"
            '      reason: "no automated check"\n'
        ),
    )
    obligations = compile_obligations(tmp_path, "sr:SR-023")
    tm = next(o for o in obligations if o.kind == "test_marker")
    assert tm.requiredness == "not_applicable"
    assert tm.state == "satisfied"


def test_compile_obligations_test_marker_legacy_binding_ignores_acceptance(tmp_path):
    # An SR with a `binding.experiment` must behave exactly as the legacy
    # path always has, even when it ALSO carries a test_marker acceptance
    # criterion pointing elsewhere -- the legacy path is not merged with the
    # acceptance-based one.
    legacy_experiment = "tests/test_legacy_sr.py"
    exp = tmp_path / legacy_experiment
    exp.parent.mkdir(parents=True, exist_ok=True)
    exp.write_text(
        '@pytest.mark.sr("SR-024")\ndef test_x():\n    assert True\n', encoding="utf-8",
    )
    other_ref = "tests/test_ac_unrelated.py"
    (tmp_path / "tests").mkdir(parents=True, exist_ok=True)
    (tmp_path / other_ref).write_text("def test_z():\n    assert True\n", encoding="utf-8")
    (tmp_path / "requirements").mkdir(exist_ok=True)
    (tmp_path / "requirements" / "SR-024.md").write_text(
        "---\n"
        "id: SR-024\ntitle: t\nstatement: s\ndomain: d\n"
        "binding:\n"
        f"  experiment: {legacy_experiment}\n"
        "  metric: m\n"
        "  assert: '>= 0.9'\n"
        "  harness: h\n"
        "acceptance:\n"
        "  - id: AC-1\n"
        '    criterion: "c"\n'
        "    verification:\n"
        "      kind: test_marker\n"
        f"      ref: \"{other_ref}\"\n"
        "---\n",
        encoding="utf-8",
    )
    obligations = compile_obligations(tmp_path, "sr:SR-024")
    tm = next(o for o in obligations if o.kind == "test_marker")
    # The bound experiment carries the marker -> satisfied, exactly like the
    # legacy path, regardless of the unrelated unresolved acceptance ref.
    assert tm.state == "satisfied"
    assert tm.requiredness == "required"
