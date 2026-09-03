from __future__ import annotations

import dataclasses
import json
from pathlib import Path

from coherence.gate.model import CorruptDecisionFile, _is_iso
from coherence.gate.store import decision_path, load_decision
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


def _expected_artifact_ref(root: Path, sr_id: str) -> str | None:
    """The SR's own canonical `artifact:` ref, computed the SAME way
    `_human_review_obligation` computes `expected_artifact_ref`
    (`src/coherence/policy/compiler.py` lines ~322-326) -- `artifact:` plus
    the SR's own requirement file path, relative-posix, resolved through the
    register rather than the trace graph (this module already reads the
    register nowhere else, but `coherence.register.register.load_register`
    is the same lower-layer source `_sr_node_path`'s trace node ultimately
    resolves from, so this stays a SEPARATE, local computation without
    importing `compiler.py` -- see the module docstring). `None` when the SR
    is not in the register (no requirement file to point at) or its path
    cannot be expressed relative to `root` -- either way there is no
    canonical ref a decision could correctly name."""
    reqs = load_register(root / "requirements")
    req = next((r for r in reqs if r.id == sr_id), None)
    if req is None:
        return None
    try:
        return "artifact:" + req.path.resolve().relative_to(root.resolve()).as_posix()
    except (OSError, ValueError):
        return None


def _accepted_review_decision_at(root: Path, sr_id: str) -> str | None:
    """The `decided_at` of an attributed `accept` decision for
    `review:<sr_id>` that is ALSO correctly scoped to this SR's own
    `artifact_ref`, or `None` when no such decision exists. Mirrors
    `_human_review_obligation`'s own rule set in full now -- gate_id, item_id
    scoping, artifact_ref scoping (`_expected_artifact_ref` above), AND
    attribution (non-blank `decided_by`, valid ISO-8601 `decided_at`) -- but
    is intentionally a SEPARATE, local read -- this module never imports
    `src/coherence/policy/compiler.py` (untouched by this task; see
    `coherence.register.fidelity`'s module docstring) and does not gate
    requirement closure itself. This is bookkeeping only: it decides whether
    a STORED finding should stop being re-escalated on re-run, not whether
    the SR is closed -- `_human_review_obligation` remains the sole gate for
    that. The artifact_ref check matters here precisely because it is
    bookkeeping with a real side effect: a mis-scoped decision (stale, wrong,
    or manually-edited `artifact_ref`) must not disposition a stored finding
    and thereby drop it out of `cmd_review_check`'s CI-blocking list while
    AC-3's own gate would still correctly treat the SR as unreviewed."""
    item_id = f"review:{sr_id}"
    path = decision_path(root, item_id)
    if not path.is_file():
        return None
    try:
        decision_file = load_decision(path)
    except CorruptDecisionFile:
        return None
    if decision_file.gate_id != item_id:
        return None
    expected_artifact_ref = _expected_artifact_ref(root, sr_id)
    if expected_artifact_ref is None or decision_file.artifact_ref != expected_artifact_ref:
        return None
    decisions = decision_file.decisions
    if len(decisions) != 1 or decisions[0].item_id != item_id or decisions[0].action != "accept":
        return None
    if not decision_file.decided_by.strip() or not _is_iso(decision_file.decided_at):
        return None
    return decision_file.decided_at


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
    "load_fidelity_result",
    "save_fidelity_result",
]
