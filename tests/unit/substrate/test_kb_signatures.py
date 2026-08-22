# tests/unit/substrate/test_kb_signatures.py
from __future__ import annotations

from pathlib import Path

import pytest

from substrate.kb.retrieval import select_entries
from substrate.kb.signatures import canonical_failure_signatures

pytestmark = pytest.mark.unit

KB_DIR = Path(__file__).resolve().parents[3] / "kb"


def test_extracts_pytest_style_exception_line():
    signatures = canonical_failure_signatures(
        "E ConnectionResetError: connection reset by peer\n1 failed in 0.2s"
    )
    assert "ConnectionResetError: connection reset by peer" in signatures


def test_ignores_non_matching_noise_lines():
    signatures = canonical_failure_signatures(
        "E ConnectionResetError: connection reset by peer\n"
        "  at some/frame.py:12\n"
        "1 failed in 0.2s\n"
    )
    assert signatures == ["ConnectionResetError: connection reset by peer"]


def test_whitespace_is_collapsed():
    signatures = canonical_failure_signatures(
        "E   ConnectionResetError:   connection   reset   by   peer   "
    )
    assert signatures == ["ConnectionResetError: connection reset by peer"]


def test_output_is_deterministically_deduplicated():
    text = "\n".join(
        [
            "E ValueError: bad input",
            "E ValueError: bad input",
            "E ValueError:   bad input",  # same after whitespace collapse
            "E TypeError: wrong type",
        ]
    )
    signatures = canonical_failure_signatures(text)
    assert signatures == ["ValueError: bad input", "TypeError: wrong type"]
    # Deterministic across repeated calls on the same input.
    assert canonical_failure_signatures(text) == signatures


def test_output_is_capped_at_max_signatures():
    text = "\n".join(f"E Error{i}Error: failure number {i}" for i in range(20))
    signatures = canonical_failure_signatures(text, max_signatures=5)
    assert len(signatures) == 5
    assert signatures == [f"Error{i}Error: failure number {i}" for i in range(5)]


def test_secret_like_token_is_redacted_not_persisted():
    signatures = canonical_failure_signatures(
        "E AuthenticationError: request failed, token=abcd1234efgh5678secret"
    )
    assert len(signatures) == 1
    assert "abcd1234efgh5678secret" not in signatures[0]
    assert "[redacted]" in signatures[0]


def test_secret_like_password_is_redacted_not_persisted():
    signatures = canonical_failure_signatures(
        "E LoginError: could not authenticate, password=hunter2superSecret"
    )
    assert len(signatures) == 1
    assert "hunter2superSecret" not in signatures[0]
    assert "[redacted]" in signatures[0]


def test_credentialed_connection_string_is_redacted_not_persisted():
    signatures = canonical_failure_signatures(
        "E OperationalError: could not connect to postgres://svc_user:p4ssw0rd@db.internal:5432/app"
    )
    assert len(signatures) == 1
    assert "svc_user:p4ssw0rd" not in signatures[0]
    assert "[redacted]" in signatures[0]


def test_bearer_token_header_is_redacted_not_persisted():
    signatures = canonical_failure_signatures(
        "E HTTPError: 401 Client Error, header Authorization: Bearer sk-live-abc123xyz"
    )
    assert len(signatures) == 1
    assert "sk-live-abc123xyz" not in signatures[0]


def test_empty_input_returns_no_signatures():
    assert canonical_failure_signatures("") == []


def test_nonmatching_input_returns_no_signatures():
    assert canonical_failure_signatures("all tests passed\nno failures here\n") == []


def test_empty_signatures_selects_no_signature_only_entry():
    # kb-0001's scope also matches by file glob, so use an unrelated touched
    # file to isolate the signature-matching path: empty/nonmatching output
    # must not act as a wildcard that hits every active entry.
    signatures = canonical_failure_signatures("all tests passed\nno failures here\n")
    assert signatures == []
    ids = select_entries(KB_DIR, ["src/unrelated/thing.py"], signatures)
    assert ids == []
