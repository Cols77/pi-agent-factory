from pathlib import Path

import pytest
from factory.requirements.register import (
    Binding,
    Requirement,
    content_checksum,
    get_requirement,
    is_checksum_current,
    load_register,
    parse_requirement,
)

pytestmark = pytest.mark.unit

_SR = """---
id: SR-001
title: "Nav preempts patrol for in-zone shark"
statement: "When a shark is detected inside a swim zone, the navigation system shall preempt patrol."
domain: behavioral
upstream: [BR-002]
binding:
  harness: sim-testbench
  experiment: shark_warning
  metric: preemption_success_rate
  trials: 20
  assert: ">= 0.90"
  window: {after_event: shark_detected, within_s: 5}
checksum: null
---
Rationale here.
"""


_PROPOSED = """---
id: SR-009
title: Investigate is abandoned when the zone clears
statement: When the swim zone becomes empty during an investigate directive, the
  navigation system shall abandon the investigation and resume patrol.
domain: behavioral
source: docs/superpowers/specs/2026-07-21-mission-agent-navigation-design.md
---

## Rationale
Zone-clear must not strand the drone in investigate.
"""


def _write(dir_: Path, name: str, text: str) -> Path:
    p = dir_ / name
    p.write_text(text, encoding="utf-8")
    return p


def test_a_requirement_with_no_binding_parses(tmp_path):
    req = parse_requirement(_write(tmp_path, "SR-009.md", _PROPOSED))
    assert req.binding is None
    assert req.id == "SR-009"
    assert req.source is not None
    assert req.source.endswith("mission-agent-navigation-design.md")


def test_a_proposed_requirement_is_never_stale(tmp_path):
    # Nothing to be stale against. False would print STALE forever.
    req = parse_requirement(_write(tmp_path, "SR-009.md", _PROPOSED))
    assert is_checksum_current(req) is True


def test_checksumming_a_proposed_requirement_is_refused(tmp_path):
    req = parse_requirement(_write(tmp_path, "SR-009.md", _PROPOSED))
    with pytest.raises(ValueError, match="no binding"):
        content_checksum(req)


def test_a_bound_requirement_carries_no_source_by_default(tmp_path):
    req = parse_requirement(_write(tmp_path, "SR-001.md", _SR))
    assert req.binding is not None
    assert req.source is None


def test_parse_requirement_reads_binding(tmp_path):
    req = parse_requirement(_write(tmp_path, "SR-001.md", _SR))
    assert req.id == "SR-001"
    assert req.domain == "behavioral"
    assert req.upstream == ["BR-002"]
    assert isinstance(req.binding, Binding)
    assert req.binding.harness == "sim-testbench"
    assert req.binding.experiment == "shark_warning"
    assert req.binding.metric == "preemption_success_rate"
    assert req.binding.trials == 20
    assert req.binding.assert_expr == ">= 0.90"
    assert req.binding.window == {"after_event": "shark_detected", "within_s": 5}


def test_checksum_is_stable_and_detects_change(tmp_path):
    req = parse_requirement(_write(tmp_path, "SR-001.md", _SR))
    c1 = content_checksum(req)
    assert c1.startswith("sha256:")
    # Same content → same checksum
    req2 = parse_requirement(_write(tmp_path, "SR-001.md", _SR))
    assert content_checksum(req2) == c1
    # Changed statement → different checksum
    changed = _SR.replace("preempt patrol", "preempt patrol IMMEDIATELY")
    req3 = parse_requirement(_write(tmp_path, "SR-001.md", changed))
    assert content_checksum(req3) != c1


def test_is_checksum_current(tmp_path):
    # File with checksum: null is never "current"
    req = parse_requirement(_write(tmp_path, "SR-001.md", _SR))
    assert is_checksum_current(req) is False
    # File whose stored checksum matches its content is "current"
    stamped = _SR.replace("checksum: null", f"checksum: {content_checksum(req)}")
    req2 = parse_requirement(_write(tmp_path, "SR-001.md", stamped))
    assert is_checksum_current(req2) is True


@pytest.mark.sr("SR-002")
def test_load_register_and_get(tmp_path):
    _write(tmp_path, "SR-001.md", _SR)
    _write(tmp_path, "SR-002.md", _SR.replace("SR-001", "SR-002"))
    reqs = load_register(tmp_path)
    assert [r.id for r in reqs] == ["SR-001", "SR-002"]
    assert get_requirement(reqs, "SR-002").id == "SR-002"
    assert get_requirement(reqs, "SR-999") is None


def test_binding_cadence_defaults_and_parses(tmp_path):
    base = _SR  # existing module-level template with a full binding
    p = tmp_path / "SR-009.md"
    p.write_text(base.replace("SR-001", "SR-009"), encoding="utf-8")
    assert parse_requirement(p).binding.cadence == "every_iteration"  # default

    p2 = tmp_path / "SR-010.md"
    p2.write_text(
        base.replace("SR-001", "SR-010").replace(
            'assert: ">= 0.90"', 'assert: ">= 0.90"\n  cadence: periodic'
        ),
        encoding="utf-8",
    )
    assert parse_requirement(p2).binding.cadence == "periodic"


def test_a_binding_may_name_no_harness_yet(tmp_path):
    path = tmp_path / "SR-050.md"
    path.write_text(
        "---\n"
        "id: SR-050\n"
        "title: No harness yet\n"
        'statement: "When X, the system shall Y."\n'
        "domain: behavioral\n"
        "upstream: []\n"
        "binding:\n"
        "  experiment: demo_experiment\n"
        "  metric: demo_rate\n"
        '  assert: ">= 0.90"\n'
        "---\nRationale.\n",
        encoding="utf-8",
    )
    req = parse_requirement(path)
    assert req.binding is not None
    assert req.binding.harness is None
    assert req.binding.metric == "demo_rate"


def test_an_absent_harness_does_not_change_an_existing_digest(tmp_path):
    """The canonical string uses `harness or ""`, so a real harness digests
    exactly as it did before this change. Guards against staling the register."""
    named = Binding(
        harness="demo-harness", experiment="e", metric="m", assert_expr=">= 1", trials=1, window=None
    )
    blank = Binding(
        harness=None, experiment="e", metric="m", assert_expr=">= 1", trials=1, window=None
    )
    req_named = Requirement(
        id="SR-001", title="t", statement="s", domain="behavioral", upstream=[],
        binding=named, body="", path=tmp_path / "SR-001.md",
    )
    req_blank = Requirement(
        id="SR-002", title="t", statement="s", domain="behavioral", upstream=[],
        binding=blank, body="", path=tmp_path / "SR-002.md",
    )
    assert content_checksum(req_named) != content_checksum(req_blank)
    assert content_checksum(req_named) == (
        "sha256:d2a144ea5b8c3213376c7241beb246edf0207f2c27cf49c237089ef6464f7ee6"
    ), "a named harness must digest exactly as it did before harness became optional"
    assert content_checksum(req_named).startswith("sha256:")
