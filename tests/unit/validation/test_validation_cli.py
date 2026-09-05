import json

import pytest
from factory.requirements.register import content_checksum, parse_requirement
from factory.validation.cli import cmd_validate, main

pytestmark = pytest.mark.unit

_SR = """---
id: SR-001
title: t
statement: "When a shark is detected in a swim zone, nav shall preempt patrol."
domain: behavioral
upstream: []
binding:
  harness: sim-testbench
  experiment: shark_warning
  metric: preemption_success_rate
  trials: 2
  assert: ">= 0.90"
  window: {{after_event: shark_detected, within_s: 5}}
checksum: {ck}
---
body
"""


# Without a registered scorer SR-001 never reaches a "passed" result -- it
# errors on "no trial scorer for metric ...", so this file's tests asserted a
# successful write over a report containing only an error entry.
# tests/unit/validation/test_pipeline.py already carries this same fixture for
# exactly this reason; test_validation_cli.py was left behind.
_SCORER_MODULE = '''
def _preempted(frames, window):
    return any(f["active_directive"]["kind"] != "patrol" for f in frames)


SCORERS = {"preemption_success_rate": _preempted}
'''


def _write_scorers(tmp_path) -> str:
    # Package name derived from tmp_path: importlib caches in sys.modules, so a
    # shared name would let one test read another's module.
    module = f"scorerpkg_cli_{tmp_path.name}".replace("-", "_")
    pkg = tmp_path / "src" / module
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "scorers.py").write_text(_SCORER_MODULE, encoding="utf-8")
    return module


def _f(t, kind, sharks=()):
    return {
        "mission_clock": t,
        "active_directive": {"kind": kind},
        "detections": [{"label": "shark", "confidence": c} for c in sharks],
    }


GOOD = [_f(0, "patrol"), _f(15, "patrol", (0.45,)), _f(17, "override"), _f(40, "patrol")]


def _project(tmp_path):
    req = tmp_path / "requirements"
    req.mkdir()
    stub = req / "SR-001.md"
    stub.write_text(_SR.format(ck="null"), encoding="utf-8")
    ck = content_checksum(parse_requirement(stub))
    stub.write_text(_SR.format(ck=ck), encoding="utf-8")
    module = _write_scorers(tmp_path)
    (tmp_path / ".factory").mkdir()
    (tmp_path / ".factory" / "factory.yaml").write_text(
        "harnesses:\n  sim-testbench:\n    type: sim-testbench\n"
        f"    traces_dir: traces\n    scorers: {module}.scorers\n",
        encoding="utf-8",
    )
    traces = tmp_path / "traces"
    traces.mkdir()
    (traces / "shark_warning.json").write_text(
        json.dumps({"trials": [{"seed": 0, "frames": GOOD}, {"seed": 1, "frames": GOOD}]}),
        encoding="utf-8",
    )
    return tmp_path


def test_cmd_validate_all_writes_report(tmp_path):
    _project(tmp_path)
    report, ok = cmd_validate(tmp_path, full_sweep=True)
    assert ok is True
    assert [e["id"] for e in report["requirements"]] == ["SR-001"]
    # Pins what this test silently lost before: a real verdict, not an error.
    assert report["requirements"][0]["passed"] is True
    on_disk = json.loads(
        (tmp_path / "validation" / "validation-report.json").read_text(encoding="utf-8")
    )
    assert on_disk == report


def test_main_returns_exit_code(tmp_path, capsys):
    _project(tmp_path)
    rc = main(["run", "--project-root", str(tmp_path), "--all"])
    assert rc == 0
    assert "SR-001" in capsys.readouterr().out


# --- Write safety: a run that measures nothing must not destroy the report ---

_SR_NO_HARNESS = """---
id: SR-002
title: t
statement: "When a shark is detected in a swim zone, nav shall preempt patrol."
domain: behavioral
upstream: []
binding:
  experiment: shark_warning
  metric: preemption_success_rate
  trials: 2
  assert: ">= 0.90"
checksum: null
---
body
"""

_AGENT_REPORT = {
    "provenance": {
        "recorded_by": "agent",
        "recorded_at": "2026-09-03T02:56:51Z",
        "command": "pytest -m sr",
        "run_id": "SR-004-006-050-evidence-refresh-20260903T025651Z",
        "evidence_manifest": "evidence/runs/x.json",
        "commit": "09376b7",
        "note": "hand-authored provenance note that cannot be recomputed",
    },
    "requirements": [{"id": "SR-050", "passed": True}],
}


