"""Legacy/structured deferral migration (Increment 6 Task 3).

`trace_deferred` has historically been a bare reason scalar; Task 3 adds a
structured form carrying `review_after`/`decided_at`/`decided_by` so a
deferral can expire. ``parse_deferral`` accepts BOTH forms and renders the
same present deferral; only structured, due (``review_after`` past ``now``)
deferrals count as expired. Unknown shapes are REJECTED -- never silently
treated as current/non-deferred.
"""
from __future__ import annotations

import pytest

from coherence.deferrals import Deferral, parse_deferral, deferral_is_due

pytestmark = pytest.mark.unit

NOW = "2026-09-15T00:00:00Z"


# -- scalar (legacy) form ---------------------------------------------------


def test_parse_legacy_scalar_reason():
    d = parse_deferral("reason text")
    assert isinstance(d, Deferral)
    assert d.reason == "reason text"
    assert d.review_after is None
    assert d.decided_at is None
    assert d.decided_by is None


def test_legend_scalar_never_expires():
    # A legacy scalar has no review_after, so it can never be "due".
    d = parse_deferral("reason text")
    assert deferral_is_due(d, NOW) is False


# --structured form ---------------------------------------------------------


def test_parse_structured_dict():
    d = parse_deferral(
        {
            "reason": "reason",
            "review_after": "2026-09-01T00:00:00Z",
            "decided_at": "2026-08-20T00:00:00Z",
            "decided_by": "human@example.invalid",
        }
    )
    assert isinstance(d, Deferral)
    assert d.reason == "reason"
    assert d.review_after == "2026-09-01T00:00:00Z"
    assert d.decided_at == "2026-08-20T00:00:00Z"
    assert d.decided_by == "human@example.invalid"


def test_structured_due_deferral_is_expired():
    d = parse_deferral(
        {"reason": "reason", "review_after": "2026-09-01T00:00:00Z"}
    )
    # review_after (Sep 1) is before NOW (Sep 15) -> due/expired.
    assert deferral_is_due(d, NOW) is True


def test_structured_future_deferral_is_not_expired():
    d = parse_deferral(
        {"reason": "reason", "review_after": "2026-12-31T00:00:00Z"}
    )
    assert deferral_is_due(d, NOW) is False


def test_structured_without_review_after_is_not_expired():
    d = parse_deferral({"reason": "reason"})
    assert deferral_is_due(d, NOW) is False


# --both forms render the same present deferral -----------------------------


def test_legacy_and_structured_render_identical_reason_deferral_now():
    # The same "present deferral" (reason + still-current review_after) is
    # what a reader shows regardless of whether it was written legacy or
    # structured -- both render as "deferred: reason" for the current date.
    legacy = parse_deferral("reason")
    structured = parse_deferral(
        {"reason": "reason", "review_after": "2026-12-31T00:00:00Z"}
    )
    assert legacy.reason == structured.reason == "reason"
    # Neither is expired as of NOW.
    assert deferral_is_due(legacy, NOW) is False
    assert deferral_is_due(structured, NOW) is False


# -- unknown shapes are rejected, not treated current -----------------------


@pytest.mark.parametrize(
    "bad",
    [
        123,
        ["reason"],
        {},
        {"review_after": "2026-09-01T00:00:00Z"},  # missing reason
        {"reason": ""},  # blank reason
    ],
)
def test_unknown_shapes_are_rejected_not_treated_current(bad):
    # A malformed trace_deferred value must be REJECTED (raise), never silently
    # interpreted as "no deferral / current".
    with pytest.raises(ValueError):
        parse_deferral(bad)


# -- integration: writers round-trip through the shared reader ----------------


@pytest.mark.parametrize(
    "write_scalar,review_after",
    [
        (True, None),
        (False, "2026-09-01T00:00:00Z"),
    ],
)
def test_structured_write_round_trips_through_parse(tmp_path, write_scalar, review_after):
    # A structured write (via write_deferral with review_after) must be
    # recoverable by parse_deferral with the same reason and expiry, while a
    # legacy reason-only write stays the bare scalar (still readable the same
    # way). This ties the writer migration to the shared reader.
    from coherence.register.write import write_deferral

    p = tmp_path / "SR-001.md"
    p.write_text("---\nid: SR-001\ntitle: t\nstatement: s\ndomain: d\n---\n\nbody\n", encoding="utf-8")
    write_deferral(p, "scheduled later", review_after=review_after)

    import frontmatter

    post = frontmatter.load(str(p))
    parsed = parse_deferral(post["trace_deferred"])
    assert parsed.reason == "scheduled later"
    if write_scalar:
        assert isinstance(post["trace_deferred"], str)
        assert parsed.review_after is None
    else:
        assert isinstance(post["trace_deferred"], dict)
        assert parsed.review_after == review_after
        assert deferral_is_due(parsed, NOW) is True