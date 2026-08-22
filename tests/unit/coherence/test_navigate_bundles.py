from __future__ import annotations

import json
from pathlib import Path

import pytest


pytestmark = pytest.mark.unit


def _seed_feature(root: Path) -> None:
    (root / "docs" / "features").mkdir(parents=True)
    (root / "requirements").mkdir()
    (root / "tasks").mkdir()
    (root / "docs" / "features" / "FEAT-001.md").write_text(
        "---\n"
        "id: FEAT-001\n"
        "title: Navigation surface\n"
        "requirements: [SR-001]\n"
        "---\n",
        encoding="utf-8",
    )
    (root / "requirements" / "SR-001.md").write_text(
        "---\n"
        "id: SR-001\n"
        "title: Navigation is reachable\n"
        "binding: {experiment: smoke, metric: reachability, assert: '>= 1'}\n"
        "---\n",
        encoding="utf-8",
    )
    (root / "tasks" / "T-001.md").write_text(
        "---\n"
        "id: T-001\n"
        "title: Add navigation route\n"
        "satisfies: [SR-001]\n"
        "---\n",
        encoding="utf-8",
    )


def test_create_draft_bundle_derives_sorted_trace_members_without_mutating_authority(tmp_path):
    from coherence.navigate.bundles import create_draft_bundle

    _seed_feature(tmp_path)
    output = tmp_path / "drafts" / "navigation.json"

    result = create_draft_bundle(tmp_path, "feat:FEAT-001", output)

    assert result == {
        "id": "bundle:FEAT-001",
        "label": "Navigation surface draft",
        "members": ["feat:FEAT-001", "sr:SR-001", "task:T-001"],
        "draft": True,
    }
    assert json.loads(output.read_text(encoding="utf-8")) == result
    assert (tmp_path / "docs" / "features" / "FEAT-001.md").read_text(encoding="utf-8").endswith(
        "---\n"
    )


def test_create_draft_bundle_requires_destination_and_refuses_existing_output(tmp_path):
    from coherence.navigate.bundles import create_draft_bundle

    _seed_feature(tmp_path)
    with pytest.raises(ValueError, match="output"):
        create_draft_bundle(tmp_path, "feat:FEAT-001", None)

    output = tmp_path / "draft.json"
    output.write_text("original", encoding="utf-8")
    with pytest.raises(FileExistsError):
        create_draft_bundle(tmp_path, "feat:FEAT-001", output)
    assert output.read_text(encoding="utf-8") == "original"

    create_draft_bundle(tmp_path, "feat:FEAT-001", output, force=True)
    assert json.loads(output.read_text(encoding="utf-8"))["draft"] is True


def test_navigate_bundle_new_cli_writes_schema_compatible_draft(tmp_path, capsys):
    from coherence.navigate.cli import main

    _seed_feature(tmp_path)
    output = tmp_path / "draft.json"

    rc = main(
        [
            "bundle",
            "new",
            "--from",
            "feat:FEAT-001",
            "--output",
            str(output),
            "--repo-root",
            str(tmp_path),
            "--json",
        ]
    )

    assert rc == 0
    assert json.loads(capsys.readouterr().out)["bundle"]["draft"] is True
    assert main(
        ["bundle", "check", "--draft", str(output), "--repo-root", str(tmp_path), "--json"]
    ) == 0


def test_membership_is_the_canonical_coverage_gate_alias(tmp_path, capsys):
    from coherence.navigate.cli import cmd_coverage, main

    _seed_feature(tmp_path)
    expected = cmd_coverage(tmp_path)

    legacy_rc = main(["coverage", "--gate", "--repo-root", str(tmp_path), "--json"])
    legacy_payload = json.loads(capsys.readouterr().out)
    canonical_rc = main(["membership", "--gate", "--repo-root", str(tmp_path), "--json"])
    canonical_payload = json.loads(capsys.readouterr().out)

    assert legacy_rc == canonical_rc == 2
    assert legacy_payload == canonical_payload == expected
