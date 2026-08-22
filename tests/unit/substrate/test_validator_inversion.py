"""substrate.validators.manifest inverts control: the pure schema/normalize/
context-ref logic lives in substrate, while connector evaluation and the
coverage floor -- both of which need factory.evidence machinery -- are
injected as callables by the factory-side caller. These tests exercise the
pure function directly (including that its two callables are only invoked
once schema validation has passed) and prove the legacy
factory.validation.manifest_validator.validate_manifest wrapper, wired with
the real factory.evidence callables, produces identical results to before."""
from __future__ import annotations

import copy
from pathlib import Path

import pytest

from substrate.validators.manifest import (
    context_ref_errors,
    normalize_manifest,
    validate_manifest_document,
)

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


def _no_errors(_normalized: dict) -> list[str]:
    return []


class _CountingErrors:
    def __init__(self, errors=None):
        self.errors = errors or []
        self.calls = 0

    def __call__(self, normalized: dict) -> list[str]:
        self.calls += 1
        return list(self.errors)


def test_normalize_manifest_strips_agent_junk_fields_and_hollow_checks():
    manifest = {
        "coherence": {
            "proven": True,
            "pass": True,
            "checks": [
                {"name": "c1", "kind": "files_exist", "args": {"paths": ["a"]}, "pass": True},
                {"name": "c2", "evidence": "looks fine"},
                "not-a-dict",
            ],
        }
    }
    normalized = normalize_manifest(manifest)
    assert "proven" not in normalized["coherence"]
    assert "pass" not in normalized["coherence"]
    assert normalized["coherence"]["checks"] == [
        {"name": "c1", "kind": "files_exist", "args": {"paths": ["a"]}}
    ]


def test_normalize_manifest_is_a_noop_without_a_coherence_dict():
    manifest = {"context": {}}
    assert normalize_manifest(manifest) is manifest


def test_context_ref_errors_reports_missing_paths_and_strips_anchors(tmp_path):
    (tmp_path / "spec.md").write_text("x", encoding="utf-8")
    manifest = {
        "context": {
            "task": "tasks/does_not_exist.md",
            "spec": ["spec.md#section"],
            "source_files": ["src/missing.py"],
        }
    }
    errors = context_ref_errors(manifest, tmp_path)
    assert any("does_not_exist" in e for e in errors)
    assert any("src/missing.py" in e for e in errors)
    assert not any("spec.md" in e for e in errors)  # anchor stripped, file exists


def test_validate_manifest_document_returns_schema_errors_without_invoking_callables(tmp_path):
    check_errors = _CountingErrors()
    coverage_errors = _CountingErrors()

    errors = validate_manifest_document(
        {"task_id": "T-001"}, tmp_path, check_errors, coverage_errors
    )

    assert errors  # schema-invalid: missing required fields
    assert check_errors.calls == 0
    assert coverage_errors.calls == 0


def test_validate_manifest_document_merges_context_check_and_coverage_errors(tmp_path):
    manifest = _manifest(tmp_path, source_files=["src/missing.py"])
    check_errors = _CountingErrors(["check failed"])
    coverage_errors = _CountingErrors(["coverage failed"])

    errors = validate_manifest_document(manifest, tmp_path, check_errors, coverage_errors)

    assert check_errors.calls == 1
    assert coverage_errors.calls == 1
    assert "check failed" in errors
    assert "coverage failed" in errors
    assert any("src/missing.py" in e for e in errors)


def test_validate_manifest_document_passes_the_normalized_manifest_to_callables(tmp_path):
    seen: dict = {}

    def _check_errors(normalized: dict) -> list[str]:
        seen["checks"] = normalized["coherence"]["checks"]
        return []

    manifest = _manifest(
        tmp_path,
        checks=[{"name": "c", "kind": "files_exist", "args": {"paths": []}, "pass": True}],
    )
    assert validate_manifest_document(manifest, tmp_path, _check_errors, _no_errors) == []
    assert seen["checks"] == [{"name": "c", "kind": "files_exist", "args": {"paths": []}}]


def test_validate_manifest_document_valid_manifest_no_checks_is_clean(tmp_path):
    manifest = _manifest(tmp_path)
    assert validate_manifest_document(manifest, tmp_path, _no_errors, _no_errors) == []


# -- Parity with the legacy factory-side wrapper -----------------------------


def test_pure_document_matches_legacy_validate_manifest_for_a_passing_connector_check(tmp_path):
    from factory.evidence.connectors import DEFAULT_REGISTRY
    from factory.evidence.types import EvidenceContext
    from factory.validation.manifest_validator import validate_manifest as legacy_validate_manifest

    (tmp_path / "real.py").write_text("x", encoding="utf-8")
    manifest = _manifest(
        tmp_path, checks=[{"name": "c", "kind": "files_exist", "args": {"paths": ["real.py"]}}]
    )
    ctx = EvidenceContext(repo_root=tmp_path, gates=None, kb_dir=tmp_path / "kb")

    def _check_errors(normalized: dict) -> list[str]:
        return DEFAULT_REGISTRY.evaluate_checks(normalized.get("coherence", {}).get("checks", []), ctx)

    pure_errors = validate_manifest_document(
        copy.deepcopy(manifest), tmp_path, _check_errors, _no_errors
    )
    legacy_errors = legacy_validate_manifest(copy.deepcopy(manifest), tmp_path)

    assert pure_errors == legacy_errors == []


def test_pure_document_matches_legacy_validate_manifest_for_a_failing_connector_check(tmp_path):
    from factory.evidence.connectors import DEFAULT_REGISTRY
    from factory.evidence.types import EvidenceContext
    from factory.validation.manifest_validator import validate_manifest as legacy_validate_manifest

    manifest = _manifest(
        tmp_path, checks=[{"name": "c", "kind": "files_exist", "args": {"paths": ["ghost.py"]}}]
    )
    ctx = EvidenceContext(repo_root=tmp_path, gates=None, kb_dir=tmp_path / "kb")

    def _check_errors(normalized: dict) -> list[str]:
        return DEFAULT_REGISTRY.evaluate_checks(normalized.get("coherence", {}).get("checks", []), ctx)

    pure_errors = validate_manifest_document(
        copy.deepcopy(manifest), tmp_path, _check_errors, _no_errors
    )
    legacy_errors = legacy_validate_manifest(copy.deepcopy(manifest), tmp_path)

    assert pure_errors == legacy_errors
    assert any("ghost.py" in e for e in pure_errors)


def test_pure_document_matches_legacy_validate_manifest_for_the_coverage_floor(tmp_path):
    from factory.evidence.coverage import coverage_errors as compute_coverage_errors
    from factory.orchestrator.ledger import Task
    from factory.validation.manifest_validator import validate_manifest as legacy_validate_manifest

    task = Task(
        id="T-001", title="t", status="todo", dod=["done"],
        body="- Modify: `src/b.py`", path=Path("x"),
    )
    manifest = _manifest(tmp_path)

    def _coverage_errors(normalized: dict) -> list[str]:
        return compute_coverage_errors(task.body, normalized.get("context", {}), tmp_path)

    pure_errors = validate_manifest_document(
        copy.deepcopy(manifest), tmp_path, _no_errors, _coverage_errors
    )
    legacy_errors = legacy_validate_manifest(copy.deepcopy(manifest), tmp_path, task=task)

    assert pure_errors == legacy_errors
    assert any("src/b.py" in e and "not gathered" in e for e in pure_errors)
