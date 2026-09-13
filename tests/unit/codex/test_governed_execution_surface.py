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


@pytest.fixture(scope="module")
def codex() -> str:
    return SKILL_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def claude() -> str:
    return COMMAND_PATH.read_text(encoding="utf-8")


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


def test_codex_and_claude_entrypoints_share_the_same_authority_contract(
    codex: str, claude: str
) -> None:
    for text in (codex, claude):
        assert "coherence execution legal-actions" in text
        assert "starts_automatically: false" in text
        assert "never" in text.lower()
        assert "consent" in text.lower()


def test_both_entrypoints_require_a_named_safe_run_and_task(codex: str, claude: str) -> None:
    for text in (codex, claude):
        normalized = _normalized(text)
        assert "[a-za-z0-9][a-za-z0-9._-]*" in normalized
        assert "run id" in normalized and "task id" in normalized
        assert "never infer" in normalized
        assert "separate argv values" in normalized


def test_both_entrypoints_query_legal_actions_before_dispatching(
    codex: str, claude: str
) -> None:
    for text in (codex, claude):
        normalized = _normalized(text)
        assert normalized.index("coherence execution legal-actions") < normalized.index(
            "coherence execution dispatch-task"
        )
        assert "only the backend-returned action" in normalized


def test_both_entrypoints_render_needs_input_without_answering_it(
    codex: str, claude: str
) -> None:
    for text in (codex, claude):
        normalized = _normalized(text)
        assert "needs_input" in normalized
        assert "request_sha256" in normalized
        assert "never answer the request" in normalized
        assert "coherence execution resolve-human" in normalized
        for decision in DECISIONS:
            assert decision in normalized


def test_both_entrypoints_stop_on_a_handoff_and_never_start_downstream_work(
    codex: str, claude: str
) -> None:
    for text in (codex, claude):
        normalized = _normalized(text)
        assert "starts_automatically: false" in normalized
        assert "stop" in normalized
        assert "never start" in normalized
        assert "downstream" in normalized
        assert "human-only" in normalized
        assert "adopt" in normalized


def test_both_entrypoints_refuse_a_host_local_lifecycle(codex: str, claude: str) -> None:
    for text in (codex, claude):
        normalized = _normalized(text)
        for refusal in (
            "never retry",  # no host-local retry loop
            "never invoke a worker process",  # no direct worker invocation
            "never interpret a gate",  # no host-side gate interpretation
            "never write a second journal",  # no second state path
            "never reproduce the driver loop",
        ):
            assert refusal in normalized, f"missing refusal: {refusal!r}"


def test_both_entrypoints_name_python_as_the_authority(codex: str, claude: str) -> None:
    for text in (codex, claude):
        normalized = _normalized(text)
        assert "python/coherence is authoritative" in normalized
        assert "a human must explicitly authorize retry, defer, block" in normalized


def test_every_declared_command_is_a_real_python_subcommand(
    codex: str, claude: str
) -> None:
    """The parity the text alone cannot prove: the docs name real commands."""
    real = _real_commands()
    for text in (codex, claude):
        declared = _declared_commands(text)
        assert declared, "no `coherence execution <command>` invocation is documented"
        assert declared <= real, f"undeclared commands: {sorted(declared - real)}"


def test_both_entrypoints_document_every_host_verb(codex: str, claude: str) -> None:
    for text in (codex, claude):
        declared = _declared_commands(text)
        assert {
            "legal-actions",
            "dispatch-task",
            "stream-progress",
            "resolve-human",
        } <= declared


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
