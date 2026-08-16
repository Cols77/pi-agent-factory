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
from factory.orchestrator.types import AgentRole, InterruptionReason

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


def test_build_command_never_disables_context_files():
    # The subagent propagation contract: children must receive the root
    # AGENTS.md. If any code path ever tried to pass --no-context-files / -nc,
    # _build_command refuses rather than silently strip context.
    for bad in ("--no-context-files", "-nc"):
        with pytest.raises(ValueError, match="context files"):
            _build_command(bad, Path("ext.ts"), None, None)
    cmd = _build_command("hello", Path("ext.ts"), None, None)
    assert "--no-context-files" not in cmd and "-nc" not in cmd


def test_run_refuses_to_spawn_beyond_subagent_depth(monkeypatch, tmp_path):
    # A child whose environment is already at the recursion bound refuses to
    # spawn a deeper pi process instead of starting a runaway chain.
    from factory.orchestrator.pi_backend import (
        SUBAGENT_DEPTH_ENV,
        _SUBAGENT_DEPTH_LIMIT,
    )

    backend = PiAgentBackend(tmp_path, Path("ext.ts"))
    monkeypatch.setenv(SUBAGENT_DEPTH_ENV, str(_SUBAGENT_DEPTH_LIMIT))
    result = backend.run(AgentRole.DEV, "do it")
    assert result.ok is False
    assert "recursion bound" in result.raw


def test_run_propagates_incremented_depth_to_child(monkeypatch, tmp_path):
    from factory.orchestrator.pi_backend import SUBAGENT_DEPTH_ENV

    captured: dict = {}

    class FakeProc:
        returncode = 0
        stdout: list = []

        def wait(self):
            return 0

        def kill(self):
            pass

    def fake_popen(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["cwd"] = kwargs.get("cwd")
        captured["env"] = kwargs.get("env")
        captured["stdin"] = kwargs.get("stdin")
        return FakeProc()

    monkeypatch.setattr("subprocess.Popen", fake_popen)
    monkeypatch.delenv(SUBAGENT_DEPTH_ENV, raising=False)
    monkeypatch.setattr(
        "factory.orchestrator.pi_backend._DEFAULT_IDLE_TIMEOUT_S", 1.0
    )
    monkeypatch.setattr(
        "factory.orchestrator.pi_backend._DEFAULT_TOTAL_TIMEOUT_S", 1.0
    )

    backend = PiAgentBackend(tmp_path, Path("ext.ts"))
    result = backend.run(AgentRole.DEV, "do it")
    assert result.ok is True
    # Child starts in the PROJECT ROOT (so the root AGENTS.md loads).
    assert captured["cwd"] == tmp_path
    # Child gets an incremented depth marker so its own extension can refuse
    # deeper spawning, and never a context-file-disabling flag.
    assert captured["env"][SUBAGENT_DEPTH_ENV] == "1"
    assert "--no-context-files" not in captured["cmd"]
    assert "-nc" not in captured["cmd"]
    # stdin is DEVNULL so a long-lived inherited pipe cannot hang the child.
    assert captured["stdin"] == subprocess.DEVNULL


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


def test_parse_extracts_json_when_thinking_contains_literal_fence():
    """Regression: thinking block containing a literal ```json fragment (agent
    quoting the prompt) must not confuse the regex. The real JSON is in the
    text block and must be the one extracted.
    """
    stream = json.dumps({
        "type": "message_end",
        "message": {
            "role": "assistant",
            "content": [
                {
                    "type": "thinking",
                    "thinking": 'The role says "Emit ONLY a fenced ```json block". I\'ll do that.\n\n',
                },
                {
                    "type": "text",
                    "text": 'Here it is:\n```json\n{"dod_met": true, "findings": []}\n```\n',
                },
            ],
        },
    })
    out = parse_pi_json(stream)
    assert out["dod_met"] is True
    assert out["findings"] == []


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

def test_classify_interruption_uses_explicit_provider_signals_only():
    from factory.orchestrator.pi_backend import classify_interruption

    provider_error = json.dumps({
        "type": "provider_error", "message": "maximum context length exceeded"
    })
    assert classify_interruption(1, provider_error) is InterruptionReason.CONTEXT_LIMIT
    stop_event = json.dumps({"type": "agent_end", "reason": "context_limit"})
    assert classify_interruption(0, stop_event) is InterruptionReason.CONTEXT_LIMIT


def test_classify_interruption_keeps_timeouts_and_process_exits_distinct():
    from factory.orchestrator.pi_backend import classify_interruption

    assert classify_interruption(-9, "", "idle") is InterruptionReason.IDLE_TIMEOUT
    assert classify_interruption(-9, "", "total") is InterruptionReason.TOTAL_TIMEOUT
    assert classify_interruption(7, "unknown crash") is InterruptionReason.PROCESS_EXIT
    assert classify_interruption(0, "") is None


def test_classify_interruption_does_not_treat_assistant_prose_as_a_signal():
    from factory.orchestrator.pi_backend import classify_interruption

    prose = json.dumps({
        "type": "message_end",
        "message": {
            "role": "assistant",
            "content": [{"type": "text", "text": "We should consider the token limit."}],
        },
    })
    assert classify_interruption(0, prose) is None


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
