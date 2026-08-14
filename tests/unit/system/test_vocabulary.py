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
