"""Human-only known-flaky registry tests (RED first).

The registry is a read path for the driver and a human-only writer: one JSON
record per test at ``flaky-tests/<safe-test-id-slug>.json``, schema 1, with
``decided_by`` and a nullable ``review_after`` expiry (no separate ``owner``).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from coherence.execution.flaky_registry import (
    FlakyRecord,
    FlakyRegistryError,
    flaky_path,
    is_registered_flaky,
    read_flaky,
    register_flaky,
)

pytestmark = pytest.mark.unit

TEST_ID = "tests/test_feature.py::test_eventually_consistent"


def test_registry_round_trip_and_human_only_fields(tmp_path: Path) -> None:
    record = register_flaky(
        tmp_path,
        TEST_ID,
        reason="external service is nondeterministic",
        decided_by="human",
        decided_at="2026-09-10T00:00:00Z",
        review_after=None,
    )

    assert read_flaky(tmp_path, record.test_id) == record
    assert record.schema == 1
    assert record.decided_by == "human"
    assert record.review_after is None
    assert flaky_path(tmp_path, TEST_ID).parent.name == "flaky-tests"
    assert flaky_path(tmp_path, TEST_ID).name.endswith(".json")
    assert is_registered_flaky(tmp_path, TEST_ID) is True
    assert is_registered_flaky(tmp_path, "tests/test_feature.py::test_other") is False


def test_registry_rejects_non_human_or_malformed_records(tmp_path: Path) -> None:
    path = flaky_path(tmp_path, TEST_ID)
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps({"schema": 1, "test_id": "x", "decided_by": "agent"}),
        encoding="utf-8",
    )

    with pytest.raises(FlakyRegistryError, match="decided_by"):
        read_flaky(tmp_path, TEST_ID)


def test_register_rejects_every_non_human_decider(tmp_path: Path) -> None:
    for decider in ("agent", "driver", "", "Human"):
        with pytest.raises(FlakyRegistryError, match="decided_by"):
            register_flaky(
                tmp_path,
                TEST_ID,
                reason="r",
                decided_by=decider,
                decided_at="2026-09-10T00:00:00Z",
            )


def test_registry_rejects_malformed_slugs_and_escaping_test_ids(tmp_path: Path) -> None:
    for bad_id in ("", "   ", "/etc/passwd", "../../etc/passwd", "tests\\..\\evil", "tests//x"):
        with pytest.raises(FlakyRegistryError):
            flaky_path(tmp_path, bad_id)
    with pytest.raises(FlakyRegistryError):
        register_flaky(
            tmp_path,
            "../../escape",
            reason="r",
            decided_by="human",
            decided_at="2026-09-10T00:00:00Z",
        )
    # Nothing may have escaped the flaky-tests directory.
    strays = [p for p in tmp_path.rglob("*") if p.is_file()]
    assert strays == []


def test_registry_rejects_bad_schema_ids_and_iso(tmp_path: Path) -> None:
    path = flaky_path(tmp_path, TEST_ID)
    path.parent.mkdir(parents=True)

    base = {
        "schema": 1,
        "test_id": TEST_ID,
        "reason": "r",
        "decided_by": "human",
        "decided_at": "2026-09-10T00:00:00Z",
        "review_after": None,
    }
    for broken in (
        {**base, "schema": 2},
        {**base, "test_id": "tests/other.py::test_x", "reason": "r"},
        {**base, "review_after": "not-an-instant"},
        {**base, "decided_at": "yesterday"},
        {**base, "reason": "  "},
    ):
        path.write_text(json.dumps(broken), encoding="utf-8")
        with pytest.raises(FlakyRegistryError):
            read_flaky(tmp_path, TEST_ID)

    with pytest.raises(FlakyRegistryError, match="decided_by"):
        register_flaky(
            tmp_path,
            "tests/test_feature.py::test_x",
            reason="r",
            decided_by="agent",
            decided_at="2026-09-10T00:00:00Z",
            review_after="2026-10-10T00:00:00Z",
        )


def test_written_record_has_no_owner_key(tmp_path: Path) -> None:
    record = register_flaky(
        tmp_path,
        "tests/unit/coherence/test_flaky_registry.py::test_x",
        reason="r",
        decided_by="human",
        decided_at="2026-09-10T00:00:00Z",
        review_after="2026-12-10T00:00:00Z",
    )
    payload = json.loads(flaky_path(tmp_path, record.test_id).read_text(encoding="utf-8"))
    assert "owner" not in payload
    assert set(payload) == {
        "schema",
        "test_id",
        "reason",
        "decided_by",
        "decided_at",
        "review_after",
    }
    assert isinstance(record, FlakyRecord)


def test_read_flaky_is_a_read_only_driver_path(tmp_path: Path) -> None:
    with pytest.raises(FlakyRegistryError):
        read_flaky(tmp_path, "tests/test_feature.py::test_never_registered")
    assert not (tmp_path / "flaky-tests").exists()
