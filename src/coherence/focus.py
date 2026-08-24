"""`coherence focus` -- persistent session focus scope (Increment 5 Task 2,
spec plan
docs/superpowers/plans/2026-08-20-coherence-increment-5-status-focus-dispatcher.md,
"Review Amendments" section):

    Focus is stored atomically in .pi/factory/session-context.json under a
    coherence_focus key, matching the existing session-policy owner; tests
    assert it is ignored/untracked.

This supersedes the earlier draft location (`sessions/.coherence-focus.json`)
named in the task's own Step 1 text.

Scope refs are validated by delegating to
`coherence.navigate.queries.parse_scope_ref` -- this module never
reimplements `<kind>:<id>` syntax checking. A malformed or unrecognized-kind
ref raises `coherence.navigate.queries.ScopeError` *before* any read or
write, so an invalid `set_focus` call creates no file and leaves an existing
file untouched.

CROSS-LANGUAGE ASYMMETRY WITH pi-ext/factory-watch/src/session-policy.ts
(documented here, not fixed -- fixing session-policy.ts is out of this
task's scope):

`.pi/factory/session-context.json` is also owned and written by
`session-policy.ts`'s `writeContext()` (called e.g. by `/factory-context`).
That function always writes a literal, fully-typed `SessionContext` object
(`schema`, `enabledFeeds`, `memory`, `head`, `audit`, `updated_at`) -- it does
NOT spread/preserve unrecognized extra keys found on disk. So: this module's
own reads and writes operate at the raw-JSON level and always preserve every
key already on disk (merge in/out only `coherence_focus`), so a `set_focus`/
`clear_focus` call from this side never destroys the TS side's keys. But the
reverse is not guarded: if a human runs `/factory-context` (or anything else
that calls `writeContext()`) after a focus was set, that write will silently
drop `coherence_focus`, because `writeContext()` does not know that key
exists. An occasional lost focus after `/factory-context` is therefore a
known, documented limitation of the shared file, not a bug in this module.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

from coherence.navigate.queries import ScopeError, parse_scope_ref

_CONTEXT_RELATIVE_PATH = Path(".pi") / "factory" / "session-context.json"
_FOCUS_KEY = "coherence_focus"


def _context_path(session_root: Path | str) -> Path:
    return Path(session_root) / _CONTEXT_RELATIVE_PATH


def _read_raw_context(path: Path) -> dict:
    """Read the shared context file at the raw-JSON level, tolerant of
    absence or corruption -- returns `{}` rather than raising, since a
    missing/corrupt file simply means "no other owner's keys to preserve
    yet", never a reason to fail a focus read or write."""
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return raw if isinstance(raw, dict) else {}


def _write_raw_context(path: Path, data: dict) -> None:
    """Atomic write: a temp file in the same directory, then an OS-level
    rename -- the same pattern session-policy.ts's own `writeContext()`
    uses (`.<stem>.tmp-<pid>-<ts>`), so a concurrent reader never observes a
    partially written file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, indent=2) + "\n"
    tmp_path = path.parent / f".{path.name}.tmp-{os.getpid()}-{int(time.time() * 1000)}"
    tmp_path.write_text(payload, encoding="utf-8")
    os.replace(tmp_path, path)


def get_focus(session_root: Path | str) -> str | None:
    """Return the currently persisted focus scope ref, or `None` when no
    focus is set: no context file at all, a file with no `coherence_focus`
    key, or a key present but not a string (defensively treated as absent
    rather than raised, since a malformed value here is another owner's
    problem, not this reader's crash)."""
    raw = _read_raw_context(_context_path(session_root))
    value = raw.get(_FOCUS_KEY)
    return value if isinstance(value, str) else None


def set_focus(session_root: Path | str, scope_ref: str) -> str:
    """Validate `scope_ref` and persist it as the session focus.

    Validation happens first, before any I/O: `parse_scope_ref` raises
    `ScopeKindError` (a `ScopeError`) for a malformed ref or one naming a
    kind that is not a legal top-level scope -- in that case nothing is
    written and any existing context file is left exactly as it was.

    A valid call reads the existing raw context (if any), merges in the new
    `coherence_focus` value, and writes the whole thing back atomically --
    every other key already on disk (including the TS-owned schema keys) is
    preserved unchanged.
    """
    parse_scope_ref(scope_ref)  # raises ScopeError; nothing written on failure
    path = _context_path(session_root)
    raw = _read_raw_context(path)
    raw[_FOCUS_KEY] = scope_ref
    _write_raw_context(path, raw)
    return scope_ref


def clear_focus(session_root: Path | str) -> None:
    """Remove any persisted session focus.

    A no-op -- no read, no write -- when no context file exists yet, or when
    it exists but carries no `coherence_focus` key: there is nothing to
    clear, so nothing is touched. Otherwise the key is removed and the rest
    of the file (every other owner's keys) is written back unchanged.
    """
    path = _context_path(session_root)
    if not path.is_file():
        return
    raw = _read_raw_context(path)
    if _FOCUS_KEY not in raw:
        return
    del raw[_FOCUS_KEY]
    _write_raw_context(path, raw)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="coherence-focus")
    parser.add_argument("scope_ref", nargs="?", default=None)
    parser.add_argument("--none", action="store_true", help="clear the current session focus")
    parser.add_argument("--session-root", default=Path("."), type=Path)
    args = parser.parse_args(argv)

    if args.none and args.scope_ref is not None:
        print("cannot pass both a scope-ref and --none")
        return 2

    if args.none:
        clear_focus(args.session_root)
        print("focus cleared")
        return 0

    if args.scope_ref is None:
        current = get_focus(args.session_root)
        print(current if current is not None else "no focus set")
        return 0

    try:
        set_focus(args.session_root, args.scope_ref)
    except ScopeError as exc:
        print(str(exc))
        return 1
    print(f"focus set: {args.scope_ref}")
    return 0


__all__ = ["get_focus", "set_focus", "clear_focus", "main"]
