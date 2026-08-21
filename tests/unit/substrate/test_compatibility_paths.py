"""Every legacy factory module extracted in this increment must still work
from its old import path -- it just warns once, naming the substrate
replacement, and returns results identical to the new module."""
from __future__ import annotations

import importlib
import sys
import warnings
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
KB_DIR = REPO_ROOT / "kb"


def _import_fresh(module_name: str):
    sys.modules.pop(module_name, None)
    return importlib.import_module(module_name)


def _warning_messages(caught: list[warnings.WarningMessage]) -> list[str]:
    return [str(item.message) for item in caught if item.category is DeprecationWarning]


def test_factory_paths_warns_once_and_matches_substrate_paths():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", DeprecationWarning)
        old = _import_fresh("factory.paths")

    assert len(caught) == 1
    assert caught[0].category is DeprecationWarning
    assert str(caught[0].message) == "factory.paths is deprecated; import substrate.paths"

    new = importlib.import_module("substrate.paths")
    assert old.factory_root() == new.factory_root()
    assert old.factory_skills_dir() == new.factory_skills_dir()
    assert old.scope_guard_extension() == new.scope_guard_extension()


def test_factory_validation_schema_validator_warns_once_and_matches_substrate():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", DeprecationWarning)
        old = _import_fresh("factory.validation.schema_validator")

    assert len(caught) == 1
    assert caught[0].category is DeprecationWarning
    assert str(caught[0].message) == (
        "factory.validation.schema_validator is deprecated; import substrate.validators.schema"
    )

    new = importlib.import_module("substrate.validators.schema")
    assert old.SCHEMA_DIR == new.SCHEMA_DIR

    schema = {"type": "object", "required": ["x"], "properties": {"x": {"type": "string"}}}
    assert old.validate_against({"x": "ok"}, schema) == new.validate_against({"x": "ok"}, schema)
    assert old.validate_against({}, schema) == new.validate_against({}, schema)

    schema_path = new.SCHEMA_DIR / "kb_entry.schema.json"
    instance = {"id": "kb-0001", "title": "t", "status": "active", "severity": "low",
                "tags": [], "scope": {"files": []}}
    assert old.validate(instance, schema_path) == new.validate(instance, schema_path)


def test_factory_validation_kb_validator_warns_once_and_matches_substrate():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", DeprecationWarning)
        old = _import_fresh("factory.validation.kb_validator")

    assert len(caught) == 1
    assert caught[0].category is DeprecationWarning
    assert str(caught[0].message) == (
        "factory.validation.kb_validator is deprecated; import substrate.validators.kb"
    )

    new = importlib.import_module("substrate.validators.kb")
    path = KB_DIR / "kb-0001-example-entry.md"
    assert old.parse_entry(path) == new.parse_entry(path)
    assert old.validate_entry_file(path) == new.validate_entry_file(path) == []


def test_factory_validation_session_validator_warns_once_and_matches_substrate():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", DeprecationWarning)
        old = _import_fresh("factory.validation.session_validator")

    assert len(caught) == 1
    assert caught[0].category is DeprecationWarning
    assert str(caught[0].message) == (
        "factory.validation.session_validator is deprecated; import substrate.validators.session"
    )

    new = importlib.import_module("substrate.validators.session")
    record = {
        "session_id": "s1",
        "started_at": "2026-07-16T14:30:00Z",
        "model_backend": "anthropic:claude-opus-4-8",
        "tasks": [
            {
                "task_id": "T-001",
                "outcome": "completed",
                "nodes": [{"node": "dev", "result": "pass"}],
                "dod": {"met": True},
            }
        ],
    }
    assert old.validate_session(record) == new.validate_session(record) == []

    bad_record = {**record, "tasks": [{**record["tasks"][0], "dod": {"met": False}}]}
    assert old.validate_session(bad_record) == new.validate_session(bad_record)
    assert old.validate_session(bad_record) != []
