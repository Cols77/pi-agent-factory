# Guards against the TypeScript mirror of the vocabulary/remediation tables
# (pi-ext/factory-watch/src/system-vocabulary-data.ts) diverging from the
# Python tables it was copied from (Task 8). The TS mirror exists because
# renderSystemPageHtml() is synchronous and cannot spawn Python at request
# time; this test is what keeps that copy honest.
import json
import re
from pathlib import Path

import pytest

from factory.system.remediation import REMEDIATION
from factory.system.vocabulary import PANELS, VOCABULARY

pytestmark = pytest.mark.unit

TS = Path("pi-ext/factory-watch/src/system-vocabulary-data.ts")


def _extract(name: str) -> dict:
    text = TS.read_text(encoding="utf-8")
    match = re.search(rf"export const {name} = (\{{.*?\}}) as const;", text, re.S)
    assert match, f"{name} not found in {TS}"
    return json.loads(match.group(1))


def test_vocabulary_mirror_matches_python():
    assert _extract("VOCABULARY_DATA") == {"version": 1, "terms": VOCABULARY}


def test_remediation_mirror_matches_python():
    assert _extract("REMEDIATION_DATA") == {"version": 1, "states": REMEDIATION}


def test_panels_mirror_matches_python():
    assert _extract("PANELS_DATA") == {"version": 1, "panels": PANELS}
