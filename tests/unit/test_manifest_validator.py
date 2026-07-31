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


def test_valid_manifest_no_checks(tmp_path):
    assert validate_manifest(_manifest(tmp_path), tmp_path) == []


def test_missing_source_file_reports_error(tmp_path):
    m = _manifest(tmp_path, source_files=["src/does_not_exist.py"])
    errors = validate_manifest(m, tmp_path)
    assert any("does_not_exist" in e for e in errors)


def test_anchor_is_stripped_before_existence_check(tmp_path):
    (tmp_path / "spec.md").write_text("x", encoding="utf-8")
    m = _manifest(tmp_path, spec=["spec.md#section"])
    assert validate_manifest(m, tmp_path) == []


def test_legacy_pass_field_is_stripped_not_rejected(tmp_path):
    # A valid check with a stray `pass` field is normalized (stripped), then
    # evaluated normally -- a model-format quirk must not block the pipeline.
    (tmp_path / "real.py").write_text("x", encoding="utf-8")
    m = _manifest(tmp_path, checks=[{"name": "x", "kind": "files_exist", "args": {"paths": ["real.py"]}, "pass": True}])
    assert validate_manifest(m, tmp_path) == []


def test_legacy_proven_field_is_stripped_not_rejected(tmp_path):
    m = _manifest(tmp_path)
    m["coherence"]["proven"] = True
    assert validate_manifest(m, tmp_path) == []


def test_evidence_style_checks_are_dropped_not_rejected(tmp_path):
    # Regression: deepseek-v4-flash emitted checks like
    # {"name": "x", "evidence": "recorder.py exists", "pass": false} with no
    # kind/args -- the schema rejected every one and the whole task died on the
    # first execution. Such checks carry no machine-verifiable claim and are
    # dropped; the manifest still validates (context refs still checked).
    m = _manifest(
        tmp_path,
        checks=[
            {"name": "c1", "evidence": "src/sim/recorder.py exists", "pass": False},
            {"name": "c2", "evidence": "test file exists", "pass": True},
        ],
    )
    assert validate_manifest(m, tmp_path) == []
    # The dropped checks must not survive into the manifest (hollow claims).
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
    # Manifest gathered nothing; the Modify: deliverable is uncovered even though
    # every declared check passes -> still an error (honest-but-hollow).
    m = _manifest(tmp_path)
    errors = validate_manifest(m, tmp_path, task=task)
    assert any("src/b.py" in e and "not gathered" in e for e in errors)
