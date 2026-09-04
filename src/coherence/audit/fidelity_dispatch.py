"""SR-050/AC-4's real, `PiAgentBackend`-dispatch fidelity `judge` (T5.3's
open design question #4).

This lives in `coherence.audit`, not `coherence.register`, purely for
layering: `coherence.register` deliberately imports nothing from `factory.*`
(`tests/unit/requirements/test_coherence_parity.py` enforces this for every
file directly under `src/coherence/register/`), but a real judge needs
`factory.orchestrator.pi_backend.PiAgentBackend` to actually dispatch a
subagent. `coherence.audit` already imports `factory.orchestrator` for the
identically-shaped `coherence.audit.runner._dispatch_sr` (coverage-review's
own per-SR subagent dispatch) and already depends on `coherence.register`
in one direction (`coherence.audit.scope`), so this module adds no new
dependency direction -- it is simply one more file on the existing side of
it.

`default_judge` matches `coherence.register.fidelity.review_fidelity`'s
injected `judge: Callable[[FidelityPacket], list[dict]]` contract exactly;
`coherence.cli` (the top-level `coherence` CLI dispatcher) is what wires it
in as the real default for `coherence register review --fidelity`/`--check`
-- see that module's own `register` group wiring.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from coherence.register.fidelity import FidelityJudgeUnavailable
from coherence.register.fidelity_packet import FidelityPacket

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def _extract_json_object(raw: str) -> dict:
    """Best-effort JSON object extraction from a subagent's raw text output
    -- a fenced ```json block first (the skill's own instructed format),
    falling back to parsing the whole string. Raises `ValueError`/`TypeError`
    (caught by `default_judge`) when neither works."""
    match = _JSON_FENCE_RE.search(raw)
    candidate = match.group(1) if match else raw.strip()
    return json.loads(candidate)


def _fidelity_prompt(packet: FidelityPacket) -> str:
    from factory.orchestrator.types import AgentRole
    from substrate.agents.skills import load_skill_block
    from substrate.paths import factory_skills_dir

    lines: list[str] = [f"# Role: {AgentRole.FIDELITY_REVIEW.value}"]
    lines.append(
        f"You are judging the semantic fidelity of {packet.sr_id}'s declared "
        "implemented_by/verified_by relations."
    )
    lines.append("")
    lines.append("## Loaded skills")
    lines.append(load_skill_block(factory_skills_dir(), "fidelity-review"))
    lines.append("")
    lines.append("## FidelityPacket (injected)")
    packet_view = {
        "sr_id": packet.sr_id,
        "statement": packet.statement,
        "profile": packet.profile,
        "acceptance": [
            {"id": a.id, "criterion": a.criterion, "verification_kind": a.verification_kind}
            for a in packet.acceptance
        ],
        "design_source": (
            {
                "doc_path": packet.design_source.doc_path,
                "anchor": packet.design_source.anchor,
                "excerpt": packet.design_source.excerpt,
            }
            if packet.design_source is not None
            else None
        ),
        "implemented": [
            {
                "path": p.path,
                "symbol": p.symbol,
                "signature": p.signature.signature,
                "summary": p.signature.summary,
                "source_excerpt": p.source_excerpt,
            }
            for p in packet.implemented
        ],
        "verified": [
            {
                "path": v.path,
                "test": v.test,
                "signature": (v.signature.signature if v.signature is not None else None),
                "source_excerpt": v.source_excerpt,
                "outcome": (
                    {"state": v.outcome.state, "stale": v.outcome.stale} if v.outcome is not None else None
                ),
            }
            for v in packet.verified
        ],
        "import_overlap": [
            {
                "implemented_ref": f.implemented_ref,
                "verified_ref": f.verified_ref,
                "reaches": f.reaches,
                "status": f.status,
            }
            for f in packet.import_overlap
        ],
        # Claims are intent, not proof -- the skill block loaded above tells
        # the judge exactly how to read them. Rendered here because a packet
        # field the prompt never carries is a fact the judge cannot use.
        "claims": [
            {
                "sha": c.sha,
                "subject": c.subject,
                "changed_files": [
                    {"path": path, "declared": declared}
                    for path, declared in zip(c.changed_files, c.declared)
                ],
            }
            for c in packet.claims
        ],
    }
    lines.append(json.dumps(packet_view, indent=2))
    lines.append("")
    lines.append("Return ONLY the fenced ```json findings block the skill describes.")
    return "\n".join(lines)


def default_judge(
    packet: FidelityPacket,
    *,
    root: Path,
    ext: Path,
    provider: str = "",
    model: str = "",
) -> list[dict]:
    """The real default `judge` for `review_fidelity` (open design question
    #4). Reuses `coherence.audit.runner._dispatch_sr`'s own subagent
    -dispatch convention: constructs a fresh `PiAgentBackend` and calls
    `backend.run(AgentRole.FIDELITY_REVIEW, prompt)`.

    Raises `FidelityJudgeUnavailable` on a failed dispatch or unparseable
    output -- it never returns a partial or guessed result. `review_fidelity`
    is what turns any exception here into the packet-level `unavailable`
    status; this function's job is only to talk to the subagent and parse
    what comes back.
    """
    from factory.orchestrator.pi_backend import PiAgentBackend
    from factory.orchestrator.types import AgentRole

    prompt = _fidelity_prompt(packet)
    backend = PiAgentBackend(root, ext, provider=provider or None, model=model or None)
    result = backend.run(AgentRole.FIDELITY_REVIEW, prompt)
    if not result.ok:
        raise FidelityJudgeUnavailable(f"subagent dispatch failed: {result.raw[:200]}")

    output = result.output if isinstance(result.output, dict) else None
    if output is None or "findings" not in output:
        try:
            output = _extract_json_object(result.raw)
        except (ValueError, TypeError) as exc:
            raise FidelityJudgeUnavailable(f"judge output was not parseable JSON: {exc}") from exc

    candidates = output.get("findings")
    if not isinstance(candidates, list):
        raise FidelityJudgeUnavailable(f"judge output missing a 'findings' list: {str(output)[:400]}")
    return candidates


__all__ = ["default_judge"]
