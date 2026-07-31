from pathlib import Path

import pytest
from factory.requirements.register import (
    Binding,
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


def _write(dir_: Path, name: str, text: str) -> Path:
    p = dir_ / name
    p.write_text(text, encoding="utf-8")
    return p


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
