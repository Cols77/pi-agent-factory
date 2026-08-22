"""Developer-checkpoint store (Inc 7 Task 1).

A checkpoint records the last commit at which a feature was reviewed. It is
*recorded, never inferred* (spec §31 `developer_checkpoint.commit`), so a
missing checkpoint is a legitimate state (`None`), not an error, and a
malformed store file degrades rather than crashes.
"""

from __future__ import annotations

import json

import pytest

from factory.delta.checkpoint import (
    Checkpoint,
    checkpoints_path,
    load_checkpoint,
    save_checkpoint,
)

pytestmark = pytest.mark.unit


def test_round_trip(tmp_path):
    cp = Checkpoint(
        feature="FEAT-NAV-017",
        commit="abc123",
        reviewed_at="2026-08-16T10:00:00Z",
    )
    save_checkpoint(tmp_path, cp)
    assert load_checkpoint(tmp_path, "FEAT-NAV-017") == cp


def test_checkpoint_file_location(tmp_path):
    save_checkpoint(tmp_path, Checkpoint("FEAT-A", "c1", "t1"))
    assert checkpoints_path(tmp_path).name == "checkpoints.json"
    assert checkpoints_path(tmp_path).exists()


def test_missing_feature_returns_none(tmp_path):
    assert load_checkpoint(tmp_path, "FEAT-NAV-017") is None


def test_missing_feature_when_other_features_exist(tmp_path):
    save_checkpoint(tmp_path, Checkpoint("FEAT-A", "c1", "t1"))
    assert load_checkpoint(tmp_path, "FEAT-B") is None


def test_save_overwrites_same_feature(tmp_path):
    save_checkpoint(tmp_path, Checkpoint("FEAT-A", "c1", "t1"))
    save_checkpoint(tmp_path, Checkpoint("FEAT-A", "c2", "t2"))
    loaded = load_checkpoint(tmp_path, "FEAT-A")
    assert loaded is not None
    assert loaded.commit == "c2"
    assert loaded.reviewed_at == "t2"


def test_multiple_features_preserved(tmp_path):
    save_checkpoint(tmp_path, Checkpoint("FEAT-A", "c1", "t1"))
    save_checkpoint(tmp_path, Checkpoint("FEAT-B", "c2", "t2"))
    assert load_checkpoint(tmp_path, "FEAT-A") == Checkpoint("FEAT-A", "c1", "t1")
    assert load_checkpoint(tmp_path, "FEAT-B") == Checkpoint("FEAT-B", "c2", "t2")


def test_malformed_file_degrades_to_none(tmp_path):
    (tmp_path / "checkpoints.json").write_text("{not json", encoding="utf-8")
    assert load_checkpoint(tmp_path, "FEAT-A") is None


def test_non_dict_root_degrades_to_none(tmp_path):
    (tmp_path / "checkpoints.json").write_text("[1, 2]", encoding="utf-8")
    assert load_checkpoint(tmp_path, "FEAT-A") is None


def test_invalid_entries_are_skipped(tmp_path):
    (tmp_path / "checkpoints.json").write_text(
        json.dumps(
            {
                "FEAT-A": {"commit": "c1", "reviewed_at": "t1"},
                "FEAT-BAD": {"commit": 5, "reviewed_at": None},
            }
        ),
        encoding="utf-8",
    )
    assert load_checkpoint(tmp_path, "FEAT-A") == Checkpoint("FEAT-A", "c1", "t1")
    assert load_checkpoint(tmp_path, "FEAT-BAD") is None
