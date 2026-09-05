from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

import frontmatter

from coherence.policy.compiler import resolve_profile
from coherence.register.register import load_register
from coherence.register.relations import ReferenceIssue, resolve_sr_relations
from coherence.register.review import claiming_commits
from coherence.trace.validation_status import load_validation
from substrate.codemap.build import file_signatures
from substrate.codemap.imports import compute_overlap
from substrate.codemap.model import CodeIndex
from substrate.codemap.store import ensure_fresh
from substrate.evidence.read import list_run_manifests

# SR-050/AC-4 (docs/superpowers/plans/2026-09-03-sr050-t5-fidelity-reviewer-plan.md,
# work package T5.1): "The per-requirement review's semantic-fidelity
# findings ... are produced by an agent-driven fidelity review ..."
# (requirements/SR-050.md).
#
# This module is the packet BUILDER only -- a pure reader/composer over four
# already-real sources (T1's relation resolver, the code map, the import-
# overlap mechanism, and evidence/validation-status readers). It parses
# nothing new, re-implements no existing resolver, and contains no
# judgement: `build_fidelity_packet` is deterministic and independently
# testable, exactly like T4's `structural_review`/`evidence_reconciliation_review`.
# The judgement step itself lives in `coherence.register.fidelity`.
#
# `line` is deliberately dropped at the packet boundary (`IndexSignatureView`
# carries no `line` field) -- the design forbids line numbers as identity
# (mirroring `relations.py`'s own `_LINE_SEGMENT_RE` rule): a fidelity
# finding's citation must stay valid across a reformat that shifts lines but
# not symbols. `IndexSignature.line` is used internally, before the packet is
# built, only to slice `source_excerpt` -- it never appears in a packet field
# a reviewer's output could cite back.
#
# `FidelityPacket.diagnostics` is one deliberate, documented addition beyond
# the plan's literal field list: the plan requires that a `design_source`
# that fails to resolve produce "None (with a diagnostic)... never a silent
# empty string standing in for 'no design context'" but does not say where
# that diagnostic lives. This module follows this repo's own established
# convention for exactly this situation -- `substrate.codemap.imports`'s
# `ImportClosure`/`OverlapResult`/`ReachabilityResult` all carry a
# `diagnostics: tuple[str, ...]` alongside a value that can come back empty/
# `None` for a legitimate reason -- rather than inventing a new one.

_SOURCE_EXCERPT_CAP = int(os.environ.get("FACTORY_INDEX_SLICE_CAP", "24000"))

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")


@dataclass(frozen=True)
class AcceptanceCriterionRef:
    """A flattened view of `coherence.register.register.AcceptanceCriterion`
    for the packet: `verification_kind` is the criterion's own
    `verification.kind` string, not the nested `VerificationBinding` object
    -- the fidelity reviewer only ever needs to know WHICH kind an AC
    declares, never re-validate it (that is `register.py`'s job)."""

    id: str
    criterion: str
    verification_kind: str


@dataclass(frozen=True)
class DesignSourceExcerpt:
    doc_path: str
    anchor: str | None
    excerpt: str


@dataclass(frozen=True)
class IndexSignatureView:
    """`{kind, name, signature, summary}` -- `IndexSignature.line` is
    deliberately dropped; see the module docstring."""

    kind: str
    name: str
    signature: str
    summary: str


@dataclass(frozen=True)
class TestOutcome:
    state: str  # "passed" | "failed" | "error" | "never_validated"
    stale: bool = False
    last_run_id: str | None = None
    summary: str | None = None


@dataclass(frozen=True)
class ResolvedProductionRef:
    path: str
    symbol: str
    signature: IndexSignatureView
    source_excerpt: str


@dataclass(frozen=True)
class ResolvedValidationRef:
    path: str
    test: str | None
    signature: IndexSignatureView | None
    source_excerpt: str | None
    outcome: TestOutcome | None


@dataclass(frozen=True)
class OverlapFact:
    implemented_ref: str
    verified_ref: str
    reaches: bool | None
    status: str


@dataclass(frozen=True)
class ClaimFact:
    """One commit that CLAIMED this SR. A claim is an assertion by whoever
    wrote the commit -- evidence of intent, never proof of correctness. A
    false claim is precisely the `different_behavior` finding the judge
    exists to catch, so this is presented to the judge as a claim and never
    as a verified fact."""

    sha: str
    subject: str
    changed_files: tuple[str, ...]
    declared: tuple[bool, ...]  # parallel to changed_files


