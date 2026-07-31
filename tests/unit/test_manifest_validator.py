import pytest
from factory.validation.manifest_validator import validate_manifest

pytestmark = pytest.mark.unit


def _manifest(tmp_path, **ctx):
    (tmp_path / "tasks").mkdir()
    (tmp_path / "tasks" / "T-001.md").write_text("dod", encoding="utf-8")
    base = {
        "task_id": "T-001",
        "generated_by": "context-gatherer",
        "generated_at": "2026-07-16T14:32:10Z",
        "coherence": {"proven": True, "checks": [{"name": "x", "pass": True}]},
        "context": {"task": "tasks/T-001.md", "source_files": [], "skills": []},
        "reject": None,
    }
    base["context"].update(ctx)
    return base


def test_valid_manifest_with_existing_paths(tmp_path):
    assert validate_manifest(_manifest(tmp_path), tmp_path) == []


def test_missing_source_file_reports_error(tmp_path):
    m = _manifest(tmp_path, source_files=["src/does_not_exist.py"])
    errors = validate_manifest(m, tmp_path)
    assert any("does_not_exist" in e for e in errors)


def test_anchor_is_stripped_before_existence_check(tmp_path):
    (tmp_path / "spec.md").write_text("x", encoding="utf-8")
    m = _manifest(tmp_path, spec=["spec.md#section"])
    assert validate_manifest(m, tmp_path) == []


def test_unproven_manifest_fails_gate(tmp_path):
    m = _manifest(tmp_path, source_files=["nope.py"])
    m["coherence"]["proven"] = False
    # Gate per spec: "coherence.proven === true" is required to pass, even
    # though the manifest is otherwise schema-valid (a REJECT manifest).
    errors = validate_manifest(m, tmp_path)
    assert errors
    assert any("proven" in e for e in errors)


def test_proven_true_with_failing_check_fails_gate(tmp_path):
    m = _manifest(tmp_path)
    m["coherence"]["checks"] = [{"name": "task-exists", "pass": False, "evidence": "missing"}]
    errors = validate_manifest(m, tmp_path)
    assert errors
    assert any("task-exists" in e for e in errors)
