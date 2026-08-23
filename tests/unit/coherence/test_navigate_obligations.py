import pytest
from pathlib import Path

from coherence.navigate.obligations import (
    effective_profile_view,
    obligations_open_count,
    present_obligations,
    why_required,
)

pytestmark = pytest.mark.unit


def _seed_gates(root: Path) -> None:
    (root / ".factory").mkdir()
    (root / ".factory" / "factory.yaml").write_text(
        "gates:\n  unit:\n  - { cmd: 'pytest -m unit -q' }\n",
        encoding="utf-8",
    )


def _seed_sr(root: Path, sr_id: str = "SR-001") -> None:
    (root / "requirements").mkdir(exist_ok=True)
    (root / "requirements" / f"{sr_id}.md").write_text(
        f"---\nid: {sr_id}\ntitle: t\nstatement: s\ndomain: d\n---\n",
        encoding="utf-8",
    )


def _seed_goal(root: Path, goal_id: str = "GOAL-001") -> None:
    (root / "goals").mkdir(exist_ok=True)
    (root / "goals" / f"{goal_id}.md").write_text(
        f"---\nid: {goal_id}\ntitle: t\nstate: PROPOSED\nfeature: []\n"
        "requirements: []\nmetric: null\ntarget: '>= 0.90'\n---\n",
        encoding="utf-8",
    )


# -- effective_profile_view --------------------------------------------------


def test_effective_profile_view_project_scope(tmp_path):
    _seed_gates(tmp_path)
    view = effective_profile_view(tmp_path, "project")
    assert view["scope_ref"] == "project"
    assert view["profile"] == "prototype"
    kinds = [o["kind"] for o in view["obligations"]]
    assert "ci_verification" in kinds
    ci = next(o for o in view["obligations"] if o["kind"] == "ci_verification")
    assert ci["requiredness"] == "blocking"
    # The full 8-field Obligation contract must survive the projection
    # (review finding #4 -- scope_ref and source_policy were being dropped).
    assert ci["scope_ref"] == "project"
    assert ci["source_policy"] == "prototype"
    assert set(ci.keys()) == {
        "id",
        "scope_ref",
        "kind",
        "requiredness",
        "reason",
        "source_policy",
        "state",
        "resolve_cmd",
    }


# -- why_required -------------------------------------------------------------


def test_why_required_explains_a_known_obligation(tmp_path):
    _seed_gates(tmp_path)
    view = effective_profile_view(tmp_path, "project")
    ob_id = view["obligations"][0]["id"]
    explanation = why_required(tmp_path, ob_id, "project")
    assert explanation is not None
    assert "prototype" in explanation


def test_why_required_unknown_id_returns_none(tmp_path):
    _seed_gates(tmp_path)
    assert why_required(tmp_path, "ob:does-not-exist", "project") is None


def test_why_required_accepts_precompiled_obligations(tmp_path):
    """The `obligations=` passthrough must answer identically to a fresh
    compile, so a caller that already has the list avoids a second
    compile_obligations() call."""
    from coherence.policy.compiler import compile_obligations

    _seed_gates(tmp_path)
    compiled = compile_obligations(tmp_path, "project")
    fresh = why_required(tmp_path, compiled[0].id, "project")
    passed_through = why_required(tmp_path, compiled[0].id, "project", obligations=compiled)
    assert fresh == passed_through


# -- obligations_open_count ----------------------------------------------------


def test_obligations_open_count_excludes_ci_verification_for_known_goal_scope(tmp_path):
    """ci_verification is compiled for EVERY scope including goal:/run: ones
    (2B D18) -- it must not make obligations_open_count structurally >= 1 for
    every goal/run in every repo (review finding #3)."""
    _seed_gates(tmp_path)
    _seed_goal(tmp_path)
    count, error = obligations_open_count(tmp_path, "goal:GOAL-001")
    assert count == 0
    assert error is None


def test_obligations_open_count_unknown_goal_fails_closed(tmp_path):
    _seed_gates(tmp_path)
    count, error = obligations_open_count(tmp_path, "goal:GOAL-DOES-NOT-EXIST")
    assert count == 0
    assert error == "no declared policy scope for 'goal:GOAL-DOES-NOT-EXIST'"


def test_obligations_open_count_marks_run_scope_unsupported(tmp_path):
    """The current trace loader has no run nodes; do not claim run policy
    resolution by falling back to the project profile."""
    _seed_gates(tmp_path)
    count, error = obligations_open_count(tmp_path, "run:RUN-3")
    assert count == 0
    assert error == ("policy scope unsupported for 'run:RUN-3': load_nodes exposes no run nodes")


def test_obligations_open_count_surfaces_uncompiled_preset_error(tmp_path):
    (tmp_path / ".factory").mkdir()
    (tmp_path / ".factory" / "factory.yaml").write_text("profile: exploration\n", encoding="utf-8")
    count, error = obligations_open_count(tmp_path, "project")
    assert count == 0
    assert error is not None
    assert "exploration" in error


# -- present_obligations --------------------------------------------------------


