from __future__ import annotations

from pathlib import Path

import frontmatter as fm
import pytest

from coherence.register.fidelity_packet import build_fidelity_packet

pytestmark = pytest.mark.unit

# SR-050/AC-4 (T5.1): the packet builder is a pure reader/composer, no
# judgement -- see src/coherence/register/fidelity_packet.py's own docstring.


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _write_meta(path: Path, meta: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(fm.dumps(fm.Post("body", **meta)), encoding="utf-8")
    return path


def _sr(**overrides) -> dict:
    meta = {"id": "SR-900", "title": "t", "statement": "s", "domain": "behavioral"}
    meta.update(overrides)
    return meta


def _write_prod(root: Path) -> None:
    _write(
        root / "src" / "widgets" / "feature.py",
        "def feature_context():\n"
        "    return 1\n"
        "\n"
        "\n"
        "def other_symbol():\n"
        "    return 2\n",
    )


def _write_test_file(root: Path) -> None:
    _write(
        root / "tests" / "unit" / "test_feature.py",
        "def test_feature_context():\n"
        "    assert True\n"
        "\n"
        "\n"
        "def test_other():\n"
        "    assert True\n",
    )


@pytest.mark.sr("SR-050")
def test_packet_includes_resolved_relations_with_signature_and_bounded_excerpt(tmp_path: Path):
    _write_prod(tmp_path)
    _write_test_file(tmp_path)
    _write_meta(
        tmp_path / "requirements" / "SR-900.md",
        _sr(
            implemented_by=[
                {"path": "src/widgets/feature.py", "symbol": "widgets.feature:feature_context"}
            ],
            verified_by=[
                {"path": "tests/unit/test_feature.py", "test": "tests/unit/test_feature.py::test_feature_context"}
            ],
        ),
    )
    packet = build_fidelity_packet(tmp_path, "SR-900")
    assert len(packet.implemented) == 1
    impl = packet.implemented[0]
    assert impl.path == "src/widgets/feature.py"
    assert impl.symbol == "widgets.feature:feature_context"
    assert impl.signature.name == "feature_context"
    assert "return 1" in impl.source_excerpt
    # Sliced up to (not including) the next signature.
    assert "other_symbol" not in impl.source_excerpt

    assert len(packet.verified) == 1
    ver = packet.verified[0]
    assert ver.path == "tests/unit/test_feature.py"
    assert ver.test == "tests/unit/test_feature.py::test_feature_context"
    assert ver.signature is not None
    assert ver.signature.name == "test_feature_context"
    assert "assert True" in ver.source_excerpt
    assert "test_other" not in ver.source_excerpt


@pytest.mark.sr("SR-050")
def test_an_unresolved_relation_appears_in_unresolved_not_in_implemented(tmp_path: Path):
    _write_prod(tmp_path)
    _write_meta(
        tmp_path / "requirements" / "SR-900.md",
        _sr(
            implemented_by=[
                {"path": "src/widgets/feature.py", "symbol": "widgets.feature:does_not_exist"}
            ]
        ),
    )
    packet = build_fidelity_packet(tmp_path, "SR-900")
    assert packet.implemented == ()
    assert len(packet.unresolved) == 1
    assert packet.unresolved[0].field == "implemented_by"


@pytest.mark.sr("SR-050")
def test_design_source_resolves_doc_and_anchor_excerpt(tmp_path: Path):
    _write(
        tmp_path / "docs" / "spec.md",
        "# Title\n\nintro\n\n## Canonical relations\n\nbody text here\n\n## Next section\n\nother\n",
    )
    _write_meta(
        tmp_path / "requirements" / "SR-900.md",
        _sr(source="docs/spec.md#canonical-relations"),
    )
    packet = build_fidelity_packet(tmp_path, "SR-900")
    assert packet.design_source is not None
    assert packet.design_source.doc_path == "docs/spec.md"
    assert packet.design_source.anchor == "canonical-relations"
    assert "body text here" in packet.design_source.excerpt
    assert "other" not in packet.design_source.excerpt
    assert packet.diagnostics == ()


@pytest.mark.sr("SR-050")
def test_design_source_missing_doc_yields_none_with_diagnostic(tmp_path: Path):
    _write_meta(
        tmp_path / "requirements" / "SR-900.md",
        _sr(source="docs/does-not-exist.md#anchor"),
    )
    packet = build_fidelity_packet(tmp_path, "SR-900")
    assert packet.design_source is None
    assert any("design_source" in d for d in packet.diagnostics)


@pytest.mark.sr("SR-050")
def test_design_source_unresolvable_anchor_yields_none_with_diagnostic(tmp_path: Path):
    _write(tmp_path / "docs" / "spec.md", "# Title\n\nintro\n")
    _write_meta(
        tmp_path / "requirements" / "SR-900.md",
        _sr(source="docs/spec.md#no-such-anchor"),
    )
    packet = build_fidelity_packet(tmp_path, "SR-900")
    assert packet.design_source is None
    assert any("anchor" in d for d in packet.diagnostics)


@pytest.mark.sr("SR-050")
def test_import_overlap_reports_none_when_not_resolved(tmp_path: Path):
    # A verified test that imports nothing from the implemented file: the
    # overlap computation still returns status "resolved" (import closure
    # walked fine, it just found no overlap) unless the source type itself
    # is unsupported. Use a non-Python "verified" path with no `test` (file
    # -only validation) to force compute_overlap's "unsupported" status,
    # proving reaches stays None rather than being coerced to False.
    _write_prod(tmp_path)
    _write(tmp_path / "docs" / "runbook.md", "not python\n")
    _write_meta(
        tmp_path / "requirements" / "SR-900.md",
        _sr(
            implemented_by=[
                {"path": "src/widgets/feature.py", "symbol": "widgets.feature:feature_context"}
            ],
            verified_by=[{"path": "docs/runbook.md"}],
        ),
    )
    packet = build_fidelity_packet(tmp_path, "SR-900")
    assert len(packet.import_overlap) == 1
    fact = packet.import_overlap[0]
    assert fact.status != "resolved"
    assert fact.reaches is None


@pytest.mark.sr("SR-050")
def test_outcome_uses_newest_manifest_naming_the_exact_test_node(tmp_path: Path, monkeypatch):
    _write_test_file(tmp_path)
    _write_meta(
        tmp_path / "requirements" / "SR-900.md",
        _sr(
            verified_by=[
                {"path": "tests/unit/test_feature.py", "test": "tests/unit/test_feature.py::test_feature_context"}
            ]
        ),
    )
    manifests_dir = tmp_path / "evidence" / "runs"
    manifests_dir.mkdir(parents=True)
    import json

    zero = "0" * 64

    def _manifest(run_id: str, ended_at: str, passed: bool) -> dict:
        return {
            "schema_version": 2,
            "run_id": run_id,
            "task_id": "T-1",
            "started_at": ended_at,
            "ended_at": ended_at,
            "start_commit": "a" * 40,
            "result_commit": "a" * 40,
            "outcome": "completed",
            "inputs": {
                "task": {"path": "tasks/T-1.md", "sha256": zero},
                "requirements": [{"id": "SR-900", "path": "requirements/SR-900.md", "sha256": zero}],
                "factory_config_sha256": zero,
            },
            "dependencies": [],
            "implementation": {"changed_files": [], "patch": {"sha256": zero, "size": 0, "media_type": "text/x-diff"}},
            "validation": [
                {
                    "requirements": [
                        {
                            "id": "SR-900",
                            "passed": passed,
                            "tests": ["tests/unit/test_feature.py::test_feature_context"],
                        }
                    ]
                }
            ],
            "reviews": [],
            "decisions": [],
            "publication": {"state": "local", "errors": []},
        }

    (manifests_dir / "run-1.json").write_text(json.dumps(_manifest("run-1", "2026-09-01T00:00:00Z", False)), encoding="utf-8")
    (manifests_dir / "run-2.json").write_text(json.dumps(_manifest("run-2", "2026-09-02T00:00:00Z", True)), encoding="utf-8")

    packet = build_fidelity_packet(tmp_path, "SR-900")
    outcome = packet.verified[0].outcome
    assert outcome is not None
    assert outcome.state == "passed"
    assert outcome.last_run_id == "run-2"


@pytest.mark.sr("SR-050")
def test_outcome_falls_back_to_sr_level_status_when_no_manifest_names_the_node(tmp_path: Path):
    _write_test_file(tmp_path)
    _write_meta(
        tmp_path / "requirements" / "SR-900.md",
        _sr(
            verified_by=[
                {"path": "tests/unit/test_feature.py", "test": "tests/unit/test_feature.py::test_feature_context"}
            ]
        ),
    )
    _write(
        tmp_path / "validation" / "validation-report.json",
        (
            '{"provenance": {"recorded_by": "harness", "recorded_at": '
            '"2026-09-01T00:00:00Z", "command": "pytest -m sr"}, '
            '"requirements": [{"id": "SR-900", "passed": true, "metric": "m", '
            '"value": 1.0, "assert": ">= 0", "trials": 1}]}'
        ),
    )
    packet = build_fidelity_packet(tmp_path, "SR-900")
    outcome = packet.verified[0].outcome
    assert outcome is not None
    assert outcome.state == "passed"
    assert outcome.last_run_id is None


@pytest.mark.sr("SR-050")
def test_outcome_stays_never_validated_when_neither_source_has_it(tmp_path: Path):
    _write_test_file(tmp_path)
    _write_meta(
        tmp_path / "requirements" / "SR-900.md",
        _sr(
            verified_by=[
                {"path": "tests/unit/test_feature.py", "test": "tests/unit/test_feature.py::test_feature_context"}
            ]
        ),
    )
    packet = build_fidelity_packet(tmp_path, "SR-900")
    outcome = packet.verified[0].outcome
    assert outcome is not None
    assert outcome.state == "never_validated"
