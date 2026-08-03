import pytest

from factory.polish.finding import Finding
from factory.polish.gates import Gate1

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
