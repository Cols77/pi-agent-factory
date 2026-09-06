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

This module also carries `program_start`/`program_token`: resolving which
token is the *actually-invoked program* in a segment (skipping leading
`VAR=value` assignments and a leading `uv run`) is a second thing both hooks
must never disagree about -- a segment cannot simultaneously "be" `coherence`
and "be" `python -m <adapter>`, so whichever check decides what a segment
*is* must be the one both hooks share, not two independently-written guesses.
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


def program_start(tokens: list[str]) -> int | None:
    """Index of the actually-invoked program in `tokens`: skips leading
    `VAR=value` assignments and a leading `uv run`. `None` if nothing is left
    to invoke after skipping (an empty or assignment-only segment)."""
    index = 0
    while index < len(tokens) and _looks_like_assignment(tokens[index]):
        index += 1
    if (
        index < len(tokens)
        and tokens[index] == "uv"
        and index + 1 < len(tokens)
        and tokens[index + 1] == "run"
    ):
        index += 2
    return index if index < len(tokens) else None


def program_token(tokens: list[str]) -> str | None:
    """The actually-invoked program token in `tokens`, or `None`."""
    index = program_start(tokens)
    return tokens[index] if index is not None else None


__all__ = ["program_start", "program_token", "segments", "tokenize"]
