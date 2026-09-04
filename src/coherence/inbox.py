"""Triage inbox (Increment 6 Task 4).

`list_items(root, now)` composes PURE source collectors into one
stable-sorted, de-duplicated `InboxItem` list. It is read-only with respect
to every SOURCE of triage state -- it never calls doctor/trace/register/KB
writers and never executes a resolver; ``resolve_cmd`` is informational (a
hint for the human who owns the item). One narrow, deliberate exception
(SR-059/AC-2): reading SR authoring consent may BACKFILL a checksum field
into an already-recorded, already-valid decision file that predates that
feature -- see ``_authoring_consent_items``'s own docstring. That backfill
never creates a new decision, never changes any decision's substance
(action/reason/attribution), and never affects what this function reports
for the read that triggered it.

Sources wired concretely here:
* coverage gates -- a ``coverage-reviews/<run>/status.json`` whose ``phase``
  is ``gates_blocked`` (Task 2) lists the ``coverage:<run>:proposal|warning:<id>``
  items a human must decide on;
* expired deferrals -- a requirement whose structured ``trace_deferred`` is
  due (Task 3 ``deferral_is_due``);
* stale register bindings -- a requirement whose recorded checksum no longer
  matches its content (``coherence.register.cli.cmd_index``);
* SR authoring consent -- every registered SR whose per-SR ``sr:SR-###``
  DecisionFile is absent, malformed, stale, addresses the wrong gate/item, or
  (SR-059/AC-2) whose recorded ``content_checksum`` no longer covers the SR's
  current content;
* an unreadable register -- a single ``register:unreadable`` item when
  ``load_register`` cannot parse the requirements directory at all, so the
  loss of every register-derived item is reported rather than looking like
  an empty queue (see ``_load_register_or_report``);
* suspect edges -- governed SR edges classified suspect/invalid/waived by
  ``edge_validity`` (Task 6 Step 4) via the ``unresolved_staleness`` sweep.

Item ids follow the Review Amendments vocabulary: ``coverage:<run>:proposal:<id>``,
``coverage:<run>:warning:<id>``, ``trace:<id>``, and ``sr:SR-###`` for authoring
consent. The list is stable-sorted by id and de-duplicated; reading never
authors a new decision or changes any existing decision's substance (see the
checksum-backfill exception above).
"""
from __future__ import annotations

import json
from pathlib import Path

from coherence.deferrals import deferral_is_due, parse_deferral


class InboxItem:
    """One triage item. A plain frozen-ish value object (JSON-serializable);
    ``resolve_cmd`` is informational, ``review_after`` an optional ISO string.
    """

    __slots__ = (
        "id", "source", "kind", "ref", "summary", "evidence",
        "resolve_cmd", "review_after",
    )

    def __init__(
        self,
        id: str,
        source: str,
        kind: str,
        ref: str,
        summary: str,
        evidence: str = "",
        resolve_cmd: tuple[str, ...] | None = None,
        review_after: str | None = None,
    ) -> None:
        self.id = id
        self.source = source
        self.kind = kind
        self.ref = ref
        self.summary = summary
        self.evidence = evidence
        self.resolve_cmd = resolve_cmd
        self.review_after = review_after

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "source": self.source,
            "kind": self.kind,
            "ref": self.ref,
            "summary": self.summary,
            "evidence": self.evidence,
            "resolve_cmd": self.resolve_cmd,
            "review_after": self.review_after,
        }


