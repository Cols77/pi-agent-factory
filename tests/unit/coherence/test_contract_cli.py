"""CLI projection tests for contract artifacts (task 8).

Drive the real ``coherence.navigate.cli.main`` entrypoint against a fixture
project that declares a catalog, and assert the *stable machine-readable* JSON
surface: the six ``CONTRACT_*`` codes, deterministic (sorted) output across two
runs, and a human projection that renders a contract finding line.

Per the SR-076 amendment, the stable codes are asserted as codes/fields, never
as prose substrings that could match by accident. This file is intentionally not
sr-tagged: SR-076's AC-2/AC-3 point at the freshness/contract suites that already
exist; a sr marker on this non-AC-ref file would be a traceability defect.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from coherence.navigate import cli as nav_cli
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


def _full_project(root: Path) -> None:
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
    _write(root, ".factory/contracts.yaml", json.dumps(document))
    _write(root, "contracts/schema.schema.json", '{"$ref": "defs.schema.json"}')
    _write(root, "contracts/defs.schema.json", '{"type": "object"}')
    _write(root, "contracts/broken.schema.json", '{"$ref": "missing.json"}')
    _write(root, "contracts/orphan.json", '{"note": "standalone"}')
    _write(root, "fixtures/seed.json", '{"a": 1}')
    _write(root, "backend/app.py", "x = 1")
    _write(root, "tests/schema_test.py", "def test_wire(): pass")


def _record_evidence_then_change(root: Path) -> None:
    """Record SCHEMA's closure as validation evidence, then change the contract
    so the recorded fingerprint, the contract, and the fixture go stale."""
    fp = _contract_closure_fingerprint(root, "SCHEMA")
    assert fp is not None
    run_dir = root / "evidence" / "runs" / "RUN-SC"
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "run": "RUN-SC",
        "feature": "FEAT-X",
        "dependencies": [
            {"kind": "contract", "name": "SCHEMA", "source": "SCHEMA", "digest": fp}
        ],
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    _write(root, "contracts/schema.schema.json", '{"$ref": "defs.schema.json", "x": true}')


def _freshness_json(root: Path, capsys) -> dict:
    code = nav_cli.main(["freshness", "--repo-root", str(root), "--json"])
    assert code == 0
    out = capsys.readouterr().out
    return json.loads(out)


def _contract_codes(data: dict) -> set[str]:
    return {f["code"] for f in data["findings"] if f["code"].startswith("CONTRACT_")}


def test_contract_cli_json_reports_six_codes_deterministically(tmp_path, capsys) -> None:
    root = tmp_path / "project"
    _full_project(root)
    _record_evidence_then_change(root)

    first = _freshness_json(root, capsys)
    second = _freshness_json(root, capsys)

    # Stable machine-readable contract codes, asserted as codes not prose.
    assert _contract_codes(first) == ALL_CONTRACT_CODES

    # Deterministic, sorted output: two runs are byte-identical JSON.
    assert json.dumps(first) == json.dumps(second)

    # Every contract finding carries the expected machine fields.
    for finding in first["findings"]:
        if finding["code"] in ALL_CONTRACT_CODES:
            assert finding["code"] and finding["subject"] and finding["detail"]


def test_contract_cli_human_projection_shows_contract_finding(tmp_path, capsys) -> None:
    root = tmp_path / "project"
    _full_project(root)
    _record_evidence_then_change(root)

    code = nav_cli.main(["freshness", "--repo-root", str(root)])
    assert code == 0
    out = capsys.readouterr().out

    # A human projection shows contract findings as stable code lines, not
    # prose -- assert the code token on the line, not free text.
    assert any(line.startswith("  [CONTRACT_") for line in out.splitlines())
    assert "  [CONTRACT_REFERENCE_BROKEN] error contract:BROKEN:" in out
    assert "  [CONTRACT_CONSUMER_STALE] error run:RUN-SC:" in out


def test_contract_cli_no_catalog_zero_contract_findings(tmp_path, capsys) -> None:
    root = tmp_path / "project"
    _full_project(root)
    (root / ".factory" / "contracts.yaml").unlink()

    data = _freshness_json(root, capsys)
    assert _contract_codes(data) == set()
