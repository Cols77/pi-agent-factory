from __future__ import annotations

from factory.orchestrator.backends import AgentBackend
from factory.orchestrator.types import AgentRole
from factory.polish.finding import Finding

# The backend parses the LAST fenced ```json block out of pi's event stream
# (parse_pi_json), so the prompt MUST demand that fence -- every ROLE_PROMPTS
# entry words it the same way. Asking merely for "JSON" yields prose or a bare
# object, which parses to {} and silently produces zero findings.
_PROMPT = """\
You are the SYNTHESIS role of a factory polish session on use case "{usecase}".
The human play-tested the app and gave this feedback:

{feedback}

Emit ONLY a fenced ```json block, no prose before or after:
{{"findings": [{{"description": str, "snapshot": object (optional,
repro route/steps/state), "sr": str|null (a violated SR-### if obvious),
"artifacts": [str] (optional)}}]}}
One finding per distinct issue. Do not invent issues the feedback does not
support. If the feedback reports no actionable problem, emit {{"findings": []}}."""


def synthesize(backend: AgentBackend, feedback: str, usecase: str) -> list[Finding]:
    result = backend.run(AgentRole.SYNTHESIS, _PROMPT.format(usecase=usecase, feedback=feedback))
    if not result.ok:
        return []
    items = result.output.get("findings", []) or []
    return [
        Finding(
            usecase=usecase,
            description=str(it["description"]),
            snapshot=dict(it.get("snapshot") or {}),
            sr=(str(it["sr"]) if it.get("sr") else None),
            artifacts=[str(a) for a in (it.get("artifacts") or [])],
        )
        for it in items
        if it.get("description")
    ]
