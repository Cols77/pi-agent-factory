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
# AgentRole.SESSION_REVIEW: its skill is now vendored under .pi/skills/session-report/SKILL.md,
# and its scope and prompt are defined below. It IS invoked: runner.py's
# run_next calls backend.run(AgentRole.SESSION_REVIEW, ...) at the end of
# every run, after the session record is written.
#
# Fast-follow (final review, part 2): ROLE_SKILLS still names
# "sim-functional-tests" (VALIDATION), which is not vendored under
# .pi/skills/ -- only the skills the currently-live roles (CONTEXT_GATHERER,
# DEV, REVIEW) need are vendored there. This was harmless while skill loading was
# soft (a bare unadvertised name was just inert), but skills.py's load_skill_block()
# now hard-loads every skill in ROLE_SKILLS[role] and raises FileNotFoundError if
# skills_dir/<name>/SKILL.md is missing, and prompts.py's compose_prompt() calls it
# unconditionally for every skill in the role's list. That means this entry is a
# LATENT TRAP for VALIDATION: if that role is ever wired up to a real compose_prompt()
# call in the future, the very first call will crash with FileNotFoundError unless
# "sim-functional-tests" is vendored under .pi/skills/ first. Per this repo's
# established practice (see git history), do NOT speculatively author content for
# that skill now while the role is still dead -- but whoever wires up that role for
# real MUST vendor its skill(s) under .pi/skills/ as part of that change.
ROLE_SKILLS: dict[AgentRole, list[str]] = {
    AgentRole.CONTEXT_GATHERER: ["verification-before-completion", "context-completeness-audit"],
    AgentRole.DEV: [
        "test-driven-development",
        "systematic-debugging",
        "receiving-code-review",
        "kb-lookup",
        # Every function Dev writes or touches must be documented (purpose,
        # args, returns, failure modes) and every module must declare its
        # traceability (SRs + modifying tasks) -- enforced deterministically
        # by the project's full gate (scripts/gates/check_documentation.py).
        "code-documentation",
    ],
    AgentRole.VALIDATION: ["verification-before-completion", "sim-functional-tests"],
    AgentRole.REVIEW: ["requesting-code-review", "verification-before-completion", "coding-principles"],
    AgentRole.SESSION_REVIEW: ["session-report"],
    AgentRole.SYNTHESIS: ["polish"],
}

ROLE_SCOPE: dict[AgentRole, Scope] = {
    AgentRole.CONTEXT_GATHERER: Scope(allow=["context-manifests/**"], bash="deny"),
    # Traceability matrices are implementation artifacts and some tasks explicitly
    # modify them. Requirements remain human-owned and writable only through the
    # registered trace tools, not through Dev's direct file tools.
    AgentRole.DEV: Scope(
        allow=["src/**", "tests/**", "docs/traceability/**"], bash="allow"
    ),
    AgentRole.VALIDATION: Scope(allow=[], bash="allow"),
    AgentRole.REVIEW: Scope(allow=[], bash="deny"),
    AgentRole.SESSION_REVIEW: Scope(allow=["sessions/**", "kb/**"], bash="deny"),
    # Synthesis only converts the human's feedback text into findings JSON. It
    # writes nothing and runs nothing -- the orchestrator routes the findings.
    AgentRole.SYNTHESIS: Scope(allow=[], bash="deny"),
}

