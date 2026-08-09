import frontmatter
import pytest
from factory.requirements.register import is_checksum_current, parse_requirement
from factory.requirements.write import (
    ReasonRequiredError,
    reaffirm,
    write_binding,
    write_deferral,
)

pytestmark = pytest.mark.unit

_PROPOSED = """---
id: SR-009
title: Proposed requirement
statement: "When the zone clears, the system shall resume patrol."
domain: behavioral
upstream: []
---
Rationale.
"""


def _write(tmp_path, text=_PROPOSED, name="SR-009.md"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_write_binding_stamps_a_current_checksum(tmp_path):
    path = _write(tmp_path)
    write_binding(
        path, experiment="zone_clear", metric="resume_rate", assert_expr=">= 0.95",
        harness="sim-testbench", trials=3, window=None,
    )
    req = parse_requirement(path)
    assert req.binding is not None
    assert req.binding.harness == "sim-testbench"
    assert req.binding.metric == "resume_rate"
    assert is_checksum_current(req), "a freshly written binding is never stale"


def test_write_binding_accepts_no_harness(tmp_path):
    path = _write(tmp_path)
    write_binding(
        path, experiment="zone_clear", metric="resume_rate", assert_expr=">= 0.95",
        harness=None, trials=1, window=None,
    )
    req = parse_requirement(path)
    assert req.binding.harness is None
    assert is_checksum_current(req)


def test_write_binding_preserves_the_body_and_other_fields(tmp_path):
    path = _write(tmp_path)
    write_binding(
        path, experiment="e", metric="m", assert_expr=">= 1", harness=None, trials=1, window=None,
    )
    post = frontmatter.load(str(path))
    assert "Rationale." in post.content
    assert post["title"] == "Proposed requirement"


def test_reaffirm_makes_a_stale_requirement_current_again(tmp_path):
    path = _write(tmp_path)
    write_binding(
        path, experiment="e", metric="m", assert_expr=">= 1", harness="h", trials=1, window=None,
    )
    post = frontmatter.load(str(path))
    post["statement"] = "When the zone clears, the system shall resume patrol PROMPTLY."
    path.write_text(frontmatter.dumps(post), encoding="utf-8")
    assert not is_checksum_current(parse_requirement(path))

    reaffirm(path, "wording clarified; the measurement is unchanged")

    assert is_checksum_current(parse_requirement(path))
    assert "wording clarified" in path.read_text(encoding="utf-8")


def test_reaffirm_without_a_reason_is_refused(tmp_path):
    path = _write(tmp_path)
    write_binding(
        path, experiment="e", metric="m", assert_expr=">= 1", harness="h", trials=1, window=None,
    )
    with pytest.raises(ReasonRequiredError):
        reaffirm(path, "   ")


def test_write_deferral_uses_the_field_trace_already_reads(tmp_path):
    path = _write(tmp_path)
    write_deferral(path, "no current task delivers this")
    post = frontmatter.load(str(path))
    assert post["trace_deferred"] == "no current task delivers this"


def test_write_deferral_refuses_a_blank_reason(tmp_path):
    path = _write(tmp_path)
    with pytest.raises(ReasonRequiredError):
        write_deferral(path, "")


def test_a_deferral_does_not_stale_a_bound_requirement(tmp_path):
    path = _write(tmp_path)
    write_binding(
        path, experiment="e", metric="m", assert_expr=">= 1", harness="h", trials=1, window=None,
    )
    write_deferral(path, "still open")
    assert is_checksum_current(parse_requirement(path)), "a disposition is not a metric input"
