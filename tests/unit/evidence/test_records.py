from __future__ import annotations

import hashlib
import json
import os
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pytest

from factory.evidence.records import (
    HISTORICAL_RECORD_SCHEMA_VERSION,
    build_historical_record,
    list_historical_records,
    load_historical_record,
    write_historical_record,
)


pytestmark = pytest.mark.unit


@dataclass(frozen=True)
class GitRepo:
    root: Path
    start: str
    result: str


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout.strip()


def _commit(repo: Path, message: str) -> str:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path: Path) -> GitRepo:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "test@example.invalid")
    _git(root, "config", "user.name", "Evidence Test")
    (root / "tasks").mkdir()
    (root / "tasks" / "T-058.md").write_text(
        "---\nid: T-058\nstatus: done\n---\n\n# Completed task\n",
        encoding="utf-8",
    )
    (root / "src" / "factory").mkdir(parents=True)
    (root / "src" / "factory" / "example.py").write_text("VALUE = 1\n", encoding="utf-8")
    start = _commit(root, "initial task")

    (root / "src" / "factory" / "example.py").write_text("VALUE = 2\n", encoding="utf-8")
    (root / "src" / "factory" / "added.py").write_text("ADDED = True\n", encoding="utf-8")
    result = _commit(root, "completed task")
    return GitRepo(root=root, start=start, result=result)


def _record(repo: GitRepo, *, now: datetime | None = None) -> dict:
    return build_historical_record(
        repo.root,
        "T-058",
        repo.start,
        repo.result,
        "human@example.invalid",
        "Recovered completed work from an interrupted session.",
        now=now or datetime(2026, 8, 20, 9, 0, tzinfo=timezone.utc),
    )


def _write_raw(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2), encoding="utf-8")


