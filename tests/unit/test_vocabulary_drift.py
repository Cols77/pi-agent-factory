# Guards against two small vocabularies that are duplicated across files
# which cannot import each other. `substrate.ledger.tasks` and
# `coherence.trace.model` each define their own `_JUSTIFICATION_KINDS`
# tuple -- `coherence.trace.model` intentionally never imports
# `substrate.ledger.tasks` (it must stay a pure frontmatter reader), so the
# two copies can only be kept honest by a test that imports both and
# compares them. Likewise `substrate.policy.vocabulary.KNOWN_PRESETS` is
# duplicated as an `"enum"` in two JSON schemas (`profile.schema.json`,
# `feat.schema.json`) that validate the same field independently of the
# Python module. These tests exist so a change to one copy that forgets
# the others fails loudly instead of silently drifting.
import json

import pytest

from coherence.trace.model import _JUSTIFICATION_KINDS as _MODEL_KINDS
from substrate.ledger.tasks import _JUSTIFICATION_KINDS as _TASKS_KINDS
from substrate.policy.vocabulary import KNOWN_PRESETS
from substrate.validators.schema import SCHEMA_DIR

pytestmark = pytest.mark.unit


def test_justification_kinds_agree_between_tasks_and_model():
    assert _TASKS_KINDS == _MODEL_KINDS


@pytest.mark.parametrize("schema_name", ["profile.schema.json", "feat.schema.json"])
def test_profile_enum_agrees_with_known_presets(schema_name):
    schema = json.loads((SCHEMA_DIR / schema_name).read_text(encoding="utf-8"))
    enum = schema["properties"]["profile"]["enum"]
    assert set(enum) == set(KNOWN_PRESETS)
