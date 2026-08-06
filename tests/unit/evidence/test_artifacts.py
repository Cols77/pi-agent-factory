from __future__ import annotations

from hashlib import sha256

import pytest

from factory.evidence.artifacts import LocalArtifactStore

pytestmark = pytest.mark.unit


def test_put_is_content_addressed_and_idempotent(tmp_path):
    store = LocalArtifactStore(tmp_path / "objects")

    first = store.put(b"hello", "text/plain")
    second = store.put(b"hello", "text/plain")

    assert first == second
    assert first.sha256 == sha256(b"hello").hexdigest()
    assert first.size == 5
    assert store.get(first.sha256) == b"hello"


def test_corrupt_object_is_rejected_on_read(tmp_path):
    store = LocalArtifactStore(tmp_path / "objects")
    ref = store.put(b"hello", "text/plain")
    store.path_for(ref.sha256).write_bytes(b"tampered")

    with pytest.raises(ValueError, match="hash mismatch"):
        store.get(ref.sha256)


def test_publish_copies_and_verifies_object(tmp_path):
    store = LocalArtifactStore(tmp_path / "objects", tmp_path / "published")
    ref = store.put(b"hello", "text/plain")

    result = store.publish(ref.sha256)

    assert result.state == "published"
    assert result.uri is not None
    assert (tmp_path / "published" / ref.sha256[:2] / ref.sha256).read_bytes() == b"hello"


def test_publish_without_destination_stays_local(tmp_path):
    store = LocalArtifactStore(tmp_path / "objects")
    ref = store.put(b"hello", "text/plain")

    assert store.publish(ref.sha256).state == "local"


def test_has_returns_false_for_missing_or_corrupt_objects(tmp_path):
    store = LocalArtifactStore(tmp_path / "objects")
    assert store.has("0" * 64) is False
    ref = store.put(b"hello", "text/plain")
    store.path_for(ref.sha256).write_bytes(b"tampered")
    assert store.has(ref.sha256) is False


def test_publish_refuses_a_missing_or_corrupt_source(tmp_path):
    store = LocalArtifactStore(tmp_path / "objects", tmp_path / "published")
    with pytest.raises(FileNotFoundError):
        store.publish("0" * 64)
