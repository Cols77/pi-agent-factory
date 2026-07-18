import pytest
from factory.validation.schema_validator import validate, SCHEMA_DIR

pytestmark = pytest.mark.unit

MANIFEST = SCHEMA_DIR / "context_manifest.schema.json"


def test_valid_manifest_passes():
    obj = {
        "task_id": "T-001",
        "generated_by": "context-gatherer",
        "generated_at": "2026-07-16T14:32:10Z",
        "coherence": {"proven": True, "checks": [{"name": "x", "pass": True}]},
        "context": {"task": "tasks/T-001.md", "source_files": [], "skills": []},
        "reject": None,
    }
    assert validate(obj, MANIFEST) == []


def test_missing_required_field_reports_error():
    obj = {"task_id": "T-001"}
    errors = validate(obj, MANIFEST)
    assert errors  # non-empty


def test_bad_task_id_pattern_reports_error():
    obj = {
        "task_id": "001",
        "generated_by": "context-gatherer",
        "generated_at": "2026-07-16T14:32:10Z",
        "coherence": {"proven": True, "checks": []},
        "context": {"task": "t", "source_files": [], "skills": []},
    }
    assert any("task_id" in e for e in validate(obj, MANIFEST))
