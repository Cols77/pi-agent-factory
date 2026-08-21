"""Comprehensive legacy-import compatibility matrix (Coherence Increment 1B,
Task 4).

Every module moved to substrate across Tasks 1-3 must still import from its
old ``factory.*`` location for one release: it works with no ImportError, it
warns exactly once naming the new substrate path, and calling a
representative public callable from the old path produces results identical
to calling the same callable's new substrate home directly.

This file is the single read-top-to-bottom proof for the whole matrix. Most
entries already have deep behavioral-parity coverage elsewhere (per-task
compatibility tests written in Tasks 1-3); rather than duplicate that
edge-case coverage, this file:

  1. Parametrizes the "warns exactly once, names the new path" assertion
     across every whole-module shim in one table (`WHOLE_MODULE_SHIMS`).
  2. Adds a light "still works + identical result" check per module using a
     representative callable, reusing existing fixtures where the other
     tasks' tests already built them (see the ``_write_via_canonical_writer``
     reuse for evidence manifests, and the plan/task-board fixtures shared
     with ``test_compatibility_paths.py``).
  3. Closes the one real gap left by Tasks 1-3's own tests:
     ``factory.validation.manifest_validator`` has deep behavioral-parity
     coverage in ``tests/unit/substrate/test_validator_inversion.py`` and
     ``tests/unit/test_manifest_validator.py``, but nothing asserted that
     importing it emits the expected single DeprecationWarning -- that
     assertion is added here.
  4. Covers the two "mixed" shims (permanent + moved surface,
     ``__getattr__``-based) -- ``factory.orchestrator.types`` and
     ``factory.evidence.manifests`` -- with their own parametrized,
     per-symbol warning table, since those don't fit the whole-module
     pattern above.

See also: ``tests/unit/substrate/test_compatibility_paths.py`` (Tasks 1-3,
deep per-module behavioral parity) and ``tests/unit/substrate/
test_compatibility_shims.py`` (freshness-specific matrix, Increment 1
predecessor). Together with this file, every moved module's one-release
compatibility is proven.
"""
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


def _deprecations(caught: list[warnings.WarningMessage]) -> list[warnings.WarningMessage]:
    return [item for item in caught if item.category is DeprecationWarning]


# -- 1. Whole-module shims: every one warns exactly once, naming the new path.

WHOLE_MODULE_SHIMS = [
    ("factory.paths", "factory.paths is deprecated; import substrate.paths"),
    (
        "factory.validation.schema_validator",
        "factory.validation.schema_validator is deprecated; import substrate.validators.schema",
    ),
    (
        "factory.validation.kb_validator",
        "factory.validation.kb_validator is deprecated; import substrate.validators.kb",
    ),
    (
        "factory.validation.session_validator",
        "factory.validation.session_validator is deprecated; import substrate.validators.session",
    ),
    (
        "factory.validation.manifest_validator",
        "factory.validation.manifest_validator is deprecated; import substrate.validators.manifest",
    ),
    (
        "factory.orchestrator.ledger",
        "factory.orchestrator.ledger is deprecated; import substrate.ledger.tasks",
    ),
    (
        "factory.orchestrator.plan_to_tasks",
        "factory.orchestrator.plan_to_tasks is deprecated; import substrate.ledger.plans",
    ),
    (
        "factory.orchestrator.skills",
        "factory.orchestrator.skills is deprecated; import substrate.agents.skills "
        "and substrate.paths",
    ),
    (
        "factory.orchestrator.pi_backend",
        "factory.orchestrator.pi_backend is deprecated; import substrate.agents.backend "
        "and compose scope_for from factory.orchestrator.roles.ROLE_SCOPE",
    ),
]


@pytest.mark.parametrize("module_name,expected_message", WHOLE_MODULE_SHIMS)
def test_whole_module_shim_warns_exactly_once_naming_substrate(
    module_name: str, expected_message: str
):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", DeprecationWarning)
        _import_fresh(module_name)

    deprecation = _deprecations(caught)
    assert len(deprecation) == 1
    assert str(deprecation[0].message) == expected_message


# -- 2. Mixed (__getattr__-based) shims: only the moved symbols warn, and each
# warns exactly once naming its new substrate path.

