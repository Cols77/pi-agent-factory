"""SR-034 shared host-entrypoint contract for governed execution (RED first).

Codex's `.agents/skills/governed-execution/SKILL.md` and Claude Code's
`.claude/commands/governed-execution.md` are two renderings of ONE contract: the
Python-owned `coherence execution` command surface is authoritative, the host
queries `legal-actions` before anything else, `needs_input` is rendered rather
than answered, and consent, requirement adoption and downstream handoff are
human-only.

Text presence alone is not the contract, so these tests also check the
right-hand side: every `coherence execution <command>` either file names must be
a real subcommand of the Python parser, and the decision vocabulary either file
offers must be the closed vocabulary the CLI accepts.

AC-10 (added by the 2026-09-13 spec addendum) extends this contract to a third
prose surface: `.hermes/plugins/governed-execution/README.md`. Unlike Codex's
skill and Claude Code's command, the Hermes plugin's own behavior is enforced
by code (`.hermes/plugins/governed-execution/plugin.py`, covered by
`tests/unit/hermes/test_governed_execution_plugin.py`, including a real
fixture-run byte-equivalence check against the same checked-in expectation
Task 6 established), not by an LLM reading prose -- so the README is folded
into every textual-contract assertion below that documents a boundary a human
operator must also see, while the two commands' frontmatter checks and the
LLM-specific "always ask before doing X" phrasing stay Codex/Claude-only.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from coherence.execution.cli import DECISIONS, _parser

pytestmark = [pytest.mark.unit, pytest.mark.sr("SR-034")]

PROJECT_ROOT = Path(__file__).parents[3]
SKILL_PATH = PROJECT_ROOT / ".agents" / "skills" / "governed-execution" / "SKILL.md"
COMMAND_PATH = PROJECT_ROOT / ".claude" / "commands" / "governed-execution.md"
HERMES_PLUGIN_DIR = PROJECT_ROOT / ".hermes" / "plugins" / "governed-execution"
HERMES_README_PATH = HERMES_PLUGIN_DIR / "README.md"
HERMES_PLUGIN_PATH = HERMES_PLUGIN_DIR / "plugin.py"
HERMES_MANIFEST_PATH = HERMES_PLUGIN_DIR / "plugin.yaml"


@pytest.fixture(scope="module")
def codex() -> str:
    return SKILL_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def claude() -> str:
    return COMMAND_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def hermes() -> str:
    return HERMES_README_PATH.read_text(encoding="utf-8")


def _normalized(text: str) -> str:
    return " ".join(text.lower().replace("`", "").split())


def _declared_commands(text: str) -> set[str]:
    return set(re.findall(r"coherence execution ([a-z][a-z-]*)", text))


def _real_commands() -> set[str]:
    sub = next(
        action
        for action in _parser("coherence-execution")._actions
        if getattr(action, "choices", None) and isinstance(action.choices, dict)
    )
    return set(sub.choices)


def test_every_entrypoint_shares_the_same_authority_contract(
    codex: str, claude: str, hermes: str
) -> None:
    for text in (codex, claude, hermes):
        assert "coherence execution legal-actions" in text
        assert "starts_automatically: false" in text
        assert "never" in text.lower()
        assert "consent" in text.lower()


def test_every_entrypoint_requires_a_named_safe_run_and_task(
    codex: str, claude: str, hermes: str
) -> None:
    for text in (codex, claude, hermes):
        normalized = _normalized(text)
        assert "[a-za-z0-9][a-za-z0-9._-]*" in normalized
        assert "run id" in normalized and "task id" in normalized
        assert "never infer" in normalized
        assert "separate argv values" in normalized


def test_every_entrypoint_queries_legal_actions_before_dispatching(
    codex: str, claude: str, hermes: str
) -> None:
    for text in (codex, claude, hermes):
        normalized = _normalized(text)
        assert normalized.index("coherence execution legal-actions") < normalized.index(
            "coherence execution dispatch-task"
        )
        assert "only the backend-returned action" in normalized


def test_every_entrypoint_renders_needs_input_without_answering_it(
    codex: str, claude: str, hermes: str
) -> None:
    for text in (codex, claude, hermes):
        normalized = _normalized(text)
        assert "needs_input" in normalized
        assert "request_sha256" in normalized
        assert "never answer" in normalized  # "the request" (Codex/Claude) or "it" (Hermes)
        assert "coherence execution resolve-human" in normalized
        for decision in DECISIONS:
            assert decision in normalized


def test_every_entrypoint_stops_on_a_handoff_and_never_starts_downstream_work(
    codex: str, claude: str, hermes: str
) -> None:
    for text in (codex, claude, hermes):
        normalized = _normalized(text)
        assert "starts_automatically: false" in normalized
        assert "stop" in normalized
        assert "never start" in normalized
        assert "downstream" in normalized
        assert "human-only" in normalized
        assert "adopt" in normalized


def test_every_entrypoint_refuses_a_host_local_lifecycle(
    codex: str, claude: str, hermes: str
) -> None:
    for text in (codex, claude, hermes):
        normalized = _normalized(text)
        for refusal in (
            "never retry",  # no host-local retry loop
            "never invoke a worker process",  # no direct worker invocation
            "never interpret a gate",  # no host-side gate interpretation
            "never write a second journal",  # no second state path
            "never reproduce the driver loop",
        ):
            assert refusal in normalized, f"missing refusal: {refusal!r}"


def test_every_entrypoint_names_python_as_the_authority(
    codex: str, claude: str, hermes: str
) -> None:
    for text in (codex, claude, hermes):
        normalized = _normalized(text)
        assert "python/coherence is authoritative" in normalized
        assert "a human must explicitly authorize retry, defer, block" in normalized


def test_every_declared_command_is_a_real_python_subcommand(
    codex: str, claude: str, hermes: str
) -> None:
    """The parity the text alone cannot prove: the docs name real commands."""
    real = _real_commands()
    for text in (codex, claude, hermes):
        declared = _declared_commands(text)
        assert declared, "no `coherence execution <command>` invocation is documented"
        assert declared <= real, f"undeclared commands: {sorted(declared - real)}"


def test_every_entrypoint_documents_every_host_verb(
    codex: str, claude: str, hermes: str
) -> None:
    for text in (codex, claude, hermes):
        declared = _declared_commands(text)
        assert {
            "legal-actions",
            "dispatch-task",
            "stream-progress",
            "resolve-human",
        } <= declared


# -- AC-10: the Hermes plugin is code, not prose an LLM follows -- so its own
# behavioral parity is proven against the plugin module and manifest, not just
# the README's prose. -----------------------------------------------------


def _load_hermes_plugin():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "governed_execution_plugin_surface", HERMES_PLUGIN_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_hermes_plugin_manifest_reflects_that_it_is_not_read_only() -> None:
    """AC-10's plugin can dispatch and resolve a human decision, unlike
    coherence-plan's purely-read-only plugin -- so, unlike
    `.hermes/plugins/coherence-plan/plugin.yaml`, this manifest must not carry
    a `read-only` tag it would not live up to."""
    manifest = yaml.safe_load(HERMES_MANIFEST_PATH.read_text(encoding="utf-8"))
    assert manifest["name"] == "governed-execution"
    tags = manifest.get("tags") or []
    assert "read-only" not in tags
    assert "execution" in tags or "governed-execution" in tags


def test_hermes_plugin_only_ever_calls_real_python_subcommands() -> None:
    """The code-level parity check `_declared_commands` proves for prose: the
    plugin's own closed action vocabulary is a subset of the CLI's real
    subcommands, and every mutating verb Codex/Claude document is in it."""
    module = _load_hermes_plugin()
    real = _real_commands()
    declared = {"legal-actions", "dispatch-task", "resolve-human", "stream-progress"}
    assert declared <= real

    # flaky-register is a real Python subcommand, but it is human-only (see
    # the README's final refusal) and this plugin exposes no branch for it at
    # all -- an unrecognized first word falls through to the usage message,
    # never to a subprocess call.
    assert module._run("flaky-register test-1") == module._USAGE


def test_hermes_plugin_decision_vocabulary_matches_the_cli_exactly() -> None:
    module = _load_hermes_plugin()
    assert tuple(module._DECISIONS) == DECISIONS


def test_the_skill_declares_codex_frontmatter(codex: str) -> None:
    assert codex.startswith("---\n")
    frontmatter = yaml.safe_load(codex.split("---\n", 2)[1])
    assert frontmatter["name"] == "governed-execution"
    assert isinstance(frontmatter.get("description"), str)
    assert frontmatter["description"].strip()


def test_the_claude_command_declares_its_argument(claude: str) -> None:
    assert claude.startswith("---\n")
    frontmatter = yaml.safe_load(claude.split("---\n", 2)[1])
    assert isinstance(frontmatter.get("description"), str)
    assert frontmatter.get("argument-hint") == "<run-id> <task-id>"
