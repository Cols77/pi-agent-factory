"""Quote-aware splitting of a shell command into independently-run segments.

Shared by `coherence_channel_guard.py` and `coherence_finalize_gate.py` so the
two hooks can never disagree about where one shell command ends and the next
begins.

A naive `str.split` on `;`, `&&`, `||`, `|`, or newline is unsafe: any of
those characters can appear *inside* a quoted argument (for example Python
code passed via `python -c "...; ..."`) without being a real segment
separator. `shlex.shlex` with `punctuation_chars` set understands quoting, so
it is used here instead -- a separator token is only treated as a boundary
when shlex itself, not a blind regex, decided it was outside any quotes.

This module also carries `program_start`/`program_token`/`program_name`:
resolving which token is the *actually-invoked program* in a segment
(skipping leading `VAR=value` assignments, a leading `(` subshell wrapper,
pass-through wrapper commands like `env`/`command`, and a leading `uv run`)
is a second thing both hooks must never disagree about -- a segment cannot
simultaneously "be" `coherence` and "be" `python -m <adapter>`, so whichever
check decides what a segment *is* must be the one both hooks share, not two
independently-written guesses. `program_name` additionally normalizes that
token to a comparable basename (final path component, lowercased, a known
interpreter suffix stripped) so `/usr/bin/python3`, `python3.exe`, and
`python3` are all recognized identically -- a program is not exempt from a
check just because of how the path to it was spelled.
"""

from __future__ import annotations

import shlex

#: Characters shlex should treat as their own tokens rather than folding into
#: adjacent words. `\n` is included (see `_tokenize`) so a newline-separated
#: compound command segments the same way `;` does.
_PUNCTUATION = ";&|()<>\n"

#: Tokens that end one segment and start the next.
_SEPARATOR_TOKENS = frozenset({";", "&&", "||", "|", "\n", "&"})


def tokenize(command: str) -> list[str] | None:
    """Tokenize `command`, respecting quoting. `None` if it cannot be parsed
    as shell words (e.g. unbalanced quotes) -- callers should fail toward
    whichever side is safe for their own check rather than guess."""
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=_PUNCTUATION)
        lexer.whitespace_split = True
        # Keep `\n` out of plain whitespace so it survives as its own
        # `_PUNCTUATION` token instead of silently merging adjacent words.
        lexer.whitespace = " \t\r"
        return list(lexer)
    except ValueError:
        return None


def segments(command: str) -> list[list[str]] | None:
    """Split `command` into the argv token lists of each independently-run
    segment. `None` if `command` cannot be tokenized at all."""
    tokens = tokenize(command)
    if tokens is None:
        return None
    result: list[list[str]] = []
    current: list[str] = []
    for token in tokens:
        if token in _SEPARATOR_TOKENS:
            result.append(current)
            current = []
        else:
            current.append(token)
    result.append(current)
    return result


def _looks_like_assignment(token: str) -> bool:
    name, sep, _ = token.partition("=")
    return bool(sep) and (name[:1].isalpha() or name[:1] == "_") and name.replace("_", "").isalnum()


#: Interpreter/executable suffixes stripped when normalizing a token to a
#: comparable program name (Windows spells an executable with one of these;
#: POSIX systems normally do not, so an absent suffix is left alone).
_INTERPRETER_SUFFIXES = (".exe", ".bat", ".cmd")

#: Commands that re-invoke another program without themselves being the
#: program a check cares about -- skipped, along with their own leading
#: flags/assignments, so the program *they* invoke is what gets checked.
_PASS_THROUGH_WRAPPERS = frozenset({"env", "command"})


def program_basename(token: str) -> str:
    """Normalize a single token to a comparable program name: the final path
    component, lowercased, with a known interpreter suffix stripped -- so an
    absolute path or an explicit `.exe` spelling is recognized the same way
    as the bare program name. Exposed (not just used internally by
    `program_name`) so a caller that already has the specific token it wants
    to classify (for example the token immediately after `-m`) need not
    re-derive `program_start` just to normalize it."""
    name = token.replace("\\", "/").rsplit("/", 1)[-1].lower()
    for suffix in _INTERPRETER_SUFFIXES:
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


def program_start(tokens: list[str]) -> int | None:
    """Index of the actually-invoked program in `tokens`.

    Skips, in any combination and order: leading `VAR=value` assignments; a
    leading `(` -- a real shell actually runs the wrapped command when a
    segment is parenthesized, so the `(` token itself must never be mistaken
    for the program; and pass-through wrapper commands (`env`, `command`)
    together with their own leading flags/assignments, since those also
    re-invoke another program rather than being the program themselves. A
    leading `uv run` (by normalized name, so `/usr/bin/uv run ...` is
    recognized identically to `uv run ...`) is skipped last. `None` if
    nothing is left to invoke after skipping (an empty, or
    assignment/wrapper-only, segment).
    """
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token == "(":
            index += 1
            continue
        if _looks_like_assignment(token):
            index += 1
            continue
        if program_basename(token) in _PASS_THROUGH_WRAPPERS:
            index += 1
            while index < len(tokens) and (
                tokens[index].startswith("-") or _looks_like_assignment(tokens[index])
            ):
                index += 1
            continue
        break
    if (
        index < len(tokens)
        and program_basename(tokens[index]) == "uv"
        and index + 1 < len(tokens)
        and tokens[index + 1] == "run"
    ):
        index += 2
    return index if index < len(tokens) else None


def program_token(tokens: list[str]) -> str | None:
    """The actually-invoked program token in `tokens`, exactly as spelled in
    the command (not normalized), or `None`."""
    index = program_start(tokens)
    return tokens[index] if index is not None else None


def program_name(tokens: list[str]) -> str | None:
    """The actually-invoked program in `tokens`, normalized to a comparable
    basename (see `program_basename`) so `/usr/bin/python3`, `python3.exe`, and
    `python3` all compare equal. `None` if there is no invoked program."""
    token = program_token(tokens)
    return program_basename(token) if token is not None else None


__all__ = [
    "program_basename",
    "program_name",
    "program_start",
    "program_token",
    "segments",
    "tokenize",
]
