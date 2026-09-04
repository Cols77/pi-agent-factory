"""SR-058/AC-2's real, `PiAgentBackend`-dispatch overlap judge.

This lives in `coherence.audit`, not `coherence.register`, for exactly the
layering reason `coherence.audit.fidelity_dispatch` (SR-050/T5) already
documents: `coherence.register` deliberately imports nothing from
`factory.*` (`tests/unit/requirements/test_coherence_parity.py` enforces
this for every file directly under `src/coherence/register/`), but a real
judge needs `factory.orchestrator.pi_backend.PiAgentBackend` to actually
dispatch a subagent. `coherence.audit` already imports `factory.orchestrator`
for the identically-shaped `coherence.audit.runner._dispatch_sr` and already
depends on `coherence.register` in one direction, so this module adds no new
dependency direction -- it is simply one more file on the existing side of
it.

`default_judge` matches `coherence.register.overlap.verify_candidates`'s
injected `judge: Callable[[OverlapCandidate], dict]` contract exactly;
`coherence.cli` is what wires it in as the real default for
`coherence register overlap-check` -- see that module's own `register` group
wiring, mirroring `_register_judge_factory`'s existing fidelity wiring.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from coherence.register.overlap import OverlapCandidate, OverlapJudgeUnavailable

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def _extract_json_object(raw: str) -> dict:
    """Best-effort JSON object extraction from a subagent's raw text output
    -- a fenced ```json block first (the skill's own instructed format),
    falling back to parsing the whole string. Raises `ValueError`/`TypeError`
    (caught by `default_judge`) when neither works."""
    match = _JSON_FENCE_RE.search(raw)
    candidate = match.group(1) if match else raw.strip()
    return json.loads(candidate)


def _overlap_prompt(candidate: OverlapCandidate) -> str:
    from factory.orchestrator.types import AgentRole
    from substrate.agents.skills import load_skill_block
    from substrate.paths import factory_skills_dir

    lines: list[str] = [f"# Role: {AgentRole.OVERLAP_REVIEW.value}"]
    lines.append(
        f"You are judging whether {candidate.sr_a} and {candidate.sr_b} make a "
        "plausibly overlapping behavioral claim."
    )
    lines.append("")
    lines.append("## Loaded skills")
    lines.append(load_skill_block(factory_skills_dir(), "overlap-review"))
    lines.append("")
    lines.append("## Candidate pair (injected)")
    lines.append(
        json.dumps(
            {
                "pair_id": candidate.pair_id,
                "lexical_similarity_score": candidate.score,
                "sr_a": {"id": candidate.sr_a, "statement": candidate.sr_a_statement},
                "sr_b": {"id": candidate.sr_b, "statement": candidate.sr_b_statement},
            },
            indent=2,
        )
    )
    lines.append("")
    lines.append("Return ONLY the fenced ```json verdict block the skill describes.")
    return "\n".join(lines)


def default_judge(
    candidate: OverlapCandidate,
    *,
    root: Path,
    ext: Path,
    provider: str = "",
    model: str = "",
) -> dict:
    """The real default `judge` for `verify_candidates`. Reuses
    `coherence.audit.runner._dispatch_sr`'s own subagent-dispatch
    convention: constructs a fresh `PiAgentBackend` and calls
    `backend.run(AgentRole.OVERLAP_REVIEW, prompt)`.

    Raises `OverlapJudgeUnavailable` on a failed dispatch or unparseable
    output -- it never returns a partial or guessed verdict.
    `verify_candidates` is what turns any exception here into the
    candidate-level `unavailable` status; this function's job is only to
    talk to the subagent and parse what comes back.
    """
    from factory.orchestrator.pi_backend import PiAgentBackend
    from factory.orchestrator.types import AgentRole

    prompt = _overlap_prompt(candidate)
    backend = PiAgentBackend(root, ext, provider=provider or None, model=model or None)
    result = backend.run(AgentRole.OVERLAP_REVIEW, prompt)
    if not result.ok:
        raise OverlapJudgeUnavailable(f"subagent dispatch failed: {result.raw[:200]}")

    output = result.output if isinstance(result.output, dict) else None
    if output is None or "confirmed" not in output:
        try:
            output = _extract_json_object(result.raw)
        except (ValueError, TypeError) as exc:
            raise OverlapJudgeUnavailable(f"judge output was not parseable JSON: {exc}") from exc

    if "confirmed" not in output:
        raise OverlapJudgeUnavailable(f"judge output missing 'confirmed': {str(output)[:400]}")
    return output


__all__ = ["default_judge"]