def _canonical_json(record: dict) -> str:
    return json.dumps(record, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _race_winner(monkeypatch: pytest.MonkeyPatch, path: Path, content: bytes) -> Path:
    """Create `path` immediately after a stale non-existence observation."""
    winner = path.with_name(path.name + ".winner")
    original_exists = Path.exists
    created = False

    def stale_exists(candidate: Path) -> bool:
        nonlocal created
        if candidate == path and not created:
            winner.write_bytes(content)
            os.link(winner, path)
            created = True
            return False
        return original_exists(candidate)

    monkeypatch.setattr(Path, "exists", stale_exists)
    return winner


def test_build_derives_changed_files_and_writer_is_atomic(repo: GitRepo) -> None:
    record = _record(repo)

    assert record == {
        "schema_version": HISTORICAL_RECORD_SCHEMA_VERSION,
        "record_id": f"manual-T-058-{repo.result[:12]}",
        "task_id": "T-058",
        "recorded_at": "2026-08-20T09:00:00Z",
        "recorded_by": "human@example.invalid",
        "reason": "Recovered completed work from an interrupted session.",
        "start_commit": repo.start,
        "result_commit": repo.result,
        "changed_files": ["src/factory/added.py", "src/factory/example.py"],
        "task_sha256": hashlib.sha256(
            (repo.root / "tasks" / "T-058.md").read_bytes()
        ).hexdigest(),
    }

    path = write_historical_record(repo.root / "evidence", record)

    assert path == repo.root / "evidence" / "records" / f"manual-T-058-{repo.result[:12]}.json"
    assert json.loads(path.read_text(encoding="utf-8")) == record
    assert not path.with_name(path.name + ".tmp").exists()


def test_build_rejects_invalid_task_or_git_input(repo: GitRepo) -> None:
    cases = [
        ("T-058", "f" * 40, "e" * 40),
        ("T-058", repo.start, repo.start),
        ("not-a-task", repo.start, repo.result),
        ("T-999", repo.start, repo.result),
        ("T-058", "HEAD", repo.result),
    ]

    for task_id, start_commit, result_commit in cases:
        with pytest.raises(ValueError):
            build_historical_record(
                repo.root,
                task_id,
                start_commit,
                result_commit,
                "human@example.invalid",
                "Recovered completed work.",
            )


def test_build_rejects_reversed_or_no_diff_ranges(repo: GitRepo) -> None:
    with pytest.raises(ValueError):
        build_historical_record(
            repo.root,
            "T-058",
            repo.result,
            repo.start,
            "human@example.invalid",
            "Recovered completed work.",
        )

    _git(repo.root, "commit", "--allow-empty", "-q", "-m", "empty follow-up")
    empty_result = _git(repo.root, "rev-parse", "HEAD")
    with pytest.raises(ValueError):
        build_historical_record(
            repo.root,
            "T-058",
            repo.result,
            empty_result,
            "human@example.invalid",
            "Recovered completed work.",
        )


def test_writer_rejects_untrusted_changed_file_paths(repo: GitRepo) -> None:
    for changed_files in [
        ["src/factory/example.py", "src/factory/example.py"],
        ["C:/absolute.py"],
    ]:
        record = _record(repo)
        record["changed_files"] = changed_files

        with pytest.raises(ValueError, match="invalid historical record"):
            write_historical_record(repo.root / "evidence", record)


def test_loader_rejects_invalid_or_stale_record_fields(repo: GitRepo) -> None:
    cases = [
        (lambda record: record.update({"outcome": "completed"}), "unknown-property.json"),
        (lambda record: record.update({"recorded_at": "2026-08-20T09:00:00+01:00"}), "bad-time.json"),
        (lambda record: record.update({"task_sha256": "a" * 63}), "bad-hash.json"),
        (lambda record: record.update({"changed_files": ["src/factory/not-real.py"]}), "bad-range.json"),
    ]
    for mutate, filename in cases:
        record = _record(repo)
        mutate(record)
        path = repo.root / "evidence" / "records" / filename
        _write_raw(path, record)

        with pytest.raises(ValueError, match="historical record"):
            load_historical_record(repo.root, path)


def test_loader_rejects_malformed_json_and_stale_task_markdown(repo: GitRepo) -> None:
    malformed = repo.root / "evidence" / "records" / "malformed.json"
    malformed.parent.mkdir(parents=True)
    malformed.write_text("not json", encoding="utf-8")

    with pytest.raises(ValueError, match="malformed.json"):
        load_historical_record(repo.root, malformed)

    path = write_historical_record(repo.root / "evidence", _record(repo))
    (repo.root / "tasks" / "T-058.md").write_text("changed after record\n", encoding="utf-8")

    with pytest.raises(ValueError, match="task_sha256"):
        load_historical_record(repo.root, path)


def test_list_returns_newest_first_and_does_not_ignore_malformed_records(repo: GitRepo) -> None:
    evidence_dir = repo.root / "evidence"
    old = _record(repo, now=datetime(2026, 8, 20, 9, 0, tzinfo=timezone.utc))
    write_historical_record(evidence_dir, old)

    (repo.root / "src" / "factory" / "second.py").write_text("SECOND = True\n", encoding="utf-8")
    newest_result = _commit(repo.root, "second completed task")
    newest = build_historical_record(
        repo.root,
        "T-058",
        repo.result,
        newest_result,
        "human@example.invalid",
        "Recovered later completed work.",
        now=datetime(2026, 8, 21, 9, 0, tzinfo=timezone.utc),
    )
    write_historical_record(evidence_dir, newest)

    assert [item["record_id"] for item in list_historical_records(repo.root, evidence_dir, "T-058")] == [
        newest["record_id"],
        old["record_id"],
    ]

    malformed = evidence_dir / "records" / "bad-record.json"
    malformed.write_text("not json", encoding="utf-8")
    with pytest.raises(ValueError, match="bad-record.json"):
        list_historical_records(repo.root, evidence_dir, "T-058")


def test_persisted_record_excludes_run_claim_fields_and_is_create_once(repo: GitRepo) -> None:
    evidence_dir = repo.root / "evidence"
    record = _record(repo)
    path = write_historical_record(evidence_dir, record)
    persisted = json.loads(path.read_text(encoding="utf-8"))

    assert not {
        "validation",
        "outcome",
        "patch",
        "transcript",
        "inferred_source",
        "inferred-source",
    }.intersection(persisted)
    assert write_historical_record(evidence_dir, record) == path

    divergent = dict(record)
    divergent["reason"] = "A different account of the same record id."
    with pytest.raises(ValueError, match="already exists"):
        write_historical_record(evidence_dir, divergent)

    assert json.loads(path.read_text(encoding="utf-8")) == persisted


def test_writer_rejects_crlf_noncanonical_existing_record(repo: GitRepo) -> None:
    evidence_dir = repo.root / "evidence"
    record = _record(repo)
    path = evidence_dir / "records" / f"{record['record_id']}.json"
    crlf_canonical = _canonical_json(record).replace("\n", "\r\n").encode("utf-8")
    path.parent.mkdir(parents=True)
    path.write_bytes(crlf_canonical)

    with pytest.raises(ValueError, match="already exists"):
        write_historical_record(evidence_dir, record)

    assert path.read_bytes() == crlf_canonical


def test_writer_preserves_equal_race_winner_without_replacement(
    repo: GitRepo, monkeypatch: pytest.MonkeyPatch
) -> None:
    evidence_dir = repo.root / "evidence"
    record = _record(repo)
    path = evidence_dir / "records" / f"{record['record_id']}.json"
    winner = _race_winner(monkeypatch, path, _canonical_json(record).encode("utf-8"))

    assert write_historical_record(evidence_dir, record) == path
    assert os.path.samefile(path, winner)
    assert not list(path.parent.glob("*.tmp"))


def test_writer_rejects_divergent_race_winner_without_replacement(
    repo: GitRepo, monkeypatch: pytest.MonkeyPatch
) -> None:
    evidence_dir = repo.root / "evidence"
    record = _record(repo)
    divergent = dict(record)
    divergent["reason"] = "A conflicting account won the create race."
    path = evidence_dir / "records" / f"{record['record_id']}.json"
    winner = _race_winner(monkeypatch, path, _canonical_json(divergent).encode("utf-8"))

    with pytest.raises(ValueError, match="already exists"):
        write_historical_record(evidence_dir, record)

    assert os.path.samefile(path, winner)
    assert path.read_bytes() == _canonical_json(divergent).encode("utf-8")
    assert not list(path.parent.glob("*.tmp"))


def test_list_sorts_fractional_utc_timestamps_by_time(repo: GitRepo) -> None:
    evidence_dir = repo.root / "evidence"
    whole_second = _record(repo, now=datetime(2026, 8, 20, 9, 0, tzinfo=timezone.utc))
    write_historical_record(evidence_dir, whole_second)

    (repo.root / "src" / "factory" / "fractional.py").write_text("FRACTIONAL = True\n", encoding="utf-8")
    fractional_result = _commit(repo.root, "fractional timestamp record")
    fractional_second = build_historical_record(
        repo.root,
        "T-058",
        repo.result,
        fractional_result,
        "human@example.invalid",
        "Recovered later completed work.",
        now=datetime(2026, 8, 20, 9, 0, tzinfo=timezone.utc),
    )
    fractional_second["recorded_at"] = "2026-08-20T09:00:00.500Z"
    write_historical_record(evidence_dir, fractional_second)

    assert [item["record_id"] for item in list_historical_records(repo.root, evidence_dir, "T-058")] == [
        fractional_second["record_id"],
        whole_second["record_id"],
    ]
