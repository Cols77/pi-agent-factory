import sys
import pytest

sys.path.insert(0, "scripts/gates")
from _proc import run_and_propagate  # noqa: E402

pytestmark = pytest.mark.unit


def test_zero_exit_propagates():
    assert run_and_propagate([sys.executable, "-c", "raise SystemExit(0)"]) == 0


def test_nonzero_exit_propagates():
    assert run_and_propagate([sys.executable, "-c", "raise SystemExit(3)"]) == 3
