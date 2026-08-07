from __future__ import annotations

import json
import subprocess

import pytest

from factory.evidence.artifacts import LocalArtifactStore
from factory.evidence.finalize import finalize_run_evidence
from factory.evidence.manifests import load_run_manifest
from factory.orchestrator.git_ops import SubprocessGitOps
from factory.orchestrator.ledger import load_tasks
from factory.orchestrator.types import NodeEvent, TaskResult

pytestmark = pytest.mark.unit


def _repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    (repo / "tasks").mkdir()
    (repo / "requirements").mkdir()
    (repo / ".factory").mkdir()
    (repo / "src").mkdir()
    (repo / "docs" / "superpowers" / "plans").mkdir(parents=True)
    (repo / "docs" / "superpowers" / "specs").mkdir(parents=True)
    (repo / "docs" / "superpowers" / "specs" / "design.md").write_text(
        "# Design\n", encoding="utf-8"
    )
    (repo / "docs" / "superpowers" / "plans" / "plan.md").write_text(
        "# Plan\n\nSpec: docs/superpowers/specs/design.md\n", encoding="utf-8"
    )
    (repo / "tasks" / "T-001-example.md").write_text(
        "---\nid: T-001\ntitle: Example\nstatus: todo\ndod:\n  - works\nsatisfies:\n  - SR-001\nsource_plan: plan.md\n---\nbody\n",
        encoding="utf-8",
    )
    (repo / "requirements" / "SR-001.md").write_text(
        "---\nid: SR-001\ntitle: Requirement\nstatement: It works\ndomain: core\nbinding:\n  harness: sim-testbench\n  experiment: demo\n  metric: score\n  assert: '>= 1'\n---\nbody\n",
        encoding="utf-8",
    )
    (repo / ".factory" / "factory.yaml").write_text("gates: {}\n", encoding="utf-8")
    (repo / "src" / "a.py").write_text("before = True\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=repo, check=True)
    return repo


def _transcript(repo):
    transcript = repo / "sessions" / ".factory-transcripts" / "run-1"
    reviews = transcript / "reviews"
    reviews.mkdir(parents=True)
    (reviews / "review-001.json").write_text(
        json.dumps(
            {
                "version": 1,
                "reviewed_at": "2026-08-07T12:00:30Z",
                "task_id": "T-001",
                "start_commit": "a" * 40,
                "decision": "reject",
                "annotations": [{"file": "src/a.py", "body": "explain", "line": 1}],
                "reviewed_files": ["src/a.py"],
                "diff": "diff --git a/src/a.py b/src/a.py\n+after = True\n",
                "diff_error": None,
            }
        ),
        encoding="utf-8",
    )
    (transcript / "review-guide.json").write_text(
        json.dumps({"confidence": "high", "verify": []}), encoding="utf-8"
    )
    (transcript / "validation-report.json").write_text(
        json.dumps({"requirements": [{"id": "SR-001", "passed": True}]}),
        encoding="utf-8",
    )
    return transcript


def test_finalize_captures_implementation_reviews_validation_and_inputs(tmp_path):
    repo = _repo(tmp_path)
    ops = SubprocessGitOps()
    start = ops.head_commit(repo)
    (repo / "src" / "a.py").write_text("after = True\n", encoding="utf-8")
    assert ops.commit_all(repo, "implementation") is True
    result_commit = ops.head_commit(repo)
    task = load_tasks(repo / "tasks")[0]
    result = TaskResult(
        "T-001",
        "Example",
        "completed",
        1,
        [NodeEvent("dev", "pass")],
        True,
        start_commit=start,
        result_commit=result_commit,
    )
    store = LocalArtifactStore(repo / ".factory" / "artifacts" / "objects")

    path = finalize_run_evidence(
        repo_root=repo,
        run_id="run-1",
        task=task,
        result=result,
        transcript_dir=_transcript(repo),
        store=store,
        evidence_dir=repo / "evidence",
        git_ops=ops,
        started_at="2026-08-07T12:00:00Z",
        ended_at="2026-08-07T12:01:00Z",
    )

    manifest = load_run_manifest(path)
    assert manifest["result_commit"] == result_commit
    assert manifest["implementation"]["changed_files"] == ["src/a.py"]
    patch_hash = manifest["implementation"]["patch"]["sha256"]
    assert b"+after = True" in store.get(patch_hash)
    assert manifest["inputs"]["requirements"][0]["id"] == "SR-001"
    assert [item["name"] for item in manifest["dependencies"]] == [
        "candidate-tree",
        "evidence-schema",
        "factory-config",
        "requirement:SR-001",
        "source-plan:plan:plan.md",
        "source-spec:spec:design.md",
        "task:T-001",
        "validator:SR-001",
    ]
    assert manifest["reviews"][0]["decision"] == "reject"
    assert "diff" not in manifest["reviews"][0]
    assert store.has(manifest["reviews"][0]["patch"]["sha256"])
    assert store.has(manifest["reviews"][0]["guide"]["sha256"])
    assert manifest["validation"][0]["requirements"][0]["passed"] is True
    assert store.has(manifest["validation"][0]["report"]["sha256"])


def test_finalize_refuses_missing_commit_identity(tmp_path):
    repo = _repo(tmp_path)
    task = load_tasks(repo / "tasks")[0]
    result = TaskResult("T-001", "Example", "completed", 1, [], True)

    with pytest.raises(ValueError, match="start_commit and result_commit"):
        finalize_run_evidence(
            repo_root=repo,
            run_id="run-1",
            task=task,
            result=result,
            transcript_dir=repo / "transcript",
            store=LocalArtifactStore(repo / ".factory" / "artifacts" / "objects"),
            evidence_dir=repo / "evidence",
            git_ops=SubprocessGitOps(),
            started_at="2026-08-07T12:00:00Z",
            ended_at="2026-08-07T12:01:00Z",
        )


def test_finalize_refuses_a_declared_requirement_that_is_missing(tmp_path):
    repo = _repo(tmp_path)
    (repo / "requirements" / "SR-001.md").unlink()
    ops = SubprocessGitOps()
    commit = ops.head_commit(repo)
    task = load_tasks(repo / "tasks")[0]
    result = TaskResult(
        "T-001", "Example", "completed", 1, [], True,
        start_commit=commit, result_commit=commit,
    )

    with pytest.raises(ValueError, match="missing requirement"):
        finalize_run_evidence(
            repo_root=repo,
            run_id="run-1",
            task=task,
            result=result,
            transcript_dir=repo / "transcript",
            store=LocalArtifactStore(repo / ".factory" / "artifacts" / "objects"),
            evidence_dir=repo / "evidence",
            git_ops=ops,
            started_at="2026-08-07T12:00:00Z",
            ended_at="2026-08-07T12:01:00Z",
        )


def test_finalize_marks_publication_local_without_target_and_published_with_target(tmp_path):
    repo = _repo(tmp_path)
    ops = SubprocessGitOps()
    start = ops.head_commit(repo)
    (repo / "src" / "a.py").write_text("after = True\n", encoding="utf-8")
    assert ops.commit_all(repo, "implementation") is True
    result_commit = ops.head_commit(repo)
    task = load_tasks(repo / "tasks")[0]
    result = TaskResult(
        "T-001",
        "Example",
        "completed",
        1,
        [NodeEvent("dev", "pass")],
        True,
        start_commit=start,
        result_commit=result_commit,
    )
    transcript = _transcript(repo)

    local_manifest = load_run_manifest(
        finalize_run_evidence(
            repo_root=repo,
            run_id="run-local",
            task=task,
            result=result,
            transcript_dir=transcript,
            store=LocalArtifactStore(repo / ".factory" / "artifacts" / "objects"),
            evidence_dir=repo / "evidence",
            git_ops=ops,
            started_at="2026-08-07T12:00:00Z",
            ended_at="2026-08-07T12:01:00Z",
        )
    )
    published_dir = repo / "published"
    published_dir.mkdir()
    published_manifest = load_run_manifest(
        finalize_run_evidence(
            repo_root=repo,
            run_id="run-published",
            task=task,
            result=result,
            transcript_dir=transcript,
            store=LocalArtifactStore(repo / ".factory" / "artifacts" / "objects", published_dir),
            evidence_dir=repo / "evidence",
            git_ops=ops,
            started_at="2026-08-07T12:00:00Z",
            ended_at="2026-08-07T12:01:00Z",
        )
    )

    assert local_manifest["publication"]["state"] == "local"
    assert published_manifest["publication"]["state"] == "published"
    assert published_manifest["implementation"]["patch"]["publication"] == "published"
    assert (published_dir / published_manifest["implementation"]["patch"]["sha256"][:2]).exists()


def test_finalize_queues_publication_when_target_is_unusable(tmp_path):
    repo = _repo(tmp_path)
    ops = SubprocessGitOps()
    start = ops.head_commit(repo)
    (repo / "src" / "a.py").write_text("after = True\n", encoding="utf-8")
    assert ops.commit_all(repo, "implementation") is True
    result_commit = ops.head_commit(repo)
    task = load_tasks(repo / "tasks")[0]
    result = TaskResult(
        "T-001",
        "Example",
        "completed",
        1,
        [NodeEvent("dev", "pass")],
        True,
        start_commit=start,
        result_commit=result_commit,
    )
    blocked = repo / "published"
    blocked.write_text("blocked", encoding="utf-8")
    store = LocalArtifactStore(repo / ".factory" / "artifacts" / "objects", blocked)

    manifest = load_run_manifest(
        finalize_run_evidence(
            repo_root=repo,
            run_id="run-queued",
            task=task,
            result=result,
            transcript_dir=_transcript(repo),
            store=store,
            evidence_dir=repo / "evidence",
            git_ops=ops,
            started_at="2026-08-07T12:00:00Z",
            ended_at="2026-08-07T12:01:00Z",
        )
    )

    assert manifest["publication"]["state"] == "queued"
    assert manifest["implementation"]["patch"]["publication"] == "queued"
    assert manifest["publication"]["errors"]
    assert store.publication_record(manifest["implementation"]["patch"]["sha256"])["state"] == "queued"