MIXED_SHIM_SYMBOLS = [
    (
        "factory.orchestrator.types",
        "AgentResult",
        "factory.orchestrator.types.AgentResult is deprecated; import substrate.agents.model.AgentResult",
    ),
    (
        "factory.orchestrator.types",
        "InterruptionReason",
        "factory.orchestrator.types.InterruptionReason is deprecated; "
        "import substrate.agents.model.InterruptionReason",
    ),
    (
        "factory.evidence.manifests",
        "load_run_manifest",
        "factory.evidence.manifests.load_run_manifest is deprecated; "
        "import substrate.evidence.read.load_run_manifest",
    ),
    (
        "factory.evidence.manifests",
        "list_run_manifests",
        "factory.evidence.manifests.list_run_manifests is deprecated; "
        "import substrate.evidence.read.list_run_manifests",
    ),
    (
        "factory.evidence.manifests",
        "migrate_manifest",
        "factory.evidence.manifests.migrate_manifest is deprecated; "
        "import substrate.evidence.model.migrate_manifest",
    ),
    (
        "factory.evidence.manifests",
        "MANIFEST_SCHEMA_VERSION",
        "factory.evidence.manifests.MANIFEST_SCHEMA_VERSION is deprecated; "
        "import substrate.evidence.model.MANIFEST_SCHEMA_VERSION",
    ),
]


@pytest.mark.parametrize("module_name,attr_name,expected_message", MIXED_SHIM_SYMBOLS)
def test_mixed_shim_symbol_warns_exactly_once_naming_substrate(
    module_name: str, attr_name: str, expected_message: str
):
    module = _import_fresh(module_name)  # importing the module itself never warns

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", DeprecationWarning)
        getattr(module, attr_name)

    deprecation = _deprecations(caught)
    assert len(deprecation) == 1
    assert str(deprecation[0].message) == expected_message


# -- 3. Representative-callable "still works, identical results" checks. -----


def test_factory_paths_representative_callable_matches_substrate():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        old = _import_fresh("factory.paths")

    new = importlib.import_module("substrate.paths")
    assert old.factory_root() == new.factory_root()


def test_factory_validation_schema_validator_representative_callable_matches_substrate():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        old = _import_fresh("factory.validation.schema_validator")

    new = importlib.import_module("substrate.validators.schema")
    schema = {"type": "object", "required": ["x"], "properties": {"x": {"type": "string"}}}
    assert old.validate_against({"x": "ok"}, schema) == new.validate_against({"x": "ok"}, schema) == []


def test_factory_validation_kb_validator_representative_callable_matches_substrate():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        old = _import_fresh("factory.validation.kb_validator")

    new = importlib.import_module("substrate.validators.kb")
    path = KB_DIR / "kb-0001-example-entry.md"
    assert old.parse_entry(path) == new.parse_entry(path)


def test_factory_validation_session_validator_representative_callable_matches_substrate():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        old = _import_fresh("factory.validation.session_validator")

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


def test_factory_validation_manifest_validator_representative_callable_delegates_to_substrate(
    tmp_path,
):
    # validate_manifest is a genuine composition adapter (it injects
    # factory.evidence connector/coverage callables into substrate's pure
    # validate_manifest_document), so "identical results" here means it still
    # produces the same verdict as the pure substrate function wired with
    # equivalent callables -- deep parity for every branch is already proven
    # in tests/unit/substrate/test_validator_inversion.py; this just proves
    # the deprecated old import path still works end to end.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        old = _import_fresh("factory.validation.manifest_validator")

    (tmp_path / "tasks").mkdir()
    (tmp_path / "tasks" / "T-001.md").write_text("dod", encoding="utf-8")
    manifest = {
        "task_id": "T-001",
        "generated_by": "context-gatherer",
        "generated_at": "2026-07-16T14:32:10Z",
        "coherence": {"checks": []},
        "context": {"task": "tasks/T-001.md", "source_files": [], "skills": []},
        "reject": None,
    }
    assert old.validate_manifest(manifest, tmp_path) == []


def _write_task(tasks_dir, name, status="todo"):
    tasks_dir.mkdir(parents=True, exist_ok=True)
    (tasks_dir / name).write_text(
        f"---\nid: {name[:-3]}\ntitle: t\nstatus: {status}\ndod:\n  - x\n---\nbody\n",
        encoding="utf-8",
    )


