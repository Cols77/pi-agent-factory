"""Task 2 — artifact -> adapter/target resolution + traversal guard (§22).

Every spec §22 example resolves to a concrete adapter target; a traversal
path never becomes a shell/URI call; INSPECT never changes application focus.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from factory.presentation.level import Facts, Level
from factory.presentation.router import dispatch, present, resolve_intent

pytestmark = pytest.mark.unit


def _repo(tmp_path: Path) -> Path:
    src = tmp_path / "src" / "navigation"
    src.mkdir(parents=True)
    (src / "reacquisition.py").write_text("# target_reacquired\n", encoding="utf-8")
    return tmp_path


def _add_goal(tmp_path: Path, goal_id: str) -> None:
    goals = tmp_path / "goals"
    goals.mkdir(parents=True)
    (goals / f"{goal_id}.md").write_text(
        f"---\nid: {goal_id}\ntitle: reacquire target\nmetric: reacquisition_rate\n"
        "target: 0.9\noperator: '>='\nstate: NOT_REACHED\n---\n",
        encoding="utf-8",
    )


def test_feature_resolves_to_browser_dossier_target(tmp_path):
    repo = _repo(tmp_path)
    intent = resolve_intent(repo, "feat:FEAT-NAV-017")
    assert intent.adapter == "browser"
    assert intent.target == "system?scope=feat:FEAT-NAV-017"
    assert "Inc 6" in intent.note  # Feature Dossier page lands in Inc 6 (D2)


def test_requirement_resolves_to_browser_vcycle_target(tmp_path):
    repo = _repo(tmp_path)
    intent = resolve_intent(repo, "sr:SR-066")
    assert intent.adapter == "browser"
    assert intent.target == "system?scope=sr:SR-066"


def test_goal_resolves_to_browser_target(tmp_path):
    repo = _repo(tmp_path)
    _add_goal(tmp_path, "GOAL-NAV-003")
    intent = resolve_intent(repo, "goal:GOAL-NAV-003")
    assert intent.adapter == "browser"
    assert intent.target == "system?scope=goal:GOAL-NAV-003"


def test_metric_resolves_to_browser_target(tmp_path):
    repo = _repo(tmp_path)
    intent = resolve_intent(repo, "metric:reacquisition_rate")
    assert intent.adapter == "browser"
    assert intent.target == "system?scope=metric:reacquisition_rate"


def test_file_path_resolves_to_ide_target(tmp_path):
    repo = _repo(tmp_path)
    intent = resolve_intent(repo, "src/navigation/reacquisition.py", "184")
    assert intent.adapter == "ide"
    assert intent.target is not None and intent.target.startswith("vscode://file/")
    assert intent.target.endswith("?line=184")


def test_file_scope_kind_also_resolves_to_ide(tmp_path):
    repo = _repo(tmp_path)
    intent = resolve_intent(repo, "file:src/navigation/reacquisition.py")
    assert intent.adapter == "ide"
    assert intent.target is not None and intent.target.startswith("vscode://file/")


def test_traversal_path_never_shells(tmp_path):
    repo = _repo(tmp_path)
    intent = resolve_intent(repo, "../../etc/passwd")
    assert intent.adapter is None
    assert intent.target is None
    assert "traversal blocked" in intent.note


def test_unknown_file_path_degrades_gracefully(tmp_path):
    repo = _repo(tmp_path)
    intent = resolve_intent(repo, "src/nope.py")
    assert intent.adapter is None
    assert intent.target is None


def test_diagram_resolves_to_canonical_html(tmp_path):
    repo = _repo(tmp_path)
    (repo / "docs" / "diagrams" / "assets").mkdir(parents=True)
    (repo / "docs" / "diagrams" / "assets" / "overview.html").write_text(
        "<svg></svg>", encoding="utf-8"
    )
    (repo / "docs" / "diagrams" / "DIAG-PRES-001.md").write_text(
        "---\nid: DIAG-PRES-001\ntitle: Overview\ndiagram_file: assets/overview.html\n---\n",
        encoding="utf-8",
    )
    intent = resolve_intent(repo, "diag:DIAG-PRES-001")
    assert intent.adapter == "browser"
    assert intent.target is not None
    assert Path(intent.target).name == "overview.html"
    assert "D7" in intent.note


def test_diagram_missing_degrades_to_brief(tmp_path):
    repo = _repo(tmp_path)
    intent = resolve_intent(repo, "diag:DIAG-MISSING")
    assert intent.adapter == "browser"
    assert intent.target == "system?scope=diag:DIAG-MISSING"
    assert "degrading" in intent.note


def test_run_resolves_to_sim_evidence_bundle(tmp_path):
    repo = _repo(tmp_path)
    run_dir = repo / "evidence" / "runs" / "RUN-20260811-1702"
    run_dir.mkdir(parents=True)
    (run_dir / "manifest.json").write_text(
        json.dumps(
            {
                "run": "RUN-20260811-1702",
                "experiment": "SIM-047",
                "feature": "FEAT-NAV-017",
                "requirements": ["sr:SR-066"],
                "goals": ["GOAL-NAV-003"],
                "result": "failed",
            }
        ),
        encoding="utf-8",
    )
    intent = resolve_intent(repo, "RUN-20260811-1702", "target_reacquired")
    assert intent.adapter == "sim"
    assert intent.target is not None
    assert intent.target.endswith("RUN-20260811-1702")
    assert "Inc 6" in intent.note  # viewer lands in Inc 6


def test_unknown_run_degrades_without_target(tmp_path):
    repo = _repo(tmp_path)
    intent = resolve_intent(repo, "RUN-NOPE")
    assert intent.adapter == "sim"
    assert intent.target is None
    assert "no simulation run" in intent.note


def test_default_level_is_inspect(tmp_path):
    repo = _repo(tmp_path)
    intent = resolve_intent(repo, "feat:FEAT-NAV-017")
    assert intent.level is Level.INSPECT


def test_explicit_level_override(tmp_path):
    repo = _repo(tmp_path)
    intent = resolve_intent(repo, "feat:FEAT-NAV-017", level=Level.PRESENT)
    assert intent.level is Level.PRESENT


def test_facts_raise_level_to_present(tmp_path):
    repo = _repo(tmp_path)
    intent = resolve_intent(repo, "feat:FEAT-NAV-017", facts=Facts(show_requested=True))
    assert intent.level is Level.PRESENT


def test_present_empty_artifact_raises(tmp_path):
    repo = _repo(tmp_path)
    with pytest.raises(ValueError):
        resolve_intent(repo, "   ")


def test_dispatch_inspect_names_no_focus_change(tmp_path):
    repo = _repo(tmp_path)
    intent = resolve_intent(repo, "feat:FEAT-NAV-017")
    action = dispatch(intent.level, intent)
    assert action["level"] == "INSPECT"
    assert "no application focus change" in action["resolution"]


def test_present_returns_ts_shaped_json(tmp_path):
    repo = _repo(tmp_path)
    action = present(repo, "feat:FEAT-NAV-017", "overview")
    assert action["artifact"] == "feat:FEAT-NAV-017"
    assert action["focus"] == "overview"
    assert action["intent"] == {"artifact": "feat:FEAT-NAV-017", "focus": "overview"}
    assert action["level"] == "INSPECT"
    assert action["adapter"] == "browser"
