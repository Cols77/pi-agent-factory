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
from dataclasses import dataclass
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

# The only member kinds a bundle may declare (design §3.3, extended by SP-A).
# `adr` refs are id-based (`adr:ADR-0001`), matching `sr:`/`task:` and unlike
# `spec:`/`plan:`, which are repo-relative paths. Resolution to a file happens
# in the caller, never here -- this only parses the ref.
_MEMBER_KINDS = ("spec", "plan", "task", "sr", "adr")


class BundleIdMismatchError(ValueError):
    """A bundle file's declared `id` does not match its filename stem.

    Bundle files must be named `<id>.json` -- this is what lets a
    `bundle:<id>` scope ref resolve exactly rather than by filesystem
    happenstance (design SS5.1). Deliberately a `ValueError`, not a
    `FileNotFoundError`: the file exists and is otherwise schema-legal, so
    treating it as "not found" would let it vanish from `list_bundles`
    without a trace. It is a `ValueError` subclass so the existing
    schema/parse-failure handling in `list_bundles` still catches it.
    """


def _parse_member_ref(raw_ref: str) -> SystemScopeRef | None:
    """Parse a raw member ref string, or return None if it does not resolve.

    A member is well-formed only if it has a recognized `spec:`/`plan:`/
    `task:`/`sr:`/`adr:` prefix and a non-empty identifier after it. Anything
    else does not resolve (design §3.3) and is reported `missing` by the
    caller rather than raised, so one bad member never drops the whole bundle.
    """
    kind, sep, identifier = raw_ref.partition(":")
    if not sep or kind not in _MEMBER_KINDS or not identifier:
        return None
    return SystemScopeRef(kind=kind, ref=raw_ref)


def load_bundle(bundles_dir: Path, bundle_id: str) -> BundleDeclaration:
    """Load and validate a single declared bundle by id.

    Raises `FileNotFoundError` if the bundle file does not exist. Raises
    `ValueError` if it fails schema validation (e.g. carries a narrative
    field, or duplicate members). Raises `BundleIdMismatchError` (a
    `ValueError` subclass) if the file exists, is schema-legal, but its
    declared `id` does not exactly equal `bundle_id` -- e.g. only the case
    differs, which some filesystems resolve to the same file, or the file is
    simply misnamed. Either way the bundle is not reachable under the
    requested id (design SS5.1: scope resolution is exact only, never
    fuzzy), but it is a distinct, visible failure rather than a silent
    "not found" -- callers that list bundles (`list_bundle_errors`) surface
    it instead of erasing it. A member ref that is merely unresolvable does
    NOT raise -- it is reported `missing` in `unresolved` instead.
    """
    path = bundles_dir / f"{bundle_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"bundle not found: {bundle_id!r} ({path})")

    raw_text = path.read_text(encoding="utf-8")
    raw = json.loads(raw_text)

    errors = validate(raw, _SCHEMA)
    if errors:
        raise ValueError(f"invalid bundle {bundle_id!r}: {'; '.join(errors)}")

    if str(raw["id"]) != bundle_id:
        raise BundleIdMismatchError(
            f"bundle file {path} declares id={raw['id']!r}, but its filename "
            f"requires id={bundle_id!r} (bundle files must be named <id>.json)"
        )

    citation = SystemCitation(
        kind=CitationKind.BUNDLE,
        path=str(path),
        sha256=hashlib.sha256(raw_text.encode("utf-8")).hexdigest(),
        anchor=None,
    )

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
                    # Points at the bundle file that declared the bad ref --
                    # not evidence that the ref itself resolves to anything,
                    # but a real, checkable pointer to where the claim
                    # originated (previously carried no citation at all).
                    citations=[citation],
                )
            )
        else:
            members.append(parsed)

    return BundleDeclaration(
        id=str(raw["id"]),
        label=str(raw["label"]),
        members=members,
        unresolved=unresolved,
        citation=citation,
    )


@dataclass(frozen=True)
class BundleLoadError:
    """A bundle file that exists but failed to load, and why.

    Reported by `list_bundle_errors` so a malformed or misnamed bundle is
    visible to an operator (e.g. via `factory.system scope`) instead of
    silently vanishing -- design SS8: a failure degrades only the affected
    scope, but it must still be reported.
    """

    path: Path
    bundle_id: str
    error: str


def _load_all(bundles_dir: Path) -> tuple[list[BundleDeclaration], list[BundleLoadError]]:
    if not bundles_dir.exists():
        return [], []
    successes: list[BundleDeclaration] = []
    failures: list[BundleLoadError] = []
    for path in sorted(bundles_dir.glob("*.json")):
        try:
            successes.append(load_bundle(bundles_dir, path.stem))
        except (OSError, ValueError) as exc:
            # json.JSONDecodeError is a ValueError subclass, already covered.
            failures.append(BundleLoadError(path=path, bundle_id=path.stem, error=str(exc)))
    return successes, failures


def list_bundles(bundles_dir: Path) -> list[BundleDeclaration]:
    """List every declared bundle in `bundles_dir`.

    An absent directory is a legitimate state, not an error: this returns an
    empty list and never creates the directory as a side effect of reading.

    A single malformed bundle file (invalid JSON, a schema violation, or an
    id/filename mismatch) must not abort the whole listing -- design SS8:
    failures degrade only the affected scope. That bundle is skipped here;
    every other bundle still loads. The skipped file is not erased, though:
    see `list_bundle_errors` for the second channel that reports it.
    """
    successes, _ = _load_all(bundles_dir)
    return successes


def list_bundle_errors(bundles_dir: Path) -> list[BundleLoadError]:
    """Every bundle file in `bundles_dir` that failed to load, and why.

    The companion to `list_bundles`: that function only returns what loaded
    cleanly, so a broken file would otherwise leave no trace at all. Callers
    (`factory.system scope`) surface these so an operator who typos a bundle
    file gets feedback instead of silence.
    """
    _, failures = _load_all(bundles_dir)
    return failures


def bundles_containing(repo_root: Path, ref: str) -> list[str]:
    """Bundle ids that declare `ref` as a member, deterministic (load) order.

    Membership is many-to-many, so a ref may appear in several bundles. The
    match is exact on the ref string, or -- for `spec:`/`plan:` members whose
    ref is a repo-relative path -- on the resolved artifact path, so two
    spellings of the same file still count as one bundle. An absent bundle
    directory or a ref in no bundle returns [].

    `member_target` is imported locally: `factory.system.coverage` imports
    this module at module level, so a top-level import here would be a cycle.
    """
    from factory.system.coverage import member_target

    target = member_target(repo_root, ref)
    containing: list[str] = []
    for bundle in list_bundles(repo_root / "bundles"):
        for m in bundle.members:
            if m.ref == ref or (target is not None and member_target(repo_root, m.ref) == target):
                containing.append(bundle.id)
                break
    return containing
