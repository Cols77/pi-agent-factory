from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from factory.evidence.artifacts import LocalArtifactStore
from factory.evidence.cli import main
from factory.evidence.manifests import load_run_manifest, write_run_manifest
from factory.evidence.reconcile import ReconcileKind, reconcile, repair_reconciliation
from factory.orchestrator.journal import RunCheckpoint, RunJournal

pytestmark = pytest.mark.unit


def _repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    (repo / "tasks").mkdir()
    (repo / "tasks" / "T-001-example.md").write_text(
        "---\nid: T-001\ntitle: Example\nstatus: done\ndod:\n  - works\n---\nbody\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=repo, check=True)
    return repo


def _manifest(repo, run_id="run-1"):
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()
    return {
        "schema_version": 2,
        "run_id": run_id,
        "task_id": "T-001",
        "started_at": "2026-08-07T12:00:00Z",
        "ended_at": "2026-08-07T12:01:00Z",
        "start_commit": head,
        "result_commit": head,
        "outcome": "completed",
        "inputs": {
            "task": {"path": "tasks/T-001-example.md", "sha256": "c" * 64},
            "requirements": [],
            "factory_config_sha256": "d" * 64,
        },
        "dependencies": [],
        "implementation": {
            "changed_files": [],
            "patch": {"sha256": "e" * 64, "size": 0, "media_type": "text/x-diff"},
        },
        "validation": [],
        "reviews": [],
        "decisions": [],
        "publication": {"state": "local", "errors": []},
    }


def _commit_all(repo):
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "fixture"], cwd=repo, check=True)


def test_completed_task_without_manifest_is_never_given_inferred_provenance(tmp_path):
    repo = _repo(tmp_path)
    items = reconcile(repo)
    missing = next(item for item in items if item.kind is ReconcileKind.MISSING_EVIDENCE)
    assert missing.subject == "T-001"
    assert "no validated evidence" in missing.detail


def test_manifest_inventory_reports_missing_blob_and_is_deterministically_sorted(tmp_path):
    repo = _repo(tmp_path)
    write_run_manifest(repo / "evidence", _manifest(repo))
    _commit_all(repo)
    items = reconcile(repo)
    assert [item.kind for item in items] == [ReconcileKind.MISSING_BLOB]
    assert items[0].subject == "e" * 64


def test_changed_recorded_file_reports_stale_validation(tmp_path):
    repo = _repo(tmp_path)
    manifest = _manifest(repo)
    manifest["dependencies"] = [
        {
            "name": "task:T-001",
            "kind": "file",
            "digest": "sha256:" + "0" * 64,
            "source": "tasks/T-001-example.md",
        }
    ]
    write_run_manifest(repo / "evidence", manifest)
    _commit_all(repo)
    kinds = [item.kind for item in reconcile(repo)]
    assert ReconcileKind.STALE_VALIDATION in kinds


def test_unattributed_worktree_change_is_reported_without_task_assignment(tmp_path):
    repo = _repo(tmp_path)
    (repo / "unexpected.txt").write_text("external", encoding="utf-8")
    item = next(item for item in reconcile(repo) if item.kind is ReconcileKind.UNATTRIBUTED_CHANGE)
    assert item.subject == "working-tree"
    assert item.repairable is False


def test_interrupted_checkpoint_suppresses_unattributed_guess(tmp_path):
    repo = _repo(tmp_path)
    run_dir = repo / "sessions" / ".factory-runs" / "by-session" / "run-1"
    RunJournal(run_dir).checkpoint(
        RunCheckpoint(
            1, "run-1", "T-001", "validation", 1, {}, "a" * 40, "a" * 40,
            "f" * 64, None, [], {}, None, [], "process_exit"
        )
    )
    items = reconcile(repo)
    assert ReconcileKind.INTERRUPTED_RUN in {item.kind for item in items}
    assert ReconcileKind.UNATTRIBUTED_CHANGE not in {item.kind for item in items}


def test_legacy_review_is_repairable_only_with_explicit_identity(tmp_path):
    repo = _repo(tmp_path)
    path = repo / "sessions" / ".factory-transcripts" / "old" / "review-history.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"task_id": "T-001", "run_id": "r", "start_commit": "a"}), encoding="utf-8")
    item = next(item for item in reconcile(repo) if item.kind is ReconcileKind.LEGACY_REVIEW)
    assert item.repairable is True


def test_publication_retry_is_durable_and_idempotent(tmp_path):
    repo = _repo(tmp_path)
    store = LocalArtifactStore(repo / ".factory" / "artifacts" / "objects", repo / "published")
    ref = store.put(b"hello", "text/plain")
    (repo / "published").write_text("blocked", encoding="utf-8")

    first = store.publish(ref.sha256)
    assert first.state == "queued"
    items = reconcile(repo)
    publication = next(item for item in items if item.kind is ReconcileKind.PUBLICATION_FAILED)
    assert publication.subject == ref.sha256
    assert publication.repairable is True

    (repo / "published").unlink()
    (repo / "published").mkdir()
    actions = repair_reconciliation(repo, items, reason=None)
    assert actions[0]["kind"] == "retry_publication"
    assert store.publication_record(ref.sha256)["state"] == "published"
    assert not any(item.kind is ReconcileKind.PUBLICATION_FAILED for item in reconcile(repo))


