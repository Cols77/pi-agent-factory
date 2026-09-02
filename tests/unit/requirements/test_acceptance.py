"""Schema and validation for the optional `acceptance:` array on an SR.

Covers T-1 of the FEAT-001 first-vertical-slice plan: each SR may declare zero or
more individually addressable acceptance criteria, each bound to a verification
kind. Absence of the field must parse exactly as it did before this field existed;
presence with a malformed entry must be rejected at load, not silently dropped.
"""

from pathlib import Path

import pytest

from coherence.register.register import (
    AcceptanceCriterion,
    VerificationBinding,
    parse_requirement,
)

pytestmark = pytest.mark.unit

_HEADER = """---
id: SR-001
title: "Nav preempts patrol for in-zone shark"
statement: "When a shark is detected inside a swim zone, the navigation system shall preempt patrol."
domain: behavioral
upstream: []
"""


def _write(tmp_path: Path, acceptance_yaml: str) -> Path:
    text = _HEADER + acceptance_yaml + "---\nRationale here.\n"
    path = tmp_path / "SR-001.md"
    path.write_text(text, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_an_sr_without_acceptance_parses_with_an_empty_tuple(tmp_path):
    req = parse_requirement(_write(tmp_path, ""))
    assert req.acceptance == ()
    assert isinstance(req.acceptance, tuple)


def test_an_sr_with_a_well_formed_acceptance_array_round_trips(tmp_path):
    yaml = """acceptance:
  - id: AC-1
    criterion: "A spec carrying duplicate ids with differing content fails deterministically."
    verification:
      kind: test_marker
      ref: "tests/unit/coherence/trace/test_spec_frontmatter.py"
  - id: AC-2
    criterion: "A harness run measures preemption latency directly."
    verification:
      kind: harness
      ref: "sim-testbench"
  - id: AC-3
    criterion: "A reviewer confirms the UX reads clearly."
    verification:
      kind: manual
      reason: "no automated oracle exists for subjective UX quality"
"""
    req = parse_requirement(_write(tmp_path, yaml))
    assert len(req.acceptance) == 3

    ac1 = req.acceptance[0]
    assert isinstance(ac1, AcceptanceCriterion)
    assert ac1.id == "AC-1"
    assert ac1.criterion == (
        "A spec carrying duplicate ids with differing content fails deterministically."
    )
    assert ac1.verification == VerificationBinding(
        kind="test_marker",
        ref="tests/unit/coherence/trace/test_spec_frontmatter.py",
    )

    ac2 = req.acceptance[1]
    assert ac2.verification.kind == "harness"
    assert ac2.verification.ref == "sim-testbench"
    assert ac2.verification.reason is None

    ac3 = req.acceptance[2]
    assert ac3.verification.kind == "manual"
    assert ac3.verification.reason == "no automated oracle exists for subjective UX quality"
    assert ac3.verification.ref is None


def test_a_criterion_is_addressable_as_sr_id_slash_ac_id(tmp_path):
    yaml = """acceptance:
  - id: AC-3
    criterion: "c"
    verification:
      kind: manual
      reason: "r"
"""
    req = parse_requirement(_write(tmp_path, yaml))
    assert req.acceptance[0].qualified_id(req.id) == "SR-001/AC-3"


# ---------------------------------------------------------------------------
# Malformed cases -- each must raise ValueError at load, naming the file, and
# each `match=` below asserts the *specific* failure reason for that case (not
# just the filename or the criterion id) so that a wrong-but-adjacent error
# from a different validation branch cannot satisfy the wrong test.
# ---------------------------------------------------------------------------


def test_acceptance_that_is_not_a_list_is_rejected(tmp_path):
    yaml = "acceptance: not-a-list\n"
    with pytest.raises(ValueError, match="acceptance: must be a list"):
        parse_requirement(_write(tmp_path, yaml))


def test_an_entry_that_is_not_a_mapping_is_rejected(tmp_path):
    yaml = "acceptance:\n  - just a string\n"
    with pytest.raises(ValueError, match="entry must be a mapping"):
        parse_requirement(_write(tmp_path, yaml))


def test_an_entry_missing_id_is_rejected(tmp_path):
    yaml = """acceptance:
  - criterion: "c"
    verification:
      kind: manual
      reason: "r"
"""
    with pytest.raises(ValueError, match=r"missing required field 'id'"):
        parse_requirement(_write(tmp_path, yaml))


def test_an_entry_missing_criterion_is_rejected(tmp_path):
    yaml = """acceptance:
  - id: AC-1
    verification:
      kind: manual
      reason: "r"
"""
    with pytest.raises(ValueError, match=r"AC-1.*missing required field 'criterion'"):
        parse_requirement(_write(tmp_path, yaml))


def test_an_entry_with_a_blank_criterion_is_rejected(tmp_path):
    yaml = """acceptance:
  - id: AC-1
    criterion: "   "
    verification:
      kind: manual
      reason: "r"
"""
    with pytest.raises(ValueError, match=r"AC-1.*missing required field 'criterion'"):
        parse_requirement(_write(tmp_path, yaml))


def test_an_entry_missing_verification_is_rejected(tmp_path):
    yaml = """acceptance:
  - id: AC-1
    criterion: "c"
"""
    with pytest.raises(ValueError, match=r"AC-1.*missing required field 'verification'"):
        parse_requirement(_write(tmp_path, yaml))


def test_an_unknown_verification_kind_is_rejected(tmp_path):
    yaml = """acceptance:
  - id: AC-1
    criterion: "c"
    verification:
      kind: telepathy
      ref: "x"
"""
    with pytest.raises(ValueError, match=r"AC-1.*verification\.kind must be one of"):
        parse_requirement(_write(tmp_path, yaml))


@pytest.mark.parametrize("kind", ["test_marker", "harness"])
def test_test_marker_and_harness_require_a_ref(tmp_path, kind):
    yaml = f"""acceptance:
  - id: AC-1
    criterion: "c"
    verification:
      kind: {kind}
"""
    with pytest.raises(ValueError, match=r"AC-1.*requires a non-blank 'ref'"):
        parse_requirement(_write(tmp_path, yaml))


@pytest.mark.parametrize("kind", ["test_marker", "harness"])
def test_test_marker_and_harness_reject_a_blank_ref(tmp_path, kind):
    yaml = f"""acceptance:
  - id: AC-1
    criterion: "c"
    verification:
      kind: {kind}
      ref: "   "
"""
    with pytest.raises(ValueError, match=r"AC-1.*requires a non-blank 'ref'"):
        parse_requirement(_write(tmp_path, yaml))


def test_manual_requires_a_reason(tmp_path):
    yaml = """acceptance:
  - id: AC-1
    criterion: "c"
    verification:
      kind: manual
"""
    with pytest.raises(ValueError, match=r"AC-1.*requires a non-blank 'reason'"):
        parse_requirement(_write(tmp_path, yaml))


def test_manual_rejects_a_blank_reason(tmp_path):
    yaml = """acceptance:
  - id: AC-1
    criterion: "c"
    verification:
      kind: manual
      reason: "   "
"""
    with pytest.raises(ValueError, match=r"AC-1.*requires a non-blank 'reason'"):
        parse_requirement(_write(tmp_path, yaml))


def test_a_duplicate_criterion_id_within_one_sr_is_rejected(tmp_path):
    yaml = """acceptance:
  - id: AC-1
    criterion: "first"
    verification:
      kind: manual
      reason: "r"
  - id: AC-1
    criterion: "second, differs from the first"
    verification:
      kind: manual
      reason: "r"
"""
    with pytest.raises(ValueError, match=r"AC-1.*duplicate criterion id"):
        parse_requirement(_write(tmp_path, yaml))


def test_a_malformed_entry_is_rejected_wholesale_not_partially_kept(tmp_path):
    """The second entry is malformed; the whole load must fail -- the first,
    well-formed entry must never be silently kept on its own."""
    yaml = """acceptance:
  - id: AC-1
    criterion: "well formed"
    verification:
      kind: manual
      reason: "r"
  - id: AC-2
    criterion: "malformed: missing verification"
"""
    with pytest.raises(ValueError, match=r"AC-2.*missing required field 'verification'"):
        parse_requirement(_write(tmp_path, yaml))
