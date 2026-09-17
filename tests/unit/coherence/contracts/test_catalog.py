"""Unit tests for the contract catalog loader (optional-contract-artifacts task 3).

The loader owns catalog *file* discovery and the two halves of declared-path
safety: lexical rejection of unsafe declared syntax *before* canonicalization
(SR-074 / AC-1), and safe resolution that rejects reparse-point escapes with a
diagnostic naming the declaration (SR-074 / AC-2). Absence is explicit and
fail-closed (SR-073 / AC-1).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from coherence.contracts.catalog import CATALOG_RELATIVE_PATH, load_contract_catalog
from coherence.contracts.model import (
    CODE_CATALOG_INVALID,
    CODE_CATALOG_UNREADABLE,
    CODE_DECLARATION_DUPLICATE_ID,
    CODE_DECLARATION_DUPLICATE_PATH,
    CODE_FILE_MISSING,
    CODE_KIND_UNSUPPORTED,
    CODE_PATH_ESCAPES_ROOT,
    CODE_PATH_UNSAFE,
)

pytestmark = pytest.mark.unit


def _contract(**overrides: object) -> dict[str, object]:
    """A minimal, valid declaration; override fields per test."""
    entry: dict[str, object] = {
        "id": "WIRE-API",
        "path": "docs/wire.schema.json",
        "kind": "json_schema",
        "status": "active",
    }
    entry.update(overrides)
    return entry


def _document(*contracts: dict[str, object]) -> dict[str, object]:
    return {"schema": "coherence.contract-catalog.v1", "contracts": list(contracts)}


def _write_catalog(root: Path, document: object) -> Path:
    """Write ``.factory/contracts.yaml`` as JSON text (a YAML subset) so unsafe
    declared strings (NUL, backslashes) round-trip exactly through the loader."""
    catalog_file = root / CATALOG_RELATIVE_PATH
    catalog_file.parent.mkdir(parents=True, exist_ok=True)
    catalog_file.write_text(json.dumps(document), encoding="utf-8")
    return catalog_file


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir(exist_ok=True)
    return root


def _codes(closure: object) -> list[str]:
    return [str(diagnostic.code) for diagnostic in getattr(closure, "diagnostics")]


# ---------------------------------------------------------------------------
# SR-073 / AC-1
# ---------------------------------------------------------------------------


@pytest.mark.sr("SR-073")
def test_sr073_ac1_absent_is_empty_and_present_but_bad_is_blocking(tmp_path: Path) -> None:
    # No catalog -> explicit empty closure state and zero contract findings.
    absent = load_contract_catalog(_project(tmp_path))
    assert absent.present is False
    assert absent.declarations == ()
    assert absent.diagnostics == ()
    assert absent.ok is True
    assert absent.to_dict() == {
        "present": False,
        "declarations": [],
        "diagnostics": [],
        "nodes": [],
        "edges": [],
    }

    # Present but malformed -> visible blocking diagnostic, not silent acceptance.
    malformed_root = tmp_path / "malformed"
    malformed_root.mkdir()
    _write_catalog(malformed_root, _document()).write_text(
        "schema: [unclosed\n", encoding="utf-8"
    )
    malformed = load_contract_catalog(malformed_root)
    assert malformed.present is True
    assert CODE_CATALOG_INVALID in _codes(malformed)
    assert malformed.declarations == ()
    assert malformed.ok is False

    # Present but duplicated -> visible diagnostic, not silently narrowed.
    duplicated = load_contract_catalog(
        _write_catalog(
            _project(tmp_path),
            _document(_contract(), _contract(path="docs/other.schema.json")),
        ).parent.parent
    )
    assert duplicated.present is True
    assert CODE_DECLARATION_DUPLICATE_ID in _codes(duplicated)
    assert duplicated.ok is False

    # Present but declares an unsupported kind -> visible diagnostic, no accept.
    unsupported = load_contract_catalog(
        _write_catalog(_project(tmp_path), _document(_contract(kind="banana"))).parent.parent
    )
    assert unsupported.present is True
    assert CODE_KIND_UNSUPPORTED in _codes(unsupported)
    assert unsupported.declarations == ()
    assert unsupported.ok is False


# ---------------------------------------------------------------------------
# SR-074 / AC-1 -- lexical rejection on the declared string, before canonicalization
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "declared",
    [
        "/schema.json",  # POSIX absolute
        "C:/schema.json",  # drive-rooted, forward slashes
        "c:\\schema.json",  # drive-rooted, backslashes
        "\\\\server\\share\\schema.json",  # UNC
        "\\schema.json",  # Windows current-drive rooted
        "docs/../docs/ok.json",  # parent component (resolves inside root)
        "a/b.json:stream",  # alternate-data-stream syntax
        "a\x00b.json",  # NUL character
        "a//b.json",  # empty intermediate component
    ],
)
def test_sr074_ac1_unsafe_declared_syntax_is_rejected(
    tmp_path: Path, declared: str
) -> None:
    root = _write_catalog(_project(tmp_path), _document(_contract(path=declared))).parent.parent
    closure = load_contract_catalog(root)

    assert CODE_PATH_UNSAFE in _codes(closure), declared
    assert closure.ok is False, declared
    assert closure.declarations == (), declared
    diagnostic = next(
        diagnostic
        for diagnostic in closure.diagnostics
        if diagnostic.code == CODE_PATH_UNSAFE
    )
    assert diagnostic.declaration_id == "WIRE-API", declared
    assert "declared path" in diagnostic.message, declared


@pytest.mark.sr("SR-074")
def test_sr074_ac1_syntax_safety_precedes_resolution(tmp_path: Path) -> None:
    # `docs/../docs/ok.json` normalizes and resolves INSIDE the repository root,
    # yet it is rejected on its declared `..` syntax: a resolution-only check
    # must not rescue unsafe declared input. This proves rejection happens
    # before canonicalization, never after.
    root = _project(tmp_path)
    _write_catalog(root, _document(_contract(path="docs/../docs/ok.json")))

    # A naive resolve-only implementation would accept this exact target.
    in_root = (root / "docs" / ".." / "docs" / "ok.json").resolve()
    assert in_root.is_relative_to(root.resolve())

    closure = load_contract_catalog(root)
    assert CODE_PATH_UNSAFE in _codes(closure)
    assert closure.declarations == ()
    diagnostic = next(
        d for d in closure.diagnostics if d.code == CODE_PATH_UNSAFE
    )
    assert diagnostic.declaration_id == "WIRE-API"
    assert ".." in diagnostic.message


# ---------------------------------------------------------------------------
# SR-074 / AC-2 -- resolution rejects reparse-point escapes, as a diagnostic
# ---------------------------------------------------------------------------


@pytest.mark.sr("SR-074")
def test_sr074_ac2_symlink_escape_is_rejected_with_a_diagnostic(tmp_path: Path) -> None:
    root = _project(tmp_path)
    _write_catalog(root, _document(_contract(path="docs/leaked.schema.json")))
    secret = tmp_path / "secret.schema.json"
    secret.write_text("{}", encoding="utf-8")
    docs = root / "docs"
    docs.mkdir()
    linked = docs / "leaked.schema.json"
    try:
        linked.symlink_to(secret)
    except OSError:
        pytest.skip("symlink creation is unavailable on this Windows runner")

    closure = load_contract_catalog(root)

    assert CODE_PATH_ESCAPES_ROOT in _codes(closure)
    assert closure.ok is False
    assert closure.declarations == ()
    diagnostic = next(
        d for d in closure.diagnostics if d.code == CODE_PATH_ESCAPES_ROOT
    )
    assert diagnostic.declaration_id == "WIRE-API"
    assert "leaked.schema.json" in diagnostic.message


# ---------------------------------------------------------------------------
# File-present / file-missing / unreadable handling
# ---------------------------------------------------------------------------


def test_load_accepts_a_safe_existing_declaration_without_diagnostics(tmp_path: Path) -> None:
    root = _project(tmp_path)
    _write_catalog(root, _document(_contract()))
    target = root / "docs" / "wire.schema.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("{}", encoding="utf-8")

    closure = load_contract_catalog(root)

    assert closure.present is True
    assert closure.diagnostics == ()
    assert [declaration.id for declaration in closure.declarations] == ["WIRE-API"]


def test_declared_file_missing_is_reported_but_not_silently_dropped(tmp_path: Path) -> None:
    root = _write_catalog(_project(tmp_path), _document(_contract())).parent.parent

    closure = load_contract_catalog(root)

    assert CODE_FILE_MISSING in _codes(closure)
    assert closure.ok is False
    assert [declaration.id for declaration in closure.declarations] == ["WIRE-API"]
    diagnostic = next(d for d in closure.diagnostics if d.code == CODE_FILE_MISSING)
    assert diagnostic.declaration_id == "WIRE-API"


def test_present_but_unreadable_catalog_returns_fail_closed_closure(tmp_path: Path) -> None:
    root = _project(tmp_path)
    catalog_file = root / CATALOG_RELATIVE_PATH
    catalog_file.parent.mkdir(parents=True, exist_ok=True)
    catalog_file.mkdir()  # a directory where a file is expected

    closure = load_contract_catalog(root)

    assert closure.present is True
    assert CODE_CATALOG_UNREADABLE in _codes(closure)
    assert closure.ok is False
    assert closure.declarations == ()


def test_duplicate_normalized_paths_are_reported_through_the_loader(tmp_path: Path) -> None:
    root = _write_catalog(
        _project(tmp_path),
        _document(
            _contract(id="WIRE", path="docs/wire.schema.json"),
            _contract(id="WIRE-ALIAS", path="./docs/wire.schema.json"),
        ),
    ).parent.parent

    closure = load_contract_catalog(root)

    assert CODE_DECLARATION_DUPLICATE_PATH in _codes(closure)
    assert closure.ok is False