from pathlib import Path

import pytest
from substrate.freshness.model import FreshnessSeverity

from coherence.register import markers
from coherence.register.closure import RequirementState, verify_sr_marker
from coherence.register.register import Binding, Requirement

pytestmark = pytest.mark.unit

_SR_EXPERIMENT_TEMPLATE = """import pytest


{preamble}


def test_example():
    assert True
"""


def _write_test(tmp_path: Path, rel: str, src: str) -> Path:
    path = tmp_path / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(src, encoding="utf-8")
    return path


def _bound_req(tmp_path: Path, req_id: str, experiment: str) -> Requirement:
    return Requirement(
        id=req_id,
        title="t",
        statement="When X, the system shall Y.",
        domain="behavioral",
        upstream=[],
        binding=Binding(
            experiment=experiment,
            metric="m",
            assert_expr=">= 0.90",
            harness="sim-testbench",
            trials=1,
            window=None,
        ),
        body="",
        path=tmp_path / "requirements" / f"{req_id}.md",
    )


# --------------------------------------------------------------------------
# marker collection (AST-based, never executes the test module)
# --------------------------------------------------------------------------


def test_collect_markers_deduplicates_within_a_file(tmp_path: Path):
    path = _write_test(
        tmp_path,
        "tests/test_sr_multi.py",
        '@pytest.mark.sr("SR-0001")\n'
        '@pytest.mark.sr("SR-0002")\n'
        "def test_first():\n"
        "    assert 1\n"
        "\n"
        '@pytest.mark.sr("SR-0002")\n'
        '@pytest.mark.sr("SR-0001", "SR-0003")\n'
        "def test_second():\n"
        "    assert 2\n",
    )
    collected = markers.collect_markers(path)
    assert collected == {"SR-0001", "SR-0002", "SR-0003"}
    assert len(collected) == 3, "duplicate marker text must collapse to a single set entry"


def test_collect_markers_matches_the_sr_id_string_exactly(tmp_path: Path):
    path = _write_test(
        tmp_path,
        "tests/test_sr_case.py",
        '@pytest.mark.sr("SR-0042")\n'
        '@pytest.mark.sr("sr-0042")\n'
        "def test_case():\n"
        "    assert 1\n",
    )
    collected = markers.collect_markers(path)
    # No normalization: "SR-0042" and "sr-0042" are distinct strings.
    assert "SR-0042" in collected
    assert "sr-0042" in collected


def test_collect_markers_ignores_unrelated_decorators(tmp_path: Path):
    path = _write_test(
        tmp_path,
        "tests/test_unrelated.py",
        "@pytest.mark.skip\n"
        "@pytest.mark.sr(\"SR-0099\")\n"
        "@not_a_marker.sr(\"SR-0999\")\n"
        "def test_skip():\n"
        "    assert 1\n",
    )
    assert markers.collect_markers(path) == {"SR-0099"}


# --------------------------------------------------------------------------
# closure integration: marker enforcement on path-bound experiments
# --------------------------------------------------------------------------


def test_a_bound_sr_resolving_to_a_test_file_without_the_marker_is_blocking(tmp_path: Path):
    experiment = "tests/test_sr_one.py"
    _write_test(tmp_path, experiment, "def test_example():\n    assert True\n")
    req = _bound_req(tmp_path, "SR-0001", experiment)
    finding = verify_sr_marker(req, project_root=tmp_path)
    assert finding is not None
    assert finding.req_id == "SR-0001"
    assert finding.severity is FreshnessSeverity.BLOCKING
    assert finding.state is RequirementState.PENDING
    assert "marker" in finding.detail.lower()


def test_a_matching_sr_marker_produces_no_finding(tmp_path: Path):
    experiment = "tests/test_sr_matched.py"
    _write_test(
        tmp_path,
        experiment,
        '@pytest.mark.sr("SR-0002")\n'
        "def test_example():\n"
        "    assert True\n",
    )
    req = _bound_req(tmp_path, "SR-0002", experiment)
    assert verify_sr_marker(req, project_root=tmp_path) is None
    # A different SR id pointing at the same file must NOT pass on a neighbour's marker.
    other = _bound_req(tmp_path, "SR-0003", experiment)
    assert verify_sr_marker(other, project_root=tmp_path) is not None


def test_a_command_experiment_yields_a_configuration_finding_not_a_guessed_marker(tmp_path: Path):
    req = _bound_req(tmp_path, "SR-0004", "patrol")
    finding = verify_sr_marker(req, project_root=tmp_path)
    assert finding is not None
    assert finding.state is RequirementState.CONFIGURATION
    assert finding.severity is FreshnessSeverity.WARNING
    # The closure must never pretend it verified a marker it could not inspect.
    assert "marker" in finding.detail.lower()
    assert "not an existing .py" in finding.detail.lower()


def test_a_nonexistent_py_path_is_a_configuration_finding_not_a_marker_result(tmp_path: Path):
    req = _bound_req(tmp_path, "SR-0005", "tests/no_such_file_exists.py")
    finding = verify_sr_marker(req, project_root=tmp_path)
    assert finding is not None
    assert finding.state is RequirementState.CONFIGURATION
    assert finding.severity is FreshnessSeverity.WARNING


def test_proposed_unbound_requirement_behaviour_is_unchanged(tmp_path: Path):
    proposed = Requirement(
        id="SR-0006",
        title="t",
        statement="When X, the system shall Y.",
        domain="behavioral",
        upstream=[],
        binding=None,
        body="",
        path=tmp_path / "requirements" / "SR-0006.md",
    )
    assert verify_sr_marker(proposed, project_root=tmp_path) is None