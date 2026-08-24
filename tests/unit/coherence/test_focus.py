"""Tests for coherence.focus: session focus persisted atomically in the
shared `.pi/factory/session-context.json` policy file (Increment 5 Task 2,
Review Amendments: "Focus is stored atomically in
.pi/factory/session-context.json under a coherence_focus key, matching the
existing session-policy owner; tests assert it is ignored/untracked.")."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from coherence.focus import clear_focus, get_focus, set_focus
from coherence.navigate.queries import ScopeError

pytestmark = pytest.mark.unit

_PROJECT_ROOT = Path(__file__).parents[3]
_CONTEXT_RELATIVE_PATH = Path(".pi") / "factory" / "session-context.json"


def _context_path(session_root: Path) -> Path:
    return session_root / _CONTEXT_RELATIVE_PATH


def _run_coherence(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "coherence", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )


# --------------------------------------------------------------------------
# get_focus / set_focus / clear_focus (pure primitives)
# --------------------------------------------------------------------------


def test_get_focus_returns_none_when_no_context_file_exists(tmp_path: Path):
    assert get_focus(tmp_path) is None


def test_set_focus_then_get_focus_round_trips(tmp_path: Path):
    result = set_focus(tmp_path, "feat:FEAT-NAV-017")

    assert result == "feat:FEAT-NAV-017"
    assert get_focus(tmp_path) == "feat:FEAT-NAV-017"


def test_set_focus_writes_to_the_shared_session_context_json_location(tmp_path: Path):
    set_focus(tmp_path, "feat:FEAT-NAV-017")

    path = _context_path(tmp_path)
    assert path.is_file()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["coherence_focus"] == "feat:FEAT-NAV-017"


def test_set_focus_with_invalid_scope_ref_raises_and_creates_no_file(tmp_path: Path):
    with pytest.raises(ScopeError):
        set_focus(tmp_path, "not-a-valid-ref")

    assert not _context_path(tmp_path).exists()
    assert not (tmp_path / ".pi").exists()


def test_set_focus_with_unknown_kind_raises_and_creates_no_file(tmp_path: Path):
    with pytest.raises(ScopeError):
        set_focus(tmp_path, "bogus:XYZ-1")

    assert not _context_path(tmp_path).exists()


def test_set_focus_invalid_ref_does_not_disturb_an_existing_file(tmp_path: Path):
    set_focus(tmp_path, "feat:FEAT-NAV-017")
    path = _context_path(tmp_path)
    before = path.read_text(encoding="utf-8")

    with pytest.raises(ScopeError):
        set_focus(tmp_path, "garbage")

    assert path.read_text(encoding="utf-8") == before


def test_clear_focus_removes_the_key(tmp_path: Path):
    set_focus(tmp_path, "sr:SR-001")
    clear_focus(tmp_path)

    assert get_focus(tmp_path) is None
    payload = json.loads(_context_path(tmp_path).read_text(encoding="utf-8"))
    assert "coherence_focus" not in payload


def test_clear_focus_is_a_noop_when_no_context_file_exists(tmp_path: Path):
    clear_focus(tmp_path)  # must not raise

    assert not _context_path(tmp_path).exists()


def test_clear_focus_is_a_noop_when_no_focus_key_is_present(tmp_path: Path):
    path = _context_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"schema": 1}), encoding="utf-8")
    before = path.read_text(encoding="utf-8")

    clear_focus(tmp_path)

    assert path.read_text(encoding="utf-8") == before


def test_set_focus_overwrites_a_previous_focus(tmp_path: Path):
    set_focus(tmp_path, "sr:SR-001")
    set_focus(tmp_path, "task:T-002")

    assert get_focus(tmp_path) == "task:T-002"


def test_get_focus_returns_none_when_key_is_present_but_not_a_string(tmp_path: Path):
    path = _context_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"coherence_focus": 42}), encoding="utf-8")

    assert get_focus(tmp_path) is None


# --------------------------------------------------------------------------
# Cross-language sharing with pi-ext's session-policy.ts owner: set_focus
# must preserve every other key already on disk (the TS-owned schema keys),
# never clobber them.
# --------------------------------------------------------------------------


def test_set_focus_preserves_unrelated_keys_already_on_disk(tmp_path: Path):
    path = _context_path(tmp_path)
    path.parent.mkdir(parents=True)
    ts_owned_payload = {
        "schema": 1,
        "enabledFeeds": ["memory", "head", "ledger"],
        "memory": {"retentionDays": 30},
        "head": {"maxCommits": 5},
        "audit": {"maxEntries": 200},
        "updated_at": "2026-08-24T00:00:00.000Z",
    }
    path.write_text(json.dumps(ts_owned_payload), encoding="utf-8")

    set_focus(tmp_path, "bundle:B-1")

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["coherence_focus"] == "bundle:B-1"
    for key, value in ts_owned_payload.items():
        assert payload[key] == value


def test_clear_focus_preserves_unrelated_keys_already_on_disk(tmp_path: Path):
    path = _context_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps({"schema": 1, "enabledFeeds": ["memory"], "coherence_focus": "sr:SR-1"}),
        encoding="utf-8",
    )

    clear_focus(tmp_path)

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert "coherence_focus" not in payload
    assert payload["schema"] == 1
    assert payload["enabledFeeds"] == ["memory"]


def test_set_focus_writes_atomically_leaving_no_stray_temp_file(tmp_path: Path):
    set_focus(tmp_path, "sr:SR-001")

    factory_dir = tmp_path / ".pi" / "factory"
    names = {p.name for p in factory_dir.iterdir()}
    assert names == {"session-context.json"}


# --------------------------------------------------------------------------
# The atomic JSON location and repo-tracking status: this path is
# `.pi/factory/session-context.json`, and this repo's own .gitignore already
# excludes it -- set_focus/clear_focus must never fight that by writing
# anywhere else, and the file this module writes must stay untracked.
# --------------------------------------------------------------------------


def test_atomic_focus_storage_location_is_pi_factory_session_context_json(tmp_path: Path):
    set_focus(tmp_path, "sr:SR-001")

    assert (tmp_path / ".pi" / "factory" / "session-context.json").is_file()
    # No other top-level location was written.
    assert not (tmp_path / "sessions" / ".coherence-focus.json").exists()


def test_session_context_json_is_gitignored_in_this_repo():
    gitignore = (_PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert ".pi/factory/session-context.json" in gitignore.splitlines()


def test_set_focus_does_not_create_any_repository_tracked_file_changes(tmp_path: Path):
    """`coherence focus` operates on a caller-supplied session_root (here, an
    isolated tmp_path), so it can never touch this actual repository's
    working tree -- verified directly: nothing exists under tmp_path except
    the gitignored `.pi/factory/session-context.json` this call wrote."""
    set_focus(tmp_path, "sr:SR-001")

    written = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_file())
    assert written == [".pi/factory/session-context.json"]


# --------------------------------------------------------------------------
# CLI wiring: `coherence focus <scope-ref>` and `coherence focus --none`.
# --------------------------------------------------------------------------


def test_cli_focus_sets_scope_and_reports_it(tmp_path: Path):
    result = _run_coherence(
        "focus", "feat:FEAT-NAV-017", "--session-root", str(tmp_path), cwd=_PROJECT_ROOT
    )

    assert result.returncode == 0
    assert "feat:FEAT-NAV-017" in result.stdout
    assert get_focus(tmp_path) == "feat:FEAT-NAV-017"


def test_cli_focus_none_clears_scope(tmp_path: Path):
    set_focus(tmp_path, "sr:SR-001")

    result = _run_coherence("focus", "--none", "--session-root", str(tmp_path), cwd=_PROJECT_ROOT)

    assert result.returncode == 0
    assert get_focus(tmp_path) is None


def test_cli_focus_with_invalid_scope_ref_exits_nonzero_and_writes_nothing(tmp_path: Path):
    result = _run_coherence(
        "focus", "not-a-ref", "--session-root", str(tmp_path), cwd=_PROJECT_ROOT
    )

    assert result.returncode != 0
    assert not _context_path(tmp_path).exists()


def test_cli_focus_with_no_arguments_reports_current_focus_or_absence(tmp_path: Path):
    result_absent = _run_coherence("focus", "--session-root", str(tmp_path), cwd=_PROJECT_ROOT)
    assert result_absent.returncode == 0

    set_focus(tmp_path, "task:T-002")
    result_present = _run_coherence("focus", "--session-root", str(tmp_path), cwd=_PROJECT_ROOT)
    assert result_present.returncode == 0
    assert "task:T-002" in result_present.stdout


def test_focus_is_a_top_level_cli_group():
    from coherence import cli

    assert "focus" in cli.GROUPS
