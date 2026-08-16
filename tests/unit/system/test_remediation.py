import re
from pathlib import Path
from typing import get_args

import pytest

from factory.system.remediation import ABSENCE_STATES, REMEDIATION
from factory.trace.gaps import GapKind

pytestmark = pytest.mark.unit


def test_every_gap_kind_has_an_entry():
    missing = [k for k in get_args(GapKind) if k not in REMEDIATION]
    assert missing == []


def test_every_absence_state_has_an_entry():
    assert [s for s in ABSENCE_STATES if s not in REMEDIATION] == []


def test_no_entry_outside_gap_kinds_and_absence_states():
    known = set(get_args(GapKind)) | set(ABSENCE_STATES)
    assert set(REMEDIATION) - known == set()


def test_severity_is_absence_or_failure():
    assert all(e["severity"] in {"absence", "failure"} for e in REMEDIATION.values())


def test_only_id_and_ref_substitutions_are_used():
    # M8: nextStepBlock (system-comprehension.ts) substitutes {id}/{ref} in
    # every templated prose field, not just `command` -- checked here too so
    # a stray, unlisted token in `what_it_means`/`why_it_matters` (which
    # would leak into the rendered card as literal `{id}` text) fails the
    # same way an unknown token in `command` already does.
    for entry in REMEDIATION.values():
        for field in ("command", "what_it_means", "why_it_matters"):
            for token in re.findall(r"\{(\w+)\}", entry[field]):
                assert token in {"id", "ref"}, (entry["state"], field)


def test_every_slash_command_is_registered():
    src = Path("pi-ext/factory-watch/src")
    registered = set()
    for path in src.glob("*.ts"):
        registered |= set(
            re.findall(r'registerCommand\("([a-z0-9-]+)"', path.read_text(encoding="utf-8"))
        )
    for entry in REMEDIATION.values():
        if entry["command_kind"] != "slash":
            continue
        name = entry["command"].split()[0].lstrip("/")
        assert name in registered, f"unregistered slash command: /{name}"


def test_every_shell_command_names_a_real_subparser():
    for entry in REMEDIATION.values():
        if entry["command_kind"] != "shell":
            continue
        parts = entry["command"].split()
        module = parts[parts.index("-m") + 1]
        sub = parts[parts.index("-m") + 2]
        # src layout: the package lives under src/, not at the repo root.
        source = Path("src") / module.replace(".", "/") / "cli.py"
        text = source.read_text(encoding="utf-8")
        assert f'add_parser("{sub}"' in text, entry
        # Two-level commands (e.g. `factory.system bundle check`) must name a
        # nested subparser too. factory.system has no top-level `check`. But
        # the token right after `sub` is not always a nested subcommand: it
        # may be the `{id}`/`{ref}` substitution or a `<placeholder>` value
        # for a plain single-level command (e.g. `factory.trace link {id}
        # --satisfies <SR-id>`). Only a bare word -- no leading `-`, `{`, or
        # `<` -- is ever a real nested subcommand literal.
        if len(parts) > parts.index("-m") + 3:
            nested = parts[parts.index("-m") + 3]
            if not nested.startswith(("-", "{", "<")):
                # Scoped, not a flat substring search over the whole file:
                # find the variable `sub`'s own parser was assigned to, then
                # the subparsers object built from *that* variable, then look
                # for `nested` only on that object. A flat `f'add_parser(
                # "{nested}"' in text` search would also pass if `nested`
                # happened to match an unrelated top-level parser elsewhere
                # in the same cli.py.
                parent_match = re.search(
                    rf'(\w+)\s*=\s*\w+\.add_parser\("{re.escape(sub)}"', text
                )
                assert parent_match, entry
                parent_var = parent_match.group(1)
                nested_subparsers_match = re.search(
                    rf'(\w+)\s*=\s*{re.escape(parent_var)}\.add_subparsers\(', text
                )
                assert nested_subparsers_match, entry
                nested_var = nested_subparsers_match.group(1)
                assert f'{nested_var}.add_parser("{nested}"' in text, entry
