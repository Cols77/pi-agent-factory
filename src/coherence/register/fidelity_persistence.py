from __future__ import annotations

import dataclasses
import json
from pathlib import Path

from coherence.gate.content import resolve_admissible_review_decision
from coherence.register.fidelity_findings import FidelityReviewResult
from coherence.register.register import load_register

# SR-050/AC-4 (docs/superpowers/plans/2026-09-03-sr050-t5-fidelity-reviewer-plan.md,
# T5.4): durable per-SR storage for a `FidelityReviewResult`, plus re-run
# disposition tracking so a human's past `accept` is not silently
# re-litigated on every subsequent run.
#
# Location: `review-findings/fidelity/<sr_id>.json`, mirroring this repo's
# existing per-artifact file convention (`gate-decisions/<gate id>.json`,
# `coherence.gate.store.decision_path`). T4's own two deterministic
# reviewers persist NOTHING (both compute fresh on every CLI call, see
# `coherence.register.review`'s module docstring and
# `requirements/SR-050.md`'s AC-2 addendum) -- fidelity review is agent
# -driven and comparatively expensive to re-run, which is what justifies
# this module existing at all when T4 needed no analogue (see the plan's
# revised "Open design questions" #3).
#
# Disposition tracking never re-derives whether a finding is "true" -- that
# stays this run's own `review_fidelity` output. It ONLY rewrites `status`:
# a finding whose `(kind, relation)` pair matches a PRIOR STORED finding
# that a `review:<sr_id>` accept decision now post-dates is written back
# `dispositioned` rather than `open`/`escalated` again. The finding is never
# deleted -- SR-050's statement requires a review that "reports ...
# findings", not one that erases its own history.
#
# `is_fidelity_current` (stale-fidelity-review remediation, HANDOFF.md Next
# Step 3 / audit finding 3.8): the dispatch-path short-circuit. Before this,
# `coherence.register.cli._fidelity_result_json` re-judged EVERY targeted
# requirement from scratch on every `register review --fidelity --check`
# run -- with no `--id` that meant a fresh subagent dispatch for all 62+
# requirements, unconditionally, even when nothing the judge reads had
# changed since the last run. Building a `FidelityPacket` and hashing it
# (`coherence.register.fidelity_packet.packet_fingerprint`) is cheap and
# deterministic -- no model call -- so that always happens; only the actual
# judge dispatch is what this function decides to skip. Mirrors `coherence.
# gate.content.resolve_decision_currency`'s grandfather-then-backfill shape:
# a `None` stored fingerprint (a result stored before this field existed) is
# never treated as "still current" -- it is judged ONE more time, and that
# run's own `review_fidelity` call (via `packet_fingerprint=` there) stamps
# the fingerprint into the result this module then persists, so every
# subsequent run with unchanged content can skip the dispatch. Unlike
# `resolve_decision_currency`, the backfill here is a side effect of doing
# the (cheap, already-necessary) work once, not an out-of-band write.

FIDELITY_FINDINGS_DIR = ("review-findings", "fidelity")


def fidelity_findings_path(root: Path, sr_id: str) -> Path:
    return root.joinpath(*FIDELITY_FINDINGS_DIR, f"{sr_id}.json")


def load_fidelity_result(root: Path, sr_id: str) -> FidelityReviewResult | None:
    """The previously stored `FidelityReviewResult` for `sr_id`, or `None`
    when no file exists, the file is unreadable, or its content does not
    validate -- a corrupt or missing prior result is treated as "no prior
    result to disposition against", never as a crash."""
    path = fidelity_findings_path(root, sr_id)
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    try:
        return FidelityReviewResult.from_dict(raw)
    except (KeyError, TypeError, ValueError):
        return None


def _sr_path(root: Path, sr_id: str) -> Path | None:
    """The SR's own requirement file, resolved through the register, or
    `None` when it is not in the register. `_human_review_obligation`
    (`coherence.policy.compiler`) resolves the same SR's path through the
    trace graph instead -- two different lower-layer sources for the same
    fact, each already used elsewhere in its own module -- but both then
    feed the identical path into the ONE shared admissibility check,
    `coherence.gate.content.resolve_admissible_review_decision`."""
    reqs = load_register(root / "requirements")
    req = next((r for r in reqs if r.id == sr_id), None)
    return None if req is None else req.path


