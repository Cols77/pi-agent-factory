"""Grounded natural-language guide synthesis and export (design SS4.4, SS4.5).

**Quotation, not paraphrase.** A synthesized guide section is fixed
scaffolding text plus **verbatim spans** copied character-for-character from
a cited source file. This module never rewords recorded text, and it never
invokes a language model -- synthesis here is deterministic template
assembly over data `coherence.navigate.queries` (brief/matrix/timeline) and the
canonical loaders (`coherence.register.register`, `coherence.navigate.bundles`,
`substrate.ledger.tasks`) already computed. A span is only ever emitted
after `_verbatim_span` independently re-reads the cited file and confirms
the candidate text is a literal substring of it -- the guide can never
assert a quote it has not just verified.

**Collapse predicate (design SS4.4).** For each section, freshness of every
fact backing it is checked: `all_dependencies_fresh(section) -> prose`,
otherwise the section renders as bullets built only from text
`coherence.navigate.queries` already produced (never new prose) -- `derived` when
the bullets roll up several distinct underlying facts (some possibly
`missing`), or the one contributing claim's own already-recorded `kind` when
there is only a single fact to fall back to unchanged (`_bullets`). This is
the one binary decision the design calls for. As a second, independent safety
net --
never itself a second *collapse* axis, since it only ever narrows an already
"fresh" section toward the same bullets outcome -- a section that is fresh
but for which a scaffolded sentence's verbatim span cannot be independently
verified also renders as bullets rather than emit unverifiable prose. In
practice, with this repo's real artifact shapes, every section template
below is designed around content that verifies whenever it is fresh, so this
safety net is not expected to fire in production; `test_guide.py` exercises
both `_verbatim_span` directly (to prove it *would* refuse an unverifiable
quote) and, by monkeypatching it to force a failure, the full
`query_guide()` path for every section that still checks a span (identity,
coverage/detail, validation -- the decision section carries no free-text
content to verify at all; see the next paragraph), proving each degrades
cleanly to bullets rather than raising or emitting a partial claim.

**What counts as "prose" needing a verified span.** The rule this module
exists to enforce is about *free-text natural-language content* (a
requirement statement, a bundle label, a task title) -- text someone wrote
in a source file that could, in principle, be reworded. Scaffolding
sentences may still directly embed *controlled-vocabulary* values --
scope/subject refs, requirement ids, and the fixed enum strings
(`ClaimClass`/`MatrixStatus`/`TimelineAction`/etc. already constrain these to
a small closed set) `coherence.navigate.queries` already computed -- the same
way the browser already prints `claim.kind`/`row.status` verbatim as a
badge. Those values are reproduced exactly, never paraphrased, and there is
nothing to "reword" in a five-way enum; only the free-text spans go through
`_verbatim_span`.

**Non-readmission (design SS4.5).** `export_guide` writes an output artifact,
never evidence: it is confined outside `evidence/`, `bundles/`, and
`requirements/`, and it carries a distinguishing `artifact` marker.
`is_exported_guide` lets `coherence.navigate.queries` refuse to cite one as a
bundle member (see the guard in `_resolve_spec_or_plan_member`) -- an
exported guide can never re-enter as a "recorded" input to a later guide.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from coherence.register import register
from coherence.navigate.models import (
    ClaimClass,
    CitationKind,
    Freshness,
    FreshnessDependency,
    FreshnessState,
    Span,
    SystemCitation,
    SystemClaim,
    SystemGuide,
    SystemScopeRef,
    to_dict,
)
from coherence.navigate.queries import (
    ScopeKindError,
    _requirements_dir,
    _tasks_dir,
    query_brief,
    query_matrix,
    query_timeline,
)
from substrate.ledger import tasks as ledger

EXPORTED_GUIDE_ARTIFACT_MARKER = "system_guide_export"

# design SS4.5: exports are written outside any evidence or manifest
# directory. `bundles`/`requirements` are additionally forbidden as a second,
# more direct non-readmission safeguard -- these are exactly the two
# directories a `bundle:`/`sr:` scope ref can ever resolve into
# (`queries._bundles_dir`/`_requirements_dir`), so an export can never even
# land somewhere a scope ref might later point at it.
_FORBIDDEN_EXPORT_DIRS = ("evidence", "bundles", "requirements")


def _identifier(scope: SystemScopeRef) -> str:
    # By the time a section builder runs, `query_brief`/`query_matrix`/
    # `query_timeline` have already validated `scope` exactly (SS5.1) --
    # raising ScopeKindError/ScopeNotFoundError if it did not resolve -- so a
    # plain split is safe here and does not re-implement that validation.
    return scope.ref.split(":", 1)[1]


def _all_fresh(freshnesses: list[Freshness]) -> bool:
    return bool(freshnesses) and all(f.state is FreshnessState.FRESH for f in freshnesses)


def _aggregate_freshness(freshnesses: list[Freshness]) -> Freshness:
    """Combine several already-computed `Freshness` values into one.

    Never recomputes staleness -- only rolls up states `coherence.navigate.
    queries` already assigned. Never returns `n/a`: an `n/a` contributor
    (a missing dependency) maps to `degraded` for the aggregate, which stays
    legal for a `recorded`/`synthesized` claim under the SS3.2 coupling rule
    (`kind == missing` iff `freshness.state == n/a`) -- only a `missing`
    claim may ever carry `n/a`, and no aggregate section here is `missing`
    (an empty-facts section is handled separately, before this is called).
    """
    states = {f.state for f in freshnesses}
    reasons = sorted({f.reason for f in freshnesses if f.reason})
    if FreshnessState.NA in states or FreshnessState.DEGRADED in states:
        state = FreshnessState.DEGRADED
    elif FreshnessState.STALE in states:
        state = FreshnessState.STALE
    else:
        state = FreshnessState.FRESH
    return Freshness(state=state, reason="; ".join(reasons) if reasons else None, dependencies=[])


def _freshness_from_dict(raw: dict) -> Freshness:
    deps = [
        FreshnessDependency(name=d["name"], expected=d.get("expected"), actual=d.get("actual"))
        for d in raw.get("dependencies", [])
    ]
    return Freshness(state=FreshnessState(raw["state"]), reason=raw.get("reason"), dependencies=deps)


def _citation_from_dict(raw: dict) -> SystemCitation:
    return SystemCitation(
        kind=CitationKind(raw["kind"]), path=raw["path"], sha256=raw.get("sha256"), anchor=raw.get("anchor")
    )


def _read_text(path: str) -> str | None:
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError:
        return None


def _verbatim_span(candidate: str, source_path: str, citation_index: int) -> Span | None:
    """Return a `Span` only after independently re-reading `source_path` and
    confirming `candidate` is a literal substring of it -- character for
    character, never reworded. Returns `None` (never a paraphrase, never a
    best-effort quote) if the file cannot be read or does not contain it.
    This is the one place text becomes "traceable to a span"; nothing else
    in this module is allowed to fabricate a `Span`.
    """
    if not candidate:
        return None
    source_text = _read_text(source_path)
    if source_text is None or candidate not in source_text:
        return None
    return Span(text=candidate, citation_index=citation_index)


def _missing_section(text: str) -> SystemClaim:
    return SystemClaim(
        kind=ClaimClass.MISSING,
        text=text,
        freshness=Freshness(state=FreshnessState.NA, reason="no recorded basis for this section", dependencies=[]),
    )


def _bullets(
    lines: list[str], citations: list[SystemCitation], freshness: Freshness, kind: ClaimClass
) -> SystemClaim:
    """Assemble a collapsed section from lines the caller already has in
    hand. `kind` is never hardcoded here -- the caller states it explicitly,
    because it depends on what the lines actually are:

    - a single already-recorded fact reproduced unchanged (the span-
      verification safety net catching one fresh claim) keeps that claim's
      own `kind` (always `recorded` in this module's real call sites);
    - a rollup over several distinct underlying facts (several bundle
      members, several matrix rows, several timeline events) is `derived`,
      never `recorded` -- collapsing multiple facts, some possibly `missing`,
      into one section is itself a transformation, not a verbatim quote.

    This is the fix for the bug where every collapsed section was
    unconditionally labelled `recorded`, even when built entirely from
    `missing` claims (design SS3.1: the badge must never overstate what
    contributed to it). The SS3.2 coupling rule still holds regardless of
    which `kind` is passed: `_aggregate_freshness` never returns `n/a` for a
    multi-claim rollup (an `n/a` contributor maps to `degraded`), so a
    `derived` section is never asked to carry `n/a`, and a single-claim
    fallback's freshness is always exactly the freshness that claim already
    had (`recorded` claims here are never `n/a` either).
    """
    return SystemClaim(kind=kind, text="\n".join(lines), freshness=freshness, citations=citations)


def _claim_bullet_line(claim: dict) -> str:
    """Render one already-computed claim dict as a bullet line, carrying its
    own `kind` and `freshness.state` the same way `cli.py:_render_brief`
    already prints `[{kind}] ({state}) {text}` for the brief -- so a
    collapsed guide section never hides which underlying claims were
    `missing` behind a section-level badge that only shows the aggregate.
    """
    return f"- [{claim['kind']}] ({claim['freshness']['state']}) {claim['text']}"


# ---------------------------------------------------------------------------
# Section 1: identity -- the bundle's declared label, or the SR's recorded
# statement. Always the scope's own declaration file, so freshness is always
# `fresh` once the scope has resolved at all (design SS3.2: "fresh: cited
# inputs match the current recorded dependencies" -- there is nothing else
# for a scope's own declaration to have drifted against).
# ---------------------------------------------------------------------------


def _identity_section(repo_root: Path, scope: SystemScopeRef, brief: dict) -> SystemClaim:
    identity_claim = brief["claims"][0]
    freshness = _freshness_from_dict(identity_claim["freshness"])
    citation = _citation_from_dict(identity_claim["citations"][0])

    if scope.kind == "bundle":
        # `queries.query_brief` sets this claim's text to `bundle.label`
        # verbatim (no added prefix), so the claim text itself is already
        # the exact candidate span.
        candidate = identity_claim["text"]
        scaffold = f'This guide covers the declared bundle "{candidate}".'
    else:
        req_id = _identifier(scope)
        reqs = register.load_register(_requirements_dir(repo_root))
        req = register.get_requirement(reqs, req_id)
        if req is None:
            return _missing_section(f"{scope.ref}: requirement no longer resolves")
        candidate = req.statement
        scaffold = f'This guide covers {req.id}, which states: "{candidate}"'

    if _all_fresh([freshness]):
        span = _verbatim_span(candidate, citation.path, 0)
        if span is not None:
            return SystemClaim(
                kind=ClaimClass.SYNTHESIZED, text=scaffold, freshness=freshness, citations=[citation], spans=[span]
            )

    # A single already-recorded claim reproduced unchanged, not a rollup --
    # keeps `identity_claim`'s own kind (always `recorded` here) rather than
    # the section-level `derived` a genuine multi-claim rollup gets below.
    return _bullets(
        [_claim_bullet_line(identity_claim)],
        [citation],
        freshness,
        kind=ClaimClass(identity_claim["kind"]),
    )


# ---------------------------------------------------------------------------
# Section 2 (bundle): implementation coverage over declared task members.
# ---------------------------------------------------------------------------


def _bundle_coverage_section(repo_root: Path, scope: SystemScopeRef, brief: dict) -> SystemClaim:
    facts = brief["claims"][1:]
    if not facts:
        return _missing_section(f"{scope.ref}: no members declared in this bundle")

    freshnesses = [_freshness_from_dict(c["freshness"]) for c in facts]
    task_ref_claims = [
        c
        for c in facts
        if c["citations"] and c["citations"][0]["kind"] == "task" and c["text"].startswith("task:")
    ]

    if _all_fresh(freshnesses) and task_ref_claims:
        tasks = ledger.load_tasks(_tasks_dir(repo_root))
        sentences: list[str] = []
        citations: list[SystemCitation] = []
        spans: list[Span] = []
        ok = True
        for claim in task_ref_claims:
            task_id = claim["text"].split(":", 1)[1]
            task = ledger.get_task(tasks, task_id)
            citation = _citation_from_dict(claim["citations"][0])
            span = None if task is None else _verbatim_span(task.title, citation.path, len(citations))
            if task is None or span is None:
                ok = False
                break
            citations.append(citation)
            spans.append(span)
            sentences.append(f'Task {task.id}, "{task.title}", is a declared member of this scope.')
        if ok:
            return SystemClaim(
                kind=ClaimClass.SYNTHESIZED,
                text=" ".join(sentences),
                freshness=_aggregate_freshness(freshnesses),
                citations=citations,
                spans=spans,
            )

    citations = []
    for c in facts:
        for cite in c["citations"]:
            sc = _citation_from_dict(cite)
            if sc not in citations:
                citations.append(sc)
    # A rollup over every declared member's own claim -- some may be
    # `missing` (an unresolved member) -- so the section is `derived`, and
    # each bullet carries the contributing claim's own `kind`/freshness
    # rather than letting the section-level badge overstate it (design
    # SS3.1; this is the fix for the bug where a bundle whose members are
    # all `missing` rendered as a `recorded` section).
    lines = [_claim_bullet_line(c) for c in facts]
    return _bullets(lines, citations, _aggregate_freshness(freshnesses), kind=ClaimClass.DERIVED)


# ---------------------------------------------------------------------------
# Section 2 (sr): the requirement's own recorded title -- a second, distinct
# quotable field from the identity section's statement.
# ---------------------------------------------------------------------------


def _sr_detail_section(repo_root: Path, scope: SystemScopeRef, brief: dict) -> SystemClaim:
    # `_sr_brief_claims` always appends the upstream claim second, right
    # after the statement claim -- always present, never missing.
    upstream_claim = brief["claims"][1]
    freshness = _freshness_from_dict(upstream_claim["freshness"])

    req_id = _identifier(scope)
    reqs = register.load_register(_requirements_dir(repo_root))
    req = register.get_requirement(reqs, req_id)
    if req is None:
        return _missing_section(f"{scope.ref}: requirement no longer resolves")

    citation = _citation_from_dict(brief["claims"][0]["citations"][0])
    if _all_fresh([freshness]):
        span = _verbatim_span(req.title, citation.path, 0)
        if span is not None:
            text = f'{req.id} is titled "{req.title}".'
            return SystemClaim(
                kind=ClaimClass.SYNTHESIZED, text=text, freshness=freshness, citations=[citation], spans=[span]
            )

    # A single already-recorded claim reproduced unchanged (the upstream
    # claim `_sr_brief_claims` always includes second) -- keeps its own
    # kind, not a rollup's `derived`.
    upstream_citations = [_citation_from_dict(c) for c in upstream_claim["citations"]] or [citation]
    return _bullets(
        [_claim_bullet_line(upstream_claim)],
        upstream_citations,
        freshness,
        kind=ClaimClass(upstream_claim["kind"]),
    )


# ---------------------------------------------------------------------------
# Section 3: validation coverage, over the validation matrix -- the section
# a stale/degraded/missing validation report genuinely collapses (design
# SS10 integration requirement: "stale validation after a content change
# collapses the guide to bullets").
# ---------------------------------------------------------------------------


def _requirement_citations_by_sr_ref(scope: SystemScopeRef, brief: dict) -> dict[str, dict]:
    if scope.kind == "sr":
        return {scope.ref: brief["claims"][0]["citations"][0]}
    lookup: dict[str, dict] = {}
    for c in brief["claims"]:
        if c["text"].startswith("sr:") and c["citations"] and c["citations"][0]["kind"] == "requirement":
            lookup[c["text"]] = c["citations"][0]
    return lookup


def _validation_section(repo_root: Path, scope: SystemScopeRef, brief: dict, matrix: dict) -> SystemClaim:
    rows = matrix["rows"]
    if not rows:
        return _missing_section(f"{scope.ref}: no validation rows recorded for this scope")

    freshnesses = [_freshness_from_dict(r["freshness"]) for r in rows]
    citation_lookup = _requirement_citations_by_sr_ref(scope, brief)

    if _all_fresh(freshnesses):
        reqs = register.load_register(_requirements_dir(repo_root))
        sentences: list[str] = []
        citations: list[SystemCitation] = []
        spans: list[Span] = []
        ok = True
        for row in rows:
            sr_ref = row["subject"]["ref"]
            cite_raw = citation_lookup.get(sr_ref)
            req = register.get_requirement(reqs, sr_ref.split(":", 1)[1])
            if cite_raw is None or req is None:
                ok = False
                break
            citation = _citation_from_dict(cite_raw)
            span = _verbatim_span(req.statement, citation.path, len(citations))
            if span is None:
                ok = False
                break
            citations.append(citation)
            spans.append(span)
            sentences.append(f'{req.id}, "{req.statement}", is recorded with validation status {row["status"]}.')
        if ok:
            return SystemClaim(
                kind=ClaimClass.SYNTHESIZED,
                text=" ".join(sentences),
                freshness=_aggregate_freshness(freshnesses),
                citations=citations,
                spans=spans,
            )

    citations = []
    lines = []
    for row in rows:
        lines.append(f"- {row['subject']['ref']}: {row['status']} ({row['freshness']['state']}) {row['summary']}")
        cite_raw = citation_lookup.get(row["subject"]["ref"])
        if cite_raw is not None:
            sc = _citation_from_dict(cite_raw)
            if sc not in citations:
                citations.append(sc)
    # A matrix row is never itself a "recorded claim" -- it is computed
    # (design SS7.3), so a rollup of one or more rows is `derived`, never
    # `recorded`. Each line already carries the row's own status/freshness.
    return _bullets(lines, citations, _aggregate_freshness(freshnesses), kind=ClaimClass.DERIVED)


# ---------------------------------------------------------------------------
# Section 4: decision history, over the timeline. This artifact type never
# records an actor (see queries.py's module comment above
# `_decision_event_from_record`), so every real event is `degraded` -- this
# section collapses to bullets whenever there is anything recorded at all,
# honestly, not as a contrived test fixture.
#
# `actor` and `action` are both controlled vocabulary (`TimelineActor`/
# `TimelineAction`, closed enums `coherence.navigate.queries` already resolved --
# design SS7.4) and `subject.ref` is a derived ref string, not free-text
# copied from a source document -- there is nothing here for
# `_verbatim_span` to verify (see the module docstring's "what counts as
# prose" note), so this section never emits a `Span` even when synthesized.
# Review round 1, finding 2: an earlier version routed `action` through
# `_verbatim_span` while embedding `actor` directly two lines later in the
# same sentence -- an inconsistency that silently defeated the fresh->prose
# path for this section in practice, because no real review record's mapped
# action string (e.g. "approve" -> "approved") is ever literally present in
# its own citation file. `test_decision_section_renders_prose_when_every_
# event_is_fresh` pins the fix.
# ---------------------------------------------------------------------------


def _decision_section(timeline: dict) -> SystemClaim:
    events = timeline["events"]
    if not events:
        return _missing_section(f"{timeline['scope']['ref']}: no recorded decisions for this scope")

    freshnesses = [_freshness_from_dict(e["freshness"]) for e in events]

    if _all_fresh(freshnesses):
        citations: list[SystemCitation] = []
        sentences: list[str] = []
        for event in events:
            citation = _citation_from_dict(event["citation"])
            if citation not in citations:
                citations.append(citation)
            sentences.append(f'{event["subject"]["ref"]} was {event["action"]} by {event["actor"]}.')
        return SystemClaim(
            kind=ClaimClass.SYNTHESIZED,
            text=" ".join(sentences),
            freshness=_aggregate_freshness(freshnesses),
            citations=citations,
            spans=[],
        )

    citations = []
    lines = []
    for event in events:
        lines.append(f"- {event['subject']['ref']}: {event['actor']} {event['action']} ({event['freshness']['state']})")
        sc = _citation_from_dict(event["citation"])
        if sc not in citations:
            citations.append(sc)
    # A timeline event is never itself a "recorded claim" -- it is derived
    # from a review record (design SS7.4) -- so a rollup of one or more
    # events is `derived`, never `recorded`.
    return _bullets(lines, citations, _aggregate_freshness(freshnesses), kind=ClaimClass.DERIVED)


def query_guide(repo_root: Path, scope: SystemScopeRef) -> dict:
    """Assemble the grounded guide for `scope` (design SS4.4, SS5.2).

    Deterministic template assembly only: no language model is invoked, and
    the four sections (identity, coverage/detail, validation, decisions) are
    built entirely from `coherence.navigate.queries.query_brief`/`query_matrix`/
    `query_timeline` plus the same canonical loaders those functions use.
    Given the same repo content, this always returns the same dict -- no
    wall-clock reads, no randomness, no unordered iteration.
    """
    if scope.kind not in ("bundle", "sr"):
        raise ScopeKindError(f"unsupported scope kind: {scope.kind!r}")

    brief = query_brief(repo_root, scope)
    matrix = query_matrix(repo_root, scope)
    timeline = query_timeline(repo_root, scope)

    identity = _identity_section(repo_root, scope, brief)
    detail = (
        _bundle_coverage_section(repo_root, scope, brief)
        if scope.kind == "bundle"
        else _sr_detail_section(repo_root, scope, brief)
    )
    validation = _validation_section(repo_root, scope, brief, matrix)
    decisions = _decision_section(timeline)

    guide = SystemGuide(scope=scope, sections=[identity, detail, validation, decisions])
    return to_dict(guide)


# ---------------------------------------------------------------------------
# Export (design SS4.5) -- the single write path. Guides are otherwise
# ephemeral: computed per request, never written, never stored as evidence.
# ---------------------------------------------------------------------------


def is_exported_guide(path: Path) -> bool:
    """True only for a file this module itself wrote via `export_guide`.

    Used by `coherence.navigate.queries._resolve_spec_or_plan_member` to refuse
    citing an exported guide as a bundle member (the non-readmission rule) --
    a bare `path.is_file()` check cannot otherwise tell an exported guide
    apart from a real spec/plan file, so this checks for the distinguishing
    `artifact` marker `export_guide` always writes. Deliberately does not
    gate on a `.json` suffix first: `--export` accepts any path, so an
    exported guide is not guaranteed to end in `.json`, and skipping the
    content check for non-`.json` paths would silently reopen the exact
    readmission hole this function exists to close. A real spec/plan file
    (markdown, YAML frontmatter, etc.) simply fails `json.loads` and is
    reported `False`, same as any other unrelated file.
    """
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(raw, dict) and raw.get("artifact") == EXPORTED_GUIDE_ARTIFACT_MARKER


def _confine_export_path(repo_root: Path, dest: Path) -> Path:
    """Resolve and validate an `--export` destination (design SS4.5, SS9).

    Rejects, all as a structured `ValueError` (never an uncaught traceback):
    - anything outside the repo root, including the root itself. `target ==
      root` used to be explicitly allowed, which let `export_guide`'s
      `tmp = target.with_name(target.name + ".tmp")` compute a *sibling* of
      the repo root (e.g. `<root>.tmp`) -- a write outside the confined tree
      that design SS9 names as a hard invariant. `Path("")` resolves to
      `root` too, so `--export ""` hits this same guard.
    - any existing directory, root or not. `export_guide` always writes a
      *file* at `target` (`tmp.replace(target)`); pointing `--export` at a
      directory that already exists crashes that rename with an OS-level
      `PermissionError`/`OSError` instead of a structured error.
    - the forbidden non-readmission directories (evidence/bundles/requirements).
    """
    root = repo_root.resolve()
    target = (dest if dest.is_absolute() else root / dest).resolve()
    if target == root or root not in target.parents:
        raise ValueError(f"export path escapes repo root: {dest}")
    if target.is_dir():
        raise ValueError(f"export path must not be an existing directory: {dest}")
    for forbidden_name in _FORBIDDEN_EXPORT_DIRS:
        forbidden = (root / forbidden_name).resolve()
        if target == forbidden or forbidden in target.parents:
            raise ValueError(
                f"export path must stay outside {forbidden_name}/ (design SS4.5 non-readmission rule): {dest}"
            )
    return target


def _collect_citations(guide_payload: dict) -> list[dict]:
    seen: list[dict] = []
    for section in guide_payload["sections"]:
        for citation in section["citations"]:
            if citation not in seen:
                seen.append(citation)
    return seen


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def export_guide(repo_root: Path, scope: SystemScopeRef, dest: Path) -> Path:
    """Write the guide for `scope` to `dest` as a point-in-time artifact.

    The only write path this package has (design SS4.5). The written file:
    - records its generation timestamp and the full citation set it was
      built from;
    - carries a header stating it is a point-in-time projection, not a
      source of truth;
    - is confined outside `evidence/`, `bundles/`, and `requirements/`
      (`_confine_export_path`);
    - carries `EXPORTED_GUIDE_ARTIFACT_MARKER` so `is_exported_guide` can
      refuse to ever cite it back in as evidence.

    Nothing is written unless this function is called explicitly -- there is
    no implicit export path anywhere in `query_guide`.
    """
    guide_payload = query_guide(repo_root, scope)
    target = _confine_export_path(repo_root, dest)

    export_doc = {
        "artifact": EXPORTED_GUIDE_ARTIFACT_MARKER,
        "warning": (
            "This is a point-in-time projection generated by the system navigator guide. "
            "It is NOT evidence and is never a source of truth. The navigator refuses to "
            "resolve a scope ref that points at this file, and refuses to cite it (design "
            "section 4.5, non-readmission rule)."
        ),
        "generated_at": _utcnow_iso(),
        "scope": {"kind": scope.kind, "ref": scope.ref},
        "guide": guide_payload,
        "citations": _collect_citations(guide_payload),
    }

    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text(json.dumps(export_doc, indent=2), encoding="utf-8")
    tmp.replace(target)
    return target

