from __future__ import annotations

from copy import deepcopy

import pytest

from substrate.artifacts import ArtifactRef, ProducerRef, SnapshotInputRef, SnapshotRef


pytestmark = pytest.mark.unit

HASH = "sha256:" + "a" * 64
OTHER_HASH = "sha256:" + "b" * 64


def artifact_payload() -> dict[str, object]:
    return {
        "schema": 1,
        "kind": "source-document",
        "ref": "artifact:source:readme",
        "location": "workspace/docs/README.md",
        "content_hash": HASH,
        "scope_refs": ["scope:project", "scope:docs"],
        "media_type": "text/markdown",
    }


def snapshot_payload() -> dict[str, object]:
    return {
        "schema": 1,
        "kind": "code-map",
        "ref": "snapshot:code-map:current",
        "fingerprint": "fp-code-map-001",
        "producer": {"name": "codemap-builder", "version": "1.2.3", "engine": "ast-v4"},
        "inputs": [
            {"ref": "artifact:source:readme", "content_hash": HASH},
            {"ref": "artifact:source:pyproject", "content_hash": OTHER_HASH},
        ],
        "generated_at": "2026-08-20T10:30:00Z",
        "supersedes": "snapshot:code-map:previous",
    }


def test_refs_round_trip_with_stable_tuple_and_list_ordering() -> None:
    artifact = ArtifactRef.from_dict(artifact_payload())
    snapshot = SnapshotRef.from_dict(snapshot_payload())

    assert artifact.scope_refs == ("scope:project", "scope:docs")
    assert artifact.to_dict() == artifact_payload()
    assert snapshot.inputs == (
        SnapshotInputRef("artifact:source:readme", HASH),
        SnapshotInputRef("artifact:source:pyproject", OTHER_HASH),
    )
    assert snapshot.to_dict() == snapshot_payload()
    assert snapshot.producer == ProducerRef("codemap-builder", "1.2.3", "ast-v4")


def test_artifact_media_type_is_optional() -> None:
    payload = artifact_payload()
    payload.pop("media_type")

    artifact = ArtifactRef.from_dict(payload)

    assert artifact.media_type is None
    assert artifact.to_dict() == payload


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema", 2),
        ("kind", "   "),
        ("ref", ""),
        ("location", "\t"),
        ("content_hash", "sha256:" + "A" * 64),
        ("content_hash", "md5:" + "a" * 32),
        ("scope_refs", ["scope:project", "scope:project"]),
    ],
)
def test_artifact_rejects_invalid_fields(field: str, value: object) -> None:
    payload = artifact_payload()
    payload[field] = value

    with pytest.raises(ValueError, match=field):
        ArtifactRef.from_dict(payload)


def test_artifact_constructor_validates_before_use() -> None:
    with pytest.raises(ValueError, match="content_hash"):
        ArtifactRef(
            schema=1,
            kind="source-document",
            ref="artifact:source:readme",
            location="workspace/docs/README.md",
            content_hash="not-a-hash",
            scope_refs=("scope:project",),
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema", 2),
        ("kind", " "),
        ("ref", ""),
        ("fingerprint", "\n"),
        ("producer", {"version": "1.0"}),
        ("producer", {"name": "builder"}),
        ("producer", {"name": " ", "version": "1.0"}),
        ("producer", {"name": "builder", "version": 0}),
        ("inputs", []),
        ("inputs", [{"ref": "input:one"}, {"ref": "input:one"}]),
        ("generated_at", "2026-08-20T10:30:00"),
        ("generated_at", "2026-08-20T10:30:00+02:00"),
        ("supersedes", "snapshot:code-map:current"),
    ],
)
def test_snapshot_rejects_invalid_fields(field: str, value: object) -> None:
    payload = snapshot_payload()
    if field == "producer":
        payload[field] = value
    else:
        payload[field] = value

    with pytest.raises((TypeError, ValueError), match=field):
        SnapshotRef.from_dict(payload)


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({**artifact_payload(), "unexpected": True}, "unexpected"),
        ({**snapshot_payload(), "unexpected": True}, "unexpected"),
        ({"name": "builder", "version": "1.0", "unexpected": True}, "unexpected"),
    ],
)
def test_unknown_fields_are_rejected_with_field_specific_errors(
    payload: dict[str, object], field: str
) -> None:
    factory = {
        "source-document": ArtifactRef.from_dict,
        "code-map": SnapshotRef.from_dict,
        "producer": ProducerRef.from_dict,
    }
    if "kind" in payload:
        parser = factory[payload["kind"]]
    else:
        parser = factory["producer"]

    with pytest.raises(ValueError, match=field):
        parser(payload)


def test_snapshot_input_ref_rejects_an_artifact_shaped_mapping() -> None:
    artifact = artifact_payload()

    with pytest.raises(ValueError, match="schema"):
        SnapshotInputRef.from_dict(artifact)


def test_snapshot_input_ref_is_narrow_and_accepts_only_ref_and_hash() -> None:
    input_ref = SnapshotInputRef.from_dict({"ref": "artifact:source:readme", "content_hash": HASH})

    assert input_ref.to_dict() == {"ref": "artifact:source:readme", "content_hash": HASH}
    assert set(input_ref.to_dict()) == {"ref", "content_hash"}


def test_snapshot_addresses_artifact_without_reading_or_copying_its_content(tmp_path) -> None:
    location = tmp_path / "content-that-must-not-be-read"
    artifact = ArtifactRef(
        schema=1,
        kind="source-document",
        ref="artifact:source:missing",
        location=str(location),
        content_hash=HASH,
        scope_refs=("scope:project",),
    )

    snapshot = SnapshotRef(
        schema=1,
        kind="derived-view",
        ref="snapshot:derived:one",
        fingerprint="fp-derived-001",
        producer=ProducerRef("test-builder", "1.0"),
        inputs=(SnapshotInputRef(artifact.ref, artifact.content_hash),),
        generated_at="2026-08-20T10:30:00Z",
    )

    assert snapshot.inputs[0].to_dict() == {"ref": artifact.ref, "content_hash": HASH}
    assert not location.exists()


@pytest.mark.parametrize(
    ("field", "value"),
    [("ref", " "), ("content_hash", "sha256:" + "A" * 64)],
)
def test_snapshot_input_ref_rejects_invalid_fields(field: str, value: object) -> None:
    payload: dict[str, object] = {"ref": "artifact:source:readme", "content_hash": HASH}
    payload[field] = value

    with pytest.raises(ValueError, match=field):
        SnapshotInputRef.from_dict(payload)


def test_snapshot_input_ref_can_omit_content_hash() -> None:
    input_ref = SnapshotInputRef.from_dict({"ref": "artifact:source:readme"})

    assert input_ref.content_hash is None
    assert input_ref.to_dict() == {"ref": "artifact:source:readme"}


def test_snapshot_rejects_invalid_nested_input_hash() -> None:
    payload = deepcopy(snapshot_payload())
    inputs = payload["inputs"]
    assert isinstance(inputs, list)
    inputs[0]["content_hash"] = "sha256:" + "A" * 64

    with pytest.raises(ValueError, match="content_hash"):
        SnapshotRef.from_dict(payload)
