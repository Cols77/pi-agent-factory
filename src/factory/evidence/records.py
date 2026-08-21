"""Explicit, manually authored provenance for completed historical Git ranges.

These records are intentionally narrower than automated run manifests: they only
bind a task's Markdown content to a real, non-empty Git commit range.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from factory.validation.schema_validator import SCHEMA_DIR, validate


HISTORICAL_RECORD_SCHEMA_VERSION = 1

_SCHEMA = SCHEMA_DIR / "evidence_record.schema.json"
_TASK_ID = re.compile(r"T-[0-9]+\Z")
_COMMIT_SHA = re.compile(r"[a-f0-9]{40}\Z")


def _validate_record(record: object, *, source: Path | None = None) -> dict:
    if not isinstance(record, dict):
        location = f" at {source}" if source is not None else ""
        raise ValueError(f"invalid historical record{location}: expected a JSON object")
    errors = validate(record, _SCHEMA)
    if errors:
        location = f" at {source}" if source is not None else ""
        raise ValueError(f"invalid historical record{location}: {'; '.join(errors)}")
    return record


def _git(repo_root: Path, *args: str) -> str:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
        )
    except OSError as exc:
        raise ValueError(f"cannot execute git in {repo_root}: {exc}") from exc
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.strip()
        command = " ".join(("git", *args))
        suffix = f": {detail}" if detail else ""
        raise ValueError(f"git command failed ({command}){suffix}") from exc
    return completed.stdout.strip()


def _resolve_commit(repo_root: Path, revision: object, label: str) -> str:
    if not isinstance(revision, str) or _COMMIT_SHA.fullmatch(revision) is None:
        raise ValueError(f"{label} must be a 40-character lower-case commit SHA")
    resolved = _git(repo_root, "rev-parse", "--verify", f"{revision}^{{commit}}")
    if resolved != revision:
        raise ValueError(f"{label} must identify a commit object directly")
    return resolved


def _require_ancestor(repo_root: Path, start_commit: str, result_commit: str) -> None:
    completed = subprocess.run(
        ["git", "merge-base", "--is-ancestor", start_commit, result_commit],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    if completed.returncode == 0:
        return
    if completed.returncode == 1:
        raise ValueError("start_commit must be an ancestor of result_commit")
    detail = completed.stderr.strip()
    suffix = f": {detail}" if detail else ""
    raise ValueError(f"git command failed (git merge-base --is-ancestor){suffix}")


def _changed_files(repo_root: Path, start_commit: str, result_commit: str) -> list[str]:
    output = _git(repo_root, "diff", "--name-only", start_commit, result_commit)
    changed_files = sorted({line for line in output.splitlines() if line})
    if not changed_files:
        raise ValueError("historical record Git range has no changed files")
    return changed_files


def _task_path(repo_root: Path, task_id: object) -> Path:
    if not isinstance(task_id, str) or _TASK_ID.fullmatch(task_id) is None:
        raise ValueError("task_id must match T-<number>")
    path = repo_root / "tasks" / f"{task_id}.md"
    if not path.is_file():
        raise ValueError(f"task Markdown does not exist: {path}")
    return path


def _task_sha256(repo_root: Path, task_id: object) -> str:
    path = _task_path(repo_root, task_id)
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise ValueError(f"cannot read task Markdown: {path}: {exc}") from exc


def _record_id(task_id: str, result_commit: str) -> str:
    return f"manual-{task_id}-{result_commit[:12]}"


def _recorded_at(now: datetime | None) -> str:
    timestamp = now if now is not None else datetime.now(timezone.utc)
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    return timestamp.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _canonical_json(record: dict) -> str:
    return json.dumps(record, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _existing_record(path: Path, canonical: bytes) -> Path:
    try:
        existing = path.read_bytes()
    except OSError as exc:
        raise ValueError(f"cannot read existing historical record: {path}: {exc}") from exc
    if existing == canonical:
        return path
    raise ValueError(f"historical record already exists with different content: {path}")


def _validate_provenance(repo_root: Path, record: dict, path: Path | None = None) -> None:
    task_sha256 = _task_sha256(repo_root, record["task_id"])
    if task_sha256 != record["task_sha256"]:
        raise ValueError(
            f"historical record{f' at {path}' if path is not None else ''} has stale task_sha256"
        )

    start_commit = _resolve_commit(repo_root, record["start_commit"], "start_commit")
    result_commit = _resolve_commit(repo_root, record["result_commit"], "result_commit")
    if record["record_id"] != _record_id(record["task_id"], result_commit):
        raise ValueError(
            f"historical record{f' at {path}' if path is not None else ''} has inconsistent record_id"
        )
    _require_ancestor(repo_root, start_commit, result_commit)
    changed_files = _changed_files(repo_root, start_commit, result_commit)
    if record["changed_files"] != changed_files:
        raise ValueError(
            f"historical record{f' at {path}' if path is not None else ''} changed_files "
            "do not match its Git range"
        )


def build_historical_record(
    repo_root: Path,
    task_id: str,
    start_commit: str,
    result_commit: str,
    recorded_by: str,
    reason: str,
    now: datetime | None = None,
) -> dict:
    """Build explicit manual provenance from an existing, non-empty Git range."""
    root = Path(repo_root)
    task_sha256 = _task_sha256(root, task_id)
    start = _resolve_commit(root, start_commit, "start_commit")
    result = _resolve_commit(root, result_commit, "result_commit")
    _require_ancestor(root, start, result)
    changed_files = _changed_files(root, start, result)
    record = {
        "schema_version": HISTORICAL_RECORD_SCHEMA_VERSION,
        "record_id": _record_id(task_id, result),
        "task_id": task_id,
        "recorded_at": _recorded_at(now),
        "recorded_by": recorded_by,
        "reason": reason,
        "start_commit": start,
        "result_commit": result,
        "changed_files": changed_files,
        "task_sha256": task_sha256,
    }
    return _validate_record(record)


def write_historical_record(evidence_dir: Path, record: dict) -> Path:
    """Create a manual record once, preserving an identical canonical write."""
    validated = _validate_record(record)
    records_dir = Path(evidence_dir) / "records"
    records_dir.mkdir(parents=True, exist_ok=True)
    path = records_dir / f"{validated['record_id']}.json"
    canonical = _canonical_json(validated).encode("utf-8")
    if path.exists():
        return _existing_record(path, canonical)

    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=records_dir,
            prefix=f".{validated['record_id']}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(canonical)
        try:
            os.link(temporary, path)
        except FileExistsError:
            return _existing_record(path, canonical)
    except OSError as exc:
        raise ValueError(f"cannot write historical record: {path}: {exc}") from exc
    finally:
        if temporary is not None:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
            except OSError as exc:
                raise ValueError(f"cannot remove temporary historical record: {temporary}: {exc}") from exc
    return path


def load_historical_record(repo_root: Path, path: Path) -> dict:
    """Load a manual record only when its task and Git provenance remain valid."""
    record_path = Path(path)
    try:
        decoded = json.loads(record_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read historical record at {record_path}: {exc}") from exc
    record = _validate_record(decoded, source=record_path)
    expected_name = f"{record['record_id']}.json"
    if record_path.name != expected_name:
        raise ValueError(
            f"historical record at {record_path} has a filename that does not match record_id"
        )
    _validate_provenance(Path(repo_root), record, record_path)
    return record


def list_historical_records(
    repo_root: Path, evidence_dir: Path, task_id: str | None = None
) -> list[dict]:
    """Return all valid manual records, newest first, without hiding invalid files."""
    if task_id is not None and _TASK_ID.fullmatch(task_id) is None:
        raise ValueError("task_id must match T-<number>")
    records_dir = Path(evidence_dir) / "records"
    if not records_dir.exists():
        return []

    records: list[dict] = []
    pattern = f"manual-{task_id}-*.json" if task_id is not None else "*.json"
    for path in sorted(records_dir.glob(pattern)):
        try:
            record = load_historical_record(repo_root, path)
        except ValueError as exc:
            raise ValueError(f"invalid historical record at {path}: {exc}") from exc
        if task_id is None or record["task_id"] == task_id:
            records.append(record)
    return sorted(
        records,
        key=lambda record: (
            datetime.fromisoformat(record["recorded_at"].replace("Z", "+00:00")).astimezone(timezone.utc),
            record["record_id"],
        ),
        reverse=True,
    )
