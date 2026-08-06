import pytest
from factory.requirements.register import Binding, Requirement


@pytest.fixture
def proposed_req(tmp_path):
    """A requirement agreed in substance, with its measurement still undecided."""
    return Requirement(
        id="SR-009",
        title="t",
        statement="s",
        domain="behavioral",
        upstream=[],
        binding=None,
        body="",
        path=tmp_path / "SR-009.md",
    )


@pytest.fixture
def bound_req(tmp_path):
    return Requirement(
        id="SR-001",
        title="t",
        statement="s",
        domain="behavioral",
        upstream=[],
        binding=Binding(
            harness="sim-testbench", experiment="e", metric="m", assert_expr=">= 0.9"
        ),
        body="",
        path=tmp_path / "SR-001.md",
    )
