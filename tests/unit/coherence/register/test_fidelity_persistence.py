from __future__ import annotations

import json
from pathlib import Path

import pytest

from coherence.gate.content import artifact_content_checksum
from coherence.gate.model import Decision, DecisionFile
from coherence.gate.store import write_decision
from coherence.register.fidelity_findings import FidelityFinding, FidelityReviewResult, RelationRef
from coherence.register.fidelity_persistence import (
    fidelity_findings_path,
    is_fidelity_current,
    load_fidelity_result,
    save_fidelity_result,
)

pytestmark = pytest.mark.unit

# SR-050/AC-4 (T5.4): persistence + re-run disposition tracking.


def _finding(*, status: str = "open", produced_at: str = "2026-09-01T00:00:00Z") -> FidelityFinding:
    return FidelityFinding(
        sr_id="SR-900",
        kind="overstated_link",
        relation=RelationRef(field="implemented_by", path="src/a.py", identity="a:f"),
        confidence=0.7,
        citations=("src/a.py#a:f",),
        rationale="r",
        acceptance_ref=None,
        status=status,
        produced_at=produced_at,
        produced_by_run="run-1",
    )


def _result(*, findings=(), status: str = "ok", packet_fingerprint: str | None = None) -> FidelityReviewResult:
    return FidelityReviewResult(
        sr_id="SR-900",
        profile="high_assurance",
        findings=findings,
        unresolved=(),
        run_id="run-1",
        produced_at="2026-09-01T00:00:00Z",
        status=status,
        packet_fingerprint=packet_fingerprint,
    )


def _seed_requirement(root: Path, sr_id: str) -> None:
    """A minimal real requirement file at the canonical path -- required so
    `_accepted_review_decision_at`'s artifact_ref scoping check (mirroring
    `_human_review_obligation`'s own) has a real SR to resolve the expected
    `artifact:` ref against."""
    path = root / "requirements" / f"{sr_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\nid: {sr_id}\ntitle: t\nstatement: s\ndomain: behavioral\n---\nbody\n",
        encoding="utf-8",
    )


def _write_accept_decision(
    root: Path,
    sr_id: str,
    decided_at: str,
    *,
    artifact_ref: str | None = None,
    content_checksum: str = "",
) -> None:
    write_decision(
        root,
        DecisionFile(
            gate_id=f"review:{sr_id}",
            artifact_ref=artifact_ref or f"artifact:requirements/{sr_id}.md",
            decisions=(Decision(f"review:{sr_id}", "accept", decided_by="reviewer@example.invalid"),),
            decided_at=decided_at,
            decided_by="reviewer@example.invalid",
            content_checksum=content_checksum,
        ),
    )


@pytest.mark.sr("SR-050")
def test_first_write_creates_the_file(tmp_path: Path):
    result = _result(findings=(_finding(),))
    path = save_fidelity_result(tmp_path, result)
    assert path == fidelity_findings_path(tmp_path, "SR-900")
    assert path.is_file()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["sr_id"] == "SR-900"
    assert len(data["findings"]) == 1


@pytest.mark.sr("SR-050")
def test_a_second_run_with_identical_findings_overwrites_idempotently(tmp_path: Path):
    result = _result(findings=(_finding(),))
    save_fidelity_result(tmp_path, result)
    save_fidelity_result(tmp_path, result)
    path = fidelity_findings_path(tmp_path, "SR-900")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert len(data["findings"]) == 1


@pytest.mark.sr("SR-050")
def test_a_finding_accepted_past_by_a_later_review_decision_is_written_back_dispositioned(tmp_path: Path):
    _seed_requirement(tmp_path, "SR-900")
    prior = _result(findings=(_finding(status="open", produced_at="2026-09-01T00:00:00Z"),))
    save_fidelity_result(tmp_path, prior)
    _write_accept_decision(tmp_path, "SR-900", decided_at="2026-09-02T00:00:00Z")

    rerun = _result(findings=(_finding(status="open", produced_at="2026-09-03T00:00:00Z"),))
    save_fidelity_result(tmp_path, rerun)

    loaded = load_fidelity_result(tmp_path, "SR-900")
    assert loaded is not None
    assert loaded.findings[0].status == "dispositioned"


@pytest.mark.sr("SR-050")
def test_a_decision_whose_artifact_ref_does_not_match_the_srs_own_path_does_not_disposition(
    tmp_path: Path,
):
    """Mirrors `_human_review_obligation`'s own `artifact_ref` scoping check
    (`src/coherence/policy/compiler.py`) -- a `review:<sr_id>` decision that
    is correctly gate_id/item_id-scoped but names a stale, wrong, or
    manually-edited `artifact_ref` (e.g. left over from before the SR's
    requirement file moved) must NOT disposition a stored finding. If it
    did, the finding would silently drop out of `cmd_review_check`'s CI
    -blocking list even though AC-3's own gate would still correctly treat
    the SR as unreviewed."""
    _seed_requirement(tmp_path, "SR-900")
    prior = _result(findings=(_finding(status="open", produced_at="2026-09-01T00:00:00Z"),))
    save_fidelity_result(tmp_path, prior)
    # Correctly scoped gate_id/item_id, but a WRONG artifact_ref -- points at
    # a different SR's requirement file entirely.
    _write_accept_decision(
        tmp_path,
        "SR-900",
        decided_at="2026-09-02T00:00:00Z",
        artifact_ref="artifact:requirements/SR-901.md",
    )

    rerun = _result(findings=(_finding(status="open", produced_at="2026-09-03T00:00:00Z"),))
    save_fidelity_result(tmp_path, rerun)

    loaded = load_fidelity_result(tmp_path, "SR-900")
    assert loaded is not None
    assert loaded.findings[0].status == "open"


