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


def test_runs_are_ordered_by_started_at_then_citation_path_on_ties(tmp_path, write_task, write_manifest):
    write_task(tmp_path, "T-080", status="done", satisfies=[])
    write_manifest(tmp_path, run_id="later", task_id="T-080", outcome="completed",
                   started_at="2026-08-09T10:00:00Z", ended_at="2026-08-09T10:30:00Z")
    write_manifest(tmp_path, run_id="earlier", task_id="T-080", outcome="completed",
                   started_at="2026-08-01T00:00:00Z", ended_at="2026-08-01T00:30:00Z")
    # Same started_at as each other -- only the citation path (which orders
    # by run_id, since the path is evidence/runs/<run_id>.json) can break
    # the tie; this is the exact defect the design calls out as already
    # fixed once in the timeline query.
    write_manifest(tmp_path, run_id="tie-b", task_id="T-080", outcome="completed",
                   started_at="2026-08-05T00:00:00Z", ended_at="2026-08-05T00:30:00Z")
    write_manifest(tmp_path, run_id="tie-a", task_id="T-080", outcome="completed",
                   started_at="2026-08-05T00:00:00Z", ended_at="2026-08-05T00:30:00Z")

    runs = query_story(tmp_path, SystemScopeRef(kind="task", ref="task:T-080"))["runs"]

    assert [r["run_id"] for r in runs] == ["earlier", "tie-a", "tie-b", "later"]


def test_escalated_and_rejected_manifest_runs_are_kept_not_filtered(tmp_path, write_task, write_manifest):
    write_task(tmp_path, "T-081", status="escalated", satisfies=[])
    write_manifest(tmp_path, run_id="r-rejected", task_id="T-081", outcome="rejected")
    write_manifest(tmp_path, run_id="r-escalated", task_id="T-081", outcome="escalated")

    runs = query_story(tmp_path, SystemScopeRef(kind="task", ref="task:T-081"))["runs"]

    assert sorted(r["outcome"] for r in runs) == ["escalated", "rejected"], (
        "a failed attempt is part of the story"
    )


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


_PLAN_TEXT = """\
# A Plan

### Task 1: First Component

Build the first thing.

### Task 2: Second Component

Build the second thing.
"""


def _write_plan_file(repo_root, name="p.md", text=_PLAN_TEXT):
    plans = repo_root / "docs" / "superpowers" / "plans"
    plans.mkdir(parents=True, exist_ok=True)
    (plans / name).write_text(text, encoding="utf-8")
    return f"docs/superpowers/plans/{name}"


def test_plan_section_resolves_by_title(tmp_path, write_task):
    plan_ref = _write_plan_file(tmp_path)
    # source_task deliberately disagrees with the title: title must win, so a
    # plan whose numbering shifted still resolves to the right section.
    write_task(tmp_path, "T-001", title="Second Component", source_plan=plan_ref, source_task=1)

    section = query_story(tmp_path, SystemScopeRef(kind="task", ref="task:T-001"))["plan_section"]

    assert section["heading"] == "Task 2: Second Component"
    assert section["plan_path"] == plan_ref
    assert "Build the second thing." in section["body"]


def test_plan_section_falls_back_to_source_task_number(tmp_path, write_task):
    plan_ref = _write_plan_file(tmp_path)
    write_task(tmp_path, "T-001", title="Renamed Since", source_plan=plan_ref, source_task=2)

    section = query_story(tmp_path, SystemScopeRef(kind="task", ref="task:T-001"))["plan_section"]

    assert section["heading"] == "Task 2: Second Component"


def test_plan_section_is_none_without_source_plan(tmp_path, write_task):
    write_task(tmp_path, "T-001", title="No Plan")

    result = query_story(tmp_path, SystemScopeRef(kind="task", ref="task:T-001"))

    assert result["plan_section"] is None


def test_plan_section_is_none_when_the_plan_file_is_missing(tmp_path, write_task):
    write_task(tmp_path, "T-001", title="X", source_plan="docs/superpowers/plans/gone.md",
               source_task=1)

    result = query_story(tmp_path, SystemScopeRef(kind="task", ref="task:T-001"))

    assert result["plan_section"] is None


def test_plan_section_is_none_when_no_section_matches(tmp_path, write_task):
    plan_ref = _write_plan_file(tmp_path)
    write_task(tmp_path, "T-001", title="Nowhere In The Plan", source_plan=plan_ref, source_task=9)

    result = query_story(tmp_path, SystemScopeRef(kind="task", ref="task:T-001"))

    assert result["plan_section"] is None


def test_plan_section_validates_against_the_response_schema(tmp_path, write_task):
    plan_ref = _write_plan_file(tmp_path)
    write_task(tmp_path, "T-001", title="First Component", source_plan=plan_ref, source_task=1)

    result = query_story(tmp_path, SystemScopeRef(kind="task", ref="task:T-001"))

    validate_against(result, _STORY_SCHEMA)


def test_task_carries_its_definition_of_done(tmp_path, write_task):
    write_task(tmp_path, "T-001", title="X")

    result = query_story(tmp_path, SystemScopeRef(kind="task", ref="task:T-001"))

    # The fixture template writes a single `- done` dod entry.
    assert result["task"]["dod"] == ["done"]
    validate_against(result, _STORY_SCHEMA)
