"""`coherence route <text>` -- a deterministic, versioned phrase-to-intent
router (Increment 5 Task 4, spec plan
docs/superpowers/plans/2026-08-20-coherence-increment-5-status-focus-dispatcher.md,
"Approved deterministic-router amendment"; controller ruling on the plan's
own self-contradiction: this router-based routing is the live requirement,
not the superseded "documented refusal" stub).

`route_text(text)` is pure string matching -- no model call, no I/O, no
randomness. It exists so `/using-coherence <free text>`
(`pi-ext/factory-watch/src/coherence-command.ts`) can classify an argument
into one of the eight named intents without ever invoking a model API for
routing: a route is either produced by this deterministic table or it is
`None`, and `None` always falls through to the existing ranked-menu render
(never a silent guess).

Threshold rule (exact, from the plan amendment): normalise the input
(lowercase, collapse whitespace), sum the weights of every phrase in an
intent's table that matches (each phrase counted once per intent, not once
per occurrence -- a repeated word must not inflate a score past the
threshold on its own), and route to the intent with a **unique** maximum
score that is **>= `_THRESHOLD`**. A tie for the maximum, no intent
reaching any nonzero score, or a max below `_THRESHOLD` all return `None`.

Scope-ref extraction reuses the one existing `<kind>:<id>` parser
(`coherence.navigate.queries.parse_scope_ref`) and its legal-kind list
(`_SCOPE_KINDS`) -- this module does not define a second copy of either.
`route_text` operates on free text (a whole sentence), so it scans for
`<kind>:<id>`-shaped substrings and keeps the first one that
`parse_scope_ref` accepts; anything that fails to parse (wrong kind, no
identifier) is simply not a scope ref in this text, not an error.
"""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from enum import Enum

from coherence.navigate.queries import ScopeKindError, _SCOPE_KINDS, parse_scope_ref

# --------------------------------------------------------------------------
# Pure contract
# --------------------------------------------------------------------------


class Intent(str, Enum):
    """The eight intents named by the plan's original Task 4 text (still
    live; only the classifier mechanism -- deterministic phrases, not a
    model call -- was superseded)."""

    UNDERSTAND = "UNDERSTAND"
    VERIFY_CLAIM = "VERIFY_CLAIM"
    CLOSE_GAPS = "CLOSE_GAPS"
    AUTHOR_REQUIREMENTS = "AUTHOR_REQUIREMENTS"
    BUILD = "BUILD"
    RECOVER = "RECOVER"
    TRIAGE = "TRIAGE"
    TEACH = "TEACH"


@dataclass(frozen=True)
class RouteMatch:
    intent: Intent
    scope_ref: str | None
    score: int


_THRESHOLD = 3

# --------------------------------------------------------------------------
# Versioned phrase-to-intent table (v1).
#
# Design notes (own judgment call -- flagged for review, not a discovered
# contract):
#   - Each intent gets one or two "strong" phrases at or above `_THRESHOLD`
#     on their own (e.g. "close gaps", "interrupted run", "triage") so a
#     clear, short utterance routes unambiguously in one match.
#   - Each intent also gets a couple of weaker, more generic phrases (e.g.
#     bare "gap"/"gaps", bare "requirement") weighted below `_THRESHOLD` --
#     these only tip a score over the line in combination with a stronger
#     phrase, or with each other; alone they correctly return `None`
#     (the "below-threshold" case the amendment explicitly requires a test
#     for).
#   - Phrases are short (1-3 words) and matched as whole words/phrases
#     (`\b...\b`) against the normalised text, never as bare substrings --
#     "gap" must not fire inside "gaping".
#   - Some overlap across intents is deliberate, not a bug: e.g. "explain"
#     (UNDERSTAND) is a substring word of "explain how to" (TEACH) and will
#     co-fire with it, which is exactly the ambiguity the tie rule exists to
#     catch (a genuinely ambiguous utterance should be refused, not guessed).
# --------------------------------------------------------------------------

