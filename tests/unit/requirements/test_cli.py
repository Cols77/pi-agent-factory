import json

import pytest
from factory.requirements.cli import cmd_bind, cmd_defer, cmd_index, cmd_new, cmd_show, cmd_status, main

pytestmark = pytest.mark.unit

# A requirement whose measurement is already decided. `cmd_new` no longer produces
# one of these -- it mints proposed requirements -- so checksum and staleness
# behaviour is exercised against an explicitly bound fixture.
_BOUND = """---
id: SR-001
title: Bound requirement
statement: "When X happens, the system shall do Y."
domain: behavioral
upstream: []
binding:
  harness: demo-harness
  experiment: demo_experiment
  metric: demo_rate
  trials: 1
  assert: ">= 0.90"
checksum: null
---
Rationale.
"""

_PROPOSED = """---
id: SR-009
title: Proposed requirement
statement: "When the zone clears, the system shall resume patrol."
domain: behavioral
upstream: []
source: docs/superpowers/specs/a.md
---
Rationale.
"""


def _write(tmp_path, name: str, text: str):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_new_allocates_sequential_ids(tmp_path):
    p1 = cmd_new(tmp_path, "First req", "behavioral")
    p2 = cmd_new(tmp_path, "Second req", "perception")
    assert p1.name == "SR-001.md"
    assert p2.name == "SR-002.md"
    assert "First req" in p1.read_text(encoding="utf-8")


def test_new_mints_a_proposed_requirement(tmp_path):
    text = cmd_new(tmp_path, "Zone clear abandons investigate", "behavioral").read_text(
        encoding="utf-8"
    )
    assert "binding:" not in text
    assert "preemption_success_rate" not in text
    assert "sim-testbench" not in text


def test_index_stamps_checksums_and_writes_index(tmp_path):
    _write(tmp_path, "SR-001.md", _BOUND)
    result = cmd_index(tmp_path)
    assert result["requirements"][0]["id"] == "SR-001"
    assert result["requirements"][0]["checksum"].startswith("sha256:")
    assert result["requirements"][0]["stale"] is False
    assert json.loads((tmp_path / "index.json").read_text(encoding="utf-8")) == result


def test_index_leaves_a_proposed_requirement_untouched(tmp_path):
    path = _write(tmp_path, "SR-009.md", _PROPOSED)
    before = path.read_text(encoding="utf-8")
    result = cmd_index(tmp_path)
    assert path.read_text(encoding="utf-8") == before
    assert result["requirements"] == [{"id": "SR-009", "checksum": None, "proposed": True}]


def test_status_flags_stale_after_edit(tmp_path):
    path = _write(tmp_path, "SR-001.md", _BOUND)
    cmd_index(tmp_path)
    assert "current" in cmd_status(tmp_path)
    # Mutate the STATEMENT so the stored checksum no longer matches.
    text = path.read_text(encoding="utf-8").replace("shall do Y", "shall do Y NOW")
    path.write_text(text, encoding="utf-8")
    assert "STALE" in cmd_status(tmp_path)
    assert "SR-001" in cmd_status(tmp_path, stale_only=True)


def test_status_says_proposed_not_current(tmp_path):
    _write(tmp_path, "SR-009.md", _PROPOSED)
    assert "[proposed]" in cmd_status(tmp_path)
    assert "current" not in cmd_status(tmp_path)


def test_status_stale_only_hides_proposed(tmp_path):
    _write(tmp_path, "SR-009.md", _PROPOSED)
    assert cmd_status(tmp_path, stale_only=True) == "no requirements"


def test_show(tmp_path):
    _write(tmp_path, "SR-001.md", _BOUND)
    assert "SR-001" in cmd_show(tmp_path, "SR-001")
    assert "not found" in cmd_show(tmp_path, "SR-999")


def test_show_reports_no_binding(tmp_path):
    _write(tmp_path, "SR-009.md", _PROPOSED)
    out = cmd_show(tmp_path, "SR-009")
    assert "not yet measurable" in out
    assert "docs/superpowers/specs/a.md" in out


