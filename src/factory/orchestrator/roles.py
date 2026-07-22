from __future__ import annotations

from dataclasses import dataclass

from factory.orchestrator.types import AgentRole


@dataclass(frozen=True)
class Scope:
    allow: list[str]  # writable path globs
    bash: str  # "allow" | "deny"


# Finding 4 (final review): AgentRole.VALIDATION has a full entry below
# (skills/scope/prompt, including the scope-guard env-var contract) for
# completeness, but it is never invoked as a real agent today. run_validation
# (nodes.py) runs the sim gate directly with no agent call, so the
# Scope/prompt/skill row for this role is intentionally dead code right now: a
# deterministic gate is preferable to an LLM agent for this step. No
# functional change implied by this comment.
#
# AgentRole.SESSION_REVIEW (formerly SESSION_WRITER) is wired up for real:
# its skill is vendored under .pi/skills/session-report/SKILL.md, so
# skills.py's load_skill_block() and prompts.py's compose_prompt() can load it
# without raising FileNotFoundError.
#
# Fast-follow (final review, part 2): ROLE_SKILLS still names
# "sim-functional-tests" (VALIDATION), which is not vendored under
# .pi/skills/ -- only the skills the currently-live roles (CONTEXT_GATHERER,
# DEV, REVIEW, SESSION_REVIEW) need are vendored there. This was harmless
# while skill loading was soft (a bare unadvertised name was just inert), but
# skills.py's load_skill_block() now hard-loads every skill in ROLE_SKILLS[role]
# and raises FileNotFoundError if skills_dir/<name>/SKILL.md is missing, and
# prompts.py's compose_prompt() calls it unconditionally for every skill in the
# role's list. That means this entry is now a LATENT TRAP: if AgentRole.VALIDATION
# is ever wired up to a real compose_prompt() call in the future (i.e. the day
# it stops being dead code per the paragraph above), the very first call will
# crash with FileNotFoundError unless "sim-functional-tests" is vendored under
# .pi/skills/ first. Per this repo's established practice (see git history), do
# NOT speculatively author content for that skill now while the role is still
# dead -- but whoever wires up that role for real MUST vendor its skill(s)
# under .pi/skills/ as part of that change, or compose_prompt() for that role
# will fail immediately at runtime.
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
    AgentRole.SESSION_REVIEW: ["session-report"],
}

ROLE_SCOPE: dict[AgentRole, Scope] = {
    AgentRole.CONTEXT_GATHERER: Scope(allow=["context-manifests/**"], bash="deny"),
    AgentRole.DEV: Scope(allow=["src/**", "tests/**"], bash="allow"),
    AgentRole.VALIDATION: Scope(allow=[], bash="allow"),
    AgentRole.REVIEW: Scope(allow=[], bash="deny"),
    AgentRole.SESSION_REVIEW: Scope(allow=["sessions/**", "kb/**"], bash="deny"),
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
    AgentRole.SESSION_REVIEW: (
        "Analyze this task's full pipeline run (see the events below): what happened at "
        "each stage, how many attempts each took, what the final outcome was. If you find "
        "an issue genuinely worth remembering for future tasks -- not every run has one -- "
        "write a new kb/kb-NNNN-<slug>.md entry (check the existing entry list below and "
        "kb/ itself for the next free number; do not duplicate an issue already recorded "
        "there). Then append a short 'Suggestions' section to this session's summary in "
        "sessions/ noting any skill or prompt improvements that would have made this run "
        "more efficient -- these are suggestions for a human to read later, not changes to "
        "apply yourself."
    ),
}
