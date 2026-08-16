import pytest

from factory.system.vocabulary import COVERAGE_REGISTRY, VOCABULARY, build_vocabulary

# Required: pyproject.toml:31 sets addopts = "-m unit". Without this marker
# every test here is deselected and pytest exits 5.
pytestmark = pytest.mark.unit


def test_every_registry_value_has_an_entry():
    missing = [
        value
        for values in COVERAGE_REGISTRY.values()
        for value in values
        if value not in VOCABULARY
    ]
    assert missing == [], f"undefined vocabulary terms: {missing}"


def test_every_entry_is_in_the_registry():
    known = {v for values in COVERAGE_REGISTRY.values() for v in values}
    assert set(VOCABULARY) - known == set()


def test_glosses_are_at_most_eight_words():
    long = {t: e["gloss"] for t, e in VOCABULARY.items() if len(e["gloss"].split()) > 8}
    assert long == {}


def test_computed_by_is_always_a_list():
    assert all(isinstance(e["computed_by"], list) for e in VOCABULARY.values())


def test_every_entry_has_a_readable_label():
    assert all(e.get("label") for e in VOCABULARY.values())


def test_health_class_labels_are_readable_not_arrow_notation():
    for name in ("task->plan", "task->SR", "plan->spec"):
        assert "->" not in VOCABULARY[name]["label"]


def test_claim_kinds_match_the_typescript_union():
    ts = (
        __import__("pathlib").Path("pi-ext/factory-watch/src/system-cli.ts")
        .read_text(encoding="utf-8")
    )
    for kind in ("recorded", "derived", "synthesized", "missing"):
        assert f'"{kind}"' in ts
        assert kind in VOCABULARY


def test_build_vocabulary_is_serialisable():
    import json
    json.dumps(build_vocabulary())


# --- Fix round 1: gate strengthening -----------------------------------
#
# The tests above only check VOCABULARY and COVERAGE_REGISTRY against each
# other, so a registry that is short of what the design actually enumerates
# (e.g. missing a real CitationKind.VALIDATION) still passes them silently.
# For every group backed by a closed Python enum, derive the expected value
# set from that enum directly -- the enum is the authority; a hand-typed
# tuple can drift from it, an enum comprehension cannot.


def test_registry_groups_backed_by_enums_match_those_enums_exactly():
    from factory.system.models import (
        CitationKind,
        ClaimClass,
        FreshnessState,
        MatrixStatus,
        TimelineAction,
        TimelineActor,
    )

    enum_backed_groups = {
        "claim-kind": ClaimClass,
        "freshness": FreshnessState,
        "matrix-status": MatrixStatus,
        "timeline-actor": TimelineActor,
        "timeline-action": TimelineAction,
        "citation-kind": CitationKind,
    }
    for group, enum_cls in enum_backed_groups.items():
        expected = {member.value for member in enum_cls}
        actual = set(COVERAGE_REGISTRY[group])
        assert actual == expected, f"{group}: registry {actual} != enum {expected}"


def test_disposition_literal_values_are_all_defined_in_vocabulary():
    # trace/gaps.py:23's Disposition Literal is the authority for trace
    # dispositions; the registry's own "disposition" tuple intentionally
    # drops "deferred" (it already has an entry under readiness-count), so
    # this checks VOCABULARY coverage directly rather than the registry
    # tuple, the same de-duplication the module docstring documents.
    from typing import get_args

    from factory.trace.gaps import Disposition

    for value in get_args(Disposition):
        assert value in VOCABULARY, f"disposition {value!r} has no vocabulary entry"