@dataclass(frozen=True)
class FidelityPacket:
    """One packet per SR, built fresh for each review run -- never cached
    across source changes (the code map's own fingerprint freshness check,
    `substrate.codemap.build.is_fresh`, already guards a stale index from
    being trusted silently)."""

    sr_id: str
    statement: str
    acceptance: tuple[AcceptanceCriterionRef, ...]
    design_source: DesignSourceExcerpt | None
    profile: str
    implemented: tuple[ResolvedProductionRef, ...]
    verified: tuple[ResolvedValidationRef, ...]
    import_overlap: tuple[OverlapFact, ...]
    unresolved: tuple[ReferenceIssue, ...]
    diagnostics: tuple[str, ...] = ()
    claims: tuple[ClaimFact, ...] = ()


def _raw_meta(path: Path) -> dict:
    return frontmatter.load(str(path)).metadata


def _entries_with_index(meta: dict, field: str) -> list[tuple[int, dict]]:
    """Every dict-shaped entry declared under ``field``, paired with its
    position in the RAW (unfiltered) list -- the exact indexing
    ``resolve_sr_relations``'s own ``ReferenceIssue.index`` uses (a non-dict
    entry does not consume a separate counter; see ``relations.py``), so a
    packet entry's index always agrees with the resolver's own issue index
    when cross-checking which entries failed."""
    raw = meta.get(field)
    if not isinstance(raw, list):
        return []
    return [(i, e) for i, e in enumerate(raw) if isinstance(e, dict)]


def _declared_paths(meta: dict) -> set[str]:
    """The ``path`` of every dict-shaped ``implemented_by``/``verified_by``
    entry this SR declares -- the same "declared" definition
    ``evidence_reconciliation_review`` operates on, and deliberately NOT the
    packet's own ``implemented``/``verified`` (those are filtered down to the
    entries that structurally resolved). A declared-but-broken relation is
    still a declaration: marking its path "undeclared" would tell the judge
    the commit touched a file no one claimed to own, which is a different --
    and false -- fact. The structural reviewer owns the broken-relation
    finding; this field must not double as it."""
    return {
        str(entry["path"]).strip()
        for field in ("implemented_by", "verified_by")
        for _, entry in _entries_with_index(meta, field)
        if entry.get("path") and str(entry["path"]).strip()
    }


def _claim_facts(manifests: list[dict], sr_id: str, declared: set[str]) -> tuple[ClaimFact, ...]:
    """Every commit that claimed ``sr_id``, with each changed path marked
    against ``declared``. The commit set comes from ``review.claiming_commits``
    -- the one authority on what "claimed this SR" means -- so a packet can
    never disagree with the reconciliation reviewer about which commits are
    in the claim denominator."""
    facts: list[ClaimFact] = []
    for commit in claiming_commits(manifests, sr_id):
        paths = tuple(str(p) for p in commit.get("changed_files") or [])
        facts.append(
            ClaimFact(
                sha=str(commit.get("sha") or ""),
                subject=str(commit.get("subject") or ""),
                changed_files=paths,
                declared=tuple(path in declared for path in paths),
            )
        )
    return tuple(facts)


def _symbol_leaf(symbol: str) -> str:
    _, _, name_part = symbol.rpartition(":")
    return name_part.strip().rsplit(".", 1)[-1]


def _test_leaf(test: str) -> str:
    parts = test.split("::")
    return parts[-1].strip()


def _find_signature(index: CodeIndex, rel_path: str, leaf: str) -> dict | None:
    sigs = file_signatures(index, rel_path) or []
    return next((s for s in sigs if s["name"] == leaf), None)


def _next_signature_line(index: CodeIndex, rel_path: str, after_line: int) -> int | None:
    sigs = file_signatures(index, rel_path) or []
    later = sorted(s["line"] for s in sigs if s["line"] > after_line)
    return later[0] if later else None


def _slice_source(text: str, start_line: int, end_line: int | None) -> str:
    """Bounded body text from ``start_line`` (1-indexed, inclusive) to
    ``end_line`` (exclusive) or EOF, capped like ``render_index_slice``'s
    ``FACTORY_INDEX_SLICE_CAP`` (see the module docstring)."""
    lines = text.splitlines()
    start = max(start_line - 1, 0)
    end = (end_line - 1) if end_line is not None else len(lines)
    excerpt = "\n".join(lines[start:end])
    if len(excerpt) > _SOURCE_EXCERPT_CAP:
        excerpt = excerpt[:_SOURCE_EXCERPT_CAP]
    return excerpt


