"""`coherence explain <term-or-id>` -- vocabulary-only lookup, nothing else
(Increment 5 Task 2, spec plan
docs/superpowers/plans/2026-08-20-coherence-increment-5-status-focus-dispatcher.md).

"Term-or-id" names the lookup key: one of
`coherence.navigate.vocabulary.VOCABULARY`'s own dict keys (e.g.
`"recorded"`, `"derived"`, `"strong"`). There is no separate artifact-id
lookup path -- this module reads the existing vocabulary data only, via
`coherence.navigate.vocabulary.build_vocabulary`, and never reimplements or
duplicates it. An unrecognized key is rejected outright.
"""
from __future__ import annotations

import argparse
import json

from coherence.navigate.vocabulary import build_vocabulary


class UnknownTermError(KeyError):
    """`term` does not match any key in the vocabulary."""


def explain_term(term: str) -> dict:
    """Return the vocabulary entry for `term`.

    Delegates entirely to `build_vocabulary()` (which itself only wraps the
    module-level `VOCABULARY` dict) -- this function performs no lookup
    logic of its own beyond the key membership check. Raises
    `UnknownTermError` for any `term` not among the vocabulary's own keys.
    """
    terms = build_vocabulary()["terms"]
    if term not in terms:
        raise UnknownTermError(term)
    return terms[term]


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="coherence-explain")
    parser.add_argument("term")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)

    try:
        entry = explain_term(args.term)
    except UnknownTermError:
        print(f"unrecognized term: {args.term!r}")
        return 1

    if args.as_json:
        print(json.dumps(entry, indent=2))
    else:
        print(f"{entry['term']} ({entry['group']}): {entry['gloss']}")
        print(entry["definition"])
    return 0


__all__ = ["explain_term", "UnknownTermError", "main"]
