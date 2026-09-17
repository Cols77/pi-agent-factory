"""CONTRACT_* freshness findings via the existing freshness engine (task 7).

Evidence for SR-076 / AC-2 -- *Contract findings are reported under stable
machine-readable codes -- CONTRACT_REFERENCE_BROKEN, CONTRACT_MISSING_PROVENANCE,
CONTRACT_STALE, CONTRACT_CONSUMER_STALE, CONTRACT_FIXTURE_STALE and
CONTRACT_VALIDATION_UNAVAILABLE -- and a declared contract is never reported as
covered merely because its file exists.*

Each finding is derived from *declared* relationships and recorded evidence
only, and always carries a stable ``code``, ``subject`` and ``detail``.
``freshness_health`` is a pure query; the no-catalog path stays byte-identical
(zero CONTRACT_* findings).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from coherence.navigate.health import freshness_health
from factory.freshness.deps import _contract_closure_fingerprint

pytestmark = pytest.mark.unit

CATALOG_SCHEMA = "coherence.contract-catalog.v1"

ALL_CONTRACT_CODES = {
    "CONTRACT_REFERENCE_BROKEN",
    "CONTRACT_MISSING_PROVENANCE",
    "CONTRACT_STALE",
    "CONTRACT_CONSUMER_STALE",
    "CONTRACT_FIXTURE_STALE",
    "CONTRACT_VALIDATION_UNAVAILABLE",
}


def _write(root: Path, rel: str, content: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _catalog(root: Path, document: dict) -> None:
    _write(root, ".factory/contracts.yaml", json.dumps(document))


def _full_project(root: Path) -> None:
    """A catalog engineered so a single ``freshness_health`` call reports all
    six CONTRACT_* codes after SCHEMA's file changes:

    * SCHEMA (json_schema) -- transitively references DEFS, declares a test
      consumer with no recorded evidence, and will be *changed* (so its
      recorded evidence goes stale).
    * DEFS (json_schema) -- the transitive ``$ref`` target of SCHEMA.
    * FIX (fixture) -- validated against SCHEMA; SCHEMA's change makes the
      fixture's validating schema stale.
    * BROKEN (json_schema) -- a ``$ref`` to a missing file -> CONTRACT_REFERENCE_BROKEN.
    * ORPHAN (other) -- no authority / validates_against / consumers ->
      CONTRACT_MISSING_PROVENANCE.
    """
    document = {
        "schema": CATALOG_SCHEMA,
        "contracts": [
            {
                "id": "SCHEMA",
                "path": "contracts/schema.schema.json",
                "kind": "json_schema",
                "status": "active",
                "authority": "spec:SPEC-1",
                "consumers": ["test:tests/schema_test.py"],
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
                "validates_against": "contract:SCHEMA",
                "consumers": ["code:backend/app.py"],
            },
            {
                "id": "BROKEN",
                "path": "contracts/broken.schema.json",
                "kind": "json_schema",
                "status": "active",
            },
            {
                "id": "ORPHAN",
                "path": "contracts/orphan.json",
                "kind": "other",
                "status": "active",
            },
        ],
    }
    _catalog(root, document)
    _write(root, "contracts/schema.schema.json", '{"$ref": "defs.schema.json"}')
    _write(root, "contracts/defs.schema.json", '{"type": "object"}')
    _write(root, "contracts/broken.schema.json", '{"$ref": "missing.json"}')
    _write(root, "contracts/orphan.json", '{"note": "standalone"}')
    _write(root, "fixtures/seed.json", '{"a": 1}')
    _write(root, "backend/app.py", "x = 1")
    _write(root, "tests/schema_test.py", "def test_wire(): pass")


def _evidence(run_id: str, contract_source: str, digest: str, root: Path) -> None:
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


def _contract_findings(root: Path) -> dict[str, list[dict]]:
    all_findings = freshness_health(root)
    out: dict[str, list[dict]] = {}
    for finding in all_findings:
        if finding.code in ALL_CONTRACT_CODES:
            out.setdefault(finding.code, []).append(
                {"code": finding.code, "severity": finding.severity, "subject": finding.subject, "detail": finding.detail}
            )
    return out


@pytest.mark.sr("SR-076")
def test_sr076_ac2_all_six_contract_codes_stable_and_attributed(tmp_path: Path) -> None:
    root = tmp_path / "project"
    _full_project(root)

    # Record SCHEMA's current closure as validation evidence, then change the
    # contract so its recorded evidence (and the fixture validated against it)
    # become stale.
    schema_closure = _contract_closure_fingerprint(root, "SCHEMA")
    assert schema_closure is not None
    _evidence("RUN-SC", "SCHEMA", schema_closure, root)
    _write(root, "contracts/schema.schema.json", '{"$ref": "defs.schema.json", "x": true}')

    by_code = _contract_findings(root)

    # All six stable codes are reported.
    assert set(by_code) == ALL_CONTRACT_CODES

    # CONTRACT_REFERENCE_BROKEN: BROKEN carries a dangling $ref (diagnostic).
    broken = by_code["CONTRACT_REFERENCE_BROKEN"]
    assert broken and broken[0]["subject"] == "contract:BROKEN"
    assert broken[0]["detail"]

    # CONTRACT_MISSING_PROVENANCE: ORPHAN has no authority/validates/consumers.
    orphan = by_code["CONTRACT_MISSING_PROVENANCE"]
    assert any(f["subject"] == "contract:ORPHAN" for f in orphan)

    # A declared contract is never "covered" merely because its file exists:
    # ORPHAN's file exists and yet it is reported (not silently fresh).
    assert any(f["subject"] == "contract:ORPHAN" for f in orphan)

    # CONTRACT_CONSUMER_STALE: the recorded SCHEMA evidence no longer matches.
    consumer = by_code["CONTRACT_CONSUMER_STALE"]
    assert any(f["subject"] == "run:RUN-SC" for f in consumer)

    # CONTRACT_STALE: SCHEMA's closure changed.
    stale = by_code["CONTRACT_STALE"]
    assert any(f["subject"] == "contract:SCHEMA" for f in stale)

    # CONTRACT_FIXTURE_STALE: FIX is validated against the changed SCHEMA.
    fixture = by_code["CONTRACT_FIXTURE_STALE"]
    assert any(f["subject"] == "contract:FIX" for f in fixture)

    # CONTRACT_VALIDATION_UNAVAILABLE: declared consumers with no recorded
    # evidence are reported, so a contract is not "covered" by nomination alone.
    unavailable = by_code["CONTRACT_VALIDATION_UNAVAILABLE"]
    assert any(f["subject"] == "test:tests/schema_test.py" for f in unavailable)
    assert any(f["subject"] == "code:backend/app.py" for f in unavailable)

    # Every finding carries code+subject+detail (machine-readable JSON fields).
    for code, items in by_code.items():
        for item in items:
            assert item["code"] == code and item["subject"] and item["detail"]


def test_no_catalog_adds_zero_contract_findings(tmp_path: Path) -> None:
    root = tmp_path / "project"
    _full_project(root)
    # Catalogue-less project -> the compiler is absent -> zero CONTRACT_* findings.
    (root / ".factory" / "contracts.yaml").unlink()
    assert _contract_findings(root) == {}


def test_catalog_present_but_no_evidence_reports_only_unavailable_and_broken(tmp_path: Path) -> None:
    """Before any evidence is recorded, staleness findings are not invented:
    no CONTRACT_STALE / CONSUMER_STALE / FIXTURE_STALE without a changed
    record, but provenance and validation gaps are still surfaced."""
    root = tmp_path / "project"
    _full_project(root)
    by_code = _contract_findings(root)
    assert "CONTRACT_STALE" not in by_code
    assert "CONTRACT_CONSUMER_STALE" not in by_code
    assert "CONTRACT_FIXTURE_STALE" not in by_code
    assert "CONTRACT_REFERENCE_BROKEN" in by_code
    assert "CONTRACT_MISSING_PROVENANCE" in by_code
    assert "CONTRACT_VALIDATION_UNAVAILABLE" in by_code