def _build_production_ref(root: Path, index: CodeIndex, path: str, symbol: str) -> ResolvedProductionRef:
    leaf = _symbol_leaf(symbol)
    sig = _find_signature(index, path, leaf)
    if sig is None:
        # resolve_sr_relations already confirmed this symbol resolves before
        # this entry ever reaches the packet builder; a miss here would mean
        # the two readers disagree, which should never happen in practice --
        # degrade to an empty view rather than raise, matching this design's
        # "never invent, but never crash on a fact gap" posture.
        return ResolvedProductionRef(
            path=path, symbol=symbol,
            signature=IndexSignatureView(kind="", name=leaf, signature="", summary=""),
            source_excerpt="",
        )
    view = IndexSignatureView(kind=sig["kind"], name=sig["name"], signature=sig["signature"], summary=sig["summary"])
    text = (root / path).read_text(encoding="utf-8", errors="replace")
    next_line = _next_signature_line(index, path, sig["line"])
    excerpt = _slice_source(text, sig["line"], next_line)
    return ResolvedProductionRef(path=path, symbol=symbol, signature=view, source_excerpt=excerpt)


def _test_outcome(manifests: list[dict], root: Path, sr_id: str, node_id: str) -> TestOutcome:
    """``verified[].outcome`` per T5.1: reflects the NEWEST manifest naming
    this exact test node id (``list_run_manifests`` already returns newest
    -first, see its own ``_run_sort_key``); falls back to SR-level
    ``load_validation`` only when no manifest names the node directly; stays
    ``never_validated`` when neither source has it -- never inferred from
    the test merely resolving structurally."""
    for manifest in manifests:
        for validation in manifest.get("validation") or []:
            if not isinstance(validation, dict):
                continue
            for entry in validation.get("requirements") or []:
                if not isinstance(entry, dict):
                    continue
                candidates = list(entry.get("tests") or [])
                for acceptance in entry.get("acceptance") or []:
                    if isinstance(acceptance, dict):
                        candidates.extend(acceptance.get("tests") or [])
                if node_id not in [str(c) for c in candidates]:
                    continue
                run_id = manifest.get("run") or manifest.get("run_id")
                error = entry.get("error")
                if error:
                    state = "error"
                elif "passed" in entry:
                    state = "passed" if entry["passed"] else "failed"
                else:
                    state = "never_validated"
                return TestOutcome(
                    state=state,
                    stale=False,
                    last_run_id=str(run_id) if run_id else None,
                    summary=str(error) if error else None,
                )
    status = load_validation(root).get(sr_id)
    if status is not None:
        return TestOutcome(state=status.state, stale=status.stale, last_run_id=None, summary=status.error)
    return TestOutcome(state="never_validated", stale=False, last_run_id=None, summary=None)


def _build_validation_ref(
    root: Path, index: CodeIndex | None, path: str, test: str | None, manifests: list[dict], sr_id: str
) -> ResolvedValidationRef:
    if test is None:
        # File-only verified_by (the design's allowance for non-pytest
        # harnesses) -- no symbol/test-node identity to resolve a signature
        # or slice a body for.
        return ResolvedValidationRef(path=path, test=None, signature=None, source_excerpt=None, outcome=None)
    assert index is not None  # a test entry always adds `path` to needed_files
    leaf = _test_leaf(test)
    sig = _find_signature(index, path, leaf)
    view: IndexSignatureView | None = None
    excerpt: str | None = None
    if sig is not None:
        view = IndexSignatureView(kind=sig["kind"], name=sig["name"], signature=sig["signature"], summary=sig["summary"])
        text = (root / path).read_text(encoding="utf-8", errors="replace")
        next_line = _next_signature_line(index, path, sig["line"])
        excerpt = _slice_source(text, sig["line"], next_line)
    outcome = _test_outcome(manifests, root, sr_id, test)
    return ResolvedValidationRef(path=path, test=test, signature=view, source_excerpt=excerpt, outcome=outcome)


