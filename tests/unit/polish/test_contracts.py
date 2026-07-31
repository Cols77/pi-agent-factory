import pytest
from factory.polish.finding import Finding
from factory.polish.playground import Playground, PlaygroundSession

pytestmark = pytest.mark.unit


def test_finding_defaults():
    f = Finding(usecase="u", description="d")
    assert f.snapshot == {} and f.sr is None and f.artifacts == []
    full = Finding("u", "d", snapshot={"k": 1}, sr="SR-001", artifacts=["a.png"])
    assert full.snapshot == {"k": 1} and full.sr == "SR-001" and full.artifacts == ["a.png"]


def test_session_teardown_invokes_callback():
    calls = []
    s = PlaygroundSession(entrypoints=["http://x"], describe="d", on_teardown=lambda: calls.append(1))
    s.teardown()
    assert calls == [1]
    # No callback → teardown is a no-op, not an error.
    PlaygroundSession().teardown()


def test_playground_is_structural():
    class Ref:
        def list_usecases(self):
            return ["a"]

        def setup(self, usecase):
            return PlaygroundSession()

    assert isinstance(Ref(), Playground)
    assert not isinstance(object(), Playground)
