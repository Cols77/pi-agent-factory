from pathlib import Path
from unittest import mock

import pytest
from substrate.freshness.model import FreshnessSeverity

from coherence.policy.compiler import compile_obligations
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


def _write_sr(tmp_path: Path, req_id: str, experiment: str, *, profile: str | None = None) -> None:
    """Seed an SR trace node (requirements/SR-*.md) carrying a bound experiment,
    so the compiler can resolve the SR's profile off the trace graph. `profile`
    is an optional frontmatter override; when omitted the SR resolves to the
    project default (prototype)."""
    req_dir = tmp_path / "requirements"
    req_dir.mkdir(parents=True, exist_ok=True)
    profile_line = f"profile: {profile}\n" if profile else ""
    (req_dir / f"{req_id}.md").write_text(
        "---\n"
        f"id: {req_id}\n"
        "title: t\n"
        "statement: When X, the system shall Y.\n"
        "domain: behavioral\n"
        f"{profile_line}"
        "binding:\n"
        f"  experiment: {experiment}\n"
        "  metric: m\n"
        "  assert: '>= 0.9'\n"
        "  harness: sim-testbench\n"
        "---\n",
        encoding="utf-8",
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
#
# The missing-marker severity is NOT re-derived by the closure check from a raw
# profile string. It is read OFF the compiled `test_marker` obligation for the
# SR's scope (Task 6 addendum): the project-default `prototype` profile compiles
# to requiredness "required"; a `high_assurance` frontmatter override compiles
# to "blocking". Both assertions compare the finding's severity to the obligation
# built at that same scope.


def _test_marker_requiredness(root: Path, sr_id: str) -> str:
    obligation = next(
        o for o in compile_obligations(root, f"sr:{sr_id}") if o.kind == "test_marker"
    )
    return obligation.requiredness


def test_a_bound_sr_without_the_marker_is_required_under_the_default_profile(tmp_path: Path):
    # No `profile:` override -> the SR resolves to the project default
    # `prototype`, which compiles test_marker requiredness "required".
    experiment = "tests/test_sr_one.py"
    _write_test(tmp_path, experiment, "def test_example():\n    assert True\n")
    _write_sr(tmp_path, "SR-0001", experiment)
    req = _bound_req(tmp_path, "SR-0001", experiment)
    finding = verify_sr_marker(req, project_root=tmp_path)
    assert finding is not None
    assert finding.req_id == "SR-0001"
    # Severity comes from the SAME compiled test_marker obligation, not an
    # independent re-derivation of the raw profile string.
    assert _test_marker_requiredness(tmp_path, "SR-0001") == "required"
    assert finding.severity == _test_marker_requiredness(tmp_path, "SR-0001")
    assert finding.severity == "required"
    assert finding.state is RequirementState.PENDING
    assert "marker" in finding.detail.lower()


def test_a_bound_sr_without_the_marker_is_blocking_under_the_high_assurance_profile(tmp_path: Path):
    # A `profile: high_assurance` frontmatter override compiles test_marker
    # requiredness "blocking" -- preserving Task 3's original BLOCKING finding
    # under this specific profile.
    experiment = "tests/test_sr_high.py"
    _write_test(tmp_path, experiment, "def test_example():\n    assert True\n")
    _write_sr(tmp_path, "SR-0010", experiment, profile="high_assurance")
    req = _bound_req(tmp_path, "SR-0010", experiment)
    finding = verify_sr_marker(req, project_root=tmp_path)
    assert finding is not None
    assert finding.req_id == "SR-0010"
    assert finding.severity == FreshnessSeverity.BLOCKING
    assert finding.severity == _test_marker_requiredness(tmp_path, "SR-0010")
    assert finding.severity == "blocking"
    assert finding.state is RequirementState.PENDING
    assert "marker" in finding.detail.lower()


def test_a_bound_sr_under_an_uncompiled_profile_skips_the_finding_and_degrades(tmp_path: Path):
    # An `exploration`-profiled SR has no compiled test_marker obligation
    # (Increment 2B). The closure check must NOT silently fall back to the
    # project default and fabricate a severity; it reports the gap on the
    # errors channel and skips the finding.
    experiment = "tests/test_sr_explore.py"
    _write_test(tmp_path, experiment, "def test_example():\n    assert True\n")
    _write_sr(tmp_path, "SR-0011", experiment, profile="exploration")
    req = _bound_req(tmp_path, "SR-0011", experiment)
    errors: list[str] = []
    finding = verify_sr_marker(req, project_root=tmp_path, errors=errors)
    assert finding is None
    assert errors, "the degrade/errors channel must carry the uncompiled-profile message"
    assert any("exploration" in e for e in errors)
    assert any("not yet compiled" in e or "uncompiled" in e for e in errors)


def test_a_matching_sr_marker_produces_no_finding(tmp_path: Path):
    experiment = "tests/test_sr_matched.py"
    _write_test(
        tmp_path,
        experiment,
        '@pytest.mark.sr("SR-0002")\n'
        "def test_example():\n"
        "    assert True\n",
    )
    _write_sr(tmp_path, "SR-0002", experiment)
    _write_sr(tmp_path, "SR-0003", experiment)  # neighbour SR, same file, no own marker
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


# --------------------------------------------------------------------------
# graceful degradation on unreadable / malformed / non-UTF8 experiment files
# --------------------------------------------------------------------------


def test_a_malformed_non_parseable_experiment_is_a_configuration_warning(tmp_path: Path):
    # A resolved .py whose source is not valid Python must NOT crash the closure;
    # it is an inspection problem, reported as a CONFIGURATION/WARNING finding.
    experiment = "tests/test_sr_malformed.py"
    _write_test(tmp_path, experiment, "def broken(:\n    this is not python\n")
    req = _bound_req(tmp_path, "SR-0007", experiment)
    finding = verify_sr_marker(req, project_root=tmp_path)
    assert finding is not None
    assert finding.state is RequirementState.CONFIGURATION
    assert finding.severity is FreshnessSeverity.WARNING
    assert "could not be inspected" in finding.detail.lower()


def test_a_non_utf8_experiment_files_is_a_configuration_warning(tmp_path: Path):
    # The file must satisfy the .py/is_file() pre-check, so write bytes that are
    # valid "source" but not decodable as UTF-8 (e.g. latin-1 accents). verify
    # must not raise and must not be treated as a healthy pass.
    experiment = "tests/test_sr_latin1.py"
    path = tmp_path / experiment
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"# \xE9\xE9\xE9\nS0\n")  # latin-1 bytes, not UTF-8
    req = _bound_req(tmp_path, "SR-0008", experiment)
    finding = verify_sr_marker(req, project_root=tmp_path)
    assert finding is not None
    assert finding.state is RequirementState.CONFIGURATION
    assert finding.severity is FreshnessSeverity.WARNING


def test_an_unreadable_experiment_file_is_a_configuration_warning_not_a_crash(tmp_path: Path):
    # Reading a real file gives no deterministic PermissionError on git-bash /
    # Windows (chmod 000 is not enforced), and  a directory path would not pass
    # resolve_experiment_path's .py + is_file() pre-check (a TOCTOU gap). Force
    # the read to fail with a PermissionError (subclass of OSError) to exercise
    # the graceful IO path deterministically on every platform.
    experiment = "tests/test_sr_unreadable.py"
    _write_test(tmp_path, experiment, "def test_example():\n    assert True\n")
    req = _bound_req(tmp_path, "SR-0009", experiment)
    with mock.patch(
        "pathlib.Path.read_text",
        side_effect=PermissionError(13, "Permission denied"),
    ):
        finding = verify_sr_marker(req, project_root=tmp_path)
    assert finding is not None
    assert finding.state is RequirementState.CONFIGURATION
    assert finding.severity is FreshnessSeverity.WARNING
    assert "could not be inspected" in finding.detail.lower()