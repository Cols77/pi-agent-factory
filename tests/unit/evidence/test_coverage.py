from __future__ import annotations

import pytest

from factory.evidence.coverage import coverage_errors

pytestmark = pytest.mark.unit

BODY = "- Modify: `src/b.py`\n- Create: `src/a.py`\n- Test: `tests/test_a.py`"


def test_passes_when_modify_gathered_and_exists(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "b.py").write_text("x", encoding="utf-8")
    context = {"source_files": ["src/b.py"], "spec": [], "plan": []}
    assert coverage_errors(BODY, context, tmp_path) == []


def test_error_when_modify_not_gathered(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "b.py").write_text("x", encoding="utf-8")
    context = {"source_files": [], "spec": [], "plan": []}
    errs = coverage_errors(BODY, context, tmp_path)
    assert errs and "src/b.py" in errs[0] and "not gathered" in errs[0]


def test_error_when_gathered_but_missing_on_disk(tmp_path):
    context = {"source_files": ["src/b.py"], "spec": [], "plan": []}
    errs = coverage_errors(BODY, context, tmp_path)
    assert errs and "src/b.py" in errs[0] and "missing on disk" in errs[0]


def test_anchor_in_gathered_ref_is_stripped(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "b.py").write_text("x", encoding="utf-8")
    context = {"source_files": ["src/b.py#Foo"], "spec": [], "plan": []}
    assert coverage_errors(BODY, context, tmp_path) == []


def test_no_modify_deliverables_is_clean(tmp_path):
    context = {"source_files": [], "spec": [], "plan": []}
    assert coverage_errors("- Create: `src/a.py`", context, tmp_path) == []
