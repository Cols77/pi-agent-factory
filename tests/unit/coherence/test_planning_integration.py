from __future__ import annotations

import json
from pathlib import Path

import pytest

from coherence.cli import main
from tests.unit.coherence.test_planning_cli import (
    _approval,
    _check_args,
    _suggest_args,
    _write_fixture,
)

pytestmark = pytest.mark.unit


def test_plan_check_to_review_to_suggest_is_end_to_end(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    intent, spec, plan = _write_fixture(tmp_path, complete=True)

    assert main(_check_args(tmp_path, intent, spec, plan)) == 0
    report = json.loads(capsys.readouterr().out)
    decision_path = tmp_path / ".factory" / "planning" / "run-001" / "review-decision.json"
    decision_path.write_text(json.dumps(_approval(report)), encoding="utf-8")

    assert main(_suggest_args(tmp_path)) == 0

    suggestion = json.loads(capsys.readouterr().out)
    assert suggestion["action"] == "suggest_downstream"
    assert suggestion["starts_automatically"] is False
    assert not (tmp_path / ".factory" / "runs").exists()
