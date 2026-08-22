# src/substrate/kb/signatures.py
"""Extract canonical failure signatures from gate/test failure output.

Turns free-form CI/test/gate stdout+stderr text into a small, deterministic
set of "signature" strings suitable for `select_entries`'s
`scope.error_signatures` substring matching, or for authoring a new KB
entry's `scope.error_signatures` list by hand.

This module only extracts candidate text -- it never decides whether a gate
passed or failed, and it never writes anything to the KB itself. Wiring
extracted signatures into a gate outcome is exclusively factory's job
(Task 4 of this plan).

Design notes (heuristic, not exhaustive):

- We target the one shape that reliably identifies a failure across
  Python tracebacks, pytest's short summary ("E   SomeError: msg" /
  "FAILED ...") and most other language tracebacks that follow the
  "Identifier: message" convention: a line whose non-whitespace prefix
  looks like an exception/error class name, followed by ": " and a
  message. This deliberately ignores stack frames, file paths, and
  free-form log noise, which are highly run-specific and would defeat
  deduplication across runs.
- Lines are whitespace-collapsed (internal runs of whitespace -> one
  space, leading/trailing stripped) before dedup, so cosmetic differences
  in indentation or column alignment do not produce distinct "signatures"
  for what is really the same failure.
- Output is deduplicated while preserving first-seen order (a plain
  ``dict`` used as an ordered set), so results are deterministic for a
  given input and stable across repeated runs of the same failure.
- Output is capped at `max_signatures` (default 10) to keep KB scope
  entries small and to bound how much of a giant failure log gets carried
  forward as "signature" text.
- Secret-like substrings (API keys/tokens, passwords, bearer/basic auth
  headers, and connection strings embedding user:pass credentials) are
  redacted to a fixed placeholder before a signature is ever returned, so
  a canonical failure signature is safe to persist as a new KB fact -- it
  never carries a live credential pulled from failure output.
"""
from __future__ import annotations

import re

# An "Identifier: message" line, optionally prefixed by pytest's "E " / "F "
# failure marker (e.g. "E   ConnectionResetError: connection reset by
# peer"). The identifier may be dotted (module-qualified, e.g.
# "requests.exceptions.ConnectionError") and end in a common
# exception/failure-ish suffix -- this keeps the pattern from matching
# arbitrary "key: value" log lines that aren't failures.
_EXCEPTION_LINE = re.compile(
    r"^(?:[EF]\s+)?"
    r"([A-Za-z_][\w.]*(?:Error|Exception|Warning|Fault|Failure|Timeout))"
    r":\s*(.+)$"
)

# Secret-like substrings to redact before a signature is returned. Kept
# deliberately narrow (named-credential key=value pairs, bearer/basic auth
# headers, and scheme://user:pass@host connection strings) rather than a
# broad "any long opaque token" rule, which would also redact legitimate
# hashes/ids and make signatures useless for matching.
_SECRET_PATTERNS = [
    # Auth headers first: "Authorization: Bearer <token>" must redact the
    # whole "Bearer <token>" span, not just the "Authorization: Bearer"
    # prefix (which the named key=value pattern below would otherwise
    # match, leaving the token itself dangling and unredacted).
    re.compile(r"(?i)\b(?:bearer|basic)\s+\S+"),
    re.compile(
        r"(?i)\b(?:api[_-]?key|access[_-]?key|secret|password|passwd|token|"
        r"authorization)\b\s*[:=]\s*\S+"
    ),
    # scheme://user:pass@host -- credential-bearing connection strings.
    re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://[^\s@/:]+:[^\s@/:]+@\S+"),
]

_REDACTED = "[redacted]"

DEFAULT_MAX_SIGNATURES = 10


def _redact_secrets(text: str) -> str:
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub(_REDACTED, text)
    return text


# Public alias: other modules (e.g. factory.orchestrator.backends, redacting
# GateRun.output before it is serialized into a durable session record) need
# the same secret-redaction behavior applied to raw gate output, not just to
# already-extracted signature lines. Reuse the implementation above rather
# than duplicating the regex list.
redact_secrets = _redact_secrets


def _collapse_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def canonical_failure_signatures(
    text: str, *, max_signatures: int = DEFAULT_MAX_SIGNATURES
) -> list[str]:
    """Extract stable, deduplicated failure signature lines from `text`.

    Returns an empty list for empty or non-matching input -- callers (e.g.
    `select_entries`) treat an empty signature list as "no signature hit",
    never as a wildcard match.
    """
    if not text:
        return []

    seen: dict[str, None] = {}
    for raw_line in text.splitlines():
        match = _EXCEPTION_LINE.match(raw_line.strip())
        if not match:
            continue
        exc_name, message = match.groups()
        signature = _collapse_whitespace(f"{exc_name}: {message}")
        signature = _redact_secrets(signature)
        if signature and signature not in seen:
            seen[signature] = None
        if len(seen) >= max_signatures:
            break

    return list(seen.keys())
