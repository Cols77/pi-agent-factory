import pytest
from factory.orchestrator.pi_backend import parse_pi_json

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
