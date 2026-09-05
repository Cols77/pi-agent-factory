from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Callable

from coherence.register.fidelity_findings import FidelityFindingError, FidelityReviewResult, RelationRef, build_finding
from coherence.register.fidelity_packet import FidelityPacket

# SR-050/AC-4 (docs/superpowers/plans/2026-09-03-sr050-t5-fidelity-reviewer-plan.md,
# T5.3): "The per-requirement review's semantic-fidelity findings ... are
# produced by an agent-driven fidelity review, and that review's verdict
# does not close the requirement until the same human_review gate AC-3
# already enforces records an attributed decision covering it."
# (requirements/SR-050.md)
#
# `review_fidelity` is the judgement step: it hands a `FidelityPacket` to an
# injected `judge` callable and validates/normalizes whatever candidate
# findings come back through `fidelity_findings.build_finding` before
# anything is returned. It NEVER writes anything, gates anything, or treats
# its own output as authoritative -- see "Enforcement mechanics" below.
#
# Layering: this module (and every other file directly under
# `src/coherence/register/`) deliberately imports NOTHING from `factory.*`
# -- `tests/unit/requirements/test_coherence_parity.py::
# test_coherence_register_owns_the_register_and_uses_substrate_dependencies`
# enforces this for the whole package. That is why the REAL, `PiAgentBackend`
# -dispatch default judge (open design question #4) does not live here: it
# lives at `coherence.audit.fidelity_dispatch.default_judge` (that package
# already imports `factory.orchestrator` for its own, identically-shaped
# subagent dispatch, `coherence.audit.runner._dispatch_sr`, and already
# depends on `coherence.register` in one direction -- `coherence.audit.scope`
# -- so this adds no new dependency direction, just one more file on the
# existing side of it). `review_fidelity` itself only ever sees `judge` as an
# injected callable; it has no opinion on where a real implementation comes
# from, which is what makes this layering split possible in the first place.
#
# Enforcement mechanics: this module adds NO new obligation kind and makes
# NO change to `src/coherence/policy/compiler.py` -- see AC-4's own body
# addendum in requirements/SR-050.md and the plan's "Enforcement mechanics"
# section. A fidelity finding is agent output; agent output is never, by
# `_human_review_obligation`'s own design, sufficient on its own to close a
# requirement. `review_fidelity`'s result is surfaced (CLI, persistence) so
# a human resolving the existing `review:<sr_id>` human_review obligation can
# see it -- it never becomes a second, parallel closure path.


class FidelityJudgeUnavailable(RuntimeError):
    """Raised by a `judge` callable (or a candidate-finding validation step)
    when no trustworthy verdict could be produced -- `review_fidelity`
    catches this (and any other exception a judge raises) and turns it into
    the packet-level `status="unavailable"` result rather than propagating
    it or silently returning an empty findings tuple."""


