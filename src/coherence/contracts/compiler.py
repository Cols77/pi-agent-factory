"""Deterministic local contract compilation (optional-contract-artifacts task 4).

Turns a parsed ``ContractClosure`` into a normalized dependency closure in which
every present, resolvable contract declaration carries two fingerprints:

* ``content_fingerprint``: the artifact file's own hash (``sha256:...``).
* ``closure_fingerprint``: the artifact file's hash folded together with every
  transitive local dependency's fingerprint, so a change to a referenced wire
  schema invalidates a root contract's compiled fingerprint even when the root
  file itself did not change (SR-075 / AC-1).

The compiler is deterministic (iterate ``closure.declarations`` in order, never
re-glob the filesystem, sort every emitted edge/node/dependency list), and
fail-closed: syntactically broken ``$ref`` values, non-local reference schemes,
and dependency cycles are reported as diagnostics -- never silently followed,
silently dropped, or resolved through retrieval (SR-075 / AC-3).

No semantic schema validation happens here: JSON is parsed only to locate string
``$ref`` values so their targets can be resolved and fingerprinted. Domain
semantics are the responsibility of project gates and declared consumer tests.
"""

from __future__ import annotations

import json
import posixpath
import re
from pathlib import Path
from typing import Any

from coherence.contracts.model import (
    CODE_DECLARATION_INVALID,
    CODE_FILE_MISSING,
    CODE_REFERENCE_BROKEN,
    CODE_REFERENCE_CYCLE,
    ContractClosure,
    ContractDeclaration,
    ContractDiagnostic,
    ContractEdge,
    ContractNode,
)
from coherence.planning.paths import safe_resolve
from substrate.freshness.fingerprint import fingerprint_file, sha256_bytes

# Edge vocabulary frozen for downstream trace graph consumers (task 5).
CONTRACT_EDGE_KINDS: tuple[str, ...] = (
    "defines",
    "consumed_by",
    "validated_by",
    "validates_against",
    "references",
)

_SCHEME_URL_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*://")
_SCHEME_URI_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*:")


def compile_contracts(closure: ContractClosure, root: Path) -> ContractClosure:
    """Compile ``closure`` into a normalized, fingerprinted dependency closure.

    Only declarations that are present and resolvable as files are compiled into
    nodes; a declaration the catalog kept but whose file is missing is skipped and
    reported with `CODE_FILE_MISSING`. Diagnostics are accumulated from the input
    closure plus everything the compiler discovers, and are re-sorted so the
    resulting closure is deterministic regardless of traversal order.
    """
    if not closure.present:
        return closure

    root = Path(root)
    diagnostics = list(closure.diagnostics)
    declared_by_path: dict[str, ContractDeclaration] = {
        declaration.path: declaration for declaration in closure.declarations
    }

    nodes: list[ContractNode] = []
    edges: list[ContractEdge] = []
    edge_keys: set[tuple[str, str, str]] = set()

    def add_edge(src: str, dst: str, kind: str) -> None:
        key = (src, dst, kind)
        if key not in edge_keys:
            edge_keys.add(key)
            edges.append(ContractEdge(src=src, dst=dst, kind=kind))

    def add_diagnostic(code: str, declaration_id: str, message: str) -> None:
        diagnostics.append(ContractDiagnostic(code=code, declaration_id=declaration_id, message=message))

    present: dict[str, Path] = {}
    for declaration in closure.declarations:
        resolved = _try_resolve(root, declaration.path)
        if resolved is None or not resolved.is_file():
            add_diagnostic(
                CODE_FILE_MISSING,
                declaration.id,
                f"contract {declaration.id!r} declares a path with no file at the "
                f"resolved location (declared path {declaration.path!r})",
            )
            continue
        present[declaration.id] = resolved
        declared_by_path.setdefault(_relpath(root, resolved), declaration)

    by_id = {declaration.id: declaration for declaration in closure.declarations}

    content_fingerprints: dict[str, str] = {}
    refs_by_id: dict[str, list[str]] = {}
    for declaration_id, resolved in present.items():
        fingerprint = fingerprint_file(
            name=f"contract:{declaration_id}", path=resolved, repo_root=root
        )
        content_fingerprints[declaration_id] = fingerprint.digest
        if by_id[declaration_id].kind == "json_schema":
            refs_by_id[declaration_id] = _collect_file_refs(
                declaration_id, resolved, declared_by_path, add_edge, add_diagnostic, root
            )
        else:
            refs_by_id[declaration_id] = []

    for declaration_id in present:
        relation_edges(by_id[declaration_id], add_edge)

    visiting: set[str] = set()
    memo: dict[str, tuple[dict[str, str], str]] = {}

    def compute(declaration_id: str) -> tuple[dict[str, str], str] | None:
        """Return (dep_path -> fingerprint map, closure_fingerprint) for a node."""
        if declaration_id in memo:
            return memo[declaration_id]
        if declaration_id in visiting:
            return None  # cycle already reported at the re-entry call site
        visiting.add(declaration_id)
        deps: dict[str, str] = {}
        for ref_path in refs_by_id.get(declaration_id, ()):
            owner = declared_by_path.get(ref_path)
            if owner is not None:
                if owner.id in visiting:
                    add_diagnostic(
                        CODE_REFERENCE_CYCLE,
                        declaration_id,
                        f"contract {declaration_id!r} references {owner.id!r}, which "
                        f"forms a dependency cycle; the cyclic edge is not followed",
                    )
                    continue
                sub = compute(owner.id)
                if sub is None:
                    continue
                sub_deps, sub_closure = sub
                for dep_path, dep_fingerprint in sub_deps.items():
                    deps.setdefault(dep_path, dep_fingerprint)
                _merge_dep(deps, ref_path, sub_closure)
            else:
                _merge_dep(
                    deps,
                    ref_path,
                    fingerprint_file(
                        name=f"contract-file:{ref_path}",
                        path=_path_from_relative(root, ref_path),
                        repo_root=root,
                    ).digest,
                )
        visiting.discard(declaration_id)
        ordered = tuple(sorted(deps))
        if ordered:
            seed = content_fingerprints[declaration_id] + "".join(deps[dep] for dep in ordered)
            closure_fingerprint = sha256_bytes(seed.encode("utf-8"))
        else:
            # No dependencies to fold: the node carries only its own content hash.
            closure_fingerprint = content_fingerprints[declaration_id]
        result = (deps, closure_fingerprint)
        memo[declaration_id] = result
        return result

    for declaration_id in present:
        deps_map, closure_fingerprint = compute(declaration_id)  # type: ignore[misc]
        declaration = by_id[declaration_id]
        nodes.append(
            ContractNode(
                id=declaration_id,
                path=declaration.path,
                kind=declaration.kind,
                status=declaration.status,
                content_fingerprint=content_fingerprints[declaration_id],
                closure_fingerprint=closure_fingerprint,
                deps=tuple(sorted(deps_map)),
            )
        )

    nodes.sort(key=lambda node: node.id)
    edges.sort(key=lambda edge: (edge.src, edge.dst, edge.kind))
    diagnostics.sort(key=lambda item: (item.declaration_id, item.code, item.message))

    return ContractClosure(
        present=True,
        declarations=closure.declarations,
        diagnostics=tuple(diagnostics),
        nodes=tuple(nodes),
        edges=tuple(edges),
    )


