"""T-031 traces to gh-issue:1 via NC-0001 (spec section 5) -- exercised against
the real repo tree, not a tmp_path fixture, because the point is to prove the
actual on-disk task and nonconformance record link, not a synthetic one."""
from __future__ import annotations

from pathlib import Path

import pytest

from factory.memory.nonconformance import load_nonconformances
from substrate.ledger.tasks import Justification, load_tasks

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_t031_corrects_nc_0001():
    task = next(t for t in load_tasks(REPO_ROOT / "tasks") if t.id == "T-031")
    assert task.justification == [Justification("corrects", "NC-0001")]

    nc = load_nonconformances(REPO_ROOT)["NC-0001"]
    assert nc.corrected_by == "T-031"
    assert nc.external_ref == "gh-issue:1"
