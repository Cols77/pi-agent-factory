import pytest
from factory.orchestrator.pi_backend import _has_json_events_without_text_field, parse_pi_json

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
