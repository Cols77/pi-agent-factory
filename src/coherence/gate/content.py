"""Content-checksum staleness for human-consent gate decisions (SR-059/AC-2).

A recorded ``accept`` decision on a `review:<sr_id>` or `sr:<sr_id>` gate
names a target artifact (`artifact_ref`) but says nothing, by itself, about
whether the artifact's content still matches what the human actually read
when they consented. `artifact_content_checksum` and
`resolve_decision_currency` close that gap: a decision now carries an
optional `content_checksum` (`coherence.gate.model.DecisionFile`) stamped
against the target's full file content, and a stored checksum that no
longer matches the target's CURRENT content means the decision no longer
covers it -- fail closed, never silently read as still current.

Deliberately separate from `coherence.register.register.content_checksum`
(measurement-binding currency): that function hashes only a requirement's
`statement` + `binding` fields, explicitly excluding body prose, because it
answers a narrower question ("has the thing a harness actually measures
changed"). Consent staleness is a broader question -- a human who accepted a
requirement's content read the WHOLE file (statement, acceptance criteria,
body prose alike), so this module hashes the artifact's raw bytes on disk,
not a parsed subset of its frontmatter. Two different staleness concerns,
two different functions, never conflated.

Migration for pre-existing decision files (real ones already exist on disk,
predating this feature, with no `content_checksum` recorded at all): a
blank stored checksum is NOT treated as automatically stale -- that would
mass-invalidate every already-granted consent across the whole repo the
moment this module ships, with no way to know whether the covered content
actually changed before or after this feature existed. Instead,
`resolve_decision_currency` grandfathers a checksum-less decision as
CURRENT this one time, then immediately backfills the checksum into the
stored file (via `coherence.gate.store.write_decision`, re-using the exact
same validated, atomic writer every other gate write already goes through)
so any FUTURE content change is correctly caught. This is a real,
deliberate judgement call, not glossed over: see `resolve_decision_currency`
for the exact contract, and requirements/SR-059.md's AC-2 closure for the
corpus-wide reasoning.

`resolve_admissible_review_decision` (below) is the ONE shared admissibility
check for a `review:<sr_id>` gate decision -- gate_id/item_id scoping,
artifact_ref scoping, attribution, and this module's own content currency --
extracted so `coherence.policy.compiler`'s `_human_review_obligation` (is the
SR closed for policy purposes) and `coherence.register.fidelity_persistence`'s
disposition tracker (should a stored fidelity finding stop being
re-escalated) read off the same completion fact instead of two
independently-maintained copies of the same six rules. It lives here, next
to `resolve_decision_currency`, because currency is the one rule of the six
that was already centralized -- the other five (scoping/attribution) belong
beside it now rather than staying split across two callers.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from coherence.gate.model import CorruptDecisionFile, DecisionFile, _is_iso
from coherence.gate.store import decision_path, load_decision, write_decision


def artifact_content_checksum(path: Path) -> str:
    """A stable checksum of `path`'s CURRENT full file content.

    Reads raw bytes -- not a parsed/field-scoped subset like
    `coherence.register.register.content_checksum` -- so any change to the
    file (statement, acceptance criteria, or body prose alike) changes this
    checksum. `sha256:<hex digest>`, the same `sha256:`-prefixed shape
    `coherence.register.overlap.content_fingerprint` already uses for its
    own, differently-scoped fingerprint.
    """
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return f"sha256:{digest}"


def resolve_decision_currency(
    run_dir: Path, decision_file: DecisionFile, target_path: Path,
) -> tuple[DecisionFile, bool]:
    """Whether `decision_file` currently covers `target_path`'s content.

    Returns `(effective_decision_file, current)`:

    * `decision_file.content_checksum` is set and matches
      `artifact_content_checksum(target_path)` right now: `(decision_file,
      True)` -- unchanged, still covers.
    * `decision_file.content_checksum` is set and does NOT match: `(decision_
      file, False)` -- stale. The caller must treat this exactly like a
      missing decision (fail closed), never continue reading it as current.
    * `decision_file.content_checksum` is blank (a pre-existing decision
      written before this feature, or a writer that never stamped one):
      grandfathered THIS ONE TIME -- `current=True` -- but the checksum is
      immediately backfilled into the stored file (`write_decision`, keyed
      by `decision_file.gate_id`, so it lands at the exact path this
      decision was already loaded from) so a SECOND content edit after this
      point is correctly caught. `effective_decision_file` is the backfilled
      file (checksum now set) so a caller that re-reads it in the same pass
      sees the up-to-date value. A backfill write that fails (e.g. a
      read-only filesystem) never raises past this function and never flips
      `current` to `False` -- the grandfather holds for this read either
      way; a failed backfill just means the next read grandfathers again,
      which is safe (it can only ever err on the side of "still covers",
      identical to today's un-migrated behaviour), never on the side of
      wrongly reporting staleness.
    * `target_path` cannot be read (missing, or any other `OSError`): fail
      closed -- `(decision_file, False)`. Absence of the target is never
      treated as "nothing to compare against, so it still covers."
    """
    try:
        current_checksum = artifact_content_checksum(target_path)
    except OSError:
        return decision_file, False

    stored = decision_file.content_checksum
    if stored:
        return decision_file, stored == current_checksum

    backfilled = DecisionFile(
        schema=decision_file.schema,
        gate_id=decision_file.gate_id,
        artifact_ref=decision_file.artifact_ref,
        decisions=decision_file.decisions,
        decided_at=decision_file.decided_at,
        decided_by=decision_file.decided_by,
        content_checksum=current_checksum,
    )
    try:
        write_decision(run_dir, backfilled)
    except OSError:
        return decision_file, True
    return backfilled, True


def artifact_ref_for(root: Path, path: Path) -> str | None:
    """The canonical `artifact:`-scheme ref for `path`, relative-posix to
    `root` -- the same computation `_human_review_obligation`
    (`coherence.policy.compiler`) and `_expected_artifact_ref`
    (`coherence.register.fidelity_persistence`) used to each perform inline.
    `None` when `path` cannot be expressed relative to `root` (outside the
    project root) -- there is no canonical ref a decision could correctly
    name in that case.
    """
    try:
        return "artifact:" + path.resolve().relative_to(root.resolve()).as_posix()
    except (OSError, ValueError):
        return None


def resolve_admissible_review_decision(
    root: Path, item_id: str, artifact_path: Path,
) -> DecisionFile | None:
    """The admissible, currently-covering `accept` DecisionFile for
    `item_id`, scoped to `artifact_path`'s own canonical `artifact:` ref, or
    `None` when no such decision exists.

    This is the ONE shared admissibility rule set for a gate decision that
    both `coherence.policy.compiler._human_review_obligation` and
    `coherence.register.fidelity_persistence._accepted_review_decision_at`
    read off -- see this module's docstring for why it lives here. I-01 --
    no self-certification -- means the producer of work is never the sole
    authority that it is done, and **the substrate cannot distinguish an
    agent-written decision from a human one**, so every rule below proves
    only what is actually on disk, never humanity itself:

    * a `DecisionFile` exists at `item_id`'s canonical path and parses/
      validates (a corrupt or missing file is `None`, never a crash and
      never a default-to-admissible);
    * its own `gate_id` equals `item_id` (never a file addressed to a
      different gate);
    * its `artifact_ref` equals `artifact_path`'s own canonical ref (never a
      decision scoped to a different artifact);
    * it carries EXACTLY one `Decision`, whose `item_id` also equals
      `item_id` and whose `action` is `accept` (never a `reject`/`defer`,
      and never a file that also decides other items);
    * it is attributed: a non-blank `decided_by` and a valid ISO-8601
      `decided_at` (`coherence.gate.model._is_iso`, the one ISO validator in
      this repo) -- a decision naming nobody, or naming no time, is
      nobody's decision;
    * and (SR-059/AC-2) its `content_checksum` currently covers
      `artifact_path`'s CURRENT full content (`resolve_decision_currency`,
      above) -- fail closed: a decision whose stored checksum no longer
      matches is treated exactly like no decision at all.

    Any one of these failing returns `None`; there is no path that infers
    admissibility from partial evidence.
    """
    expected_artifact_ref = artifact_ref_for(root, artifact_path)
    if expected_artifact_ref is None:
        return None
    path = decision_path(root, item_id)
    if not path.is_file():
        return None
    try:
        decision_file = load_decision(path)
    except CorruptDecisionFile:
        return None
    if decision_file.gate_id != item_id or decision_file.artifact_ref != expected_artifact_ref:
        return None
    decisions = decision_file.decisions
    if (
        len(decisions) != 1
        or decisions[0].item_id != item_id
        or decisions[0].action != "accept"
    ):
        return None
    if not decision_file.decided_by.strip() or not _is_iso(decision_file.decided_at):
        return None
    effective, current = resolve_decision_currency(root, decision_file, artifact_path)
    return effective if current else None


__all__ = [
    "artifact_content_checksum",
    "artifact_ref_for",
    "resolve_admissible_review_decision",
    "resolve_decision_currency",
]
