from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from substrate.freshness.model import DependencyFingerprint


def sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def fingerprint_file(name: str, path: Path, repo_root: Path | None = None) -> DependencyFingerprint:
    try:
        data = path.read_bytes()
        digest = sha256_bytes(data)
    except FileNotFoundError:
        digest = "missing"
    if repo_root is not None:
        try:
            source = path.resolve().relative_to(repo_root.resolve()).as_posix()
        except ValueError:
            source = str(path.resolve())
    else:
        source = str(path)
    return DependencyFingerprint(name=name, kind="file", digest=digest, source=source)


def fingerprint_value(name: str, value: object, source: str = "value") -> DependencyFingerprint:
    data = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return DependencyFingerprint(name=name, kind="value", digest=sha256_bytes(data), source=source)


def fingerprint_tool(name: str, version: str) -> DependencyFingerprint:
    return DependencyFingerprint(
        name=name,
        kind="tool",
        digest=sha256_bytes(version.encode("utf-8")),
        source=version,
    )


def fingerprint_git_tree(
    repo_root: Path, name: str = "candidate-tree", ref: str = "HEAD"
) -> DependencyFingerprint:
    result = subprocess.run(
        ["git", "rev-parse", f"{ref}^{{tree}}"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )
    tree = result.stdout.strip()
    return DependencyFingerprint(name=name, kind="git-tree", digest=f"git-tree:{tree}", source=ref)