def relation_edges(declaration: ContractDeclaration, add_edge: Any) -> None:
    """Emit the declared-relationship edges for one compiled declaration."""
    validators = declaration.validates_against
    if validators is not None and validators.kind == "contract":
        add_edge(declaration.id, validators.target, "validates_against")
        add_edge(validators.target, declaration.id, "validated_by")
    for consumer in declaration.consumers:
        add_edge(declaration.id, f"{consumer.kind}:{consumer.target}", "consumed_by")
    authority = declaration.authority
    if authority is not None and authority.kind == "spec":
        add_edge(f"spec:{authority.target}", declaration.id, "defines")


def _merge_dep(deps: dict[str, str], path: str, fingerprint: str) -> None:
    deps.setdefault(path, fingerprint)


def _collect_file_refs(
    declaration_id: str,
    resolved: Path,
    declared_by_path: dict[str, ContractDeclaration],
    add_edge: Any,
    add_diagnostic: Any,
    root: Path,
) -> list[str]:
    """Parse a json_schema file and return its resolved local file dependencies.

    Invalid JSON yields a syntax diagnostic and no dependency traversal (only the
    file's own content hash remains). Each valid non-fragment ``$ref`` is resolved
    and de-duplicated by resolved path; broken refs become diagnostics, never edges.
    """
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as error:
        add_diagnostic(
            CODE_DECLARATION_INVALID,
            declaration_id,
            f"contract {declaration_id!r} is declared `json_schema` but its content "
            f"is not valid JSON: syntax/parse failure ({error}); only its content "
            "hash is recorded and no dependency references are traversed",
        )
        return []

    seen: set[str] = set()
    resolved_refs: list[str] = []
    for ref in _iter_json_pointer_refs(payload):
        relative = _resolve_local_ref(declaration_id, ref, resolved, declared_by_path, add_edge, add_diagnostic, root)
        if relative is not None and relative not in seen:
            seen.add(relative)
            resolved_refs.append(relative)
    return resolved_refs


def _iter_json_pointer_refs(value: object) -> list[str]:
    """Breadth-first collect every ``$ref`` string anywhere in a JSON value."""
    refs: list[str] = []
    stack: list[object] = [value]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            for key, child in item.items():
                if key == "$ref" and isinstance(child, str):
                    refs.append(child)
                else:
                    stack.append(child)
        elif isinstance(item, list):
            stack.extend(item)
    return refs


