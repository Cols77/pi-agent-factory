"""Hash-bound, run-local manifests for planning lifecycle artifacts."""
from __future__ import annotations

import hashlib
import os
import tempfile
from collections.abc import Iterable, Mapping
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from coherence.planning.legal_actions_adapter import is_safe_run_id
from coherence.planning.paths import safe_resolve, safe_root
from coherence.planning.serialization import strict_json_dumps, strict_json_loads


class ArtifactError(ValueError):
    """An artifact manifest or its source files are unsafe or invalid."""


def sha256_file(path: Path) -> str:
    """Return the lowercase SHA-256 digest for ``path``'s current bytes."""
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
    except OSError as exc:
        raise ArtifactError(f"artifact file is unreadable: {path}") from exc
    return digest.hexdigest()


def _safe_run_directory(root: Path, run_id: str) -> tuple[Path, Path]:
    if not isinstance(run_id, str) or not is_safe_run_id(run_id):
        raise ArtifactError("invalid run_id")
    safe = safe_root(root)
    if safe is None:
        raise ArtifactError("project root is unsafe")
    run_dir = safe_resolve(safe, safe / ".factory" / "planning" / run_id)
    if run_dir is None:
        raise ArtifactError("artifact manifest directory is unsafe")
    return safe, run_dir


def _artifact_path(root: Path, value: object) -> tuple[str, Path]:
    if not isinstance(value, str):
        raise ArtifactError("artifact path is invalid")
    if (
        not value
        or "\\" in value
        or PurePosixPath(value).is_absolute()
        or PureWindowsPath(value).is_absolute()
    ):
        raise ArtifactError(f"artifact path is unsafe: {value}")
    posix = PurePosixPath(value)
    if any(part in {"", ".", ".."} for part in posix.parts):
        raise ArtifactError(f"artifact path is unsafe: {value}")
    source = safe_resolve(root, root.joinpath(*posix.parts))
    if source is None:
        raise ArtifactError(f"artifact path is unsafe: {value}")
    try:
        relative = source.relative_to(root).as_posix()
    except ValueError as exc:
        raise ArtifactError(f"artifact path is unsafe: {value}") from exc
    if relative != value:
        raise ArtifactError(f"artifact path is unsafe: {value}")
    if not source.is_file():
        raise ArtifactError(f"artifact missing: {value}")
    return value, source


def _artifact_kind(value: object) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ArtifactError("artifact kind is invalid")
    return value


def _artifact_items(root: Path, artifacts: object, *, hashed: bool) -> list[dict[str, str]]:
    if not isinstance(artifacts, Iterable) or isinstance(artifacts, (str, bytes, Mapping)):
        raise ArtifactError("artifact manifest artifacts are invalid")
    expected_keys = {"kind", "path", "sha256"} if hashed else {"kind", "path"}
    result: list[dict[str, str]] = []
    kinds: set[str] = set()
    paths: set[str] = set()
    for item in artifacts:
        if not isinstance(item, Mapping) or set(item) != expected_keys:
            raise ArtifactError("artifact manifest artifacts are invalid")
        kind = _artifact_kind(item["kind"])
        path, source = _artifact_path(root, item["path"])
        if kind in kinds:
            raise ArtifactError(f"duplicate artifact kind: {kind}")
        if path in paths:
            raise ArtifactError(f"duplicate artifact path: {path}")
        kinds.add(kind)
        paths.add(path)
        digest = sha256_file(source)
        if hashed:
            claimed = item["sha256"]
            if not isinstance(claimed, str) or len(claimed) != 64 or any(
                character not in "0123456789abcdef" for character in claimed
            ):
                raise ArtifactError(f"artifact sha256 is invalid: {path}")
            if digest != claimed:
                raise ArtifactError(f"artifact changed: {path}")
        result.append({"kind": kind, "path": path, "sha256": digest})
    return sorted(result, key=lambda item: item["kind"])


def _validated_manifest(root: Path, manifest: object) -> dict[str, object]:
    if not isinstance(manifest, Mapping) or set(manifest) != {"schema", "run_id", "artifacts"}:
        raise ArtifactError("artifact manifest is invalid")
    if type(manifest["schema"]) is not int or manifest["schema"] != 1:
        raise ArtifactError("artifact manifest schema is invalid")
    run_id = manifest["run_id"]
    if not isinstance(run_id, str) or not is_safe_run_id(run_id):
        raise ArtifactError("artifact manifest run_id is invalid")
    safe, _ = _safe_run_directory(root, run_id)
    artifacts = _artifact_items(safe, manifest["artifacts"], hashed=True)
    return {"schema": 1, "run_id": run_id, "artifacts": artifacts}


def build_artifact_manifest(
    root: Path, run_id: str, artifacts: Iterable[Mapping[str, object]]
) -> dict[str, object]:
    """Build a deterministic, hash-bound manifest without writing files."""
    safe, _ = _safe_run_directory(root, run_id)
    return {"schema": 1, "run_id": run_id, "artifacts": _artifact_items(safe, artifacts, hashed=False)}


def write_artifact_manifest(root: Path, run_id: str, manifest: Mapping[str, object]) -> Path:
    """Atomically persist a validated manifest in its safe run-local location."""
    safe, run_dir = _safe_run_directory(root, run_id)
    normalized = _validated_manifest(safe, manifest)
    if normalized["run_id"] != run_id:
        raise ArtifactError("artifact manifest run_id does not match write run_id")
    run_dir.mkdir(parents=True, exist_ok=True)
    target = safe_resolve(safe, run_dir / "artifacts.json")
    if target is None:
        raise ArtifactError("artifact manifest directory is unsafe")
    descriptor, temporary = tempfile.mkstemp(prefix=".artifacts-", dir=str(run_dir))
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(strict_json_dumps(normalized) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return target


def read_artifact_manifest(root: Path, run_id: str) -> dict[str, object]:
    """Read and validate the run-local artifact manifest, failing closed."""
    safe, run_dir = _safe_run_directory(root, run_id)
    path = safe_resolve(safe, run_dir / "artifacts.json")
    if path is None:
        raise ArtifactError("artifact manifest directory is unsafe")
    try:
        payload: Any = strict_json_loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise ArtifactError("artifact manifest JSON is unreadable") from exc
    normalized = _validated_manifest(safe, payload)
    if normalized["run_id"] != run_id:
        raise ArtifactError("artifact manifest run_id does not match read run_id")
    return normalized


def validate_artifact_manifest(root: Path, manifest: Mapping[str, object]) -> dict[str, object]:
    """Validate manifest structure, locations, and current source bytes without writing."""
    safe = safe_root(root)
    if safe is None:
        raise ArtifactError("project root is unsafe")
    return _validated_manifest(safe, manifest)


__all__ = [
    "ArtifactError",
    "build_artifact_manifest",
    "read_artifact_manifest",
    "sha256_file",
    "validate_artifact_manifest",
    "write_artifact_manifest",
]
