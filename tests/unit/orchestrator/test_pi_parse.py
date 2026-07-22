from pathlib import Path

import pytest
from factory.orchestrator.pi_backend import (
    _build_command,
    _extract_snippet,
    _has_json_events_without_text_field,
    parse_pi_json,
)

pytestmark = pytest.mark.unit

# Minimal stand-in for Pi's json event stream: assistant text deltas carrying a json block.
STREAM = "\n".join([
    '{"type": "assistant_text", "text": "Here is the manifest:\\n```json\\n{\\"task_id\\": \\"T-001\\","}',
    '{"type": "assistant_text", "text": " \\"ok\\": true}\\n```\\nDone."}',
])


def test_parse_extracts_last_json_block():
    out = parse_pi_json(STREAM)
    assert out["task_id"] == "T-001"
    assert out["ok"] is True


def test_parse_returns_empty_when_no_block():
    assert parse_pi_json('{"type":"assistant_text","text":"no json here"}') == {}


# Finding 1+2 (final review): tests for the pure helper that detects the
# field-name-mismatch signature -- valid JSON events with no "text" field.


def test_field_mismatch_detected_when_events_have_no_text_field():
    stream = "\n".join([
        '{"type": "tool_call", "name": "read_file"}',
        '{"type": "tool_result", "value": "ok"}',
    ])
    assert _has_json_events_without_text_field(stream) is True


def test_field_mismatch_not_signaled_for_normal_empty_response():
    # Valid "text" fields present, just no fenced json block -> genuinely empty
    # response, not a field-name mismatch.
    stream = '{"type":"assistant_text","text":"no json here"}'
    assert _has_json_events_without_text_field(stream) is False


def test_field_mismatch_not_signaled_for_empty_stdout():
    assert _has_json_events_without_text_field("") is False


# _build_command: pure command-construction, testable without a real subprocess.


def test_build_command_omits_provider_and_model_when_unset():
    cmd = _build_command("hello", Path("ext.ts"), None, None)
    # Binary may resolve to full path on Windows (pi.CMD), so check args, not bin
    assert cmd[0].endswith("pi") or cmd[0].endswith("pi.CMD") or cmd[0].endswith("pi.cmd")
    assert cmd[1:] == ["-p", "hello", "--mode", "json", "--extension", "ext.ts"]


def test_build_command_includes_provider_and_model_when_set():
    cmd = _build_command("hello", Path("ext.ts"), "openrouter", "anthropic/claude-opus-4")
    assert cmd[0].endswith("pi") or cmd[0].endswith("pi.CMD") or cmd[0].endswith("pi.cmd")
    assert cmd[1:] == [
        "-p", "hello", "--mode", "json", "--extension", "ext.ts",
        "--provider", "openrouter",
        "--model", "anthropic/claude-opus-4",
    ]


def test_build_command_provider_only():
    cmd = _build_command("hello", Path("ext.ts"), "openrouter", None)
    assert "--provider" in cmd and "openrouter" in cmd
    assert "--model" not in cmd


def test_extract_snippet_returns_text_field():
    line = '{"type": "assistant_text", "text": "hello"}'
    assert _extract_snippet(line) == "hello"


def test_extract_snippet_empty_for_non_text_event():
    line = '{"type": "tool_call", "name": "read_file"}'
    assert _extract_snippet(line) == ""


def test_extract_snippet_empty_for_malformed_json():
    assert _extract_snippet("not json at all") == ""


def test_extract_snippet_empty_for_blank_line():
    assert _extract_snippet("   ") == ""