def _all_error_project(tmp_path):
    """A project whose only bound requirement names no harness -- the exact
    shape this repo's SR-001..SR-007 have, which makes every entry an error."""
    req = tmp_path / "requirements"
    req.mkdir()
    (req / "SR-002.md").write_text(_SR_NO_HARNESS, encoding="utf-8")
    (tmp_path / ".factory").mkdir()
    (tmp_path / ".factory" / "factory.yaml").write_text("harnesses: {}\n", encoding="utf-8")
    return tmp_path


def _seed(tmp_path, payload):
    path = tmp_path / "validation" / "validation-report.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2)
    path.write_text(text, encoding="utf-8")
    return path, text


def test_a_run_that_measures_nothing_does_not_destroy_the_report(tmp_path):
    """The reported defect: every entry is an error placeholder, yet the
    command overwrites an irreplaceable agent-recorded report and exits 0."""
    _all_error_project(tmp_path)
    path, before = _seed(tmp_path, _AGENT_REPORT)

    report, ok = cmd_validate(tmp_path, full_sweep=True)

    assert all("error" in e for e in report["requirements"])
    assert path.read_text(encoding="utf-8") == before
    assert ok is False


_HAND_REPORT = {
    "provenance": {
        "recorded_by": "hand",
        "recorded_at": "2026-09-03T02:56:51Z",
        "command": "pytest -m sr",
        "run_id": "r",
        "evidence_manifest": "evidence/runs/x.json",
        "commit": "09376b7",
        "note": "transcribed by a human",
    },
    "requirements": [{"id": "SR-050", "passed": True}],
}


@pytest.mark.parametrize("origin,payload", [("agent", _AGENT_REPORT), ("hand", _HAND_REPORT)])
def test_a_real_measurement_refuses_to_supersede_a_report_it_did_not_produce(
    tmp_path, capsys, origin, payload
):
    """A harness run measures for real, but the report already on disk was
    recorded by someone else. This code cannot reproduce what it would
    destroy, so it must not replace it without explicit consent."""
    _project(tmp_path)
    path, before = _seed(tmp_path, payload)

    report, ok = cmd_validate(tmp_path, full_sweep=True)

    assert ok is False
    assert path.read_text(encoding="utf-8") == before
    assert "--replace-recorded" in capsys.readouterr().err
    assert origin in report["write_skipped"]


def test_replace_recorded_supersedes_a_foreign_report_deliberately(tmp_path):
    _project(tmp_path)
    path, _ = _seed(tmp_path, _AGENT_REPORT)

    report, ok = cmd_validate(tmp_path, full_sweep=True, replace_recorded=True)

    assert ok is True
    assert "write_skipped" not in report
    assert json.loads(path.read_text(encoding="utf-8")) == report


def test_a_harness_report_supersedes_its_own_prior_output_without_friction(tmp_path):
    """Harness replacing harness is never the destructive case -- it is
    reproducible by definition, so it needs no flag."""
    _project(tmp_path)
    cmd_validate(tmp_path, full_sweep=True)

    report, ok = cmd_validate(tmp_path, full_sweep=True)

    assert ok is True
    assert "write_skipped" not in report


@pytest.mark.parametrize(
    "text",
    [
        "{not json",
        "[]",
        '{"requirements": []}',
        '{"provenance": "not-an-object", "requirements": []}',
        '{"provenance": {"recorded_by": "wat"}, "requirements": []}',
    ],
    ids=["unparseable", "array", "no-provenance", "provenance-not-object", "origin-off-enum"],
)
def test_a_real_measurement_refuses_when_the_existing_report_cannot_be_attributed(tmp_path, text):
    """Fail closed: something is there, this code cannot show it produced it,
    so it is not this code's to overwrite silently."""
    _project(tmp_path)
    path = tmp_path / "validation" / "validation-report.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")

    _report, ok = cmd_validate(tmp_path, full_sweep=True)

    assert ok is False
    assert path.read_text(encoding="utf-8") == text


def test_main_exits_non_zero_when_it_refuses_to_write(tmp_path):
    """The other half of the defect: it exited 0 while destroying the file."""
    _all_error_project(tmp_path)
    _seed(tmp_path, _AGENT_REPORT)
    assert main(["run", "--project-root", str(tmp_path), "--all"]) == 1


def test_main_threads_the_replace_recorded_flag(tmp_path):
    _project(tmp_path)
    path, before = _seed(tmp_path, _AGENT_REPORT)
    assert main(["run", "--project-root", str(tmp_path), "--all"]) == 1
    assert path.read_text(encoding="utf-8") == before

    rc = main(["run", "--project-root", str(tmp_path), "--all", "--replace-recorded"])
    assert rc == 0
    assert json.loads(path.read_text(encoding="utf-8"))["provenance"]["recorded_by"] == "harness"
