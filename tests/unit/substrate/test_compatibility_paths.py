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


def _write_task(tasks_dir, name, status="todo"):
    tasks_dir.mkdir(parents=True, exist_ok=True)
    (tasks_dir / name).write_text(
        f"---\nid: {name[:-3]}\ntitle: t\nstatus: {status}\ndod:\n  - x\n---\nbody\n",
        encoding="utf-8",
    )


def test_factory_orchestrator_ledger_warns_once_and_matches_substrate(tmp_path):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", DeprecationWarning)
        old = _import_fresh("factory.orchestrator.ledger")

    assert len(caught) == 1
    assert caught[0].category is DeprecationWarning
    assert str(caught[0].message) == (
        "factory.orchestrator.ledger is deprecated; import substrate.ledger.tasks"
    )

    new = importlib.import_module("substrate.ledger.tasks")
    assert old.Task is new.Task

    tasks_dir = tmp_path / "tasks"
    _write_task(tasks_dir, "T-001-a.md")
    old_tasks = old.load_tasks(tasks_dir)
    new_tasks = new.load_tasks(tasks_dir)
    assert old_tasks == new_tasks
    assert old.get_task(old_tasks, "T-001") == new.get_task(new_tasks, "T-001")
    assert old.format_task_board(old_tasks) == new.format_task_board(new_tasks)


def test_factory_orchestrator_plan_to_tasks_warns_once_and_matches_substrate(tmp_path):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", DeprecationWarning)
        old = _import_fresh("factory.orchestrator.plan_to_tasks")

    assert len(caught) == 1
    assert caught[0].category is DeprecationWarning
    assert str(caught[0].message) == (
        "factory.orchestrator.plan_to_tasks is deprecated; import substrate.ledger.plans"
    )

    new = importlib.import_module("substrate.ledger.plans")
    assert old.NoTasksFoundError is new.NoTasksFoundError

    text = "# no sections here\n"
    assert old.parse_plan_tasks(text) == new.parse_plan_tasks(text) == []

    plan_dir = tmp_path / "docs" / "superpowers" / "plans"
    plan_dir.mkdir(parents=True)
    plan_path = plan_dir / "p.md"
    plan_path.write_text(
        "### Task 1: A\n\n**Files:**\n- Create: `a.py`\n\n**Interfaces:**\n- Produces: `f()`.\n",
        encoding="utf-8",
    )
    old_created = old.run(plan_path, tmp_path)
    assert old_created == ["T-001"]
    assert new.run(plan_path, tmp_path) == []  # already parsed -- idempotent


def test_factory_config_load_config_and_require_gates_do_not_warn(tmp_path):
    # factory.config is the composition adapter, not a moved module -- its
    # public behaviour is unchanged, so importing/calling it must stay silent.
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", DeprecationWarning)
        cfg_module = _import_fresh("factory.config")

    assert caught == []

    (tmp_path / ".factory").mkdir()
    (tmp_path / ".factory" / "factory.yaml").write_text(
        'gates:\n  unit:\n    - { cmd: "pytest -q" }\n', encoding="utf-8"
    )

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", DeprecationWarning)
        cfg = cfg_module.load_config(tmp_path)
        cfg_module.require_gates(cfg, tmp_path)

    assert caught == []

    from substrate.config import GateStep as SubstrateGateStep

    assert cfg.gates == {"unit": [SubstrateGateStep(cmd="pytest -q")]}


def test_factory_orchestrator_skills_warns_once_and_matches_substrate(tmp_path):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", DeprecationWarning)
        old = _import_fresh("factory.orchestrator.skills")

    assert len(caught) == 1
    assert caught[0].category is DeprecationWarning
    assert str(caught[0].message) == (
        "factory.orchestrator.skills is deprecated; import substrate.agents.skills "
        "and substrate.paths"
    )

    from substrate.agents.skills import load_skill_block as new_load_skill_block
    from substrate.paths import factory_skills_dir as new_factory_skills_dir

    assert old.load_skill_block is new_load_skill_block
    assert old.factory_skills_dir is new_factory_skills_dir

    (tmp_path / "s").mkdir()
    (tmp_path / "s" / "SKILL.md").write_text("---\nname: s\n---\n\nbody\n", encoding="utf-8")
    assert old.load_skill_block(tmp_path, "s") == new_load_skill_block(tmp_path, "s")


