from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from coherence.planning.artifacts import (
    ArtifactError,
    build_artifact_manifest,
    read_artifact_manifest,
    sha256_file,
    validate_artifact_manifest,
    write_artifact_manifest,
)

pytestmark = pytest.mark.unit


def _artifacts(root: Path) -> list[dict[str, str]]:
    (root / "docs").mkdir()
    (root / "docs" / "plan.md").write_text("plan", encoding="utf-8")
    (root / "docs" / "spec.md").write_text("spec", encoding="utf-8")
    return [
        {"kind": "spec", "path": "docs/spec.md"},
        {"kind": "plan", "path": "docs/plan.md"},
    ]


def test_build_manifest_hashes_root_relative_files_and_sorts_kinds(tmp_path: Path) -> None:
    manifest = build_artifact_manifest(tmp_path, "run-001", _artifacts(tmp_path))

    assert manifest == {
        "schema": 1,
        "run_id": "run-001",
        "artifacts": [
            {"kind": "plan", "path": "docs/plan.md", "sha256": sha256_file(tmp_path / "docs/plan.md")},
            {"kind": "spec", "path": "docs/spec.md", "sha256": sha256_file(tmp_path / "docs/spec.md")},
        ],
    }
    assert not (tmp_path / ".factory").exists()


def test_write_and_read_manifest_are_run_local_and_hash_bound(tmp_path: Path) -> None:
    manifest = build_artifact_manifest(tmp_path, "run-001", _artifacts(tmp_path))

    path = write_artifact_manifest(tmp_path, "run-001", manifest)

    assert path == tmp_path / ".factory" / "planning" / "run-001" / "artifacts.json"
    assert read_artifact_manifest(tmp_path, "run-001") == manifest
    assert validate_artifact_manifest(tmp_path, manifest) == manifest


@pytest.mark.parametrize(
    ("artifacts", "reason"),
    [
        ([{"kind": "plan", "path": "docs/missing.md"}], "artifact missing: docs/missing.md"),
        ([{"kind": "plan", "path": "../outside.md"}], "artifact path is unsafe: ../outside.md"),
        ([{"kind": "plan", "path": "docs\\plan.md"}], "artifact path is unsafe: docs\\plan.md"),
        (
            [{"kind": "plan", "path": "docs/plan.md"}, {"kind": "plan", "path": "docs/spec.md"}],
            "duplicate artifact kind: plan",
        ),
        (
            [{"kind": "plan", "path": "docs/plan.md"}, {"kind": "spec", "path": "docs/plan.md"}],
            "duplicate artifact path: docs/plan.md",
        ),
    ],
)
def test_build_rejects_invalid_sources_with_stable_reasons(
    tmp_path: Path, artifacts: list[dict[str, str]], reason: str
) -> None:
    _artifacts(tmp_path)

    with pytest.raises(ArtifactError, match=f"^{re.escape(reason)}$"):
        build_artifact_manifest(tmp_path, "run-001", artifacts)


def test_read_rejects_malformed_json(tmp_path: Path) -> None:
    path = tmp_path / ".factory" / "planning" / "run-001" / "artifacts.json"
    path.parent.mkdir(parents=True)
    path.write_text("{not json", encoding="utf-8")

    with pytest.raises(ArtifactError, match="^artifact manifest JSON is unreadable$"):
        read_artifact_manifest(tmp_path, "run-001")


def test_validate_rejects_malformed_hash_and_detects_content_mutation(tmp_path: Path) -> None:
    manifest = build_artifact_manifest(tmp_path, "run-001", _artifacts(tmp_path))
    malformed = json.loads(json.dumps(manifest))
    malformed["artifacts"][0]["sha256"] = "A" * 64

    with pytest.raises(ArtifactError, match="^artifact sha256 is invalid: docs/plan.md$"):
        validate_artifact_manifest(tmp_path, malformed)

    (tmp_path / "docs" / "plan.md").write_text("changed", encoding="utf-8")
    with pytest.raises(ArtifactError, match="^artifact changed: docs/plan.md$"):
        validate_artifact_manifest(tmp_path, manifest)