def test_publication_retry_refuses_when_no_target_is_recorded(tmp_path):
    repo = _repo(tmp_path)
    store = LocalArtifactStore(repo / ".factory" / "artifacts" / "objects")
    ref = store.put(b"hello", "text/plain")
    queue_dir = repo / ".factory" / "artifacts" / "publish-queue"
    queue_dir.mkdir(parents=True)
    (queue_dir / f"{ref.sha256}.json").write_text(
        json.dumps({"sha256": ref.sha256, "state": "queued", "errors": []}),
        encoding="utf-8",
    )

    item = next(item for item in reconcile(repo) if item.kind is ReconcileKind.PUBLICATION_FAILED)
    assert item.repairable is False
    assert item.blocking is False
    assert "no real configured publication target" in item.detail
    assert repair_reconciliation(repo, [item], reason=None) == []


def test_disposable_index_rebuild_is_bounded_to_real_kb_index(tmp_path):
    repo = _repo(tmp_path)
    kb_dir = repo / "kb"
    kb_dir.mkdir()
    source = Path(__file__).resolve().parents[3] / "kb" / "kb-0001-example-entry.md"
    (kb_dir / source.name).write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    (kb_dir / "index.json").write_text("{}", encoding="utf-8")

    item = next(item for item in reconcile(repo) if item.kind is ReconcileKind.DISPOSABLE_INDEX)
    assert item.repairable is True
    actions = repair_reconciliation(repo, [item], reason=None)
    assert actions[0]["kind"] == "rebuild_disposable_index"
    assert json.loads((kb_dir / "index.json").read_text(encoding="utf-8"))["kb-0001"]["status"] == "active"


def test_legacy_review_migration_requires_explicit_provenance_and_updates_manifest(tmp_path):
    repo = _repo(tmp_path)
    manifest_path = write_run_manifest(repo / "evidence", _manifest(repo))
    legacy = repo / "sessions" / ".factory-transcripts" / "run-1" / "review-history.json"
    legacy.parent.mkdir(parents=True)
    legacy.write_text(
        json.dumps(
            {
                "task_id": "T-001",
                "run_id": "run-1",
                "start_commit": subprocess.run(
                    ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
                ).stdout.strip(),
                "decision": "approve",
                "annotations": [],
            }
        ),
        encoding="utf-8",
    )

    item = next(item for item in reconcile(repo) if item.kind is ReconcileKind.LEGACY_REVIEW)
    assert item.repairable is True
    actions = repair_reconciliation(repo, [item], reason=None)
    assert actions[0]["kind"] == "migrate_legacy_review"
    loaded = load_run_manifest(manifest_path)
    assert loaded["reviews"][0]["source"] == item.source
    assert all(candidate.kind is not ReconcileKind.LEGACY_REVIEW for candidate in reconcile(repo))


def test_legacy_review_refuses_when_start_commit_is_missing(tmp_path):
    repo = _repo(tmp_path)
    legacy = repo / "sessions" / ".factory-transcripts" / "run-1" / "review-history.json"
    legacy.parent.mkdir(parents=True)
    legacy.write_text(json.dumps({"task_id": "T-001", "run_id": "run-1"}), encoding="utf-8")
    item = next(item for item in reconcile(repo) if item.kind is ReconcileKind.LEGACY_REVIEW)
    assert item.repairable is False
    assert repair_reconciliation(repo, [item], reason=None) == []


def test_reconcile_cli_emits_json_and_uses_pending_exit_code(tmp_path, capsys):
    repo = _repo(tmp_path)
    assert main(["reconcile", "--repo", str(repo), "--json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["items"][0]["kind"] == "missing_evidence"


def test_repair_abandons_only_explicit_interrupted_run_with_reason(tmp_path, capsys):
    repo = _repo(tmp_path)
    run_dir = repo / "sessions" / ".factory-runs" / "by-session" / "run-1"
    RunJournal(run_dir).checkpoint(
        RunCheckpoint(
            1, "run-1", "T-001", "validation", 1, {}, "a" * 40, "a" * 40,
            "f" * 64, None, [], {}, None, [], "process_exit"
        )
    )
    assert main([
        "reconcile", "--repo", str(repo), "--repair", "--reason", "superseded", "--json"
    ]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["repairs"][0]["kind"] == "abandon_interrupted_run"
    assert (run_dir / "abandoned.json").exists()
    assert all(item["kind"] != "interrupted_run" for item in payload["items"])


def test_repair_refuses_interrupted_run_without_reason(tmp_path, capsys):
    repo = _repo(tmp_path)
    run_dir = repo / "sessions" / ".factory-runs" / "by-session" / "run-1"
    RunJournal(run_dir).checkpoint(
        RunCheckpoint(
            1, "run-1", "T-001", "validation", 1, {}, "a" * 40, "a" * 40,
            "f" * 64, None, [], {}, None, [], "process_exit"
        )
    )
    assert main(["reconcile", "--repo", str(repo), "--repair", "--json"]) == 2
    assert "requires --reason" in capsys.readouterr().err


def test_gate_ignores_warnings_unless_strict(tmp_path, capsys):
    repo = _repo(tmp_path)
    task = repo / "tasks" / "T-001-example.md"
    task.write_text(task.read_text(encoding="utf-8").replace("status: done", "status: todo"), encoding="utf-8")
    _commit_all(repo)
    (repo / "unexpected.txt").write_text("external", encoding="utf-8")
    assert main(["reconcile", "--repo", str(repo), "--gate", "--json"]) == 0
    capsys.readouterr()
    assert main([
        "reconcile", "--repo", str(repo), "--gate", "--strict", "--json"
    ]) == 1


def test_reconcile_cli_returns_zero_for_clean_todo_repository(tmp_path, capsys):
    repo = _repo(tmp_path)
    task = repo / "tasks" / "T-001-example.md"
    task.write_text(task.read_text(encoding="utf-8").replace("status: done", "status: todo"), encoding="utf-8")
    _commit_all(repo)
    assert main(["reconcile", "--repo", str(repo), "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {"items": [], "repairs": []}
