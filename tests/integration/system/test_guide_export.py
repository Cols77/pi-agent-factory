"""Integration tests for guide export and the non-readmission rule (design
SS4.5).

Self-contained (matches `test_navigator_projection.py`'s convention rather
than importing `tests/unit/system/_fixtures.py`; `tests/unit`/`tests/
integration` are separate top-level packages with no shared `__init__.py`
chain, so a cross-directory relative import would be fragile).
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from factory.system.guide import EXPORTED_GUIDE_ARTIFACT_MARKER, export_guide, is_exported_guide, query_guide
from factory.system.models import SystemScopeRef
from factory.system.queries import query_brief

pytestmark = pytest.mark.integration

_SR_BOUND = """---
id: SR-001
title: "Demo requirement"
statement: "When X happens, the system shall Y."
domain: behavioral
upstream: []
binding:
  harness: sim-testbench
  experiment: demo_experiment
  metric: demo_rate
  trials: 1
  assert: ">= 0.5"
checksum: null
---
Rationale.
"""

_ISO_TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def _write_sr_repo(root: Path) -> None:
    (root / "requirements").mkdir(parents=True, exist_ok=True)
    (root / "requirements" / "SR-001.md").write_text(_SR_BOUND, encoding="utf-8")
    validation_dir = root / "validation"
    validation_dir.mkdir(parents=True, exist_ok=True)
    (validation_dir / "validation-report.json").write_text(
        json.dumps({"requirements": [{"id": "SR-001", "passed": True, "stale": False, "artifacts": []}]}),
        encoding="utf-8",
    )


@pytest.fixture()
def repo(tmp_path) -> Path:
    _write_sr_repo(tmp_path)
    return tmp_path


_SCOPE = SystemScopeRef(kind="sr", ref="sr:SR-001")


# ---------------------------------------------------------------------------
# The write path: generation timestamp, full citation set, the
# not-a-source-of-truth header, and a confined destination.
# ---------------------------------------------------------------------------


def test_export_writes_generation_timestamp_and_full_citation_set(repo):
    dest = repo / "exports" / "guide.json"

    written = export_guide(repo, _SCOPE, dest)

    assert written == dest.resolve()
    doc = json.loads(dest.read_text(encoding="utf-8"))

    assert _ISO_TIMESTAMP_RE.match(doc["generated_at"]), doc["generated_at"]

    guide_payload = query_guide(repo, _SCOPE)
    expected_citations: list[dict] = []
    for section in guide_payload["sections"]:
        for citation in section["citations"]:
            if citation not in expected_citations:
                expected_citations.append(citation)

    assert doc["citations"] == expected_citations
    assert len(doc["citations"]) > 0  # this fixture has real citations to carry


def test_export_carries_not_a_source_of_truth_header(repo):
    dest = repo / "exports" / "guide.json"
    export_guide(repo, _SCOPE, dest)
    doc = json.loads(dest.read_text(encoding="utf-8"))

    assert doc["artifact"] == EXPORTED_GUIDE_ARTIFACT_MARKER
    warning = doc["warning"].lower()
    assert "point-in-time" in warning
    assert "not" in warning and "source of truth" in warning


def test_export_path_confined_inside_evidence_directory_is_rejected(repo):
    (repo / "evidence").mkdir(parents=True, exist_ok=True)
    with pytest.raises(ValueError, match="evidence"):
        export_guide(repo, _SCOPE, repo / "evidence" / "guide.json")


def test_export_path_confined_inside_bundles_directory_is_rejected(repo):
    with pytest.raises(ValueError, match="bundles"):
        export_guide(repo, _SCOPE, repo / "bundles" / "guide.json")


def test_export_path_confined_inside_requirements_directory_is_rejected(repo):
    with pytest.raises(ValueError, match="requirements"):
        export_guide(repo, _SCOPE, repo / "requirements" / "guide.json")


def test_export_path_escaping_repo_root_is_rejected(repo, tmp_path_factory):
    outside = tmp_path_factory.mktemp("outside-repo") / "guide.json"
    with pytest.raises(ValueError, match="escapes repo root"):
        export_guide(repo, _SCOPE, outside)


def test_export_lands_outside_every_forbidden_directory_when_confined(repo):
    dest = repo / "exports" / "guide.json"
    written = export_guide(repo, _SCOPE, dest)

    resolved = written.resolve()
    for forbidden in ("evidence", "bundles", "requirements"):
        assert (repo / forbidden).resolve() not in resolved.parents
        assert resolved != (repo / forbidden).resolve()


# ---------------------------------------------------------------------------
# Nothing is written unless --export is passed explicitly.
# ---------------------------------------------------------------------------


def test_guide_query_alone_writes_nothing(repo):
    before = {p for p in repo.rglob("*") if p.is_file()}
    query_guide(repo, _SCOPE)
    after = {p for p in repo.rglob("*") if p.is_file()}
    assert before == after


def test_cli_guide_without_export_flag_writes_nothing(repo):
    before = {p for p in repo.rglob("*") if p.is_file()}
    result = subprocess.run(
        [sys.executable, "-m", "factory.system", "guide", "--scope", "sr:SR-001", "--repo-root", str(repo), "--json"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    after = {p for p in repo.rglob("*") if p.is_file()}
    assert before == after


def test_cli_guide_with_export_flag_writes_exactly_the_requested_file(repo):
    dest = repo / "exports" / "guide.json"
    result = subprocess.run(
        [
            sys.executable, "-m", "factory.system", "guide",
            "--scope", "sr:SR-001", "--repo-root", str(repo), "--json",
            "--export", str(dest),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert dest.is_file()
    doc = json.loads(dest.read_text(encoding="utf-8"))
    assert doc["artifact"] == EXPORTED_GUIDE_ARTIFACT_MARKER

    # stdout stays pure JSON; the confirmation of where the file actually
    # landed goes to stderr (review round 1 finding: cmd_guide previously
    # discarded export_guide's returned path).
    json.loads(result.stdout)
    assert "guide exported to" in result.stderr
    assert str(dest.resolve()) in result.stderr


# ---------------------------------------------------------------------------
# Non-readmission: an exported guide can never re-enter as evidence.
# ---------------------------------------------------------------------------


def test_is_exported_guide_true_for_a_real_export_false_for_ordinary_files(repo):
    dest = repo / "exports" / "guide.json"
    export_guide(repo, _SCOPE, dest)

    assert is_exported_guide(dest) is True
    assert is_exported_guide(repo / "requirements" / "SR-001.md") is False


def test_exported_guide_cited_as_a_bundle_spec_member_is_refused_and_degrades_the_bundle(repo):
    dest = repo / "exports" / "guide.json"
    export_guide(repo, _SCOPE, dest)

    bundles_dir = repo / "bundles"
    bundles_dir.mkdir(parents=True, exist_ok=True)
    (bundles_dir / "b1.json").write_text(
        json.dumps({"id": "b1", "label": "Bundle citing an export", "members": ["spec:exports/guide.json"]}),
        encoding="utf-8",
    )

    result = query_brief(repo, SystemScopeRef(kind="bundle", ref="bundle:b1"))

    assert result["degraded"] is True
    missing = [c for c in result["claims"] if c["kind"] == "missing"]
    assert any(c["text"] == "spec:exports/guide.json" for c in missing)
    reason = next(c for c in missing if c["text"] == "spec:exports/guide.json")
    assert "exported guide" in reason["freshness"]["reason"]
    # And never carries a citation to the exported file -- refused, not
    # silently admitted with a citation attached.
    assert reason["citations"] == []


def test_exported_guide_renamed_into_bundles_directory_does_not_resolve_as_a_scope(repo):
    dest = repo / "exports" / "guide.json"
    export_guide(repo, _SCOPE, dest)
    exported_content = dest.read_text(encoding="utf-8")

    bundles_dir = repo / "bundles"
    bundles_dir.mkdir(parents=True, exist_ok=True)
    (bundles_dir / "masquerade.json").write_text(exported_content, encoding="utf-8")

    # The exported document's shape (artifact/warning/generated_at/guide/
    # citations) fails system_bundle.schema.json's required id/label/members
    # + additionalProperties:false -- a scope ref can never resolve into it.
    with pytest.raises(ValueError):
        query_brief(repo, SystemScopeRef(kind="bundle", ref="bundle:masquerade"))


def test_exported_guide_renamed_into_requirements_directory_does_not_resolve_as_a_scope(tmp_path):
    # A dedicated, isolated repo: factory.requirements.register.load_register
    # parses every SR-*.md file in the directory eagerly, so a malformed file
    # here must not share a directory with an unrelated, valid SR file.
    dest = tmp_path / "exports" / "guide.json"
    _write_sr_repo(tmp_path)
    export_guide(tmp_path, _SCOPE, dest)
    exported_content = dest.read_text(encoding="utf-8")

    (tmp_path / "requirements" / "SR-999.md").write_text(exported_content, encoding="utf-8")

    with pytest.raises(ValueError):
        query_brief(tmp_path, SystemScopeRef(kind="sr", ref="sr:SR-999"))


def test_exported_guide_is_never_accepted_as_a_task_member_either(repo):
    # Belt-and-suspenders: task: members resolve through the ledger, which
    # can never match an exported guide's shape, so citing one that way is
    # refused by construction here -- "exports/guide.json" is not a task id
    # the ledger could ever look up, so `ledger.get_task` returns `None`
    # without ever attempting to read/parse the exported file at all. See
    # `test_exported_guide_placed_as_a_real_sr_file_is_refused_when_cited_
    # as_a_bundle_member` below for the companion case that genuinely
    # attempts interpretation instead (review round 1, finding: this test
    # alone was judged insufficient because it never actually reads the
    # exported file's content).
    dest = repo / "exports" / "guide.json"
    export_guide(repo, _SCOPE, dest)

    bundles_dir = repo / "bundles"
    bundles_dir.mkdir(parents=True, exist_ok=True)
    (bundles_dir / "b2.json").write_text(
        json.dumps({"id": "b2", "label": "Bundle", "members": ["task:exports/guide.json"]}),
        encoding="utf-8",
    )

    result = query_brief(repo, SystemScopeRef(kind="bundle", ref="bundle:b2"))
    assert result["degraded"] is True
    missing = [c for c in result["claims"] if c["kind"] == "missing"]
    assert any(c["text"] == "task:exports/guide.json" for c in missing)


def test_exported_guide_placed_as_a_real_sr_file_is_refused_when_cited_as_a_bundle_member(repo):
    # The genuine-interpretation companion to the task: case above (review
    # round 1 finding): `sr:` members resolve by requirement id, not by
    # path, so the only way to actually exercise "an exported guide sits
    # where a real SR file would" is to place its raw content at the exact
    # path `sr:SR-999` resolves to (requirements/SR-999.md) and let
    # `factory.requirements.register` genuinely attempt to parse it as a
    # requirement. It fails -- the exported document has no YAML
    # frontmatter and none of the required id/title/statement/domain
    # fields -- so the bundle load itself raises rather than silently
    # admitting SR-999 as a readmitted "requirement". This is a harder
    # failure mode than the graceful `missing` a genuinely nonexistent SR id
    # gets (design SS8), but it is still a refusal: the exported guide is
    # never accepted as a citable requirement, under any bundle member kind.
    dest = repo / "exports" / "guide.json"
    export_guide(repo, _SCOPE, dest)
    exported_content = dest.read_text(encoding="utf-8")

    (repo / "requirements" / "SR-999.md").write_text(exported_content, encoding="utf-8")

    bundles_dir = repo / "bundles"
    bundles_dir.mkdir(parents=True, exist_ok=True)
    (bundles_dir / "b3.json").write_text(
        json.dumps({"id": "b3", "label": "Bundle", "members": ["sr:SR-999"]}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        query_brief(repo, SystemScopeRef(kind="bundle", ref="bundle:b3"))
