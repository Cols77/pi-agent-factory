# tests/unit/coverage/test_coherence_parity.py
"""Migration-safety tests for Coherence Increment 4, Task 1: coverage/audit
moves from factory.coverage to coherence.audit, and cuts the overlap
computation over to substrate.codemap.compute_overlap (already the only
overlap implementation in this codebase since Increment 1C -- there is no
separate "old private walker" left to diverge from it; see
tests/unit/substrate/test_codemap_imports.py's own factory.coverage.imports
parity suite for that algorithm-level guarantee).

This file instead guards the things specific to *this* move:
  1. Old (factory.coverage) and new (coherence.audit) import paths produce
     byte-identical audit/consolidate/gate/report output for the same
     feature fixtures -- expected trivially once factory.coverage.* becomes
     a `sys.modules[__name__] = _canonical` alias (see
     tests/unit/coherence/test_legacy_shims.py for the alias contract
     itself), but exercised here end to end through the real cmd_* pipeline
     rather than as a bare identity check.
  2. A binding test selection that no longer exists on disk is reported as
     `{"ok": false, "reason": "binding test selection missing", ...}`,
     distinct from a selection that resolves fine but simply has zero
     overlap with the changed files (which carries no "reason" key at all).
  3. coherence.audit's own source only reaches import-overlap through
     substrate.codemap.imports.compute_overlap -- never through the legacy
     factory.coverage.imports shim.
"""
from __future__ import annotations

import ast
import json
import warnings
from pathlib import Path

import pytest

with warnings.catch_warnings():
    warnings.simplefilter("ignore", DeprecationWarning)
    from factory.coverage import cli as legacy_cli
from coherence.audit import cli as canonical_cli

pytestmark = pytest.mark.unit

AUDIT_ROOT = Path(__file__).resolve().parents[3] / "src" / "coherence" / "audit"


def _feat_scope(root: Path, *, experiment: str = "tests/test_x.py") -> None:
    """Minimal fixture with one SR, one task, one manifest -- same shape as
    tests/unit/coverage/test_cli.py's `_feat_scope`."""
    (root / "docs" / "features").mkdir(parents=True)
    (root / "docs" / "features" / "FEAT-001.md").write_text(
        "---\nid: FEAT-001\ntitle: Test\nrequirements: [SR-001]\n---\n"
    )
    (root / "requirements").mkdir()
    (root / "requirements" / "SR-001.md").write_text(
        "---\nid: SR-001\ntitle: X\nstatement: shall do X\ndomain: behavioral\n"
        f"binding:\n  harness: sim-testbench\n  experiment: {experiment}\n"
        "  metric: unit_pass_rate\n  trials: 1\n  assert: '== 1.0'\nchecksum: null\n---\n"
    )
    (root / "tasks").mkdir()
    (root / "tasks" / "T-001.md").write_text(
        "---\nid: T-001\ntitle: T\ndeliverables: []\nsatisfies: [SR-001]\n---\n"
    )
    (root / "evidence" / "runs").mkdir(parents=True)
    manifest = {
        "schema_version": 2, "run_id": "RUN-001", "task_id": "T-001",
        "started_at": "2026-08-01T00:00:00Z", "ended_at": "2026-08-01T01:00:00Z",
        "start_commit": "a" * 40, "result_commit": "b" * 40, "outcome": "completed",
        "inputs": {"task": {"path": "tasks/T-001.md", "sha256": "0" * 64}, "requirements": [], "factory_config_sha256": "0" * 64},
        "implementation": {
            "changed_files": ["src/x.py"],
            "patch": {"sha256": "0" * 64, "size": 0, "media_type": "application/json"},
        },
        "dependencies": [], "validation": [], "reviews": [], "decisions": [],
        "publication": {"state": "local", "errors": []},
    }
    (root / "evidence" / "runs" / "RUN-001.json").write_text(json.dumps(manifest), encoding="utf-8")


def _verdict() -> dict:
    return {
        "sr_id": "SR-001", "implemented": True, "honest": True,
        "confidence": "high", "margin": None,
        "reasoning": "Test exercises the preempt path.",
        "checked": ["preempt path"], "assumed": ["fixture"],
        "verify": [],
    }


def _strip_volatile(payload: dict) -> dict:
    """Drop timestamp fields that legitimately differ between two separate
    calls (wall-clock generated_at), leaving everything else comparable."""
    stripped = dict(payload)
    stripped.pop("generated_at", None)
    return stripped


def _strip_generated_line(text: str) -> str:
    return "\n".join(line for line in text.splitlines() if not line.startswith("Generated:"))


# -- 1. Old and new import paths produce identical pipeline output. --------


def test_cmd_audit_matches_between_factory_coverage_and_coherence_audit(tmp_path: Path) -> None:
    legacy_root = tmp_path / "legacy"
    canonical_root = tmp_path / "canonical"
    _feat_scope(legacy_root)
    _feat_scope(canonical_root)

    legacy = legacy_cli.cmd_audit(legacy_root, "FEAT-001", run_id="parity-run")
    canonical = canonical_cli.cmd_audit(canonical_root, "FEAT-001", run_id="parity-run")

    assert _strip_volatile(legacy) == _strip_volatile(canonical)
    assert "SR-001" in canonical["srs"]