def _import_overlap(
    root: Path, implemented: tuple[ResolvedProductionRef, ...], verified: tuple[ResolvedValidationRef, ...]
) -> tuple[OverlapFact, ...]:
    """One `OverlapFact` per (verified, implemented) pair, reusing
    SR-023's mechanism (`substrate.codemap.imports.compute_overlap`)
    directly. ``reaches`` is ``None`` -- never coerced to ``False``, which
    would read as a confirmed non-overlap fidelity signal it is not -- when
    ``compute_overlap``'s own status is not ``"resolved"``."""
    facts: list[OverlapFact] = []
    for v in verified:
        selection = v.test if v.test is not None else v.path
        for p in implemented:
            result = compute_overlap(root, selection, [p.path])
            reaches = None if result.status != "resolved" else bool(result.overlap)
            facts.append(
                OverlapFact(
                    implemented_ref=f"{p.path}#{p.symbol}",
                    verified_ref=f"{v.path}::{v.test}" if v.test is not None else v.path,
                    reaches=reaches,
                    status=result.status,
                )
            )
    return tuple(facts)


def _slugify(heading: str) -> str:
    """GitHub/Obsidian-style heading slug: lowercase, strip punctuation,
    collapse whitespace to hyphens. Matches this design's own `source:`
    frontmatter anchor convention (e.g. `#canonical-relations`)."""
    s = heading.strip().lower()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"\s+", "-", s)
    return s


def _excerpt_for_anchor(text: str, anchor: str) -> str | None:
    """The body of the heading section whose slug matches ``anchor`` --
    from that heading line to the next heading of equal or shallower depth,
    or EOF. ``None`` when no heading slugifies to ``anchor``."""
    lines = text.splitlines()
    start: int | None = None
    level = 0
    for i, line in enumerate(lines):
        m = _HEADING_RE.match(line)
        if m and _slugify(m.group(2)) == anchor:
            start = i
            level = len(m.group(1))
            break
    if start is None:
        return None
    end = len(lines)
    for j in range(start + 1, len(lines)):
        m = _HEADING_RE.match(lines[j])
        if m and len(m.group(1)) <= level:
            end = j
            break
    return "\n".join(lines[start:end])


def _resolve_design_source(root: Path, source: str | None) -> tuple[DesignSourceExcerpt | None, tuple[str, ...]]:
    """SR frontmatter ``source:`` (e.g.
    ``docs/superpowers/specs/...design.md#canonical-relations``) resolved to
    the referenced doc/section with a bounded excerpt -- ``(None,
    diagnostics)`` when the source doc or anchor does not resolve, never a
    silent empty excerpt standing in for "no design context" (see the
    module docstring for where the diagnostic lives)."""
    if not source or not source.strip():
        return None, ()
    doc_path_str, sep, anchor = source.partition("#")
    doc_path_str = doc_path_str.strip()
    candidate = Path(doc_path_str)
    if candidate.is_absolute() or ".." in candidate.parts:
        return None, (f"design_source: {doc_path_str!r} does not resolve inside the project",)
    full = root / candidate
    if not full.is_file():
        return None, (f"design_source: doc not found at {doc_path_str}",)
    text = full.read_text(encoding="utf-8", errors="replace")
    anchor_val = anchor if sep else None
    if anchor_val:
        excerpt = _excerpt_for_anchor(text, anchor_val)
        if excerpt is None:
            return None, (f"design_source: anchor {anchor_val!r} not found in {doc_path_str}",)
    else:
        excerpt = text
    if len(excerpt) > _SOURCE_EXCERPT_CAP:
        excerpt = excerpt[:_SOURCE_EXCERPT_CAP]
    return DesignSourceExcerpt(doc_path=doc_path_str, anchor=anchor_val, excerpt=excerpt), ()