_PHRASE_TABLE: dict[Intent, tuple[tuple[str, int], ...]] = {
    Intent.UNDERSTAND: (
        ("what is", 3),
        ("how does", 3),
        ("brief me", 3),
        ("overview", 2),
        ("understand", 2),
        ("explain", 2),
    ),
    Intent.VERIFY_CLAIM: (
        ("verify", 3),
        ("is it true", 3),
        ("check claim", 3),
        ("validate", 2),
        ("prove", 2),
        ("confirm", 2),
    ),
    Intent.CLOSE_GAPS: (
        ("close gaps", 4),
        ("close the gap", 4),
        ("fill gap", 3),
        ("missing coverage", 3),
        ("gap", 1),
        ("gaps", 1),
    ),
    Intent.AUTHOR_REQUIREMENTS: (
        ("write requirement", 4),
        ("author requirement", 4),
        ("new requirement", 3),
        ("draft sr", 3),
        ("add requirement", 3),
        ("requirement", 1),
    ),
    Intent.BUILD: (
        ("build", 3),
        ("implement", 3),
        ("write code", 3),
        ("create feature", 3),
        ("ship", 2),
        ("develop", 2),
    ),
    Intent.RECOVER: (
        ("interrupted run", 4),
        ("recover", 3),
        ("resume", 3),
        ("continue run", 3),
        ("restart run", 3),
        ("pick up where", 3),
    ),
    Intent.TRIAGE: (
        ("triage", 4),
        ("what's broken", 3),
        ("diagnose", 3),
        ("investigate failure", 3),
        ("debug", 2),
        ("root cause", 2),
    ),
    Intent.TEACH: (
        ("teach me", 4),
        ("tutorial", 3),
        ("walk me through", 3),
        ("show me how", 3),
        ("explain how to", 3),
        ("learn", 2),
    ),
}


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _score_intent(normalized: str, phrases: tuple[tuple[str, int], ...]) -> int:
    total = 0
    for phrase, weight in phrases:
        if re.search(rf"\b{re.escape(phrase)}\b", normalized):
            total += weight
    return total


# Trailing punctuation that can attach to a scope ref matched out of a free
# sentence (e.g. "task:T-001," or "sr:SR-001.") but is never part of the id
# itself.
_TRAILING_PUNCTUATION = ".,;:!?)]}'\""

_SCOPE_REF_RE = re.compile(rf"\b(?:{'|'.join(_SCOPE_KINDS)}):\S+")


def _extract_scope_ref(text: str) -> str | None:
    """First `<kind>:<id>`-shaped substring of `text` that
    `parse_scope_ref` accepts, or `None`. Never re-implements
    `parse_scope_ref`'s own validation -- a candidate that fails it (an
    unrecognized kind never even matches the regex; an empty identifier
    after stripping trailing punctuation raises `ScopeKindError`) is simply
    skipped, not treated as a routing error."""
    for match in _SCOPE_REF_RE.finditer(text):
        candidate = match.group(0).rstrip(_TRAILING_PUNCTUATION)
        try:
            scope = parse_scope_ref(candidate)
        except ScopeKindError:
            continue
        return scope.ref
    return None


def route_text(text: str) -> RouteMatch | None:
    """Classify free text into one of the eight `Intent`s, or `None`.

    Pure and deterministic: same input always yields the same output, no
    I/O, no model call. See module docstring for the exact threshold rule.
    """
    normalized = _normalize(text)
    scores = {intent: _score_intent(normalized, phrases) for intent, phrases in _PHRASE_TABLE.items()}
    max_score = max(scores.values())
    if max_score < _THRESHOLD:
        return None
    winners = [intent for intent, score in scores.items() if score == max_score]
    if len(winners) != 1:
        return None
    return RouteMatch(intent=winners[0], scope_ref=_extract_scope_ref(text), score=max_score)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _route_payload(match: RouteMatch | None) -> dict | None:
    if match is None:
        return None
    return {"intent": match.intent.value, "scope_ref": match.scope_ref, "score": match.score}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="coherence-route")
    parser.add_argument("text")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    match = route_text(args.text)
    if args.json:
        print(json.dumps({"route": _route_payload(match)}))
    elif match is None:
        print("no route")
    else:
        scope_suffix = f" scope_ref={match.scope_ref}" if match.scope_ref is not None else ""
        print(f"{match.intent.value} score={match.score}{scope_suffix}")
    return 0


__all__ = ["Intent", "RouteMatch", "route_text", "main"]
