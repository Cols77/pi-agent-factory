"""Tests for factory.system.story.query_story (increment B, forward half of
the V-cycle: open a task, see how it was implemented).

`write_task`, `write_manifest`, `write_session` are imported as fixture
factories from `._fixtures` -- see that module's docstring for why they are
separate objects from the plain, directly-callable builders other test
files in this package use.
"""
import json

import pytest
from factory.system.models import SystemScopeRef
from factory.system.story import query_story
from factory.validation.schema_validator import SCHEMA_DIR, validate_against

from ._fixtures import _write_task_fixture, _write_manifest_fixture, _write_session_fixture  # noqa: F401

pytestmark = pytest.mark.unit

_RESPONSE_SCHEMA = json.loads(
    (SCHEMA_DIR / "system_response.schema.json").read_text(encoding="utf-8")
)
_STORY_SCHEMA = {
    "$defs": _RESPONSE_SCHEMA["$defs"],
    "properties": {"story": _RESPONSE_SCHEMA["properties"]["story"]},
    "$ref": "#/properties/story",
}


def test_manifest_runs_carry_implementation_detail(tmp_path, write_task, write_manifest):
    write_task(tmp_path, "T-059", status="done", satisfies=["SR-146"])
    write_manifest(tmp_path, run_id="r1", task_id="T-059", outcome="completed",
                   changed_files=["src/a.py"])

    result = query_story(tmp_path, SystemScopeRef(kind="task", ref="task:T-059"))

    assert result["task"]["id"] == "T-059"
    assert len(result["runs"]) == 1
    run = result["runs"][0]
    assert run["source"] == "manifest"
    assert run["implementation"]["changed_files"] == ["src/a.py"]
    assert result["requirements"] == ["sr:SR-146"]


def test_session_only_runs_report_implementation_missing(tmp_path, write_task, write_session):
    write_task(tmp_path, "T-055", status="done", satisfies=[])
    write_session(tmp_path, "s1", "T-055", "completed")

    run = query_story(tmp_path, SystemScopeRef(kind="task", ref="task:T-055"))["runs"][0]

    assert run["source"] == "session"
    assert run["implementation"]["kind"] == "missing"
    assert run["implementation"]["freshness"]["state"] == "n/a"
    assert run["citation"]["kind"] == "session"


def test_a_manifest_wins_over_a_session_record_for_the_same_run(tmp_path, write_task,
                                                                write_manifest, write_session):
    write_task(tmp_path, "T-059", status="done", satisfies=[])
    write_manifest(tmp_path, run_id="dup", task_id="T-059", outcome="completed",
                   changed_files=["src/a.py"])
    write_session(tmp_path, "dup", "T-059", "completed")

    runs = query_story(tmp_path, SystemScopeRef(kind="task", ref="task:T-059"))["runs"]

    assert len(runs) == 1
    assert runs[0]["source"] == "manifest"


def test_a_task_with_no_runs_still_renders_with_history_missing(tmp_path, write_task):
    write_task(tmp_path, "T-070", status="todo", satisfies=["SR-1"])

    result = query_story(tmp_path, SystemScopeRef(kind="task", ref="task:T-070"))

    assert result["runs"] == []
    assert result["degraded"] is True
    assert any("no recorded runs" in r for r in result["degraded_reasons"])
    assert result["requirements"] == ["sr:SR-1"]


def test_an_unknown_task_raises_scope_not_found(tmp_path):
    from factory.system.queries import ScopeNotFoundError
    with pytest.raises(ScopeNotFoundError):
        query_story(tmp_path, SystemScopeRef(kind="task", ref="task:T-999"))


def test_story_validates_against_the_response_schemas_story_member(
    tmp_path, write_task, write_manifest, write_session
):
    # Covers both a manifest run and a session-only run in one story, plus
    # an unmappable satisfies entry, so every branch of the schema's
    # storyRun/storyImplementation shape is exercised at once.
    write_task(tmp_path, "T-059", status="done", satisfies=["SR-146", "not-an-sr"])
    write_manifest(tmp_path, run_id="r1", task_id="T-059", outcome="completed",
                   changed_files=["src/a.py"])
    write_session(tmp_path, "s1", "T-059", "completed")

    result = query_story(tmp_path, SystemScopeRef(kind="task", ref="task:T-059"))

    assert validate_against(result, _STORY_SCHEMA) == []