def test_factory_orchestrator_pi_backend_warns_once_and_delegates_to_substrate(tmp_path):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", DeprecationWarning)
        old = _import_fresh("factory.orchestrator.pi_backend")

    assert len(caught) == 1
    assert caught[0].category is DeprecationWarning
    assert str(caught[0].message) == (
        "factory.orchestrator.pi_backend is deprecated; import substrate.agents.backend "
        "and compose scope_for from factory.orchestrator.roles.ROLE_SCOPE"
    )

    from substrate.agents.model import AgentResult as SubstrateAgentResult
    from substrate.agents.model import InterruptionReason as SubstrateInterruptionReason

    assert old.AgentResult is SubstrateAgentResult
    assert old.InterruptionReason is SubstrateInterruptionReason
    # Pure functions are re-exported unchanged (not copies), so behavior is
    # byte-identical regardless of which module a caller imports it from.
    from substrate.agents.backend import parse_pi_json as new_parse_pi_json

    assert old.parse_pi_json is new_parse_pi_json


def test_factory_orchestrator_types_agent_result_and_interruption_reason_warn(tmp_path):
    # AgentResult/InterruptionReason moved to substrate.agents.model; the four
    # domain/pipeline types below (AgentRole, NodeOutcome, NodeEvent, TaskResult)
    # did NOT move and must stay completely silent -- this module is the
    # "mixed" shim case (permanent surface + two deprecated re-exports), not a
    # whole-module warn like factory.paths.
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", DeprecationWarning)
        types_module = _import_fresh("factory.orchestrator.types")
        types_module.AgentRole.DEV
        types_module.NodeOutcome.PASS
        types_module.NodeEvent(node="dev", result="pass")
        types_module.TaskResult(
            task_id="T-1", title="t", outcome="completed", iterations=1,
            events=[], dod_met=True,
        )

    assert caught == []  # the permanent surface never warns

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", DeprecationWarning)
        agent_result_cls = types_module.AgentResult
        interruption_cls = types_module.InterruptionReason

    deprecation = [item for item in caught if item.category is DeprecationWarning]
    assert len(deprecation) == 2
    assert str(deprecation[0].message) == (
        "factory.orchestrator.types.AgentResult is deprecated; import substrate.agents.model.AgentResult"
    )
    assert str(deprecation[1].message) == (
        "factory.orchestrator.types.InterruptionReason is deprecated; "
        "import substrate.agents.model.InterruptionReason"
    )

    from substrate.agents.model import AgentResult as SubstrateAgentResult
    from substrate.agents.model import InterruptionReason as SubstrateInterruptionReason

    assert agent_result_cls is SubstrateAgentResult
    assert interruption_cls is SubstrateInterruptionReason


def test_factory_evidence_manifests_write_stays_silent_read_functions_warn(tmp_path):
    # write_run_manifest is retained permanently (not deprecated); only the two
    # read functions moved to substrate.evidence.read -- the same "mixed
    # module" shape as factory.orchestrator.types above.
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", DeprecationWarning)
        manifests_module = _import_fresh("factory.evidence.manifests")
        write_run_manifest = manifests_module.write_run_manifest

    assert caught == []
    assert callable(write_run_manifest)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", DeprecationWarning)
        load_run_manifest = manifests_module.load_run_manifest
        list_run_manifests = manifests_module.list_run_manifests
        schema_version = manifests_module.MANIFEST_SCHEMA_VERSION

    deprecation = [item for item in caught if item.category is DeprecationWarning]
    assert len(deprecation) == 3

    from substrate.evidence.model import MANIFEST_SCHEMA_VERSION as new_schema_version
    from substrate.evidence.read import list_run_manifests as new_list_run_manifests
    from substrate.evidence.read import load_run_manifest as new_load_run_manifest

    assert load_run_manifest is new_load_run_manifest
    assert list_run_manifests is new_list_run_manifests
    assert schema_version == new_schema_version
