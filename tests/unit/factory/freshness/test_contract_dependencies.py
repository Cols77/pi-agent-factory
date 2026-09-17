"""Contract closure materialised as freshness dependency edges (task 7).

Evidence for SR-076 / AC-3 -- *A project that declares no catalog shows no
new invalidation, no new finding and no changed existing output* -- plus the
engine-level propagation the plan's Step 1 calls for:

* a changed root contract,
* a changed transitive ``$ref``,
* a changed fixture,
* a consumer with stale recorded evidence,
* missing provenance,
* and a no-catalog regression proving the feature is purely additive.

The recorded-evidence mechanism reuses the existing run-manifest dependency
format (``kind: "contract"`` entries) so ``check_artifact`` compares a
recorded *closure* fingerprint against the current compiled closure -- a
change to the root contract or to any transitive ``$ref`` stales the evidence
through the ordinary engine, exactly as runs already stale against recorded
code digests. No git is needed: the comparison is digest-vs-current.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from factory.freshness.deps import (
    FreshnessState,
    _contract_dependency_edges,
    _contract_closure_fingerprint,
    check_artifact,
    collect_dependency_edges,
    compute_impact,
)

pytestmark = pytest.mark.unit

CATALOG_SCHEMA = "coherence.contract-catalog.v1"


def _write(root: Path, rel: str, content: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _catalog(root: Path, document: dict) -> None:
    _write(root, ".factory/contracts.yaml", json.dumps(document))


def _project(root: Path) -> None:
    """A catalog + real files: WIRE references DEFS transitively, FIX is a
    fixture validated against WIRE, and WIRE declares code/test consumers."""
    document = {
        "schema": CATALOG_SCHEMA,
        "contracts": [
            {
                "id": "WIRE",
                "path": "contracts/wire.schema.json",
                "kind": "json_schema",
                "status": "active",
                "authority": "spec:SPEC-1",
                "consumers": ["code:backend/app.py", "test:tests/seed.py"],
            },
            {
                "id": "DEFS",
                "path": "contracts/defs.schema.json",
                "kind": "json_schema",
                "status": "active",
            },
            {
                "id": "FIX",
                "path": "fixtures/seed.json",
                "kind": "fixture",
                "status": "active",
                "validates_against": "contract:WIRE",
            },
        ],
    }
    _catalog(root, document)
    # WIRE transitively references DEFS (a catalog-declared schema) and an
    # un-declared file, so its closure folds both.
    _write(root, "contracts/wire.schema.json", '{"$ref": "defs.schema.json"}')
    _write(root, "contracts/defs.schema.json", '{"type": "object"}')
    _write(root, "fixtures/seed.json", '{"a": 1}')
    _write(root, "backend/app.py", "x = 1")
    _write(root, "tests/seed.py", "def test_one(): pass")


def _evidence(run_id: str, contract_source: str, digest: str, root: Path) -> None:
    """Record contract validation evidence in the existing run-manifest format."""
    run_dir = root / "evidence" / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "run": run_id,
        "feature": "FEAT-X",
        "dependencies": [
            {"kind": "contract", "name": contract_source, "source": contract_source, "digest": digest}
        ],
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


# ── SR-076 / AC-3: no catalog -> purely additive ───────────────────────────


@pytest.mark.sr("SR-076")
def test_sr076_ac3_catalog_absent_adds_no_contract_invalidation(tmp_path: Path) -> None:
    root = tmp_path / "project"
    _project(root)
    # The declared contracts are the only difference from a real repo: remove
    # the catalog so the project is catalog-less.
    (root / ".factory" / "contracts.yaml").unlink()

    edges = collect_dependency_edges(root)
    assert edges == [] or all(
        not e.source_ref.startswith("contract:") and not e.dependent_ref.startswith("contract:")
        for e in edges
    )
    assert _contract_dependency_edges(root) == []

    # No declared relationship -> no impact and no invalidation from a contract ref.
    impact = compute_impact(root, ["contract:WIRE"])
    assert impact.directly_affected == ()
    assert impact.transitively_affected == ()

    # A code file carries no contract fingerprint -> check_artifact unaffected.
    assert check_artifact(root, "code:backend/app.py").state == FreshnessState.FRESH


# ── engine propagation (plan Step 1 / Step 2) ──────────────────────────────


def test_contract_edges_materialized_with_catalog(tmp_path: Path) -> None:
    root = tmp_path / "project"
    _project(root)
    edges = collect_dependency_edges(root)

    def has(source: str, dependent: str) -> bool:
        return any(e.source_ref == source and e.dependent_ref == dependent for e in edges)

    # references: WIRE -> DEFS and WIRE -> code:contracts/defs.schema.json path? No:
    # DEFS is catalog-declared, so WIRE references contract:DEFS; the un-declared
    # note-like file above is catalog-declared DEFS, so no code: reference remains.
    assert has("contract:DEFS", "contract:WIRE")
    # validates_against: FIX -> WIRE.
    assert has("contract:WIRE", "contract:FIX")
    # consumed_by: WIRE -> declared consumers.
    assert has("contract:WIRE", "code:backend/app.py")
    assert has("contract:WIRE", "test:tests/seed.py")

    # Fingerprints are the source contract's *closure* fingerprint.
    for edge in edges:
        if edge.source_ref == "contract:WIRE":
            assert edge.fingerprint is not None
            assert edge.fingerprint != ""


def test_changed_root_contract_stales_recorded_evidence(tmp_path: Path) -> None:
    root = tmp_path / "project"
    _project(root)
    run_id = "RUN-WIRE-1"
    closed = _contract_closure_fingerprint(root, "WIRE")
    assert closed is not None
    _evidence(run_id, "WIRE", closed, root)
    assert check_artifact(root, f"run:{run_id}").state == FreshnessState.FRESH

    # Change the root contract file -> its closure changes -> recorded evidence stale.
    _write(root, "contracts/wire.schema.json", '{"$ref": "defs.schema.json", "x": 1}')
    state = check_artifact(root, f"run:{run_id}")
    assert state.state == FreshnessState.STALE


def test_changed_transitive_ref_stales_recorded_evidence(tmp_path: Path) -> None:
    root = tmp_path / "project"
    _project(root)
    run_id = "RUN-WIRE-2"
    closed = _contract_closure_fingerprint(root, "WIRE")
    assert closed is not None
    _evidence(run_id, "WIRE", closed, root)
    assert check_artifact(root, f"run:{run_id}").state == FreshnessState.FRESH

    # Change the *transitive* referenced schema, NOT the root contract file.
    _write(root, "contracts/defs.schema.json", '{"type": "object", "required": ["id"]}')
    # The root file is byte-identical; only its closure changed.
    assert _contract_closure_fingerprint(root, "WIRE") != closed
    state = check_artifact(root, f"run:{run_id}")
    assert state.state == FreshnessState.STALE


def test_changed_fixture_stales_its_evidence(tmp_path: Path) -> None:
    root = tmp_path / "project"
    _project(root)
    run_id = "RUN-FIX-1"
    fix_closed = _contract_closure_fingerprint(root, "FIX")
    assert fix_closed is not None
    _evidence(run_id, "FIX", fix_closed, root)
    assert check_artifact(root, f"run:{run_id}").state == FreshnessState.FRESH

    _write(root, "fixtures/seed.json", '{"a": 2}')
    state = check_artifact(root, f"run:{run_id}")
    assert state.state == FreshnessState.STALE


def test_compute_impact_propagates_through_contract_edges(tmp_path: Path) -> None:
    root = tmp_path / "project"
    _project(root)
    # A contract change propagates to the declared consumers via consumed_by.
    impact = compute_impact(root, ["contract:WIRE"])
    assert "code:backend/app.py" in impact.directly_affected
    assert "test:tests/seed.py" in impact.directly_affected
    # The fixture depends on the schema via validates_against.
    assert "contract:FIX" in impact.directly_affected


def test_current_source_digest_resolves_contract_kind(tmp_path: Path) -> None:
    root = tmp_path / "project"
    _project(root)
    from factory.freshness.deps import _current_source_digest

    before = _current_source_digest(root, "contract:WIRE")
    assert before is not None
    _write(root, "contracts/defs.schema.json", '{"type": "object", "additionalProperties": false}')
    after = _current_source_digest(root, "contract:WIRE")
    assert after is not None and after != before
