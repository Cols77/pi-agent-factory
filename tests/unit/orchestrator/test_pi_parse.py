import json
import subprocess
from pathlib import Path

import pytest
from factory.orchestrator.pi_backend import (
    PiAgentBackend,
    _build_command,
    _extract_snippet,
    _has_json_events_without_text_field,
    parse_pi_json,
)
from factory.orchestrator.types import AgentRole

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


# Regression: Pi's own CLI (dist/main.js's readPipedStdin) blocks forever
# waiting for stdin's "end" event whenever stdin is a non-TTY pipe with no
# writer -- exactly what happens when the orchestrator itself is spawned by
# factory-watch's launchInteractiveReview with stdio: ["pipe","pipe","pipe"]
# (kept open for the human-review decision handshake) and Popen here doesn't
# override stdin, so every per-role Pi subprocess inherits that same
# never-closed pipe. Each role subprocess never expects piped input, so it
# must get stdin=DEVNULL explicitly rather than inheriting the parent's.


class _FakeProc:
    def __init__(self, lines: list[str]) -> None:
        self.stdout = iter(lines)
        self.returncode = 0

    def wait(self) -> None:
        pass


def test_run_spawns_pi_subprocess_with_stdin_devnull(monkeypatch, tmp_path):
    captured_kwargs: dict = {}

    def _fake_popen(cmd, **kwargs):
        captured_kwargs.update(kwargs)
        return _FakeProc(["line1\n"])

    monkeypatch.setattr(subprocess, "Popen", _fake_popen)

    backend = PiAgentBackend(tmp_path, tmp_path / "ext.ts")
    backend.run(AgentRole.DEV, "hello")

    assert captured_kwargs.get("stdin") == subprocess.DEVNULL


def test_parse_session_id_extracts_id_from_session_event():
    from factory.orchestrator.pi_backend import parse_session_id
    stream = "\n".join([
        '{"type":"session","version":3,"id":"019f8ef3-6103-725c-997a-a9159325ebf1"}',
        '{"type":"message_end","message":{"role":"assistant","content":[]}}',
    ])
    assert parse_session_id(stream) == "019f8ef3-6103-725c-997a-a9159325ebf1"


def test_parse_session_id_returns_none_when_absent():
    from factory.orchestrator.pi_backend import parse_session_id
    assert parse_session_id('{"type":"message_end","message":{}}') is None
    assert parse_session_id("") is None


def test_run_populates_session_id(monkeypatch, tmp_path):
    from factory.orchestrator.pi_backend import PiAgentBackend
    from factory.orchestrator.types import AgentRole

    class _FakeProc:
        def __init__(self, lines):
            self.stdout = iter(lines)
            self.returncode = 0

        def wait(self):
            pass

    lines = [
        '{"type":"session","id":"abc-123"}\n',
        '{"type":"message_end","message":{"role":"assistant","content":[{"type":"text","text":"```json\\n{}\\n```"}]}}\n',
    ]
    monkeypatch.setattr(subprocess, "Popen", lambda cmd, **kw: _FakeProc(lines))
    result = PiAgentBackend(tmp_path, tmp_path / "ext.ts").run(AgentRole.DEV, "hi")
    assert result.session_id == "abc-123"


# deepseek via OpenRouter (openai-completions API, thinkingLevel high) emits the
# fenced ```json manifest inside a "thinking" block and produces NO "text"
# block -- parse_pi_json must still find it.
THINKING_STREAM = json.dumps({
    "type": "message_end",
    "message": {
        "role": "assistant",
        "content": [
            {"type": "thinking", "thinking": 'Building it.\n```json\n{"task_id": "T-9", "ok": true}\n```'},
            {"type": "toolCall", "id": "1", "name": "read", "arguments": "{}"},
        ],
    },
})


def test_parse_extracts_json_from_thinking_blocks():
    out = parse_pi_json(THINKING_STREAM)
    assert out["task_id"] == "T-9"
    assert out["ok"] is True


def test_thinking_only_message_is_not_flagged_as_missing_text():
    # A thinking block IS content; the field-mismatch diagnostic must not treat
    # a thinking-only assistant message as an empty response.
    assert _has_json_events_without_text_field(THINKING_STREAM) is False


# --- RC1: agent-subprocess timeouts (a stalled or runaway agent must not hang
# the orchestrator forever) -----------------------------------------------------

def test_drain_lines_yields_all_then_stops_without_timeout():
    from factory.orchestrator.pi_backend import _drain_lines

    fired: list[str] = []
    out = list(_drain_lines(iter(["a\n", "b\n"]), 5, 5, lambda r: fired.append(r)))
    assert out == ["a\n", "b\n"]
    assert fired == []  # ended normally, no timeout


def test_drain_lines_idle_timeout_kills_a_stalled_stream():
    import threading

    from factory.orchestrator.pi_backend import _drain_lines

    block = threading.Event()

    def stalled():
        yield "first\n"
        block.wait(5)  # stall: no further lines arrive

    fired: list[str] = []
    out = list(_drain_lines(stalled(), idle_timeout=0.15, total_timeout=5, on_timeout=fired.append))
    block.set()
    assert out == ["first\n"]
    assert fired == ["idle"]


def test_drain_lines_total_timeout_kills_a_runaway_stream():
    import threading
    import time as _t

    from factory.orchestrator.pi_backend import _drain_lines

    stop = threading.Event()

    def runaway():
        # Keeps streaming (never idle) -- only a total wall-clock bound can stop it.
        while not stop.is_set():
            yield "loop\n"
            _t.sleep(0.02)

    fired: list[str] = []
    out = list(_drain_lines(runaway(), idle_timeout=5, total_timeout=0.2, on_timeout=fired.append))
    stop.set()
    assert fired == ["total"]
    assert len(out) >= 1  # streamed some output before being cut off


def test_run_kills_and_fails_the_attempt_on_timeout(monkeypatch, tmp_path):
    import threading

    killed: list[bool] = []
    block = threading.Event()

    class _StallProc:
        def __init__(self) -> None:
            self.returncode = 0

            def gen():
                yield '{"type":"session","id":"sess-x"}\n'
                block.wait(5)  # then stall forever

            self.stdout = gen()

        def kill(self) -> None:
            killed.append(True)
            block.set()  # let the reader thread finish

        def wait(self) -> None:
            pass

    monkeypatch.setattr(subprocess, "Popen", lambda cmd, **kw: _StallProc())
    backend = PiAgentBackend(tmp_path, tmp_path / "ext.ts", idle_timeout_s=0.15, total_timeout_s=0.5)
    result = backend.run(AgentRole.DEV, "hi")

    assert result.ok is False
    assert "timeout" in result.raw
    assert killed == [True]
    assert result.session_id == "sess-x"  # captured before the stall