def test_full_pipeline_matches_between_factory_coverage_and_coherence_audit(tmp_path: Path) -> None:
    legacy_root = tmp_path / "legacy"
    canonical_root = tmp_path / "canonical"
    _feat_scope(legacy_root)
    _feat_scope(canonical_root)

    legacy_cli.cmd_audit(legacy_root, "FEAT-001", run_id="parity-run")
    canonical_cli.cmd_audit(canonical_root, "FEAT-001", run_id="parity-run")

    legacy_cli.cmd_verdict(legacy_root, "FEAT-001", "parity-run", "SR-001", _verdict())
    canonical_cli.cmd_verdict(canonical_root, "FEAT-001", "parity-run", "SR-001", _verdict())

    legacy_report = legacy_cli.cmd_consolidate(legacy_root, "FEAT-001", "parity-run")
    canonical_report = canonical_cli.cmd_consolidate(canonical_root, "FEAT-001", "parity-run")
    assert _strip_volatile(legacy_report) == _strip_volatile(canonical_report)
    assert legacy_report["states"] == canonical_report["states"]

    legacy_gate = legacy_cli.cmd_gate(legacy_root, "FEAT-001", "parity-run")
    canonical_gate = canonical_cli.cmd_gate(canonical_root, "FEAT-001", "parity-run")
    assert legacy_gate == canonical_gate == "pass"

    legacy_human = legacy_cli.cmd_report(legacy_root, "FEAT-001", "parity-run")
    canonical_human = canonical_cli.cmd_report(canonical_root, "FEAT-001", "parity-run")
    # Both reports differ only in their "Generated: <timestamp>" line.
    assert _strip_generated_line(legacy_human) == _strip_generated_line(canonical_human)


# -- 2. A missing binding-test selection is distinguishable from a --------
# -- resolvable selection that simply has zero overlap. --------------------


def test_binding_test_selection_missing_reports_a_distinct_reason(tmp_path: Path) -> None:
    """The binding's experiment path (tests/test_ghost.py) is never created."""
    _feat_scope(tmp_path, experiment="tests/test_ghost.py")

    result = canonical_cli.cmd_audit(tmp_path, "FEAT-001", run_id="ghost-run")

    assert result["overlaps"]["SR-001"] == {
        "ok": False,
        "reason": "binding test selection missing",
        "test_source": None,
        "reached_files": (),
        "changed_files": ("src/x.py",),
        "overlap": (),
        "unresolved": (),
    }


def test_zero_overlap_is_not_conflated_with_missing_selection(tmp_path: Path) -> None:
    """The binding's experiment path exists and resolves fine, but its import
    closure never reaches the changed file -- a real, distinct failure mode
    from a missing selection, and must not carry a "reason" key."""
    _feat_scope(tmp_path, experiment="tests/test_x.py")
    test_path = tmp_path / "tests" / "test_x.py"
    test_path.parent.mkdir(parents=True)
    test_path.write_text("def test_nothing():\n    assert True\n", encoding="utf-8")

    result = canonical_cli.cmd_audit(tmp_path, "FEAT-001", run_id="zero-overlap-run")

    overlap = result["overlaps"]["SR-001"]
    assert overlap["ok"] is False
    assert overlap["overlap"] == ()
    # A resolved selection reports a real test_source -- the missing-selection
    # case above reports None instead. Not the same string form as the SR's
    # declared binding path (compute_overlap doesn't root-relativize it), but
    # unambiguously "found", which is exactly what distinguishes it.
    assert overlap["test_source"] is not None
    assert "reason" not in overlap


# -- 3. coherence.audit's overlap computation only ever reaches ------------
# -- substrate.codemap.imports.compute_overlap -- never the legacy shim. ---


def _module_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_coherence_audit_cli_imports_compute_overlap_only_from_substrate_codemap() -> None:
    imports = _module_names(AUDIT_ROOT / "cli.py")
    assert "substrate.codemap.imports" in imports
    assert not any(name.startswith("factory.coverage") for name in imports)


def test_no_coherence_audit_module_imports_the_legacy_imports_shim() -> None:
    modules = sorted(AUDIT_ROOT.glob("*.py"))
    assert modules  # sanity: the package isn't empty
    imports = set().union(*(_module_names(path) for path in modules))
    assert "factory.coverage.imports" not in imports


# -- 4. Every current Python-import overlap fixture, exercised through the --
# -- full cmd_audit pipeline (not just the bare function), still lands on --
# -- the truth values substrate.codemap.compute_overlap gives directly. ----


def test_cmd_audit_overlap_matches_direct_compute_overlap_for_the_same_fixture(
    tmp_path: Path,
) -> None:
    from substrate.codemap.imports import compute_overlap

    _feat_scope(tmp_path)
    (tmp_path / "tests").mkdir()
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "x.py").write_text("def implemented():\n    return True\n", encoding="utf-8")
    (tmp_path / "tests" / "test_x.py").write_text(
        "from src.x import implemented\n\n\ndef test_x():\n    assert implemented()\n",
        encoding="utf-8",
    )

    result = canonical_cli.cmd_audit(tmp_path, "FEAT-001", run_id="direct-run")
    via_pipeline = result["overlaps"]["SR-001"]

    direct = compute_overlap(tmp_path, "tests/test_x.py", ["src/x.py"])

    assert via_pipeline["ok"] == direct.ok
    assert via_pipeline["overlap"] == direct.overlap
