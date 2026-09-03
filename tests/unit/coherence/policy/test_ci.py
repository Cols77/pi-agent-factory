import sys
from pathlib import Path

import pytest

from coherence.policy.ci import NoBlockingObligationError, required_ci_commands
from substrate.policy.obligation import Obligation

pytestmark = pytest.mark.unit


def _seed(root: Path) -> None:
    (root / ".factory").mkdir()
    (root / ".factory" / "factory.yaml").write_text(
        "gates:\n"
        "  unit:\n"
        "    - { cmd: \"{python} -m pytest -m unit -q\" }\n"
        "  integration:\n"
        "    - { cmd: \"{python} -m pytest tests/integration/ -q -m integration\" }\n"
        "  full:\n"
        "    - { cmd: \"{python} -m ruff check .\" }\n"
        "    - { cmd: \"{python} -m pyright\" }\n"
        "    - { cmd: \"{python} -m pytest -m unit -q\" }\n"
        "    - { cmd: \"{python} scripts/gates/ext.py\" }\n"
        "    - { cmd: \"{python} scripts/gates/watch_ext.py\" }\n",
        encoding="utf-8",
    )


@pytest.mark.sr("SR-009")
@pytest.mark.sr("SR-048")
def test_includes_every_declared_gate_command_in_order_with_python_substituted(tmp_path):
    _seed(tmp_path)

    commands = required_ci_commands(tmp_path)
    configured = commands[:-2]

    assert len(configured) == 7
    assert not any("{python}" in command for command in commands)
    assert all(sys.executable in command for command in configured)
    assert configured == [
        f"{sys.executable} -m pytest -m unit -q",
        f"{sys.executable} -m pytest tests/integration/ -q -m integration",
        f"{sys.executable} -m ruff check .",
        f"{sys.executable} -m pyright",
        f"{sys.executable} -m pytest -m unit -q",
        f"{sys.executable} scripts/gates/ext.py",
        f"{sys.executable} scripts/gates/watch_ext.py",
    ]


@pytest.mark.sr("SR-048")
def test_structural_checks_are_always_appended(tmp_path):
    _seed(tmp_path)

    assert required_ci_commands(tmp_path)[-2:] == [
        "coherence trace check",
        "coherence register check",
    ]


@pytest.mark.sr("SR-048")
def test_no_declared_gates_raises_no_blocking_obligation_error(tmp_path):
    (tmp_path / ".factory").mkdir()
    (tmp_path / ".factory" / "factory.yaml").write_text("harnesses: {}\n", encoding="utf-8")

    with pytest.raises(NoBlockingObligationError):
        required_ci_commands(tmp_path)


@pytest.mark.sr("SR-048")
def test_commandless_blocking_obligation_rejects_partial_results(tmp_path, monkeypatch):
    from coherence.policy import ci

    monkeypatch.setattr(
        ci,
        "compile_obligations",
        lambda _root, _scope_ref: [
            Obligation(
                id="ob:ci_verification:project:unit",
                scope_ref="project",
                kind="ci_verification",
                requiredness="blocking",
                reason="unit",
                source_policy="prototype",
                state="open",
                resolve_cmd=("python -m pytest -m unit -q",),
            ),
            Obligation(
                id="ob:ci_verification:project:missing",
                scope_ref="project",
                kind="ci_verification",
                requiredness="blocking",
                reason="missing command",
                source_policy="prototype",
                state="open",
                resolve_cmd=None,
            ),
        ],
    )

    with pytest.raises(NoBlockingObligationError):
        required_ci_commands(tmp_path)
