"""Build contract-artifact fixture projects and capture real CLI output.

Used to generate verbatim examples for docs/contract-artifacts.md. Real
`coherence.navigate` freshness CLI output, captured with the actual entrypoint.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FIX = ROOT / "fixtures"

CATALOG_SCHEMA = "coherence.contract-catalog.v1"


def write(root: Path, rel: str, content: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def catalog(root: Path, document: dict) -> None:
    write(root, ".factory/contracts.yaml", json.dumps(document))


def run_freshness(root: Path, args=None) -> str:
    cmd = [sys.executable, "-m", "coherence.navigate", "freshness", "--repo-root", str(root), "--json"]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT.parent.parent)
    return proc.stdout


def contract_findings(root: Path) -> list[dict]:
    data = json.loads(run_freshness(root))
    return [f for f in data["findings"] if f["code"].startswith("CONTRACT_")]


COMMON = {
    "schema": CATALOG_SCHEMA,
    "contracts": [
        {"id": "SCHEMA", "path": "contracts/schema.schema.json", "kind": "json_schema",
         "status": "active", "authority": "spec:SPEC-1", "consumers": ["test:tests/schema_test.py"]},
        {"id": "DEFS", "path": "contracts/defs.schema.json", "kind": "json_schema", "status": "active"},
        {"id": "FIX", "path": "fixtures/seed.json", "kind": "fixture", "status": "active",
         "validates_against": "contract:SCHEMA", "consumers": ["code:backend/app.py"]},
        {"id": "BROKEN", "path": "contracts/broken.schema.json", "kind": "json_schema", "status": "active"},
        {"id": "ORPHAN", "path": "contracts/orphan.json", "kind": "other", "status": "active"},
    ],
}


def full_project(root: Path) -> None:
    """Valid catalog, five declarations, contract files present; no evidence yet
    (validation unavailable for declared consumers)."""
    catalog(root, dict(COMMON))
    write(root, "contracts/schema.schema.json", '{"$ref": "defs.schema.json"}')
    write(root, "contracts/defs.schema.json", '{"type": "object"}')
    write(root, "contracts/broken.schema.json", '{"$ref": "missing.json"}')
    write(root, "contracts/orphan.json", '{"note": "standalone"}')
    write(root, "fixtures/seed.json", '{"a": 1}')
    write(root, "backend/app.py", "x = 1")
    write(root, "tests/schema_test.py", "def test_wire(): pass")


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"

    def reset(name: str) -> Path:
        p = FIX / name
        if p.exists():
            import shutil
            shutil.rmtree(p)
        p.mkdir(parents=True, exist_ok=True)
        return p

    if which in ("all", "valid"):
        root = reset("valid")
        full_project(root)
        print("=== valid (freshness --json, CONTRACT_ only) ===")
        print(json.dumps(contract_findings(root), indent=2))

    if which in ("all", "stale"):
        root = reset("stale")
        full_project(root)
        # Record SCHEMA's current closure as evidence, then change the contract.
        from subprocess import run
        # compute fingerprint via the real API
        import factory.freshness.deps as deps
        fp = deps._contract_closure_fingerprint(root, "SCHEMA")
        rd = root / "evidence/runs/RUN-SC"
        rd.mkdir(parents=True, exist_ok=True)
        manifest = {"run": "RUN-SC", "feature": "FEAT-X", "dependencies": [
            {"kind": "contract", "name": "SCHEMA", "source": "SCHEMA", "digest": fp}]}
        (rd / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        write(root, "contracts/schema.schema.json", '{"$ref": "defs.schema.json", "x": true}')
        print("=== stale (freshness --json, CONTRACT_ only) ===")
        print(json.dumps(contract_findings(root), indent=2))

    if which in ("all", "malformed"):
        root = reset("malformed")
        write(root, ".factory/contracts.yaml", "schema: coherence.contract-catalog.v1\ncontracts: [ not valid\n")
        write(root, "contracts/defs.schema.json", '{"type": "object"}')
        print("=== malformed (freshness --json, CONTRACT_ only) ===")
        print(json.dumps(contract_findings(root), indent=2))

    if which in ("all", "nocatalog"):
        root = reset("nocatalog")
        write(root, "contracts/defs.schema.json", '{"type": "object"}')
        print("=== no catalog (freshness --json, CONTRACT_ only) ===")
        print(json.dumps(contract_findings(root), indent=2))

    print("done")