ROLE_PROMPTS: dict[AgentRole, str] = {
    AgentRole.CONTEXT_GATHERER: (
        "You verify that spec, plan, prior session, and this task are coherent and "
        "that context is complete. Emit ONLY a context manifest as a fenced ```json block "
        "matching the context_manifest schema.\n"
        "Coherence is established by DECLARED, MACHINE-VERIFIABLE checks -- the factory RE-RUNS "
        "every check you list, so a hollow or trivially-true check buys you nothing. Do NOT "
        "set any 'proven' or 'pass' field; the factory derives the verdict. Populate "
        "coherence.checks with entries of the form {\"name\": <str>, \"kind\": <str>, "
        "\"args\": {...}} drawn ONLY from this vocabulary:\n"
        "  - files_exist   {\"paths\": [<path>, ...]}\n"
        "  - file_contains {\"path\": <path>, \"pattern\": <str>, \"mode\": \"regex\"|\"literal\"}\n"
        "  - symbol_defined {\"path\": <path>, \"symbol\": <name>}\n"
        "  - anchor_resolves {\"ref\": \"<path>#<symbol-or-heading>\"}\n"
        "  - test_result   {\"gate\": \"unit\"|\"sim\"|\"full\", \"expected\": \"pass\"|\"fail\"}\n"
        "test_result is a BASELINE check (it runs before any work): expected=pass means a "
        "regression net exists; expected=fail means the bug reproduces now. Every file this "
        "task declares with a `Modify:` line MUST appear in context.source_files (it is a "
        "pre-existing file you must gather). A file_contains literal pattern MUST be copied "
        "verbatim from an actual read of that exact path -- never invented, paraphrased, or "
        "lifted from a different file; if the text is not in the file, do not assert that check. "
        "When the run is a retry, the validator's rejected checks appear under '## Feedback to "
        "address': you MUST remove or correct every one of them in your next manifest -- the "
        "factory re-runs each check, and resubmitting a check the validator already failed "
        "rejects the run. If you cannot ground coherence in such checks, populate reject instead.\n"
        "FIRST, before anything else: check whether this task's deliverables (the "
        "`Create:`/`Modify:`/`Test:` paths in the task body) already exist and satisfy "
        "the Definition of Done. Read files with the read/view tool -- NOT with bash "
        "(bash is disabled for your role). If the work already appears complete, add "
        '"already_done": true and a one-line "already_done_reason" to the manifest '
        "JSON; coherence checks need not be provided in that case."
    ),
    AgentRole.DEV: (
        "Implement the task using strict TDD (write the failing test first). "
        "Consult the provided knowledge-base entries. Do not stop until unit tests pass."
    ),
    AgentRole.VALIDATION: "Run the functional/sim suite. Do not modify source.",
    AgentRole.SYNTHESIS: (
        "Convert the human's play-test feedback into structured findings. Emit ONLY a "
        'fenced ```json block: {"findings": [{"description": <str>, '
        '"snapshot": {<repro route/steps/state>, optional}, '
        '"sr": "<a violated SR-### if obvious, else null>", '
        '"artifacts": [<path>, ...] (optional)}]}. '
        "One finding per distinct issue. Do NOT invent issues the feedback does not "
        "support, and do not fix anything -- the orchestrator routes each finding to a "
        "task after the human accepts it. "
        "Read files with the read/view tool -- NOT with bash (bash is disabled for your role)."
    ),
    AgentRole.REVIEW: (
        "Review the change for YAGNI/DRY and against the Definition of Done. Emit ONLY a "
        "fenced ```json block: {\"dod_met\": bool, \"principles\": [..], \"findings\": [..], "
        "\"confidence\": \"<one line: how sure you are and why>\", "
        "\"verify\": [{\"item\": \"<a concrete behavior/edge case a human should check "
        "before approving>\", \"file\": \"<path, optional>\", \"line\": <n, optional>, "
        "\"why\": \"<one line, optional>\"}]}. "
        "ALWAYS include confidence and 3-6 verify items -- even when dod_met is true; that is "
        "exactly when the human needs to know where you are least sure. verify items are "
        "concrete behaviors to check, NOT file summaries.\n"
        "Read files with the read/view tool -- NOT with bash (bash is disabled for your role). "
        "The sim and integration suites have ALREADY been run for you by the validation node "
        "before you were invoked; see 'What happened this run' below for their results. Do not "
        "ask the human to run them again. verify items are behaviors to check by hand, never "
        "commands the factory has already executed."
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
        "apply yourself.\n"
        "Finally, emit ONLY a single fenced ```json block as your very last message, with "
        "EXACTLY this schema:\n"
        '{"suggestions": [{"target": "prompt"|"skill"|"role"|"gate"|"config"|"other", '
        '"summary": "<one line>", "proposed": "<change>", '
        '"evidence": "<which event/observation>"}], "kb_added": ["kb/<path>", ...]}\n'
        "suggestions may be an empty list if nothing about the factory is worth changing. "
        "Target meaning: gate = .factory/factory.yaml (e.g. the interpreter/gate command); "
        "prompt = ROLE_PROMPTS wording; skill = a .pi/skills/<name>/SKILL.md improvement; "
        "role = agent scope/permission changes. This JSON block is the machine-readable "
        "outcome a consuming tool reads to propose factory-run updates automatically, so "
        "each entry's 'proposed' must be a concrete, actionable change.\n"
        "Read and write files with the read/view and write tools -- NOT with bash (bash is "
        "disabled for your role)."
    ),
}
