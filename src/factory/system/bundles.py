"""Declared feature-scope bundle loading (design §3.3).

A bundle is an authored file that names its members by exact ref. It
declares membership only -- no status, no claims, no rationale -- and is
validated against `system_bundle.schema.json`, which rejects anything else
at the top level. Mirrors the existing requirements-register convention
(`factory.requirements.register.load_register`): the directory is a
parameter, never hardcoded, and an absent directory is a legitimate state
rather than an error.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from factory.system.models import (
    BundleDeclaration,
    ClaimClass,
    CitationKind,
    Freshness,
    FreshnessState,
    SystemCitation,
    SystemClaim,
    SystemScopeRef,
)
from factory.validation.schema_validator import SCHEMA_DIR, validate

_SCHEMA = SCHEMA_DIR / "system_bundle.schema.json"

# The only member kinds a bundle may declare (design §3.3).
_MEMBER_KINDS = ("spec", "plan", "task", "sr")


def _parse_member_ref(raw_ref: str) -> SystemScopeRef | None:
    """Parse a raw member ref string, or return None if it does not resolve.

    A member is well-formed only if it has a recognized `spec:`/`plan:`/
    `task:`/`sr:` prefix and a non-empty identifier after it. Anything else
    does not resolve (design §3.3) and is reported `missing` by the caller
    rather than raised, so one bad member never drops the whole bundle.
    """
    kind, sep, identifier = raw_ref.partition(":")
    if not sep or kind not in _MEMBER_KINDS or not identifier:
        return None
    return SystemScopeRef(kind=kind, ref=raw_ref)


def load_bundle(bundles_dir: Path, bundle_id: str) -> BundleDeclaration:
    """Load and validate a single declared bundle by id.

    Raises `FileNotFoundError` if the bundle file does not exist, and
    `ValueError` if it fails schema validation (e.g. carries a narrative
    field, or duplicate members). A member ref that is merely unresolvable
    does NOT raise -- it is reported `missing` in `unresolved` instead.
    """
    path = bundles_dir / f"{bundle_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"bundle not found: {bundle_id!r} ({path})")

    raw_text = path.read_text(encoding="utf-8")
    raw = json.loads(raw_text)

    errors = validate(raw, _SCHEMA)
    if errors:
        raise ValueError(f"invalid bundle {bundle_id!r}: {'; '.join(errors)}")

    members: list[SystemScopeRef] = []
    unresolved: list[SystemClaim] = []
    for raw_ref in raw["members"]:
        parsed = _parse_member_ref(raw_ref)
        if parsed is None:
            unresolved.append(
                SystemClaim(
                    kind=ClaimClass.MISSING,
                    text=raw_ref,
                    freshness=Freshness(
                        state=FreshnessState.NA,
                        reason="bundle member ref did not resolve",
                    ),
                )
            )
        else:
            members.append(parsed)

    citation = SystemCitation(
        kind=CitationKind.BUNDLE,
        path=str(path),
        sha256=hashlib.sha256(raw_text.encode("utf-8")).hexdigest(),
        anchor=None,
    )

    return BundleDeclaration(
        id=str(raw["id"]),
        label=str(raw["label"]),
        members=members,
        unresolved=unresolved,
        citation=citation,
    )


def list_bundles(bundles_dir: Path) -> list[BundleDeclaration]:
    """List every declared bundle in `bundles_dir`.

    An absent directory is a legitimate state, not an error: this returns an
    empty list and never creates the directory as a side effect of reading.
    """
    if not bundles_dir.exists():
        return []
    return [load_bundle(bundles_dir, p.stem) for p in sorted(bundles_dir.glob("*.json"))]
