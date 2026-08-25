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
from substrate.codemap.imports import reachable_symbols

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


# -- Symbol scope: match canonical qualified names from reachable_symbols. --


def _symbol_repo(root: Path) -> None:
    """Same 'moved symbol' fixture as test_codemap_imports: `factory.function`
    lives in src/factory/module.py and the edited file client.py reaches it by
    import. Returns nothing; builds in place under `root`."""
    (root / "src" / "factory").mkdir(parents=True)
    (root / "src" / "factory" / "__init__.py").write_text("")
    (root / "src" / "factory" / "module.py").write_text(
        '"""Home of the moved symbol."""\n'
        "def function(value=1):\n"
        "    return value + 1\n"
    )
    (root / "src" / "factory" / "client.py").write_text(
        "from factory.module import function\n\n"
        "def call():\n"
        "    return function(2)\n"
    )


def _fresh_symbol_snapshot(root: Path) -> None:
    from substrate.codemap.store import ensure_fresh

    ensure_fresh(
        root,
        files=[
            "src/factory/__init__.py",
            "src/factory/module.py",
            "src/factory/client.py",
        ],
    )


def _write_symbol_kb(kb_dir: Path, entry_id: str = "kb-0201") -> None:
    """Write a KB entry scoped PURELY by a canonical qualified symbol."""
    kb_dir.mkdir(parents=True, exist_ok=True)
    (kb_dir / f"{entry_id}-symbol-scope.md").write_text(
        "---\n"
        f"id: {entry_id}\n"
        "title: Moved-symbol issue\n"
        "status: active\n"
        "severity: low\n"
        "tags: []\n"
        "scope:\n"
        "  symbols:\n"
        '    - "factory.module.function"\n'
        "---\n"
        "body\n",
        encoding="utf-8",
    )


def test_select_entries_matches_moved_symbol_via_reachable_symbols(tmp_path):
    _symbol_repo(tmp_path)
    _fresh_symbol_snapshot(tmp_path)
    reachable = reachable_symbols(tmp_path, ["src/factory/client.py"])
    assert reachable.status == "resolved"

    kb = tmp_path / "kb"
    _write_symbol_kb(kb)
    ids = substrate_select_entries(kb, ["src/factory/client.py"], [], reachable_symbols=reachable)
    assert ids == ["kb-0201"]


def test_select_entries_stale_codemap_diagnostic_and_no_file_glob_fallback(tmp_path):
    _symbol_repo(tmp_path)
    _fresh_symbol_snapshot(tmp_path)
    # Make the snapshot stale by editing a source file after building it.
    (tmp_path / "src" / "factory" / "module.py").write_text(
        "def renamed():\n    return 9\n"
    )
    reachable = reachable_symbols(tmp_path, ["src/factory/client.py"])
    assert reachable.status == "stale"
    assert reachable.symbols == ()

    kb = tmp_path / "kb"
    _write_symbol_kb(kb)
    diagnostics: list[str] = []
    # The touched file actually addresses the symbol, yet a stale snapshot must
    # NOT fall back to a file-glob / text match to claim a symbol hit.
    ids = substrate_select_entries(
        kb,
        ["src/factory/client.py"],
        [],
        reachable_symbols=reachable,
        diagnostics=diagnostics,
    )
    assert ids == []
    assert any("stale" in d.lower() for d in diagnostics)


def test_select_entries_missing_codemap_diagnostic_and_no_symbol_hit(tmp_path):
    _symbol_repo(tmp_path)  # code present, no snapshot ever built
    reachable = reachable_symbols(tmp_path, ["src/factory/client.py"])
    assert reachable.status == "missing"

    kb = tmp_path / "kb"
    _write_symbol_kb(kb)
    diagnostics: list[str] = []
    ids = substrate_select_entries(
        kb,
        ["src/factory/client.py"],
        [],
        reachable_symbols=reachable,
        diagnostics=diagnostics,
    )
    assert ids == []
    assert any("missing" in d.lower() for d in diagnostics)


def test_select_entries_symbol_match_is_exact_qualified_name(tmp_path):
    kb = tmp_path / "kb"
    _write_symbol_kb(kb)

    # A partial / last-segment name must NOT match -- canonical qualified names only.
    ids = substrate_select_entries(
        kb, [], [], reachable_symbols=("module.function",)
    )
    assert ids == []

    # The fully-qualified canonical name does match.
    ids = substrate_select_entries(
        kb, [], [], reachable_symbols=("factory.module.function",)
    )
    assert ids == ["kb-0201"]


def test_select_entries_legacy_files_and_signatures_still_work_with_symbols_present(tmp_path):
    # A symbol-scoped entry can ALSO carry legacy files/error_signatures scope,
    # and those keep selecting on their own terms (backward compat).
    kb = tmp_path / "kb"
    kb.mkdir(parents=True, exist_ok=True)
    (kb / "kb-0202-hybrid.md").write_text(
        "---\n"
        "id: kb-0202\n"
        "title: Hybrid-scoped issue\n"
        "status: active\n"
        "severity: low\n"
        "tags: []\n"
        "scope:\n"
        "  symbols:\n"
        '    - "factory.module.function"\n'
        "  files:\n"
        '    - "src/legacy/handler.py"\n'
        "  error_signatures:\n"
        '    - "TimeoutError"\n'
        "---\n"
        "body\n",
        encoding="utf-8",
    )

    # Legacy match by touched file, with no reachable symbols supplied at all.
    assert substrate_select_entries(kb, ["src/legacy/handler.py"], []) == ["kb-0202"]
    # Legacy match by failure signature.
    assert substrate_select_entries(kb, [], ["boom TimeoutError boom"]) == ["kb-0202"]

    # Legacy selects with an EMPTY reachable set stay unchanged (default value).
    assert (
        substrate_select_entries(
            kb, ["src/legacy/handler.py"], [], reachable_symbols=()
        )
        == ["kb-0202"]
    )
