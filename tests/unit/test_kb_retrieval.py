import warnings
import pytest
from pathlib import Path

with warnings.catch_warnings():
    warnings.simplefilter("ignore", DeprecationWarning)
    from factory.kb.retrieval import select_entries, list_kb_titles

from substrate.kb.retrieval import (
    list_kb_titles as substrate_list_kb_titles,
    load_entries,
    select_entries as substrate_select_entries,
)

pytestmark = pytest.mark.unit

KB_DIR = Path(__file__).resolve().parents[2] / "kb"


def test_matches_by_file_glob():
    ids = select_entries(KB_DIR, ["src/example/retry_client.py"], [])
    assert "kb-0001" in ids


def test_matches_by_signature_substring():
    ids = select_entries(KB_DIR, [], ["ConnectionResetError: connection reset by peer"])
    assert "kb-0001" in ids


def test_no_match_returns_empty():
    assert select_entries(KB_DIR, ["src/unrelated/thing.py"], ["totally other"]) == []


def test_invalid_entry_skipped_without_crashing(tmp_path):
    import shutil

    shutil.copy(
        KB_DIR / "kb-0001-example-entry.md", tmp_path / "kb-0001-example-entry.md"
    )
    # Missing the required "id" field entirely: would raise KeyError if
    # selected without validation first.
    (tmp_path / "kb-0002-broken.md").write_text(
        "---\ntitle: t\nstatus: active\nseverity: low\n"
        "tags: []\nscope:\n  files: ['*']\n---\nbody\n",
        encoding="utf-8",
    )
    ids = select_entries(tmp_path, [], ["ConnectionResetError: connection reset by peer"])
    assert ids == ["kb-0001"]


def test_list_kb_titles_returns_id_and_title_for_every_entry():
    titles = list_kb_titles(KB_DIR)
    assert ("kb-0001", "Example: flaky retry needs a longer backoff") in titles


def test_list_kb_titles_empty_dir_returns_empty_list(tmp_path):
    assert list_kb_titles(tmp_path) == []


def test_list_kb_titles_includes_inactive_entries(tmp_path):
    # Unlike select_entries, list_kb_titles is for duplicate-avoidance
    # awareness, not task relevance -- it should not filter by status.
    (tmp_path / "kb-0099-retired.md").write_text(
        "---\nid: kb-0099\ntitle: Retired issue\nstatus: retired\nseverity: low\n"
        "tags: []\nscope:\n  files: []\n---\nbody\n",
        encoding="utf-8",
    )
    assert ("kb-0099", "Retired issue") in list_kb_titles(tmp_path)


def test_old_shim_warns_and_matches_substrate_retrieval_on_path_glob_fixtures():
    import importlib
    import sys

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", DeprecationWarning)
        sys.modules.pop("factory.kb.retrieval", None)
        old_retrieval_module = importlib.import_module("factory.kb.retrieval")

    deprecations = [item for item in caught if item.category is DeprecationWarning]
    assert len(deprecations) == 1
    assert str(deprecations[0].message) == (
        "factory.kb.retrieval is deprecated; import substrate.kb.retrieval"
    )

    old_ids = old_retrieval_module.select_entries(
        KB_DIR, ["src/example/retry_client.py"], []
    )
    new_ids = substrate_select_entries(KB_DIR, ["src/example/retry_client.py"], [])
    assert old_ids == new_ids == ["kb-0001"]

    assert old_retrieval_module.list_kb_titles(KB_DIR) == substrate_list_kb_titles(KB_DIR)
    assert old_retrieval_module.load_entries is load_entries


def test_load_entries_returns_all_valid_entries_when_ids_is_none():
    entries = load_entries(KB_DIR)
    assert any(e.get("id") == "kb-0001" for e in entries)


def test_load_entries_filters_by_ids():
    entries = load_entries(KB_DIR, ids=["kb-0001"])
    assert [e.get("id") for e in entries] == ["kb-0001"]


def test_load_entries_skips_invalid_entry_without_crashing(tmp_path):
    import shutil

    shutil.copy(
        KB_DIR / "kb-0001-example-entry.md", tmp_path / "kb-0001-example-entry.md"
    )
    (tmp_path / "kb-0002-broken.md").write_text(
        "---\ntitle: t\nstatus: active\nseverity: low\ntags: []\nscope:\n  files: []\n---\nbody\n",
        encoding="utf-8",
    )
    entries = load_entries(tmp_path)
    assert [e.get("id") for e in entries] == ["kb-0001"]


def test_load_entries_unknown_id_returns_empty():
    assert load_entries(KB_DIR, ids=["kb-9999"]) == []
