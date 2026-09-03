from __future__ import annotations

import json
from pathlib import Path

import frontmatter as fm
import pytest

from coherence.register.cli import cmd_review, cmd_review_check, main

pytestmark = pytest.mark.unit

# SR-050/AC-4 (T5.5): `coherence register review ... --fidelity` and
# `--check`, extending T4's existing `structural`/`evidence_reconciliation`
# CLI surface with a third, distinct `fidelity` key.


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _write_meta(path: Path, meta: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(fm.dumps(fm.Post("body", **meta)), encoding="utf-8")
    return path


def _write_prod(root: Path) -> None:
    _write(
        root / "src" / "widgets" / "feature.py",
        "def feature_context():\n    return 1\n",
    )


def _seed_sr(root: Path, sr_id: str, *, profile: str | None = None) -> None:
    _write_prod(root)
    meta = {
        "id": sr_id,
        "title": "t",
        "statement": "s",
        "domain": "behavioral",
        "implemented_by": [
            {"path": "src/widgets/feature.py", "symbol": "widgets.feature:feature_context"}
        ],
    }
    _write_meta(root / "requirements" / f"{sr_id}.md", meta)
    if profile == "high_assurance":
        _write(
            root / "docs" / "features" / "FEAT-900.md",
            f"---\nid: FEAT-900\ntitle: f\nprofile: high_assurance\nrequirements: [{sr_id}]\n---\n",
        )


_CANDIDATE = {
    "kind": "overstated_link",
    "relation": {"field": "implemented_by", "path": "src/widgets/feature.py", "identity": "widgets.feature:feature_context"},
    "confidence": 0.7,
    "citations": ["src/widgets/feature.py#widgets.feature:feature_context"],
    "rationale": "r",
    "acceptance_ref": None,
}


@pytest.mark.sr("SR-050")
def test_fidelity_prints_a_distinct_key_alongside_structural_and_reconciliation(tmp_path: Path):
    _seed_sr(tmp_path, "SR-901")
    result = json.loads(cmd_review(tmp_path, "SR-901", fidelity=True, judge=lambda p: []))
    assert set(result.keys()) == {"structural", "evidence_reconciliation", "fidelity"}
    assert "SR-901" in result["fidelity"]
    assert result["fidelity"]["SR-901"]["status"] == "ok"
    assert result["fidelity"]["SR-901"]["findings"] == []


@pytest.mark.sr("SR-050")
def test_without_fidelity_flag_no_fidelity_key_is_present(tmp_path: Path):
    _seed_sr(tmp_path, "SR-902")
    result = json.loads(cmd_review(tmp_path, "SR-902"))
    assert "fidelity" not in result


@pytest.mark.sr("SR-050")
def test_check_exits_zero_for_an_all_escalated_non_high_assurance_fixture(tmp_path: Path):
    _seed_sr(tmp_path, "SR-903")  # no owning high_assurance feature -> profile "prototype"
    text, code = cmd_review_check(tmp_path, "SR-903", judge=lambda p: [dict(_CANDIDATE)])
    assert code == 0
    payload = json.loads(text)
    assert payload["fidelity"]["SR-903"]["findings"][0]["status"] == "escalated"
    assert payload["blocking"] == []


@pytest.mark.sr("SR-050")
def test_check_exits_non_zero_for_an_open_high_assurance_finding(tmp_path: Path):
    _seed_sr(tmp_path, "SR-904", profile="high_assurance")
    text, code = cmd_review_check(tmp_path, "SR-904", judge=lambda p: [dict(_CANDIDATE)])
    assert code != 0
    payload = json.loads(text)
    assert payload["fidelity"]["SR-904"]["findings"][0]["status"] == "open"
    assert len(payload["blocking"]) == 1
    assert payload["blocking"][0]["sr_id"] == "SR-904"


@pytest.mark.sr("SR-050")
def test_check_exits_zero_when_the_high_assurance_finding_is_already_dispositioned(tmp_path: Path):
    from coherence.gate.model import Decision, DecisionFile
    from coherence.gate.store import write_decision

    _seed_sr(tmp_path, "SR-905", profile="high_assurance")
    # First run records the finding.
    cmd_review_check(tmp_path, "SR-905", judge=lambda p: [dict(_CANDIDATE)])
    # A human accepts the review after that.
    write_decision(
        tmp_path,
        DecisionFile(
            gate_id="review:SR-905",
            artifact_ref="artifact:requirements/SR-905.md",
            decisions=(Decision("review:SR-905", "accept", decided_by="reviewer@example.invalid"),),
            decided_at="2099-01-01T00:00:00Z",
            decided_by="reviewer@example.invalid",
        ),
    )
    text, code = cmd_review_check(tmp_path, "SR-905", judge=lambda p: [dict(_CANDIDATE)])
    payload = json.loads(text)
    assert payload["fidelity"]["SR-905"]["findings"][0]["status"] == "dispositioned"
    assert code == 0


@pytest.mark.sr("SR-050")
def test_a_judge_that_fails_degrades_to_unavailable_and_blocks_a_high_assurance_check(tmp_path: Path):
    """A judge outage on a `high_assurance` SR must fail closed -- absence of
    a verdict is never read as "reviewed, found nothing". The command still
    never crashes and still records the SR's own status/error for visibility;
    it just also joins `blocking` and pushes the exit code non-zero, exactly
    like an actual open finding would."""
    _seed_sr(tmp_path, "SR-906", profile="high_assurance")

    def _broken_judge(packet):
        raise RuntimeError("no live dispatch context")

    text, code = cmd_review_check(tmp_path, "SR-906", judge=_broken_judge)
    payload = json.loads(text)
    assert payload["fidelity"]["SR-906"]["status"] == "unavailable"
    assert code != 0
    assert len(payload["blocking"]) == 1
    assert payload["blocking"][0]["sr_id"] == "SR-906"
    assert payload["blocking"][0]["kind"] == "fidelity_unavailable"


@pytest.mark.sr("SR-050")
def test_a_judge_that_fails_does_not_block_a_non_high_assurance_check(tmp_path: Path):
    _seed_sr(tmp_path, "SR-908")  # no owning high_assurance feature -> profile "prototype"

    def _broken_judge(packet):
        raise RuntimeError("no live dispatch context")

    text, code = cmd_review_check(tmp_path, "SR-908", judge=_broken_judge)
    payload = json.loads(text)
    assert payload["fidelity"]["SR-908"]["status"] == "unavailable"
    assert code == 0
    assert payload["blocking"] == []


@pytest.mark.sr("SR-050")
def test_check_blocks_when_the_packet_itself_fails_to_build_for_a_high_assurance_sr(
    tmp_path: Path, monkeypatch
):
    """A packet-build failure (frontmatter error, missing register entry,
    etc) must not masquerade as a non-`high_assurance` SR just because the
    packet -- and with it, the packet's own resolved `profile` -- never got
    built: the CI gate independently resolves the SR's real configured
    profile so a `high_assurance` SR that cannot even be packaged still
    blocks, exactly like an unavailable judge does."""
    import coherence.register.cli as cli_module

    _seed_sr(tmp_path, "SR-907", profile="high_assurance")

    def _broken_packet_build(root, sr_id):
        raise ValueError("frontmatter parse error")

    monkeypatch.setattr(cli_module, "build_fidelity_packet", _broken_packet_build)
    text, code = cmd_review_check(tmp_path, "SR-907", judge=lambda p: [])
    payload = json.loads(text)
    assert payload["fidelity"]["SR-907"]["profile"] == "high_assurance"
    assert payload["fidelity"]["SR-907"]["status"] == "unavailable"
    assert code != 0
    assert len(payload["blocking"]) == 1
    assert payload["blocking"][0]["sr_id"] == "SR-907"


@pytest.mark.sr("SR-050")
def test_check_scopes_to_the_whole_register_with_neither_an_id_nor_all(tmp_path: Path, monkeypatch):
    # .factory/factory.yaml's gate entry is exactly
    # `{python} -m coherence register review --fidelity --check` -- no id,
    # no --all. `--check` must not require either; it always scopes to
    # every SR in scope on its own. cmd_review_check itself is stubbed so
    # this test only exercises argument parsing/dispatch, never the real
    # default judge.
    import coherence.register.cli as cli_module

    captured: dict = {}

    def _fake_check(project_root, req_id, *, judge=None):
        captured["project_root"] = project_root
        captured["req_id"] = req_id
        return "{}", 0

    monkeypatch.setattr(cli_module, "cmd_review_check", _fake_check)
    code = main(["review", "--fidelity", "--check", "--project-root", str(tmp_path)])
    assert code == 0
    assert captured["req_id"] is None
    assert captured["project_root"] == tmp_path
