from __future__ import annotations

import ast
import importlib.util
import io
import json
import shutil
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from factory.requirements import cli as factory_cli
from coherence.register import cli as coherence_cli

_REFERENCE_SPEC = importlib.util.spec_from_file_location(
    "legacy_cli_reference", Path(__file__).with_name("legacy_cli_reference.py")
)
assert _REFERENCE_SPEC is not None and _REFERENCE_SPEC.loader is not None
legacy_cli_reference = importlib.util.module_from_spec(_REFERENCE_SPEC)
_REFERENCE_SPEC.loader.exec_module(legacy_cli_reference)

pytestmark = pytest.mark.unit

ROOT = Path(__file__).parents[3]
REGISTER_ROOT = ROOT / "src" / "coherence" / "register"
STATEMENT = legacy_cli_reference.STATEMENT


def _write_requirement(root: Path, state: str) -> Path:
    requirements = root / "requirements"
    requirements.mkdir(parents=True, exist_ok=True)
    binding = "" if state == "proposed" else """binding:
  experiment: patrol
  metric: success_rate
  assert: \">= 0.90\"
  harness: sim-testbench
  trials: 1
"""
    deferred = "trace_deferred: waiting for the next test window\n" if state == "deferred" else ""
    document = (
        "---\n"
        "id: SR-001\n"
        f"title: {state} requirement\n"
        f"statement: {STATEMENT}\n"
        "domain: behavioral\n"
        "upstream: []\n"
        f"{binding}"
        f"{deferred}"
        "---\n\nRequirement body.\n"
    )
    path = requirements / "SR-001.md"
    path.write_text(document, encoding="utf-8")
    if state != "proposed":
        legacy_cli_reference.stamp_checksum(path)
    if state == "stale":
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                "warn the swimmer", "warn the swimmer immediately"
            ),
            encoding="utf-8",
        )
    if state in {"measured-passing", "measured-failing"}:
        evidence = root / "evidence" / "runs"
        evidence.mkdir(parents=True, exist_ok=True)
        passed = state == "measured-passing"
        manifest = {
            "schema_version": 2,
            "run_id": "run-1",
            "task_id": "T-001",
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
            "validation": [{"requirements": [{"id": "SR-001", "passed": passed}]}],
            "reviews": [],
            "decisions": [],
            "publication": {"state": "local", "errors": []},
        }
        (evidence / "run-1.json").write_text(json.dumps(manifest), encoding="utf-8")
    return requirements


def _capture(module, argv: list[str]) -> tuple[str, int]:
    output = io.StringIO()
    with redirect_stdout(output):
        code = module.main(argv)
    return output.getvalue(), code


COMMANDS = (
    ("new", lambda root, requirements: ["new", "A new requirement", "--requirements-dir", str(requirements)]),
    ("index", lambda root, requirements: ["index", "--requirements-dir", str(requirements)]),
    ("status", lambda root, requirements: ["status", "--requirements-dir", str(requirements)]),
    ("show", lambda root, requirements: ["show", "SR-001", "--requirements-dir", str(requirements)]),
    (
        "bind",
        lambda root, requirements: [
            "bind",
            "SR-001",
            "--requirements-dir",
            str(requirements),
            "--experiment",
            "patrol-v2",
            "--metric",
            "success_rate",
            "--assert",
            ">= 0.95",
            "--harness",
            "sim-testbench",
        ],
    ),
    (
        "defer",
        lambda root, requirements: [
            "defer",
            "SR-001",
            "--requirements-dir",
            str(requirements),
            "--reason",
            "blocked by the next test window",
        ],
    ),
    ("check", lambda root, requirements: ["check", "--project-root", str(root)]),
    ("next", lambda root, requirements: ["next", "--project-root", str(root)]),
)


@pytest.mark.parametrize(
    "state", ["proposed", "bound-current", "stale", "deferred", "measured-passing", "measured-failing"]
)
@pytest.mark.parametrize("command,argv_for", COMMANDS, ids=lambda value: value[0] if isinstance(value, tuple) else value)
def test_coherence_register_matches_factory_register_for_every_command(
    tmp_path: Path, state: str, command: str, argv_for
):
    root = tmp_path / "project"
    requirements = _write_requirement(root, state)
    legacy = _capture(legacy_cli_reference, argv_for(root, requirements))

    shutil.rmtree(root)
    requirements = _write_requirement(root, state)
    canonical = _capture(coherence_cli, argv_for(root, requirements))

    assert canonical == legacy, f"{command} diverged for {state}"


def test_factory_requirements_cli_forwards_to_canonical_cli():
    assert factory_cli is coherence_cli
    assert factory_cli.main is coherence_cli.main


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_coherence_register_owns_the_register_and_uses_substrate_dependencies():
    modules = sorted(REGISTER_ROOT.glob("*.py"))
    assert {path.name for path in modules} >= {
        "register.py",
        "closure.py",
        "write.py",
        "cli.py",
        "__main__.py",
    }
    imports = set().union(*(_imports(path) for path in modules))
    assert "substrate.ledger.tasks" in imports
    assert "substrate.evidence.read" in imports
    assert "substrate.freshness.model" in imports
    assert not any(name.startswith("factory.") for name in imports)


def test_canonical_check_preserves_report_punctuation(tmp_path: Path):
    _write_requirement(tmp_path, "measured-failing")

    from coherence.register.cli import cmd_check

    report, code = cmd_check(tmp_path)

    assert code == 0
    expected = f"measured failing {chr(0x2014)} decided and measured; the system does not meet these:"
    assert expected in report
