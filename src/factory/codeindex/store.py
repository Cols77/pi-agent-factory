from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from factory.codeindex.build import LATEST_STEM, index_dir
from factory.codeindex.model import CodeIndex


def ensure_fresh(repo_root: Path, files: list[str] | None = None) -> CodeIndex:
    """Return a fresh index, rebuilding ONLY when the code changed.

    The fingerprint is the cheap checksum for change detection (hash-only, no
    parsing). When it still matches the stored latest index, reuse it; otherwise
    rebuild + persist. This is what any 'recompute at session open if the code
    changed' hook calls."""
    from factory.codeindex.build import build_index, discover_source_files, fingerprint_for

    files = files or discover_source_files(repo_root)
    if not files:
        return CodeIndex(generated_at=_now_str(), fingerprint="no-files")
    fp = fingerprint_for(files, repo_root)
    latest = load_latest(repo_root)
    if latest is not None and latest.fingerprint == fp and set(latest.files.keys()) == set(files):
        return latest
    index = build_index(repo_root, files)
    save_index(index, repo_root)
    return index


def _now_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _safe_fp(fingerprint: str) -> str:
    # fingerprint digests carry a "sha256:" prefix whose colon is invalid in a
    # Windows filename; sanitize it for the on-disk index name.
    return fingerprint.replace(":", "_")


def save_index(index: CodeIndex, repo_root: Path) -> Path:
    """Persist latest.json + <fingerprint>.json atomically under
    .factory/code-index/."""
    d = index_dir(repo_root)
    d.mkdir(parents=True, exist_ok=True)

    fp_file = d / f"{_safe_fp(index.fingerprint)}.json"
    _atomic_json(fp_file, index.to_dict())

    latest = {"schema": 1, "fingerprint": index.fingerprint, "engine": index.engine, "path": fp_file.name}
    _atomic_json(d / LATEST_STEM, latest)
    return fp_file


def _atomic_json(path: Path, data: dict) -> None:
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def load_latest(repo_root: Path) -> CodeIndex | None:
    """Load the index that latest.json points to, if present and readable."""
    latest_path = index_dir(repo_root) / LATEST_STEM
    if not latest_path.exists():
        return None
    try:
        latest = json.loads(latest_path.read_text(encoding="utf-8"))
        fp_file = index_dir(repo_root) / latest["path"]
        return CodeIndex.from_dict(json.loads(fp_file.read_text(encoding="utf-8")))
    except (OSError, ValueError, KeyError):
        return None
