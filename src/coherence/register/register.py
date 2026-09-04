from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

import frontmatter

# `binding` is deliberately absent: a requirement may be agreed in substance
# before its measurement is decided. The absence of a binding IS the proposed
# state -- there is no status field that could disagree with the content.
_REQUIRED = ("id", "title", "statement", "domain")

_VERIFICATION_KINDS = ("test_marker", "harness", "manual")


@dataclass(frozen=True)
class Binding:
    experiment: str
    metric: str
    assert_expr: str
    # A requirement may have a decided measurement before its instrument exists.
    # `None` is the "no harness named yet" state -- a WARNING, never a blocker.
    harness: str | None = None
    trials: int = 1
    window: dict | None = None
    cadence: str = "every_iteration"


@dataclass(frozen=True)
class VerificationBinding:
    """How a single acceptance criterion is satisfied.

    `test_marker` and `harness` require a non-blank `ref`; `manual` requires a
    non-blank `reason` instead and is satisfied only via a `human_review` decision.
    """

    kind: str
    ref: str | None = None
    reason: str | None = None


@dataclass(frozen=True)
class AcceptanceCriterion:
    """One individually addressable, verifiable criterion on a requirement."""

    id: str
    criterion: str
    verification: VerificationBinding

    def qualified_id(self, req_id: str) -> str:
        """The `<SR-ID>/<AC-ID>` address form, e.g. `SR-025/AC-3`."""
        return f"{req_id}/{self.id}"


@dataclass(frozen=True)
class Requirement:
    id: str
    title: str
    statement: str
    domain: str
    upstream: list[str]
    binding: Binding | None
    body: str
    path: Path
    checksum: str | None = None
    source: str | None = None
    acceptance: tuple[AcceptanceCriterion, ...] = ()
    # SR-057: a flat list of ids from ANY artifact family this requirement
    # declares itself to relate to/cover -- `spec:<id>`-prefixed for a spec
    # (matching the trace graph's own `spec:<id>` node id), bare `SR-NNN`/
    # `FEAT-NNN` otherwise (matching those node ids exactly, no prefix).
    # Deliberately a separate field from `upstream`, which SR-001/AC-3 already
    # scopes to requirement-to-requirement dependency relations only -- see
    # this dataclass's `upstream` field and SR-057.md's body for why the two
    # are not merged.
    relates_to: list[str] = field(default_factory=list)


def _parse_binding(raw: dict) -> Binding:
    harness = raw.get("harness")
    return Binding(
        experiment=str(raw["experiment"]),
        metric=str(raw["metric"]),
        assert_expr=str(raw["assert"]),
        harness=str(harness) if harness else None,
        trials=int(raw.get("trials", 1)),
        window=raw.get("window"),
        cadence=str(raw.get("cadence", "every_iteration")),
    )


def _parse_acceptance(path: Path, raw: object) -> tuple[AcceptanceCriterion, ...]:
    if not isinstance(raw, list):
        raise ValueError(f"{path.name}: acceptance: must be a list, got {type(raw).__name__}")

    criteria: list[AcceptanceCriterion] = []
    seen_ids: set[str] = set()
    for index, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise ValueError(f"{path.name}: acceptance[{index}]: entry must be a mapping")

        raw_id = entry.get("id")
        if raw_id is None or not str(raw_id).strip():
            raise ValueError(f"{path.name}: acceptance[{index}]: missing required field 'id'")
        entry_id = str(raw_id)
        if entry_id in seen_ids:
            raise ValueError(f"{path.name}: acceptance[{entry_id}]: duplicate criterion id")
        seen_ids.add(entry_id)

        criterion = entry.get("criterion")
        if criterion is None or not str(criterion).strip():
            raise ValueError(
                f"{path.name}: acceptance[{entry_id}]: missing required field 'criterion'"
            )

        verification_raw = entry.get("verification")
        if not isinstance(verification_raw, dict):
            raise ValueError(
                f"{path.name}: acceptance[{entry_id}]: missing required field 'verification'"
            )

        kind = verification_raw.get("kind")
        if kind not in _VERIFICATION_KINDS:
            raise ValueError(
                f"{path.name}: acceptance[{entry_id}]: verification.kind must be one of "
                f"{_VERIFICATION_KINDS}, got {kind!r}"
            )

        if kind == "manual":
            reason = verification_raw.get("reason")
            if reason is None or not str(reason).strip():
                raise ValueError(
                    f"{path.name}: acceptance[{entry_id}]: verification.kind=manual requires "
                    "a non-blank 'reason'"
                )
            verification = VerificationBinding(kind=kind, reason=str(reason).strip())
        else:
            ref = verification_raw.get("ref")
            if ref is None or not str(ref).strip():
                raise ValueError(
                    f"{path.name}: acceptance[{entry_id}]: verification.kind={kind} requires "
                    "a non-blank 'ref'"
                )
            verification = VerificationBinding(kind=kind, ref=str(ref).strip())

        criteria.append(
            AcceptanceCriterion(id=entry_id, criterion=str(criterion).strip(), verification=verification)
        )
    return tuple(criteria)