def _resolve_local_ref(
    declaration_id: str,
    ref: str,
    resolved: Path,
    declared_by_path: dict[str, ContractDeclaration],
    add_edge: Any,
    add_diagnostic: Any,
    root: Path,
) -> str | None:
    """Resolve one ``$ref`` to a repository-relative path, or None when broken.

    A local file ``$ref`` resolves relative to the DIRECTORY of the file that
    contains it (RFC 3986), never the repository root. The raw ref string is
    screened first -- before any base-relative joining -- for network URLs and
    non-file URI schemes and for rooted/absolute and UNC forms. In-tree parent
    ``..`` components in a *provided* ``$ref`` are legal (SR-075) and are
    collapsed lexically against the containing file's directory; only a ``..``
    that escapes the repository root is rejected. After lexical collapse the
    candidate is safety-checked and resolved via ``safe_resolve``; a reparse
    escape or non-file target is `CODE_REFERENCE_BROKEN`.
    """
    text = ref.strip()
    if text.startswith("#"):
        return None
    if _has_non_local_scheme(text):
        add_diagnostic(
            CODE_REFERENCE_BROKEN,
            declaration_id,
            f"contract {declaration_id!r} local $ref {ref!r} names an absolute URI or "
            "network URL, not an in-repository file; the reference is rejected",
        )
        return None
    if _raw_ref_is_rooted_or_unc(text):
        add_diagnostic(
            CODE_REFERENCE_BROKEN,
            declaration_id,
            f"contract {declaration_id!r} local $ref {ref!r} is an absolute or UNC "
            "path, not a repository-relative path; the reference is rejected",
        )
        return None

    # Resolve the ref against the directory of the containing contract file.
    containing_rel = _relpath(root, resolved)
    base_dir = posixpath.dirname(containing_rel)
    joined = text if not base_dir else f"{base_dir}/{text}"
    candidate_repo_rel = posixpath.normpath(joined.replace("\\", "/"))

    safety = _candidate_safety_error(candidate_repo_rel)
    if safety is not None:
        add_diagnostic(
            CODE_REFERENCE_BROKEN,
            declaration_id,
            f"contract {declaration_id!r} local $ref {ref!r} is an unsafe repository "
            f"path: {safety}",
        )
        return None

    resolved_target = _try_resolve(root, candidate_repo_rel)
    if resolved_target is None:
        add_diagnostic(
            CODE_REFERENCE_BROKEN,
            declaration_id,
            f"contract {declaration_id!r} local $ref {ref!r} does not resolve inside "
            "the repository root (escapes through a symlink, junction, mount point "
            "or other reparse point); the reference is rejected",
        )
        return None
    if not resolved_target.is_file():
        add_diagnostic(
            CODE_REFERENCE_BROKEN,
            declaration_id,
            f"contract {declaration_id!r} local $ref {ref!r} resolves to a missing or "
            "non-file target; the reference is rejected",
        )
        return None
    relative = candidate_repo_rel
    owner = declared_by_path.get(relative)
    if owner is not None:
        add_edge(declaration_id, owner.id, "references")
    else:
        add_edge(declaration_id, f"code:{relative}", "references")
    return relative


def _has_non_local_scheme(text: str) -> bool:
    """True when ``text`` is a network URL or an absolute URI with a scheme."""
    if _SCHEME_URL_RE.match(text):
        return True
    # A scheme is any leading ``[A-Za-z][A-Za-z0-9+.-]*:`` (http, https, file, ftp,
    # urn, ...); Windows drive roots (``C:\``) also match and are unsafe anyway.
    return bool(_SCHEME_URI_RE.match(text))


def _raw_ref_is_rooted_or_unc(text: str) -> bool:
    """True when a raw ``$ref`` is an absolute or UNC path (still unsafe)."""
    forward = text.replace("\\", "/")
    return forward.startswith("//") or forward.startswith("/")


def _candidate_safety_error(candidate: str) -> str | None:
    """Reason a lexically-normalized repo-relative candidate is unsafe, or None.

    The lexical collapse already removed harmless in-tree ``///./`` / ``..``, so
    the remaining threats are NUL/drive/UNC/rooted forms, empty paths, and a
    leading ``..`` that proves the parent traversal escaped the repository root.
    """
    if candidate == "":
        return "path is empty or whitespace-only; a repository-relative path is required"
    if "\x00" in candidate:
        return "path contains a NUL character, which is not a valid path"
    if candidate.startswith("//"):
        return "path is a UNC absolute path; a repository-relative path is required"
    if candidate.startswith("/"):
        return "path is rooted/absolute; a repository-relative path is required"
    if len(candidate) >= 2 and candidate[0].isalpha() and candidate[1] == ":":
        return "path is drive-rooted (absolute); a repository-relative path is required"
    if candidate == ".." or candidate.startswith("../"):
        return (
            "path contains a parent '..' component that escapes the repository root; "
            "the reference is rejected"
        )
    return None


def _try_resolve(root: Path, relative: str) -> Path | None:
    """Resolve a repository-relative path under ``root``, or None when unsafe."""
    candidate = root / relative.replace("\\", "/")
    try:
        return safe_resolve(root, candidate)
    except (OSError, RuntimeError, ValueError):
        return None


def _relpath(root: Path, absolute: Path) -> str:
    try:
        return absolute.absolute().resolve().relative_to(root.absolute().resolve()).as_posix()
    except (OSError, ValueError):
        return absolute.as_posix()


def _path_from_relative(root: Path, relative: str) -> Path:
    return (root / relative).resolve()


__all__ = ["CONTRACT_EDGE_KINDS", "compile_contracts"]