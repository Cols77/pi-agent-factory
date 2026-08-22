from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest


pytestmark = pytest.mark.unit


def test_navigate_and_presentation_preserve_scope_and_stale_snapshot_truth(tmp_path):
    from coherence.navigate.queries import parse_scope_ref
    from coherence.navigate.snapshots import (
        resolve_navigation_snapshot,
        write_navigation_snapshot,
    )
    from coherence.presentation.router import resolve_intent

    plan = tmp_path / "plans" / "PLAN-001.md"
    plan.parent.mkdir()
    plan.write_text("# Plan\n\nCurrent content.\n", encoding="utf-8")

    scope = parse_scope_ref("file:plans/PLAN-001.md")
    assert scope.ref == "file:plans/PLAN-001.md"
    current = resolve_navigation_snapshot(tmp_path, scope.ref)
    assert current.freshness == "fresh"
    assert current.artifact_ref is not None
    assert current.resolver_cmd is None

    write_navigation_snapshot(tmp_path, scope.ref)
    plan.write_text("# Plan\n\nChanged content.\n", encoding="utf-8")
    stale = resolve_navigation_snapshot(tmp_path, scope.ref)
    assert stale.freshness == "stale"
    assert stale.resolver_cmd
    assert stale.artifact_ref is not None

    intent = resolve_intent(tmp_path, "file:plans/PLAN-001.md")
    assert intent.artifact == "file:plans/PLAN-001.md"


def test_coherence_navigation_and_presentation_do_not_import_factory():
    for package in ("navigate", "presentation"):
        package_root = Path("src/coherence") / package
        for path in package_root.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    modules = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    modules = [node.module or ""]
                else:
                    continue
                assert not any(
                    (module == "factory" or module.startswith("factory."))
                    and not (
                        module.startswith("factory.memory")
                        or module.startswith("factory.delta")
                        or module.startswith("factory.freshness")
                    )
                    for module in modules
                ), path


def test_stale_snapshot_report_is_machine_readable(tmp_path):
    from coherence.navigate.snapshots import resolve_navigation_snapshot

    code = tmp_path / "src" / "example.py"
    code.parent.mkdir()
    code.write_text("def current():\n    return True\n", encoding="utf-8")
    metadata = tmp_path / ".factory" / "navigation-snapshots"
    metadata.mkdir(parents=True)
    (metadata / "codemap-src-example.py.json").write_text(
        json.dumps({
            "ref": "codemap:src/example.py",
            "fingerprint": "sha256:" + "0" * 64,
            "location": "src/example.py",
        }),
        encoding="utf-8",
    )

    result = resolve_navigation_snapshot(tmp_path, "codemap:src/example.py")
    assert result.freshness == "stale"
    assert "codemap:src/example.py" in result.ref
    assert result.resolver_cmd


def test_stale_snapshot_blocks_route_content_and_presentation_target(tmp_path):
    from coherence.navigate.cli import cmd_brief
    from coherence.navigate.snapshots import write_navigation_snapshot
    from coherence.presentation.router import resolve_intent

    source = tmp_path / "src" / "route.py"
    source.parent.mkdir(parents=True)
    source.write_text("return 'current'\n", encoding="utf-8")
    ref = "file:src/route.py"
    write_navigation_snapshot(tmp_path, ref)
    source.write_text("return 'changed'\n", encoding="utf-8")

    route = cmd_brief(tmp_path, ref)
    assert route["stale"] is True
    assert route["snapshot"]["ref"] == ref
    assert route["resolver"]
    assert "changed" not in json.dumps(route)

    intent = resolve_intent(tmp_path, ref)
    presented = {
        "artifact": intent.artifact,
        "adapter": intent.adapter,
        "target": intent.target,
        "note": intent.note,
        "snapshot": intent.snapshot_ref,
    }
    assert presented["adapter"] is None
    assert presented["target"] is None
    assert presented["snapshot"] == ref
