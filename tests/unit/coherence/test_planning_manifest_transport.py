from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from coherence.planning.cli import main

pytestmark = pytest.mark.unit


def test_manifest_transport_writes_only_canonical_manifest(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "requirement.md"
    source.write_text("Explicitly authored requirement.\n", encoding="utf-8")
    artifacts = [{"kind": "requirements", "path": "requirement.md",
                  "sha256": hashlib.sha256(source.read_bytes()).hexdigest()}]

    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("manifest transport must not launch subprocesses")

    monkeypatch.setattr(subprocess, "run", forbidden)
    assert main(["write-artifact-manifest", "--project-root", str(tmp_path),
                 "--run-id", "run-001", "--artifacts-json", json.dumps(artifacts), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {"schema": 2, "run_id": "run-001", "ok": True,
                       "action": "write-artifact-manifest",
                       "manifest": ".factory/planning/run-001/artifacts.json"}
    target = tmp_path / payload["manifest"]
    assert json.loads(target.read_text(encoding="utf-8")) == {
        "schema": 1, "run_id": "run-001", "artifacts": artifacts,
    }
    assert sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*")
                  if path.is_file()) == [payload["manifest"], "requirement.md"]


@pytest.mark.parametrize("run_id,artifacts_json", [
    ("../outside", "[]"), ("bad:id", "[]"), ("run-001", "{}"),
    ("run-001", "NaN"), ("run-001", '[{"kind":"spec","kind":"plan"}]'),
    ("run-001", '[{"kind":"requirements","path":"requirement.md"}]'),
    ("run-001", json.dumps([{"kind": "requirements", "path": "../requirement.md", "sha256": "a" * 64}])),
    ("run-001", json.dumps([{"kind": "requirements", "path": "requirement.md", "sha256": "a" * 64}])),
    ("run-001", json.dumps([{"kind": "requirements", "path": "requirement.md", "sha256": "invalid"}])),
])
def test_manifest_transport_rejects_invalid_input_without_writing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], run_id: str, artifacts_json: str,
) -> None:
    (tmp_path / "requirement.md").write_text("Authored requirement.\n", encoding="utf-8")
    assert main(["write-artifact-manifest", "--project-root", str(tmp_path),
                 "--run-id", run_id, "--artifacts-json", artifacts_json, "--json"]) == 1
    assert json.loads(capsys.readouterr().out)["blocked"] is True
    assert not (tmp_path / ".factory").exists()


def test_planning_cli_rejects_abbreviated_project_root_option() -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["status", "--run-id", "run-001", "--project=/override"])

    assert exc_info.value.code == 2
