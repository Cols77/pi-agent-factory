import pytest
from factory.doctor.write import mint, promote
from factory.requirements.register import is_checksum_current, parse_requirement

pytestmark = pytest.mark.unit


def _repo(tmp_path):
    specs = tmp_path / "docs" / "superpowers" / "specs"
    specs.mkdir(parents=True)
    (specs / "a.md").write_text("# A\n", encoding="utf-8")
    mint(tmp_path, "docs/superpowers/specs/a.md", "t", "s", "behavioral")
    return tmp_path


def _declare_scorers(repo, pkg: str, body: str) -> None:
    d = repo / "src" / pkg
    d.mkdir(parents=True)
    (d / "__init__.py").write_text("", encoding="utf-8")
    (d / "scorers.py").write_text(body, encoding="utf-8")
    (repo / ".factory").mkdir(exist_ok=True)
    (repo / ".factory" / "factory.yaml").write_text(
        "harnesses:\n  sim-testbench:\n    type: sim-testbench\n"
        f"    traces_dir: validation/traces\n    scorers: {pkg}.scorers\n"
        'gates:\n  unit:\n    - { cmd: "true" }\n',
        encoding="utf-8",
    )


def test_promote_binds_the_requirement_and_writes_a_current_checksum(tmp_path):
    path, implemented = promote(
        _repo(tmp_path),
        "SR-001",
        "sim-testbench",
        "demo_experiment",
        "demo_rate",
        ">= 0.90",
        trials=20,
    )
    req = parse_requirement(path)
    assert req.binding is not None
    assert req.binding.trials == 20
    assert req.binding.metric == "demo_rate"
    assert is_checksum_current(req) is True
    assert implemented is False  # no .factory/factory.yaml in this repo


def test_promote_records_the_window_when_given(tmp_path):
    path, _ = promote(
        _repo(tmp_path),
        "SR-001",
        "sim-testbench",
        "e",
        "m",
        ">= 0.9",
        window={"after_event": "zone_clear", "within_s": 5},
    )
    assert parse_requirement(path).binding.window == {"after_event": "zone_clear", "within_s": 5}


def test_promote_reports_an_implemented_metric(tmp_path):
    repo = _repo(tmp_path)
    _declare_scorers(repo, "demo_promote_ok", "SCORERS = {'demo_rate': lambda f, w: True}\n")
    _, implemented = promote(
        repo, "SR-001", "sim-testbench", "demo_experiment", "demo_rate", ">= 0.90"
    )
    assert implemented is True


def test_promote_does_not_refuse_an_unimplemented_metric(tmp_path):
    # "bound, and we know it cannot run yet" is a state the register can hold.
    # Refusing would push it back into prose.
    repo = _repo(tmp_path)
    _declare_scorers(repo, "demo_promote_gap", "SCORERS = {'something_else': lambda f, w: True}\n")
    path, implemented = promote(
        repo, "SR-001", "sim-testbench", "e", "not_built_yet", ">= 0.9"
    )
    assert implemented is False
    assert parse_requirement(path).binding.metric == "not_built_yet"


def test_promote_refuses_an_unknown_requirement(tmp_path):
    with pytest.raises(ValueError, match="SR-404"):
        promote(_repo(tmp_path), "SR-404", "sim-testbench", "e", "m", ">= 0.9")