def test_factory_orchestrator_ledger_representative_callable_matches_substrate(tmp_path):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        old = _import_fresh("factory.orchestrator.ledger")

    new = importlib.import_module("substrate.ledger.tasks")
    tasks_dir = tmp_path / "tasks"
    _write_task(tasks_dir, "T-001-a.md")
    assert old.load_tasks(tasks_dir) == new.load_tasks(tasks_dir)


def test_factory_orchestrator_plan_to_tasks_representative_callable_matches_substrate():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        old = _import_fresh("factory.orchestrator.plan_to_tasks")

    new = importlib.import_module("substrate.ledger.plans")
    text = "# no sections here\n"
    assert old.parse_plan_tasks(text) == new.parse_plan_tasks(text) == []


def test_factory_orchestrator_skills_representative_callable_matches_substrate(tmp_path):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        old = _import_fresh("factory.orchestrator.skills")

    from substrate.agents.skills import load_skill_block as new_load_skill_block

    (tmp_path / "s").mkdir()
    (tmp_path / "s" / "SKILL.md").write_text("---\nname: s\n---\n\nbody\n", encoding="utf-8")
    assert old.load_skill_block(tmp_path, "s") == new_load_skill_block(tmp_path, "s")


def test_factory_orchestrator_pi_backend_representative_callable_delegates_to_substrate():
    # PiAgentBackend's wrapper preserves the AgentRole-typed public signature
    # (role catalogue composition stays factory-side); "identical results"
    # for this shim means the pure re-exported helper is the exact same
    # object as substrate's, not a copy -- byte-identical behavior guaranteed
    # by identity rather than by re-running the parsing logic twice.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        old = _import_fresh("factory.orchestrator.pi_backend")

    from substrate.agents.backend import parse_pi_json as new_parse_pi_json

    assert old.parse_pi_json is new_parse_pi_json
    line = '{"type": "assistant", "message": {"content": [{"type": "text", "text": "hi"}]}}'
    assert old.parse_pi_json(line) == new_parse_pi_json(line)


def test_factory_orchestrator_types_representative_symbols_are_substrate_identity():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        old = _import_fresh("factory.orchestrator.types")

    from substrate.agents.model import AgentResult as SubstrateAgentResult
    from substrate.agents.model import InterruptionReason as SubstrateInterruptionReason

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        assert old.AgentResult is SubstrateAgentResult
        assert old.InterruptionReason is SubstrateInterruptionReason


def _manifest_dict(run_id: str = "run-1", task_id: str = "T-001") -> dict:
    return {
        "schema_version": 2,
        "run_id": run_id,
        "task_id": task_id,
        "started_at": "2026-08-07T12:00:00Z",
        "ended_at": "2026-08-07T12:01:00Z",
        "start_commit": "a" * 40,
        "result_commit": "b" * 40,
        "outcome": "completed",
        "inputs": {
            "task": {"path": "tasks/T-001.md", "sha256": "c" * 64},
            "requirements": [],
            "factory_config_sha256": "d" * 64,
        },
        "dependencies": [],
        "implementation": {
            "changed_files": ["src/a.py"],
            "patch": {"sha256": "e" * 64, "size": 12, "media_type": "text/x-diff"},
        },
        "validation": [],
        "reviews": [],
        "decisions": [],
        "publication": {"state": "local", "errors": []},
    }


def test_factory_evidence_manifests_representative_callables_match_substrate(tmp_path):
    # Reuses the same "write via the one canonical writer, read back via the
    # moved function" pattern as test_evidence_read_model.py (Task 3), rather
    # than hand-rolling a second on-disk fixture shape.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        old = _import_fresh("factory.evidence.manifests")
        write_run_manifest = old.write_run_manifest  # permanent surface, never warns

    evidence_dir = tmp_path / "evidence"
    path = write_run_manifest(evidence_dir, _manifest_dict())

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        old_load_run_manifest = old.load_run_manifest
        old_list_run_manifests = old.list_run_manifests

    from substrate.evidence.read import list_run_manifests as new_list_run_manifests
    from substrate.evidence.read import load_run_manifest as new_load_run_manifest

    assert old_load_run_manifest(path) == new_load_run_manifest(path)
    assert old_list_run_manifests(evidence_dir, "T-001") == new_list_run_manifests(
        evidence_dir, "T-001"
    )