def test_present_obligations_attaches_why_for_relevant_obligations(tmp_path):
    """Blocking finding #1: --why-required must actually call why_required,
    not just attach effective_profile_view's dicts unexplained."""
    _seed_gates(tmp_path)
    _seed_sr(tmp_path)
    result = present_obligations(tmp_path, "sr:SR-001")
    assert result["obligations"] is not None
    ci = next(o for o in result["obligations"] if o["kind"] == "ci_verification")
    assert ci["why"] is not None
    assert "prototype" in ci["why"]


def test_present_obligations_none_for_non_scope_artifact_kind(tmp_path):
    """file:/a raw path/RUN-*/catchup: never resolve to a real trace-node
    policy scope -- must not silently mislabel project-default obligations
    as if they were that artifact's own (review finding #7)."""
    result = present_obligations(tmp_path, "file:.factory/factory.yaml")
    assert result == {
        "obligations": None,
        "obligations_note": "no policy scope for this artifact kind",
    }


def test_present_obligations_none_for_unknown_goal(tmp_path):
    result = present_obligations(tmp_path, "goal:GOAL-DOES-NOT-EXIST")
    assert result == {"obligations": None, "obligations_note": "no declared policy scope"}


def test_present_obligations_rejects_windows_path_looking_like_a_scope(tmp_path):
    """A Windows absolute path contains ':' (C:\\...) and must not be
    misparsed as scope kind 'C' (review finding #7a)."""
    result = present_obligations(tmp_path, "C:\\src\\x.py")
    assert result == {
        "obligations": None,
        "obligations_note": "no policy scope for this artifact kind",
    }


def test_present_obligations_surfaces_uncompiled_preset_error(tmp_path):
    (tmp_path / ".factory").mkdir()
    (tmp_path / ".factory" / "factory.yaml").write_text("profile: exploration\n", encoding="utf-8")
    _seed_sr(tmp_path)
    result = present_obligations(tmp_path, "sr:SR-001")
    assert result["obligations"] == []
    assert result["obligations_error"] is not None


@pytest.mark.parametrize(
    "error_type",
    [
        "InvalidProfileError",
        "ProfileConflictError",
        "UncompiledPresetError",
    ],
)
def test_present_obligations_degrades_all_policy_resolution_errors(
    tmp_path, monkeypatch, error_type
):
    """Optional enrichment reports every 2B policy-resolution failure in its
    additive error field; none is converted into a successful empty view."""
    from coherence.navigate import obligations as module
    from substrate.policy import vocabulary

    _seed_sr(tmp_path)
    error = getattr(vocabulary, error_type)("policy cannot be resolved")
    monkeypatch.setattr(module, "_compile", lambda *_args, **_kwargs: (_ for _ in ()).throw(error))
    result = module.present_obligations(tmp_path, "sr:SR-001")
    assert result == {"obligations": [], "obligations_error": "policy cannot be resolved"}


def test_effective_profile_view_has_fixed_future_safe_order(tmp_path, monkeypatch):
    from coherence.navigate import obligations as module
    from substrate.policy.obligation import Obligation

    _seed_gates(tmp_path)
    values = [
        Obligation("ob:z", "project", "human_review", "required", "z", "prototype", "open", None),
        Obligation(
            "ob:a", "project", "ci_verification", "blocking", "a", "prototype", "open", None
        ),
        Obligation(
            "ob:b", "project", "task_justification", "advisory", "b", "prototype", "open", None
        ),
    ]
    monkeypatch.setattr(module, "compile_obligations", lambda *_args, **_kwargs: values)
    view = module.effective_profile_view(tmp_path, "project")
    assert [ob["kind"] for ob in view["obligations"]] == [
        "ci_verification",
        "task_justification",
        "human_review",
    ]


def test_effective_profile_view_orders_unknown_kinds_after_known_deterministically(
    tmp_path, monkeypatch
):
    """Unknown future kinds use the fallback rank, then kind/scope/id, so
    adding a new compiler kind cannot disturb the established order."""
    from coherence.navigate import obligations as module
    from substrate.policy.obligation import Obligation

    _seed_gates(tmp_path)
    values = [
        Obligation("ob:z2", "task:T-2", "z_future", "required", "z2", "prototype", "open", None),
        Obligation("ob:a", "task:T-1", "a_future", "required", "a", "prototype", "open", None),
        Obligation("ob:z1", "task:T-1", "z_future", "required", "z1", "prototype", "open", None),
        Obligation(
            "ob:human", "project", "human_review", "required", "h", "prototype", "open", None
        ),
        Obligation(
            "ob:ci", "project", "ci_verification", "blocking", "c", "prototype", "open", None
        ),
    ]
    monkeypatch.setattr(module, "compile_obligations", lambda *_args, **_kwargs: values)
    view = module.effective_profile_view(tmp_path, "project")
    assert [(ob["kind"], ob["scope_ref"], ob["id"]) for ob in view["obligations"]] == [
        ("ci_verification", "project", "ob:ci"),
        ("human_review", "project", "ob:human"),
        ("a_future", "task:T-1", "ob:a"),
        ("z_future", "task:T-1", "ob:z1"),
        ("z_future", "task:T-2", "ob:z2"),
    ]
