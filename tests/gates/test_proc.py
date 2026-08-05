import sys
import pytest

sys.path.insert(0, "scripts/gates")
from _proc import run_and_propagate  # noqa: E402

pytestmark = pytest.mark.unit


def test_zero_exit_propagates():
    assert run_and_propagate([sys.executable, "-c", "raise SystemExit(0)"]) == 0


def test_nonzero_exit_propagates():
    assert run_and_propagate([sys.executable, "-c", "raise SystemExit(3)"]) == 3


def test_run_and_propagate_treats_no_pytest_tests_collected_as_success():
    # all.py runs AGENT_CMD; every agent-marked test is a drone test, so after the
    # split that selection is empty and pytest exits 5. "This project has no agent
    # tests" must not fail the pipeline.
    import importlib.util
    import sys

    spec = importlib.util.spec_from_file_location("_proc_t", "scripts/gates/_proc.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    exit5 = [sys.executable, "-c", "import sys; sys.exit(5)"]
    assert mod.run_and_propagate([*exit5[:2], "import sys; sys.exit(5)", "pytest"]) == 0
    # a non-pytest tool exiting 5 is a real failure and must survive
    assert mod.run_and_propagate(exit5) == 5
    assert mod.run_and_propagate([sys.executable, "-c", "import sys; sys.exit(1)", "pytest"]) == 1
    assert mod.run_and_propagate([sys.executable, "-c", "import sys; sys.exit(0)", "pytest"]) == 0
