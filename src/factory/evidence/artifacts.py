from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class BlobRef:
    sha256: str
    size: int
    media_type: str
    local: bool = True
    publication: str = "local"
    uri: str | None = None


@dataclass(frozen=True)
class PublicationResult:
    state: str
    uri: str | None = None
    error: str | None = None


class ArtifactStore(Protocol):
    def put(self, data: bytes, media_type: str) -> BlobRef: ...

    def get(self, sha256: str) -> bytes: ...

    def has(self, sha256: str) -> bool: ...

    def publish(self, sha256: str) -> PublicationResult: ...


class LocalArtifactStore:
    """Content-addressed artifact storage with optional filesystem publication."""

    def __init__(
        self,
        root: Path,
        publish_root: Path | None = None,
        *,
        publication_required: bool = False,
    ) -> None:
        if publication_required and publish_root is None:
            raise ValueError("required publication needs a publication target")
        self.root = root
        self.publish_root = publish_root
        self.publication_required = publication_required

    def path_for(self, digest: str, root: Path | None = None) -> Path:
        base = self.root if root is None else root
        return base / digest[:2] / digest

    def publication_queue_root(self) -> Path:
        return self.root.parent / "publish-queue"

    def publication_record_path(self, sha256: str) -> Path:
        return self.publication_queue_root() / f"{sha256}.json"

    def _write_publication_record(
        self,
        sha256: str,
        *,
        state: str,
        errors: list[str] | None = None,
        uri: str | None = None,
    ) -> None:
        if self.publish_root is None:
            return
        record = {
            "sha256": sha256,
            "state": state,
            "errors": errors or [],
            "uri": uri,
            "publish_root": str(self.publish_root.resolve()),
        }
        path = self.publication_record_path(sha256)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(record, indent=2), encoding="utf-8")
        tmp.replace(path)

    def _record_publication_safely(
        self,
        sha256: str,
        *,
        state: str,
        errors: list[str] | None = None,
        uri: str | None = None,
    ) -> str | None:
        try:
            self._write_publication_record(
                sha256, state=state, errors=errors, uri=uri
            )
        except OSError as exc:
            return f"publication queue write failed: {exc}"
        return None

    def publication_record(self, sha256: str) -> dict | None:
        path = self.publication_record_path(sha256)
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return value if isinstance(value, dict) else None

    def put(self, data: bytes, media_type: str) -> BlobRef:
        digest = hashlib.sha256(data).hexdigest()
        path = self.path_for(digest)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            # Verify an existing object rather than trusting its filename.
            if self.get(digest) != data:
                raise ValueError(f"artifact collision for {digest}")
        else:
            tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
            tmp.write_bytes(data)
            tmp.replace(path)
        return BlobRef(digest, len(data), media_type)

    def get(self, sha256: str) -> bytes:
        data = self.path_for(sha256).read_bytes()
        if hashlib.sha256(data).hexdigest() != sha256:
            raise ValueError(f"artifact hash mismatch: {sha256}")
        return data

    def has(self, sha256: str) -> bool:
        try:
            self.get(sha256)
            return True
        except (OSError, ValueError):
            return False

    def publish(self, sha256: str) -> PublicationResult:
        data = self.get(sha256)
        if self.publish_root is None:
            return PublicationResult("local")
        target = self.path_for(sha256, self.publish_root)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() == sha256:
                uri = target.resolve().as_uri()
                self._record_publication_safely(sha256, state="published", uri=uri)
                return PublicationResult("published", uri=uri)
            tmp = target.with_name(f"{target.name}.{os.getpid()}.tmp")
            tmp.write_bytes(data)
            tmp.replace(target)
            if hashlib.sha256(target.read_bytes()).hexdigest() != sha256:
                error = "destination hash mismatch"
                queue_error = self._record_publication_safely(
                    sha256, state="failed", errors=[error]
                )
                if queue_error is not None:
                    error = f"{error}; {queue_error}"
                return PublicationResult("failed", error=error)
            uri = target.resolve().as_uri()
            self._record_publication_safely(sha256, state="published", uri=uri)
            return PublicationResult("published", uri=uri)
        except OSError as exc:
            error = str(exc)
            state = "queued" if not target.exists() else "failed"
            queue_error = self._record_publication_safely(
                sha256, state=state, errors=[error]
            )
            if queue_error is not None:
                error = f"{error}; {queue_error}"
            return PublicationResult(state, error=error)
