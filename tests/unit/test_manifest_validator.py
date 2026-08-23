import pytest
from factory.validation.manifest_validator import validate_manifest

pytestmark = pytest.mark.unit


def _manifest(tmp_path, checks=None, **ctx):
    (tmp_path / "tasks").mkdir(exist_ok=True)
    (tmp_path / "tasks" / "T-001.md").write_text("dod", encoding="utf-8")
    base = {
        "task_id": "T-001",
        "generated_by": "context-gatherer",
        "generated_at": "2026-07-16T14:32:10Z",
        "coherence": {"checks": checks if checks is not None else []},
        "context": {"task": "tasks/T-001.md", "source_files": [], "skills": []},
        "reject": None,
    }
    base["context"].update(ctx)
    return base


def test_empty_checks_now_rejected(tmp_path):
    # A context-gatherer that emits zero proof obligations must fail schema
    # validation, not pass silently (spec §1 gap 3).
    errors = validate_manifest(_manifest(tmp_path), tmp_path)  # default checks=[]
    assert any("checks" in e for e in errors)


def test_valid_manifest_with_one_check(tmp_path):
    (tmp_path / "spec.md").write_text("x", encoding="utf-8")
    checks = [{"name": "n", "kind": "files_exist", "args": {"paths": ["spec.md"]}}]
    errors = validate_manifest(_manifest(tmp_path, checks=checks), tmp_path)
    assert errors == []


def test_missing_source_file_reports_error(tmp_path):
    m = _manifest(
        tmp_path,
        checks=[{"name": "c", "kind": "files_exist", "args": {"paths": ["tasks/T-001.md"]}}],
        source_files=["src/does_not_exist.py"],
    )
    errors = validate_manifest(m, tmp_path)
    assert any("does_not_exist" in e for e in errors)


def test_anchor_is_stripped_before_existence_check(tmp_path):
    (tmp_path / "spec.md").write_text("x", encoding="utf-8")
    m = _manifest(
        tmp_path,
        checks=[{"name": "c", "kind": "files_exist", "args": {"paths": ["spec.md"]}}],
        spec=["spec.md#section"],
    )
    assert validate_manifest(m, tmp_path) == []


def test_legacy_pass_field_is_stripped_not_rejected(tmp_path):
    # A valid check with a stray `pass` field is normalized (stripped), then
    # evaluated normally -- a model-format quirk must not block the pipeline.
    (tmp_path / "real.py").write_text("x", encoding="utf-8")
    m = _manifest(tmp_path, checks=[{"name": "x", "kind": "files_exist", "args": {"paths": ["real.py"]}, "pass": True}])
    assert validate_manifest(m, tmp_path) == []


def test_legacy_proven_field_is_stripped_not_rejected(tmp_path):
    m = _manifest(
        tmp_path,
        checks=[{"name": "c", "kind": "files_exist", "args": {"paths": ["tasks/T-001.md"]}}],
    )
    m["coherence"]["proven"] = True
    assert validate_manifest(m, tmp_path) == []


def test_evidence_style_checks_are_dropped_but_the_resulting_emptiness_now_fails_schema(tmp_path):
    # Regression pedigree unchanged: deepseek-v4-flash emitted checks like
    # {"name": "x", "evidence": "recorder.py exists", "pass": false} with no
    # kind/args -- normalize_manifest still strips them (no machine-verifiable
    # claim survives). What changes here is what happens AFTER stripping: a
    # manifest whose checks are stripped to [] is exactly "zero proof
    # obligations, still schema-valid" -- the bug spec §1 gap 3 targets, in a
    # different disguise -- so minItems: 1 now catches it as a schema error
    # instead of a silent pass. This is the new, correct default-deny stance,
    # not a regression of the original strip-not-reject fix: the STRIPPING
    # behavior (hollow checks never survive into the manifest) is unchanged
    # and still asserted below; only the final validity verdict changed.
    m = _manifest(
        tmp_path,
        checks=[
            {"name": "c1", "evidence": "src/sim/recorder.py exists", "pass": False},
            {"name": "c2", "evidence": "test file exists", "pass": True},
        ],
    )
    errors = validate_manifest(m, tmp_path)
    assert any("checks" in e for e in errors)
    assert m["coherence"]["checks"] == []


def test_connector_check_evaluated_pass(tmp_path):
    (tmp_path / "real.py").write_text("x", encoding="utf-8")
    m = _manifest(tmp_path, checks=[{"name": "c", "kind": "files_exist", "args": {"paths": ["real.py"]}}])
    assert validate_manifest(m, tmp_path) == []


def test_connector_check_evaluated_fail(tmp_path):
    m = _manifest(tmp_path, checks=[{"name": "c", "kind": "files_exist", "args": {"paths": ["ghost.py"]}}])
    errors = validate_manifest(m, tmp_path)
    assert any("ghost.py" in e for e in errors)


def test_unknown_kind_rejected(tmp_path):
    m = _manifest(tmp_path, checks=[{"name": "c", "kind": "made_up", "args": {}}])
    errors = validate_manifest(m, tmp_path)
    assert any("unknown kind" in e for e in errors)


def test_coverage_floor_requires_modify_deliverable(tmp_path):
    from factory.orchestrator.ledger import Task
    from pathlib import Path
    task = Task(id="T-001", title="t", status="todo", dod=["done"],
                body="- Modify: `src/b.py`", path=Path("x"))
    # Manifest gathered nothing but a real, passing, unrelated check; the
    # Modify: deliverable is still uncovered even though every declared check
    # passes -> still an error (honest-but-hollow).
    m = _manifest(
        tmp_path,
        checks=[{"name": "c", "kind": "files_exist", "args": {"paths": ["tasks/T-001.md"]}}],
    )
    errors = validate_manifest(m, tmp_path, task=task)
    assert any("src/b.py" in e and "not gathered" in e for e in errors)


def test_manifest_task_id_mismatch_rejected(tmp_path):
    from substrate.ledger.tasks import Task
    m = _manifest(tmp_path, checks=[{"name": "n", "kind": "k", "args": {}}])
    m["task_id"] = "T-999"  # gathered for a different task than the one running
    task = Task(id="T-001", title="t", status="todo", dod=["d"], body="", path=tmp_path / "tasks" / "T-001.md")
    errors = validate_manifest(m, tmp_path, task=task)
    assert any("task_id" in e for e in errors)


def test_manifest_task_id_match_accepted(tmp_path):
    from substrate.ledger.tasks import Task
    m = _manifest(tmp_path, checks=[{"name": "n", "kind": "k", "args": {}}])
    task = Task(id="T-001", title="t", status="todo", dod=["d"], body="", path=tmp_path / "tasks" / "T-001.md")
    errors = validate_manifest(m, tmp_path, task=task)
    assert not any("task_id" in e for e in errors)