def parse_requirement(path: Path) -> Requirement:
    post = frontmatter.load(str(path))
    meta = post.metadata
    missing = [k for k in _REQUIRED if k not in meta]
    if missing:
        raise ValueError(f"{path.name}: missing required field(s): {missing}")
    upstream = meta.get("upstream") or []
    if isinstance(upstream, str):
        upstream = [upstream]
    relates_to = meta.get("relates_to") or []
    if isinstance(relates_to, str):
        relates_to = [relates_to]
    checksum = meta.get("checksum")
    source = meta.get("source")
    acceptance = _parse_acceptance(path, meta["acceptance"]) if "acceptance" in meta else ()
    return Requirement(
        id=str(meta["id"]),
        title=str(meta["title"]),
        statement=str(meta["statement"]),
        domain=str(meta["domain"]),
        upstream=[str(u) for u in upstream],  # type: ignore[union-attr]
        binding=_parse_binding(meta["binding"]) if "binding" in meta else None,  # type: ignore[arg-type]
        body=post.content,
        path=path,
        checksum=str(checksum) if checksum else None,
        source=str(source) if source else None,
        acceptance=acceptance,
        relates_to=[str(r) for r in relates_to],  # type: ignore[union-attr]
    )


def content_checksum(req: Requirement) -> str:
    # cadence is intentionally excluded: it is scheduling (how often the SR runs),
    # not a metric input, so changing it must not stale the requirement.
    b = req.binding
    if b is None:
        raise ValueError(f"{req.id}: proposed requirement has no binding to checksum")
    canonical = "\n".join(
        [
            req.statement.strip(),
            b.harness or "",
            b.experiment,
            b.metric,
            b.assert_expr,
            str(b.trials),
            repr(b.window),
        ]
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def is_checksum_current(req: Requirement) -> bool:
    # A proposed requirement has no binding, so there is nothing for a checksum to
    # go stale against. Returning False would print STALE forever.
    if req.binding is None:
        return True
    return req.checksum is not None and req.checksum == content_checksum(req)


def _missing_wikilinks(ids: list[str], body: str) -> tuple[str, ...]:
    """Ids with no ``[[id]]``/``[[id|...]]`` mirror anywhere in ``body``, in
    declared order, deduplicated.

    The shared matching logic behind both ``missing_upstream_wikilinks``
    (SR-001/AC-3, ``req.upstream`` only) and ``missing_relation_wikilinks``
    (SR-057/AC-1, ``req.upstream`` and ``req.relates_to`` together) -- see
    ``missing_upstream_wikilinks``'s docstring for the plain-vs-pipe-alias
    rationale, which applies identically here.
    """
    seen: set[str] = set()
    missing: list[str] = []
    for uid in ids:
        if uid in seen:
            continue
        seen.add(uid)
        if f"[[{uid}]]" not in body and f"[[{uid}|" not in body:
            missing.append(uid)
    return tuple(missing)


def missing_upstream_wikilinks(req: Requirement) -> tuple[str, ...]:
    """Ids in ``req.upstream`` that carry no ``[[id]]`` wikilink anywhere in
    ``req.body``, in declared order, deduplicated.

    Checks one direction only: every declared relation is mirrored as a
    wikilink. It does not check the reverse (that every wikilink in the body
    corresponds to a declared relation) -- a body routinely and legitimately
    wikilinks other nodes for narrative context (see SR-001) that are not
    upstream dependencies. Nor does it check that an upstream id resolves to
    a real requirement; pair with a register-membership check for that.

    Recognises both the plain (``[[SR-050]]``) and Obsidian pipe-alias
    (``[[SR-050|display title]]``) wikilink forms as a mirror -- this repo
    uses the alias form routinely for ``source:`` links, so a bare
    ``[[id]]`` search would false-positive "missing" the moment an upstream
    mirror uses it too.

    Unaffected by SR-057: this function's contract, signature, and behaviour
    are exactly what they were before ``relates_to`` existed -- it still
    reads only ``req.upstream``. ``missing_relation_wikilinks`` below is the
    generalization that also covers ``req.relates_to``; this function is now
    that check's ``upstream`` half, implemented via the shared
    ``_missing_wikilinks`` helper rather than its own copy of the matching
    logic.
    """
    return _missing_wikilinks(req.upstream, req.body)


def missing_relates_to_wikilinks(req: Requirement) -> tuple[str, ...]:
    """Ids in ``req.relates_to`` that carry no ``[[id]]``/``[[id|...]]``
    wikilink anywhere in ``req.body`` -- SR-057/AC-1's new half of the
    generalized mirror check, matched by the exact same rules as
    ``missing_upstream_wikilinks`` (see its docstring) via the shared
    ``_missing_wikilinks`` helper. ``req.relates_to`` may reference any
    artifact family (a bare ``SR-NNN``/``FEAT-NNN`` id, or a ``spec:<id>``
    id matching the trace graph's own spec node id) -- the mirror is checked
    against the literal declared string either way, with no per-kind
    transform.
    """
    return _missing_wikilinks(req.relates_to, req.body)


def missing_relation_wikilinks(req: Requirement) -> tuple[str, ...]:
    """SR-057/AC-1: every id a requirement declares via EITHER ``upstream``
    or ``relates_to`` must be mirrored as a wikilink somewhere in its body,
    checked the same way ``missing_upstream_wikilinks`` already checks
    ``upstream`` alone (SR-001/AC-3). Returns the still-missing ids from
    both fields combined -- ``upstream``'s own declared order first, then
    ``relates_to``'s, deduplicated across both fields together (an id
    declared in both, once mirrored, is not reported twice; declared in both
    and never mirrored, is reported once).

    ``upstream`` itself stays exactly as narrow as SR-001/AC-3 already
    scoped it (requirement-to-requirement dependency only) -- this function
    only broadens the wikilink CHECK to a second field, it does not
    repurpose or widen what ``upstream`` may reference.
    """
    return _missing_wikilinks([*req.upstream, *req.relates_to], req.body)


def load_register(requirements_dir: Path) -> list[Requirement]:
    if not requirements_dir.exists():
        return []
    return sorted(
        (parse_requirement(p) for p in requirements_dir.glob("SR-*.md")),
        key=lambda r: r.id,
    )


def get_requirement(reqs: list[Requirement], req_id: str) -> Requirement | None:
    return next((r for r in reqs if r.id == req_id), None)


__all__ = [
    "AcceptanceCriterion",
    "Binding",
    "Requirement",
    "VerificationBinding",
    "content_checksum",
    "get_requirement",
    "is_checksum_current",
    "load_register",
    "missing_relates_to_wikilinks",
    "missing_relation_wikilinks",
    "missing_upstream_wikilinks",
    "parse_requirement",
]