def build_fidelity_packet(root: Path, sr_id: str) -> FidelityPacket:
    """Compose one `FidelityPacket` for `sr_id` (SR-050/AC-4, T5.1). Raises
    `ValueError` when `sr_id` is not in the register -- there is no
    meaningful packet to build for an SR that does not exist."""
    reqs = load_register(root / "requirements")
    req = next((r for r in reqs if r.id == sr_id), None)
    if req is None:
        raise ValueError(f"{sr_id}: not found in the register")
    meta = _raw_meta(req.path)

    resolution = resolve_sr_relations(root, meta)
    failed = {(issue.field, issue.index) for issue in resolution.issues}

    impl_pairs: list[tuple[str, str]] = []
    ver_pairs: list[tuple[str, str | None]] = []
    needed_files: set[str] = set()

    for i, entry in _entries_with_index(meta, "implemented_by"):
        if ("implemented_by", i) in failed:
            continue
        raw_path = str(entry.get("path") or "").strip()
        raw_symbol = str(entry.get("symbol") or "").strip()
        if not raw_path or not raw_symbol:
            continue
        impl_pairs.append((raw_path, raw_symbol))
        needed_files.add(raw_path)

    for i, entry in _entries_with_index(meta, "verified_by"):
        if ("verified_by", i) in failed:
            continue
        raw_path = str(entry.get("path") or "").strip()
        if not raw_path:
            continue
        raw_test = str(entry.get("test") or "").strip() or None
        ver_pairs.append((raw_path, raw_test))
        if raw_test is not None:
            needed_files.add(raw_path)

    index = ensure_fresh(root, files=sorted(needed_files)) if needed_files else None
    manifests = list_run_manifests(root / "evidence")

    implemented = tuple(_build_production_ref(root, index, path, symbol) for path, symbol in impl_pairs)
    verified = tuple(
        _build_validation_ref(root, index, path, test, manifests, sr_id) for path, test in ver_pairs
    )
    import_overlap = _import_overlap(root, implemented, verified)

    acceptance = tuple(
        AcceptanceCriterionRef(id=ac.id, criterion=ac.criterion, verification_kind=ac.verification.kind)
        for ac in req.acceptance
    )
    design_source, diagnostics = _resolve_design_source(root, req.source)
    profile = resolve_profile(root, f"sr:{sr_id}")

    return FidelityPacket(
        sr_id=sr_id,
        statement=req.statement,
        acceptance=acceptance,
        design_source=design_source,
        profile=profile,
        implemented=implemented,
        verified=verified,
        import_overlap=import_overlap,
        unresolved=resolution.issues,
        diagnostics=diagnostics,
        claims=_claim_facts(manifests, sr_id, _declared_paths(meta)),
    )


def packet_fingerprint(packet: FidelityPacket) -> str:
    """A stable checksum over the WHOLE packet the fidelity judge actually
    reads -- statement, acceptance, design_source, implemented (source +
    signature), verified (source + signature + outcome), import_overlap,
    claims, and profile -- deliberately mirroring
    `coherence.audit.fidelity_dispatch._fidelity_prompt`'s own `packet_view`
    dict field-for-field (that module cannot be imported from here --
    `coherence.register` imports nothing from `coherence.audit`/`factory.*`,
    see this module's own docstring on `FidelityPacket.diagnostics` and
    `coherence/register/fidelity.py`'s "Layering" section -- so the two are
    independently maintained but MUST be kept in lockstep: a field added to
    one belongs in the other too).

    This is a FOURTH, deliberately distinct staleness hash, never unified
    with the other three already in this codebase (see `coherence.gate.
    content`'s module docstring, "two different staleness concerns, two
    different functions, never conflated" -- extended here to four):

    * `coherence.register.register.content_checksum` -- statement + binding
      only (measurement-currency: has the thing a harness measures changed).
    * `coherence.gate.content.artifact_content_checksum` -- an artifact's
      raw file bytes (human-consent currency).
    * `coherence.register.overlap.content_fingerprint` -- statement +
      acceptance text only (the overlap vectorizer's own cache key).
    * this function -- everything the FIDELITY JUDGE's own prompt is built
      from, which is a strict superset of all three: source excerpts,
      signatures, test outcomes, import-overlap facts, and commit claims
      that none of the other three ever look at.

    `unresolved` and `diagnostics` are deliberately EXCLUDED: neither is
    rendered into the judge's prompt (see `_fidelity_prompt`'s own
    `packet_view`), so a change to either can never actually change what the
    judge sees, and must never falsely mark a stored review stale.
    """
    canonical = {
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
                    {
                        "state": v.outcome.state,
                        "stale": v.outcome.stale,
                        "last_run_id": v.outcome.last_run_id,
                        "summary": v.outcome.summary,
                    }
                    if v.outcome is not None
                    else None
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
        "claims": [
            {
                "sha": c.sha,
                "subject": c.subject,
                "changed_files": list(c.changed_files),
                "declared": list(c.declared),
            }
            for c in packet.claims
        ],
    }
    digest = hashlib.sha256(json.dumps(canonical, sort_keys=True).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


__all__ = [
    "AcceptanceCriterionRef",
    "ClaimFact",
    "DesignSourceExcerpt",
    "FidelityPacket",
    "IndexSignatureView",
    "OverlapFact",
    "ResolvedProductionRef",
    "ResolvedValidationRef",
    "TestOutcome",
    "build_fidelity_packet",
    "packet_fingerprint",
]
