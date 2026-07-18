from __future__ import annotations

from dataclasses import dataclass

from factory.orchestrator.types import AgentRole


@dataclass(frozen=True)
class Scope:
    allow: list[str]  # writable path globs
    bash: str  # "allow" | "deny"


# Finding 4 (final review): AgentRole.VALIDATION and AgentRole.SESSION_WRITER have
# full entries below (skills/scope/prompt, including the scope-guard env-var
# contract) for completeness, but neither is ever invoked as a real agent today.
# run_validation (nodes.py) runs the sim gate directly with no agent call, and
# session writing (session.build_record/write_session) is pure Python. So the
# Scope/prompt/skill rows for those two roles are intentionally dead code right
# now: a deterministic gate/pure-Python step is preferable to an LLM agent for
# these two steps. No functional change implied by this comment.
ROLE_SKILLS: dict[AgentRole, list[str]] = {
    AgentRole.CONTEXT_GATHERER: ["verification-before-completion", "context-completeness-audit"],
    AgentRole.DEV: [
        "test-driven-development",
        "systematic-debugging",
        "receiving-code-review",
        "kb-lookup",
    ],
    AgentRole.VALIDATION: ["verification-before-completion", "sim-functional-tests"],
    AgentRole.REVIEW: ["requesting-code-review", "verification-before-completion", "coding-principles"],
    AgentRole.SESSION_WRITER: ["session-report"],
}

ROLE_SCOPE: dict[AgentRole, Scope] = {
    AgentRole.CONTEXT_GATHERER: Scope(allow=["context-manifests/**"], bash="deny"),
    AgentRole.DEV: Scope(allow=["src/**", "tests/**"], bash="allow"),
    AgentRole.VALIDATION: Scope(allow=[], bash="allow"),
    AgentRole.REVIEW: Scope(allow=[], bash="deny"),
    AgentRole.SESSION_WRITER: Scope(allow=["sessions/**"], bash="deny"),
}

ROLE_PROMPTS: dict[AgentRole, str] = {
    AgentRole.CONTEXT_GATHERER: (
        "You verify that spec, plan, prior session, and this task are coherent and "
        "that context is complete. Emit ONLY a context manifest as a fenced ```json block "
        "matching the context_manifest schema. If you cannot prove coherence, set "
        "coherence.proven=false and populate reject."
    ),
    AgentRole.DEV: (
        "Implement the task using strict TDD (write the failing test first). "
        "Consult the provided knowledge-base entries. Do not stop until unit tests pass."
    ),
    AgentRole.VALIDATION: "Run the functional/sim suite. Do not modify source.",
    AgentRole.REVIEW: (
        "Review the change for YAGNI/DRY and against the Definition of Done. Emit ONLY a "
        "fenced ```json block: {\"dod_met\": bool, \"principles\": [..], \"findings\": [..]}."
    ),
    AgentRole.SESSION_WRITER: "Summarize what happened this session for reliable resume.",
}
