from pathlib import Path

import pytest

from factory.polish.finding import Finding
from factory.polish.gates import Gate1, Gate2
from factory.polish.worker import LandedChange

pytestmark = pytest.mark.unit


def _f(desc="x"):
    return Finding(usecase="sign-in", description=desc)


def test_gate1_accept_returns_and_clears():
    g = Gate1()
    gid = g.add(_f("broken"))
    assert list(g.pending()) == [gid]
    f = g.accept(gid)
    assert f.description == "broken"
    assert g.pending() == {}


def test_gate1_edit_applies_changes_then_returns():
    g = Gate1()
    gid = g.add(_f("typo desc"))
    f = g.edit(gid, description="clearer desc", sr="SR-010")
    assert f.description == "clearer desc" and f.sr == "SR-010"
    assert g.pending() == {}


def test_gate1_discard_drops():
    g = Gate1()
    gid = g.add(_f())
    g.discard(gid)
    assert g.pending() == {}
    with pytest.raises(KeyError):
        g.accept(gid)


def _landed(desc="x", sr=None, status="landed"):
    f = Finding(usecase="sign-in", description=desc, sr=sr)
    return LandedChange(finding=f, task_path=Path("tasks/T-007.md"), task_id="T-007", status=status)


def test_gate2_tick_accepts_and_returns_sr_finding():
    g = Gate2()
    gid = g.add(_landed(sr="SR-010"))
    reground = g.tick(gid)
    assert reground is not None and reground.sr == "SR-010"
    assert g.rows()[0].verdict == "accepted"


def test_gate2_tick_without_sr_returns_none():
    g = Gate2()
    gid = g.add(_landed(sr=None))
    assert g.tick(gid) is None
    assert g.rows()[0].verdict == "accepted"


def test_gate2_comment_spawns_linked_rework_finding():
    g = Gate2()
    gid = g.add(_landed(desc="sign-in fix", sr="SR-010"))
    rework = g.comment(gid, "still fails on Safari")
    assert "still fails on Safari" in rework.description
    assert rework.sr == "SR-010"
    assert rework.snapshot.get("rework_of") == "T-007"
    assert g.rows()[0].verdict == "wrong"
