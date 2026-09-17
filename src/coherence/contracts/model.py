"""Pure model for the versioned contract catalog document (plan task 2).

The catalog is the project's own opt-in inventory of declared contract artifacts:
identity, relationships and status only. This module owns the *document* model --
parsing a catalog that is handed to it and reporting declaration-scoped findings.
Catalog *file* discovery and lexical path safety belong to the loader that calls
`parse_catalog_text`/`parse_catalog`; nothing here walks or reads the project tree.

Four rules drive the shape of this module:

* Absence is valid. `absent_closure()` is the explicit empty state a project without
  a catalog compiles to: ``present=False``, no declarations, no diagnostics.
* Presence is fail-closed. Once a catalog document is supplied, every declared entry
  is validated against the single versioned schema in
  ``src/substrate/schemas/contract_catalog.schema.json`` (explicit ``schema`` identity,
  unknown fields rejected). An entry that fails any rule is reported as a
  `ContractDiagnostic` and is *not* accepted into ``declarations`` -- the model never
  silently narrows or silently accepts.
* Diagnostics, not exceptions. Invalid input is data to be reported, not a crash:
  a later task turns these codes into blocking findings.
* Pure and deterministic. Parsing touches no filesystem and no clock; output ordering
  is derived from the document only (declarations sorted by id, diagnostics sorted by
  ``(declaration_id, code, message)``), so two runs over equal documents are equal.

Projections use explicit ``to_dict()`` methods that return JSON-serializable values
only -- no `Path`, no sets, no dataclass instances.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from substrate.validators.schema import SCHEMA_DIR, validate_against

CATALOG_SCHEMA_ID = "coherence.contract-catalog.v1"
CATALOG_SCHEMA_FILENAME = "contract_catalog.schema.json"
CATALOG_SCHEMA_PATH: Path = SCHEMA_DIR / CATALOG_SCHEMA_FILENAME

CONTRACT_KINDS: frozenset[str] = frozenset(
    {"json_schema", "fixture", "template", "ddl_manifest", "protocol", "other"}
)
CONTRACT_STATUSES: frozenset[str] = frozenset({"active", "deprecated", "draft"})
RELATION_KINDS: frozenset[str] = frozenset({"contract", "code", "test", "spec"})

DEFAULT_CONTRACT_STATUS = "active"
MISSING_DECLARATION_ID = "<unknown>"

CODE_CATALOG_INVALID = "CONTRACT_CATALOG_INVALID"
CODE_DECLARATION_DUPLICATE_ID = "CONTRACT_DECLARATION_DUPLICATE_ID"
CODE_DECLARATION_DUPLICATE_PATH = "CONTRACT_DECLARATION_DUPLICATE_PATH"
CODE_DECLARATION_INVALID = "CONTRACT_DECLARATION_INVALID"
CODE_RELATION_INVALID = "CONTRACT_RELATION_INVALID"
CODE_KIND_UNSUPPORTED = "CONTRACT_KIND_UNSUPPORTED"
CODE_STATUS_UNSUPPORTED = "CONTRACT_STATUS_UNSUPPORTED"
CODE_PATH_UNSAFE = "CONTRACT_PATH_UNSAFE"
CODE_PATH_ESCAPES_ROOT = "CONTRACT_PATH_ESCAPES_ROOT"
CODE_FILE_MISSING = "CONTRACT_DECLARED_FILE_MISSING"
CODE_CATALOG_UNREADABLE = "CONTRACT_CATALOG_UNREADABLE"
CODE_REFERENCE_BROKEN = "CONTRACT_REFERENCE_BROKEN"
CODE_REFERENCE_CYCLE = "CONTRACT_REFERENCE_CYCLE"

DIAGNOSTIC_CODES: frozenset[str] = frozenset(
    {
        CODE_CATALOG_INVALID,
        CODE_DECLARATION_DUPLICATE_ID,
        CODE_DECLARATION_DUPLICATE_PATH,
        CODE_DECLARATION_INVALID,
        CODE_RELATION_INVALID,
        CODE_KIND_UNSUPPORTED,
        CODE_STATUS_UNSUPPORTED,
        CODE_PATH_UNSAFE,
        CODE_PATH_ESCAPES_ROOT,
        CODE_FILE_MISSING,
        CODE_CATALOG_UNREADABLE,
        CODE_REFERENCE_BROKEN,
        CODE_REFERENCE_CYCLE,
    }
)

# Loaded once, at import. Parsing must not read the filesystem, and the schema is a
# package asset rather than project input, so it is read here and never again.
CATALOG_SCHEMA: dict[str, Any] = json.loads(CATALOG_SCHEMA_PATH.read_text(encoding="utf-8"))


def catalog_schema() -> dict[str, Any]:
    """Return a defensive copy of the versioned contract catalog JSON Schema."""
    return copy.deepcopy(CATALOG_SCHEMA)


@dataclass(frozen=True, slots=True)
class ContractRelation:
    """A parsed ``<kind>:<identifier>`` relationship ref declared by the catalog."""

    kind: str
    target: str
    raw: str

    @property
    def ref(self) -> str:
        """Canonical ``<kind>:<identifier>`` form (whitespace already stripped)."""
        return f"{self.kind}:{self.target}"

    def to_dict(self) -> dict[str, object]:
        return {"kind": self.kind, "target": self.target, "raw": self.raw}


@dataclass(frozen=True, slots=True)
class ContractDeclaration:
    """One accepted catalog entry. Only fully valid entries reach this type."""

    id: str
    path: str
    kind: str
    status: str
    authority: ContractRelation | None = None
    validates_against: ContractRelation | None = None
    consumers: tuple[ContractRelation, ...] = ()

    @property
    def ref(self) -> str:
        """Canonical ``contract:<id>`` reference used by trace and bundle surfaces."""
        return f"contract:{self.id}"

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "path": self.path,
            "kind": self.kind,
            "status": self.status,
            "authority": None if self.authority is None else self.authority.ref,
            "validates_against": (
                None if self.validates_against is None else self.validates_against.ref
            ),
            "consumers": [consumer.ref for consumer in self.consumers],
        }


@dataclass(frozen=True, slots=True)
class ContractDiagnostic:
    """A stable, machine-readable finding about one catalog declaration."""

    code: str
    declaration_id: str
    message: str

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "declaration_id": self.declaration_id,
            "message": self.message,
        }


@dataclass(frozen=True, slots=True)
class ContractNode:
    """One compiled contract artifact with its dependency fingerprints (task 4).

    ``content_fingerprint`` is the artifact file's own hash; ``closure_fingerprint``
    folds in every transitive local dependency's fingerprint, so a change to a
    referenced schema invalidates its referrers even when their own bytes are
    unchanged. ``deps`` is the reference-relative sorted path closure.
    """

    id: str
    path: str
    kind: str
    status: str
    content_fingerprint: str
    closure_fingerprint: str
    deps: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "path": self.path,
            "kind": self.kind,
            "status": self.status,
            "content_fingerprint": self.content_fingerprint,
            "closure_fingerprint": self.closure_fingerprint,
            "deps": list(self.deps),
        }


@dataclass(frozen=True, slots=True)
class ContractEdge:
    """A directed relationship between two compiled contract surfaces (task 4)."""

    src: str
    dst: str
    kind: str

    def to_dict(self) -> dict[str, object]:
        return {"src": self.src, "dst": self.dst, "kind": self.kind}


@dataclass(frozen=True, slots=True)
class ContractClosure:
    """The parsed catalog: presence flag, accepted declarations, findings.

    ``nodes`` and ``edges`` are populated by the deterministic compiler (a later
    task) and are empty for a freshly parsed catalog. They default to ``()`` so a
    parsed closure and ``absent_closure()`` carry no compilation state.
    """

    present: bool
    declarations: tuple[ContractDeclaration, ...] = ()
    diagnostics: tuple[ContractDiagnostic, ...] = ()
    nodes: tuple[ContractNode, ...] = ()
    edges: tuple[ContractEdge, ...] = ()

    @property
    def ok(self) -> bool:
        """True when nothing was reported; an absent catalog is ok by definition."""
        return not self.diagnostics

    def to_dict(self) -> dict[str, object]:
        return {
            "present": self.present,
            "declarations": [declaration.to_dict() for declaration in self.declarations],
            "diagnostics": [diagnostic.to_dict() for diagnostic in self.diagnostics],
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
        }


def absent_closure() -> ContractClosure:
    """The explicit empty state for a project with no contract catalog.

    Absence is a supported configuration, not an error: it carries no diagnostics so
    a project without a catalog gains no contract-specific findings.
    """
    return ContractClosure(present=False)


def normalize_repository_path(raw: object) -> str | None:
    """Normalize a declared repository-relative path, or return None if unusable.

    Forward slashes are canonical, ``.`` segments and repeated separators are dropped,
    and surrounding whitespace is removed, so ``./docs//x.json`` and ``docs/x.json``
    compare equal for duplicate detection. ``..`` segments are deliberately preserved
    and a rooted prefix is deliberately preserved: rejecting either is the catalog
    loader's lexical safety check, and normalizing them away here would destroy the
    evidence that check needs.
    """
    if not isinstance(raw, str):
        return None
    candidate = raw.strip().replace("\\", "/")
    if not candidate:
        return None
    rooted = candidate.startswith("/")
    segments = [segment for segment in candidate.split("/") if segment not in ("", ".")]
    if not segments:
        return None
    normalized = "/".join(segments)
    return f"/{normalized}" if rooted else normalized


def parse_relation_ref(raw: object) -> ContractRelation | None:
    """Parse a ``<kind>:<identifier>`` relationship ref, or None when malformed.

    The whole ref is stripped, but its parts are not: ``spec :SPEC-X`` is malformed
    because ``"spec "`` is not a known kind. Unparseable refs become
    `CODE_RELATION_INVALID` findings at the call site; a compact helper returning a
    bare None keeps that decision in one place.
    """
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    kind, separator, target = text.partition(":")
    if not separator or kind not in RELATION_KINDS or not target:
        return None
    return ContractRelation(kind=kind, target=target, raw=text)


def parse_catalog_text(text: str) -> ContractClosure:
    """Parse catalog text (YAML or JSON; JSON is a YAML subset) into a closure.

    Text that is present but unreadable is a failure, never an absence: an empty or
    unparsable document yields ``present=True`` plus `CODE_CATALOG_INVALID`. Only
    `absent_closure()` reports absence.
    """
    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError as error:
        return ContractClosure(
            present=True,
            diagnostics=(
                _catalog_diagnostic(f"catalog text is not parseable YAML or JSON: {error}"),
            ),
        )
    return parse_catalog(document)


def parse_catalog(document: object) -> ContractClosure:
    """Validate and model an already-parsed catalog document.

    The document is validated against `CATALOG_SCHEMA` first; if any schema rule fails
    the whole document is rejected (no partial acceptance) and one
    `CODE_CATALOG_INVALID` diagnostic is emitted per schema error, attributed to the
    offending declaration when the error path names one. A schema-valid document is
    then checked declaration by declaration for the rules the schema deliberately does
    not own (usable id/path, known kind and status, uniqueness, relationship syntax).

    This function performs no I/O and raises nothing for invalid input.
    """
    if not isinstance(document, Mapping):
        return ContractClosure(
            present=True,
            diagnostics=(
                _catalog_diagnostic(
                    "catalog document must be a mapping with a `schema` identity and a "
                    f"`contracts` list, got {type(document).__name__}"
                ),
            ),
        )

    errors = validate_against(dict(document), CATALOG_SCHEMA)
    if errors:
        return ContractClosure(
            present=True,
            diagnostics=tuple(_schema_diagnostic(document, error) for error in errors),
        )
    return _build_closure(document)


def _build_closure(document: Mapping[str, Any]) -> ContractClosure:
    entries = document.get("contracts")
    declarations: list[ContractDeclaration] = []
    diagnostics: list[ContractDiagnostic] = []
    seen_ids: set[str] = set()
    seen_paths: dict[str, str] = {}

    if isinstance(entries, list):
        for entry in entries:
            declaration, entry_diagnostics = _parse_entry(entry, seen_ids, seen_paths)
            diagnostics.extend(entry_diagnostics)
            if declaration is not None:
                declarations.append(declaration)

    declarations.sort(key=lambda declaration: declaration.id)
    diagnostics.sort(
        key=lambda diagnostic: (diagnostic.declaration_id, diagnostic.code, diagnostic.message)
    )
    return ContractClosure(
        present=True,
        declarations=tuple(declarations),
        diagnostics=tuple(diagnostics),
    )


def _parse_entry(
    entry: object,
    seen_ids: set[str],
    seen_paths: dict[str, str],
) -> tuple[ContractDeclaration | None, list[ContractDiagnostic]]:
    """Validate one declaration. Returns (accepted declaration or None, findings).

    Ids and usable paths are registered even when the entry is later rejected, so a
    duplicate declaration is always visible rather than hidden behind the rejection
    of the entry that got there first.
    """
    if not isinstance(entry, Mapping):
        return None, [
            ContractDiagnostic(
                code=CODE_DECLARATION_INVALID,
                declaration_id=MISSING_DECLARATION_ID,
                message="catalog entry must be a mapping",
            )
        ]

    declared_id = entry.get("id")
    if not isinstance(declared_id, str) or not declared_id.strip():
        return None, [
            ContractDiagnostic(
                code=CODE_DECLARATION_INVALID,
                declaration_id=MISSING_DECLARATION_ID,
                message="declaration is missing a usable non-empty `id`",
            )
        ]
    identifier = declared_id.strip()
    if identifier in seen_ids:
        return None, [
            ContractDiagnostic(
                code=CODE_DECLARATION_DUPLICATE_ID,
                declaration_id=identifier,
                message=(
                    f"declaration id {identifier!r} is already declared; duplicate ids are "
                    "ambiguous, so the first declaration is kept and this entry is rejected"
                ),
            )
        ]
    seen_ids.add(identifier)

    normalized_path = normalize_repository_path(entry.get("path"))
    if normalized_path is None:
        return None, [
            ContractDiagnostic(
                code=CODE_DECLARATION_INVALID,
                declaration_id=identifier,
                message=(
                    f"declaration {identifier!r} has no usable repository-relative `path`"
                ),
            )
        ]
    owner = seen_paths.get(normalized_path)
    if owner is not None:
        return None, [
            ContractDiagnostic(
                code=CODE_DECLARATION_DUPLICATE_PATH,
                declaration_id=identifier,
                message=(
                    f"declaration {identifier!r} normalizes to path {normalized_path!r}, "
                    f"already declared by {owner!r}"
                ),
            )
        ]
    seen_paths[normalized_path] = identifier

    kind = entry.get("kind")
    if not isinstance(kind, str) or kind not in CONTRACT_KINDS:
        return None, [
            ContractDiagnostic(
                code=CODE_KIND_UNSUPPORTED,
                declaration_id=identifier,
                message=(
                    f"declaration {identifier!r} declares kind {kind!r}; supported kinds are "
                    f"{sorted(CONTRACT_KINDS)}"
                ),
            )
        ]

    status = entry.get("status", DEFAULT_CONTRACT_STATUS)
    if not isinstance(status, str) or status not in CONTRACT_STATUSES:
        return None, [
            ContractDiagnostic(
                code=CODE_STATUS_UNSUPPORTED,
                declaration_id=identifier,
                message=(
                    f"declaration {identifier!r} declares status {status!r}; supported statuses "
                    f"are {sorted(CONTRACT_STATUSES)}"
                ),
            )
        ]

    relation_diagnostics: list[ContractDiagnostic] = []
    declaration = ContractDeclaration(
        id=identifier,
        path=normalized_path,
        kind=kind,
        status=status,
        authority=_relation_field(entry, "authority", identifier, relation_diagnostics),
        validates_against=_relation_field(
            entry, "validates_against", identifier, relation_diagnostics
        ),
        consumers=_relation_list(entry, identifier, relation_diagnostics),
    )
    if relation_diagnostics:
        return None, relation_diagnostics
    return declaration, []


def _relation_field(
    entry: Mapping[str, Any],
    field_name: str,
    identifier: str,
    diagnostics: list[ContractDiagnostic],
) -> ContractRelation | None:
    raw = entry.get(field_name)
    if raw is None:
        return None
    relation = parse_relation_ref(raw)
    if relation is None:
        diagnostics.append(_invalid_relation(identifier, field_name, raw))
    return relation


def _relation_list(
    entry: Mapping[str, Any],
    identifier: str,
    diagnostics: list[ContractDiagnostic],
) -> tuple[ContractRelation, ...]:
    raw = entry.get("consumers")
    if raw is None:
        return ()
    if not isinstance(raw, (list, tuple)):
        diagnostics.append(_invalid_relation(identifier, "consumers", raw))
        return ()
    relations: list[ContractRelation] = []
    for item in raw:
        relation = parse_relation_ref(item)
        if relation is None:
            diagnostics.append(_invalid_relation(identifier, "consumers", item))
        else:
            relations.append(relation)
    return tuple(relations)


def _invalid_relation(identifier: str, field_name: str, raw: object) -> ContractDiagnostic:
    return ContractDiagnostic(
        code=CODE_RELATION_INVALID,
        declaration_id=identifier,
        message=(
            f"declaration {identifier!r} has a malformed `{field_name}` relationship ref "
            f"{raw!r}; expected `<kind>:<identifier>` with kind in {sorted(RELATION_KINDS)}"
        ),
    )


def _catalog_diagnostic(message: str) -> ContractDiagnostic:
    return ContractDiagnostic(
        code=CODE_CATALOG_INVALID,
        declaration_id=MISSING_DECLARATION_ID,
        message=message,
    )


def _schema_diagnostic(document: Mapping[str, Any], error: str) -> ContractDiagnostic:
    return ContractDiagnostic(
        code=CODE_CATALOG_INVALID,
        declaration_id=_error_declaration_id(document, error),
        message=error,
    )


def _error_declaration_id(document: Mapping[str, Any], error: str) -> str:
    """Attribute a substrate schema error to a declaration when its path names one.

    `validate_against` renders errors as ``<json/pointer/path>: message``; a path
    beginning ``contracts/<index>`` identifies the offending entry, so the finding can
    name that declaration instead of collapsing every schema error into the
    placeholder. Anything else (including root-level failures) keeps the placeholder.
    """
    path_text, separator, _message = error.partition(": ")
    if not separator:
        return MISSING_DECLARATION_ID
    parts = path_text.split("/")
    if len(parts) >= 2 and parts[0] == "contracts" and parts[1].isdigit():
        return _entry_id(document, int(parts[1]))
    return MISSING_DECLARATION_ID


def _entry_id(document: Mapping[str, Any], index: int) -> str:
    entries = document.get("contracts")
    if isinstance(entries, list) and index < len(entries):
        entry = entries[index]
        if isinstance(entry, Mapping):
            declared_id = entry.get("id")
            if isinstance(declared_id, str) and declared_id.strip():
                return declared_id.strip()
    return MISSING_DECLARATION_ID
