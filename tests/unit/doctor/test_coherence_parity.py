from __future__ import annotations

import ast
import importlib.util
import io
from contextlib import redirect_stdout
from pathlib import Path

import frontmatter
import pytest

from coherence.register.register import is_checksum_current, parse_requirement
from coherence.doctor import cli as coherence_cli

_REFERENCE_SPEC = importlib.util.spec_from_file_location(
    "legacy_doctor_reference", Path(__file__).with_name("legacy_doctor_reference.py")
)
assert _REFERENCE_SPEC is not None and _REFERENCE_SPEC.loader is not None
legacy_doctor_reference = importlib.util.module_from_spec(_REFERENCE_SPEC)
_REFERENCE_SPEC.loader.exec_module(legacy_doctor_reference)

pytestmark = pytest.mark.unit

ROOT = Path(__file__).parents[3]
DOCTOR_ROOT = ROOT / "src" / "coherence" / "doctor"


def _repo(root: Path) -> Path:
    specs = root / "docs" / "superpowers" / "specs"
    specs.mkdir(parents=True)
    (specs / "a.md").write_text("# A\n", encoding="utf-8")
    return root


def _capture(main, argv: list[str]) -> tuple[str, int]:
    output = io.StringIO()
    with redirect_stdout(output):
        code = main(argv)
    return output.getvalue(), code


def _run_pair(tmp_path: Path, argv: list[str]) -> tuple[tuple[str, int], tuple[str, int], Path, Path]:
    factory_root = _repo(tmp_path / "factory")
    coherence_root = _repo(tmp_path / "coherence")
    command = [*argv, "--project-root"]
    legacy_result = _capture(legacy_doctor_reference.main, [*command, str(factory_root)])
    coherence_result = _capture(coherence_cli.main, [*command, str(coherence_root)])
    return legacy_result, coherence_result, factory_root, coherence_root


def _assert_parity(
    legacy: tuple[str, int], coherence: tuple[str, int], legacy_root: Path, coherence_root: Path
) -> None:
    legacy_output = legacy[0].replace(str(legacy_root), "<project-root>")
    coherence_output = coherence[0].replace(str(coherence_root), "<project-root>")
    assert coherence[1] == legacy[1]
    assert coherence_output == legacy_output


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
    legacy_root = _repo(tmp_path / "factory")
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
    _capture(legacy_doctor_reference.main, [*mint_argv, "--project-root", str(legacy_root)])
    _capture(coherence_cli.main, [*mint_argv, "--project-root", str(coherence_root)])

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
    legacy = _capture(
        legacy_doctor_reference.main, [*promote_argv, "--project-root", str(legacy_root)]
    )
    coherence = _capture(
        coherence_cli.main, [*promote_argv, "--project-root", str(coherence_root)]
    )

    _assert_parity(legacy, coherence, legacy_root, coherence_root)
    legacy_path = legacy_root / "requirements" / "SR-001.md"
    coherence_path = coherence_root / "requirements" / "SR-001.md"
    assert coherence_path.read_bytes() == legacy_path.read_bytes()
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
    _capture(legacy_doctor_reference.main, [*mint_argv, "--project-root", str(factory_root)])
    _capture(coherence_cli.main, [*mint_argv, "--project-root", str(coherence_root)])

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
    legacy = _capture(legacy_doctor_reference.main, [*task_argv, "--project-root", str(factory_root)])
    coherence = _capture(
        coherence_cli.main, [*task_argv, "--project-root", str(coherence_root)]
    )

    _assert_parity(legacy, coherence, factory_root, coherence_root)
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
