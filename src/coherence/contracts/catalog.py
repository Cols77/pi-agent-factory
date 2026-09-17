"""Catalog file discovery and lexical path safety (optional-contract-artifacts task 3).

Builds on the pure document model in ``coherence.contracts.model``. This module
owns the opt-in file location and the two halves of declared-path safety:

* **Lexical half** (SR-074 / AC-1): runs on the *declared* string before any
  canonicalization and rejects absolute/rooted POSIX and drive-rooted and UNC
  forms, current-drive-rooted paths, parent ``..`` components, NUL characters,
  alternate-data-stream colons and empty components. An in-root *resolution*
  must never rescue unsafe declared syntax.
* **Resolution half** (SR-074 / AC-2): via ``coherence.planning.paths.safe_resolve``,
  rejects a target that resolves outside the resolved root through a symlink,
  junction, mount point or other reparse point, reported as a diagnostic naming
  the offending declaration rather than an unhandled filesystem error.

The loader is TOTAL and never raises on bad input: an absent catalog returns
``model.absent_closure()`` (``present=False``, no declarations, no
diagnostics); a present-but-unreadable or unparseable catalog returns
``present=True`` with structured diagnostics. Only genuine programming errors
may raise. Both modules live under ``coherence``, so importing
``coherence.planning.paths`` respects the layering rule
``factory -> coherence -> substrate``.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import yaml

from coherence.contracts.model import (
    CODE_CATALOG_INVALID,
    CODE_CATALOG_UNREADABLE,
    CODE_FILE_MISSING,
    CODE_PATH_ESCAPES_ROOT,
    CODE_PATH_UNSAFE,
    MISSING_DECLARATION_ID,
    ContractClosure,
    ContractDiagnostic,
    absent_closure,
    parse_catalog,
)
from coherence.planning.paths import safe_resolve

CATALOG_RELATIVE_PATH = ".factory/contracts.yaml"


def load_contract_catalog(root: Path) -> ContractClosure:
    """Load the opt-in contract catalog for ``root``, fail-closed.

    Never raises for bad input. Absence -> ``absent_closure()``. A catalog that
    is present but unreadable or unparseable yields ``present=True`` plus
    diagnostics. Declared paths are checked lexically before canonicalization
    and then by safe resolution; each unsafe or missing declaration is reported,
    and unsafe declarations are excluded from the returned closure.
    """
    catalog_file = Path(root) / CATALOG_RELATIVE_PATH
    project_root = Path(root)
    try:
        if catalog_file.is_file():
            text = catalog_file.read_text(encoding="utf-8")
        elif catalog_file.exists():
            return _unreadable_closure(str(catalog_file), "path exists but is not a file")
        else:
            return absent_closure()
    except OSError as error:
        return _unreadable_closure(str(catalog_file), str(error))

    try:
        raw_document = yaml.safe_load(text)
    except yaml.YAMLError as error:
        return ContractClosure(
            present=True,
            diagnostics=(
                ContractDiagnostic(
                    code=CODE_CATALOG_INVALID,
                    declaration_id=MISSING_DECLARATION_ID,
                    message=f"catalog text is not parseable YAML or JSON: {error}",
                ),
            ),
        )

    closure = parse_catalog(raw_document)
    return _apply_path_safety(project_root, raw_document, closure)


def _apply_path_safety(
    root: Path, raw_document: object, closure: ContractClosure
) -> ContractClosure:
    """Check every accepted declaration's declared path against the two halves.

    A declaration whose declared syntax is unsafe, or whose resolution fails,
    is reported and excluded from ``closure.declarations``. A declaration whose
    declared file is missing is reported but kept: it is not silently dropped.
    """
    if not isinstance(raw_document, Mapping):
        return closure
    entries = raw_document.get("contracts")
    if not isinstance(entries, list):
        return closure

    accepted_ids = {declaration.id for declaration in closure.declarations}
    rejected_ids: set[str] = set()
    new_diagnostics: list[ContractDiagnostic] = []

    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        declared_id = entry.get("id")
        if not isinstance(declared_id, str) or not declared_id.strip():
            continue
        identifier = declared_id.strip()
        if identifier not in accepted_ids:
            continue
        declared_path = entry.get("path")
        if not isinstance(declared_path, str):
            continue

        lexical = _lexical_error(declared_path)
        if lexical is not None:
            rejected_ids.add(identifier)
            new_diagnostics.append(
                _diagnostic(CODE_PATH_UNSAFE, identifier, declared_path, lexical)
            )
            continue

        resolved = _resolve(root, declared_path)
        if resolved is None:
            rejected_ids.add(identifier)
            new_diagnostics.append(
                _diagnostic(
                    CODE_PATH_ESCAPES_ROOT,
                    identifier,
                    declared_path,
                    "path is not a plain repository-relative file (it resolves outside the "
                    "resolved repository root through a symlink, junction, mount point or "
                    "other reparse point); the declaration is rejected",
                )
            )
        elif not resolved.is_file():
            new_diagnostics.append(
                _diagnostic(
                    CODE_FILE_MISSING,
                    identifier,
                    declared_path,
                    "declares a path with no file at the resolved location",
                )
            )
        # else: safe and present -> accepted, no diagnostic.

    if not new_diagnostics:
        return closure

    kept_declarations = tuple(
        declaration
        for declaration in closure.declarations
        if declaration.id not in rejected_ids
    )
    combined = list(closure.diagnostics) + new_diagnostics
    combined.sort(key=lambda item: (item.declaration_id, item.code, item.message))
    return ContractClosure(
        present=True,
        declarations=kept_declarations,
        diagnostics=tuple(combined),
    )


def _lexical_error(raw: str) -> str | None:
    """Return a reason the declared string is unsafe, or None when it is safe.

    The check is deliberately lexical, on the declared string before any
    canonicalization: a later in-root resolution must not rescue unsafe input.
    """
    if "\x00" in raw:
        return "path contains a NUL character, which is not a valid path"
    text = raw.strip()
    if not text:
        return "path is empty or whitespace-only; a repository-relative path is required"
    forward = text.replace("\\", "/")
    if forward.startswith("//"):
        return "path is a UNC absolute path; a repository-relative path is required"
    if forward.startswith("/"):
        return "path is rooted/absolute; a repository-relative path is required"
    if _drive_rooted(text):
        return "path is drive-rooted (absolute); a repository-relative path is required"
    if _alternate_data_stream(forward):
        return "path uses Windows alternate-data-stream ':' syntax"
    for segment in forward.split("/"):
        if segment == "..":
            return "path contains a parent '..' component; escaping the repository root is not allowed"
        if not segment:
            return "path contains an empty path component"
    return None


def _drive_rooted(text: str) -> bool:
    return len(text) >= 2 and text[0].isalpha() and text[1] == ":"


def _alternate_data_stream(forward: str) -> bool:
    rest = forward[2:] if _drive_rooted(forward) else forward
    return ":" in rest


def _resolve(root: Path, declared_path: str) -> Path | None:
    """Resolve a lexical-safe declared path under the root, or None when unsafe."""
    candidate = Path(root) / Path(declared_path.replace("\\", "/"))
    try:
        return safe_resolve(Path(root), candidate)
    except (OSError, RuntimeError, ValueError):
        return None


def _diagnostic(code: str, identifier: str, declared: str, detail: str) -> ContractDiagnostic:
    return ContractDiagnostic(
        code=code,
        declaration_id=identifier,
        message=f"declaration {identifier!r} {detail} (declared path {declared!r})",
    )


def _unreadable_closure(location: str, detail: str) -> ContractClosure:
    return ContractClosure(
        present=True,
        diagnostics=(
            ContractDiagnostic(
                code=CODE_CATALOG_UNREADABLE,
                declaration_id=MISSING_DECLARATION_ID,
                message=(
                    f"catalog file at {location} is present but could not be read: {detail}"
                ),
            ),
        ),
    )


__all__ = ["CATALOG_RELATIVE_PATH", "load_contract_catalog"]