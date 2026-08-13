import json

import pytest
from factory.validation.schema_validator import validate, SCHEMA_DIR

pytestmark = pytest.mark.unit

MANIFEST = SCHEMA_DIR / "context_manifest.schema.json"

ARTIFACT_SCHEMA_CASES = [
    (
        "feat",
        "^FEAT-[A-Z0-9-]+$",
        ["id", "title", "requirements"],
        {"id": "FEAT-NAV-017", "title": "Target reacquisition", "requirements": ["SR-001"]},
    ),
    (
        "metric",
        "^MET-[A-Z0-9-]+$",
        ["id", "title"],
        {"id": "MET-NAV-004", "title": "Reacquisition rate"},
    ),
    (
        "goal",
        "^GOAL-[A-Z0-9-]+$",
        ["id", "title", "feature", "requirements", "metric", "target"],
        {
            "id": "GOAL-NAV-003",
            "title": "Reach the target reacquisition rate",
            "feature": "FEAT-NAV-017",
            "requirements": ["SR-001"],
            "metric": "MET-NAV-004",
            "target": ">= 0.90",
        },
    ),
    (
        "diag",
        "^DIAG-[A-Z0-9-]+$",
        ["id", "kind", "title", "illustrates", "diagram_file"],
        {
            "id": "DIAG-NAV-001",
            "kind": "diag",
            "title": "Navigator overview",
            "focus": "Traceability",
            "illustrates": "FEAT-NAV-017",
            "diagram_file": "DIAG-NAV-003.html",
        },
    ),
]

ARTIFACT_DOCUMENTS = {kind: document for kind, _, _, document in ARTIFACT_SCHEMA_CASES}

INVALID_ARTIFACT_DOCUMENT_CASES = [
    ("feat", "empty requirements", {"requirements": []}),
    ("feat", "non-SR requirement", {"requirements": ["BR-001"]}),
    ("goal", "empty requirements", {"requirements": []}),
    ("goal", "non-SR requirement", {"requirements": ["BR-001"]}),
    ("goal", "non-feature feature reference", {"feature": "MET-NAV-004"}),
    ("goal", "non-metric metric reference", {"metric": "FEAT-NAV-017"}),
    ("goal", "blank target", {"target": ""}),
    ("goal", "non-string target", {"target": 0.9}),
    ("diag", "bad diagram id", {"id": "FEAT-NAV-001"}),
    ("diag", "wrong kind", {"kind": "feat"}),
    ("diag", "non-HTML diagram file", {"diagram_file": "diagram.mmd"}),
    ("diag", "unknown property", {"unknown": True}),
    ("feat", "unknown property", {"unknown": True}),
    ("metric", "unknown property", {"unknown": True}),
    ("goal", "unknown property", {"unknown": True}),
]


@pytest.mark.parametrize(("kind", "id_pattern", "required", "document"), ARTIFACT_SCHEMA_CASES)
def test_artifact_schema_contracts(kind, id_pattern, required, document):
    schema_path = SCHEMA_DIR / f"{kind}.schema.json"

    assert schema_path.is_file()
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["$id"] == f"https://factory.local/schemas/{kind}.schema.json"
    assert schema["title"]
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(required)
    assert schema["properties"]["id"] == {"type": "string", "pattern": id_pattern}
    assert schema["properties"]["title"] == {"type": "string", "minLength": 1}
    assert validate(document, schema_path) == []


@pytest.mark.parametrize(("kind", "case", "overrides"), INVALID_ARTIFACT_DOCUMENT_CASES)
def test_artifact_schemas_reject_invalid_documents(kind, case, overrides):
    schema_path = SCHEMA_DIR / f"{kind}.schema.json"
    document = {**ARTIFACT_DOCUMENTS[kind], **overrides}

    assert validate(document, schema_path), case


def test_diag_schema_requires_kind():
    schema_path = SCHEMA_DIR / "diag.schema.json"
    document = {key: value for key, value in ARTIFACT_DOCUMENTS["diag"].items() if key != "kind"}

    assert validate(document, schema_path)


def test_diag_schema_accepts_an_omitted_optional_focus():
    document = {key: value for key, value in ARTIFACT_DOCUMENTS["diag"].items() if key != "focus"}

    assert validate(document, SCHEMA_DIR / "diag.schema.json") == []


def test_diag_schema_accepts_canonical_list_frontmatter_with_html_artifact():
    document = {
        "id": "DIAG-NAV-001",
        "kind": "diag",
        "title": "Navigator overview",
        "focus": ["NAV-REQ-021"],
        "illustrates": ["FEAT-NAV-017"],
        "diagram_file": "DIAG-NAV-003.html",
    }

    assert validate(document, SCHEMA_DIR / "diag.schema.json") == []


def test_valid_manifest_passes():
    obj = {
        "task_id": "T-001",
        "generated_by": "context-gatherer",
        "generated_at": "2026-07-16T14:32:10Z",
        "coherence": {"checks": [{"name": "x", "kind": "files_exist", "args": {"paths": ["a"]}}]},
        "context": {"task": "tasks/T-001.md", "source_files": [], "skills": []},
        "reject": None,
    }
    assert validate(obj, MANIFEST) == []


def test_missing_required_field_reports_error():
    obj = {"task_id": "T-001"}
    errors = validate(obj, MANIFEST)
    assert errors  # non-empty


def test_bad_datetime_format_reports_error():
    obj = {
        "task_id": "T-001",
        "generated_by": "context-gatherer",
        "generated_at": "not-a-date",
        "coherence": {"checks": []},
        "context": {"task": "t", "source_files": [], "skills": []},
    }
    assert any("generated_at" in e for e in validate(obj, MANIFEST))


def test_bad_task_id_pattern_reports_error():
    obj = {
        "task_id": "001",
        "generated_by": "context-gatherer",
        "generated_at": "2026-07-16T14:32:10Z",
        "coherence": {"checks": []},
        "context": {"task": "t", "source_files": [], "skills": []},
    }
    assert any("task_id" in e for e in validate(obj, MANIFEST))


def test_validate_against_accepts_dict_schema():
    from factory.validation.schema_validator import validate_against
    schema = {"type": "object", "required": ["x"], "properties": {"x": {"type": "string"}}}
    assert validate_against({"x": "ok"}, schema) == []
    errs = validate_against({}, schema)
    assert errs and any("x" in e for e in errs)