def _new_run_id() -> str:
    return f"fidelity-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def review_fidelity(
    packet: FidelityPacket,
    judge: Callable[[FidelityPacket], list[dict]],
    *,
    run_id: str | None = None,
    produced_at: str | None = None,
    packet_fingerprint: str | None = None,
) -> FidelityReviewResult:
    """Run the fidelity judgement step for one packet (SR-050/AC-4, T5.3).

    `judge(packet)` must return a list of candidate finding dicts (each
    matching `FidelityFinding`'s JSON shape minus `sr_id`/`status`/
    `produced_at`/`produced_by_run`, which this function fills in). ANY
    failure -- the judge raises, returns a non-list, or returns a candidate
    that fails `build_finding`'s validation (including a hallucinated
    `relation` the packet never resolved) -- produces `status="unavailable"`
    for the WHOLE result, never a partial list of the candidates that
    happened to validate: a judge that got even one finding wrong about this
    SR is not a source this function trusts piecemeal for the rest, matching
    this design's existing all-or-nothing posture elsewhere (e.g.
    `substrate.validation.model.validation_report_errors`: any schema
    violation yields no statuses, not the ones that happened to be well
    -formed).

    `status="open"` is assigned to every fresh finding under `high_assurance`
    and `status="escalated"` under every other compiled profile -- T5's own
    status-assignment rule, distinct from (and never a substitute for)
    `_human_review_obligation`'s own, separately tested closure logic.

    `packet_fingerprint` (stale-fidelity-review remediation, HANDOFF.md Next
    Step 3 / audit finding 3.8) is an opaque pass-through: this function
    never computes it (that is `coherence.register.fidelity_packet.
    packet_fingerprint`'s job) and never inspects it -- the caller (`coherence.
    register.cli._fidelity_result_json`) is the one place that decides
    whether `judge` needs to run at all before ever calling this function,
    using `coherence.register.fidelity_persistence.is_fidelity_current`. It
    is stamped onto EVERY returned result, `status == "unavailable"`
    included, so a stored `unavailable` result still carries the fingerprint
    of the packet that produced it -- `is_fidelity_current` needs that value
    to correctly report "still not current" for an unavailable result whose
    fingerprint happens to match (see its own docstring: an unavailable
    result is never trusted regardless of fingerprint match).
    """
    run_id = run_id or _new_run_id()
    produced_at = produced_at or _now_iso()

    try:
        raw_candidates = judge(packet)
    except Exception as exc:  # noqa: BLE001 - a judge failure must never propagate or silently pass
        return FidelityReviewResult(
            sr_id=packet.sr_id,
            profile=packet.profile,
            findings=(),
            unresolved=packet.unresolved,
            run_id=run_id,
            produced_at=produced_at,
            status="unavailable",
            error=f"judge failed: {exc}",
            packet_fingerprint=packet_fingerprint,
        )

    if not isinstance(raw_candidates, list):
        return FidelityReviewResult(
            sr_id=packet.sr_id,
            profile=packet.profile,
            findings=(),
            unresolved=packet.unresolved,
            run_id=run_id,
            produced_at=produced_at,
            status="unavailable",
            error=f"judge returned {type(raw_candidates).__name__}, expected a list of findings",
            packet_fingerprint=packet_fingerprint,
        )

    status_for_new = "open" if packet.profile == "high_assurance" else "escalated"
    findings = []
    for i, raw in enumerate(raw_candidates):
        try:
            if not isinstance(raw, dict):
                raise FidelityFindingError(f"candidate finding {i} is not an object: {raw!r}")
            relation_raw = raw["relation"]
            relation = RelationRef(
                field=str(relation_raw["field"]),
                path=str(relation_raw["path"]),
                identity=str(relation_raw.get("identity", "")),
            )
            finding = build_finding(
                packet,
                sr_id=packet.sr_id,
                kind=str(raw["kind"]),
                relation=relation,
                confidence=float(raw["confidence"]),
                citations=tuple(str(c) for c in raw.get("citations") or ()),
                rationale=str(raw["rationale"]),
                acceptance_ref=(str(raw["acceptance_ref"]) if raw.get("acceptance_ref") is not None else None),
                status=status_for_new,
                produced_at=produced_at,
                produced_by_run=run_id,
            )
        except (KeyError, TypeError, ValueError, FidelityFindingError) as exc:
            return FidelityReviewResult(
                sr_id=packet.sr_id,
                profile=packet.profile,
                findings=(),
                unresolved=packet.unresolved,
                run_id=run_id,
                produced_at=produced_at,
                status="unavailable",
                error=f"candidate finding {i} invalid: {exc}",
                packet_fingerprint=packet_fingerprint,
            )
        findings.append(finding)

    return FidelityReviewResult(
        sr_id=packet.sr_id,
        profile=packet.profile,
        findings=tuple(findings),
        unresolved=packet.unresolved,
        run_id=run_id,
        produced_at=produced_at,
        status="ok",
        error=None,
        packet_fingerprint=packet_fingerprint,
    )


__all__ = [
    "FidelityJudgeUnavailable",
    "review_fidelity",
]
