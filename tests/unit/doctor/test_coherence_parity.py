from __future__ import annotations

import ast
import importlib
import io
from contextlib import redirect_stdout
from pathlib import Path

import frontmatter
import pytest

from coherence.register.register import is_checksum_current, parse_requirement

pytestmark = pytest.mark.unit

ROOT = Path(__file__).parents[3]
DOCTOR_ROOT = ROOT / "src" / "coherence" / "doctor"


def _repo(root: Path) -> Path:
    specs = root / "docs" / "superpowers" / "specs"
    specs.mkdir(parents=True)
    (specs / "a.md").write_text("# A\n", encoding="utf-8")
    return root


def _capture(module_name: str, argv: list[str]) -> tuple[str, int]:
    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        if module_name.startswith("coherence.doctor"):
            pytest.fail(f"canonical doctor is not available: {exc}")
        raise
    output = io.StringIO()
    with redirect_stdout(output):
        code = module.main(argv)
    return output.getvalue(), code


def _run_pair(tmp_path: Path, argv: list[str]) -> tuple[tuple[str, int], tuple[str, int], Path, Path]:
    factory_root = _repo(tmp_path / "factory")
    coherence_root = _repo(tmp_path / "coherence")
    command = [*argv, "--project-root"]
    factory_result = _capture("factory.doctor.cli", [*command, str(factory_root)])
    coherence_result = _capture("coherence.doctor.cli", [*command, str(coherence_root)])
    return factory_result, coherence_result, factory_root, coherence_root


def _assert_parity(
    factory: tuple[str, int], coherence: tuple[str, int], factory_root: Path, coherence_root: Path
) -> None:
    factory_output = factory[0].replace(str(factory_root), "<project-root>")
    coherence_output = coherence[0].replace(str(coherence_root), "<project-root>")
    assert coherence[1] == factory[1]
    assert coherence_output == factory_output


def test_context_stdout_and_exit_code_match_factory(tmp_path: Path):
    factory, coherence, factory_root, coherence_root = _run_pair(tmp_path, ["context", "--json"])

    _assert_parity(factory, coherence, factory_root, coherence_root)


def test_mint_preserves_proposed_requirement_content_and_effects(tmp_path: Path):
    factory, coherence, factory_root, coherence_root = _run_pair(
        tmp_path,
        [
            "mint",
            "--source",
            "docs/superpowers/specs/a.md",
            "--title",
            "Zone clear resumes patrol",
            "--statement",
            "When the zone clears, the system shall resume patrol.",
        ],
    )

    _assert_parity(factory, coherence, factory_root, coherence_root)
    factory_path = factory_root / "requirements" / "SR-001.md"
    coherence_path = coherence_root / "requirements" / "SR-001.md"
    assert coherence_path.read_bytes() == factory_path.read_bytes()
    proposed = parse_requirement(coherence_path)
    assert proposed.binding is None
    assert proposed.source == "docs/superpowers/specs/a.md"


def test_promote_preserves_stdout_exit_and_explicit_binding_writer_effects(tmp_path: Path):
    factory_root = _repo(tmp_path / "factory")
    coherence_root = _repo(tmp_path / "coherence")
    mint_argv = [
        "mint",
        "--source",
        "docs/superpowers/specs/a.md",
        "--title",
        "t",
        "--statement",
        "s",
    ]
    _capture("factory.doctor.cli", [*mint_argv, "--project-root", str(factory_root)])
    _capture("coherence.doctor.cli", [*mint_argv, "--project-root", str(coherence_root)])

    promote_argv = [
        "promote",
        "SR-001",
        "--harness",
        "sim-testbench",
        "--experiment",
        "patrol",
        "--metric",
        "success_rate",
        "--assert",
        ">= 0.90",
        "--trials",
        "20",
        "--window-json",
        '{"after_event": "zone_clear", "within_s": 5}',
    ]
    factory = _capture("factory.doctor.cli", [*promote_argv, "--project-root", str(factory_root)])
    coherence = _capture(
        "coherence.doctor.cli", [*promote_argv, "--project-root", str(coherence_root)]
    )

    _assert_parity(factory, coherence, factory_root, coherence_root)
    factory_path = factory_root / "requirements" / "SR-001.md"
    coherence_path = coherence_root / "requirements" / "SR-001.md"
    assert coherence_path.read_bytes() == factory_path.read_bytes()
    promoted = parse_requirement(coherence_path)
    assert promoted.binding is not None
    assert promoted.binding.trials == 20
    assert promoted.binding.window == {"after_event": "zone_clear", "within_s": 5}
    assert is_checksum_current(promoted)


def test_task_preserves_stdout_exit_and_explicit_task_writer_effects(tmp_path: Path):
    factory_root = _repo(tmp_path / "factory")
    coherence_root = _repo(tmp_path / "coherence")
    mint_argv = [
        "mint",
        "--source",
        "docs/superpowers/specs/a.md",
        "--title",
        "t",
        "--statement",
        "s",
    ]
    _capture("factory.doctor.cli", [*mint_argv, "--project-root", str(factory_root)])
    _capture("coherence.doctor.cli", [*mint_argv, "--project-root", str(coherence_root)])

    task_argv = [
        "task",
        "--satisfies",
        "SR-001",
        "--title",
        "Implement the scorer",
        "--dod",
        "SCORERS exposes success_rate",
        "--dod",
        "unit test covers pass and fail trials",
        "--body",
        "Add the scorer to src/validation/scorers.py.",
    ]
    factory = _capture("factory.doctor.cli", [*task_argv, "--project-root", str(factory_root)])
    coherence = _capture(
        "coherence.doctor.cli", [*task_argv, "--project-root", str(coherence_root)]
    )

    _assert_parity(factory, coherence, factory_root, coherence_root)
    factory_path = factory_root / "tasks" / "T-001.md"
    coherence_path = coherence_root / "tasks" / "T-001.md"
    assert coherence_path.read_bytes() == factory_path.read_bytes()
    task = frontmatter.load(str(coherence_path))
    assert task["satisfies"] == ["SR-001"]
    assert task["dod"] == ["SCORERS exposes success_rate", "unit test covers pass and fail trials"]


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_coherence_doctor_is_canonical_and_does_not_own_factory_runtime():
    assert {path.name for path in DOCTOR_ROOT.glob("*.py")} >= {
        "__init__.py",
        "__main__.py",
        "context.py",
        "write.py",
        "cli.py",
    }
    imports = set().union(*(_imports(path) for path in DOCTOR_ROOT.glob("*.py")))

    assert "coherence.register.register" in imports
    assert "coherence.register.write" in imports
    assert not any(name.startswith("factory.") for name in imports)
    assert not any(term in name for name in imports for term in ("bootstrap", "recovery"))


def test_doctor_refusals_match_without_creating_writer_outputs(tmp_path: Path):
    factory, coherence, factory_root, coherence_root = _run_pair(
        tmp_path,
        [
            "mint",
            "--source",
            "docs/superpowers/specs/missing.md",
            "--title",
            "t",
            "--statement",
            "s",
        ],
    )

    _assert_parity(factory, coherence, factory_root, coherence_root)
    assert factory[1] == 1
    assert not (factory_root / "requirements").exists()
    assert not (coherence_root / "requirements").exists()