def _accepted_review_decision_at(root: Path, sr_id: str) -> str | None:
    """The `decided_at` of the admissible `accept` decision for
    `review:<sr_id>`, or `None` when no such decision exists.

    Admissibility (gate_id/item_id scoping, artifact_ref scoping,
    attribution, and SR-059/AC-2 content currency) is delegated entirely to
    `coherence.gate.content.resolve_admissible_review_decision` -- the SAME
    check `_human_review_obligation` (`coherence.policy.compiler`) uses, so
    this module and that one read one completion fact instead of two
    independently-maintained copies of it. This function's own remaining
    job is narrow: resolve `sr_id`'s path through THIS module's own source
    (the register, via `_sr_path` above) and read back `decided_at` -- it
    never re-derives any of the admissibility rules itself.

    This is bookkeeping only: it decides whether a STORED finding should
    stop being re-escalated on re-run, not whether the SR is closed --
    `_human_review_obligation` remains the sole gate for that."""
    sr_path = _sr_path(root, sr_id)
    if sr_path is None:
        return None
    decision = resolve_admissible_review_decision(root, f"review:{sr_id}", sr_path)
    return None if decision is None else decision.decided_at


def is_fidelity_current(prior: FidelityReviewResult | None, fingerprint: str) -> bool:
    """True when `prior` -- the previously persisted `FidelityReviewResult`
    for this SR, or `None` when there is none -- still covers `fingerprint`,
    the CURRENT packet's own `packet_fingerprint`. `True` means the caller
    (`coherence.register.cli._fidelity_result_json`) may reuse `prior`
    as-is instead of dispatching the judge again; `False` means it must
    re-dispatch.

    * `prior is None` (never judged before): `False` -- always dispatch.
    * `prior.status != "ok"` (the last run's judge failed, timed out, or
      returned something unparseable -- `FidelityJudgeUnavailable` and
      `review_fidelity`'s own catch-all): `False` UNCONDITIONALLY, even when
      `prior.packet_fingerprint == fingerprint`. A judge outage must never
      be read as "reviewed, found nothing" (the same rule `review_fidelity`
      and `cmd_review_check`'s own `unavailable`-blocks-`high_assurance`
      logic already hold this design to) -- trusting a fingerprint match on
      a failed run would let one judge outage silently freeze a stale
      "unavailable" verdict in place forever.
    * `prior.packet_fingerprint is None` (a legacy result stored before this
      field existed): `False` -- "stale once". There is no fingerprint on
      record to compare against, so this run must judge it at least one
      more time; that run's own result carries the fingerprint that lets
      every LATER run with unchanged content skip the dispatch (see the
      module docstring's grandfather-then-backfill note).
    * otherwise: `True` exactly when `prior.packet_fingerprint == fingerprint`.
    """
    if prior is None or prior.status != "ok" or prior.packet_fingerprint is None:
        return False
    return prior.packet_fingerprint == fingerprint


def apply_dispositions(root: Path, result: FidelityReviewResult) -> FidelityReviewResult:
    """Re-run disposition tracking (T5.4): a finding whose `(kind, relation)`
    matches a PRIOR STORED finding that a `review:<sr_id>` accept decision
    now post-dates is rewritten `dispositioned`. A finding with no matching
    prior finding, or no accept decision recorded (or one that predates the
    prior finding), keeps the `status` `review_fidelity` already assigned
    it. Never mutates `result`'s own findings in place -- returns a new
    `FidelityReviewResult`."""
    prior = load_fidelity_result(root, result.sr_id)
    if prior is None or not prior.findings:
        return result
    decided_at = _accepted_review_decision_at(root, result.sr_id)
    if decided_at is None:
        return result
    prior_by_key = {(f.kind, f.relation): f for f in prior.findings}
    new_findings = []
    for finding in result.findings:
        prior_match = prior_by_key.get((finding.kind, finding.relation))
        if prior_match is not None and prior_match.produced_at <= decided_at:
            new_findings.append(finding.with_status("dispositioned"))
        else:
            new_findings.append(finding)
    return dataclasses.replace(result, findings=tuple(new_findings))


def save_fidelity_result(root: Path, result: FidelityReviewResult) -> Path:
    """Apply re-run disposition tracking against the prior stored result (if
    any), then persist atomically. Overwrites the whole per-SR file (never
    appends), so a second run with identical findings overwrites idempotently
    -- there is no way for this to accumulate duplicate entries."""
    disposed = apply_dispositions(root, result)
    path = fidelity_findings_path(root, result.sr_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps(disposed.to_dict(), indent=2), encoding="utf-8")
    tmp.replace(path)
    return path


__all__ = [
    "FIDELITY_FINDINGS_DIR",
    "apply_dispositions",
    "fidelity_findings_path",
    "is_fidelity_current",
    "load_fidelity_result",
    "save_fidelity_result",
]
