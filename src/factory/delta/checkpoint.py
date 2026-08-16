"""Developer checkpoint store for `/catchup` (Inc 7 Task 1).

A checkpoint records the last commit at which a developer reviewed a feature
-- the "since your last review" base of the context delta. Checkpoints are
*recorded, never inferred* (spec §31 `developer_checkpoint.commit`):
`load_checkpoint` returns `None` for a feature that has never been reviewed,
which is a legitimate state, not an error.

The store is a minimal JSON file under `.pi/` (`.pi/checkpoints.json`),
canonical-only -- never evidence. A malformed or unreadable file degrades to
"no checkpoints" rather than crashing the delta pipeline.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

CHECKPOINTS_FILENAME = "checkpoints.json"


@dataclass(frozen=True)
class Checkpoint:
    """One recorded review checkpoint for one feature."""

    feature: str
    commit: str
    reviewed_at: str


def checkpoints_path(pi_dir: Path) -> Path:
    """The checkpoint file inside a project's `.pi` directory."""
    return pi_dir / CHECKPOINTS_FILENAME


def _parse_checkpoint(feature: str, raw: object) -> Checkpoint | None:
    if not isinstance(raw, dict):
        return None
    commit = raw.get("commit")
    reviewed_at = raw.get("reviewed_at")
    if not isinstance(commit, str) or not isinstance(reviewed_at, str):
        return None
    return Checkpoint(feature=feature, commit=commit, reviewed_at=reviewed_at)


def save_checkpoint(pi_dir: Path, cp: Checkpoint) -> None:
    """Record (or update) one feature's checkpoint, atomically.

    Other features' checkpoints are preserved. The write is atomic
    (temp-file + rename) so a crash mid-write never corrupts the store.
    """
    path = checkpoints_path(pi_dir)
    store: dict[str, object] = {}
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                store = raw
        except (OSError, ValueError):
            # Malformed store: rebuild from scratch rather than crash.
            store = {}
    store[cp.feature] = asdict(cp)
    pi_dir.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps(store, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)


def load_checkpoint(pi_dir: Path, feature: str) -> Checkpoint | None:
    """Return the recorded checkpoint for one feature, or `None`.

    `None` means "no review has been recorded for this feature yet" -- a
    legitimate state, never an error. A malformed store file degrades to
    `None` as well.
    """
    path = checkpoints_path(pi_dir)
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(raw, dict):
        return None
    return _parse_checkpoint(feature, raw.get(feature))