def _coverage_gate_items(root: Path) -> list[InboxItem]:
    """Collect coverage gates awaiting a decision (Task 2 ``gates_blocked``)."""
    reviews_dir = root / "coverage-reviews"
    if not reviews_dir.is_dir():
        return []
    items: list[InboxItem] = []
    for status_path in sorted(reviews_dir.glob("*/status.json")):
        try:
            status = json.loads(status_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if status.get("phase") != "gates_blocked":
            continue
        needed = status.get("needed_items") or []
        for item_id in needed:
            prefix, rest = item_id.split(":", 1) if ":" in item_id else (item_id, "")
            kind = "proposal" if ":proposal:" in item_id else "warning"
            sr = item_id.rsplit(":", 1)[-1]
            items.append(
                InboxItem(
                    id=item_id,
                    source="coverage",
                    kind=kind,
                    ref=f"sr:{sr}",
                    summary=f"coverage gate needs a decision on {kind} {sr}",
                    evidence=str(status_path),
                )
            )
    return items


def _expired_deferral_items(root: Path, now: str) -> list[InboxItem]:
    """Collect requirements whose structured deferral is due (Task 3)."""
    import frontmatter

    req_dir = root / "requirements"
    if not req_dir.is_dir():
        return []
    items: list[InboxItem] = []
    for path in sorted(req_dir.glob("*.md")):
        try:
            meta = frontmatter.load(str(path)).metadata
        except Exception:
            continue
        raw = meta.get("trace_deferred")
        if raw is None:
            continue
        try:
            deferral = parse_deferral(raw)
        except ValueError:
            continue
        sr_id = str(meta.get("id") or path.stem)
        try:
            due = deferral_is_due(deferral, now)
        except ValueError as exc:
            items.append(
                InboxItem(
                    id=f"trace:{sr_id}",
                    source="deferrals",
                    kind="unresolved_deferral",
                    ref=f"sr:{sr_id}",
                    summary=f"deferral status for {sr_id} is unresolved ({exc})",
                    evidence=deferral.reason,
                    resolve_cmd=(f"coherence register show {sr_id}",),
                    review_after=deferral.review_after,
                )
            )
            continue
        if due:
            items.append(
                InboxItem(
                    id=f"trace:{sr_id}",
                    source="deferrals",
                    kind="expired_deferral",
                    ref=f"sr:{sr_id}",
                    summary=f"deferral on {sr_id} expired at {deferral.review_after}",
                    evidence=deferral.reason,
                    resolve_cmd=(f"coherence register defer {sr_id} --reason ... --review-after <new>",),
                    review_after=deferral.review_after,
                )
            )
    return items


def _load_register_or_report(req_dir: Path) -> tuple[list, list[InboxItem]]:
    """The register, or the one inbox item saying it could not be read.

    Important 7 (review round 3): `_stale_binding_items` and
    `_authoring_consent_items` both called `load_register` unguarded, so a
    single malformed `acceptance:` block raised a `ValueError` straight out
    of `list_items` -- and the human lost coverage gates, expired deferrals
    and suspect edges along with the register. Every other source in this
    module is per-file try/excepted; these now match.

    The failure is REPORTED, not swallowed: an unreadable register is not
    "no requirements" (I-03 -- missing evidence is reported, never
    inferred), so it becomes a visible `register:unreadable` item carrying
    the parser's own message. Both callers emit the same item id, and
    `list_items` de-duplicates by id, so the human sees it exactly once.
    """
    from coherence.register.register import load_register

    try:
        return load_register(req_dir), []
    except Exception as exc:  # noqa: BLE001 -- reported below, never swallowed
        return [], [
            InboxItem(
                id="register:unreadable",
                source="register",
                kind="unreadable_register",
                ref="register",
                summary=(
                    "the requirement register could not be loaded; every "
                    "register-derived inbox item is missing until this is fixed"
                ),
                evidence=f"{type(exc).__name__}: {exc}",
                resolve_cmd=("coherence register check",),
            )
        ]


def _stale_binding_items(root: Path) -> list[InboxItem]:
    """Collect register bindings whose recorded checksum is stale (read-only).

    Uses `load_register` + `is_checksum_current` directly, never the
    writer `cmd_index` (which stamps checksums and writes index.json) -- the
    inbox must not create or modify files.
    """
    from coherence.register.register import is_checksum_current

    req_dir = root / "requirements"
    if not req_dir.is_dir():
        return []
    requirements, failure = _load_register_or_report(req_dir)
    if failure:
        return failure
    items: list[InboxItem] = []
    for req in requirements:
        if not is_checksum_current(req):
            items.append(
                InboxItem(
                    id=f"trace:{req.id}",
                    source="register",
                    kind="stale_binding",
                    ref=f"sr:{req.id}",
                    summary=f"binding on {req.id} is stale (recorded checksum changed)",
                )
            )
    return items


def _suspect_edge_items(root: Path) -> list[InboxItem]:
    """Collect governed edges classified suspect/invalid/waived (Task 6 Step 4).

    Reads `unresolved_staleness` -- the plan's gateway sweep -- into `suspect:<sr_id>`
    inbox items. It does NOT execute a resolver and does NOT author a decision;
    each item carries the human `accept` DecisionFile action (the only path to
    restore `valid`, per §13 amendment row 3 STRICT). A waived classification is
    still surfaced as an explicit recorded acceptance -- never dropped from view.
    """
    from coherence.staleness import unresolved_staleness

    items: list[InboxItem] = []
    for finding in unresolved_staleness(root):
        sr_id = finding.ref.partition(":")[2]
        items.append(
            InboxItem(
                id=f"suspect:{sr_id}",
                source="trace",
                kind="suspect_edge",
                ref=finding.ref,
                summary=(
                    f"governed edge {sr_id} needs a human accept to record `valid`"
                ),
                evidence=finding.reason,
                resolve_cmd=finding.resolve_cmd,
            )
        )
    return items


def _authoring_consent_items(root: Path, now: str) -> list[InboxItem]:
    """Collect SRs awaiting the authoring-consent gate.

    Authoring consent is deliberately a separate gate from verification review:
    only the exact ``sr:<requirement-id>`` gate and item can clear an SR from
    this queue. Reads are fail-closed. A malformed, duplicate, or mismatched
    DecisionFile remains visible as a pending item rather than being treated
    as consent.

    SR-059/AC-2: an otherwise-valid accept also stops counting as consent the
    moment the SR's own file content changes after it was recorded --
    ``coherence.gate.content.resolve_decision_currency`` compares the
    decision's stored ``content_checksum`` against the requirement's CURRENT
    content and, on mismatch, this item stays pending exactly as if no
    DecisionFile existed (fail closed, never silently read as still
    current). This is the ONE deliberate, documented exception to this
    module's "reads are side-effect free" contract stated above: a
    pre-existing decision with no checksum recorded is grandfathered as
    still-current for this one read, then has that checksum BACKFILLED into
    its stored file so a future content edit is correctly caught -- see
    ``resolve_decision_currency``'s own docstring for the full migration
    contract. The backfill only ever rewrites the machine-computed
    ``content_checksum`` field of an already-valid, already-recorded
    decision; it never authors a new decision and never changes any
    decision's ``action``/``reason``.
    """
    from coherence.gate.content import resolve_decision_currency
    from coherence.gate.model import CorruptDecisionFile
    from coherence.gate.store import decision_path, load_decision

    req_dir = root / "requirements"
    if not req_dir.is_dir():
        return []

    requirements, failure = _load_register_or_report(req_dir)
    if failure:
        return failure

    items: list[InboxItem] = []
    duplicate_ids = {
        req.id for req in requirements if sum(other.id == req.id for other in requirements) > 1
    }
    emitted_duplicate_ids: set[str] = set()
    project_root = root.resolve()
    for req in requirements:
        item_id = f"sr:{req.id}"
        path = decision_path(root, item_id)
        reason: str | None = None
        expected_artifact_ref = ""
        if req.id in duplicate_ids:
            if req.id in emitted_duplicate_ids:
                continue
            emitted_duplicate_ids.add(req.id)
            reason = "duplicate requirement registration"
        else:
            try:
                requirement_path = req.path.resolve().relative_to(project_root).as_posix()
            except (OSError, ValueError):
                reason = "requirement path is outside the canonical project root"
            else:
                expected_artifact_ref = f"artifact:{requirement_path}"

        if reason is None and path.is_file():
            try:
                decision_file = load_decision(path)
            except CorruptDecisionFile as exc:
                reason = f"invalid DecisionFile ({exc})"
            else:
                decisions = decision_file.decisions
                if (
                    decision_file.gate_id != item_id
                    or decision_file.artifact_ref != expected_artifact_ref
                    or len(decisions) != 1
                    or decisions[0].item_id != item_id
                ):
                    reason = "stale or mismatched DecisionFile"
                elif decisions[0].action == "defer":
                    try:
                        due = deferral_is_due(
                            parse_deferral(
                                {
                                    "reason": decisions[0].reason,
                                    "review_after": decisions[0].review_after,
                                }
                            ),
                            now,
                        )
                    except ValueError as exc:
                        reason = f"invalid defer freshness ({exc})"
                    else:
                        if due:
                            reason = "authoring consent defer expired"
                elif decisions[0].action == "accept":
                    # SR-059/AC-2: a correctly-scoped, attributed accept still
                    # does not clear this item if its content_checksum no
                    # longer covers req.path's CURRENT content -- see this
                    # function's own docstring for the grandfather/backfill
                    # migration `resolve_decision_currency` performs for a
                    # pre-existing, checksum-less decision.
                    current = resolve_decision_currency(root, decision_file, req.path)[1]
                    if not current:
                        reason = "authoring consent decision is stale (content changed since accept)"
        else:
            reason = "no DecisionFile"

        if reason is None:
            continue
        items.append(
            InboxItem(
                id=item_id,
                source="register",
                kind="authoring_consent",
                ref=item_id,
                summary=(
                    f"{req.id}: authoring consent pending ({reason}; expected DecisionFile "
                    f"at {path})"
                ),
                evidence=str(req.path),
                resolve_cmd=(f"coherence register show {req.id}",),
            )
        )
    return items


def list_items(root: Path | str, now: str) -> list[InboxItem]:
    """Compose all inbox sources into one stable-sorted, de-duplicated list
    (never authors a decision or executes a resolver; the one narrow,
    documented exception is `_authoring_consent_items`'s SR-059/AC-2 checksum
    backfill onto an already-recorded, pre-existing decision -- see that
    function's docstring)."""
    root = Path(root)
    collected: list[InboxItem] = []
    collected.extend(_coverage_gate_items(root))
    collected.extend(_expired_deferral_items(root, now))
    collected.extend(_stale_binding_items(root))
    collected.extend(_authoring_consent_items(root, now))
    collected.extend(_suspect_edge_items(root))

    # Stable sort by id; de-duplicate by id (first occurrence wins).
    seen: set[str] = set()
    deduped: list[InboxItem] = []
    for item in sorted(collected, key=lambda i: i.id):
        if item.id in seen:
            continue
        seen.add(item.id)
        deduped.append(item)
    return deduped


__all__ = ["InboxItem", "list_items"]