@pytest.mark.sr("SR-050")
def test_a_finding_with_no_matching_prior_disposition_stays_open_every_rerun(tmp_path: Path):
    rerun = _result(findings=(_finding(status="open"),))
    save_fidelity_result(tmp_path, rerun)
    loaded = load_fidelity_result(tmp_path, "SR-900")
    assert loaded is not None
    assert loaded.findings[0].status == "open"


@pytest.mark.sr("SR-050")
def test_an_accept_decision_that_predates_the_prior_finding_does_not_disposition_it(tmp_path: Path):
    # decision decided BEFORE the prior finding was produced -- the human
    # never saw this exact finding, so it must not be silently dispositioned.
    _seed_requirement(tmp_path, "SR-900")
    _write_accept_decision(tmp_path, "SR-900", decided_at="2026-08-01T00:00:00Z")
    prior = _result(findings=(_finding(status="open", produced_at="2026-09-01T00:00:00Z"),))
    save_fidelity_result(tmp_path, prior)

    rerun = _result(findings=(_finding(status="open", produced_at="2026-09-05T00:00:00Z"),))
    save_fidelity_result(tmp_path, rerun)

    loaded = load_fidelity_result(tmp_path, "SR-900")
    assert loaded is not None
    assert loaded.findings[0].status == "open"


@pytest.mark.sr("SR-050")
def test_loading_a_missing_file_returns_none(tmp_path: Path):
    assert load_fidelity_result(tmp_path, "SR-999") is None


@pytest.mark.sr("SR-050")
def test_a_decision_whose_content_checksum_no_longer_covers_the_sr_does_not_disposition(
    tmp_path: Path,
):
    """SR-059/AC-2 applies here exactly as it does to
    `_human_review_obligation`: a recorded accept stops covering its target
    the moment the target's content changes. A finding dispositioned by
    consent a human gave for DIFFERENT content would silently drop out of
    `cmd_review_check`'s CI-blocking list, which is the same fail-open the
    `artifact_ref` scoping test above guards against."""
    _seed_requirement(tmp_path, "SR-900")
    prior = _result(findings=(_finding(status="open", produced_at="2026-09-01T00:00:00Z"),))
    save_fidelity_result(tmp_path, prior)

    sr_path = tmp_path / "requirements" / "SR-900.md"
    _write_accept_decision(
        tmp_path,
        "SR-900",
        decided_at="2026-09-02T00:00:00Z",
        content_checksum=artifact_content_checksum(sr_path),
    )
    # The human consented to the content above; it has since changed.
    sr_path.write_text(
        "---\nid: SR-900\ntitle: t\nstatement: MATERIALLY DIFFERENT\ndomain: behavioral\n---\nbody\n",
        encoding="utf-8",
    )

    rerun = _result(findings=(_finding(status="open", produced_at="2026-09-03T00:00:00Z"),))
    save_fidelity_result(tmp_path, rerun)

    loaded = load_fidelity_result(tmp_path, "SR-900")
    assert loaded is not None
    assert loaded.findings[0].status == "open"


# is_fidelity_current -- stale-fidelity-review remediation (HANDOFF.md Next
# Step 3 / audit finding 3.8): the dispatch-path short-circuit's decision
# matrix, tested directly (pure function, no filesystem/CLI needed).


@pytest.mark.sr("SR-050")
def test_no_prior_result_is_never_current():
    assert is_fidelity_current(None, "sha256:abc") is False


@pytest.mark.sr("SR-050")
def test_matching_fingerprint_on_an_ok_result_is_current():
    prior = _result(status="ok", packet_fingerprint="sha256:abc")
    assert is_fidelity_current(prior, "sha256:abc") is True


@pytest.mark.sr("SR-050")
def test_a_different_fingerprint_on_an_ok_result_is_not_current():
    prior = _result(status="ok", packet_fingerprint="sha256:abc")
    assert is_fidelity_current(prior, "sha256:changed") is False


@pytest.mark.sr("SR-050")
def test_a_null_legacy_fingerprint_is_stale_once():
    prior = _result(status="ok", packet_fingerprint=None)
    assert is_fidelity_current(prior, "sha256:abc") is False


@pytest.mark.sr("SR-050")
def test_a_stored_unavailable_result_is_never_current_even_with_a_matching_fingerprint():
    prior = _result(status="unavailable", packet_fingerprint="sha256:abc")
    assert is_fidelity_current(prior, "sha256:abc") is False