def test_index_refuses_to_relaunder_a_stale_checksum(tmp_path):
    path = _write(tmp_path, "SR-001.md", _BOUND)
    cmd_index(tmp_path)
    stamped = path.read_text(encoding="utf-8")

    text = stamped.replace("shall do Y", "shall do Y NOW")
    path.write_text(text, encoding="utf-8")

    result = cmd_index(tmp_path)

    entry = next(r for r in result["requirements"] if r["id"] == "SR-001")
    assert entry["stale"] is True, "index must report staleness, never absorb it"
    assert path.read_text(encoding="utf-8") == text, "a stale file is left exactly as found"
    assert "STALE" in cmd_status(tmp_path), "the signal survives an index run"


def test_index_still_stamps_a_requirement_that_has_no_checksum(tmp_path):
    _write(tmp_path, "SR-001.md", _BOUND)
    result = cmd_index(tmp_path)
    entry = next(r for r in result["requirements"] if r["id"] == "SR-001")
    assert entry["stale"] is False
    assert entry["checksum"].startswith("sha256:")


def test_main_status_exit_code(tmp_path, capsys):
    cmd_new(tmp_path, "First", "behavioral")
    rc = main(["status", "--requirements-dir", str(tmp_path)])
    assert rc == 0
    assert "SR-001" in capsys.readouterr().out


def test_show_reports_no_harness_binding(tmp_path):
    _write(tmp_path, "SR-009.md", _PROPOSED)
    cmd_bind(
        tmp_path, "SR-009", experiment="zone_clear", metric="resume_rate",
        assert_expr=">= 0.95", harness=None, trials=1, reaffirm_reason=None,
    )
    out = cmd_show(tmp_path, "SR-009")
    assert "(no harness)" in out
    assert "None" not in out


def test_bind_writes_a_measurement_and_reports_it(tmp_path):
    _write(tmp_path, "SR-009.md", _PROPOSED)
    out = cmd_bind(
        tmp_path, "SR-009", experiment="zone_clear", metric="resume_rate",
        assert_expr=">= 0.95", harness="sim-testbench", trials=3, reaffirm_reason=None,
    )
    assert "SR-009" in out
    assert "sim-testbench" in out
    assert "[proposed]" not in cmd_status(tmp_path)


def test_bind_accepts_no_harness_and_says_so(tmp_path):
    _write(tmp_path, "SR-009.md", _PROPOSED)
    out = cmd_bind(
        tmp_path, "SR-009", experiment="zone_clear", metric="resume_rate",
        assert_expr=">= 0.95", harness=None, trials=1, reaffirm_reason=None,
    )
    assert "no harness" in out.lower()


def test_bind_on_an_unknown_id_is_reported_not_raised(tmp_path):
    assert "not found" in cmd_bind(
        tmp_path, "SR-999", experiment="e", metric="m", assert_expr=">= 1",
        harness=None, trials=1, reaffirm_reason=None,
    )


def test_defer_records_the_reason_where_trace_reads_it(tmp_path):
    _write(tmp_path, "SR-009.md", _PROPOSED)
    out = cmd_defer(tmp_path, "SR-009", "no current task delivers this")
    assert "SR-009" in out
    assert "trace_deferred: no current task delivers this" in (
        tmp_path / "SR-009.md"
    ).read_text(encoding="utf-8")


def test_defer_with_a_blank_reason_is_refused(tmp_path):
    _write(tmp_path, "SR-009.md", _PROPOSED)
    assert "reason" in cmd_defer(tmp_path, "SR-009", "   ").lower()


def test_main_wires_bind_and_defer(tmp_path, capsys):
    _write(tmp_path, "SR-009.md", _PROPOSED)
    rc = main([
        "bind", "SR-009", "--requirements-dir", str(tmp_path),
        "--experiment", "zone_clear", "--metric", "resume_rate", "--assert", ">= 0.95",
    ])
    assert rc == 0
    assert "SR-009" in capsys.readouterr().out
    rc = main(["defer", "SR-009", "--requirements-dir", str(tmp_path), "--reason", "later"])
    assert rc == 0
