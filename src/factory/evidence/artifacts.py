from __future__ import annotations

import hashlib
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

    def __init__(self, root: Path, publish_root: Path | None = None) -> None:
        self.root = root
        self.publish_root = publish_root

    def path_for(self, digest: str, root: Path | None = None) -> Path:
        base = self.root if root is None else root
        return base / digest[:2] / digest

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
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(f"{target.name}.{os.getpid()}.tmp")
        tmp.write_bytes(data)
        tmp.replace(target)
        if hashlib.sha256(target.read_bytes()).hexdigest() != sha256:
            return PublicationResult("failed", error="destination hash mismatch")
        return PublicationResult("published", uri=target.resolve().as_uri())
