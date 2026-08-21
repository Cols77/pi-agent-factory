# tests/unit/coverage/test_audit.py
from __future__ import annotations

import json
from pathlib import Path

import pytest

from factory.coverage.audit import (
    SrState,
    classify,
    validate_verdict,
)
from factory.coverage.cli import cmd_audit
from tests.unit.coverage.test_scope import (
    _feat_file,
    _manifest,
    _req_file,
    _task_file,
    _write_historical_record,
)

pytestmark = pytest.mark.unit


def _sr(**kw: object) -> dict:
    return {
        "sr_id": "SR-001",
        "statement": "shall do X",
        "binding": {"experiment": "tests/test_x.py", "metric": "unit_pass_rate", "assert_expr": "== 1.0", "trials": 1},
        "checksum_state": "current",
        "tasks": ({"task_id": "T-001", "changed_files": ("src/x.py",)},),
        "measurement": {"passed": True, "value": 1.0},
        "deferred": False,
        "domain": "behavioral",
        **kw,
    }


def _overlap(ok: bool = True) -> dict:
    return {
        "ok": ok,
        "test_source": "tests/test_x.py",
        "reached_files": ("src/x.py",),
        "changed_files": ("src/x.py",),
        "overlap": ("src/x.py",),
        "unresolved": (),
    }


def _done_task(root: Path, task_id: str, sr_id: str) -> None:
    task_path = _task_file(root, task_id, [sr_id])
    task_path.write_text(
        task_path.read_text(encoding="utf-8").replace(
            "satisfies:", "status: done\nsatisfies:"
        ),
        encoding="utf-8",
    )


def _verdict(ok: bool = True) -> dict:
    return {
        "sr_id": "SR-001",
        "implemented": ok,
        "honest": ok,
        "confidence": "high",
        "margin": None,
        "reasoning": "Test exercises the preempt path.",
        "checked": ["preempt path in priority_filter.py"],
        "assumed": ["fixture represents the sim scenario"],
        "verify": [],
    }


def test_cmd_audit_reports_missing_evidence_for_done_navigator_tasks(tmp_path: Path) -> None:
    _feat_file(tmp_path, "FEAT-NAV-017", ["SR-NAV-001"])
    _req_file(tmp_path, "SR-NAV-001")
    _done_task(tmp_path, "T-058", "SR-NAV-001")
    _done_task(tmp_path, "T-067", "SR-NAV-001")

    result = cmd_audit(tmp_path, "FEAT-NAV-017", run_id="audit-test")

    assert result["overlaps"]["SR-NAV-001"] == {
        "ok": False,
        "reason": "missing evidence for tasks",
        "missing_task_ids": ["T-058", "T-067"],
    }
    assert result["srs"]["SR-NAV-001"]["tasks"] == [
        {
            "task_id": "T-058",
            "changed_files": [],
            "manifests": [],
            "record_paths": [],
            "evidence_state": "missing",
        },
        {
            "task_id": "T-067",
            "changed_files": [],
            "manifests": [],
            "record_paths": [],
            "evidence_state": "missing",
        },
    ]


def test_cmd_audit_uses_approved_historical_record_for_navigator_overlap(tmp_path: Path) -> None:
    _write_historical_record(tmp_path, "T-058", "src/factory/navigator.py")
    test_path = tmp_path / "tests" / "test_SR-001.py"
    test_path.parent.mkdir()
    test_path.write_text(
        "from factory.navigator import navigate\n\n\ndef test_navigate() -> None:\n    assert navigate()\n",
        encoding="utf-8",
    )

    result = cmd_audit(tmp_path, "FEAT-001", run_id="audit-test")

    overlap = result["overlaps"]["SR-001"]
    assert overlap["ok"] is True
    assert overlap["overlap"] == ("src/factory/navigator.py",)
    assert overlap.get("reason") != "no changed files from tasks"


def test_cmd_audit_reports_recorded_empty_evidence_for_done_task(tmp_path: Path) -> None:
    _feat_file(tmp_path, "FEAT-NAV-017", ["SR-NAV-001"])
    _req_file(tmp_path, "SR-NAV-001")
    _done_task(tmp_path, "T-058", "SR-NAV-001")
    manifest_path = tmp_path / "evidence" / "runs" / "RUN-001.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(
        json.dumps(_manifest(task_id="T-058", changed_files=[])),
        encoding="utf-8",
    )

    result = cmd_audit(tmp_path, "FEAT-NAV-017", run_id="audit-test")

    assert result["overlaps"]["SR-NAV-001"] == {
        "ok": False,
        "reason": "recorded evidence has no changed files",
        "empty_task_ids": ["T-058"],
    }


def test_validate_verdict_ok() -> None:
    v = _verdict()
    result, error = validate_verdict(v)
    assert result is not None
    assert error is None


def test_validate_verdict_missing_reasoning() -> None:
    v = _verdict()
    v.pop("reasoning")
    result, error = validate_verdict(v)
    assert result is None
    assert error is not None
    assert "reasoning" in error


def test_validate_verdict_missing_checked() -> None:
    v = _verdict()
    v.pop("checked")
    result, error = validate_verdict(v)
    assert result is None
    assert error is not None
    assert "checked" in error


def test_validate_verdict_missing_assumed() -> None:
    v = _verdict()
    v.pop("assumed")
    result, error = validate_verdict(v)
    assert result is None
    assert error is not None
    assert "assumed" in error


def test_validate_verify_item_requires_item() -> None:
    v = _verdict()
    v["verify"] = [{"file": "src/x.py", "why": "tight margin"}]
    result, error = validate_verdict(v)
    assert result is None
    assert error is not None
    assert "verify" in error


def test_validate_verify_item_full() -> None:
    v = _verdict()
    v["verify"] = [{"item": "Check margin", "file": "src/x.py", "line": 42, "why": "tight"}]
    result, error = validate_verdict(v)
    assert result is not None


def test_classify_declined() -> None:
    sr = _sr(deferred=True)
    state, notes = classify(sr, None, None, False)
    assert state == SrState.DECLINED


def test_classify_unlinked() -> None:
    sr = _sr(tasks=())
    state, notes = classify(sr, None, None, False)
    assert state == SrState.UNLINKED


def test_classify_unverified() -> None:
    sr = _sr()
    state, notes = classify(sr, None, None, False)
    assert state == SrState.UNVERIFIED


def test_classify_not_implemented() -> None:
    sr = _sr()
    v = _verdict(ok=False)
    state, notes = classify(sr, _overlap(), v, False)
    assert state == SrState.NOT_IMPLEMENTED


def test_classify_dishonest() -> None:
    sr = _sr()
    v = _verdict(ok=True)
    v["honest"] = False
    state, notes = classify(sr, _overlap(), v, False)
    assert state == SrState.DISHONEST


def test_classify_pass() -> None:
    sr = _sr()
    v = _verdict()
    state, notes = classify(sr, _overlap(), v, False)
    assert state == SrState.PASS


def test_classify_unmeasured() -> None:
    sr = _sr(measurement=None)
    v = _verdict()
    state, notes = classify(sr, _overlap(), v, False)
    assert state == SrState.UNMEASURED


def test_classify_suspect_overlap() -> None:
    sr = _sr()
    v = _verdict()
    o = _overlap(ok=False)
    state, notes = classify(sr, o, v, False)
    assert state == SrState.SUSPECT
