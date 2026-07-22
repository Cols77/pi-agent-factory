import json
from pathlib import Path

import pytest
from factory.orchestrator.pi_backend import (
    _build_command,
    _extract_snippet,
    _has_json_events_without_text_field,
    parse_pi_json,
)

pytestmark = pytest.mark.unit

# Minimal stand-in for Pi's real v3 json event stream: one "message_end" event
# per complete assistant message, each carrying its full text in
# message.content[].text. Two events here (as if two separate assistant
# turns) whose concatenated text spans a fenced json block, matching how
# parse_pi_json is expected to reconstruct text across multiple messages.
STREAM = "\n".join([
    json.dumps({
        "type": "message_end",
        "message": {
            "role": "assistant",
            "content": [{"type": "text", "text": 'Here is the manifest:\n```json\n{"task_id": "T-001",'}],
        },
    }),
    json.dumps({
        "type": "message_end",
        "message": {
            "role": "assistant",
            "content": [{"type": "text", "text": ' "ok": true}\n```\nDone.'}],
        },
    }),
])


def test_parse_extracts_last_json_block():
    out = parse_pi_json(STREAM)
    assert out["task_id"] == "T-001"
    assert out["ok"] is True


def test_parse_returns_empty_when_no_block():
    line = json.dumps({
        "type": "message_end",
        "message": {"role": "assistant", "content": [{"type": "text", "text": "no json here"}]},
    })
    assert parse_pi_json(line) == {}


# Finding 1+2 (final review): tests for the pure helper that detects the
# field-name-mismatch signature -- valid JSON events with no assistant text.


def test_field_mismatch_detected_when_events_have_no_text_field():
    stream = "\n".join([
        '{"type": "tool_call", "name": "read_file"}',
        '{"type": "tool_result", "value": "ok"}',
    ])
    assert _has_json_events_without_text_field(stream) is True


def test_field_mismatch_not_signaled_for_normal_empty_response():
    # Valid assistant text present, just no fenced json block -> genuinely empty
    # response, not a field-name mismatch.
    stream = json.dumps({
        "type": "message_end",
        "message": {"role": "assistant", "content": [{"type": "text", "text": "no json here"}]},
    })
    assert _has_json_events_without_text_field(stream) is False


def test_field_mismatch_not_signaled_for_empty_stdout():
    assert _has_json_events_without_text_field("") is False


# _build_command: pure command-construction, testable without a real subprocess.


def test_build_command_omits_provider_and_model_when_unset():
    cmd = _build_command("hello", Path("ext.ts"), None, None)
    # Binary may resolve to full path on Windows (pi.CMD), so check args, not bin
    assert cmd[0].endswith("pi") or cmd[0].endswith("pi.CMD") or cmd[0].endswith("pi.cmd")
    assert cmd[1:] == ["-p", "hello", "--mode", "json", "--extension", "ext.ts"]


def test_build_command_uses_at_file_when_prompt_file_given():
    cmd = _build_command("hello", Path("ext.ts"), None, None, prompt_file="/tmp/p.md")
    assert cmd[0].endswith("pi") or cmd[0].endswith("pi.CMD") or cmd[0].endswith("pi.cmd")
    assert cmd[1:] == ["-p", "@/tmp/p.md", "--mode", "json", "--extension", "ext.ts"]


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


def test_extract_snippet_returns_delta_from_text_delta_event():
    line = json.dumps({
        "type": "message_update",
        "assistantMessageEvent": {"type": "text_delta", "contentIndex": 0, "delta": "hello"},
    })
    assert _extract_snippet(line) == "hello"


def test_extract_snippet_empty_for_non_text_delta_message_update():
    line = json.dumps({
        "type": "message_update",
        "assistantMessageEvent": {"type": "text_start", "contentIndex": 0},
    })
    assert _extract_snippet(line) == ""


def test_extract_snippet_empty_for_non_text_event():
    line = '{"type": "tool_call", "name": "read_file"}'
    assert _extract_snippet(line) == ""


def test_extract_snippet_empty_for_malformed_json():
    assert _extract_snippet("not json at all") == ""


def test_extract_snippet_empty_for_blank_line():
    assert _extract_snippet("   ") == ""
