from __future__ import annotations

import ast
import json
from dataclasses import asdict
from pathlib import Path

import pytest


pytestmark = pytest.mark.unit


def _write_goal(root: Path) -> None:
    goals = root / "goals"
    goals.mkdir()
    (goals / "GOAL-001.md").write_text(
        "---\n"
        "id: GOAL-001\n"
        "title: Reach the target\n"
        "feature: [FEAT-001]\n"
        "requirements: [SR-001]\n"
        "metric: {name: score, source_experiment: EXP-001}\n"
        "target: '>= 0.9'\n"
        "---\n\nGoal body.\n",
        encoding="utf-8",
    )


def _write_run(root: Path) -> None:
    run = root / "evidence" / "runs" / "RUN-001"
    run.mkdir(parents=True)
    (run / "manifest.json").write_text(
        json.dumps(
            {
                "run": "RUN-001",
                "experiment": "EXP-001",
                "feature": "FEAT-001",
                "requirements": ["SR-001"],
                "goals": ["GOAL-001"],
                "commit": "a" * 40,
                "result": "passed",
                "recorded_ts": "2026-08-22T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    (run / "metrics.json").write_text('{"score": 0.95}\n', encoding="utf-8")


def test_coherence_goal_and_simulation_public_apis_match_factory(tmp_path, capsys):
    _write_goal(tmp_path)
    _write_run(tmp_path)

    from coherence.goals.cli import main as coherence_goals_main
    from coherence.goals.registry import load_goals as coherence_load_goals
    from coherence.simulation.cli import main as coherence_simulation_main
    from coherence.simulation.registry import load_runs as coherence_load_runs
    from factory.goals.cli import main as factory_goals_main
    from factory.goals.registry import load_goals as factory_load_goals
    from factory.simulation.cli import main as factory_simulation_main
    from factory.simulation.registry import load_runs as factory_load_runs

    assert {
        key: asdict(value)
        for key, value in coherence_load_goals(tmp_path).items()
    } == {
        key: asdict(value)
        for key, value in factory_load_goals(tmp_path).items()
    }
    assert [asdict(value) for value in coherence_load_runs(tmp_path / "evidence")] == [
        asdict(value) for value in factory_load_runs(tmp_path / "evidence")
    ]

    assert coherence_goals_main(["list", "--repo", str(tmp_path), "--json"]) == 0
    coherence_output = capsys.readouterr().out
    assert factory_goals_main(["list", "--repo", str(tmp_path), "--json"]) == 0
    assert json.loads(coherence_output) == json.loads(capsys.readouterr().out)

    assert coherence_simulation_main(["runs", str(tmp_path), "--json"]) == 0
    simulation_output = capsys.readouterr().out
    assert factory_simulation_main(["runs", str(tmp_path), "--json"]) == 0
    assert json.loads(simulation_output) == json.loads(capsys.readouterr().out)


def test_coherence_goal_and_simulation_modules_do_not_import_factory():
    for package in ("goals", "simulation"):
        package_root = Path("src/coherence") / package
        for path in package_root.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    modules = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    modules = [node.module or ""]
                else:
                    continue
                assert not any(module == "factory" or module.startswith("factory.") for module in modules), path
