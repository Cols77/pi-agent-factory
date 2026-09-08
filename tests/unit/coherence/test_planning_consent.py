from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import cast

import pytest

from coherence.planning.consent import (
    CONSENT_PHRASE,
    validate_sr_decisions,
    write_sr_decision,
)
from coherence.planning.cli import main
from coherence.planning.gates import validate_sr_consent

pytestmark = pytest.mark.unit


def _current(**hashes: str) -> dict[str, str]:
    return hashes


def _write_approval(root: Path, run_id: str, sr_id: str, digest: str) -> Path:
    return write_sr_decision(
        root,
        run_id,
        sr_id,
        digest,
        "approve",
        "human",
        CONSENT_PHRASE,
        "I reviewed this requirement independently.",
    )


def test_each_candidate_requires_its_own_human_hash_bound_decision(tmp_path: Path) -> None:
    current = _current(**{"SR-071": "1" * 64, "SR-072": "2" * 64})
    _write_approval(tmp_path, "run-17", "SR-071", current["SR-071"])

    assert validate_sr_decisions(tmp_path, "run-17", current) == (
        False,
        "missing human consent: SR-072",
    )

    _write_approval(tmp_path, "run-17", "SR-072", current["SR-072"])
    assert validate_sr_decisions(tmp_path, "run-17", current) == (
        True,
        "human consent is current for all candidate SRs",
    )


def test_changed_requirement_hash_stales_only_the_matching_sr(tmp_path: Path) -> None:
    current = _current(**{"SR-071": "1" * 64, "SR-072": "2" * 64})
    for sr_id, digest in current.items():
        _write_approval(tmp_path, "run-17", sr_id, digest)

    revised = _current(**{"SR-071": "3" * 64, "SR-072": "2" * 64})
    assert validate_sr_decisions(tmp_path, "run-17", revised) == (
        False,
        "stale human consent: SR-071",
    )
    assert validate_sr_decisions(tmp_path, "run-17", {"SR-072": revised["SR-072"]}) == (
        True,
        "human consent is current for all candidate SRs",
    )


@pytest.mark.parametrize(
    ("mutation", "detail"),
    [
        ({"reviewer": "agent"}, "invalid human consent: SR-071"),
        ({"decision": "warning"}, "invalid human consent: SR-071"),
        ({"phrase": "I approve"}, "invalid human consent: SR-071"),
        ({"reason": "   "}, "invalid human consent: SR-071"),
        ({"reviewer": "human", "bulk": ["SR-071", "SR-072"]}, "invalid human consent: SR-071"),
    ],
)
def test_rejects_invalid_provenance_phrase_and_bulk_or_malformed_records(
    tmp_path: Path,
    mutation: dict[str, object],
    detail: str,
) -> None:
    digest = "1" * 64
    path = _write_approval(tmp_path, "run-17", "SR-071", digest)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.update(mutation)
    path.write_text(json.dumps(payload), encoding="utf-8")

    assert validate_sr_decisions(tmp_path, "run-17", {"SR-071": digest}) == (False, detail)


def test_rejects_malformed_json_and_does_not_accept_a_bulk_record(tmp_path: Path) -> None:
    consent_dir = tmp_path / ".factory" / "planning" / "run-17" / "consent"
    consent_dir.mkdir(parents=True)
    (consent_dir / "SR-071.json").write_text('{"schema": 1, "schema": 1}', encoding="utf-8")
    (consent_dir / "bulk.json").write_text("{}", encoding="utf-8")

    assert validate_sr_decisions(tmp_path, "run-17", {"SR-071": "1" * 64}) == (
        False,
        "invalid human consent: SR-071",
    )
    assert validate_sr_decisions(tmp_path, "run-17", {"SR-072": "2" * 64}) == (
        False,
        "missing human consent: SR-072",
    )


@pytest.mark.parametrize(
    ("run_id", "sr_id"),
    [
        ("../run-17", "SR-071"),
        ("run-17", "../SR-071"),
        ("run-17", "SR-071/extra"),
    ],
)
def test_safe_path_guards_reject_unsafe_decision_identity(
    tmp_path: Path, run_id: str, sr_id: str
) -> None:
    with pytest.raises(ValueError, match="invalid (?:planning run id|SR identifier)"):
        _write_approval(tmp_path, run_id, sr_id, "1" * 64)

    assert not (tmp_path / ".factory").exists()


def test_validation_is_read_only_when_a_decision_is_missing(tmp_path: Path) -> None:
    before = sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*"))

    assert validate_sr_decisions(tmp_path, "run-17", {"SR-071": "1" * 64}) == (
        False,
        "missing human consent: SR-071",
    )

    after = sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*"))
    assert after == before


def test_validation_rejects_mixed_type_candidate_identifiers_without_raising(
    tmp_path: Path,
) -> None:
    current = cast(Mapping[str, str], {"SR-071": "1" * 64, 1: "2" * 64})

    assert validate_sr_decisions(tmp_path, "run-17", current) == (
        False,
        "candidate SR set is invalid",
    )


def test_legacy_aggregate_consent_contract_remains_available(tmp_path: Path) -> None:
    path = tmp_path / ".factory" / "planning" / "run-17" / "sr-consent.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "schema": 2,
                "run_id": "run-17",
                "decision": "approve",
                "reviewer": "human",
                "phrase": "I explicitly consent to adopt exactly these candidate SRs.",
                "candidate_srs": ["SR-071"],
                "derivation_report_sha256": "0" * 64,
                "artifact_hashes": {},
            }
        ),
        encoding="utf-8",
    )

    assert validate_sr_consent(tmp_path, "run-17", ["SR-071"], "0" * 64, {}) == (
        True,
        "explicit SR consent is current and exact",
    )


def test_cli_records_exactly_one_sr_consent_with_all_human_fields(tmp_path: Path) -> None:
    assert main(
        [
            "record-sr-consent",
            "--project-root",
            str(tmp_path),
            "--run-id",
            "run-17",
            "--sr-id",
            "SR-071",
            "--requirement-sha256",
            "1" * 64,
            "--decision",
            "approve",
            "--reviewer",
            "human",
            "--phrase",
            CONSENT_PHRASE,
            "--reason",
            "I reviewed the final wording independently.",
        ]
    ) == 0

    consent_dir = tmp_path / ".factory" / "planning" / "run-17" / "consent"
    assert sorted(path.name for path in consent_dir.iterdir()) == ["SR-071.json"]
