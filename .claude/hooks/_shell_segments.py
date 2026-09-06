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


__all__ = ["segments", "tokenize"]
